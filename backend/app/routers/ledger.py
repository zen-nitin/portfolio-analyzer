"""
Ledger router.

GET  /api/ledger?account_id=        – list cash-ledger entries
POST /api/ledger/import             – multipart Zerodha funds/ledger CSV upload

The ledger is the cash account (deposits, withdrawals, charges, settlements),
distinct from the tradebook (`/api/transactions`). It drives the "invested from
pocket" figure and the personal XIRR on the portfolio summary.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ledger import LedgerEntry
from app.schemas.ledger import LedgerEntryRead, LedgerImportResponse
from app.services.import_ledger import import_ledger

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


@router.get("", response_model=list[LedgerEntryRead])
def list_ledger(
    account_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return all ledger entries, optionally filtered by account (newest first)."""
    q = db.query(LedgerEntry)
    if account_id is not None:
        q = q.filter(LedgerEntry.account_id == account_id)
    return q.order_by(LedgerEntry.entry_date.desc(), LedgerEntry.id.desc()).all()


@router.post("/import", response_model=LedgerImportResponse)
async def import_ledger_csv(
    file: UploadFile,
    account_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Import a Zerodha Console funds/ledger CSV.

    Multipart form:
        ``file``       – CSV file upload
        ``account_id`` – target account (required)

    Expected columns: particulars, posting_date, cost_center, voucher_type,
    debit, credit, net_balance. Duplicates are silently skipped.
    """
    if account_id is None:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for ledger import",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    result = import_ledger(db, content, account_id)
    return {
        "message": (
            f"Import complete: {result['imported']} entries imported, "
            f"{result['skipped']} skipped"
        ),
        "imported": result["imported"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "net_deposited": result["net_deposited"],
        "total_deposited": result["total_deposited"],
        "total_withdrawn": result["total_withdrawn"],
        "total_charges": result["total_charges"],
        "free_cash": result["free_cash"],
    }
