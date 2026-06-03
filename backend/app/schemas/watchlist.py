from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WatchlistItemCreate(BaseModel):
    symbol: str
    exchange: str = "NSE"
    note: Optional[str] = None


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    exchange: str
    note: Optional[str] = None
    created_at: datetime
