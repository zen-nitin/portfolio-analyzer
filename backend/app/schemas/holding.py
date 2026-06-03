from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field


class HoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    exchange: str
    isin: Optional[str] = None
    quantity: float
    average_price: float
    last_price: float
    pnl: float
    day_change: float
    updated_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def pnl_pct(self) -> float:
        cost = self.average_price * self.quantity
        if cost == 0:
            return 0.0
        return round((self.pnl / cost) * 100, 4)

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> str:
        pct = self.pnl_pct
        if pct > 15:
            return "STRONG_GAIN"
        elif pct > 0:
            return "GAIN"
        elif pct >= -0.5:
            return "FLAT"
        elif pct > -15:
            return "LOSS"
        else:
            return "STRONG_LOSS"
