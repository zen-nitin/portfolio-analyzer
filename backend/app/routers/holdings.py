"""
Holdings router.

GET /api/holdings?account_id=<id>

Returns holdings with computed pnl_pct and status classifier.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.holding import Holding
from app.schemas.holding import HoldingRead

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


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
