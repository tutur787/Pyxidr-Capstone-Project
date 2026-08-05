"""fabn_finance — shared financial math for the FABN optimizer.

Pure, dependency-light functions extracted from the notebooks so the math has a
single source of truth and can be unit-tested (see tests/test_fabn_finance.py).
Both ``FABN_Data_Pipeline.ipynb`` and ``FABN_Optimizer_SAP_Backtest.ipynb``
previously duplicated the IRR / duration logic; import from here instead.

Conventions
-----------
- Cashflows ``cf`` are **per $1 face** (the BigQuery per-100 figures divided by
  100). The matching price target is therefore ``price / 100`` (per $1 face).
- ``t`` / ``t_vec`` are times in **years** from the valuation date.
- Yields, durations, and C-1 factors are returned in decimal / years.

Formulas (one-line references)
------------------------------
- Book yield  : effective-interest IRR solving  sum_t CF_t (1+y)^(-t) = P/100.
- Duration    : Macaulay  D = sum_t t*PV(CF_t) / sum_t PV(CF_t);
                Modified   D_mod = D / (1+y).
- C-1 factor  : NAIC rating -> capital charge lookup (S&P, then Moody's, then BBB).
- Amortization: book_yield = coupon_inc + amort_inc, with
                coupon_inc = annual_coupon / (price/100).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

# Search bracket / iteration cap for the IRR solve — kept identical to the
# original notebook code so results are bit-for-bit reproducible.
_IRR_LO, _IRR_HI, _IRR_MAXITER = -0.5, 1.0, 200


# ---------------------------------------------------------------------------
# Book yield (effective-interest IRR)
# ---------------------------------------------------------------------------
def book_yield(cf, t, target_pv):
    """Effective-interest yield solving ``sum_t cf_t (1+y)^(-t) = target_pv``.

    Parameters
    ----------
    cf : array-like
        Cashflows per $1 face, aligned to ``t``.
    t : array-like
        Times in years (same length as ``cf``).
    target_pv : float
        Present-value target per $1 face (i.e. ``price / 100``).

    Returns
    -------
    float
        The IRR, or ``np.nan`` if there are no cashflows, the target is
        non-positive, or no root exists in ``[-0.5, 1.0]``.
    """
    cf = np.asarray(cf, dtype=float)
    t = np.asarray(t, dtype=float)
    if cf.sum() == 0 or target_pv <= 0:
        return np.nan
    f = lambda y: float((cf * (1.0 + y) ** (-t)).sum() - target_pv)
    try:
        return brentq(f, _IRR_LO, _IRR_HI, maxiter=_IRR_MAXITER)
    except (ValueError, OverflowError):
        return np.nan


def book_yields(bond_cf, t_vec, prices, fallback=None):
    """Vectorised :func:`book_yield` over an (T, N) cashflow matrix.

    ``prices`` are per-100 face; the per-$1 PV target is ``price / 100``.
    Where the solve fails and ``fallback`` is given, the fallback value for that
    bond is used (the notebook uses ``rf + spread``).
    """
    bond_cf = np.asarray(bond_cf, dtype=float)
    prices = np.asarray(prices, dtype=float)
    n = bond_cf.shape[1]
    out = np.array(
        [book_yield(bond_cf[:, i], t_vec, prices[i] / 100.0) for i in range(n)]
    )
    if fallback is not None:
        fallback = np.asarray(fallback, dtype=float)
        out = np.where(np.isnan(out), fallback, out)
    return out


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------
def macaulay_duration(cf, t, y):
    """Macaulay duration ``sum_t t*PV(CF_t) / sum_t PV(CF_t)`` at yield ``y``."""
    cf = np.asarray(cf, dtype=float)
    t = np.asarray(t, dtype=float)
    if y <= -1 or cf.sum() == 0:
        return np.nan
    discount = (1.0 + y) ** (-t)
    pv_cf = cf * discount
    total_pv = pv_cf.sum()
    if total_pv == 0:
        return np.nan
    return (t * pv_cf).sum() / total_pv


def modified_duration(cf, t, y):
    """Modified duration ``Macaulay / (1 + y)``."""
    mac = macaulay_duration(cf, t, y)
    if np.isnan(mac):
        return np.nan
    return mac / (1.0 + y)


def modified_durations(bond_cf, t_vec, yields, fallback=None):
    """Vectorised :func:`modified_duration` over an (T, N) cashflow matrix.

    ``yields`` is the per-bond discount yield (e.g. ``rf + spread``). Where the
    calc fails and ``fallback`` is given (e.g. Bloomberg duration), it is used.
    """
    bond_cf = np.asarray(bond_cf, dtype=float)
    yields = np.asarray(yields, dtype=float)
    n = bond_cf.shape[1]
    out = np.array(
        [modified_duration(bond_cf[:, i], t_vec, yields[i]) for i in range(n)]
    )
    if fallback is not None:
        fallback = np.asarray(fallback, dtype=float)
        out = np.where(np.isnan(out), fallback, out)
    return out


# ---------------------------------------------------------------------------
# Coupon / amortization split
# ---------------------------------------------------------------------------
def coupon_amort_split(book_yield_arr, annual_coupon, price):
    """Decompose book yield into current coupon yield and amortization/accretion.

    ``annual_coupon`` and ``price`` are per-$1-face and per-100-face respectively
    (matching the pipeline). Returns ``(coupon_inc, amort_inc)`` where
    ``book_yield = coupon_inc + amort_inc``. Premium bonds (price > 100) get
    ``amort_inc < 0``; discount bonds get ``amort_inc > 0``.
    """
    book_yield_arr = np.asarray(book_yield_arr, dtype=float)
    annual_coupon = np.asarray(annual_coupon, dtype=float)
    price_per_1 = np.asarray(price, dtype=float) / 100.0
    coupon_inc = annual_coupon / price_per_1
    amort_inc = book_yield_arr - coupon_inc
    return coupon_inc, amort_inc


# ---------------------------------------------------------------------------
# NAIC C-1 capital charge lookup
# ---------------------------------------------------------------------------
C1_SP = {
    "AAA": 0.00158, "AA+": 0.00271, "AA": 0.00419, "AA-": 0.00523,
    "A+": 0.00657, "A": 0.00816, "A-": 0.01016,
    "BBB+": 0.01261, "BBB": 0.01523, "BBB-": 0.02168,
    "BB+": 0.03151, "BB": 0.04537, "BB-": 0.06017,
    "B+": 0.07386, "B": 0.09535, "B-": 0.12428,
    "CCC+": 0.16942, "CCC": 0.23798, "CCC-": 0.32975,
    "D": 0.30000,
}

C1_MOODYS = {
    "Aaa": 0.00158, "Aa1": 0.00271, "Aa2": 0.00419, "Aa3": 0.00523,
    "A1": 0.00657, "A2": 0.00816, "A3": 0.01016,
    "Baa1": 0.01261, "Baa2": 0.01523, "Baa3": 0.02168,
    "Ba1": 0.03151, "Ba2": 0.04537, "Ba3": 0.06017,
    "B1": 0.07386, "B2": 0.09535, "B3": 0.12428,
    "Caa1": 0.16942, "Caa2": 0.23798, "Caa3": 0.32975,
    "Ca": 0.30000, "C": 0.30000,
}

DEFAULT_C1 = C1_SP["BBB"]  # conservative investment-grade default for missing ratings


def _clean_rating(r):
    """Return a stripped string rating, or None if missing/NaN."""
    if r is None:
        return None
    if isinstance(r, float) and np.isnan(r):
        return None
    s = str(r).strip()
    return s if s and s.lower() != "nan" else None


def lookup_c1(sp_rating, moodys_rating, default=DEFAULT_C1):
    """C-1 charge for one bond: S&P first, then Moody's, then ``default`` (BBB)."""
    sp = _clean_rating(sp_rating)
    if sp is not None and sp in C1_SP:
        return C1_SP[sp]
    md = _clean_rating(moodys_rating)
    if md is not None and md in C1_MOODYS:
        return C1_MOODYS[md]
    return default


