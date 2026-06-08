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

import json
from datetime import date

from fastapi import HTTPException

from app.ai import registry as ai_registry
from app.ai import prompts
from app.models.holding import Holding
from app.models.watchlist import WatchlistItem
from app.services.portfolio import compute_pnl_pct


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


def _fetch_movers(count: int = 10) -> dict:
    """Best-effort structured top gainers/losers. Returns empty lists on failure."""
    try:
        from app.market.registry import get_market_provider
        return get_market_provider().get_movers(count=count)
    except Exception:
        return {"gainers": [], "losers": []}


def _format_movers(movers: dict) -> str:
    """Format structured movers into compact prompt text."""
    def fmt(items: list) -> str:
        rows = [
            f"- {i.get('symbol')} ({i.get('exchange', 'NSE')}) {i.get('change_pct', 0):+.1f}%"
            + (f" | {i['name']}" if i.get("name") else "")
            for i in items
        ]
        return "\n".join(rows) if rows else "  (none available)"

    return (
        f"TOP GAINERS (momentum / breakouts):\n{fmt(movers.get('gainers', []))}\n\n"
        f"TOP LOSERS (oversold / turnaround candidates):\n{fmt(movers.get('losers', []))}"
    )


def _market_provider():
    """Best-effort market provider, or None."""
    try:
        from app.market.registry import get_market_provider
        return get_market_provider()
    except Exception:
        return None


def _fetch_sector_leaders() -> list[dict]:
    p = _market_provider()
    try:
        return p.get_sector_leaders() if p else []
    except Exception:
        return []


def _fetch_growth_leaders() -> list[dict]:
    p = _market_provider()
    try:
        return p.get_growth_leaders() if p else []
    except Exception:
        return []


def _fetch_industry_peers(industries: list[str], exclude: set[str]) -> dict:
    p = _market_provider()
    if not p or not industries:
        return {}
    try:
        return p.get_industry_peers(industries, exclude=exclude)
    except Exception:
        return {}


def _fetch_industries(pairs: list[tuple[str, str]]) -> list[str]:
    """Best-effort distinct Yahoo industry strings for (symbol, exchange) pairs
    (bounded to bound network cost — used for the watchlist names)."""
    out: list[str] = []
    for sym, exch in pairs[:20]:
        stats = _fetch_market_stats(sym, exch) or {}
        if stats.get("industry"):
            out.append(stats["industry"])
    return out


def _exclude_symbols(items: list[dict], exclude: set[str]) -> list[dict]:
    return [i for i in items if (i.get("symbol") or "").upper() not in exclude]


def _format_idea_list(items: list[dict], with_sector: bool = False) -> str:
    rows = []
    for i in items:
        tag = f" [{i['sector']}]" if with_sector and i.get("sector") else ""
        name = f" | {i['name']}" if i.get("name") else ""
        rows.append(f"- {i.get('symbol')} ({i.get('exchange', 'NSE')}){tag}{name}")
    return "\n".join(rows) if rows else "  (none available)"


def _format_peers(peers: dict) -> str:
    if not peers:
        return "  (none available)"
    return "\n".join(
        f"- {ind}: {', '.join(i.get('symbol') for i in items)}"
        for ind, items in peers.items()
    )


def _build_holdings_risk_context(holdings: list[Holding]) -> tuple[str, str, list[str]]:
    """Return (per-holding risk block, sector-exposure block, holding industries).

    Per holding: portfolio weight %, P&L %, sector/beta (best-effort via market
    stats), and risk flags (concentrated / big-run-up / high-beta / rich-PE) so
    the model can flag risky positions and propose swap candidates. The distinct
    Yahoo industry strings are also collected to drive the peer/competitive pool.
    """
    total_value = sum(h.last_price * h.quantity for h in holdings)
    lines: list[str] = []
    sector_weights: dict[str, float] = {}
    industries: list[str] = []

    for h in holdings:
        value = h.last_price * h.quantity
        weight = (value / total_value * 100) if total_value else 0.0
        pnl_pct = compute_pnl_pct(h.pnl, h.average_price, h.quantity)
        stats = _fetch_market_stats(h.symbol, h.exchange) or {}
        sector = stats.get("sector")
        beta = stats.get("beta")
        pe = stats.get("pe_ratio")
        if stats.get("industry"):
            industries.append(stats["industry"])

        flags: list[str] = []
        if weight > 18:
            flags.append("concentrated")
        if pnl_pct > 60:
            flags.append("big-run-up")
        if beta is not None and beta > 1.3:
            flags.append("high-beta")
        if pe is not None and pe > 60:
            flags.append("rich-PE")

        extras = ""
        if sector:
            extras += f" | {sector}"
        if beta is not None:
            extras += f" | beta {beta:.2f}"
        if flags:
            extras += f" | RISK: {', '.join(flags)}"
        lines.append(
            f"- {h.symbol} ({h.exchange}) | weight {weight:.1f}% | P&L {pnl_pct:+.1f}%{extras}"
        )
        if sector:
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

    holdings_block = "\n".join(lines) if lines else "No current holdings."
    sector_block = (
        "\n".join(
            f"- {sec}: {w:.0f}%"
            for sec, w in sorted(sector_weights.items(), key=lambda kv: -kv[1])
        )
        or "Sector data unavailable."
    )
    return holdings_block, sector_block, list(dict.fromkeys(industries))


