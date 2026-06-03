"""
Live price refresh service.

Fetches current market quotes for an account's holdings via the configured
MarketDataProvider and updates ``last_price``, ``day_change``, and ``pnl``
on each Holding row.

Partial updates are acceptable: if a particular symbol fails to fetch a price
it is silently skipped so the rest of the holdings can still be updated.
If the provider itself is unavailable (RuntimeError from the registry) the
whole refresh is aborted and the error is propagated to the caller.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.market.registry import get_market_provider
from app.models.holding import Holding


def refresh_prices(db: Session, account_id: int) -> int:
    """Update live prices for all holdings in an account.

    Args:
        db:         Active SQLAlchemy session.
        account_id: Account whose holdings to refresh.

    Returns:
        Number of holdings successfully updated.

    Raises:
        RuntimeError: If the market data provider is not available.
    """
    holdings = (
        db.query(Holding)
        .filter(Holding.account_id == account_id)
        .all()
    )

    if not holdings:
        return 0

    # Let RuntimeError propagate so the router can return HTTP 503
    provider = get_market_provider()

    # Build list of (symbol, exchange) pairs
    pairs = [(h.symbol, h.exchange) for h in holdings]

    # Batch fetch – provider silently skips per-symbol failures
    quotes = provider.get_quotes(pairs)

    # Build lookup keyed by (symbol, exchange)
    quote_map: dict[tuple[str, str], dict] = {}
    for q in quotes:
        key = (q["symbol"].upper(), q["exchange"].upper())
        quote_map[key] = q

    updated = 0
    now = datetime.utcnow()

    for holding in holdings:
        key = (holding.symbol.upper(), (holding.exchange or "NSE").upper())
        quote = quote_map.get(key)
        if quote is None:
            continue

        last_price = quote.get("last_price")
        if last_price is None:
            continue

        holding.last_price = float(last_price)
        holding.day_change = float(quote.get("day_change") or 0.0)
        holding.pnl = round(
            (holding.last_price - holding.average_price) * holding.quantity, 4
        )
        holding.updated_at = now
        updated += 1

    if updated:
        db.commit()

    return updated
