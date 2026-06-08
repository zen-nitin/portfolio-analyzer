"""
AI insights router.

POST /api/insights/watchlist-suggestions        {count}
POST /api/insights/watchlist-suggestions/batch  {count}              -> {batch_id, status}
POST /api/insights/recommendation               {symbol, exchange}
POST /api/insights/portfolio-review             {account_id, target, messages}
POST /api/insights/portfolio-review/batch       {account_id, target} -> {batch_id, status}
GET  /api/insights/batch/{batch_id}             ?feature=&target=    -> {status, result?}
GET  /api/insights/analysis/{symbol}            ?exchange=NSE
GET  /api/ai/providers

The batch routes send the two non-interactive features (daily review, watchlist
suggestions) through the provider's Batch API (~50% cheaper, async). They fall
back to a synchronous result inline when AI_BATCH is off or the active provider
has no batch support, so the frontend works identically either way.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai import registry as ai_registry
from app.config import settings
from app.database import get_db
from app.models.account import Account
from app.models.holding import Holding
from app.models.watchlist import WatchlistItem
from app.services import insights as insights_service
from app.services.portfolio import (
    build_summary,
    get_holdings_for_accounts,
    get_ledger_for_accounts,
    get_transactions_for_accounts,
    resolve_free_cash_override,
)

router = APIRouter(tags=["insights"])


# ------------------------------------------------------------------
# Request / response schemas (inline – small enough)
# ------------------------------------------------------------------

class WatchlistSuggestionsRequest(BaseModel):
    count: int = 10


class RecommendationRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"


class ReviewMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class PortfolioReviewRequest(BaseModel):
    account_id: Optional[int] = None
    target_profit_pct: float = 75.0
    messages: list[ReviewMessage] = []


class AIProviderInfo(BaseModel):
    name: str
    active: bool
    configured: bool


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _all_active_holdings(db: Session) -> list[Holding]:
    active_ids = [a.id for a in db.query(Account).filter(Account.is_active == True).all()]  # noqa: E712
    if not active_ids:
        return []
    return db.query(Holding).filter(Holding.account_id.in_(active_ids)).all()


def _review_inputs(db: Session, account_id: Optional[int]):
    """Gather (holdings, watchlist, summary) for a portfolio review.

    Shared by the synchronous review route and the batch submit route.
    """
    if account_id is not None:
        account_ids = [account_id]
    else:
        active = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        account_ids = [a.id for a in active]

    holdings = get_holdings_for_accounts(db, account_ids)
    transactions = get_transactions_for_accounts(db, account_ids)
    ledger = get_ledger_for_accounts(db, account_ids)
    free_cash_override = resolve_free_cash_override(db, account_ids, ledger)
    summary = build_summary(holdings, transactions, ledger, free_cash_override)
    watchlist = db.query(WatchlistItem).all()
    return holdings, watchlist, summary


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.post("/api/insights/watchlist-suggestions")
def watchlist_suggestions(
    body: WatchlistSuggestionsRequest,
    db: Session = Depends(get_db),
):
    """AI-powered watchlist suggestions based on current portfolio."""
    holdings = _all_active_holdings(db)
    watchlist = db.query(WatchlistItem).all()
    return insights_service.watchlist_suggestions(body.count, holdings, watchlist)


@router.post("/api/insights/recommendation")
def get_recommendation(
    body: RecommendationRequest,
    db: Session = Depends(get_db),
):
    """BUY/SELL/HOLD recommendation for a symbol."""
    holdings = _all_active_holdings(db)
    return insights_service.recommendation(body.symbol, body.exchange, holdings)


@router.post("/api/insights/portfolio-review")
def portfolio_review(
    body: PortfolioReviewRequest,
    db: Session = Depends(get_db),
):
    """Review all holdings + watchlist against an FY profit goal.

    Injects the current portfolio standing (invested, value, P&L, XIRR) and the
    target so the AI reasons from where the portfolio actually stands, then
    returns a per-stock BUY/SELL/HOLD call plus overall commentary.

    Synchronous (real-time) — used for chat follow-ups. The initial daily review
    goes through the batch route below.
    """
    holdings, watchlist, summary = _review_inputs(db, body.account_id)
    return insights_service.portfolio_review(
        holdings, watchlist, summary, body.target_profit_pct, messages=body.messages
    )


@router.get("/api/insights/analysis/{symbol}")
def get_analysis(
    symbol: str,
    exchange: Optional[str] = Query("NSE"),
    db: Session = Depends(get_db),
):
    """Comprehensive AI analysis for a symbol."""
    holdings = _all_active_holdings(db)
    return insights_service.analysis(symbol.upper(), exchange or "NSE", holdings)


# ------------------------------------------------------------------
# Batch routes (~50% cheaper, asynchronous) for the two non-interactive
# features. Submit -> poll -> result. Fall back to a synchronous result inline
# when AI_BATCH is off or the active provider has no batch support.
# ------------------------------------------------------------------

def _batch_enabled(provider) -> bool:
    return settings.AI_BATCH and getattr(provider, "supports_batch", False)


@router.post("/api/insights/portfolio-review/batch")
def submit_portfolio_review_batch(
    body: PortfolioReviewRequest,
    db: Session = Depends(get_db),
):
    """Submit the INITIAL daily review as a batch job (cheaper, async).

    Returns ``{batch_id, status: "pending"}`` while the batch runs. When batch
    mode is unavailable, runs synchronously and returns
    ``{batch_id: null, status: "completed", result}``.
    """
    holdings, watchlist, summary = _review_inputs(db, body.account_id)
    provider = insights_service._require_provider()  # raises 503 if unconfigured

    if not _batch_enabled(provider):
        result = insights_service.portfolio_review(
            holdings, watchlist, summary, body.target_profit_pct
        )
        return {"batch_id": None, "status": "completed", "result": result}

    system, user, schema = insights_service.build_portfolio_review_request(
        provider, holdings, watchlist, summary, body.target_profit_pct
    )
    batch_id = provider.submit_batch(
        [{"custom_id": "portfolio_review", "system": system, "user": user, "json_schema": schema}]
    )
    return {"batch_id": batch_id, "status": "pending"}


@router.post("/api/insights/watchlist-suggestions/batch")
def submit_watchlist_suggestions_batch(
    body: WatchlistSuggestionsRequest,
    db: Session = Depends(get_db),
):
    """Submit watchlist suggestions as a batch job (cheaper, async)."""
    holdings = _all_active_holdings(db)
    watchlist = db.query(WatchlistItem).all()
    provider = insights_service._require_provider()

    if not _batch_enabled(provider):
        result = insights_service.watchlist_suggestions(body.count, holdings, watchlist)
        return {"batch_id": None, "status": "completed", "result": result}

    system, user, schema = insights_service.build_watchlist_suggestions_request(
        provider, body.count, holdings, watchlist
    )
    batch_id = provider.submit_batch(
        [{"custom_id": "watchlist_suggestions", "system": system, "user": user, "json_schema": schema}]
    )
    return {"batch_id": batch_id, "status": "pending"}


@router.post("/api/insights/portfolio-review/prompt")
def portfolio_review_prompt(
    body: PortfolioReviewRequest,
    db: Session = Depends(get_db),
):
    """Return the assembled portfolio-review prompt for pasting into ChatGPT/Claude.

    Requires NO AI provider — lets the user generate on their own subscription
    and paste the JSON back. Same prompt the app would send (minus web research,
    which the external model can do itself).
    """
    holdings, watchlist, summary = _review_inputs(db, body.account_id)
    return {
        "prompt": insights_service.external_review_prompt(
            holdings, watchlist, summary, body.target_profit_pct
        )
    }


@router.post("/api/insights/watchlist-suggestions/prompt")
def watchlist_suggestions_prompt(
    body: WatchlistSuggestionsRequest,
    db: Session = Depends(get_db),
):
    """Return the assembled watchlist-suggestions prompt for ChatGPT/Claude."""
    holdings = _all_active_holdings(db)
    watchlist = db.query(WatchlistItem).all()
    return {
        "prompt": insights_service.external_watchlist_prompt(body.count, holdings, watchlist)
    }


@router.get("/api/insights/batch/{batch_id}")
def get_batch_job(
    batch_id: str,
    feature: str = Query(..., description="portfolio_review | watchlist_suggestions"),
    target_profit_pct: float = Query(75.0),
):
    """Poll a batch job; when completed, return the feature-shaped result."""
    provider = insights_service._require_provider()
    if not getattr(provider, "supports_batch", False):
        raise HTTPException(
            status_code=503, detail="Active AI provider does not support batch mode."
        )

    poll = provider.poll_batch(batch_id)
    status = poll.get("status", "pending")
    if status != "completed":
        return {"batch_id": batch_id, "status": status, "error": poll.get("error")}

    raw = (poll.get("results") or {}).get(feature)
    if feature == "portfolio_review":
        result = insights_service.shape_portfolio_review_result(raw or {}, target_profit_pct)
    elif feature == "watchlist_suggestions":
        result = insights_service.shape_watchlist_result(raw or {})
    else:
        result = raw
    return {"batch_id": batch_id, "status": "completed", "result": result}


@router.get("/api/ai/providers", response_model=list[AIProviderInfo])
def list_ai_providers():
    """List all known AI providers with active/configured flags."""
    return ai_registry.list_providers()