def build_watchlist_suggestions_request(
    provider,
    count: int,
    holdings: list[Holding],
    watchlist: list[WatchlistItem] | None = None,
) -> tuple[str, str, dict]:
    """Build the ``(system, user, json_schema)`` for watchlist suggestions.

    Shared by the synchronous and batch paths. Assembles, all best-effort:
    per-holding risk context (weights, sector, risk flags), structured top
    gainers/losers, and a web-research brief (news/catalysts/sentiment). The
    Responses API web-search tool cannot be batched, so research runs here.
    """
    watchlist = watchlist or []
    context = _build_portfolio_context(holdings)

    held_symbols = [h.symbol.upper() for h in holdings]
    watch_symbols = [w.symbol.upper() for w in watchlist]
    exclude = set(held_symbols) | set(watch_symbols)

    holdings_block, sector_block, holding_industries = _build_holdings_risk_context(holdings)
    context["holdings_risk_block"] = holdings_block
    context["sector_block"] = sector_block
    context["movers_block"] = _format_movers(_fetch_movers(count=10))
    context["watchlist_symbols"] = watch_symbols

    # Additional structured idea pools (all best-effort → omitted if empty):
    #  • sector leaders (top by size across industries)
    #  • growth leaders (high revenue/EPS growth across industries)
    #  • competitive set (peers of the user's holdings + watchlist, by industry)
    context["sector_leaders_block"] = _format_idea_list(
        _exclude_symbols(_fetch_sector_leaders(), exclude), with_sector=True
    )
    context["growth_leaders_block"] = _format_idea_list(
        _exclude_symbols(_fetch_growth_leaders(), exclude)
    )
    industries = list(dict.fromkeys(
        holding_industries + _fetch_industries([(w.symbol, w.exchange) for w in watchlist])
    ))
    context["peers_block"] = _format_peers(_fetch_industry_peers(industries, exclude))

    context["web_research"] = _run_web_search(
        provider,
        prompts.watchlist_research_system(),
        prompts.watchlist_research_user(held_symbols, count),
    )
    return (
        prompts.watchlist_suggestions_system(),
        prompts.watchlist_suggestions_user(count, context),
        prompts.WATCHLIST_SUGGESTIONS_SCHEMA,
    )


def shape_watchlist_result(result: dict | str) -> dict:
    """Normalize a watchlist-suggestions completion into the API response shape.

    Used by both the sync service and the batch poll endpoint so they return an
    identical ``{"suggestions": [...], "flagged_holdings": [...]}`` payload.
    """
    if not isinstance(result, dict):
        return {"suggestions": [], "flagged_holdings": []}
    result.setdefault("suggestions", [])
    result.setdefault("flagged_holdings", [])
    return result


def watchlist_suggestions(
    count: int, holdings: list[Holding], watchlist: list[WatchlistItem] | None = None
) -> dict:
    """Suggest ``count`` stocks to watch — a bucketed bench (core/tactical/swap).

    Returns ``{"suggestions": [...], "flagged_holdings": [...]}``.
    """
    provider = _require_provider()
    system, user, schema = build_watchlist_suggestions_request(
        provider, count, holdings, watchlist
    )
    result = provider.complete(system=system, user=user, json_schema=schema)
    return shape_watchlist_result(result)


# ------------------------------------------------------------------
# "Generate elsewhere" — assemble the prompt for pasting into ChatGPT/Claude.
# Requires NO AI provider/API key: the user runs it on their own subscription
# and pastes the JSON back. Web research is skipped (the external model can
# browse); all the portfolio context (movers, holdings risk) is still included.
# ------------------------------------------------------------------

def _external_prompt(system: str, user: str, schema: dict) -> str:
    """Combine (system, user, schema) into one copy-paste prompt that asks for
    raw JSON matching the schema."""
    return (
        f"{system}\n\n"
        f"{user}\n\n"
        "No DEEP RESEARCH section is included here — so YOU must do that research: browse the web "
        "for each name you recommend and gather recent news + the latest annual-report / results "
        "fundamentals (revenue & PAT growth, margins, debt, ROE, guidance, key risks) before "
        "recommending it, and cite that evidence in each rationale.\n\n"
        "Return ONLY a single JSON object — no prose, no markdown code fences — that strictly "
        "matches this JSON schema:\n"
        f"{json.dumps(schema, indent=2)}"
    )


