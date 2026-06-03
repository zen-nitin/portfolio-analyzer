"""
Pure-Python XIRR (Extended Internal Rate of Return) computation.

No external dependencies (no scipy, no numpy).

Convention:
    Outflows (purchases / buys)  → **negative** values
    Inflows  (sells + final value) → **positive** values

Algorithm:
    1. Newton-Raphson method (fast convergence near the solution).
    2. Bisection fallback if Newton diverges or fails to converge.

Signature:
    xirr(cashflows: list[tuple[date, float]]) -> float | None

Returns ``None`` if the rate cannot be determined (e.g. all cashflows are
the same sign, or the iteration does not converge).
"""
from __future__ import annotations

from datetime import date
from typing import Optional


def _npv(rate: float, cashflows: list[tuple[date, float]], t0: date) -> float:
    """Net present value at the given annual rate."""
    total = 0.0
    for cf_date, amount in cashflows:
        years = (cf_date - t0).days / 365.0
        total += amount / ((1.0 + rate) ** years)
    return total


def _dnpv(rate: float, cashflows: list[tuple[date, float]], t0: date) -> float:
    """Derivative of NPV with respect to rate (for Newton step)."""
    total = 0.0
    for cf_date, amount in cashflows:
        years = (cf_date - t0).days / 365.0
        if years == 0:
            continue
        total -= years * amount / ((1.0 + rate) ** (years + 1))
    return total


def xirr(cashflows: list[tuple[date, float]]) -> Optional[float]:
    """Compute the annualised XIRR for a series of dated cashflows.

    Args:
        cashflows: List of (date, amount) tuples.
                   Outflows (buys) must be **negative**.
                   Inflows (sells, current value) must be **positive**.

    Returns:
        Annualised return as a decimal (e.g. 0.184 = 18.4%), or ``None``
        if convergence fails or the input is degenerate.

    Examples:
        >>> from datetime import date
        >>> # Buy 100 on Jan 1, value is 120 on Dec 31 → ~20% return
        >>> xirr([(date(2023, 1, 1), -100), (date(2023, 12, 31), 120)])
        ~0.2007
    """
    if not cashflows:
        return None

    # Need at least one positive and one negative cashflow
    has_positive = any(a > 0 for _, a in cashflows)
    has_negative = any(a < 0 for _, a in cashflows)
    if not (has_positive and has_negative):
        return None

    # Use earliest date as time zero
    t0 = min(d for d, _ in cashflows)

    # --- Newton-Raphson ---
    rate = 0.10  # initial guess: 10%
    MAX_ITER = 200
    TOLERANCE = 1e-7

    for _ in range(MAX_ITER):
        npv = _npv(rate, cashflows, t0)
        d = _dnpv(rate, cashflows, t0)
        if d == 0.0:
            break
        new_rate = rate - npv / d
        if abs(new_rate - rate) < TOLERANCE:
            # Check it's a valid rate (>-1 means no more than 100% loss)
            if new_rate > -1.0:
                return round(new_rate, 8)
            break
        rate = new_rate
        # Keep rate in reasonable bounds to avoid divergence
        rate = max(-0.9999, min(rate, 100.0))

    # --- Bisection fallback ---
    return _bisection(cashflows, t0, TOLERANCE)


def _bisection(
    cashflows: list[tuple[date, float]],
    t0: date,
    tol: float = 1e-7,
) -> Optional[float]:
    """Bisection method fallback for XIRR."""
    # Find a bracket [lo, hi] where NPV changes sign
    lo, hi = -0.9999, 10.0  # -99.99% to +1000%
    f_lo = _npv(lo, cashflows, t0)
    f_hi = _npv(hi, cashflows, t0)

    # If same sign, try to expand the bracket
    if f_lo * f_hi > 0:
        # Try hi = 100 (10000%)
        hi = 100.0
        f_hi = _npv(hi, cashflows, t0)
        if f_lo * f_hi > 0:
            return None

    for _ in range(300):
        mid = (lo + hi) / 2.0
        f_mid = _npv(mid, cashflows, t0)
        if abs(f_mid) < tol or (hi - lo) / 2.0 < tol:
            return round(mid, 8)
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid

    return None
