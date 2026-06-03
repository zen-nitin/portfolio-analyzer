"""
Abstract broker connector interface.

Extension guide – adding a new broker:
1. Create ``app/brokers/<name>.py`` and subclass ``BrokerConnector``.
2. Implement every abstract method.  The constructor receives api_key,
   api_secret, and (optionally) access_token so it is fully self-contained.
3. Register the new class in ``app/brokers/registry.py`` under an
   identifying string (e.g. ``"zerodha"``).
4. Add an Account row with ``broker=<that string>`` – the factory will
   automatically instantiate the right connector.

No other changes are needed anywhere in the codebase.
"""
from abc import ABC, abstractmethod
from typing import Any


class BrokerConnector(ABC):
    """Base class for all broker integrations.

    Every method raises ``NotImplementedError`` at the ABC level so that
    partially-implemented subclasses fail loudly at call time.
    """

    def __init__(self, api_key: str, api_secret: str, access_token: str | None = None) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token

    # ------------------------------------------------------------------
    # Authentication flow
    # ------------------------------------------------------------------

    @abstractmethod
    def get_login_url(self) -> str:
        """Return the OAuth / redirect URL the user must visit to authorise.

        After visiting this URL the broker redirects back with a
        ``request_token`` query-parameter that is passed to
        ``generate_session``.
        """

    @abstractmethod
    def generate_session(self, request_token: str) -> dict:
        """Exchange a one-time request token for a persistent access token.

        Returns a dict with at minimum:
            ``access_token`` (str)
            ``user_id``      (str, optional)
            ``user_name``    (str, optional)
        """

    # ------------------------------------------------------------------
    # Data methods – require a valid access token
    # ------------------------------------------------------------------

    @abstractmethod
    def get_holdings(self) -> list[dict]:
        """Return the long-term equity holdings for the account.

        Each item should include at minimum:
            tradingsymbol, exchange, isin, quantity, average_price,
            last_price, pnl, day_change
        """

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return open intraday / short-term F&O positions.

        Each item should include at minimum:
            tradingsymbol, exchange, quantity, average_price, last_price,
            pnl, day_change
        """

    @abstractmethod
    def get_quote(self, instruments: list[str]) -> dict[str, Any]:
        """Fetch live quotes for a list of instrument keys.

        ``instruments`` format: ``["NSE:INFY", "BSE:RELIANCE"]``

        Returns a dict keyed by instrument key.
        """

    @abstractmethod
    def get_profile(self) -> dict:
        """Return the broker account profile (name, email, etc.)."""
