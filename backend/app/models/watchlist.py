"""
WatchlistItem model – global watchlist (not per-account).

The Kite API does not expose watchlist data, so we manage our own.

Each item may carry an optional **entry zone** — a buy-price range you're
waiting for — an optional **trade plan** (free-text ``catalyst`` + ``exit_when``
notes), and an optional **manual sort position**. All three live in separate
tables (``watchlist_entry_zones`` / ``watchlist_plans`` / ``watchlist_positions``)
rather than columns on ``watchlist`` so the existing SQLite database picks them up
automatically via ``create_all`` — no column migration needed. The item exposes
``entry_low`` / ``entry_high`` / ``catalyst`` / ``exit_when`` / ``sort_position``
properties so callers (and the read schema) can treat them as if they were inline.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False, default="NSE")
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Optional buy-price range. Deleting the item deletes its zone (delete-orphan).
    entry_zone: Mapped[Optional["WatchlistEntryZone"]] = relationship(
        "WatchlistEntryZone",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="item",
        lazy="joined",
    )

    # Optional trade-plan notes (catalyst + exit-when). Deleting the item
    # deletes its plan (delete-orphan).
    plan: Mapped[Optional["WatchlistPlan"]] = relationship(
        "WatchlistPlan",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="item",
        lazy="joined",
    )

    # Optional manual sort position (set by drag-to-reorder). Null = unordered.
    order: Mapped[Optional["WatchlistPosition"]] = relationship(
        "WatchlistPosition",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="item",
        lazy="joined",
    )

    @property
    def entry_low(self) -> Optional[float]:
        return self.entry_zone.low if self.entry_zone else None

    @property
    def entry_high(self) -> Optional[float]:
        return self.entry_zone.high if self.entry_zone else None

    @property
    def catalyst(self) -> Optional[str]:
        return self.plan.catalyst if self.plan else None

    @property
    def exit_when(self) -> Optional[str]:
        return self.plan.exit_when if self.plan else None

    @property
    def sort_position(self) -> Optional[int]:
        return self.order.position if self.order else None


class WatchlistEntryZone(Base):
    """A buy-price range (low/high) for a watchlist item. Either bound may be
    null (e.g. "buy below X" sets only ``high``)."""

    __tablename__ = "watchlist_entry_zones"

    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), primary_key=True
    )
    low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    item: Mapped["WatchlistItem"] = relationship(
        "WatchlistItem", back_populates="entry_zone"
    )


class WatchlistPlan(Base):
    """Free-text trade-plan notes for a watchlist item: the ``catalyst`` you're
    waiting on (why you'd buy) and ``exit_when`` (the condition that would make
    you sell). Either field may be null."""

    __tablename__ = "watchlist_plans"

    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), primary_key=True
    )
    catalyst: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    exit_when: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    item: Mapped["WatchlistItem"] = relationship(
        "WatchlistItem", back_populates="plan"
    )


class WatchlistPosition(Base):
    """A manual sort position for a watchlist item (lower = higher in the list)."""

    __tablename__ = "watchlist_positions"

    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    item: Mapped["WatchlistItem"] = relationship(
        "WatchlistItem", back_populates="order"
    )
