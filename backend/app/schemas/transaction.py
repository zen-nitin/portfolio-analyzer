from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    exchange: str
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
