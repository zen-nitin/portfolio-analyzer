from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class LedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    entry_date: date
    entry_type: str
    debit: float
    credit: float
    amount: float
    balance: float
    particulars: str
    voucher_type: str
    created_at: datetime


class LedgerImportResponse(BaseModel):
    message: str
    imported: int
    skipped: int
    errors: list[str]
    # Headline figures derived from the import, for immediate feedback.
    net_deposited: float        # total bank deposits − withdrawals
    total_deposited: float
    total_withdrawn: float
    total_charges: float
    free_cash: float            # current ledger balance
