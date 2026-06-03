"""
Authentication router.

Handles the Kite Connect OAuth flow (login URL → request_token → session).

Kite access tokens expire daily (midnight IST).  The status endpoint
compares ``access_token_date`` to today to detect expiry.
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.brokers.registry import get_connector
from app.database import get_db
from app.models.account import Account
from app.schemas.account import (
    AuthLoginUrlResponse,
    AuthSessionRequest,
    AuthSessionResponse,
    AuthStatusResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_account_or_404(account_id: int, db: Session) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return account


@router.get("/{account_id}/login-url", response_model=AuthLoginUrlResponse)
def get_login_url(account_id: int, db: Session = Depends(get_db)):
    """Return the Kite Connect login URL for the given account."""
    account = _get_account_or_404(account_id, db)
    try:
        connector = get_connector(account)
        url = connector.get_login_url()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"login_url": url}


@router.post("/{account_id}/session", response_model=AuthSessionResponse)
def generate_session(
    account_id: int,
    body: AuthSessionRequest,
    db: Session = Depends(get_db),
):
    """Exchange a request_token for an access_token and persist it."""
    account = _get_account_or_404(account_id, db)
    try:
        connector = get_connector(account)
        session_data = connector.generate_session(body.request_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Broker session generation failed: {exc}",
        )

    account.access_token = session_data.get("access_token", "")
    account.access_token_date = datetime.utcnow()
    db.commit()

    return {
        "message": "Session created successfully",
        "user_id": session_data.get("user_id"),
    }


@router.get("/{account_id}/status", response_model=AuthStatusResponse)
def get_auth_status(account_id: int, db: Session = Depends(get_db)):
    """Return whether the account token is valid (issued today).

    Kite tokens expire at midnight IST; we treat any token not from today
    as expired.
    """
    account = _get_account_or_404(account_id, db)

    if not account.access_token or not account.access_token_date:
        return {"connected": False, "reason": "No access token", "access_token_date": None}

    token_date = account.access_token_date.date()
    today = date.today()

    if token_date < today:
        return {
            "connected": False,
            "reason": "Token expired (Kite tokens expire daily – please re-login)",
            "access_token_date": account.access_token_date,
        }

    return {
        "connected": True,
        "reason": None,
        "access_token_date": account.access_token_date,
    }