def c1_factors(sp_ratings, moodys_ratings, default=DEFAULT_C1):
    """Vectorised :func:`lookup_c1` over aligned rating sequences."""
    return np.array(
        [lookup_c1(s, m, default) for s, m in zip(sp_ratings, moodys_ratings)]
    )


# ---------------------------------------------------------------------------
# IMR (Interest Maintenance Reserve) — Phase 2 foundation
# ---------------------------------------------------------------------------
# Statutory treatment of a realized, interest-rate-driven gain/loss on a bond
# sale: it does NOT hit income at the sale date. It enters the IMR and is
# amortized into income over the SOLD bond's remaining life. Booking the full
# gain immediately would overstate earnings — the same anti-pattern as crediting
# discounted future cashflows as sale proceeds, which this project explicitly
# avoids. (AVR, the credit/default-driven reserve, is out of scope for the MVP.)
def realized_gain_on_sale(sale_book_value, mid_price, book_price):
    """Realized gain/loss when selling a lot carried at amortized cost.

    Parameters
    ----------
    sale_book_value : float
        Dollars of amortized book value being sold.
    mid_price, book_price : float
        Current market mid and amortized book price, both per 100 face.

    Returns
    -------
    float
        Realized gain (positive) or loss (negative): the sold book value scaled
        by the proportional gap between market and book price.
    """
    if book_price <= 0:
        return 0.0
    return sale_book_value * (mid_price - book_price) / book_price


