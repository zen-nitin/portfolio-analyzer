"""
AI prompt templates for portfolio insights.

Centralises all prompts so they can be tuned without touching service logic.
"""


def watchlist_suggestions_system() -> str:
    return (
        "You are a growth-focused Indian (NSE/BSE) equity analyst. You build an ACTIONABLE "
        "WATCHLIST BENCH for an aggressive investor (FY profit goal ~75%), tilted toward GROWTH. "
        "The bench is not a list of random good stocks — every idea must serve one of three roles "
        "(you decide the mix based on the portfolio and the market):\n"
        "1. CORE_GROWTH — high-quality companies to hold for long-term growth (durable demand, "
        "strong execution, scalable). Horizon long-term.\n"
        "2. TACTICAL — attractive only for a WINDOW due to a SPECIFIC company development. You "
        "MUST give the concrete catalyst, a validity window (horizon), and an explicit "
        "exit_trigger (when the thesis is spent). Not generic momentum.\n"
        "3. SWAP_CANDIDATE — a name to rotate INTO when one of the user's CURRENT holdings becomes "
        "too risky and must be exited. Set 'replaces' to the specific held symbol it would replace "
        "and explain why it's a better risk/reward (e.g. less concentrated, cheaper, lower beta, "
        "stronger growth). Use the per-holding RISK flags provided.\n\n"
        "Rules: avoid names the user already HOLDS or already has on their WATCHLIST. Do not rely "
        "on training-cutoff knowledge — synthesise across ALL the structured idea pools provided, "
        "not just one:\n"
        "• TOP GAINERS/LOSERS — momentum and turnaround candidates.\n"
        "• SECTOR LEADERS — the biggest names across industries; use for quality core ideas and to "
        "diversify away from the user's overweight sectors.\n"
        "• HIGH-GROWTH COMPANIES — fast revenue/EPS growers across industries; prime CORE_GROWTH "
        "hunting ground given the growth tilt.\n"
        "• COMPETITIVE SET — peers of the user's holdings/watchlist, grouped by industry. Run "
        "COMPETITIVE ANALYSIS: compare each holding/watchlist name to its peers; if a peer is a "
        "stronger growth/quality/risk proposition, surface it (as CORE_GROWTH, or as a "
        "SWAP_CANDIDATE that 'replaces' the weaker held name).\n"
        "• DEEP RESEARCH — recent news/catalysts AND annual-report/results fundamentals (growth, "
        "margins, debt, ROE, guidance, key risks) for the names in focus.\n"
        "GROUND every pick in deep research: use the DEEP RESEARCH section if provided; if it is "
        "NOT provided, research each name you suggest yourself first (browse for recent results, "
        "annual-report figures and news). Each rationale must cite the concrete signal + the "
        "fundamentals/results that back it (not just price action); don't suggest a name you "
        "haven't researched. Favour growth. Also return flagged_holdings: the current positions you "
        "judge risky, each with a one-line reason. Be concise and actionable."
    )


def watchlist_research_system() -> str:
    return (
        "You are an Indian (NSE/BSE) equity analyst with live web access, scouting and DEEP-"
        "researching new stock ideas. For each name you surface, go beyond the headline: pull the "
        "concrete catalyst AND verify the fundamentals from the latest ANNUAL REPORT / quarterly "
        "results — revenue & PAT growth, margins, debt, cash flow, ROE/ROCE, plus management's "
        "guidance and the key risks the report flags. Use results coverage, investor "
        "presentations, earnings calls, filings and annual-report highlights. Focus on CURRENT "
        "sentiment and the FORWARD outlook. (Top gainers/losers are supplied separately and "
        "structured, so you need not list them.) Be factual, name specific tickers, attribute "
        "sources, and date findings (e.g. 'as of <date>')."
    )


def watchlist_research_user(held_symbols: list[str], count: int) -> str:
    held = ", ".join(held_symbols) if held_symbols else "none"
    return (
        f"Scout and deep-research fresh stock ideas for an aggressive, growth-tilted watchlist "
        f"(about {count}). Surface NSE/BSE names currently IN FOCUS for a concrete development — "
        "results beats, order wins, capex/expansion, demergers, upgrades, or strong sector setups. "
        "For each, give: the catalyst (dated); FUNDAMENTALS from the latest annual report / results "
        "(revenue & PAT growth, margins, debt, ROE/ROCE); the annual-report guidance + key risk; "
        "and whether it's a durable long-term growth story or a shorter, event-driven (time-bound) "
        f"play. The user ALREADY HOLDS: {held} — the goal is FRESH ideas beyond these. Keep the "
        "brief under ~900 words; one tight block per ticker."
    )


