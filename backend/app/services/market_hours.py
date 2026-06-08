"""
Indian equity market trading hours (NSE / BSE).

Used to gate the dashboard's automatic background price poll so it does not
hammer the market-data provider when the market is closed and prices cannot
change. The regular trading session is **Mon–Fri, 09:15–15:30 IST**.

Note: this is a weekday + time-window check only. It does NOT account for
exchange trading holidays (there is no holiday calendar in the app), so the
window may report "open" on a holiday weekday — acceptable for the purpose of
throttling a best-effort price poll.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# NSE/BSE normal trading session.
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def is_market_open(now: datetime | None = None) -> bool:
    """Return True if the Indian equity market is in its regular session.

    Args:
        now: Instant to test. If naive it is assumed to be IST; if timezone-aware
            it is converted to IST. Defaults to the current time.
    """
    if now is None:
        now = datetime.now(IST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)

    # Monday=0 … Sunday=6; markets are closed on weekends.
    if now.weekday() >= 5:
        return False

    return MARKET_OPEN <= now.time() <= MARKET_CLOSE
