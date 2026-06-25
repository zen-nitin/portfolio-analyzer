"""
Prompt templates for the AI portfolio features.

The backend does NOT call any AI model and does NOT fetch market data for these
features. It assembles a self-contained prompt (these templates + the user's
portfolio context, which only the app knows: holdings, cost basis, P&L,
watchlist, free cash, XIRR) that the user pastes into Claude/ChatGPT. That model
is expected to spin up its OWN subagents, fetch live data from Yahoo Finance,
research the latest news/fundamentals for every stock, and return JSON matching
the schema below — which the user pastes back into the app.
"""

_MAX_CALLS = 5


def _agentic_research_instructions() -> str:
    """Shared 'do the research yourself — subagents + Yahoo Finance' block.

    The app pre-fetches nothing market-related, so every prompt tells the model
    to gather live data and news itself, in parallel, before deciding.
    """
    return (
        "HOW TO WORK — nothing is pre-fetched for you; gather EVERYTHING live:\n"
        "• Spin up MULTIPLE SUBAGENTS that work IN PARALLEL — at least one per "
        "stock under consideration (every current holding, every watchlist name, "
        "and every fresh idea you evaluate). Invoke as many subagents as you need; "
        "there is no limit.\n"
        "• Each subagent must pull LIVE data from Yahoo Finance for its stock — "
        "current price, P/E, P/B, EPS, market cap, 52-week range, beta, dividend "
        "yield, sector/industry and the most recent results — AND research the "
        "latest DATED news & catalysts (results, orders, capex, M&A, "
        "management/regulatory actions, broker moves) plus the fundamentals from "
        "the latest ANNUAL REPORT / quarterly results (revenue & PAT growth, "
        "margins, debt, ROE/ROCE, guidance, key risks).\n"
        "• Base EVERY call STRICTLY on this freshly-fetched, current information — "
        "never on stale or training-cutoff knowledge. Cite the concrete, dated "
        "evidence (figures + news) behind each call.\n"
    )


# ------------------------------------------------------------------
# Watchlist suggestions
# ------------------------------------------------------------------

def watchlist_suggestions_system() -> str:
    return (
        "You are a growth-focused Indian (NSE/BSE) equity analyst with full web "
        "access and the ability to run many subagents in parallel. You build an "
        "ACTIONABLE WATCHLIST BENCH for an aggressive, growth-tilted investor "
        "(FY profit goal ~75%).\n\n"
        + _agentic_research_instructions()
        + "\nTO FIND IDEAS, fetch these yourself (Yahoo Finance / the web) and then "
        "investigate the promising names with subagents: the latest top gainers & "
        "losers, sector leaders, high revenue/EPS-growth companies, and the peers "
        "/ competitors of the user's current holdings and watchlist.\n\n"
        "THE BENCH — every idea must serve ONE of three roles (you choose the mix "
        "based on the portfolio and the market):\n"
        "1. CORE_GROWTH — a durable, high-quality long-term compounder to hold.\n"
        "2. TACTICAL — attractive only for a WINDOW due to a SPECIFIC, dated "
        "company development. Give the concrete catalyst, a validity window "
        "(horizon), and an explicit exit_trigger (when the thesis is spent). Not "
        "generic momentum.\n"
        "3. SWAP_CANDIDATE — a name to rotate INTO when one of the user's current "
        "holdings becomes too risky and must be exited; set 'replaces' to that "
        "held symbol and explain why it is a better risk/reward (cheaper, less "
        "concentrated, lower beta, stronger growth).\n\n"
        "Avoid names the user already HOLDS or WATCHES. Favour growth. Every "
        "rationale must cite the concrete, recent signal + the fundamentals behind "
        "it (not just price action). Also return flagged_holdings: current "
        "positions you judge risky (using their latest live data + news), each "
        "with a one-line reason. Be concise and actionable."
    )


