"""
Portfolio summary router.

GET /api/portfolio/summary?account_id=<id>

If account_id is omitted, aggregates ALL active accounts.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.database import get_db
from app.models.account import Account
from app.schemas.portfolio import PortfolioSummary
from app.services.portfolio import (
    build_summary,
    get_holdings_for_accounts,
    get_ledger_for_accounts,
    get_transactions_for_accounts,
    resolve_free_cash_override,
)
from app.services.market_hours import is_market_open
from app.services.price_refresh import refresh_prices

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class RefreshPricesResult(BaseModel):
    prices_refreshed: int
    market_open: bool = True


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
    ledger = get_ledger_for_accounts(db, account_ids)
    free_cash_override = resolve_free_cash_override(db, account_ids, ledger)
    summary = build_summary(holdings, transactions, ledger, free_cash_override)
    return summary


@router.post("/refresh-prices", response_model=RefreshPricesResult)
def refresh_portfolio_prices(
    account_id: Optional[int] = Query(None, description="Refresh one account; omit for all active"),
    db: Session = Depends(get_db),
):
    """Refresh live prices for holdings across all active accounts (or one).

    Powers the dashboard's periodic live refresh. Best-effort: a provider
    failure for one account is swallowed so a transient yfinance hiccup never
    breaks the poll — it just refreshes what it can and reports the count.

    Skipped outside NSE/BSE trading hours (Mon–Fri 09:15–15:30 IST): prices
    cannot change when the market is closed, so this becomes a no-op rather than
    hammering the market-data provider. User-initiated refreshes
    (``POST /accounts/{id}/refresh-prices``, sync) are unaffected.
    """
    if not is_market_open():
        return {"prices_refreshed": 0, "market_open": False}

    if account_id is not None:
        account_ids = [account_id]
    else:
        active = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        account_ids = [a.id for a in active]

    total = 0
    for aid in account_ids:
        try:
            total += refresh_prices(db, aid)
        except Exception:
            # Provider down / partial failure — keep going, stay quiet for polling.
            continue
    return {"prices_refreshed": total, "market_open": True}
