"""
Yahoo Finance market data provider (via the ``yfinance`` package).

IMPORTANT DISCLAIMER: yfinance is an UNOFFICIAL, reverse-engineered wrapper
around Yahoo Finance's internal API.  It is not endorsed by Yahoo and may
break without notice when Yahoo changes its endpoints or data format.  Do not
use this in production systems that require guaranteed uptime.  For a personal
local tool it is perfectly adequate.

Exchange suffix mapping:
    NSE  →  .NS   (National Stock Exchange of India)
    BSE  →  .BO   (Bombay Stock Exchange)
    (all other exchange values are passed through unchanged)
"""
from __future__ import annotations

import yfinance as yf  # type: ignore[import-untyped]
from datetime import datetime, timedelta
from typing import Any

from app.market.base import MarketDataProvider

# Exchange identifier → Yahoo Finance ticker suffix
_EXCHANGE_SUFFIX: dict[str, str] = {
    "NSE": ".NS",
    "BSE": ".BO",
}


def _yahoo_symbol(symbol: str, exchange: str) -> str:
    """Build the Yahoo Finance ticker string for a given symbol + exchange."""
    suffix = _EXCHANGE_SUFFIX.get(exchange.upper(), "")
    return f"{symbol.upper()}{suffix}"


def _safe(value: Any, cast=None, default=None):
    """Return value converted by cast, or default on None/NaN/exception."""
    if value is None:
        return default
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return default
    except Exception:
        pass
    if cast is not None:
        try:
            return cast(value)
        except (TypeError, ValueError):
            return default
    return value


class YFinanceProvider(MarketDataProvider):
    """MarketDataProvider implementation backed by yfinance."""

    def _ticker(self, symbol: str, exchange: str):
        """Return a yfinance Ticker object."""
        return yf.Ticker(_yahoo_symbol(symbol, exchange))

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str, exchange: str = "NSE") -> dict:
        """Fetch a live quote from Yahoo Finance."""
        try:
            ticker = self._ticker(symbol, exchange)
            info = ticker.fast_info  # fast_info is lighter than full .info
            last_price = _safe(getattr(info, "last_price", None), float)
            previous_close = _safe(getattr(info, "previous_close", None), float)
            if last_price is None:
                # Try full info as fallback
                full = ticker.info
                last_price = _safe(
                    full.get("currentPrice") or full.get("regularMarketPrice"),
                    float,
                )
                previous_close = _safe(full.get("previousClose"), float)

            if last_price is None:
                raise RuntimeError(
                    f"No price data returned by Yahoo Finance for "
                    f"{_yahoo_symbol(symbol, exchange)}. "
                    "The symbol may be delisted, incorrect, or Yahoo Finance may be unavailable."
                )

            day_change: float | None = None
            day_change_pct: float | None = None
            if last_price is not None and previous_close:
                day_change = round(last_price - previous_close, 4)
                day_change_pct = round((day_change / previous_close) * 100, 4)

            return {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "last_price": round(last_price, 4),
                "previous_close": round(previous_close, 4) if previous_close else None,
                "day_change": day_change,
                "day_change_pct": day_change_pct,
                "currency": _safe(getattr(info, "currency", None), str, "INR"),
            }
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Yahoo Finance quote failed for {symbol} ({exchange}): {exc}"
            ) from exc

    def get_quotes(self, symbols: list[tuple[str, str]]) -> list[dict]:
        """Fetch quotes for a batch of (symbol, exchange) pairs."""
        results = []
        for sym, exch in symbols:
            try:
                results.append(self.get_quote(sym, exch))
            except RuntimeError:
                # Skip individual failures; don't abort the whole batch
                continue
        return results

    # ------------------------------------------------------------------
    # Stats / fundamentals
    # ------------------------------------------------------------------

    def get_stats(self, symbol: str, exchange: str = "NSE") -> dict:
        """Fetch key financial statistics from Yahoo Finance."""
        try:
            ticker = self._ticker(symbol, exchange)
            info = ticker.info  # full info dict

            def g(key, cast=None, default=None):
                return _safe(info.get(key), cast, default)

            last_price = g("currentPrice", float) or g("regularMarketPrice", float)
            volume = g("volume", int) or g("regularMarketVolume", int)
            avg_volume = g("averageVolume", int) or g("averageVolume10days", int)

            return {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "name": g("longName", str) or g("shortName", str),
                "last_price": round(last_price, 4) if last_price else None,
                "market_cap": g("marketCap", float),
                "pe_ratio": g("trailingPE", float) or g("forwardPE", float),
                "pb_ratio": g("priceToBook", float),
                "eps": g("trailingEps", float),
                "dividend_yield": g("dividendYield", float),
                "week52_high": g("fiftyTwoWeekHigh", float),
                "week52_low": g("fiftyTwoWeekLow", float),
                "beta": g("beta", float),
                "volume": volume,
                "avg_volume": avg_volume,
                "day_high": g("dayHigh", float) or g("regularMarketDayHigh", float),
                "day_low": g("dayLow", float) or g("regularMarketDayLow", float),
                "sector": g("sector", str),
                "industry": g("industry", str),
            }
        except Exception as exc:
            raise RuntimeError(
                f"Yahoo Finance stats failed for {symbol} ({exchange}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    def get_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        exchange: str = "NSE",
    ) -> dict:
        """Download OHLCV history from Yahoo Finance."""
        try:
            ticker = self._ticker(symbol, exchange)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)

            if df is None or df.empty:
                raise RuntimeError(
                    f"No history returned by Yahoo Finance for "
                    f"{_yahoo_symbol(symbol, exchange)} "
                    f"(period={period}, interval={interval})."
                )

            points = []
            for ts, row in df.iterrows():
                try:
                    date_str = ts.strftime("%Y-%m-%d")
                    close = _safe(row.get("Close"), float)
                    volume = _safe(row.get("Volume"), int, 0)
                    if close is None:
                        continue
                    points.append({"date": date_str, "close": close, "volume": volume})
                except Exception:
                    continue

            return {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "period": period,
                "interval": interval,
                "points": points,
            }
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Yahoo Finance history failed for {symbol} ({exchange}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Derived performance
    # ------------------------------------------------------------------

    def get_performance(self, symbol: str, exchange: str = "NSE") -> dict:
        """Compute trailing return percentages from Yahoo Finance history."""
        try:
            # Fetch 5y of daily closes so we can compute all periods
            ticker = self._ticker(symbol, exchange)
            df = ticker.history(period="5y", interval="1d", auto_adjust=True)

            returns: dict[str, float | None] = {"1m": None, "6m": None, "1y": None, "5y": None}

            if df is None or df.empty:
                return {
                    "symbol": symbol.upper(),
                    "exchange": exchange.upper(),
                    "returns": returns,
                }

            # Build a sorted list of (date, close)
            closes = []
            for ts, row in df.iterrows():
                close = _safe(row.get("Close"), float)
                if close is not None:
                    closes.append((ts.to_pydatetime(), close))
            closes.sort(key=lambda x: x[0])

            if not closes:
                return {
                    "symbol": symbol.upper(),
                    "exchange": exchange.upper(),
                    "returns": returns,
                }

            latest_dt, latest_close = closes[-1]

            def _return_for_days(days: int) -> float | None:
                target = latest_dt - timedelta(days=days)
                # Find the first close on or after the target date
                candidates = [(dt, c) for dt, c in closes if dt <= latest_dt]
                past = [c for dt, c in candidates if dt <= target]
                if not past:
                    return None
                past_close = past[-1]
                if past_close == 0:
                    return None
                return round((latest_close - past_close) / past_close, 6)

            returns["1m"] = _return_for_days(30)
            returns["6m"] = _return_for_days(180)
            returns["1y"] = _return_for_days(365)
            returns["5y"] = _return_for_days(1825)

            return {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "returns": returns,
            }
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Yahoo Finance performance failed for {symbol} ({exchange}): {exc}"
            ) from exc