def watchlist_suggestions_user(count: int, context: dict) -> str:
    held = ", ".join(context.get("symbols", [])) or "None"
    watching = ", ".join(context.get("watchlist_symbols", [])) or "None"
    return (
        f"Build a {count}-name watchlist bench (you choose the CORE_GROWTH / "
        f"TACTICAL / SWAP_CANDIDATE mix). Growth tilt; aggressive FY goal ~75%. "
        f"Avoid names already held or watched.\n\n"
        f"PORTFOLIO STANDING (the user's own figures):\n"
        f"- Total invested: ₹{context.get('total_invested', 0):,.0f}\n"
        f"- Current value: ₹{context.get('current_value', 0):,.0f}\n"
        f"- P&L: ₹{context.get('pnl', 0):,.0f} ({context.get('pnl_pct', 0):.1f}%)\n\n"
        f"CURRENT HOLDINGS (symbol | exchange | qty | avg cost | last-known price | "
        f"P&L% — the cost basis and quantity are the user's; FETCH the current "
        f"price, valuation and fundamentals yourself):\n"
        f"{context.get('holdings_block', 'None.')}\n\n"
        f"ALREADY WATCHING (do not repeat): {watching}\n"
        f"ALREADY HOLDING (do not suggest): {held}\n\n"
        f"Research each current holding (live data + latest news) to flag the risky "
        f"ones and to source SWAP_CANDIDATEs, then scout and investigate fresh "
        f"ideas with subagents. Return {count} suggestions per the schema. For "
        f"each: symbol (NSE ticker), exchange, bucket, a 2-3 sentence rationale "
        f"naming the concrete signal + forward catalyst, risk, and horizon. For "
        f"TACTICAL set catalyst + exit_trigger; for SWAP_CANDIDATE set 'replaces' "
        f"to the held symbol it would replace. Also return flagged_holdings (risky "
        f"current positions with reasons)."
    )


# ------------------------------------------------------------------
# Portfolio review
# ------------------------------------------------------------------

def portfolio_review_system() -> str:
    return (
        "You are a senior Indian portfolio strategist reviewing an NSE/BSE equity "
        "portfolio, with full web access and the ability to run many subagents in "
        "parallel. This is decision-support for the user's own judgement — "
        "informative, not personalised investment advice.\n\n"
        + _agentic_research_instructions()
        + "\nSurface ONLY the few highest-conviction, ACTIONABLE moves (BUY or "
        "SELL) — never a wall of 'hold everything' noise. Weigh cost basis, "
        "unrealised P&L, concentration, valuation and risk. It is valid and "
        "PREFERRED to return ZERO recommendations on a poor day (a sharp broad "
        "move, names extended above good entries, nothing near a sensible exit) "
        "rather than force a trade; explain the wait in portfolio_commentary.\n\n"
        "REAL CAPITAL IS DEPLOYED ON YOUR CALLS, so groundedness beats boldness. "
        "Ground every call in the LIVE data + latest dated news your subagents "
        "fetched. Build the bear case before any BUY and the bull case before any "
        "SELL; if the evidence is thin, stale or conflicting, ABSTAIN. Each "
        "rationale must cite concrete, current evidence — results / annual-report "
        "figures (revenue & PAT growth, margins, debt, ROE) AND the relevant "
        "latest news. A cheap-looking laggard with deteriorating fundamentals is "
        "not a buy; a strong performer with improving prospects may still be one. "
        "Set 'conviction' to reflect the verified evidence, not enthusiasm.\n\n"
        "Use each name's recent price action / intraday range (which you fetch) "
        "for timing — note when a name is near support (better entry) or extended "
        "(consider waiting). SIZE every BUY to the FREE CASH available: do not "
        "recommend deploying more than the user has, and if cash is tight or "
        "untracked, say so and prioritise the highest-conviction buys (or fund "
        "them via a SELL). For each BUY give an 'entry_hint' (a concrete entry "
        "price or zone; null for SELLs); for each SELL give an 'exit_hint' (a "
        "concrete exit/target price, zone or trigger; null for BUYs). "
        "Treat the user's FY return target as their stated AMBITION and CONTEXT — "
        "NOT a promise these trades will achieve it. If it is unrealistic for a "
        "diversified equity book, say so plainly in portfolio_commentary, then "
        "still give the best risk-aware moves on their own merits."
    )


