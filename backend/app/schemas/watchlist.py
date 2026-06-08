from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WatchlistItemCreate(BaseModel):
    symbol: str
    exchange: str = "NSE"
    note: Optional[str] = None
    # Optional buy-price range to set at creation time.
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None


class WatchlistEntryZoneUpdate(BaseModel):
    """Set or clear an item's entry zone. Both bounds null clears it."""

    entry_low: Optional[float] = None
    entry_high: Optional[float] = None


class WatchlistReorder(BaseModel):
    """Full ordered list of item ids, top first."""

    ids: list[int]


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    exchange: str
    note: Optional[str] = None
    # Read from the item's entry_low / entry_high properties.
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    created_at: datetime
