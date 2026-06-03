"""
Zerodha Kite Connect broker connector.

Uses the official ``kiteconnect`` Python SDK.  Credentials (api_key,
api_secret) are stored per-account in the database; the access_token is
refreshed daily via the auth flow.
"""
from typing import Any

from kiteconnect import KiteConnect  # type: ignore[import-untyped]

from app.brokers.base import BrokerConnector


class ZerodhaConnector(BrokerConnector):
    """Broker connector implementation for Zerodha Kite Connect API."""

    def __init__(self, api_key: str, api_secret: str, access_token: str | None = None) -> None:
        super().__init__(api_key, api_secret, access_token)
        self._kite = KiteConnect(api_key=api_key)
        if access_token:
            self._kite.set_access_token(access_token)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def get_login_url(self) -> str:
        """Return the Kite login URL (redirects back with request_token)."""
        return self._kite.login_url()

    def generate_session(self, request_token: str) -> dict:
        """Exchange request_token for access_token using api_secret.

        Returns a dict with access_token, user_id, user_name, etc.
        """
        data = self._kite.generate_session(request_token, api_secret=self.api_secret)
        # Store the token on this instance so subsequent calls work
        self._kite.set_access_token(data["access_token"])
        self.access_token = data["access_token"]
        return data

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def get_holdings(self) -> list[dict]:
        """Fetch equity holdings (long-term) from Kite API."""
        return self._kite.holdings()  # type: ignore[return-value]

    def get_positions(self) -> list[dict]:
        """Fetch open positions (intraday + short-term) from Kite API.

        Returns a flat list merging ``net`` and ``day`` position buckets.
        """
        positions = self._kite.positions()
        # Kite returns {"net": [...], "day": [...]}; we expose the net view
        if isinstance(positions, dict):
            return positions.get("net", [])
        return positions  # type: ignore[return-value]

    def get_quote(self, instruments: list[str]) -> dict[str, Any]:
        """Fetch live quotes for a list of 'EXCHANGE:SYMBOL' strings."""
        return self._kite.quote(instruments)  # type: ignore[return-value]

    def get_profile(self) -> dict:
        """Fetch the Kite user profile."""
        return self._kite.profile()  # type: ignore[return-value]
