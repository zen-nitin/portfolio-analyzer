"""
Prompt assembly for the AI portfolio features.

The app does NOT call any AI model and does NOT fetch market data for these
features. It assembles a self-contained prompt from the user's portfolio context
— the data only the app has: holdings, cost basis, P&L, watchlist, free cash,
XIRR — and hands it to the user to run in Claude/ChatGPT. That model spins up its
own subagents, fetches live data from Yahoo Finance, researches the latest news,
and returns JSON matching the schema, which the user pastes back into the app.

All prompt text + JSON schemas live in ``app/ai/prompts.py``.
"""
from __future__ import annotations

import json
from datetime import date

from app.ai import prompts
from app.models.holding import Holding
from app.models.watchlist import WatchlistItem
from app.services.portfolio import compute_pnl_pct


def current_fy_label(today: date | None = None) -> str:
    """Return the Indian financial year label (Apr–Mar) for ``today``.

    e.g. 2026-06-04 → "2026-27"; 2026-02-10 → "2025-26".
    """
    today = today or date.today()
    start_year = today.year if today.month >= 4 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _portfolio_standing(holdings: list[Holding]) -> dict:
    """Invested / value / P&L and the held symbols, all from the DB (no network)."""
    total_invested = sum(h.average_price * h.quantity for h in holdings)
    current_value = sum(h.last_price * h.quantity for h in holdings)
    pnl = current_value - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested else 0.0
    return {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "symbols": [h.symbol for h in holdings],
    }


def _holdings_block(holdings: list[Holding]) -> str:
    """One line per holding from DB data only — the model fetches live prices."""
    lines = [
        f"- {h.symbol} ({h.exchange}) | qty {h.quantity:g} | avg ₹{h.average_price:,.2f} | "
        f"last-known ₹{h.last_price:,.2f} | "
        f"{compute_pnl_pct(h.pnl, h.average_price, h.quantity):+.1f}%"
        for h in holdings
    ]
    return "\n".join(lines) if lines else "None."


def _watchlist_block(watchlist: list[WatchlistItem]) -> str:
    """One line per watchlist item from DB data only (symbol, exchange, entry zone)."""
    lines = []
    for w in watchlist:
        zone = ""
        low, high = getattr(w, "entry_low", None), getattr(w, "entry_high", None)
        if low is not None or high is not None:
            zone = f" | entry zone ₹{low or '?'}–₹{high or '?'}"
        lines.append(f"- {w.symbol} ({w.exchange}){zone}")
    return "\n".join(lines) if lines else "None."


def _wrap_as_prompt(system: str, user: str, schema: dict) -> str:
    """Combine (system, user, schema) into one copy-paste prompt ending in a
    strict JSON-only instruction."""
    return (
        f"{system}\n\n"
        f"{user}\n\n"
        "When you have finished researching, return ONLY a single JSON object — no "
        "prose, no markdown code fences — that strictly matches this JSON schema:\n"
        f"{json.dumps(schema, indent=2)}"
    )


def watchlist_suggestions_prompt(
    count: int, holdings: list[Holding], watchlist: list[WatchlistItem] | None = None
) -> str:
    """Assemble the watchlist-suggestions prompt to paste into Claude/ChatGPT.

    Carries the user's portfolio context (standing, holdings cost basis, watched
    symbols); the model fetches all market data and does all research itself.
    """
    watchlist = watchlist or []
    context = _portfolio_standing(holdings)
    context["watchlist_symbols"] = [w.symbol.upper() for w in watchlist]
    context["holdings_block"] = _holdings_block(holdings)
    return _wrap_as_prompt(
        prompts.watchlist_suggestions_system(),
        prompts.watchlist_suggestions_user(count, context),
        prompts.WATCHLIST_SUGGESTIONS_SCHEMA,
    )


def portfolio_review_prompt(
    holdings: list[Holding],
    watchlist: list[WatchlistItem],
    summary: dict,
    target_profit_pct: float,
    today: date | None = None,
) -> str:
    """Assemble the portfolio-review prompt to paste into Claude/ChatGPT.

    Carries the portfolio standing (invested, value, P&L, XIRR, free cash) plus
    holdings cost basis and the watchlist; the model fetches live prices/news and
    returns the highest-conviction BUY/SELL moves as JSON.
    """
    context = {
        "fy": current_fy_label(today),
        "target_profit_pct": target_profit_pct,
        "summary": summary,
        "holdings_block": _holdings_block(holdings),
        "watchlist_block": _watchlist_block(watchlist),
    }
    return _wrap_as_prompt(
        prompts.portfolio_review_system(),
        prompts.portfolio_review_user(context),
        prompts.PORTFOLIO_REVIEW_SCHEMA,
    )