class IMRLedger:
    """Straight-line IMR amortization of realized rate-driven gains/losses.

    Each realized gain ``G`` (can be negative) is amortized linearly into income
    over the sold bond's ``remaining_years``. Releasing ``balance·dt/years_left``
    each step is exactly straight-line (constant ``G/years``) because balance and
    years_left decay together. Guarantees ``Σ released over life == Σ added`` — no
    gain is lost, double-counted, or front-loaded.
    """

    def __init__(self):
        self._lots = []  # each: [remaining_balance, years_left]

    @property
    def balance(self):
        """Unamortized IMR balance (sum of open lots; may be negative)."""
        return float(sum(b for b, _ in self._lots))

    def add_realized(self, gain, remaining_years):
        """Book a realized gain/loss to be amortized over ``remaining_years``."""
        if abs(float(gain)) < 1e-12:
            return
        self._lots.append([float(gain), max(float(remaining_years), 1e-9)])

    def accrue(self, dt_years):
        """Advance ``dt_years`` and return the income released into NII this step."""
        dt = float(dt_years)
        if dt <= 0:
            return 0.0
        released = 0.0
        new = []
        for bal, yrs in self._lots:
            if dt >= yrs:                       # final slice — release the rest
                released += bal
            else:
                r = bal * dt / yrs
                released += r
                new.append([bal - r, yrs - dt])
        self._lots = new
        return released


# ---------------------------------------------------------------------------
# Amortized-cost basis tracking (for computing realized gains feeding the IMR)
# ---------------------------------------------------------------------------
def amortize_price_to_par(cb_px, dt_years, remaining_years, par=100.0):
    """Pull an amortized-cost price toward par over the bond's remaining life.

    Linear pull-to-par: advancing ``dt_years`` moves ``cb_px`` a fraction
    ``dt/remaining`` of the way to ``par``, so it reaches par exactly at maturity.
    This keeps the carrying value consistent with amortized-cost accounting (no
    artificial gain/loss at redemption) and isolates the *rate-driven* gain in a
    pre-maturity sale. Works on scalars or arrays.
    """
    cb_px = np.asarray(cb_px, dtype=float)
    rem = np.asarray(remaining_years, dtype=float)
    frac = np.clip(np.where(rem > dt_years, dt_years / np.maximum(rem, 1e-9), 1.0), 0.0, 1.0)
    return cb_px + (par - cb_px) * frac


def blend_cost_basis(retained_dollars, cb_old, buy_dollars, buy_px, par=100.0):
    """Dollar-weighted average cost price after adding new buys to a retained lot.

    Retained notional keeps its carried cost price ``cb_old``; new ``buy_dollars``
    enter at today's market price ``buy_px``. Returns the blended cost price (par
    where the resulting position is ~0). Works on scalars or arrays.
    """
    retained_dollars = np.asarray(retained_dollars, dtype=float)
    cb_old = np.asarray(cb_old, dtype=float)
    buy_dollars = np.asarray(buy_dollars, dtype=float)
    buy_px = np.asarray(buy_px, dtype=float)
    tot = retained_dollars + buy_dollars
    return np.where(tot > 1e-12,
                    (retained_dollars * cb_old + buy_dollars * buy_px) / np.where(tot > 1e-12, tot, 1.0),
                    par)


# ---------------------------------------------------------------------------
# Interest Rate Swaps — plain vanilla receive-fixed / pay-floating
# ---------------------------------------------------------------------------
# All three functions model a RECEIVE-FIXED swap from the portfolio's perspective:
# we receive the fixed leg (known coupon stream) and pay floating (SOFR-linked).
# Duration is positive (like holding a bond); fair value rises when rates rise.
#
# Convention: notional = $1; scale by actual notional in the optimizer.
# ---------------------------------------------------------------------------

