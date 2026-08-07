"""Unit tests for the swap-overlay and CVaR-shock additions to fabn_finance.

Covers the 5 functions ported from Optimization/fabn_finance.py into src/
(see Optimization/CLAUDE.md for the model these support): swap_fixed_leg_duration,
swap_quarterly_cashflows, swap_fair_value, historical_shock_scenarios, and
market_values_under_shocks. None of these were unit-tested before this port.
"""

from __future__ import annotations

import numpy as np
import pytest

import fabn_finance as ff


def make_bond(coupon_rate, years, freq=1):
    """Return (cf, t) for a bullet bond, per $1 face."""
    n = int(round(years * freq))
    per = coupon_rate / freq
    t = np.array([(k + 1) / freq for k in range(n)], dtype=float)
    cf = np.full(n, per, dtype=float)
    cf[-1] += 1.0
    return cf, t


# ---------------------------------------------------------------------------
# swap_fixed_leg_duration
# ---------------------------------------------------------------------------
def test_swap_fixed_leg_duration_matches_par_bond_duration():
    # A receive-fixed swap's duration equals a par bond's duration with the
    # same coupon/maturity (the ALM equivalence documented in the docstring).
    dur = ff.swap_fixed_leg_duration(3.0, 0.0435, 0.0435, settlement_freq=2)
    cf, t = make_bond(0.0435, 3.0, freq=2)
    expected = ff.modified_duration(cf, t, 0.0435)
    assert dur == pytest.approx(expected, rel=1e-9)


def test_swap_fixed_leg_duration_increases_with_tenor():
    d1 = ff.swap_fixed_leg_duration(1.0, 0.0435, 0.0435)
    d3 = ff.swap_fixed_leg_duration(3.0, 0.0435, 0.0435)
    assert d3 > d1 > 0


def test_swap_fixed_leg_duration_degenerate_tenor_is_nan():
    assert np.isnan(ff.swap_fixed_leg_duration(0.0, 0.0435, 0.0435))


# ---------------------------------------------------------------------------
# swap_quarterly_cashflows
# ---------------------------------------------------------------------------
def test_swap_quarterly_cashflows_shape_and_zero_beyond_maturity():
    cf = ff.swap_quarterly_cashflows(0.0435, 0.0435, 2.0, n_quarters=12, settlement_freq=2)
    assert cf.shape == (12,)
    # At-the-money (fixed == float): every settlement nets to zero.
    assert np.allclose(cf, 0.0)
    # Semi-annual settlements land on quarters 1 and 3 (0-indexed); quarters
    # beyond the 2yr maturity (index >= 8) are untouched (still zero here).
    assert cf[8:].sum() == 0.0


def test_swap_quarterly_cashflows_receive_fixed_positive_when_rates_fall():
    # Fixed > floating -> receive-fixed party is net positive.
    cf = ff.swap_quarterly_cashflows(0.05, 0.03, 1.0, n_quarters=4, settlement_freq=2)
    nonzero = cf[cf != 0]
    assert len(nonzero) == 2  # semi-annual settlements within 1yr
    assert np.all(nonzero > 0)


# ---------------------------------------------------------------------------
# swap_fair_value
# ---------------------------------------------------------------------------
def test_swap_fair_value_near_zero_at_the_money():
    # Not exactly zero: the semi-annual coupon accrual (simple, dt-based) and the
    # annual-compounding discount factor are slightly different conventions, so
    # an at-the-money swap prices a few bps away from par rather than exactly 0.
    fv = ff.swap_fair_value(0.0435, 0.0435, 3.0)
    assert fv == pytest.approx(0.0, abs=0.005)


def test_swap_fair_value_positive_when_rates_fall():
    # Fixed receipts above the new market rate -> in-the-money for receive-fixed.
    fv = ff.swap_fair_value(0.05, 0.03, 3.0)
    assert fv > 0


def test_swap_fair_value_zero_maturity():
    assert ff.swap_fair_value(0.0435, 0.03, 0.0) == 0.0


# ---------------------------------------------------------------------------
# historical_shock_scenarios
# ---------------------------------------------------------------------------
def test_historical_shock_scenarios_shape_and_horizon():
    # 150 obs, horizon 21, under the 250 max_scenarios cap -> no subsampling.
    rng = np.random.default_rng(0)
    rate_hist = np.cumsum(rng.normal(0, 0.0005, 150)) + 0.04
    spread_hist = np.cumsum(rng.normal(0, 0.0003, 150)) + 0.01
    dr, ds = ff.historical_shock_scenarios(rate_hist, spread_hist, horizon_days=21, max_scenarios=250)
    assert len(dr) == len(ds)
    assert len(dr) == 150 - 21
    # Each shock is a genuine k-day difference of the input series.
    assert dr[0] == pytest.approx(rate_hist[21] - rate_hist[0])


def test_historical_shock_scenarios_caps_at_max_scenarios():
    rng = np.random.default_rng(1)
    rate_hist = rng.normal(0.04, 0.001, 500)
    spread_hist = rng.normal(0.01, 0.001, 500)
    dr, ds = ff.historical_shock_scenarios(rate_hist, spread_hist, horizon_days=21, max_scenarios=100)
    assert len(dr) == 100
    assert len(ds) == 100


def test_historical_shock_scenarios_insufficient_history_returns_empty():
    dr, ds = ff.historical_shock_scenarios([0.04, 0.041], [0.01, 0.011], horizon_days=21)
    assert len(dr) == 0 and len(ds) == 0


# ---------------------------------------------------------------------------
# market_values_under_shocks
# ---------------------------------------------------------------------------
def test_market_values_under_shocks_zero_shock_reproduces_book_value():
    # Base yield = the IRR that reprices the bond at its own book value, so a
    # zero shock must reproduce that same value (the CVaR pipeline relies on
    # this to normalize forced-sale loss as 1 - MV/BV).
    cf, t = make_bond(0.05, 5)
    price = 100.0
    book_yield_arr = ff.book_yields(cf[None, :].T, t, np.array([price]))
    mv = ff.market_values_under_shocks(cf[:, None], t, book_yield_arr, np.array([0.0]), np.array([0.0]))
    assert mv[0, 0] == pytest.approx(price / 100.0, rel=1e-6)


def test_market_values_under_shocks_rate_up_lowers_value():
    cf, t = make_bond(0.05, 5)
    base_yield = np.array([0.05])
    mv = ff.market_values_under_shocks(cf[:, None], t, base_yield, np.array([0.0, 0.01]), np.array([0.0, 0.0]))
    assert mv[1, 0] < mv[0, 0]


def test_market_values_under_shocks_shape():
    cf, t = make_bond(0.05, 5)
    base_yield = np.array([0.05])
    d_rate = np.zeros(10)
    d_spread = np.zeros(10)
    mv = ff.market_values_under_shocks(cf[:, None], t, base_yield, d_rate, d_spread)
    assert mv.shape == (10, 1)
