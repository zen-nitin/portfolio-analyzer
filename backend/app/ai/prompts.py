"""
AI prompt templates for portfolio insights.

Centralises all prompts so they can be tuned without touching service logic.
"""


def watchlist_suggestions_system() -> str:
    return (
        "You are an expert Indian stock market analyst with deep knowledge of NSE/BSE equities, "
        "sectoral dynamics, and portfolio construction. "
        "You provide thoughtful, research-backed suggestions for stocks to watch. "
        "Always consider diversification, risk, and the user's existing portfolio context. "
        "Be concise but actionable."
    )


def watchlist_suggestions_user(count: int, portfolio_context: dict) -> str:
    return (
        f"Based on the following portfolio context, suggest {count} stocks worth watching. "
        f"Avoid stocks already in the portfolio. Focus on quality, growth potential, and diversification.\n\n"
        f"Current portfolio:\n"
        f"- Total invested: ₹{portfolio_context.get('total_invested', 0):,.0f}\n"
        f"- Current value: ₹{portfolio_context.get('current_value', 0):,.0f}\n"
        f"- P&L: ₹{portfolio_context.get('pnl', 0):,.0f} ({portfolio_context.get('pnl_pct', 0):.1f}%)\n"
        f"- Holdings: {', '.join(portfolio_context.get('symbols', [])) or 'None'}\n\n"
        f"Return a JSON array of {count} objects with fields: symbol (NSE ticker), exchange, rationale (2-3 sentences)."
    )


def recommendation_system() -> str:
    return (
        "You are a senior Indian equity analyst. You provide BUY/SELL/HOLD recommendations "
        "based on fundamental and technical factors, with clear rationale. "
        "Always contextualise against the user's current portfolio. "
        "Be direct and data-aware. Never give generic disclaimers as the main response."
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
                    "rationale": {"type": "string"},
                },
                "required": ["symbol", "exchange", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
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
