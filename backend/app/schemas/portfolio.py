from typing import Optional

from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    pnl: float
    pnl_pct: float
    xirr: Optional[float] = None  # decimal, e.g. 0.184 = 18.4%
    day_change: float
