"""
AI insights router.

POST /api/insights/watchlist-suggestions  {count}
POST /api/insights/recommendation         {symbol, exchange}
GET  /api/insights/analysis/{symbol}      ?exchange=NSE
GET  /api/ai/providers
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai import registry as ai_registry
from app.database import get_db
from app.models.account import Account
from app.models.holding import Holding
from app.services import insights as insights_service

router = APIRouter(tags=["insights"])


# ------------------------------------------------------------------
# Request / response schemas (inline – small enough)
# ------------------------------------------------------------------

class WatchlistSuggestionsRequest(BaseModel):
    count: int = 5


class RecommendationRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"


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
    return insights_service.watchlist_suggestions(body.count, holdings)


@router.post("/api/insights/recommendation")
def get_recommendation(
    body: RecommendationRequest,
    db: Session = Depends(get_db),
):
    """BUY/SELL/HOLD recommendation for a symbol."""
    holdings = _all_active_holdings(db)
    return insights_service.recommendation(body.symbol, body.exchange, holdings)


@router.get("/api/insights/analysis/{symbol}")
def get_analysis(
    symbol: str,
    exchange: Optional[str] = Query("NSE"),
    db: Session = Depends(get_db),
):
    """Comprehensive AI analysis for a symbol."""
    holdings = _all_active_holdings(db)
    return insights_service.analysis(symbol.upper(), exchange or "NSE", holdings)


@router.get("/api/ai/providers", response_model=list[AIProviderInfo])
def list_ai_providers():
    """List all known AI providers with active/configured flags."""
    return ai_registry.list_providers()
