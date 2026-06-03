from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    label: str
    broker: str = "zerodha"
    # api_key / api_secret are required for Zerodha accounts but optional for
    # manual (CSV-only) accounts that have no broker API integration.
    api_key: Optional[str] = None
    api_secret: Optional[str] = None


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    broker: str
    api_key: Optional[str] = None
    is_active: bool
    access_token_date: Optional[datetime] = None
    created_at: datetime


class AccountSyncResponse(BaseModel):
    message: str
    holdings_synced: int
    positions_synced: int
    prices_refreshed: Optional[int] = None


class AuthLoginUrlResponse(BaseModel):
    login_url: str


class AuthSessionRequest(BaseModel):
    request_token: str


class AuthSessionResponse(BaseModel):
    message: str
    user_id: Optional[str] = None


class AuthStatusResponse(BaseModel):
    connected: bool
    reason: Optional[str] = None
    access_token_date: Optional[datetime] = None