def swap_fixed_leg_duration(maturity_years, fixed_rate, r_discount, settlement_freq=2):
    """Modified duration of a receive-fixed interest rate swap per $1 notional.

    Computed as the modified duration of a par bond with the same coupon and
    maturity — the standard ALM equivalence: a receive-fixed swap changes
    portfolio rate sensitivity exactly like adding a par fixed-rate bond and
    removing a par floater (duration ≈ 0).

    Parameters
    ----------
    maturity_years : float
        Swap tenor in years.
    fixed_rate : float
        Annual fixed coupon rate, decimal (e.g. 0.044 for 4.40%).
    r_discount : float
        Annual discount rate for PV, decimal; use the current risk-free rate.
    settlement_freq : int
        Settlements per year: 2 = semi-annual (standard IRS), 4 = quarterly.

    Returns
    -------
    float
        Modified duration in years. Positive for receive-fixed.
        Returns ``np.nan`` if inputs are degenerate.
    """
    n = int(round(maturity_years * settlement_freq))
    if n == 0:
        return np.nan
    dt = 1.0 / settlement_freq
    t = np.arange(1, n + 1, dtype=float) * dt          # settlement times (years)
    cf = np.full(n, fixed_rate * dt)                    # coupon cash flows per $1
    cf[-1] += 1.0                                        # implicit notional at maturity
    return modified_duration(cf, t, r_discount)


def swap_quarterly_cashflows(fixed_rate, r_float, maturity_years, n_quarters,
                             settlement_freq=2):
    """Net quarterly cash flows of a receive-fixed swap per $1 notional.

    Maps swap settlements onto the optimizer's quarterly grid. Positive values
    are cash received (floating > fixed); negative are cash paid (fixed > floating).
    Quarters beyond swap maturity are zero.

    Parameters
    ----------
    fixed_rate : float
        Annual fixed rate received by us (receive-fixed), decimal.
    r_float : float or array-like of length n_quarters
        Annual floating rate received. Scalar = constant (single-period use);
        array = rate per quarter (backtest use, one entry per quarter).
    maturity_years : float
        Swap tenor in years (must be a multiple of 0.25 * settlement_freq / 2 to
        land on a quarter boundary; otherwise truncated to nearest settlement).
    n_quarters : int
        Total number of quarters in the optimizer grid (len of qtr_bond_cf axis 0).
    settlement_freq : int
        Swap settlement frequency per year (2 = semi-annual, 4 = quarterly).

    Returns
    -------
    np.ndarray, shape (n_quarters,)
        Net cash flow per $1 notional for each quarter.
        Positive when fixed > float (we receive more than we pay).
    """
    dt_q       = 0.25                                   # quarter length (years)
    dt_settle  = 1.0 / settlement_freq                  # accrual period per settlement
    q_per_set  = max(1, int(round(dt_settle / dt_q)))   # quarters between settlements
    n_settle   = int(round(maturity_years * settlement_freq))

    r_float = np.asarray(r_float, dtype=float)
    scalar  = r_float.ndim == 0

    cf = np.zeros(n_quarters)
    for k in range(n_settle):
        settle_q = (k + 1) * q_per_set - 1             # 0-indexed quarter of cash flow
        if settle_q >= n_quarters:
            break
        if scalar:
            rf_k = float(r_float)
        else:
            q0 = k * q_per_set
            q1 = settle_q + 1
            rf_k = float(r_float[max(0, q0):min(len(r_float), q1)].mean())
        cf[settle_q] = (fixed_rate - rf_k) * dt_settle   # receive-fixed net: fixed − float
    return cf


def swap_fair_value(fixed_rate, r_market, maturity_years, settlement_freq=2):
    """Mark-to-market fair value of a receive-fixed swap per $1 notional.

    Approximates fair value as PV(fixed leg at r_market) minus par (= PV of the
    floating leg, which always reprices to par at the next reset). Positive when
    r_market < fixed_rate (rates have FALLEN since inception — fixed receipts are
    above market, so the swap is in-the-money for the receive-fixed party).
    Negative when r_market > fixed_rate (rates have risen — out-of-the-money).
    Used for risk reporting and IMR treatment of unwinds; NOT used directly in the
    LP objective (which is SAP book-based).

    Parameters
    ----------
    fixed_rate : float
        Annual fixed rate agreed at inception, decimal.
    r_market : float
        Current market rate for a new swap of the same remaining tenor, decimal.
    maturity_years : float
        Remaining tenor in years.
    settlement_freq : int
        Settlements per year.

    Returns
    -------
    float
        Fair value per $1 notional.  0.0 if maturity_years <= 0.
    """
    if maturity_years <= 0:
        return 0.0
    n = int(round(maturity_years * settlement_freq))
    if n == 0:
        return 0.0
    dt = 1.0 / settlement_freq
    t  = np.arange(1, n + 1, dtype=float) * dt
    cf = np.full(n, fixed_rate * dt)
    cf[-1] += 1.0                                        # implicit notional
    pv_fixed = float((cf * (1.0 + r_market) ** (-t)).sum())
    return pv_fixed - 1.0                                # minus PV(floating leg) = par