def watchlist_suggestions_user(count: int, portfolio_context: dict) -> str:
    held = ", ".join(portfolio_context.get("symbols", [])) or "None"
    watching = ", ".join(portfolio_context.get("watchlist_symbols", [])) or "None"

    base = (
        f"Build a {count}-name watchlist bench (you choose the CORE_GROWTH / TACTICAL / "
        f"SWAP_CANDIDATE mix). Growth tilt; aggressive FY goal ~75%. Avoid names already held or "
        f"watched.\n\n"
        f"PORTFOLIO STANDING:\n"
        f"- Total invested: ₹{portfolio_context.get('total_invested', 0):,.0f}\n"
        f"- Current value: ₹{portfolio_context.get('current_value', 0):,.0f}\n"
        f"- P&L: ₹{portfolio_context.get('pnl', 0):,.0f} ({portfolio_context.get('pnl_pct', 0):.1f}%)\n\n"
        f"CURRENT HOLDINGS (weight, P&L, sector, risk flags — use to flag risky names & source SWAP_CANDIDATEs):\n"
        f"{portfolio_context.get('holdings_risk_block', 'None.')}\n\n"
        f"SECTOR EXPOSURE (diversify away from overweights):\n"
        f"{portfolio_context.get('sector_block', 'Unavailable.')}\n\n"
        f"ALREADY WATCHING (do not repeat): {watching}\n"
        f"ALREADY HOLDING (do not suggest): {held}\n\n"
        f"TOP MOVERS — latest session (structured; a hunting ground for ideas):\n"
        f"{portfolio_context.get('movers_block', '(none available)')}\n\n"
        f"SECTOR LEADERS (top by size across industries; quality core ideas & diversification):\n"
        f"{portfolio_context.get('sector_leaders_block', '  (none available)')}\n\n"
        f"HIGH-GROWTH COMPANIES (fast revenue/EPS growers across industries):\n"
        f"{portfolio_context.get('growth_leaders_block', '  (none available)')}\n\n"
        f"COMPETITIVE SET (peers of your holdings/watchlist by industry — run competitive analysis):\n"
        f"{portfolio_context.get('peers_block', '  (none available)')}\n\n"
    )

    web_research = portfolio_context.get("web_research")
    if web_research:
        base += (
            "DEEP RESEARCH (recent news + annual-report/results fundamentals, guidance & risks):\n"
            f"{web_research}\n\n"
        )

    base += (
        f"Return {count} suggestions per the schema. For each: symbol (NSE ticker), exchange, "
        "bucket, a 2-3 sentence rationale naming the concrete signal + forward catalyst, risk, and "
        "horizon. For TACTICAL set catalyst + exit_trigger; for SWAP_CANDIDATE set 'replaces' to "
        "the held symbol it would replace. Also return flagged_holdings (risky current positions "
        "with reasons)."
    )
    return base


def recommendation_system() -> str:
    return (
        "You are a senior Indian equity analyst. You provide BUY/SELL/HOLD recommendations "
        "based on fundamental and technical factors, with clear rationale. "
        "Always contextualise against the user's current portfolio. "
        "Be direct and data-aware. Never give generic disclaimers as the main response. "
        "You are NOT obliged to recommend a trade: if today is a poor day to act on this name "
        "— e.g. it is extended above a sensible entry, there is no clean level to buy or sell "
        "into, or the setup is simply unattractive right now — return HOLD and say plainly that "
        "waiting is the call (and, where useful, what level or trigger would change it). A "
        "forced BUY or SELL on a bad day is worse than no action."
    )


def recommendation_user(symbol: str, context: dict) -> str:
    market_stats = context.get("market_stats", "Market data unavailable.")
    return (
        f"Provide a BUY/SELL/HOLD recommendation for {symbol} ({context.get('exchange', 'NSE')}).\n\n"
        f"Live market data: {market_stats}\n\n"
        f"Portfolio context:\n"
        f"- User already holds: {', '.join(context.get('symbols', [])) or 'Nothing yet'}\n"
        f"- Portfolio P&L: {context.get('pnl_pct', 0):.1f}%\n"
        f"- Holding detail for {symbol}: {context.get('holding_detail', 'Not currently held')}\n\n"
        f"Return JSON with fields: action (BUY|SELL|HOLD), confidence (0.0-1.0), rationale (3-5 sentences), "
        f"key_risks (list of strings), time_horizon (short/medium/long)."
    )


