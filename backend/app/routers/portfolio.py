"""
Portfolio summary router.

GET /api/portfolio/summary?account_id=<id>

If account_id is omitted, aggregates ALL active accounts.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.schemas.portfolio import PortfolioSummary
from app.services.portfolio import (
    build_summary,
    get_holdings_for_accounts,
    get_transactions_for_accounts,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(
    account_id: Optional[int] = Query(None, description="Filter by account; omit for all active"),
    db: Session = Depends(get_db),
):
    """Return aggregated portfolio metrics.

    If ``account_id`` is provided, scopes to that account.
    Otherwise, aggregates across all active accounts.
    """
    if account_id is not None:
        account_ids = [account_id]
    else:
        active = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        account_ids = [a.id for a in active]

    holdings = get_holdings_for_accounts(db, account_ids)
    transactions = get_transactions_for_accounts(db, account_ids)
    summary = build_summary(holdings, transactions)
    return summary
