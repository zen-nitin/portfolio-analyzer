"""
Transactions router.

GET    /api/transactions?account_id=&symbol=   (symbol → just one holding's trades)
POST   /api/transactions          (add a single trade)
PUT    /api/transactions/{id}      (edit a trade)
DELETE /api/transactions/{id}      (remove a trade)
POST   /api/transactions/import    (multipart CSV upload)

The single-trade mutations are how a holding's *unit details* are viewed and
corrected: transactions are the source of truth, so after any change we
re-derive the account's holdings (and best-effort refresh prices), exactly like
the add-/sell-shares helpers do.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import (
    TransactionCreate,
    TransactionDeleteResponse,
    TransactionImportResponse,
    TransactionMutationResponse,
    TransactionRead,
    TransactionUpdate,
)
from app.services.holdings_derivation import (
    derive_holdings_from_transactions,
    group_transactions_by_instrument,
)
from app.services.import_csv import import_csv
from app.services.price_refresh import refresh_prices

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# A trade is one of these. The importer writes buy/sell, add-shares writes
# buy/bonus, sell-shares writes sell — so this is the full valid set, and the
# holdings derivation understands exactly these three.
_VALID_TRADE_TYPES = {"buy", "sell", "bonus"}


def _normalise_trade_type(raw: str) -> Optional[str]:
    v = (raw or "").strip().lower()
    return v if v in _VALID_TRADE_TYPES else None


def _amount_for(trade_type: str, quantity: float, price: float) -> float:
    """Cost recorded for a trade: qty × price, but a bonus is always free."""
    return 0.0 if trade_type == "bonus" else round(quantity * price, 2)


def _rederive(db: Session, account_id: int) -> tuple[int, int]:
    """Rebuild this account's holdings from its transactions, then best-effort
    refresh prices. Returns (holdings_count, prices_refreshed)."""
    holdings = derive_holdings_from_transactions(db, account_id)
    prices_refreshed = 0
    try:
        prices_refreshed = refresh_prices(db, account_id)
    except RuntimeError:
        pass  # market provider down — holdings are still rebuilt
    return len(holdings), prices_refreshed


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    account_id: Optional[int] = Query(None),
    symbol: Optional[str] = Query(
        None, description="Return only the trades behind this holding (its instrument group)"
    ),
    db: Session = Depends(get_db),
):
    """Return transactions, optionally filtered by account and/or holding.

    When ``symbol`` is given, the result is the single **instrument group**
    containing that symbol — the same union-find over symbol/ISIN the holdings
    derivation uses — so it captures every trade behind the holding even across
    ticker renames (ZOMATO→ETERNAL) or blank-ISIN rows. Pass ``account_id`` too
    (the holdings UI always does) so grouping stays within one account.
    """
    q = db.query(Transaction)
    if account_id is not None:
        q = q.filter(Transaction.account_id == account_id)
    txns = q.order_by(Transaction.trade_date.desc()).all()

    if symbol:
        target = symbol.strip().upper()
        for group in group_transactions_by_instrument(txns):
            if any(t.symbol.upper() == target for t in group):
                # Most recent first, stable by id for same-day trades.
                return sorted(group, key=lambda t: (t.trade_date, t.id), reverse=True)
        return []

    return txns


@router.post("", response_model=TransactionMutationResponse, status_code=201)
def create_transaction(body: TransactionCreate, db: Session = Depends(get_db)):
    """Add a single trade to a holding, then re-derive the account's holdings."""
    account = db.get(Account, body.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {body.account_id} not found")

    ttype = _normalise_trade_type(body.trade_type)
    if ttype is None:
        raise HTTPException(
            status_code=400,
            detail=f"trade_type must be one of {sorted(_VALID_TRADE_TYPES)}",
        )
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if body.price < 0:
        raise HTTPException(status_code=400, detail="price cannot be negative")
    if body.fees < 0:
        raise HTTPException(status_code=400, detail="fees cannot be negative")

    tx = Transaction(
        account_id=body.account_id,
        symbol=symbol,
        exchange=(body.exchange.strip().upper() or "NSE"),
        isin=(body.isin.strip().upper() if body.isin else None),
        trade_type=ttype,
        quantity=body.quantity,
        price=body.price,
        amount=_amount_for(ttype, body.quantity, body.price),
        fees=body.fees,
        trade_date=body.trade_date,
    )
    db.add(tx)
    db.commit()
    tx_id = tx.id

    holdings_synced, prices_refreshed = _rederive(db, body.account_id)

    return {
        "message": f"Added {ttype} {body.quantity:g} {symbol}; holdings re-derived.",
        "transaction": db.get(Transaction, tx_id),
        "holdings_synced": holdings_synced,
        "prices_refreshed": prices_refreshed,
    }


@router.put("/{transaction_id}", response_model=TransactionMutationResponse)
def update_transaction(
    transaction_id: int, body: TransactionUpdate, db: Session = Depends(get_db)
):
    """Edit a single trade, then re-derive the account's holdings.

    Only the fields supplied change; ``amount`` is recomputed from the resulting
    type/qty/price so the cost basis can never drift out of sync.
    """
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")

    if body.trade_type is not None:
        ttype = _normalise_trade_type(body.trade_type)
        if ttype is None:
            raise HTTPException(
                status_code=400,
                detail=f"trade_type must be one of {sorted(_VALID_TRADE_TYPES)}",
            )
        tx.trade_type = ttype
    if body.symbol is not None:
        symbol = body.symbol.strip().upper()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol cannot be blank")
        tx.symbol = symbol
    if body.exchange is not None:
        tx.exchange = body.exchange.strip().upper() or "NSE"
    if body.isin is not None:
        tx.isin = body.isin.strip().upper() or None
    if body.quantity is not None:
        if body.quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity must be positive")
        tx.quantity = body.quantity
    if body.price is not None:
        if body.price < 0:
            raise HTTPException(status_code=400, detail="price cannot be negative")
        tx.price = body.price
    if body.fees is not None:
        if body.fees < 0:
            raise HTTPException(status_code=400, detail="fees cannot be negative")
        tx.fees = body.fees
    if body.trade_date is not None:
        tx.trade_date = body.trade_date

    # Recompute amount from the final state (a bonus is always free).
    tx.amount = _amount_for(tx.trade_type, tx.quantity, tx.price)

    account_id = tx.account_id
    db.commit()
    tx_id = tx.id

    holdings_synced, prices_refreshed = _rederive(db, account_id)

    return {
        "message": f"Updated {tx.symbol} trade; holdings re-derived.",
        "transaction": db.get(Transaction, tx_id),
        "holdings_synced": holdings_synced,
        "prices_refreshed": prices_refreshed,
    }


@router.delete("/{transaction_id}", response_model=TransactionDeleteResponse)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Delete a single trade (e.g. a wrong entry), then re-derive holdings."""
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")

    account_id = tx.account_id
    symbol = tx.symbol
    db.delete(tx)
    db.commit()

    holdings_synced, prices_refreshed = _rederive(db, account_id)

    return {
        "message": f"Deleted {symbol} trade; holdings re-derived.",
        "holdings_synced": holdings_synced,
        "prices_refreshed": prices_refreshed,
    }


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