def portfolio_review_system() -> str:
    return (
        "You are a senior Indian portfolio strategist reviewing an NSE/BSE equity portfolio. This "
        "is decision-support analysis for the user's own judgement — informative, not personalised "
        "investment advice. Surface ONLY the few highest-conviction, ACTIONABLE moves (BUY or SELL) "
        "— never a wall of 'hold everything' noise. Weigh cost basis, unrealised P&L, "
        "concentration, valuation and risk. "
        "You are NOT required to produce moves: if today is simply a poor day to transact — a sharp "
        "broad-market move, names extended well above good entries, nothing near a sensible exit — "
        "it is valid and PREFERRED to return ZERO recommendations rather than force a trade. When "
        "you do, say so candidly in portfolio_commentary/answer (what's holding you back, and what "
        "level or trigger would make you act). Quality over quantity: an empty list on a bad day is "
        "a legitimate answer. "
        "Do NOT reason from past price performance alone — every call must be grounded in DEEP "
        "RESEARCH (recent news + annual-report / latest-results fundamentals, management guidance "
        "and key risks). If a DEEP RESEARCH section is provided below, ground your calls in it; if "
        "it is NOT provided, research each name yourself first (browse for recent results, "
        "annual-report figures and news) before recommending it. Either way, each rationale must "
        "cite the concrete evidence — results / annual-report figures (e.g. revenue & PAT growth, "
        "margins, debt, ROE) AND the relevant recent news. Do not recommend a name you haven't "
        "researched: a cheap-looking laggard with deteriorating fundamentals is not a buy, and a "
        "strong performer with improving prospects may still be one. "
        "Be direct and specific — cite the numbers AND the forward-looking findings. "
        "Use today's DAY HIGH/LOW (shown per name) for timing — note when a name is near its "
        "day's low (better entry) or high (consider waiting). SIZE every BUY to the FREE CASH "
        "available: do not recommend deploying more than the user has, and if cash is tight or "
        "untracked, say so and prioritise the highest-conviction buys (or fund them via a SELL). "
        "For each BUY, give an 'entry_hint' — a concrete entry price or zone (null for SELLs). "
        "For each SELL, give an 'exit_hint' — a concrete exit/target price, zone, or trigger to "
        "sell into (e.g. 'trim above ₹X, stop below ₹Y'), grounded in the day range and cost "
        "basis (null for BUYs). "
        "When the user pushes back or asks a question, answer it honestly and revise your calls to "
        "reflect their reasoning and constraints. "
        "Treat the user's FY return target as their stated AMBITION and CONTEXT — NOT a promise "
        "these trades will achieve it, and never frame any move as 'the path to' that number. If "
        "the target is unrealistic for a diversified equity book, say so plainly in "
        "portfolio_commentary, then still give the best risk-aware moves on their own merits. Your "
        "job is the highest-conviction moves that improve the portfolio, not to manufacture a route "
        "to a specific return."
    )


def portfolio_web_research_system() -> str:
    return (
        "You are a diligent fundamental equity research analyst with live web access, covering "
        "Indian (NSE/BSE) stocks. Do DEEP research — go beyond headlines. For each stock, dig into "
        "BOTH (1) the latest NEWS/catalysts and (2) the company's FUNDAMENTALS from its most recent "
        "ANNUAL REPORT and quarterly results. Read results coverage, investor presentations, "
        "earnings-call summaries, exchange filings and annual-report highlights — not just price "
        "commentary. Be factual, cite/attribute sources, and date findings (e.g. 'as of <month>'). "
        "If something material can't be verified, say so rather than guessing."
    )


def portfolio_web_research_user(symbols: list[str], fy: str) -> str:
    names = ", ".join(symbols) if symbols else "the user's portfolio"
    return (
        f"It is Indian financial year {fy}. Do deep fundamental + news research on these stocks "
        f"(prioritise the names with the most material recent developments): {names}.\n\n"
        "For each notable name, give a tight block covering:\n"
        "• NEWS / CATALYSTS — the most recent results, order wins, management/regulatory moves "
        "(dated).\n"
        "• FUNDAMENTALS (from the latest annual report & quarterly results) — revenue & PAT "
        "growth, operating/net margins, debt/leverage, cash flow, and ROE/ROCE where available.\n"
        "• ANNUAL-REPORT TAKE — management's stated guidance / strategy and the KEY RISKS the "
        "report flags.\n"
        "• VALUATION & STANCE — rough valuation vs peers and the analyst direction "
        "(bullish / neutral / bearish).\n"
        "End with one line on the overall market/sector mood relevant to this portfolio. Prioritise "
        "depth on the most material names; keep the whole brief under ~1000 words."
    )


