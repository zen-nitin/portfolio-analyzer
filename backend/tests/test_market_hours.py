"""Tests for the NSE/BSE trading-hours gate (app.services.market_hours)."""
from datetime import datetime

from zoneinfo import ZoneInfo

from app.services.market_hours import IST, is_market_open

# 2026-06-05 is a Friday; 2026-06-06/07 are the weekend.


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


class TestIsMarketOpen:
    def test_open_midsession_weekday(self):
        assert is_market_open(_ist(2026, 6, 5, 12, 0)) is True

    def test_open_at_exact_bounds(self):
        assert is_market_open(_ist(2026, 6, 5, 9, 15)) is True
        assert is_market_open(_ist(2026, 6, 5, 15, 30)) is True

    def test_closed_before_open(self):
        assert is_market_open(_ist(2026, 6, 5, 9, 14)) is False

    def test_closed_after_close(self):
        assert is_market_open(_ist(2026, 6, 5, 15, 31)) is False

    def test_closed_on_weekend(self):
        # Saturday and Sunday, even mid-session-time.
        assert is_market_open(_ist(2026, 6, 6, 12, 0)) is False
        assert is_market_open(_ist(2026, 6, 7, 12, 0)) is False

    def test_naive_datetime_assumed_ist(self):
        assert is_market_open(datetime(2026, 6, 5, 12, 0)) is True

    def test_aware_datetime_converted_to_ist(self):
        # 06:00 UTC == 11:30 IST on a weekday → open.
        utc_noon_session = datetime(2026, 6, 5, 6, 0, tzinfo=ZoneInfo("UTC"))
        assert is_market_open(utc_noon_session) is True
        # 12:00 UTC == 17:30 IST → after close.
        utc_after_close = datetime(2026, 6, 5, 12, 0, tzinfo=ZoneInfo("UTC"))
        assert is_market_open(utc_after_close) is False
