"""
AI insights router — PROMPT-ONLY.

The app does not call any AI model. These endpoints assemble a self-contained
prompt (with the user's live portfolio context) for the user to paste into
Claude/ChatGPT, which runs its own subagents, fetches Yahoo Finance data,
researches the latest news, and returns JSON. The frontend ingests that pasted
JSON.

POST /api/insights/watchlist-suggestions/prompt  {count}             -> {prompt}
POST /api/insights/portfolio-review/prompt        {account_id, target} -> {prompt}
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
# Request schemas
# ------------------------------------------------------------------

class WatchlistSuggestionsRequest(BaseModel):
    count: int = 10


class PortfolioReviewRequest(BaseModel):
    account_id: Optional[int] = None
    target_profit_pct: float = 75.0


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _all_active_holdings(db: Session) -> list[Holding]:
    active_ids = [a.id for a in db.query(Account).filter(Account.is_active == True).all()]  # noqa: E712
    if not active_ids:
        return []
    return db.query(Holding).filter(Holding.account_id.in_(active_ids)).all()


def _review_inputs(db: Session, account_id: Optional[int]):
    """Gather (holdings, watchlist, summary) for a portfolio review prompt."""
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
# Prompt routes — assemble a prompt to run in Claude/ChatGPT
# ------------------------------------------------------------------

@router.post("/api/insights/watchlist-suggestions/prompt")
def watchlist_suggestions_prompt(
    body: WatchlistSuggestionsRequest,
    db: Session = Depends(get_db),
):
    """Return the watchlist-suggestions prompt to paste into Claude/ChatGPT."""
    holdings = _all_active_holdings(db)
    watchlist = db.query(WatchlistItem).all()
    return {"prompt": insights_service.watchlist_suggestions_prompt(body.count, holdings, watchlist)}


@router.post("/api/insights/portfolio-review/prompt")
def portfolio_review_prompt(
    body: PortfolioReviewRequest,
    db: Session = Depends(get_db),
):
    """Return the portfolio-review prompt to paste into Claude/ChatGPT."""
    holdings, watchlist, summary = _review_inputs(db, body.account_id)
    return {
        "prompt": insights_service.portfolio_review_prompt(
            holdings, watchlist, summary, body.target_profit_pct
        )
    }
