"""
Abstract market data provider interface.

Extension guide – adding a new market data provider:
1. Create ``app/market/<name>_provider.py`` and subclass ``MarketDataProvider``.
2. Implement every abstract method.  All methods should be defensive: market
   data sources (especially unofficial ones) may return ``None``, missing
   fields, or raise unexpectedly.  Convert hard failures into ``RuntimeError``
   so the registry and routers can return HTTP 503 gracefully.
3. Add an entry to ``app/market/registry.py`` PROVIDER_REGISTRY.
4. Set ``MARKET_DATA_PROVIDER=<name>`` in ``.env``.

Providers:
* Should never propagate raw third-party exceptions to callers.
* Should return ``None`` for optional numeric fields that are unavailable
  rather than omitting the key entirely – keeps the response shape stable.
* Are responsible for mapping exchange identifiers (e.g. "NSE", "BSE") to
  whatever the underlying data source requires.
"""
from abc import ABC, abstractmethod


class MarketDataProvider(ABC):
    """Base class for live market data integrations."""

    # ------------------------------------------------------------------
    # Quote methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_quote(self, symbol: str, exchange: str = "NSE") -> dict:
        """Fetch a live quote for a single instrument.

        Args:
            symbol:   Trading symbol (e.g. "RELIANCE", "INFY").
            exchange: Exchange identifier – "NSE" (default) or "BSE".

        Returns:
            Dict with keys:
                symbol       (str)
                exchange     (str)
                last_price   (float)
                previous_close (float | None)
                day_change   (float | None)   – absolute change
                day_change_pct (float | None) – percentage change
                currency     (str)            – e.g. "INR"

        Raises:
            RuntimeError: On hard failure (provider unavailable, symbol not
                found, etc.).  The router converts this to HTTP 503.
        """

    @abstractmethod
    def get_quotes(self, symbols: list[tuple[str, str]]) -> list[dict]:
        """Fetch live quotes for a batch of instruments.

        Args:
            symbols: List of (symbol, exchange) tuples.

        Returns:
            List of quote dicts (same shape as ``get_quote``).  If a
            particular symbol fails, it may be omitted from the result
            rather than causing the entire batch to fail.

        Raises:
            RuntimeError: On hard failure affecting the whole batch.
        """

    # ------------------------------------------------------------------
    # Stats / fundamentals
    # ------------------------------------------------------------------

    @abstractmethod
    def get_stats(self, symbol: str, exchange: str = "NSE") -> dict:
        """Fetch key financial statistics for a stock.

        Args:
            symbol:   Trading symbol.
            exchange: Exchange identifier.

        Returns:
            Dict with keys (all optional fields may be ``None``):
                symbol        (str)
                exchange      (str)
                name          (str | None)    – company name
                last_price    (float | None)
                market_cap    (float | None)  – in local currency units
                pe_ratio      (float | None)
                pb_ratio      (float | None)
                eps           (float | None)
                dividend_yield (float | None) – as decimal, e.g. 0.02 = 2%
                week52_high   (float | None)
                week52_low    (float | None)
                beta          (float | None)
                volume        (int | None)    – latest day volume
                avg_volume    (int | None)    – 3-month average volume
                day_high      (float | None)
                day_low       (float | None)
                sector        (str | None)
                industry      (str | None)

        Raises:
            RuntimeError: On hard failure.
        """

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        exchange: str = "NSE",
    ) -> dict:
        """Fetch OHLCV history for a stock.

        Args:
            symbol:   Trading symbol.
            period:   Duration string – "1mo", "3mo", "6mo", "1y", "5y", "max".
            interval: Bar size – "1d", "1wk", "1mo".
            exchange: Exchange identifier.

        Returns:
            Dict with keys:
                symbol   (str)
                exchange (str)
                period   (str)
                interval (str)
                points   (list[dict]) – each point: {date: "YYYY-MM-DD",
                                         close: float, volume: int}

        Raises:
            RuntimeError: On hard failure.
        """

    # ------------------------------------------------------------------
    # Derived performance
    # ------------------------------------------------------------------

    @abstractmethod
    def get_performance(self, symbol: str, exchange: str = "NSE") -> dict:
        """Compute trailing return percentages from historical closes.

        Args:
            symbol:   Trading symbol.
            exchange: Exchange identifier.

        Returns:
            Dict with keys:
                symbol   (str)
                exchange (str)
                returns  (dict) – {
                    "1m":  float | None,   – 1-month return as decimal
                    "6m":  float | None,   – 6-month return
                    "1y":  float | None,   – 1-year return
                    "5y":  float | None,   – 5-year return
                }
            Convention: 0.12 means +12%, -0.05 means -5%.

        Raises:
            RuntimeError: On hard failure.
        """