def portfolio_review_user(context: dict) -> str:
    s = context.get("summary", {})
    xirr = s.get("xirr")
    xirr_str = f"{xirr * 100:.1f}%" if xirr is not None else "N/A"
    target = context.get("target_profit_pct")

    free_cash = s.get("free_cash")
    free_cash_str = (
        f"₹{free_cash:,.0f}" if free_cash is not None
        else "not tracked (no funds ledger imported)"
    )

    return (
        f"Financial year: {context.get('fy')} (Indian FY, Apr–Mar).\n"
        f"USER'S AMBITION (context only — NOT a promise; flag it if unrealistic): "
        f"grow the portfolio ~{target:g}% this FY.\n\n"
        f"Current standing (the user's own figures):\n"
        f"- Total invested (cost basis): ₹{s.get('total_invested', 0):,.0f}\n"
        f"- Current value: ₹{s.get('current_value', 0):,.0f}\n"
        f"- Unrealised P&L: ₹{s.get('pnl', 0):,.0f} ({s.get('pnl_pct', 0):.1f}%)\n"
        f"- Trade XIRR so far: {xirr_str}\n"
        f"- FREE CASH to deploy: {free_cash_str}  (size BUY moves to this)\n\n"
        f"HOLDINGS (symbol | exchange | qty | avg cost | last-known price | P&L% — "
        f"the cost basis and quantity are the user's; FETCH the current price, "
        f"intraday range, valuation and news yourself):\n"
        f"{context.get('holdings_block') or 'None'}\n\n"
        f"WATCHLIST (symbol | exchange — FETCH current price/levels and research "
        f"each yourself):\n"
        f"{context.get('watchlist_block') or 'None'}\n\n"
        f"Investigate every holding and watchlist name with subagents (live data + "
        f"latest news), then return ONLY the {_MAX_CALLS} or fewer highest-"
        f"conviction ACTIONABLE moves (BUY or SELL) that most improve this "
        f"portfolio's risk/reward on their own merits — NOT framed as a route to "
        f"the {target:g}% number. Do NOT list HOLD/no-change positions. If nothing "
        f"clears the bar today, return an EMPTY recommendations list and explain "
        f"the wait in portfolio_commentary. Set 'answer' to a single-sentence "
        f"headline of your overall stance, and use portfolio_commentary (2-3 "
        f"sentences) for a candid read on whether the ~{target:g}% ambition is "
        f"realistic and the biggest portfolio risk (e.g. concentration).\n\n"
        "Return JSON: answer (string), portfolio_commentary (string), "
        "recommendations (array of {symbol, exchange, position (HELD|WATCHLIST), "
        "action (BUY|SELL), conviction (0.0-1.0), rationale (1-2 sentences citing "
        "the fetched evidence), entry_hint (BUY: an entry price/zone; null for "
        "SELL), exit_hint (SELL: an exit/target price, zone or trigger; null for "
        "BUY)}). Only BUY/SELL items belong in recommendations."
    )


# ------------------------------------------------------------------
# JSON schemas (the shape the pasted-back JSON must match)
# ------------------------------------------------------------------

WATCHLIST_SUGGESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "exchange": {"type": "string"},
                    "bucket": {
                        "type": "string",
                        "enum": ["CORE_GROWTH", "TACTICAL", "SWAP_CANDIDATE"],
                        "description": (
                            "CORE_GROWTH = durable long-term growth compounder to hold; "
                            "TACTICAL = good only for a window due to a specific development; "
                            "SWAP_CANDIDATE = rotate into this when a risky holding must be exited."
                        ),
                    },
                    "rationale": {"type": "string"},
                    "risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                    "horizon": {
                        "type": "string",
                        "description": "e.g. 'long-term (3+ yrs)', 'next 1-2 quarters', 'until Q2 results'.",
                    },
                    "catalyst": {
                        "type": ["string", "null"],
                        "description": "TACTICAL only: the specific development driving the thesis (else null).",
                    },
                    "exit_trigger": {
                        "type": ["string", "null"],
                        "description": "TACTICAL only: when the thesis is spent / when to exit (else null).",
                    },
                    "replaces": {
                        "type": ["string", "null"],
                        "description": "SWAP_CANDIDATE only: the held symbol this could replace (else null).",
                    },
                },
                "required": [
                    "symbol", "exchange", "bucket", "rationale", "risk",
                    "horizon", "catalyst", "exit_trigger", "replaces",
                ],
                "additionalProperties": False,
            },
        },
        "flagged_holdings": {
            "type": "array",
            "description": "Current holdings judged risky (concentration, run-up, valuation, momentum).",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["symbol", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["suggestions", "flagged_holdings"],
    "additionalProperties": False,
}

PORTFOLIO_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "portfolio_commentary": {"type": "string"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "exchange": {"type": "string"},
                    "position": {"type": "string", "enum": ["HELD", "WATCHLIST"]},
                    "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                    "conviction": {"type": "number"},
                    "rationale": {"type": "string"},
                    "entry_hint": {
                        "type": ["string", "null"],
                        "description": (
                            "For BUY: a suggested entry price or zone (e.g. '₹1,180–1,210, near "
                            "today's low') grounded in the day range / cost basis. Null for SELL."
                        ),
                    },
                    "exit_hint": {
                        "type": ["string", "null"],
                        "description": (
                            "For SELL: a suggested exit price/zone or trigger (e.g. 'trim above "
                            "₹1,650, stop below ₹1,540') grounded in the day range / cost basis. "
                            "Null for BUY."
                        ),
                    },
                },
                "required": [
                    "symbol", "exchange", "position", "action", "conviction", "rationale",
                    "entry_hint", "exit_hint",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "portfolio_commentary", "recommendations"],
    "additionalProperties": False,
}
