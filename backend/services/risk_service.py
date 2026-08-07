"""
risk_service — historical-simulation CVaR for the FABN portfolio, plus a
volatility-threshold trading signal. Both are driven off the same underlying
data: the daily FABN YTM series already pulled by fabn_market_service (no
separate data source needed), clipped to history on or before the target date
(no look-ahead).

── CVaR (historical simulation, duration-mapped) ──────────────────────────────
  1. Day-over-day FABN YTM changes (delta_y, decimal fraction) form the
     historical shock distribution. FABN YTM already embeds both rate and
     credit-spread moves, so this single factor captures total return risk.
  2. Each day's hypothetical portfolio return: r_i = -duration * delta_y_i
     (first-order duration shock — convexity and per-bond idiosyncratic spread
     risk aren't modeled; only the aggregate FABN series has enough history).
  3. VaR(confidence) = the loss at the (1 - confidence) percentile.
     CVaR(confidence) = the expected loss conditional on being in that tail.
  4. Scaled from a 1-day to a 1-quarter (HORIZON_DAYS) horizon via the
     standard sqrt-time rule — a standard simplification (assumes i.i.d.
     daily changes; real yield changes have some autocorrelation).

── Trading signal (volatility threshold reoptimization trigger) ───────────────
  Implements the "Strategy 1" spec from the Size-of-Prize work
  (`Optimization/Size of the Prize/Results_Summary_Arthur.md`,
  `FABN_Size_of_Prize_Arthur.ipynb` cell 7): the perfect-foresight LP is
  "volatility-triggered, not volatility-proportional" — it barely trades in
  normal regimes and fires only when yield dislocations exceed a threshold.

    sigma_t  = 21-day rolling std of the cross-sectional median book yield
               across the full N-bond universe, i.e. std({median_i(y_i,
               t-k)) : k = 0..20}) — computed on the SAME per-bond book-yield
               panel (`Y`, shape [dates, bonds]) the notebook used, loaded
               from `Optimization/Size of the Prize/prize_panels.npz` (a
               precomputed BigQuery snapshot spanning the app's full backtest
               window, 2024-03-01 to 2026-02-26). This is the actual
               cross-sectional dispersion measure from the spec, not a
               single-benchmark proxy.
    threshold = the `percentile`-th percentile of sigma_t over the trailing
               252 days (default 75th, matching the notebook's
               `quantile(0.75)` cutoff — see cell 7, "TRADING INTENSITY OVER
               TIME"). trigger = sigma_t > threshold.

  We use a percentile (rank-based) cutoff rather than a multiplicative
  median*(1+kappa) rule: a percentile always selects exactly the same
  fraction of historical days regardless of the distribution's shape, so its
  selectivity is stable across calm and choppy regimes. A multiplicative
  deviation-from-median rule doesn't have this property — empirically its
  actual percentile rank drifted between ~75th and ~97th across different
  historical windows in this data, i.e. the same multiplier meant very
  different things in different vol regimes. The percentile cutoff is the
  statistically sound choice; `percentile` is still tunable (e.g. 90 for a
  stricter, rarer trigger) but always means the same thing regardless of
  when it's evaluated.

  This is exposed purely as an informational signal (banner + chart) — it
  does NOT gate the optimizer call. The optimizer still re-solves on every
  date change; the signal only tells the user whether the current regime
  historically justified active trading.

Below MIN_OBS historical days, both risk models are flagged `degraded`.
"""

from __future__ import annotations

import math
import os

from services import fabn_market_service

MIN_OBS       = 60    # ~3 months of trading days
HORIZON_DAYS  = 63    # ~1 quarter of trading days
N_HIST_BINS   = 18
VOL_WINDOW    = 21     # trading days — matches the Size-of-Prize notebook
LOOKBACK_DAYS = 252    # ~1 trading year, for the self-calibrating baseline
DEFAULT_PERCENTILE = 75.0  # top-quartile cutoff, matches the notebook's quantile(0.75)

PROJECT_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PRIZE_PANELS_PATH = os.path.join(PROJECT_ROOT, 'Optimization', 'Size of the Prize', 'prize_panels.npz')


def _fabn_ytm_series(date: str) -> list[float]:
    history = [h for h in fabn_market_service.get_history() if h["date"] <= date]
    return [h["fabn_ytm"] / 100.0 for h in history]  # fabn_ytm is in percent (e.g. 5.45)


