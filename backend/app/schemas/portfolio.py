from typing import Optional

from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    pnl: float
    pnl_pct: float
    xirr: Optional[float] = None  # decimal, e.g. 0.184 = 18.4%
    day_change: float

    # Ledger-derived "from pocket" figures (None until a funds ledger is imported)
    net_deposited: Optional[float] = None   # bank deposits − withdrawals
    total_withdrawn: Optional[float] = None
    total_charges: Optional[float] = None
    free_cash: Optional[float] = None
    personal_xirr: Optional[float] = None   # return on your own money, decimal
