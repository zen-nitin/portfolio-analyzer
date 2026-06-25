from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    exchange: str
    isin: Optional[str] = None
    trade_type: str
    quantity: float
    price: float
    amount: float
    fees: float
    trade_date: date
    created_at: datetime


class TransactionImportResponse(BaseModel):
    message: str
    imported: int
    skipped: int
    errors: list[str]


class TransactionCreate(BaseModel):
    """Manually add a single trade behind a holding (buy / sell / bonus).

    ``amount`` is always derived server-side (qty × price, or 0 for a bonus), so
    the cost basis stays consistent with the importer and add-/sell-shares flows.
    """
    account_id: int
    symbol: str
    exchange: str = "NSE"
    isin: Optional[str] = None
    trade_type: str           # buy | sell | bonus
    quantity: float
    price: float = 0.0        # per-share; 0 for a bonus
    trade_date: date
    fees: float = 0.0


class TransactionUpdate(BaseModel):
    """Edit a single trade. All fields optional — only those provided change;
    ``amount`` is recomputed from the resulting type/qty/price."""
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    isin: Optional[str] = None
    trade_type: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    trade_date: Optional[date] = None
    fees: Optional[float] = None


class TransactionMutationResponse(BaseModel):
    """Result of a create/edit — the saved row plus the re-derive counts so the
    UI can confirm the holding was rebuilt."""
    message: str
    transaction: TransactionRead
    holdings_synced: int
    prices_refreshed: int


class TransactionDeleteResponse(BaseModel):
    message: str
    holdings_synced: int
    prices_refreshed: int