# ---------------------------------------------------------------------------
# CVaR support (Phase 2 / Step 4) — scenario generation + mark-to-market pricing
# ---------------------------------------------------------------------------
# The tail risk the FABN book actually cares about is the book-value-vs-market-
# value gap at a forced unwind (Robin: "the real risk is the book-vs-market gap
# at maturity, not exact cash-flow dedication"). To bound it with a CVaR limit we
# need (a) a set of rate+spread shock scenarios and (b) the market value of each
# bond under each scenario. Both are pure functions so they can be unit-tested and
# shared by the static optimizer and the backtest (single source of truth).

def historical_shock_scenarios(rate_hist, spread_hist, horizon_days=21, max_scenarios=250):
    """Joint (rate, spread) shock scenarios from historical levels.

    Each overlapping ``horizon_days`` change in the representative risk-free rate
    and OAS spread is one scenario, so the empirical rate/spread co-movement (and
    fat tails) is preserved without any distributional assumption.

    Parameters
    ----------
    rate_hist, spread_hist : array-like
        Time series (decimal) of a representative risk-free rate and OAS spread.
    horizon_days : int
        Change horizon in observations (e.g. ~21 ≈ one trading month).
    max_scenarios : int
        Cap on the number of scenarios (evenly subsampled if exceeded).

    Returns
    -------
    (np.ndarray, np.ndarray)
        ``d_rate``, ``d_spread`` — equal-length shock arrays (decimal).
    """
    r = np.asarray(rate_hist, dtype=float)
    s = np.asarray(spread_hist, dtype=float)
    k = max(int(horizon_days), 1)
    if len(r) <= k or len(s) <= k:
        return np.zeros(0), np.zeros(0)
    dr = r[k:] - r[:-k]
    ds = s[k:] - s[:-k]
    m = np.isfinite(dr) & np.isfinite(ds)
    dr, ds = dr[m], ds[m]
    if len(dr) > max_scenarios and len(dr) > 0:
        idx = np.linspace(0, len(dr) - 1, max_scenarios).astype(int)
        dr, ds = dr[idx], ds[idx]
    return dr, ds


def market_values_under_shocks(bond_cf, t_vec, base_yields, d_rate, d_spread):
    """Market value per $1 face of each bond under each (rate, spread) shock.

    ``MV[s, n] = sum_t cf[t, n] * (1 + y0_n + dr_s + ds_s) ** (-t)`` — each bond's
    cashflows re-discounted at its base yield plus a parallel rate shock and a
    uniform spread shock. Higher yields (rate/spread up) → lower MV, so
    ``BV - MV`` is the forced-sale loss the CVaR limit will cap.

    Parameters
    ----------
    bond_cf : (T, N) array — cashflows per $1 face, aligned to ``t_vec``.
    t_vec   : (T,) array — times in years.
    base_yields : (N,) array — current discount yield per bond (rf + spread).
    d_rate, d_spread : (S,) arrays — per-scenario shocks (decimal).

    Returns
    -------
    (S, N) np.ndarray — market value per $1 face.
    """
    cf = np.asarray(bond_cf, dtype=float)          # (T, N)
    t = np.asarray(t_vec, dtype=float)             # (T,)
    y0 = np.asarray(base_yields, dtype=float)      # (N,)
    dy = np.asarray(d_rate, dtype=float) + np.asarray(d_spread, dtype=float)  # (S,)
    yS = y0[None, :] + dy[:, None]                 # (S, N) shocked yield
    yS = np.maximum(yS, -0.99)                     # guard against (1+y)<=0
    disc = (1.0 + yS)[:, :, None] ** (-t[None, None, :])   # (S, N, T)
    return np.einsum("tn,snt->sn", cf, disc)       # (S, N)
