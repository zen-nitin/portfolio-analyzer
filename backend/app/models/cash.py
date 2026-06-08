"""
Manual free-cash override.

Free cash (idle money in the trading account) is normally taken from the latest
imported funds-ledger balance. But the ledger export is often stale relative to
the tradebook, so this table lets the user set the current free cash by hand,
per account. When an override exists it replaces the ledger-derived figure in
the portfolio summary (and therefore in the personal XIRR). A separate table is
used (rather than a column on ``accounts``) so the existing SQLite database
picks it up automatically via ``create_all`` — no column migration needed.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FreeCashOverride(Base):
    __tablename__ = "free_cash_overrides"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), primary_key=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )
