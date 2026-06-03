"""
Market data router.

Exposes live price quotes, financial statistics, historical data, and
performance metrics from the configured MarketDataProvider.

All endpoints return HTTP 503 when the provider raises RuntimeError
(provider unavailable, symbol not found, Yahoo Finance down, etc.).

Endpoints:
    GET /api/market/quote?symbols=RELIANCE,INFY&exchange=NSE
    GET /api/market/stats/{symbol}?exchange=NSE
    GET /api/market/history/{symbol}?period=1y&interval=1d&exchange=NSE
    GET /api/market/performance/{symbol}?exchange=NSE
    GET /api/market/providers
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.market.registry import get_market_provider, list_market_providers

router = APIRouter(prefix="/api/market", tags=["market"])


# ------------------------------------------------------------------
# Response schemas (lightweight – provider dicts pass through directly)
# ------------------------------------------------------------------

class MarketProviderInfo(BaseModel):
    name: str
    active: bool
    configured: bool


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _get_provider():
    """Return the active MarketDataProvider or raise HTTP 503."""
    try:
        return get_market_provider()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Market data provider not available: {exc}",
        )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/quote")
def get_quotes(
    symbols: str = Query(
        ...,
        description="Comma-separated list of trading symbols, e.g. RELIANCE,INFY",
    ),
    exchange: str = Query("NSE", description="Exchange: NSE (default) or BSE"),
):
    """Fetch live quotes for one or more symbols.

    ``symbols`` is a comma-separated string; all are looked up on the same
    ``exchange``.  To mix exchanges, call this endpoint multiple times.
    """
    provider = _get_provider()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="No symbols provided")

    pairs = [(sym, exchange.upper()) for sym in symbol_list]
    try:
        result = provider.get_quotes(pairs)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return result


@router.get("/stats/{symbol}")
def get_stats(
    symbol: str,
    exchange: str = Query("NSE", description="Exchange: NSE (default) or BSE"),
):
    """Fetch financial statistics for a single symbol."""
    provider = _get_provider()
    try:
        return provider.get_stats(symbol.upper(), exchange.upper())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/history/{symbol}")
def get_history(
    symbol: str,
    period: str = Query("1y", description="History period: 1mo, 3mo, 6mo, 1y, 5y, max"),
    interval: str = Query("1d", description="Bar interval: 1d, 1wk, 1mo"),
    exchange: str = Query("NSE", description="Exchange: NSE (default) or BSE"),
):
    """Fetch OHLCV history for a symbol."""
    provider = _get_provider()
    try:
        return provider.get_history(symbol.upper(), period, interval, exchange.upper())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/performance/{symbol}")
def get_performance(
    symbol: str,
    exchange: str = Query("NSE", description="Exchange: NSE (default) or BSE"),
):
    """Fetch trailing return percentages (1m, 6m, 1y, 5y) for a symbol."""
    provider = _get_provider()
    try:
        return provider.get_performance(symbol.upper(), exchange.upper())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/providers", response_model=list[MarketProviderInfo])
def list_providers():
    """List all known market data providers with active/configured flags."""
    return list_market_providers()
