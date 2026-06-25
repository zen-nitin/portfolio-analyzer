"""
Accounts router.

CRUD for broker accounts + manual sync trigger + live price refresh.

Sync behaviour:
  - broker="zerodha" (or any registered broker with credentials): calls the
    Kite Connect broker API, pulls live holdings/positions, persists them.
  - broker="manual" (CSV-only accounts, no broker API): derives holdings from
    imported Transaction rows, then refreshes live prices via the market data
    provider.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountRead, AccountSyncResponse
from app.services.sync import sync_account
from app.services.holdings_derivation import derive_holdings_from_transactions
from app.services.price_refresh import refresh_prices

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class RefreshPricesResponse(BaseModel):
    message: str
    prices_refreshed: int


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _is_manual(account: Account) -> bool:
    """Return True for CSV-only accounts that have no broker API."""
    return account.broker.lower() == "manual"


def _has_broker_creds(account: Account) -> bool:
    """Return True when api_key and api_secret are populated."""
    return bool(account.api_key and account.api_secret)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    """List all accounts."""
    return db.query(Account).all()


@router.post("", response_model=AccountRead, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    """Create a new broker account.

    For ``broker="zerodha"`` supply ``api_key`` and ``api_secret``.
    For ``broker="manual"`` (CSV-only) those fields are optional/empty.
    """
    if body.broker.lower() != "manual" and not (body.api_key and body.api_secret):
        raise HTTPException(
            status_code=400,
            detail=(
                f"api_key and api_secret are required for broker '{body.broker}'. "
                "Use broker='manual' for CSV-only accounts."
            ),
        )

    account = Account(
        label=body.label,
        broker=body.broker,
        api_key=body.api_key or None,
        api_secret=body.api_secret or None,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get a single account by ID."""
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return account


# ------------------------------------------------------------------
# Sync
# ------------------------------------------------------------------

@router.post("/{account_id}/sync", response_model=AccountSyncResponse)
def trigger_sync(account_id: int, db: Session = Depends(get_db)):
    """Sync holdings for this account.

    - **Zerodha / broker accounts**: pull live holdings + positions from the
      Kite Connect API (requires a valid access token from today).
    - **Manual accounts** (``broker="manual"``): derive holdings from imported
      Transaction rows, then refresh live prices from the market data provider.
    """
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # ----------------------------------------------------------
    # Manual / CSV-only account
    # ----------------------------------------------------------
    if _is_manual(account):
        try:
            holdings = derive_holdings_from_transactions(db, account.id)
            holdings_count = len(holdings)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Holdings derivation failed: {exc}",
            )

        prices_refreshed = 0
        try:
            prices_refreshed = refresh_prices(db, account.id)
        except RuntimeError as exc:
            # Market provider down – return partial result with a warning
            return {
                "message": (
                    f"Holdings derived from transactions but price refresh failed: {exc}"
                ),
                "holdings_synced": holdings_count,
                "positions_synced": 0,
                "prices_refreshed": 0,
            }

        return {
            "message": "Holdings derived from transactions and prices refreshed",
            "holdings_synced": holdings_count,
            "positions_synced": 0,
            "prices_refreshed": prices_refreshed,
        }

    # ----------------------------------------------------------
    # Broker-backed account (e.g. Zerodha)
    # ----------------------------------------------------------
    if not account.access_token:
        raise HTTPException(
            status_code=400,
            detail="No access token configured. Please complete the login flow first.",
        )

    try:
        result = sync_account(db, account)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Broker sync failed: {exc}. Token may be expired – please re-login.",
        )

    return {
        "message": "Sync completed",
        "holdings_synced": result["holdings_synced"],
        "positions_synced": result["positions_synced"],
        "prices_refreshed": None,
    }


# ------------------------------------------------------------------
# Price refresh
# ------------------------------------------------------------------

@router.post("/{account_id}/refresh-prices", response_model=RefreshPricesResponse)
def trigger_price_refresh(account_id: int, db: Session = Depends(get_db)):
    """Refresh live prices for all holdings in this account.

    Fetches current quotes from the market data provider and updates
    ``last_price``, ``day_change``, and ``pnl`` on each Holding row.
    Returns HTTP 503 if the market data provider is unavailable.
    """
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    try:
        count = refresh_prices(db, account.id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Market data provider unavailable: {exc}",
        )

    return {"message": "Prices refreshed", "prices_refreshed": count}


