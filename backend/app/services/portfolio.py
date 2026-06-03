"""
Portfolio computation service.

Computes aggregate portfolio metrics from the DB holdings and transactions.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.transaction import Transaction
from app.services.xirr import xirr


# ------------------------------------------------------------------
# Holding status classifier
# ------------------------------------------------------------------

def holding_status(pnl_pct: float) -> str:
    """Classify a holding based on its P&L percentage vs average cost.

    Thresholds:
        STRONG_GAIN  : pnl_pct >  15%
        GAIN         : pnl_pct >   0%  (and ≤ 15%)
        FLAT         : pnl_pct within ±0.5%
        LOSS         : pnl_pct <   0%  (and ≥ -15%)
        STRONG_LOSS  : pnl_pct < -15%
    """
    if pnl_pct > 15.0:
        return "STRONG_GAIN"
    elif pnl_pct > 0.5:
        return "GAIN"
    elif pnl_pct >= -0.5:
        return "FLAT"
    elif pnl_pct >= -15.0:
        return "LOSS"
    else:
        return "STRONG_LOSS"


def compute_pnl_pct(pnl: float, average_price: float, quantity: float) -> float:
    """Return P&L % relative to cost basis.  Returns 0.0 if cost is zero."""
    cost = average_price * quantity
    if cost == 0:
        return 0.0
    return round((pnl / cost) * 100, 4)


# ------------------------------------------------------------------
# Portfolio summary builder
# ------------------------------------------------------------------

def build_summary(
    holdings: list[Holding],
    transactions: list[Transaction],
) -> dict:
    """Compute aggregate portfolio metrics.

    Args:
        holdings:     List of Holding ORM rows (current snapshot).
        transactions: List of Transaction ORM rows (full trade history).

    Returns:
        Dict matching the ``PortfolioSummary`` schema:
        {total_invested, current_value, pnl, pnl_pct, xirr, day_change}
    """
    total_invested = sum(h.average_price * h.quantity for h in holdings)
    current_value = sum(h.last_price * h.quantity for h in holdings)
    pnl = current_value - total_invested
    pnl_pct = round((pnl / total_invested * 100), 4) if total_invested else 0.0
    day_change = sum(h.day_change for h in holdings)

    xirr_value = _compute_xirr(transactions, holdings)

    return {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": pnl_pct,
        "xirr": xirr_value,
        "day_change": round(day_change, 2),
    }


def _compute_xirr(
    transactions: list[Transaction],
    holdings: list[Holding],
) -> Optional[float]:
    """Build cashflows from transactions + current holdings and run XIRR.

    Cashflow convention:
        Buys  → negative (money out)
        Sells → positive (money in)
        Current holding value → positive (money in, as of today)
    """
    cashflows: list[tuple[date, float]] = []

    for tx in transactions:
        if tx.trade_type.lower() == "buy":
            cashflows.append((tx.trade_date, -(tx.amount + tx.fees)))
        elif tx.trade_type.lower() == "sell":
            cashflows.append((tx.trade_date, tx.amount - tx.fees))

    # Add current value of holdings as today's inflow
    today = date.today()
    for h in holdings:
        current_val = h.last_price * h.quantity
        if current_val > 0:
            cashflows.append((today, current_val))

    if not cashflows:
        return None

    result = xirr(cashflows)
    return round(result, 6) if result is not None else None


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

def get_holdings_for_accounts(
    db: Session, account_ids: list[int]
) -> list[Holding]:
    """Fetch all holdings for the given account IDs."""
    if not account_ids:
        return []
    return db.query(Holding).filter(Holding.account_id.in_(account_ids)).all()


def get_transactions_for_accounts(
    db: Session, account_ids: list[int]
) -> list[Transaction]:
    """Fetch all transactions for the given account IDs."""
    if not account_ids:
        return []
    return db.query(Transaction).filter(Transaction.account_id.in_(account_ids)).all()