def external_watchlist_prompt(
    count: int, holdings: list[Holding], watchlist: list[WatchlistItem] | None = None
) -> str:
    """The watchlist-suggestions prompt, ready to paste into ChatGPT/Claude."""
    system, user, schema = build_watchlist_suggestions_request(None, count, holdings, watchlist)
    return _external_prompt(system, user, schema)


def external_review_prompt(
    holdings: list[Holding],
    watchlist: list[WatchlistItem],
    summary: dict,
    target_profit_pct: float,
    today: date | None = None,
) -> str:
    """The portfolio-review prompt, ready to paste into ChatGPT/Claude."""
    system, user, schema = build_portfolio_review_request(
        None, holdings, watchlist, summary, target_profit_pct, today
    )
    return _external_prompt(system, user, schema)


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


def current_fy_label(today: date | None = None) -> str:
    """Return the Indian financial year label (Apr–Mar) for ``today``.

    e.g. 2026-06-04 → "2026-27"; 2026-02-10 → "2025-26".
    """
    today = today or date.today()
    start_year = today.year if today.month >= 4 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _fetch_quotes(items: list) -> dict:
    """Best-effort batch quotes for any objects with ``.symbol``/``.exchange``
    (holdings or watchlist items), keyed SYMBOL:EXCHANGE.

    Returns an empty dict if the market provider is unavailable so the review
    still runs (lines simply show "price n/a" / no day range).
    """
    pairs = [(it.symbol, it.exchange) for it in items]
    if not pairs:
        return {}
    try:
        from app.market.registry import get_market_provider
        provider = get_market_provider()
        quotes = provider.get_quotes(pairs)
    except Exception:
        return {}
    return {
        f"{q['symbol'].upper()}:{q['exchange'].upper()}": q for q in quotes
    }


def _run_web_search(provider, system: str, user: str) -> str | None:
    """Best-effort native web search. Returns the brief, or ``None`` when the
    feature is disabled, the provider has no web search, or it errors out."""
    settings = ai_registry.settings
    if not getattr(settings, "AI_WEB_SEARCH", False):
        return None
    try:
        return provider.web_search(
            system=system,
            user=user,
            max_uses=getattr(settings, "AI_WEB_SEARCH_MAX_USES", 6),
        )
    except Exception:
        return None


def _maybe_web_research(
    provider,
    holdings: list[Holding],
    watchlist: list[WatchlistItem],
    fy: str,
    is_followup: bool,
) -> str | None:
    """Best-effort live web research brief (sentiment + forward outlook) for the
    portfolio review. Skipped on chat follow-ups and when there are no symbols.
    """
    if is_followup:
        return None

    # Unique symbols across holdings + watchlist, capped to bound the search.
    seen: set[str] = set()
    symbols: list[str] = []
    for s in [h.symbol for h in holdings] + [w.symbol for w in watchlist]:
        u = s.upper()
        if u not in seen:
            seen.add(u)
            symbols.append(u)
    if not symbols:
        return None
    symbols = symbols[:20]

    return _run_web_search(
        provider,
        prompts.portfolio_web_research_system(),
        prompts.portfolio_web_research_user(symbols, fy),
    )


def portfolio_review(
    holdings: list[Holding],
    watchlist: list[WatchlistItem],
    summary: dict,
    target_profit_pct: float,
    messages: list | None = None,
    today: date | None = None,
) -> dict:
    """Review the portfolio + watchlist against an FY profit goal.

    Surfaces the few highest-conviction BUY/SELL moves (not a call for every
    stock) plus overall commentary, with the user's current standing (invested,
    value, P&L, XIRR) injected so the model reasons from where the portfolio
    actually stands. Watchlist symbols are enriched with live quotes when the
    market provider is available.

    ``messages`` is an optional conversation transcript — a list of
    ``{role, content}`` (role ``user``/``assistant``). When supplied, the LAST
    user message is treated as a follow-up question: the model answers it (in
    ``answer``) and re-issues an updated, refined set of recommendations.

    Returns:
        ``{fy, target_profit_pct, answer, portfolio_commentary,
        recommendations: [...]}``
    """
    provider = _require_provider()
    question, conversation = _split_conversation(messages)
    system, user, schema = _build_review_request(
        provider, holdings, watchlist, summary, target_profit_pct,
        question, conversation, today,
    )
    result = provider.complete(system=system, user=user, json_schema=schema)
    return shape_portfolio_review_result(result, target_profit_pct, today)


