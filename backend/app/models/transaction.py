"""
Transaction model – individual buy/sell trades.

Used as source of cashflows for XIRR calculation.
Import from Zerodha Console tradebook CSV via the /api/transactions/import
endpoint.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False, default="NSE")
    # ISIN identifies the underlying instrument across exchanges AND ticker
    # renames (e.g. ZOMATO→ETERNAL share one ISIN). It is the correct key for
    # netting holdings; symbol is only a fallback when ISIN is absent.
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    trade_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "buy" | "sell"

    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)   # quantity * price
    fees: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship("Account", lazy="select")  # type: ignore[name-defined]
