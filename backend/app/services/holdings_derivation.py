"""
Holdings derivation service.

Derives current holdings from Transaction rows (buy/sell history) so that
accounts without a live broker connection (broker="manual") can still show
meaningful holdings.

Algorithm:
  For each (symbol, exchange) pair:
    net_quantity  = sum(qty for buys)  – sum(qty for sells)
    weighted_avg  = total_buy_cost / total_buy_qty   (weighted average cost)
    Skip if net_quantity <= 0 (fully sold out).

Derived holdings are persisted to the ``holdings`` table, replacing any
existing rows for that account.  ``last_price``, ``day_change``, and ``pnl``
are set to 0.0 initially; call ``refresh_prices`` afterwards to populate them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.transaction import Transaction


def derive_holdings_from_transactions(
    db: Session,
    account_id: int,
) -> list[Holding]:
    """Compute net holdings from Transaction rows and persist them.

    Args:
        db:         Active SQLAlchemy session.
        account_id: Account to derive holdings for.

    Returns:
        List of newly created/replaced Holding ORM objects.
    """
    transactions = (
        db.query(Transaction)
        .filter(Transaction.account_id == account_id)
        .all()
    )

    # Aggregate by (symbol, exchange)
    # key -> {"buy_qty": float, "buy_cost": float, "sell_qty": float, "exchange": str}
    agg: dict[tuple[str, str], dict] = {}

    for tx in transactions:
        sym = tx.symbol.upper()
        exch = (tx.exchange or "NSE").upper()
        key = (sym, exch)

        if key not in agg:
            agg[key] = {"buy_qty": 0.0, "buy_cost": 0.0, "sell_qty": 0.0, "exchange": exch}

        if tx.trade_type.lower() == "buy":
            agg[key]["buy_qty"] += tx.quantity
            agg[key]["buy_cost"] += tx.amount  # quantity * price, pre-recorded
        elif tx.trade_type.lower() == "sell":
            agg[key]["sell_qty"] += tx.quantity

    # Delete existing holdings for this account; synchronize_session="evaluate"
    # keeps the session identity map clean so we don't get stale-object warnings.
    db.query(Holding).filter(Holding.account_id == account_id).delete(
        synchronize_session="evaluate"
    )

    now = datetime.utcnow()
    derived: list[Holding] = []

    for (sym, exch), data in agg.items():
        net_qty = data["buy_qty"] - data["sell_qty"]
        if net_qty <= 0:
            continue  # fully sold; skip

        buy_qty = data["buy_qty"]
        buy_cost = data["buy_cost"]
        avg_price = (buy_cost / buy_qty) if buy_qty > 0 else 0.0

        holding = Holding(
            account_id=account_id,
            symbol=sym,
            exchange=exch,
            isin=None,
            quantity=round(net_qty, 6),
            average_price=round(avg_price, 4),
            last_price=0.0,   # to be filled by price refresh
            pnl=0.0,
            day_change=0.0,
            updated_at=now,
        )
        db.add(holding)
        derived.append(holding)

    db.commit()
    db.expire_all()  # Ensure fresh state after commit

    return derived
