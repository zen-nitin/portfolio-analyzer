"""
Portfolio computation service.

Computes aggregate portfolio metrics from the DB holdings and transactions.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.ledger import (
    ENTRY_CHARGE,
    ENTRY_DEPOSIT,
    ENTRY_WITHDRAWAL,
    LedgerEntry,
)
from app.models.transaction import Transaction
from app.services.xirr import xirr


# ------------------------------------------------------------------
# Holding status classifier
# ------------------------------------------------------------------

def holding_status(pnl_pct: float) -> str:
    """Classify a holding based on its P&L percentage vs average cost.

    Thresholds:
        STRONG_GAIN  : pnl_pct >  15%
        GAIN         : pnl_pct >   0%  (and ≤ 15%)
        FLAT         : pnl_pct within ±0.5%
        LOSS         : pnl_pct <   0%  (and ≥ -15%)
        STRONG_LOSS  : pnl_pct < -15%
    """
    if pnl_pct > 15.0:
        return "STRONG_GAIN"
    elif pnl_pct > 0.5:
        return "GAIN"
    elif pnl_pct >= -0.5:
        return "FLAT"
    elif pnl_pct >= -15.0:
        return "LOSS"
    else:
        return "STRONG_LOSS"


def compute_pnl_pct(pnl: float, average_price: float, quantity: float) -> float:
    """Return P&L % relative to cost basis.  Returns 0.0 if cost is zero."""
    cost = average_price * quantity
    if cost == 0:
        return 0.0
    return round((pnl / cost) * 100, 4)


# ------------------------------------------------------------------
# Portfolio summary builder
# ------------------------------------------------------------------

def build_summary(
    holdings: list[Holding],
    transactions: list[Transaction],
    ledger: Optional[list[LedgerEntry]] = None,
    free_cash_override: Optional[float] = None,
) -> dict:
    """Compute aggregate portfolio metrics.

    Args:
        holdings:     List of Holding ORM rows (current snapshot).
        transactions: List of Transaction ORM rows (full trade history).
        ledger:       Optional list of LedgerEntry rows (cash movements). When
                      present, "from-pocket" metrics and a personal XIRR are
                      derived from bank deposits/withdrawals — see below.
        free_cash_override: Optional manual free-cash figure. When provided it
                      replaces the ledger-derived balance (which is often stale)
                      everywhere free cash is used, including the personal XIRR.

    Returns:
        Dict matching the ``PortfolioSummary`` schema. The ledger-derived
        fields (net_deposited, free_cash, personal_xirr, …) are ``None`` when
        no ledger has been imported.
    """
    total_invested = sum(h.average_price * h.quantity for h in holdings)
    current_value = sum(h.last_price * h.quantity for h in holdings)
    pnl = current_value - total_invested
    pnl_pct = round((pnl / total_invested * 100), 4) if total_invested else 0.0
    day_change = sum(h.day_change for h in holdings)

    xirr_value = _compute_xirr(transactions, holdings)

    summary = {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": pnl_pct,
        "xirr": xirr_value,
        "day_change": round(day_change, 2),
        # Ledger-derived (None until a funds ledger is imported)
        "net_deposited": None,
        "total_withdrawn": None,
        "total_charges": None,
        "free_cash": None,
        "personal_xirr": None,
    }

    if ledger:
        summary.update(_ledger_metrics(ledger, current_value, free_cash_override))
    elif free_cash_override is not None:
        # No funds ledger imported, but the user set free cash manually.
        summary["free_cash"] = round(free_cash_override, 2)

    return summary


def _ledger_metrics(
    ledger: list[LedgerEntry],
    current_value: float,
    free_cash_override: Optional[float] = None,
) -> dict:
    """Derive from-pocket figures and personal XIRR from cash-ledger rows.

    "Net deposited" = bank deposits − withdrawals: the money you actually put
    in from your own pocket. "Free cash" is the latest ledger balance (summed
    per account). Personal XIRR runs only on external bank movements plus the
    current total account value (holdings + free cash) — charges and trade
    settlements are intentionally excluded so this measures the return on *your*
    money, with no double counting against the tradebook trade XIRR.
    """
    total_deposited = sum(e.amount for e in ledger if e.entry_type == ENTRY_DEPOSIT)
    total_withdrawn = -sum(e.amount for e in ledger if e.entry_type == ENTRY_WITHDRAWAL)
    total_charges = -sum(e.amount for e in ledger if e.entry_type == ENTRY_CHARGE)
    net_deposited = total_deposited - total_withdrawn
    free_cash = free_cash_override if free_cash_override is not None else _free_cash(ledger)

    personal_xirr = _compute_personal_xirr(ledger, current_value + free_cash)

    return {
        "net_deposited": round(net_deposited, 2),
        "total_withdrawn": round(total_withdrawn, 2),
        "total_charges": round(total_charges, 2),
        "free_cash": round(free_cash, 2),
        "personal_xirr": personal_xirr,
    }


def _free_cash(ledger: list[LedgerEntry]) -> float:
    """Sum each account's most recent ledger balance (current idle cash)."""
    latest: dict[int, LedgerEntry] = {}
    for e in ledger:
        cur = latest.get(e.account_id)
        if cur is None or (e.entry_date, e.id) >= (cur.entry_date, cur.id):
            latest[e.account_id] = e
    return sum(e.balance for e in latest.values())


