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
