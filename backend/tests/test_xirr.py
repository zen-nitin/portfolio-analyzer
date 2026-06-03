"""
Thorough tests for the pure-Python XIRR implementation.

Tests cover:
- Simple buy + current value (known answer)
- Multiple cashflows across years
- All-loss scenario
- Exactly break-even
- Single cashflow (degenerate – returns None)
- All-positive cashflows (degenerate – returns None)
- Empty input
- High-return scenario
- Very small return
"""
from datetime import date

import pytest

from app.services.xirr import xirr


# -----------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------

def approx_equal(a: float | None, b: float, tol: float = 0.001) -> bool:
    """True if |a - b| <= tol (tolerates small numerical differences)."""
    if a is None:
        return False
    return abs(a - b) <= tol


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------

class TestXIRRKnownAnswers:
    """Known-answer tests verified against Excel XIRR / financial calculators."""

    def test_simple_one_year_gain(self):
        """Buy 1000, receive 1200 exactly one year later → ~20% p.a."""
        cashflows = [
            (date(2023, 1, 1), -1000.0),
            (date(2024, 1, 1),  1200.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        # Excel XIRR gives ~0.2000 for exactly 365 days
        assert approx_equal(result, 0.2000, tol=0.002)

    def test_simple_six_month_gain(self):
        """Buy 1000, receive 1100 after ~6 months → ~20% annualised."""
        cashflows = [
            (date(2023, 1, 1),  -1000.0),
            (date(2023, 7, 1),   1100.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        # ~21% annualised for ~10% half-year gain
        assert result > 0.15
        assert result < 0.30

    def test_multiple_purchases_gain(self):
        """SIP-style: buy 3 times, current value positive."""
        cashflows = [
            (date(2021, 1, 1),  -10000.0),
            (date(2022, 1, 1),  -10000.0),
            (date(2023, 1, 1),  -10000.0),
            (date(2024, 1, 1),   38000.0),  # total 30k invested, 38k value
        ]
        result = xirr(cashflows)
        assert result is not None
        # Should be a meaningful positive return
        assert result > 0.05
        assert result < 0.50

    def test_buy_and_partial_sell(self):
        """Buy, partially sell for profit, still hold remainder."""
        cashflows = [
            (date(2020, 1, 1),  -50000.0),
            (date(2021, 6, 1),   20000.0),  # partial sell
            (date(2024, 1, 1),   45000.0),  # current value of remainder
        ]
        result = xirr(cashflows)
        assert result is not None
        assert result > 0

    def test_all_loss_scenario(self):
        """Buy 10000, current value 7000 → negative XIRR."""
        cashflows = [
            (date(2022, 1, 1), -10000.0),
            (date(2024, 1, 1),   7000.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        assert result < 0  # loss scenario gives negative rate

    def test_exactly_breakeven(self):
        """Buy and sell for exact same amount → XIRR ≈ 0."""
        cashflows = [
            (date(2023, 1, 1), -5000.0),
            (date(2024, 1, 1),  5000.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        assert approx_equal(result, 0.0, tol=0.001)

    def test_high_return(self):
        """Buy 1000, worth 3000 in one year → ~200% return."""
        cashflows = [
            (date(2023, 1, 1), -1000.0),
            (date(2024, 1, 1),  3000.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        assert approx_equal(result, 2.0, tol=0.05)

    def test_very_small_return(self):
        """Buy 10000, worth 10050 after one year → ~0.5% p.a."""
        cashflows = [
            (date(2023, 1, 1), -10000.0),
            (date(2024, 1, 1),  10050.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        assert approx_equal(result, 0.005, tol=0.002)

    def test_realistic_sip_scenario(self):
        """Realistic monthly SIP over 2 years with decent returns."""
        from datetime import timedelta
        start = date(2022, 1, 1)
        cashflows = []
        # 24 monthly instalments of 5000
        for i in range(24):
            d = date(start.year, start.month, 1)
            # Advance by i months
            month = start.month + i
            year = start.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            cashflows.append((date(year, month, 1), -5000.0))
        # Final value: 24 * 5000 = 120k invested, say 145k now
        cashflows.append((date(2024, 1, 1), 145000.0))
        result = xirr(cashflows)
        assert result is not None
        assert result > 0.10  # decent return


class TestXIRRDegenerateCases:
    """Tests for edge cases that should return None."""

    def test_empty_cashflows(self):
        result = xirr([])
        assert result is None

    def test_all_negative_cashflows(self):
        """Only outflows – no return date, cannot compute."""
        cashflows = [
            (date(2023, 1, 1), -1000.0),
            (date(2023, 6, 1), -2000.0),
        ]
        result = xirr(cashflows)
        assert result is None

    def test_all_positive_cashflows(self):
        """Only inflows – no investment, cannot compute."""
        cashflows = [
            (date(2023, 1, 1), 1000.0),
            (date(2023, 6, 1), 2000.0),
        ]
        result = xirr(cashflows)
        assert result is None

    def test_single_cashflow(self):
        """Cannot compute XIRR from a single cashflow."""
        result = xirr([(date(2023, 1, 1), -1000.0)])
        assert result is None


class TestXIRRReturnType:
    """Type safety and return-value contracts."""

    def test_returns_float_when_valid(self):
        cashflows = [
            (date(2023, 1, 1), -1000.0),
            (date(2024, 1, 1),  1100.0),
        ]
        result = xirr(cashflows)
        assert isinstance(result, float)

    def test_result_is_decimal_not_percent(self):
        """Result must be a decimal (0.10 = 10%), not a percentage (10.0)."""
        cashflows = [
            (date(2023, 1, 1), -1000.0),
            (date(2024, 1, 1),  1100.0),
        ]
        result = xirr(cashflows)
        assert result is not None
        # Should be ~0.10, definitely not 10.0
        assert result < 1.0