def _latest_balance_by_account(ledger: Optional[list[LedgerEntry]]) -> dict[int, float]:
    """Most recent ledger balance per account_id (empty if no ledger)."""
    latest: dict[int, LedgerEntry] = {}
    for e in ledger or []:
        cur = latest.get(e.account_id)
        if cur is None or (e.entry_date, e.id) >= (cur.entry_date, cur.id):
            latest[e.account_id] = e
    return {aid: e.balance for aid, e in latest.items()}


def resolve_free_cash_override(
    db: Session,
    account_ids: list[int],
    ledger: Optional[list[LedgerEntry]] = None,
) -> Optional[float]:
    """Effective free cash for the given accounts, or None if nothing to override.

    For each account, a manual override (if set) wins; otherwise the account's
    latest ledger balance is used. Returns ``None`` when no manual override
    exists for any of the accounts, so the caller falls back to the plain
    ledger-derived figure (preserving prior behaviour).
    """
    from app.models.cash import FreeCashOverride

    overrides = {
        o.account_id: o.amount
        for o in db.query(FreeCashOverride)
        .filter(FreeCashOverride.account_id.in_(account_ids))
        .all()
    }
    if not overrides:
        return None

    ledger_balance = _latest_balance_by_account(ledger)
    return round(
        sum(overrides.get(aid, ledger_balance.get(aid, 0.0)) for aid in account_ids), 2
    )


def _compute_personal_xirr(
    ledger: list[LedgerEntry],
    final_value: float,
) -> Optional[float]:
    """Personal (pocket) XIRR from external bank movements + final value.

    Cashflow convention (from your pocket's perspective):
        Deposit (money out of pocket)  → negative
        Withdrawal (money back to you) → positive
        Final account value today      → positive
    """
    # Personal return is only meaningful against a known current value. Without
    # one (e.g. ledger imported but holdings not yet refreshed), deposits vs
    # withdrawals alone would yield a bogus rate — so report None instead.
    if final_value <= 0:
        return None

    cashflows: list[tuple[date, float]] = []
    for e in ledger:
        if e.entry_type in (ENTRY_DEPOSIT, ENTRY_WITHDRAWAL):
            # e.amount is +deposit / −withdrawal (account view); flip for pocket.
            cashflows.append((e.entry_date, -e.amount))

    if not cashflows:
        return None

    cashflows.append((date.today(), final_value))

    result = xirr(cashflows)
    return round(result, 6) if result is not None else None


def _compute_xirr(
    transactions: list[Transaction],
    holdings: list[Holding],
) -> Optional[float]:
    """Build cashflows from transactions + current holdings and run XIRR.

    Cashflow convention:
        Buys  → negative (money out)
        Sells → positive (money in)
        Current holding value → positive (money in, as of today)
    """
    cashflows: list[tuple[date, float]] = []

    for tx in transactions:
        if tx.trade_type.lower() == "buy":
            cashflows.append((tx.trade_date, -(tx.amount + tx.fees)))
        elif tx.trade_type.lower() == "sell":
            cashflows.append((tx.trade_date, tx.amount - tx.fees))

    # Add current value of holdings as today's inflow
    today = date.today()
    for h in holdings:
        current_val = h.last_price * h.quantity
        if current_val > 0:
            cashflows.append((today, current_val))

    if not cashflows:
        return None

    result = xirr(cashflows)
    return round(result, 6) if result is not None else None


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

def get_holdings_for_accounts(
    db: Session, account_ids: list[int]
) -> list[Holding]:
    """Fetch all holdings for the given account IDs."""
    if not account_ids:
        return []
    return db.query(Holding).filter(Holding.account_id.in_(account_ids)).all()


def get_transactions_for_accounts(
    db: Session, account_ids: list[int]
) -> list[Transaction]:
    """Fetch all transactions for the given account IDs."""
    if not account_ids:
        return []
    return db.query(Transaction).filter(Transaction.account_id.in_(account_ids)).all()


def get_ledger_for_accounts(
    db: Session, account_ids: list[int]
) -> list[LedgerEntry]:
    """Fetch all ledger entries for the given account IDs (chronological)."""
    if not account_ids:
        return []
    return (
        db.query(LedgerEntry)
        .filter(LedgerEntry.account_id.in_(account_ids))
        .order_by(LedgerEntry.entry_date.asc(), LedgerEntry.id.asc())
        .all()
    )
