"""
Accounts router.

CRUD for broker accounts + manual sync trigger.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountRead, AccountSyncResponse
from app.services.sync import sync_account

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    """List all accounts."""
    return db.query(Account).all()


@router.post("", response_model=AccountRead, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    """Create a new broker account."""
    account = Account(
        label=body.label,
        broker=body.broker,
        api_key=body.api_key,
        api_secret=body.api_secret,
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


@router.post("/{account_id}/sync", response_model=AccountSyncResponse)
def trigger_sync(account_id: int, db: Session = Depends(get_db)):
    """Sync holdings and positions from the broker for this account.

    Requires a valid (today's) access token.  Returns 503 if broker
    call fails (e.g. expired token).
    """
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

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
    }