_MAX_CALLS = 5


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

    base = (
        f"Financial year: {context.get('fy')} (Indian FY, Apr–Mar).\n"
        f"USER'S AMBITION (context only — NOT a promise; flag it if unrealistic): grow the "
        f"portfolio ~{target}% this FY.\n\n"
        f"Current standing:\n"
        f"- Total invested (cost basis): ₹{s.get('total_invested', 0):,.0f}\n"
        f"- Current value: ₹{s.get('current_value', 0):,.0f}\n"
        f"- Unrealised P&L: ₹{s.get('pnl', 0):,.0f} ({s.get('pnl_pct', 0):.1f}%)\n"
        f"- Trade XIRR so far: {xirr_str}\n"
        f"- Today's change: ₹{s.get('day_change', 0):,.0f}\n"
        f"- FREE CASH to deploy: {free_cash_str}  (size BUY moves to this)\n\n"
        f"HOLDINGS (symbol | qty | avg cost | last price | unrealised P&L% | today's day range):\n"
        f"{context.get('holdings_block') or 'None'}\n\n"
        f"WATCHLIST (symbol | last price | day change% | today's day range):\n"
        f"{context.get('watchlist_block') or 'None'}\n\n"
    )

    web_research = context.get("web_research")
    if web_research:
        base += (
            "DEEP RESEARCH (recent news + annual-report/results fundamentals, guidance & risks — "
            "ground every call in this and cite the figures):\n"
            f"{web_research}\n\n"
        )

    question = context.get("question")
    conversation = context.get("conversation")

    if question:
        convo_prefix = ""
        if conversation:
            convo_prefix = "Conversation so far:\n" + conversation + "\n\n"
        instruction = (
            convo_prefix
            + f'The user now asks: "{question}"\n\n'
            + "In 'answer' (2-4 sentences) respond to them directly and specifically, citing the "
            "numbers. Then RE-ISSUE the recommendation list, updated to reflect this discussion and "
            "the user's stated preferences/constraints. Keep ONLY the few highest-conviction "
            f"ACTIONABLE moves (BUY or SELL), at most {_MAX_CALLS}. Never include HOLD/no-change "
            "items — and if nothing is worth acting on today, return an EMPTY recommendations list "
            "and say why in 'answer'. Update portfolio_commentary if your overall stance changed.\n\n"
        )
    else:
        instruction = (
            f"Return ONLY the {_MAX_CALLS} or fewer highest-conviction ACTIONABLE moves (BUY or "
            "SELL) that most improve this portfolio's risk/reward on their own merits — NOT framed "
            f"as a route to the {target}% number. Do NOT list HOLD/no-change positions; skip "
            "anything where the call is to do nothing. If today is a poor day to transact and "
            "nothing clears the bar, returning an EMPTY recommendations list is valid and preferred "
            "over forcing a trade — explain the wait in portfolio_commentary. Set 'answer' to a "
            "single-sentence headline "
            "of your overall stance, and use portfolio_commentary (2-3 sentences) to give a candid "
            f"read on whether the ~{target}% ambition is realistic and to call out the biggest "
            "portfolio risk (e.g. concentration).\n\n"
        )

    schema_line = (
        "Return JSON: answer (string), portfolio_commentary (string), recommendations (array of "
        "{symbol, exchange, position (HELD|WATCHLIST), action (BUY|SELL|HOLD), conviction "
        "(0.0-1.0), rationale (1-2 sentences), entry_hint (BUY: an entry price/zone; null for "
        "SELL), exit_hint (SELL: an exit/target price, zone or trigger; null for BUY) — both "
        "grounded in the day range & cost basis}). Only BUY/SELL items belong in recommendations."
    )

    return base + instruction + schema_line


def analysis_system() -> str:
    return (
        "You are a comprehensive Indian equity research analyst. "
        "You produce structured stock analysis covering business fundamentals, technicals, "
        "valuation, risks, and catalysts. "
        "Tailor insights to an Indian retail investor context (NSE/BSE). "
        "Be specific, factual, and avoid vague platitudes."
    )


def analysis_user(symbol: str, context: dict) -> str:
    market_stats = context.get("market_stats", "Market data unavailable.")
    return (
        f"Provide a comprehensive analysis of {symbol} ({context.get('exchange', 'NSE')}).\n\n"
        f"Live market data: {market_stats}\n\n"
        f"User context:\n"
        f"- Currently held: {'Yes, ' + str(context.get('holding_detail', '')) if context.get('holding_detail') else 'No'}\n"
        f"- Portfolio P&L: {context.get('pnl_pct', 0):.1f}%\n\n"
        f"Return JSON with fields: symbol, exchange, summary (2-3 sentences), "
        f"strengths (list), weaknesses (list), opportunities (list), threats (list), "
        f"valuation_view (undervalued/fairly_valued/overvalued), "
        f"sentiment (bullish/neutral/bearish), catalysts (list of upcoming events/triggers)."
    )


# JSON schemas for structured output

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

RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "time_horizon": {"type": "string"},
    },
    "required": ["action", "confidence", "rationale", "key_risks", "time_horizon"],
    "additionalProperties": False,
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "exchange": {"type": "string"},
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": {"type": "string"}},
        "threats": {"type": "array", "items": {"type": "string"}},
        "valuation_view": {"type": "string"},
        "sentiment": {"type": "string"},
        "catalysts": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "symbol", "exchange", "summary", "strengths", "weaknesses",
        "opportunities", "threats", "valuation_view", "sentiment", "catalysts",
    ],
    "additionalProperties": False,
}
