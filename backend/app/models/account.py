"""
Account model – one row per broker account.

SECURITY NOTE: api_secret and access_token are stored in plain text in the
local SQLite database.  This is acceptable for a single-user local tool but
the database file should not be committed to version control or exposed
externally.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # "zerodha" – Kite Connect; "manual" – CSV-only, no broker API
    broker: Mapped[str] = mapped_column(String(50), nullable=False, default="zerodha")

    # Broker app credentials – optional for manual/CSV-only accounts
    api_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    api_secret: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Session token – refreshed daily for Kite
    access_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    access_token_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
