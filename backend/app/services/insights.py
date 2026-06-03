"""
AI-powered portfolio insights service.

Builds portfolio context from the DB and calls the configured AI provider.
All prompts live in ``app/ai/prompts.py``.
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