# ------------------------------------------------------------------
# Add shares the tradebook is missing: bonus issues (free) OR a missing
# buy such as an IPO allotment (real cost). Both re-derive holdings.
# ------------------------------------------------------------------

class AddSharesRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    quantity: float          # number of shares to add
    price: float = 0.0       # per-share cost; 0 = free bonus shares, >0 = a missing buy
    trade_date: str          # YYYY-MM-DD (record date for a bonus, trade/allotment date for a buy)
    isin: Optional[str] = None


class AddSharesResponse(BaseModel):
    message: str
    holdings_synced: int
    prices_refreshed: int


@router.post("/{account_id}/add-shares", response_model=AddSharesResponse)
def add_shares(
    account_id: int,
    body: AddSharesRequest,
    db: Session = Depends(get_db),
):
    """Add shares the tradebook is missing, then re-derive holdings.

    Two cases the tradebook cannot capture:

    * **Bonus / split** (``price = 0``): free shares credited with no trade.
      Recorded as a zero-cost ``bonus`` transaction — raises quantity and
      dilutes the average cost, leaving total cost (and XIRR) unchanged.
    * **Missing buy** (``price > 0``), e.g. an IPO allotment that never appears
      in the Console tradebook: recorded as a real ``buy`` (amount = qty × price)
      so it adds both quantity AND cost basis, and counts as a cashflow in XIRR.
    """
    from datetime import date as _date

    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if body.price < 0:
        raise HTTPException(status_code=400, detail="price cannot be negative")
    try:
        tx_date = _date.fromisoformat(body.trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="trade_date must be YYYY-MM-DD")

    is_bonus = body.price == 0
    db.add(Transaction(
        account_id=account_id,
        symbol=symbol,
        exchange=body.exchange.strip().upper() or "NSE",
        isin=(body.isin.strip().upper() if body.isin else None),
        trade_type="bonus" if is_bonus else "buy",
        quantity=body.quantity,
        price=body.price,
        amount=round(body.quantity * body.price, 2),  # 0 for a bonus
        fees=0.0,
        trade_date=tx_date,
    ))
    db.commit()

    try:
        holdings = derive_holdings_from_transactions(db, account_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Holdings derivation failed: {exc}")

    prices_refreshed = 0
    try:
        prices_refreshed = refresh_prices(db, account_id)
    except RuntimeError:
        pass  # market provider down — holdings still updated

    kind = "bonus" if is_bonus else f"buy @ ₹{body.price:g}"
    return {
        "message": f"Recorded {body.quantity:g} {symbol} shares ({kind}); holdings re-derived.",
        "holdings_synced": len(holdings),
        "prices_refreshed": prices_refreshed,
    }


# ------------------------------------------------------------------
# Record a sale the tradebook is missing: reduces (or fully closes) a
# holding and books realized P&L, then re-derives holdings. The sell-side
# counterpart of add-shares.
# ------------------------------------------------------------------

class SellSharesRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    quantity: float          # number of shares sold
    price: float             # per-share sale price
    trade_date: str          # YYYY-MM-DD
    isin: Optional[str] = None


class SellSharesResponse(BaseModel):
    message: str
    holdings_synced: int
    prices_refreshed: int
    realized_pnl: float       # P&L booked by THIS sale: qty * (price − avg cost)


@router.post("/{account_id}/sell-shares", response_model=SellSharesResponse)
def sell_shares(
    account_id: int,
    body: SellSharesRequest,
    db: Session = Depends(get_db),
):
    """Record a sale and re-derive holdings.

    The sell-side counterpart of :func:`add_shares`: writes a ``sell``
    Transaction (the same row a tradebook import would create), then re-derives
    holdings via the shared moving-average logic — so the position's quantity
    drops, its average cost is left unchanged, and a fully-sold position moves to
    the *Exited* view with its realized P&L. The P&L booked by *this* sale
    (``qty × (price − average cost)``) is returned for immediate feedback.

    You can only sell what the account currently holds; selling more than the
    derived quantity is rejected (add the missing buy first via add-shares).
    """
    from datetime import date as _date

    from app.models.holding import Holding

    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if body.price < 0:
        raise HTTPException(status_code=400, detail="price cannot be negative")
    try:
        tx_date = _date.fromisoformat(body.trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="trade_date must be YYYY-MM-DD")

    # Sell against the current derived holding. Match on symbol alone: holdings
    # are netted per instrument (fungible across exchanges) and Holding.symbol is
    # always stored upper-cased by the derivation, so this is an exact match.
    held = (
        db.query(Holding)
        .filter(Holding.account_id == account_id, Holding.symbol == symbol)
        .first()
    )
    if held is None or held.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"You don't currently hold any {symbol} to sell.",
        )
    if body.quantity > held.quantity + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=f"You hold {held.quantity:g} {symbol}; cannot sell {body.quantity:g}.",
        )

    # Realized P&L is booked at the average cost held BEFORE this sale.
    realized_pnl = round(body.quantity * (body.price - held.average_price), 2)

    db.add(Transaction(
        account_id=account_id,
        symbol=symbol,
        exchange=body.exchange.strip().upper() or "NSE",
        # Carry the instrument's ISIN so the netting groups this sell with the
        # rest of the position even if the symbol was later renamed.
        isin=(body.isin.strip().upper() if body.isin else (held.isin or None)),
        trade_type="sell",
        quantity=body.quantity,
        price=body.price,
        amount=round(body.quantity * body.price, 2),
        fees=0.0,
        trade_date=tx_date,
    ))
    db.commit()

    try:
        holdings = derive_holdings_from_transactions(db, account_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Holdings derivation failed: {exc}")

    prices_refreshed = 0
    try:
        prices_refreshed = refresh_prices(db, account_id)
    except RuntimeError:
        pass  # market provider down — holdings still updated

    outcome = "gain" if realized_pnl >= 0 else "loss"
    return {
        "message": (
            f"Sold {body.quantity:g} {symbol} @ ₹{body.price:g} "
            f"(realized {outcome} ₹{abs(realized_pnl):,.2f}); holdings re-derived."
        ),
        "holdings_synced": len(holdings),
        "prices_refreshed": prices_refreshed,
        "realized_pnl": realized_pnl,
    }


# ------------------------------------------------------------------
# Free cash (manual override of the stale funds-ledger balance)
# ------------------------------------------------------------------

class FreeCashResponse(BaseModel):
    account_id: int
    amount: Optional[float]            # current effective free cash (None if unknown)
    source: str                       # "manual" | "ledger" | "none"


class FreeCashRequest(BaseModel):
    amount: float


@router.get("/{account_id}/free-cash", response_model=FreeCashResponse)
def get_free_cash(account_id: int, db: Session = Depends(get_db)):
    """Current free cash for an account — the manual override if set, else the
    latest imported funds-ledger balance."""
    from app.models.cash import FreeCashOverride
    from app.services.portfolio import _latest_balance_by_account, get_ledger_for_accounts

    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    override = db.get(FreeCashOverride, account_id)
    if override is not None:
        return {"account_id": account_id, "amount": round(override.amount, 2), "source": "manual"}

    ledger = get_ledger_for_accounts(db, [account_id])
    bal = _latest_balance_by_account(ledger).get(account_id)
    if bal is not None:
        return {"account_id": account_id, "amount": round(bal, 2), "source": "ledger"}
    return {"account_id": account_id, "amount": None, "source": "none"}


@router.put("/{account_id}/free-cash", response_model=FreeCashResponse)
def set_free_cash(account_id: int, body: FreeCashRequest, db: Session = Depends(get_db)):
    """Set (upsert) the manual free-cash override for an account. This replaces
    the ledger-derived balance in the portfolio summary and personal XIRR."""
    from app.models.cash import FreeCashOverride

    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    override = db.get(FreeCashOverride, account_id)
    if override is None:
        override = FreeCashOverride(account_id=account_id, amount=body.amount)
        db.add(override)
    else:
        override.amount = body.amount
    db.commit()
    return {"account_id": account_id, "amount": round(body.amount, 2), "source": "manual"}