def compute_cvar(date: str, duration: float, confidence: float = 0.95) -> dict:
    ytms  = _fabn_ytm_series(date)
    n_obs = len(ytms)

    if n_obs < 3:
        return {
            "cvar_pct":   None,
            "var_pct":    None,
            "n_obs":      n_obs,
            "degraded":   True,
            "method":     "insufficient_history",
            "histogram":  [],
        }

    deltas = [ytms[i] - ytms[i - 1] for i in range(1, n_obs)]

    # Quarterly-scaled simulated returns (sqrt-time rule), worst-first.
    scale       = math.sqrt(HORIZON_DAYS)
    sim_returns = sorted(-duration * d * scale for d in deltas)

    tail_n = max(1, math.ceil((1 - confidence) * len(sim_returns)))
    tail   = sim_returns[:tail_n]
    var_   = -tail[-1]                 # loss at the percentile boundary
    cvar   = -sum(tail) / len(tail)    # expected loss within the tail

    # Histogram of the full simulated-return distribution, for charting.
    lo, hi = min(sim_returns), max(sim_returns)
    span   = (hi - lo) or 1e-6
    width  = span / N_HIST_BINS
    counts = [0] * N_HIST_BINS
    for r in sim_returns:
        idx = min(int((r - lo) / width), N_HIST_BINS - 1)
        counts[idx] += 1
    histogram = [
        {
            "bin_mid_pct": round((lo + width * (i + 0.5)) * 100, 3),
            "count":       counts[i],
        }
        for i in range(N_HIST_BINS)
    ]

    return {
        "cvar_pct":  round(cvar * 100, 3),
        "var_pct":   round(var_ * 100, 3),
        "n_obs":     n_obs,
        "degraded":  n_obs < MIN_OBS,
        "method":    "historical_simulation_duration_mapped_quarterly",
        "histogram": histogram,
    }


_prize_panel_cache: dict | None = None
_prize_panel_missing = False  # sticky: avoid re-stat'ing a known-absent file on every call


def _load_prize_panel() -> dict | None:
    """Cross-sectional book-yield panel (Y: [dates, bonds]) from the Size-of-Prize
    precompute — the exact data source `Results_Summary_Arthur.md` cell 7 used for
    sigma_t. Loaded once and cached; it's a static BigQuery snapshot, not re-pulled
    live, but it spans the app's full backtest window (2024-03-01 to 2026-02-26).

    Returns ``None`` if the panel file isn't present — it's git-ignored, proprietary
    pricing data generated by running the Size-of-Prize notebook locally (see
    `Optimization/CLAUDE.md`), not something every environment has. The trading
    signal degrades gracefully in that case rather than raising (matches
    ``compute_cvar``'s own degraded-on-insufficient-data convention above)."""
    global _prize_panel_cache, _prize_panel_missing
    if _prize_panel_missing:
        return None
    if _prize_panel_cache is None:
        import numpy as np
        import pandas as pd

        try:
            d = np.load(PRIZE_PANELS_PATH, allow_pickle=True)
        except FileNotFoundError:
            _prize_panel_missing = True
            return None
        dates = pd.to_datetime(d["BT_DATES_ns"]).strftime("%Y-%m-%d").tolist()
        med_yield_pct = np.nanmedian(d["Y"], axis=1) * 100.0  # decimal -> percent
        _prize_panel_cache = {"dates": dates, "med_yield_pct": med_yield_pct}
    return _prize_panel_cache


def compute_trading_signal(
    date: str,
    short_window: int = VOL_WINDOW,
    lookback_days: int = LOOKBACK_DAYS,
    percentile: float = DEFAULT_PERCENTILE,
) -> dict:
    import numpy as np

    panel = _load_prize_panel()
    if panel is None:
        return {
            "series":            [],
            "current_vol_bps":   None,
            "median_vol_bps":    None,
            "threshold_vol_bps": None,
            "ratio_to_median":   None,
            "percentile":        percentile,
            "worth_trading":     None,
            "n_obs":             0,
            "lookback_n":        0,
            "degraded":          True,
        }
    dates, med_yield_pct = panel["dates"], panel["med_yield_pct"]

    # Clip to history on/before the target date — no look-ahead.
    n_obs = sum(1 for d in dates if d <= date)

    if n_obs < short_window + 5:
        return {
            "series":            [],
            "current_vol_bps":   None,
            "median_vol_bps":    None,
            "threshold_vol_bps": None,
            "ratio_to_median":   None,
            "percentile":        percentile,
            "worth_trading":     None,
            "n_obs":             n_obs,
            "lookback_n":        0,
            "degraded":          True,
        }

    ytms = med_yield_pct[:n_obs]

    # sigma_t: 21-day rolling std (ddof=1) of the cross-sectional median yield, in bps.
    roll_vol = [
        float(np.std(ytms[i - short_window + 1 : i + 1], ddof=1)) * 100  # % -> bps
        for i in range(short_window - 1, n_obs)
    ]
    roll_dates = dates[short_window - 1 : n_obs]

    current_vol = roll_vol[-1]
    lookback_n  = min(lookback_days, len(roll_vol))
    trailing    = roll_vol[-lookback_n:]

    # threshold: the `percentile`-th percentile of sigma_t over the trailing year —
    # a rank-based cutoff, so it always selects the same fraction of days regardless
    # of the distribution's shape (unlike a multiplicative median*(1+kappa) rule).
    median_vol = float(np.median(trailing))
    threshold  = float(np.percentile(trailing, percentile))
    ratio      = current_vol / median_vol if median_vol > 0 else None

    series = [{"date": d, "vol_21_bps": round(v, 2)} for d, v in zip(roll_dates, roll_vol)]

    return {
        "series":            series,
        "current_vol_bps":   round(current_vol, 2),
        "median_vol_bps":    round(median_vol, 2),
        "threshold_vol_bps": round(threshold, 2),
        "ratio_to_median":   round(ratio, 3) if ratio is not None else None,
        "percentile":        percentile,
        "worth_trading":     bool(current_vol > threshold),
        "n_obs":             n_obs,
        "lookback_n":        lookback_n,
        "degraded":          lookback_n < MIN_OBS,
    }
