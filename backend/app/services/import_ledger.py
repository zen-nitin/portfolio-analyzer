"""
Zerodha Console funds/ledger CSV importer.

Converts cash-account movements into ``LedgerEntry`` rows. This is the source
of "money invested from your pocket" and the personal XIRR — distinct from the
tradebook (``import_csv.py``), which records share trades.

Expected columns (Zerodha Console → Reports → Funds / Ledger), tolerant of
header-name variants:

    particulars     – free-text description (contains "Funds added", "Payout"…)
    posting_date    – YYYY-MM-DD (also tolerates dd/mm/yyyy etc.)
    cost_center     – e.g. "NSE-EQ - Z" (kept for reference, not parsed)
    voucher_type    – the row's category driver (see _classify below)
    debit           – money out of the trading account
    credit          – money into the trading account
    net_balance     – running balance after the row

Each row is classified by ``voucher_type`` (and particulars as a fallback):

    Bank Receipts   → deposit     (money you added from your bank)
    Bank Payments   → withdrawal  (money paid back to your bank)
    Journal Entry   → charge      (DP / AMC / gateway / call-and-trade fees)
                                  unless the text mentions a dividend
    Book Voucher    → trade       (equity settlement, T-Bill/SDL blocks)
    Reversal Voucher→ other       (price-difference reversals)

Opening/Closing Balance rows (no date, no voucher type) are skipped. Rows are
de-duplicated against existing DB records on
(account_id, entry_date, particulars, debit, credit).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ledger import (
    ENTRY_CHARGE,
    ENTRY_DEPOSIT,
    ENTRY_DIVIDEND,
    ENTRY_OTHER,
    ENTRY_TRADE,
    ENTRY_WITHDRAWAL,
    LedgerEntry,
)

# Column-name aliases (lower-stripped, underscores→spaces) → canonical field
_FIELD_MAP: dict[str, str] = {
    "particulars": "particulars",
    "description": "particulars",
    "narration": "particulars",
    "posting date": "entry_date",
    "date": "entry_date",
    "value date": "entry_date",
    "cost center": "cost_center",
    "cost centre": "cost_center",
    "voucher type": "voucher_type",
    "voucher": "voucher_type",
    "type": "voucher_type",
    "debit": "debit",
    "withdrawal": "debit",
    "credit": "credit",
    "deposit": "credit",
    "net balance": "balance",
    "balance": "balance",
    "closing balance": "balance",
}

# voucher_type (lower) → canonical entry category
_VOUCHER_MAP: dict[str, str] = {
    "bank receipts": ENTRY_DEPOSIT,
    "bank payments": ENTRY_WITHDRAWAL,
    "journal entry": ENTRY_CHARGE,
    "book voucher": ENTRY_TRADE,
    "reversal voucher": ENTRY_OTHER,
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


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return default


def _classify(voucher_type: str, particulars: str) -> str:
    """Map a ledger row to a canonical entry category."""
    vt = voucher_type.strip().lower()
    text = particulars.strip().lower()
    # Dividends are credited via a journal/book entry; detect by text first.
    if "dividend" in text:
        return ENTRY_DIVIDEND
    return _VOUCHER_MAP.get(vt, ENTRY_OTHER)


def import_ledger(
    db: Session,
    csv_content: bytes,
    account_id: int,
) -> dict:
    """Parse a Zerodha funds/ledger CSV and insert LedgerEntry rows.

    Returns a dict with ``imported``, ``skipped``, ``errors`` plus the derived
    headline figures (``net_deposited``, ``total_deposited``,
    ``total_withdrawn``, ``total_charges``, ``free_cash``).
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
        return {
            "imported": 0, "skipped": 0, "errors": ["CSV has no headers"],
            "net_deposited": 0.0, "total_deposited": 0.0,
            "total_withdrawn": 0.0, "total_charges": 0.0, "free_cash": 0.0,
        }

    col_map: dict[str, str] = {}
    for orig_header in reader.fieldnames:
        normalised = orig_header.strip().lower().replace("_", " ")
        canonical = _FIELD_MAP.get(normalised)
        if canonical:
            col_map[orig_header] = canonical

    last_balance = 0.0

    for row_num, row in enumerate(reader, start=2):
        mapped: dict[str, str] = {}
        for orig, canonical in col_map.items():
            mapped[canonical] = (row.get(orig) or "").strip()

        particulars = mapped.get("particulars", "")
        voucher_type = mapped.get("voucher_type", "")

        # Skip Opening/Closing Balance markers (no date, no voucher type).
        entry_date = _parse_date(mapped.get("entry_date", ""))
        if entry_date is None or not voucher_type:
            # Still track the balance so free_cash reflects the closing row.
            bal_raw = mapped.get("balance", "")
            if bal_raw:
                last_balance = _safe_float(bal_raw, last_balance)
            skipped += 1
            continue

        debit = _safe_float(mapped.get("debit", "0"))
        credit = _safe_float(mapped.get("credit", "0"))
        balance = _safe_float(mapped.get("balance", "0"))
        last_balance = balance
        amount = round(credit - debit, 6)
        entry_type = _classify(voucher_type, particulars)

        exists = (
            db.query(LedgerEntry)
            .filter(
                LedgerEntry.account_id == account_id,
                LedgerEntry.entry_date == entry_date,
                LedgerEntry.particulars == particulars,
                LedgerEntry.debit == debit,
                LedgerEntry.credit == credit,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        db.add(LedgerEntry(
            account_id=account_id,
            entry_date=entry_date,
            entry_type=entry_type,
            debit=debit,
            credit=credit,
            amount=amount,
            balance=balance,
            particulars=particulars[:500],
            voucher_type=voucher_type[:50],
        ))
        imported += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(f"DB commit error: {exc}")
        return {
            "imported": 0, "skipped": skipped, "errors": errors,
            "net_deposited": 0.0, "total_deposited": 0.0,
            "total_withdrawn": 0.0, "total_charges": 0.0, "free_cash": 0.0,
        }

    # Derive headline figures across ALL of this account's ledger (not just the
    # rows imported this run), so re-imports/partial files still report totals.
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.account_id == account_id)
        .order_by(LedgerEntry.entry_date.asc(), LedgerEntry.id.asc())
        .all()
    )
    total_deposited = sum(e.amount for e in entries if e.entry_type == ENTRY_DEPOSIT)
    total_withdrawn = -sum(e.amount for e in entries if e.entry_type == ENTRY_WITHDRAWAL)
    total_charges = -sum(e.amount for e in entries if e.entry_type == ENTRY_CHARGE)
    net_deposited = total_deposited - total_withdrawn
    free_cash = entries[-1].balance if entries else last_balance

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "net_deposited": round(net_deposited, 2),
        "total_deposited": round(total_deposited, 2),
        "total_withdrawn": round(total_withdrawn, 2),
        "total_charges": round(total_charges, 2),
        "free_cash": round(free_cash, 2),
    }