def _day_range(quotes: dict, symbol: str, exchange: str) -> str:
    """Return ' | day ₹low–₹high' for a symbol if its quote has the range, else ''."""
    q = quotes.get(f"{symbol.upper()}:{exchange.upper()}")
    if q and q.get("day_low") is not None and q.get("day_high") is not None:
        return f" | day ₹{q['day_low']:,.2f}–₹{q['day_high']:,.2f}"
    return ""


def _wl_line(w: WatchlistItem, quotes: dict) -> str:
    """Format one watchlist line for the review prompt (price n/a if no quote)."""
    q = quotes.get(f"{w.symbol.upper()}:{w.exchange.upper()}")
    if q and q.get("last_price") is not None:
        return (
            f"- {w.symbol} ({w.exchange}) | last ₹{q['last_price']:,.2f} | "
            f"{q.get('day_change_pct', 0):+.2f}%"
            f"{_day_range(quotes, w.symbol, w.exchange)}"
        )
    return f"- {w.symbol} ({w.exchange}) | price n/a"


def _build_review_request(
    provider,
    holdings: list[Holding],
    watchlist: list[WatchlistItem],
    summary: dict,
    target_profit_pct: float,
    question: str | None,
    conversation: str | None,
    today: date | None,
) -> tuple[str, str, dict]:
    """Build the ``(system, user, json_schema)`` for a portfolio review.

    Shared by the sync path (which may pass a follow-up ``question``) and the
    batch path (initial review only, ``question is None``).
    """
    fy = current_fy_label(today)

    # One batch quote fetch covers both holdings and watchlist (for the day range).
    quotes = _fetch_quotes(list(holdings) + list(watchlist))

    holdings_block = "\n".join(
        f"- {h.symbol} ({h.exchange}) | qty {h.quantity:g} | avg ₹{h.average_price:,.2f} | "
        f"last ₹{h.last_price:,.2f} | "
        f"{compute_pnl_pct(h.pnl, h.average_price, h.quantity):+.1f}%"
        f"{_day_range(quotes, h.symbol, h.exchange)}"
        for h in holdings
    )

    watchlist_block = "\n".join(_wl_line(w, quotes) for w in watchlist)

    context = {
        "fy": fy,
        "target_profit_pct": target_profit_pct,
        "summary": summary,
        "holdings_block": holdings_block,
        "watchlist_block": watchlist_block,
        "question": question,
        "conversation": conversation,
    }

    # Web research: pull live sentiment + forward outlook so the calls aren't
    # based on past performance alone. Best-effort — runs on the initial review
    # (not every chat follow-up, to bound latency/cost) and degrades to no web
    # context if disabled, unsupported, or it errors.
    context["web_research"] = _maybe_web_research(
        provider, holdings, watchlist, fy, is_followup=question is not None
    )

    return (
        prompts.portfolio_review_system(),
        prompts.portfolio_review_user(context),
        prompts.PORTFOLIO_REVIEW_SCHEMA,
    )


def build_portfolio_review_request(
    provider,
    holdings: list[Holding],
    watchlist: list[WatchlistItem],
    summary: dict,
    target_profit_pct: float,
    today: date | None = None,
) -> tuple[str, str, dict]:
    """Public request builder for the INITIAL (non-follow-up) review — for batch."""
    return _build_review_request(
        provider, holdings, watchlist, summary, target_profit_pct,
        question=None, conversation=None, today=today,
    )


def shape_portfolio_review_result(
    result: dict | str, target_profit_pct: float, today: date | None = None
) -> dict:
    """Normalize a review completion into the API response shape.

    Used by both the sync service and the batch poll endpoint so they return an
    identical ``{fy, target_profit_pct, answer, portfolio_commentary,
    recommendations}`` payload.
    """
    if isinstance(result, str):
        result = {"answer": result, "portfolio_commentary": result, "recommendations": []}
    result.setdefault("answer", "")
    result["fy"] = current_fy_label(today)
    result["target_profit_pct"] = target_profit_pct
    return result  # type: ignore[return-value]


def _msg_field(msg, field: str) -> str:
    """Read a field from a message that may be a pydantic model or a dict."""
    if isinstance(msg, dict):
        return str(msg.get(field, ""))
    return str(getattr(msg, field, ""))


def _split_conversation(messages: list | None) -> tuple[str | None, str | None]:
    """Split a transcript into (latest_user_question, prior_conversation_text).

    Returns ``(None, None)`` when there is no conversation (initial review).
    """
    if not messages:
        return None, None
    last = messages[-1]
    question = _msg_field(last, "content") if _msg_field(last, "role") == "user" else None
    prior = messages[:-1] if question is not None else messages
    conversation = (
        "\n".join(f"[{_msg_field(m, 'role')}]: {_msg_field(m, 'content')}" for m in prior)
        or None
    )
    return question, conversation
