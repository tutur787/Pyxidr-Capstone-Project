"""Unit + identity tests for fabn_finance (Test Plan #1).

Run from the Optimization folder:  pytest tests/ -v
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fabn_finance as ff


# ---------------------------------------------------------------------------
# Helpers: build a synthetic annual-coupon bullet bond, per $1 face.
# ---------------------------------------------------------------------------
def make_bond(coupon_rate, years, freq=1):
    """Return (cf, t) for a bullet bond, per $1 face.

    coupon_rate is the annual decimal coupon (e.g. 0.05). Cashflows include the
    per-period coupon each period and the par redemption (1.0) at maturity.
    """
    n = int(round(years * freq))
    per = coupon_rate / freq
    t = np.array([(k + 1) / freq for k in range(n)], dtype=float)
    cf = np.full(n, per, dtype=float)
    cf[-1] += 1.0  # par redemption per $1 face
    return cf, t


def price_at_yield(cf, t, y):
    """Dirty PV per $1 face at yield y (inverse of book_yield), times 100."""
    return float((cf * (1.0 + y) ** (-t)).sum()) * 100.0


# ---------------------------------------------------------------------------
# Book yield
# ---------------------------------------------------------------------------
def test_par_bond_yield_equals_coupon():
    # A bond priced at exactly par should yield ~ its coupon rate.
    cf, t = make_bond(0.05, 5)
    y = ff.book_yield(cf, t, target_pv=1.0)  # price 100 -> per $1 = 1.0
    assert y == pytest.approx(0.05, abs=1e-6)


def test_premium_bond_yield_below_coupon():
    cf, t = make_bond(0.06, 5)
    price = price_at_yield(cf, t, 0.038)  # construct a known premium price
    y = ff.book_yield(cf, t, target_pv=price / 100.0)
    assert y == pytest.approx(0.038, abs=1e-6)
    assert y < 0.06


def test_discount_bond_yield_above_coupon():
    cf, t = make_bond(0.06, 5)
    price = price_at_yield(cf, t, 0.072)
    y = ff.book_yield(cf, t, target_pv=price / 100.0)
    assert y == pytest.approx(0.072, abs=1e-6)
    assert y > 0.06


def test_book_yield_roundtrip():
    # Pricing at y then solving must recover y.
    cf, t = make_bond(0.045, 7)
    for y_true in (-0.01, 0.0, 0.03, 0.08, 0.15):
        pv = float((cf * (1.0 + y_true) ** (-t)).sum())
        assert ff.book_yield(cf, t, pv) == pytest.approx(y_true, abs=1e-7)


def test_book_yield_guards():
    cf, t = make_bond(0.05, 5)
    assert np.isnan(ff.book_yield(np.zeros_like(cf), t, 1.0))  # no cashflows
    assert np.isnan(ff.book_yield(cf, t, 0.0))  # non-positive target


def test_book_yields_vectorised_with_fallback():
    cf1, t = make_bond(0.05, 5)
    bond_cf = np.column_stack([cf1, np.zeros_like(cf1)])  # 2nd bond has no CFs
    prices = np.array([100.0, 99.0])
    out = ff.book_yields(bond_cf, t, prices, fallback=np.array([0.0, 0.123]))
    assert out[0] == pytest.approx(0.05, abs=1e-6)
    assert out[1] == pytest.approx(0.123)  # fallback used for the empty bond


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------
def test_zero_coupon_modified_duration():
    # Zero-coupon: Macaulay = maturity, Modified = maturity / (1+y).
    T = 6.0
    cf = np.array([1.0])
    t = np.array([T])
    y = 0.04
    assert ff.macaulay_duration(cf, t, y) == pytest.approx(T)
    assert ff.modified_duration(cf, t, y) == pytest.approx(T / (1 + y))


def test_coupon_bond_duration_less_than_maturity():
    cf, t = make_bond(0.05, 10)
    D = ff.macaulay_duration(cf, t, 0.05)
    assert 0 < D < 10  # coupon bond duration strictly below maturity


def test_duration_guards():
    cf, t = make_bond(0.05, 5)
    assert np.isnan(ff.modified_duration(cf, t, -1.5))  # y <= -1
    assert np.isnan(ff.modified_duration(np.zeros_like(cf), t, 0.05))


# ---------------------------------------------------------------------------
# Coupon / amortization identity
# ---------------------------------------------------------------------------
def test_amort_split_identity_and_signs():
    book = np.array([0.038, 0.072, 0.05])
    annual_coupon = np.array([0.06, 0.06, 0.05])
    price = np.array([110.0, 95.0, 100.0])  # premium, discount, par
    coupon_inc, amort_inc = ff.coupon_amort_split(book, annual_coupon, price)
    # identity: book == coupon + amort
    np.testing.assert_allclose(book, coupon_inc + amort_inc, atol=1e-12)
    assert amort_inc[0] < 0  # premium -> amortize down
    assert amort_inc[1] > 0  # discount -> accrete up
    assert amort_inc[2] == pytest.approx(0.0, abs=1e-12)  # par


# ---------------------------------------------------------------------------
# C-1 lookup
# ---------------------------------------------------------------------------
def test_c1_known_ratings():
    assert ff.lookup_c1("AAA", None) == pytest.approx(0.00158)
    assert ff.lookup_c1("BBB", None) == pytest.approx(0.01523)
    assert ff.lookup_c1("  A-  ", None) == pytest.approx(0.01016)  # whitespace


def test_c1_moodys_fallback():
    # No usable S&P -> fall through to Moody's.
    assert ff.lookup_c1(None, "Baa2") == pytest.approx(0.01523)
    assert ff.lookup_c1(np.nan, "Aaa") == pytest.approx(0.00158)


def test_c1_default_when_missing():
    assert ff.lookup_c1(None, None) == ff.DEFAULT_C1
    assert ff.lookup_c1("not-a-rating", "also-bad") == ff.DEFAULT_C1
    assert ff.lookup_c1(np.nan, np.nan) == ff.DEFAULT_C1


def test_c1_vectorised():
    sp = ["AAA", None, "junk"]
    md = ["Aa2", "Baa3", None]
    out = ff.c1_factors(sp, md)
    assert out[0] == pytest.approx(0.00158)  # S&P wins
    assert out[1] == pytest.approx(0.02168)  # Moody's Baa3
    assert out[2] == ff.DEFAULT_C1  # both unusable


# ---------------------------------------------------------------------------
# IMR (Phase 2 foundation)
# ---------------------------------------------------------------------------
def test_realized_gain_sign():
    # Sell $1M book value; market above book -> gain, below -> loss.
    assert ff.realized_gain_on_sale(1_000_000, 105.0, 100.0) == pytest.approx(50_000.0)
    assert ff.realized_gain_on_sale(1_000_000, 98.0, 100.0) == pytest.approx(-20_000.0)
    assert ff.realized_gain_on_sale(1_000_000, 100.0, 0.0) == 0.0  # guard


def test_imr_straight_line_release():
    imr = ff.IMRLedger()
    imr.add_realized(100.0, remaining_years=2.0)
    assert imr.balance == pytest.approx(100.0)
    assert imr.accrue(1.0) == pytest.approx(50.0)   # half over year 1
    assert imr.balance == pytest.approx(50.0)
    assert imr.accrue(1.0) == pytest.approx(50.0)   # rest over year 2
    assert imr.balance == pytest.approx(0.0)


def test_imr_conservation_identity():
    # KEY accounting identity: total released over life == total gains added,
    # nothing booked at t=sale, nothing lost or double-counted.
    rng = np.random.default_rng(0)
    imr = ff.IMRLedger()
    gains = []
    released = 0.0
    for k in range(50):
        if rng.random() < 0.4:                       # occasionally realize a gain/loss
            g = float(rng.normal(0, 1000)); yrs = float(rng.uniform(0.3, 5.0))
            imr.add_realized(g, yrs); gains.append(g)
        released += imr.accrue(0.25)                 # quarterly steps
    # flush any residual far past the longest horizon
    released += imr.accrue(100.0)
    assert imr.balance == pytest.approx(0.0, abs=1e-9)
    assert released == pytest.approx(sum(gains), abs=1e-6)


def test_imr_handles_losses_and_zero():
    imr = ff.IMRLedger()
    imr.add_realized(-200.0, 1.0)
    imr.add_realized(0.0, 1.0)                        # ignored
    assert imr.balance == pytest.approx(-200.0)
    assert imr.accrue(0.5) == pytest.approx(-100.0)   # losses amortize too


# ---------------------------------------------------------------------------
# Amortized cost basis (feeds the realized-gain → IMR calc)
# ---------------------------------------------------------------------------
def test_amortize_price_to_par():
    # Premium 104 with 2y left, advance 1y -> halfway to par = 102.
    assert ff.amortize_price_to_par(104.0, 1.0, 2.0) == pytest.approx(102.0)
    # Advancing the full remaining life lands exactly on par.
    assert ff.amortize_price_to_par(104.0, 2.0, 2.0) == pytest.approx(100.0)
    # Past maturity (dt >= remaining) clamps to par; discount pulls UP to par.
    assert ff.amortize_price_to_par(96.0, 5.0, 2.0) == pytest.approx(100.0)


def test_amortize_price_to_par_vectorised():
    out = ff.amortize_price_to_par(np.array([104.0, 96.0]), 1.0, np.array([2.0, 4.0]))
    assert out[0] == pytest.approx(102.0)
    assert out[1] == pytest.approx(97.0)  # 96 + (100-96)*1/4


def test_blend_cost_basis():
    # $100 retained at 102 + $100 bought at 98 -> dollar-weighted 100.
    assert ff.blend_cost_basis(100.0, 102.0, 100.0, 98.0) == pytest.approx(100.0)
    # No buys -> cost price unchanged.
    assert ff.blend_cost_basis(50.0, 105.0, 0.0, 99.0) == pytest.approx(105.0)
    # Empty resulting position -> par.
    assert ff.blend_cost_basis(0.0, 105.0, 0.0, 99.0) == pytest.approx(100.0)


def test_imr_end_to_end_buy_hold_sell():
    """Buy at par, rates fall (mid rises to 106), sell after 2y of a 5y bond:
    the realized rate-driven gain is recognized gradually over the 3y remaining
    life, and total recognized equals the gain (conservation)."""
    imr = ff.IMRLedger()
    cb = 100.0                                   # bought $10M at par
    book_dollars = 10_000_000.0
    # hold 2 years: amortized cost barely moves for a par bond (stays ~100)
    cb = ff.amortize_price_to_par(cb, 2.0, 5.0)  # 100 -> stays 100
    # sell at mid 106 with 3y remaining
    gain = ff.realized_gain_on_sale(book_dollars, 106.0, cb)
    assert gain == pytest.approx(600_000.0)
    imr.add_realized(gain, remaining_years=3.0)
    assert imr.balance == pytest.approx(600_000.0)   # nothing booked at sale
    rel_y1 = imr.accrue(1.0)
    assert rel_y1 == pytest.approx(200_000.0)        # straight-line over 3y
    total = rel_y1 + imr.accrue(1.0) + imr.accrue(1.0)
    assert total == pytest.approx(gain)              # fully recognized = the gain
    assert imr.balance == pytest.approx(0.0)
