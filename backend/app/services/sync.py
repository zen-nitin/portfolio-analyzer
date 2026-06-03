"""
Broker sync service.

Pulls live holdings and positions from the broker API and persists them
in the local DB.  Also creates Transaction rows for today's trades if
the broker exposes them.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.brokers.registry import get_connector
from app.models.account import Account
from app.models.holding import Holding
from app.models.transaction import Transaction


def sync_account(db: Session, account: Account) -> dict:
    """Pull holdings + positions from broker and persist to DB.

    Args:
        db:      Active SQLAlchemy session.
        account: The Account to sync.

    Returns:
        Dict with ``holdings_synced`` and ``positions_synced`` counts.
    """
    connector = get_connector(account)

    # ------------------------------------------------------------------ #
    # Holdings                                                             #
    # ------------------------------------------------------------------ #
    raw_holdings = connector.get_holdings()

    # Delete stale rows for this account
    db.query(Holding).filter(Holding.account_id == account.id).delete()

    holdings_count = 0
    for h in raw_holdings:
        quantity = float(h.get("quantity", 0))
        if quantity <= 0:
            continue
        holding = Holding(
            account_id=account.id,
            symbol=h.get("tradingsymbol", h.get("symbol", "")),
            exchange=h.get("exchange", "NSE"),
            isin=h.get("isin"),
            quantity=quantity,
            average_price=float(h.get("average_price", 0)),
            last_price=float(h.get("last_price", 0)),
            pnl=float(h.get("pnl", 0)),
            day_change=float(h.get("day_change", h.get("unrealised_profit", 0))),
            updated_at=datetime.utcnow(),
        )
        db.add(holding)
        holdings_count += 1

    # ------------------------------------------------------------------ #
    # Positions (intraday / short-term)                                    #
    # ------------------------------------------------------------------ #
    raw_positions = connector.get_positions()
    positions_count = 0

    for p in raw_positions:
        quantity = float(p.get("quantity", 0))
        if quantity == 0:
            continue

        # Check if we already created a Transaction for this today
        today = date.today()
        symbol = p.get("tradingsymbol", p.get("symbol", ""))
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == account.id,
                Transaction.symbol == symbol,
                Transaction.trade_date == today,
            )
            .first()
        )
        if existing:
            continue

        trade_type = "buy" if quantity > 0 else "sell"
        qty = abs(quantity)
        avg_price = float(p.get("average_price", 0))
        amount = qty * avg_price

        tx = Transaction(
            account_id=account.id,
            symbol=symbol,
            exchange=p.get("exchange", "NSE"),
            trade_type=trade_type,
            quantity=qty,
            price=avg_price,
            amount=amount,
            fees=0.0,
            trade_date=today,
        )
        db.add(tx)
        positions_count += 1

    db.commit()

    return {
        "holdings_synced": holdings_count,
        "positions_synced": positions_count,
    }
