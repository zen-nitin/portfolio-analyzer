"""
Holdings derivation service.

Derives current holdings from Transaction rows (buy/sell history) so that
accounts without a live broker connection (broker="manual") can still show
meaningful holdings.

Algorithm:
  Group transactions into instruments (union-find: rows sharing a symbol OR an
  ISIN are the same instrument), then for each instrument group:
    net_quantity  = sum(qty for buys)  – sum(qty for sells)
    weighted_avg  = total_buy_cost / total_buy_qty   (weighted average cost)
    Skip if net_quantity <= 0 (fully sold out).

Netting is NOT per (symbol, exchange): shares of the same company are fungible
across exchanges in a single demat (buy on NSE, sell on BSE), so a per-exchange
key leaves **phantom holdings**. The instrument grouping links rows by symbol or
ISIN, which simultaneously handles:
  • ticker renames     — same ISIN, different symbols (ZOMATO→ETERNAL)
  • corporate actions  — same symbol, different ISINs (face-value change)
  • blank ISIN rows    — the tradebook leaves ISIN empty on some rows; the symbol
                         still ties them to the rest of the instrument's history
The display symbol + exchange come from the most recent trade, so a renamed
holding shows its current ticker (also what live-price lookup needs).

Derived holdings are persisted to the ``holdings`` table, replacing any
existing rows for that account.  ``last_price``, ``day_change``, and ``pnl``
are set to 0.0 initially; call ``refresh_prices`` afterwards to populate them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.transaction import Transaction


def group_transactions_by_instrument(
    transactions: list[Transaction],
) -> list[list[Transaction]]:
    """Group transactions into instruments via union-find over symbol/ISIN.

    Two rows are the same instrument if they share a symbol OR an ISIN. Linking
    both ways (transitively) merges:
      • ticker renames — same ISIN, different symbols (e.g. ZOMATO↔ETERNAL)
      • corporate actions — same symbol, different ISINs (e.g. a face-value change)
    and it is robust to the tradebook leaving ISIN blank on some rows (the symbol
    still ties those rows to the rest of the instrument's history). A plain
    "isin or symbol" key cannot do this — blank-ISIN rows would split off into a
    phantom holding for an otherwise fully-sold position.
    """
    parent: dict[str, str] = {}

    def _find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:          # path compression
            parent[x], x = root, parent[x]
        return root

    def _union(a: str, b: str) -> None:
        parent[_find(a)] = _find(b)

    for tx in transactions:
        sym = tx.symbol.upper()
        isin = (getattr(tx, "isin", None) or "").strip().upper() or None
        _find("sym:" + sym)
        if isin:
            _union("sym:" + sym, "isin:" + isin)

    group_txns: dict[str, list[Transaction]] = {}
    for tx in transactions:
        key = _find("sym:" + tx.symbol.upper())
        group_txns.setdefault(key, []).append(tx)
    return list(group_txns.values())


def derive_holdings_from_transactions(
    db: Session,
    account_id: int,
) -> list[Holding]:
    """Compute net holdings from Transaction rows and persist them.

    Args:
        db:         Active SQLAlchemy session.
        account_id: Account to derive holdings for.

    Returns:
        List of newly created/replaced Holding ORM objects.
    """
    transactions = (
        db.query(Transaction)
        .filter(Transaction.account_id == account_id)
        .all()
    )

    # Delete existing holdings for this account; synchronize_session="evaluate"
    # keeps the session identity map clean so we don't get stale-object warnings.
    db.query(Holding).filter(Holding.account_id == account_id).delete(
        synchronize_session="evaluate"
    )

    now = datetime.utcnow()
    derived: list[Holding] = []

    for txs in group_transactions_by_instrument(transactions):
        # Chronological replay, stable by id for same-day trades. We use a MOVING
        # weighted-average — the convention brokers (Zerodha) show:
        #   • buy   → qty += q;  cost += amount;  avg = cost / qty
        #   • bonus → qty += q;  cost += 0        (free shares dilute the average)
        #   • sell  → remove q shares AT the current average: cost -= q * avg, qty -= q
        #             (a sell leaves the average UNCHANGED)
        # When the position is fully closed the cost basis resets to zero, so a
        # later re-buy is averaged fresh — e.g. selling out of SBIN and rebuying
        # gives the new lot's price, not a blend with long-gone lots. Averaging
        # over *all* buys ever (the old method) is wrong once anything is sold.
        txs_sorted = sorted(txs, key=lambda t: (t.trade_date, t.id))

        qty = 0.0
        cost = 0.0
        isin: str | None = None
        last_date = None
        disp_symbol = txs_sorted[0].symbol.upper()
        disp_exchange = (txs_sorted[0].exchange or "NSE").upper()

        for tx in txs_sorted:
            isin = isin or ((getattr(tx, "isin", None) or "").strip().upper() or None)
            ttype = tx.trade_type.lower()

            if ttype in ("buy", "bonus"):
                qty += tx.quantity
                cost += tx.amount  # quantity * price, pre-recorded (0 for a bonus)
            elif ttype == "sell":
                if qty > 0:
                    cost -= tx.quantity * (cost / qty)  # remove at current avg
                qty -= tx.quantity
                if qty <= 1e-9:        # fully sold (or oversold) → reset cost basis
                    qty = 0.0
                    cost = 0.0

            # Most recent trade (any type) sets the display ticker + exchange, so a
            # renamed holding shows its current ticker (ETERNAL, not delisted ZOMATO).
            if last_date is None or tx.trade_date >= last_date:
                last_date = tx.trade_date
                disp_symbol = tx.symbol.upper()
                disp_exchange = (tx.exchange or "NSE").upper()

        if qty <= 1e-9:
            continue  # fully sold (across all exchanges / renames); skip

        avg_price = cost / qty if qty > 0 else 0.0

        holding = Holding(
            account_id=account_id,
            symbol=disp_symbol,
            exchange=disp_exchange,
            isin=isin,
            quantity=round(qty, 6),
            average_price=round(avg_price, 4),
            last_price=0.0,   # to be filled by price refresh
            pnl=0.0,
            day_change=0.0,
            updated_at=now,
        )
        db.add(holding)
        derived.append(holding)

    db.commit()
    db.expire_all()  # Ensure fresh state after commit

    return derived


def compute_exited_positions(transactions: list[Transaction]) -> list[dict]:
    """Positions the user FULLY EXITED (net quantity now zero), with the average
    price they held at the moment of exit, plus realized P&L.

    Uses the same instrument grouping and moving-average convention as the live
    derivation. For each fully-closed instrument it captures, at the final
    closing sell: the moving average held (``average_price``), the lot size held
    just before exiting (``quantity``), the exit date, and realized P&L summed
    across all sells (each sell's proceeds minus its cost at the then-average,
    so bonus shares correctly boost realized gains).

    Open positions (net qty > 0) are skipped — those are current holdings.
    """
    out: list[dict] = []

    for txs in group_transactions_by_instrument(transactions):
        txs_sorted = sorted(txs, key=lambda t: (t.trade_date, t.id))

        qty = 0.0
        cost = 0.0
        realized = 0.0
        buy_value = 0.0
        sell_value = 0.0
        exit_avg = 0.0
        exit_qty = 0.0
        exit_date = None
        isin: str | None = None
        last_date = None
        disp_symbol = txs_sorted[0].symbol.upper()
        disp_exchange = (txs_sorted[0].exchange or "NSE").upper()

        for tx in txs_sorted:
            isin = isin or ((getattr(tx, "isin", None) or "").strip().upper() or None)
            ttype = tx.trade_type.lower()

            if ttype in ("buy", "bonus"):
                qty += tx.quantity
                cost += tx.amount          # 0 for a bonus
                if ttype == "buy":
                    buy_value += tx.amount
            elif ttype == "sell":
                avg = (cost / qty) if qty > 0 else 0.0
                sell_price = (tx.amount / tx.quantity) if tx.quantity else 0.0
                realized += tx.quantity * (sell_price - avg)
                sell_value += tx.amount
                # Snapshot the position AS IT STOOD before this sell — the last
                # such snapshot is the final exit (avg held + lot size + date).
                exit_avg = avg
                exit_qty = qty
                exit_date = tx.trade_date
                cost -= tx.quantity * avg
                qty -= tx.quantity
                if qty <= 1e-9:
                    qty = 0.0
                    cost = 0.0

            if last_date is None or tx.trade_date >= last_date:
                last_date = tx.trade_date
                disp_symbol = tx.symbol.upper()
                disp_exchange = (tx.exchange or "NSE").upper()

        if qty > 1e-9:
            continue  # still open → a current holding, not an exited position

        if exit_date is None:
            continue  # never sold (e.g. only bonus rows with no buys) → skip

        out.append({
            "symbol": disp_symbol,
            "exchange": disp_exchange,
            "isin": isin,
            "quantity": round(exit_qty, 6),
            "average_price": round(exit_avg, 4),
            "exit_date": exit_date.isoformat() if exit_date else None,
            "realized_pnl": round(realized, 2),
            "buy_value": round(buy_value, 2),
            "sell_value": round(sell_value, 2),
        })

    # Most recently exited first.
    out.sort(key=lambda p: p["exit_date"] or "", reverse=True)
    return out
