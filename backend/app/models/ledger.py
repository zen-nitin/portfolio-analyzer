"""
LedgerEntry model – cash movements in the broker funds ledger.

This is the **cash account**, distinct from ``Transaction`` (which records
share trades). A ledger captures every rupee that moves in/out of the trading
account: bank deposits (money from your pocket), withdrawals, brokerage/DP/AMC
charges, trade settlements, dividends, and reversals.

It answers a different question than the tradebook: "how much have I put in
from my own pocket, and what did *my money* actually earn?" — see
``services/portfolio.py`` (net_deposited + personal XIRR).

Imported from a **Zerodha Console funds/ledger CSV** via
``/api/ledger/import``. Trade settlement rows here are NOT used for the trade
XIRR (that still comes from ``Transaction``) — the two cashflow sources are
deliberately disjoint to avoid double counting.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# Canonical entry categories (the importer classifies each row into one).
ENTRY_DEPOSIT = "deposit"        # money added from your bank (from pocket)
ENTRY_WITHDRAWAL = "withdrawal"  # money paid back to your bank
ENTRY_CHARGE = "charge"          # brokerage / DP / AMC / gateway charges
ENTRY_TRADE = "trade"            # equity settlement, T-Bill/SDL blocks
ENTRY_DIVIDEND = "dividend"      # dividend credited to the ledger
ENTRY_OTHER = "other"            # reversals, anything unclassified


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)  # see ENTRY_* above

    # Raw amounts from the ledger (one of the two is non-zero).
    debit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    credit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Signed amount from the trading account's perspective: credit − debit.
    # Deposits/dividends are positive; withdrawals/charges/buys are negative.
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Running balance after this entry (the last row's value is current free cash).
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    particulars: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    voucher_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship("Account", lazy="select")  # type: ignore[name-defined]
