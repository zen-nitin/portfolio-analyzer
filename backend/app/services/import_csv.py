"""
Zerodha Console tradebook CSV importer.

Converts historical trade records into ``Transaction`` rows for XIRR
calculation.

Expected columns (Zerodha Console tradebook export, tolerates variants):

    trade_date   / Trade Date / Date
    symbol       / Symbol / tradingsymbol / Instrument
    exchange     / Exchange (defaults to "NSE")
    trade_type   / Trade Type / Buy/Sell / Type  (value: buy/sell/B/S)
    quantity     / Qty / Quantity
    price        / Price / Trade Price / Rate
    amount       / Amount / Trade Value (quantity * price if absent)
    fees         / Brokerage / Charges / Fee (optional, default 0)

Rows are de-duplicated against existing DB records on
(account_id, symbol, exchange, trade_type, quantity, price, trade_date).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.transaction import Transaction

# Column-name aliases (lower-stripped) → canonical field
_FIELD_MAP: dict[str, str] = {
    # trade_date
    "trade date": "trade_date",
    "tradedate": "trade_date",
    "date": "trade_date",
    "order date": "trade_date",
    # symbol
    "symbol": "symbol",
    "tradingsymbol": "symbol",
    "instrument": "symbol",
    "scrip": "symbol",
    # exchange
    "exchange": "exchange",
    # trade_type
    "trade type": "trade_type",
    "tradetype": "trade_type",
    "buy/sell": "trade_type",
    "type": "trade_type",
    "transaction type": "trade_type",
    # quantity
    "quantity": "quantity",
    "qty": "quantity",
    "shares": "quantity",
    # price
    "price": "price",
    "trade price": "price",
    "rate": "price",
    "avg. price": "price",
    "average price": "price",
    # amount
    "amount": "amount",
    "trade value": "amount",
    "value": "amount",
    "net amount": "amount",
    # fees
    "fees": "fees",
    "brokerage": "fees",
    "charges": "fees",
    "fee": "fees",
    "total charges": "fees",
}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%Y/%m/%d",
    "%b %d, %Y",
]


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _normalise_trade_type(raw: str) -> Optional[str]:
    v = raw.strip().lower()
    if v in ("buy", "b", "purchase"):
        return "buy"
    if v in ("sell", "s", "sale"):
        return "sell"
    return None


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return default


def import_csv(
    db: Session,
    csv_content: bytes,
    account_id: int,
) -> dict:
    """Parse a Zerodha tradebook CSV and insert Transaction rows.

    Args:
        db:          Active SQLAlchemy session.
        csv_content: Raw CSV bytes (from file upload).
        account_id:  Account to associate the transactions with.

    Returns:
        Dict with ``imported``, ``skipped``, ``errors`` keys.
    """
    imported = 0
    skipped = 0
    errors: list[str] = []

    try:
        text = csv_content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text = csv_content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return {"imported": 0, "skipped": 0, "errors": ["CSV has no headers"]}

    # Build column mapping: original header -> canonical field
    col_map: dict[str, str] = {}
    for orig_header in reader.fieldnames:
        normalised = orig_header.strip().lower()
        canonical = _FIELD_MAP.get(normalised)
        if canonical:
            col_map[orig_header] = canonical

    for row_num, row in enumerate(reader, start=2):
        # Map columns to canonical names
        mapped: dict[str, str] = {}
        for orig, canonical in col_map.items():
            mapped[canonical] = row.get(orig, "").strip()

        # Validate required fields
        missing = [f for f in ("trade_date", "symbol", "trade_type", "quantity", "price")
                   if not mapped.get(f)]
        if missing:
            errors.append(f"Row {row_num}: missing fields {missing}")
            skipped += 1
            continue

        trade_date = _parse_date(mapped["trade_date"])
        if trade_date is None:
            errors.append(f"Row {row_num}: cannot parse date '{mapped['trade_date']}'")
            skipped += 1
            continue

        trade_type = _normalise_trade_type(mapped["trade_type"])
        if trade_type is None:
            errors.append(f"Row {row_num}: unknown trade type '{mapped['trade_type']}'")
            skipped += 1
            continue

        quantity = _safe_float(mapped["quantity"])
        price = _safe_float(mapped["price"])
        amount_raw = mapped.get("amount", "")
        amount = _safe_float(amount_raw) if amount_raw else round(quantity * price, 2)
        fees = _safe_float(mapped.get("fees", "0"))
        exchange = mapped.get("exchange", "NSE") or "NSE"
        symbol = mapped["symbol"].upper()

        # De-duplicate
        exists = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == account_id,
                Transaction.symbol == symbol,
                Transaction.exchange == exchange,
                Transaction.trade_type == trade_type,
                Transaction.quantity == quantity,
                Transaction.price == price,
                Transaction.trade_date == trade_date,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        tx = Transaction(
            account_id=account_id,
            symbol=symbol,
            exchange=exchange,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            amount=amount,
            fees=fees,
            trade_date=trade_date,
        )
        db.add(tx)
        imported += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(f"DB commit error: {exc}")
        return {"imported": 0, "skipped": skipped, "errors": errors}

    return {"imported": imported, "skipped": skipped, "errors": errors}
