"""
AI-powered portfolio insights service.

Builds portfolio context from the DB and calls the configured AI provider.
All prompts live in ``app/ai/prompts.py``.

Market stats (PE, 52-wk range, etc.) are fetched from the configured
MarketDataProvider and injected into the prompt context when available.
If the market provider is unavailable the AI still generates a response
using only the holdings data it already has.
"""
from __future__ import annotations

from fastapi import HTTPException

from app.ai import registry as ai_registry
from app.ai import prompts
from app.models.holding import Holding


def _require_provider():
    """Get active AI provider or raise HTTP 503."""
    provider = ai_registry.get_provider()
    if provider is None:
        active = ai_registry.settings.AI_PROVIDER
        raise HTTPException(
            status_code=503,
            detail=(
                f"AI provider '{active}' is not available. "
                "Check that the API key is configured in .env. "
                "NOTE: A ChatGPT subscription does NOT include API access – "
                "obtain an API key from https://platform.openai.com/api-keys"
            ),
        )
    return provider


def _build_portfolio_context(holdings: list[Holding]) -> dict:
    """Build a lightweight context dict from current holdings."""
    total_invested = sum(h.average_price * h.quantity for h in holdings)
    current_value = sum(h.last_price * h.quantity for h in holdings)
    pnl = current_value - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested else 0.0
    symbols = [h.symbol for h in holdings]
    return {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "symbols": symbols,
    }


def _fetch_market_stats(symbol: str, exchange: str) -> dict | None:
    """Fetch market stats for a symbol, returning None on any failure."""
    try:
        from app.market.registry import get_market_provider
        provider = get_market_provider()
        return provider.get_stats(symbol, exchange)
    except Exception:
        return None


def _format_market_stats(stats: dict | None) -> str:
    """Format market stats into a compact string for the prompt context."""
    if not stats:
        return "Market data unavailable."
    parts = []
    if stats.get("name"):
        parts.append(f"Company: {stats['name']}")
    if stats.get("last_price") is not None:
        parts.append(f"Last price: ₹{stats['last_price']:,.2f}")
    if stats.get("market_cap") is not None:
        mc = stats["market_cap"]
        if mc >= 1e12:
            parts.append(f"Market cap: ₹{mc/1e12:.2f}T")
        elif mc >= 1e9:
            parts.append(f"Market cap: ₹{mc/1e9:.1f}B")
        else:
            parts.append(f"Market cap: ₹{mc:,.0f}")
    if stats.get("pe_ratio") is not None:
        parts.append(f"P/E: {stats['pe_ratio']:.1f}x")
    if stats.get("pb_ratio") is not None:
        parts.append(f"P/B: {stats['pb_ratio']:.2f}x")
    if stats.get("eps") is not None:
        parts.append(f"EPS: ₹{stats['eps']:.2f}")
    if stats.get("dividend_yield") is not None:
        parts.append(f"Dividend yield: {stats['dividend_yield']*100:.2f}%")
    if stats.get("week52_high") is not None and stats.get("week52_low") is not None:
        parts.append(
            f"52-wk range: ₹{stats['week52_low']:,.2f} – ₹{stats['week52_high']:,.2f}"
        )
    if stats.get("beta") is not None:
        parts.append(f"Beta: {stats['beta']:.2f}")
    if stats.get("sector"):
        parts.append(f"Sector: {stats['sector']}")
    if stats.get("industry"):
        parts.append(f"Industry: {stats['industry']}")
    return " | ".join(parts) if parts else "Market data unavailable."


def watchlist_suggestions(count: int, holdings: list[Holding]) -> dict:
    """Suggest ``count`` stocks to watch based on current portfolio.

    Returns:
        ``{"suggestions": [{symbol, exchange, rationale}, ...]}``
    """
    provider = _require_provider()
    context = _build_portfolio_context(holdings)
    result = provider.complete(
        system=prompts.watchlist_suggestions_system(),
        user=prompts.watchlist_suggestions_user(count, context),
        json_schema=prompts.WATCHLIST_SUGGESTIONS_SCHEMA,
    )
    if isinstance(result, str):
        return {"suggestions": []}
    return result  # type: ignore[return-value]


def recommendation(symbol: str, exchange: str, holdings: list[Holding]) -> dict:
    """BUY/SELL/HOLD recommendation for ``symbol``.

    Includes live market stats in the prompt context when available.

    Returns:
        ``{action, confidence, rationale, key_risks, time_horizon}``
    """
    provider = _require_provider()
    context = _build_portfolio_context(holdings)
    context["exchange"] = exchange

    # Find holding detail if the user already holds this symbol
    held = next((h for h in holdings if h.symbol.upper() == symbol.upper()), None)
    if held:
        context["holding_detail"] = (
            f"qty={held.quantity}, avg_price={held.average_price}, "
            f"last_price={held.last_price}, pnl={held.pnl}"
        )
    else:
        context["holding_detail"] = None

    # Enrich with live market stats (degrade gracefully if unavailable)
    stats = _fetch_market_stats(symbol, exchange)
    context["market_stats"] = _format_market_stats(stats)

    result = provider.complete(
        system=prompts.recommendation_system(),
        user=prompts.recommendation_user(symbol, context),
        json_schema=prompts.RECOMMENDATION_SCHEMA,
    )
    if isinstance(result, str):
        return {"action": "HOLD", "confidence": 0.0, "rationale": result,
                "key_risks": [], "time_horizon": "unknown"}
    return result  # type: ignore[return-value]


def analysis(symbol: str, exchange: str, holdings: list[Holding]) -> dict:
    """Comprehensive structured analysis for ``symbol``.

    Includes live market stats in the prompt context when available.

    Returns a dict matching ANALYSIS_SCHEMA.
    """
    provider = _require_provider()
    context = _build_portfolio_context(holdings)
    context["exchange"] = exchange

    held = next((h for h in holdings if h.symbol.upper() == symbol.upper()), None)
    if held:
        context["holding_detail"] = (
            f"qty={held.quantity}, avg_price={held.average_price}, "
            f"last_price={held.last_price}, pnl={held.pnl}"
        )
    else:
        context["holding_detail"] = None

    # Enrich with live market stats (degrade gracefully if unavailable)
    stats = _fetch_market_stats(symbol, exchange)
    context["market_stats"] = _format_market_stats(stats)

    result = provider.complete(
        system=prompts.analysis_system(),
        user=prompts.analysis_user(symbol, context),
        json_schema=prompts.ANALYSIS_SCHEMA,
    )
    if isinstance(result, str):
        return {"symbol": symbol, "exchange": exchange, "summary": result,
                "strengths": [], "weaknesses": [], "opportunities": [], "threats": [],
                "valuation_view": "unknown", "sentiment": "neutral", "catalysts": []}
    return result  # type: ignore[return-value]
