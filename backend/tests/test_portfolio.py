"""
Tests for portfolio service:
- holding_status classifier (all 5 buckets + boundaries)
- build_summary aggregation
- compute_pnl_pct edge cases
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.services.portfolio import (
    build_summary,
    compute_pnl_pct,
    holding_status,
)


# -----------------------------------------------------------------------
# holding_status classifier
# -----------------------------------------------------------------------

class TestHoldingStatus:
    """Verify the 5-bucket classification with exact boundary behaviour."""

    # STRONG_GAIN: pnl_pct > 15%
    def test_strong_gain_above_15(self):
        assert holding_status(15.1) == "STRONG_GAIN"

    def test_strong_gain_large(self):
        assert holding_status(100.0) == "STRONG_GAIN"

    def test_strong_gain_exactly_15_is_gain(self):
        # 15.0 is NOT > 15, so it should be GAIN
        assert holding_status(15.0) == "GAIN"

    # GAIN: 0.5 < pnl_pct <= 15%
    def test_gain_typical(self):
        assert holding_status(10.0) == "GAIN"

    def test_gain_just_above_flat(self):
        assert holding_status(0.6) == "GAIN"

    def test_gain_just_below_strong(self):
        assert holding_status(14.9) == "GAIN"

    # FLAT: -0.5 <= pnl_pct <= 0.5
    def test_flat_zero(self):
        assert holding_status(0.0) == "FLAT"

    def test_flat_small_positive(self):
        assert holding_status(0.4) == "FLAT"

    def test_flat_small_negative(self):
        assert holding_status(-0.4) == "FLAT"

    def test_flat_at_positive_boundary(self):
        assert holding_status(0.5) == "FLAT"

    def test_flat_at_negative_boundary(self):
        assert holding_status(-0.5) == "FLAT"

    # LOSS: -15% <= pnl_pct < -0.5%
    def test_loss_typical(self):
        assert holding_status(-5.0) == "LOSS"

    def test_loss_just_below_flat(self):
        assert holding_status(-0.6) == "LOSS"

    def test_loss_near_strong_threshold(self):
        assert holding_status(-14.9) == "LOSS"

    # STRONG_LOSS: pnl_pct < -15%
    def test_strong_loss_below_minus_15(self):
        assert holding_status(-15.1) == "STRONG_LOSS"

    def test_strong_loss_large(self):
        assert holding_status(-80.0) == "STRONG_LOSS"

    def test_strong_loss_exactly_minus_15_is_loss(self):
        # -15.0 is NOT < -15, so it should be LOSS
        assert holding_status(-15.0) == "LOSS"


# -----------------------------------------------------------------------
# compute_pnl_pct
# -----------------------------------------------------------------------

class TestComputePnlPct:
    def test_positive_pnl(self):
        # cost = 100*10 = 1000, pnl = 100 → 10%
        result = compute_pnl_pct(pnl=100.0, average_price=100.0, quantity=10.0)
        assert abs(result - 10.0) < 0.01

    def test_zero_cost(self):
        result = compute_pnl_pct(pnl=100.0, average_price=0.0, quantity=10.0)
        assert result == 0.0

    def test_zero_quantity(self):
        result = compute_pnl_pct(pnl=100.0, average_price=100.0, quantity=0.0)
        assert result == 0.0

    def test_negative_pnl(self):
        result = compute_pnl_pct(pnl=-200.0, average_price=100.0, quantity=10.0)
        assert abs(result - (-20.0)) < 0.01


# -----------------------------------------------------------------------
# build_summary
# -----------------------------------------------------------------------

def _make_holding(average_price, quantity, last_price, pnl=None, day_change=0.0):
    """Create a mock Holding with the given attributes."""
    h = MagicMock()
    h.average_price = average_price
    h.quantity = quantity
    h.last_price = last_price
    h.pnl = pnl if pnl is not None else (last_price - average_price) * quantity
    h.day_change = day_change
    return h


def _make_transaction(trade_type, amount, fees, trade_date):
    tx = MagicMock()
    tx.trade_type = trade_type
    tx.amount = amount
    tx.fees = fees
    tx.trade_date = trade_date
    return tx


class TestBuildSummary:
    def test_single_holding_no_transactions(self):
        holdings = [_make_holding(100.0, 10, 120.0, pnl=200.0, day_change=50.0)]
        result = build_summary(holdings, [])
        assert result["total_invested"] == 1000.0
        assert result["current_value"] == 1200.0
        assert result["pnl"] == 200.0
        assert abs(result["pnl_pct"] - 20.0) < 0.01
        assert result["day_change"] == 50.0
        assert result["xirr"] is None  # no transactions

    def test_multiple_holdings_aggregated(self):
        holdings = [
            _make_holding(100.0, 10, 120.0, pnl=200.0, day_change=10.0),
            _make_holding(50.0, 20, 55.0, pnl=100.0, day_change=5.0),
        ]
        result = build_summary(holdings, [])
        # total_invested = 1000 + 1000 = 2000
        assert result["total_invested"] == 2000.0
        # current_value = 1200 + 1100 = 2300
        assert result["current_value"] == 2300.0
        assert result["pnl"] == 300.0
        assert result["day_change"] == 15.0

    def test_empty_holdings(self):
        result = build_summary([], [])
        assert result["total_invested"] == 0.0
        assert result["current_value"] == 0.0
        assert result["pnl"] == 0.0
        assert result["pnl_pct"] == 0.0
        assert result["xirr"] is None

    def test_xirr_computed_with_transactions(self):
        holdings = [_make_holding(100.0, 10, 110.0, pnl=100.0)]
        transactions = [
            _make_transaction("buy", 1000.0, 10.0, date(2023, 1, 1)),
        ]
        result = build_summary(holdings, transactions)
        # XIRR should be computed (positive return)
        assert result["xirr"] is not None
        assert result["xirr"] > 0

    def test_pnl_pct_zero_when_no_investment(self):
        result = build_summary([], [])
        assert result["pnl_pct"] == 0.0

    def test_loss_portfolio(self):
        holdings = [_make_holding(100.0, 10, 80.0, pnl=-200.0, day_change=-20.0)]
        result = build_summary(holdings, [])
        assert result["pnl"] == -200.0
        assert result["pnl_pct"] < 0
        assert result["day_change"] == -20.0
