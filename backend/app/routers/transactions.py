"""
Transactions router.

GET  /api/transactions?account_id=
POST /api/transactions/import  (multipart CSV upload)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionImportResponse, TransactionRead
from app.services.import_csv import import_csv

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    account_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return all transactions, optionally filtered by account."""
    q = db.query(Transaction)
    if account_id is not None:
        q = q.filter(Transaction.account_id == account_id)
    return q.order_by(Transaction.trade_date.desc()).all()


@router.post("/import", response_model=TransactionImportResponse)
async def import_transactions(
    file: UploadFile,
    account_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Import a Zerodha Console tradebook CSV.

    Multipart form:
        ``file``       – CSV file upload
        ``account_id`` – target account (required)

    Expected CSV columns (Zerodha tradebook export):
        trade_date, symbol, exchange, trade_type (buy/sell),
        quantity, price, amount (optional), fees (optional)

    Duplicates are silently skipped.
    """
    if account_id is None:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for CSV import",
        )

    if file.content_type not in ("text/csv", "application/csv",
                                  "application/vnd.ms-excel", "text/plain", None):
        # Be lenient – browsers send various content types for CSV
        pass

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    result = import_csv(db, content, account_id)
    return {
        "message": f"Import complete: {result['imported']} rows imported, {result['skipped']} skipped",
        "imported": result["imported"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }
