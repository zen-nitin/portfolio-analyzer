from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    label: str
    broker: str = "zerodha"
    api_key: str
    api_secret: str


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    broker: str
    api_key: str
    is_active: bool
    access_token_date: Optional[datetime] = None
    created_at: datetime


class AccountSyncResponse(BaseModel):
    message: str
    holdings_synced: int
    positions_synced: int


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
