"""
Holdings router.

GET /api/holdings?account_id=<id>          — current holdings
GET /api/holdings/exited?account_id=<id>   — fully-exited (no-longer-held) positions

Returns holdings with computed pnl_pct and status classifier.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.holding import Holding
from app.schemas.holding import HoldingRead
from app.services.holdings_derivation import compute_exited_positions
from app.services.portfolio import get_transactions_for_accounts

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


class ExitedPositionRead(BaseModel):
    symbol: str
    exchange: str
    isin: Optional[str] = None
    quantity: float          # lot size held just before the final exit
    average_price: float     # moving average held at exit
    exit_date: Optional[str] = None
    realized_pnl: float
    buy_value: float
    sell_value: float


def _active_account_ids(db: Session, account_id: Optional[int]) -> list[int]:
    if account_id is not None:
        return [account_id]
    active = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
    return [a.id for a in active]


@router.get("", response_model=list[HoldingRead])
def list_holdings(
    account_id: Optional[int] = Query(None, description="Filter by account; omit for all"),
    db: Session = Depends(get_db),
):
    """Return all holdings, optionally filtered by account.

    Each holding includes computed ``pnl_pct`` and ``status``.
    """
    if account_id is not None:
        holdings = db.query(Holding).filter(Holding.account_id == account_id).all()
    else:
        active = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        account_ids = [a.id for a in active]
        if not account_ids:
            return []
        holdings = db.query(Holding).filter(Holding.account_id.in_(account_ids)).all()
    return holdings


@router.get("/exited", response_model=list[ExitedPositionRead])
def list_exited_positions(
    account_id: Optional[int] = Query(None, description="Filter by account; omit for all"),
    db: Session = Depends(get_db),
):
    """Positions fully exited (no longer held), derived from the trade history.

    Each row shows the average price the position was held at when it was exited,
    the lot size held just before exiting, the exit date, and realized P&L.
    """
    account_ids = _active_account_ids(db, account_id)
    if not account_ids:
        return []
    transactions = get_transactions_for_accounts(db, account_ids)
    return compute_exited_positions(transactions)
