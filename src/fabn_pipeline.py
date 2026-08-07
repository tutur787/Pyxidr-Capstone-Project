"""
FABN SAP data pipeline — BigQuery → numpy/pandas arrays for the Gurobi solver.
"""

from __future__ import annotations

import logging
import os
import time
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pandas_datareader.data as web
from google.cloud import bigquery
from scipy.interpolate import interp1d

import fabn_finance as ff

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger(__name__)

MATURITIES_YRS = [1 / 12, 3 / 12, 6 / 12, 1, 2, 3, 5, 7, 10, 20, 30]
FRED_TICKERS = [
    "DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2",
    "DGS3", "DGS5", "DGS7", "DGS10", "DGS20", "DGS30",
]
FRED_FALLBACK = [4.40, 4.35, 4.26, 4.19, 4.27, 4.34, 4.45, 4.55, 4.66, 4.95, 4.88]

PRICE_TABLES = {
    "mid": "{project}.Mid_Price.mid_long_raw",
    "bid": "{project}.Bid_Price.bid_long_raw",
    "ask": "{project}.Ask_Price.ask_long_raw",
}

# CVaR tail-loss scenarios (Step 4): historical rate+spread shocks used to build
# the forced-sale loss coefficients that feed the solver's CVaR risk limit.
CVAR_HORIZON_DAYS = 21     # ~1 trading month change horizon
CVAR_MAX_SCEN = 250
CVAR_ALPHA = 0.95          # tail level (worst 5%)


@dataclass
class FabnPipelineParams:
    """Parameters for a FABN SAP optimization job."""

    project_id: str = "insurance-backed-securities"
    dataset: str = "Securities"
    optimization_date: pd.Timestamp = pd.Timestamp("2025-01-15")

    FABN_ISSUE: pd.Timestamp = pd.Timestamp("2022-09-06")
    FABN_MATURITY: pd.Timestamp = pd.Timestamp("2027-09-06")
    FABN_COUPON: float = 0.03205

    H: float = 500_000_000.0
    C_curr: float = 5_000_000.0
    C_min: float = 1_000_000.0
    RBC_bar: float = 3.0
    dt: float = 1.0

    gamma_w: float = 0.15
    lambda_w: float = 1.0
    eps_D: float = 0.3
    w_max: float = 0.05
    n_min: int = 20
    phi_cvar: float = 0.01

    beta_w: float = 0.0
    alpha_w: float = 0.0

    @classmethod
    def from_env(cls) -> FabnPipelineParams:
        date_str = os.environ.get("FABN_OPTIMIZATION_DATE", "2025-01-15")
        return cls(
            project_id=os.environ.get("GCP_PROJECT_ID", "insurance-backed-securities"),
            dataset=os.environ.get("BIGQUERY_DATASET", "Securities"),
            optimization_date=pd.Timestamp(date_str),
        )


def _fetch_treasury_curve(optimization_date: pd.Timestamp, n_retries: int = 3) -> pd.Series:
    last_err: Exception | None = None
    for attempt in range(1, n_retries + 1):
        try:
            raw = web.DataReader(
                FRED_TICKERS,
                "fred",
                start=optimization_date - pd.Timedelta(days=7),
                end=optimization_date + pd.Timedelta(days=7),
            )
            raw.columns = MATURITIES_YRS
            raw = raw.dropna(how="all")
            if raw.empty:
                raise ValueError("FRED returned no rows in the date window")
            day_diff = np.abs((raw.index - optimization_date).days)
            row = raw.iloc[day_diff.argmin()]
            logger.info("Treasury curve as-of %s (FRED, attempt %d)", row.name.date(), attempt)
            return row
        except Exception as exc:
            last_err = exc
            logger.warning("FRED fetch attempt %d/%d failed: %s", attempt, n_retries, type(exc).__name__)
            if attempt < n_retries:
                time.sleep(2 * attempt)
    logger.warning(
        "FRED unreachable (%s); using static fallback Treasury curve",
        type(last_err).__name__ if last_err else "unknown",
    )
    return pd.Series(FRED_FALLBACK, index=MATURITIES_YRS, name=optimization_date)


def _fetch_shock_history(optimization_date: pd.Timestamp, n_retries: int = 3) -> tuple[np.ndarray | None, tuple]:
    """~2yr history of 5yr UST (DGS5) and IG corp OAS (BAMLC0A0CM) from FRED.

    Returns ``(rate_hist, spread_hist)`` on success, or ``(None, (dr, ds))`` with
    parametric fallback raw shocks if FRED is unreachable.
    """
    last_err: Exception | None = None
    for attempt in range(1, n_retries + 1):
        try:
            raw = web.DataReader(
                ["DGS5", "BAMLC0A0CM"],
                "fred",
                start=optimization_date - pd.Timedelta(days=760),
                end=optimization_date,
            ).dropna(how="any")
            if len(raw) < CVAR_HORIZON_DAYS + 10:
                raise ValueError("insufficient FRED history")
            logger.info("CVaR shock history: %d days DGS5+IG-OAS (FRED, attempt %d)", len(raw), attempt)
            return raw["DGS5"].values / 100.0, raw["BAMLC0A0CM"].values / 100.0
        except Exception as exc:
            last_err = exc
            logger.warning("CVaR-history FRED attempt %d/%d failed: %s", attempt, n_retries, type(exc).__name__)
            if attempt < n_retries:
                time.sleep(2 * attempt)
    logger.warning(
        "FRED history unreachable (%s); using parametric fallback shocks",
        type(last_err).__name__ if last_err else "unknown",
    )
    rng = np.random.default_rng(0)
    n = 250
    dr = rng.normal(0.0, 0.0035, n)             # ~35bp monthly rate vol
    ds = 0.3 * dr + rng.normal(0.0, 0.0020, n)  # spread partly co-moves with rates
    return None, (dr, ds)


def _nearest_price_map(
    client: bigquery.Client,
    table: str,
    optimization_date: pd.Timestamp,
    *,
    cast_float: bool = False,
) -> pd.Series:
    price_expr = "SAFE_CAST(Price AS FLOAT64)" if cast_float else "Price"
    sql = f"""
    WITH ranked AS (
        SELECT CUSIP, {price_expr} AS Price, Date,
               ROW_NUMBER() OVER (
                   PARTITION BY CUSIP
                   ORDER BY ABS(DATE_DIFF(Date, DATE '{optimization_date.date()}', DAY))
               ) AS rn
        FROM `{table}`
        WHERE Date BETWEEN DATE_SUB(DATE '{optimization_date.date()}', INTERVAL 10 DAY)
                       AND DATE_ADD(DATE '{optimization_date.date()}', INTERVAL 10 DAY)
    )
    SELECT CUSIP, Price FROM ranked WHERE rn = 1
    """
    return client.query(sql).to_dataframe().set_index("CUSIP")["Price"]


def _run_validation(
    *,
    bond_cf: np.ndarray,
    qtr_bond_cf: np.ndarray,
    durs: np.ndarray,
    theta: np.ndarray,
    spread: np.ndarray,
    h_curr: np.ndarray,
    score: np.ndarray,
    qtr_fabn_cf: np.ndarray,
    N: int,
    T: int,
    Q: int,
) -> None:
    checks = [
        ("bond_cf shape", bond_cf.shape == (T, N)),
        ("qtr_bond_cf shape", qtr_bond_cf.shape == (Q, N)),
        ("durs length", len(durs) == N),
        ("theta length", len(theta) == N),
        ("spread length", len(spread) == N),
        ("h_curr length", len(h_curr) == N),
        ("score length", len(score) == N),
        ("qtr_fabn_cf length", len(qtr_fabn_cf) == Q),
        ("no NaN in durs", not np.isnan(durs).any()),
        ("no NaN in theta", not np.isnan(theta).any()),
        ("spread coverage", (~np.isnan(spread)).mean() > 0.8),
    ]
    for name, ok in checks:
        if not ok:
            logger.warning("pipeline check FAIL: %s", name)
        else:
            logger.debug("pipeline check PASS: %s", name)


def build_pipeline(
    client: bigquery.Client,
    params: FabnPipelineParams | None = None,
) -> dict[str, Any]:
    """Query BigQuery and build the pipeline dict consumed by the SAP solver."""
    p = params or FabnPipelineParams()
    optimization_date = p.optimization_date
    pid, ds = p.project_id, p.dataset

    logger.info(
        "building pipeline date=%s project=%s H=%.0f r_FABN=%.4f",
        optimization_date.date(),
        client.project,
        p.H,
        p.FABN_COUPON,
    )

    sql_fixed = f"""
    SELECT
        CUSIP,
        `Amt Out`          AS amt_out,
        Cpn                AS coupon,
        Maturity           AS maturity,
        `BBG Composite`    AS rating_sp,
        `Mac Dur _Ask_`    AS mac_dur_bbg,
        RTG_MOODY          AS rating_moodys,
        BICS_LEVEL_1_SECTOR_NAME  AS sector,
        CPN_FREQ           AS cpn_freq
    FROM `{pid}.{ds}.Agg_Fixed_Field`
    WHERE CUSIP IS NOT NULL
      AND Maturity > '{optimization_date.date()}'
    """
    fixed = client.query(sql_fixed).to_dataframe()
    fixed["maturity"] = pd.to_datetime(fixed["maturity"])
    fixed = fixed.drop_duplicates(subset="CUSIP").reset_index(drop=True)

    cusips = fixed["CUSIP"].tolist()
    n = len(cusips)

    sql_spread = f"""
    WITH ranked AS (
        SELECT
            CUSIP, Spread, Date,
            ROW_NUMBER() OVER (
                PARTITION BY CUSIP
                ORDER BY ABS(DATE_DIFF(Date, DATE '{optimization_date.date()}', DAY))
            ) AS rn
        FROM `{pid}.{ds}.Agg_Spread_Long`
        WHERE Date BETWEEN DATE_SUB(DATE '{optimization_date.date()}', INTERVAL 5 DAY)
                       AND DATE_ADD(DATE '{optimization_date.date()}', INTERVAL 5 DAY)
    )
    SELECT CUSIP, Spread, Date FROM ranked WHERE rn = 1
    """
    spread_df = client.query(sql_spread).to_dataframe()
    spread_map = spread_df.set_index("CUSIP")["Spread"]
    spread_bps = np.array([spread_map.get(c, np.nan) for c in cusips])
    spread = spread_bps / 10_000.0
    logger.info("universe N=%d spread_missing=%d", n, int(np.isnan(spread).sum()))

    sql_cf = f"""
    SELECT PaymentDate, CUSIP, Payment, Type
    FROM `{pid}.{ds}.Asset_Cashflows`
    WHERE PaymentDate > @opt_date
      AND CUSIP IN UNNEST(@cusips)
    """
    job_cf = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("opt_date", "DATE", optimization_date.date()),
            bigquery.ArrayQueryParameter("cusips", "STRING", cusips),
        ]
    )
    cf_raw = client.query(sql_cf, job_config=job_cf).to_dataframe()
    cf_raw["PaymentDate"] = pd.to_datetime(cf_raw["PaymentDate"])
    logger.info("cashflow rows loaded: %d", len(cf_raw))

    cf_agg = cf_raw.groupby(["PaymentDate", "CUSIP"])["Payment"].sum().reset_index()
    cf_pivot = cf_agg.pivot(
        index="PaymentDate", columns="CUSIP", values="Payment"
    ).fillna(0.0)
    cf_pivot = cf_pivot.reindex(columns=cusips, fill_value=0.0)

    bond_cf = cf_pivot.values / 100.0
    t_dates = cf_pivot.index
    t_vec = (t_dates - optimization_date).days.values / 365.25
    t = len(t_dates)

    cf_agg["Quarter"] = cf_agg["PaymentDate"].dt.to_period("Q")
    qtr_pivot = (
        cf_agg.groupby(["Quarter", "CUSIP"])["Payment"]
        .sum()
        .unstack(fill_value=0.0)
        .reindex(columns=cusips, fill_value=0.0)
    )
    qtr_bond_cf = qtr_pivot.values / 100.0
    qtr_idx = qtr_pivot.index
    q = len(qtr_idx)

    rf_row = _fetch_treasury_curve(optimization_date)
    valid = rf_row.dropna()
    rf_interp = interp1d(
        valid.index.astype(float),
        valid.values / 100.0,
        kind="linear",
        fill_value="extrapolate",
    )
    mat_years = ((fixed["maturity"] - optimization_date).dt.days / 365.25).values
    mat_years = np.clip(mat_years, MATURITIES_YRS[0], MATURITIES_YRS[-1])
    rf_per_bond = rf_interp(mat_years)
    yield_per_bond = rf_per_bond + spread
    disc_yield = np.where(np.isnan(yield_per_bond), rf_per_bond, yield_per_bond)
    bbg_dur = fixed["mac_dur_bbg"].values
    mod_dur_calc = ff.modified_durations(bond_cf, t_vec, disc_yield)
    durs = np.where(np.isnan(mod_dur_calc), bbg_dur, mod_dur_calc)

    theta = ff.c1_factors(fixed["rating_sp"].values, fixed["rating_moodys"].values)

    h = p.H
    h_curr = np.full(n, h / n)
    tau = np.zeros(n)
    signal = np.zeros(n)

    semi_coupon = p.FABN_COUPON / 2
    face = 100.0
    n_periods = round((p.FABN_MATURITY - p.FABN_ISSUE).days / 365.25 * 2)
    fabn_dates = pd.DatetimeIndex(
        [p.FABN_ISSUE + pd.DateOffset(months=6 * k) for k in range(1, n_periods + 1)]
    )
    fabn_cf_full = pd.DataFrame({
        "date": fabn_dates,
        "coupon": semi_coupon * face,
        "principal": [0.0] * (len(fabn_dates) - 1) + [face],
    })
    fabn_cf_full["total"] = fabn_cf_full["coupon"] + fabn_cf_full["principal"]

    fabn_future = fabn_cf_full[fabn_cf_full["date"] > optimization_date].copy()
    fabn_future["t_years"] = (fabn_future["date"] - optimization_date).dt.days / 365.25
    total_pv = fabn_future["total"].sum()
    mac_d_fabn = (fabn_future["t_years"] * fabn_future["total"]).sum() / total_pv
    r_fabn = p.FABN_COUPON
    d_fabn = mac_d_fabn / (1 + r_fabn / 2)

    fabn_future["quarter"] = fabn_future["date"].dt.to_period("Q")
    fabn_qtr_series = fabn_future.groupby("quarter")["total"].sum()
    qtr_fabn_cf = np.array([fabn_qtr_series.get(qi, 0.0) * (h / face) for qi in qtr_idx])

    score = spread + p.beta_w * signal

    _run_validation(
        bond_cf=bond_cf,
        qtr_bond_cf=qtr_bond_cf,
        durs=durs,
        theta=theta,
        spread=spread,
        h_curr=h_curr,
        score=score,
        qtr_fabn_cf=qtr_fabn_cf,
        N=n,
        T=t,
        Q=q,
    )

    sector_map = fixed.set_index("CUSIP")["sector"]
    spread_series = pd.Series(spread, index=cusips)
    sector_medians = spread_series.groupby(sector_map).transform("median")
    spread_clean = spread_series.fillna(sector_medians).fillna(spread_series.median()).values
    score_clean = spread_clean + p.beta_w * signal

    mid_map = _nearest_price_map(
        client, PRICE_TABLES["mid"].format(project=pid), optimization_date
    )
    bid_map = _nearest_price_map(
        client, PRICE_TABLES["bid"].format(project=pid), optimization_date
    )
    ask_map = _nearest_price_map(
        client, PRICE_TABLES["ask"].format(project=pid), optimization_date, cast_float=True
    )

    mid_raw = np.array([mid_map.get(c, np.nan) for c in cusips])
    bid = np.array([bid_map.get(c, np.nan) for c in cusips])
    ask = np.array([ask_map.get(c, np.nan) for c in cusips])
    price = np.where(np.isnan(mid_raw) | (mid_raw <= 0), 100.0, mid_raw)

    annual_coupon = fixed.set_index("CUSIP").loc[cusips, "coupon"].values / 100.0
    fallback_y = np.nan_to_num(rf_per_bond) + spread_clean
    book_yield_raw = ff.book_yields(bond_cf, t_vec, price)
    book_yield = np.where(np.isnan(book_yield_raw), fallback_y, book_yield_raw)
    coupon_inc, amort_inc = ff.coupon_amort_split(book_yield, annual_coupon, price)

    with np.errstate(invalid="ignore", divide="ignore"):
        tau = (ask - bid) / (2.0 * price)
    tau_valid = np.isfinite(tau) & (tau > 0)
    tau = np.where(tau_valid, tau, np.nan)
    tau = np.where(np.isnan(tau), np.nanmedian(tau), tau)

    # ── CVaR tail-loss scenarios (Step 4) ──────────────────────────────────
    # Tail risk = the book-value-vs-market-value gap at a forced unwind. Build the
    # loss distribution from historical joint moves of a benchmark Treasury rate
    # (DGS5) and the IG corporate OAS (BAMLC0A0CM) -- real data, no distributional
    # assumption -- then reprice every bond's cashflows under each shock.
    # cvar_relloss[s, i] = 1 - MV_i(shock_s)/BV_i is the per-$ forced-sale loss
    # (linear in the holdings) that feeds a Rockafellar-Uryasev CVaR limit in the
    # solver. Base yield = book_yield, so BV = zero-shock MV reproduces book value.
    hist = _fetch_shock_history(optimization_date)
    if hist[0] is None:
        cvar_d_rate, cvar_d_spread = hist[1]
    else:
        rate_hist, spread_hist = hist
        cvar_d_rate, cvar_d_spread = ff.historical_shock_scenarios(
            rate_hist, spread_hist, horizon_days=CVAR_HORIZON_DAYS, max_scenarios=CVAR_MAX_SCEN,
        )
    bv0 = ff.market_values_under_shocks(bond_cf, t_vec, book_yield, np.array([0.0]), np.array([0.0]))[0]
    mv_scen = ff.market_values_under_shocks(bond_cf, t_vec, book_yield, cvar_d_rate, cvar_d_spread)
    cvar_relloss = 1.0 - mv_scen / np.where(bv0 > 1e-9, bv0, 1.0)

    logger.info(
        "pipeline ready N=%d T=%d Q=%d spread_mean_bps=%.1f book_yield_mean=%.2f%% D_FABN=%.4f",
        n, t, q,
        spread_clean.mean() * 10_000,
        float(np.nanmean(book_yield) * 100),
        float(d_fabn),
    )

    return {
        "optimization_date": optimization_date,
        "N": n,
        "T": t,
        "Q": q,
        "CUSIPS": cusips,
        "fixed": fixed,
        "spread": spread_clean,
        "durs": durs,
        "theta": theta,
        "tau": tau,
        "signal": signal,
        "score": score_clean,
        "h_curr": h_curr,
        "price": price,
        "book_yield": book_yield,
        "coupon_inc": coupon_inc,
        "amort_inc": amort_inc,
        "bond_cf": bond_cf,
        "qtr_bond_cf": qtr_bond_cf,
        "qtr_fabn_cf": qtr_fabn_cf,
        "qtr_idx": qtr_idx,
        "t_vec": t_vec,
        "cvar_d_rate": cvar_d_rate,     # (S,) per-scenario rate shock (swap MV)
        "cvar_relloss": cvar_relloss,   # (S,N) per-$ forced-sale loss coefficients
        "cvar_alpha": CVAR_ALPHA,       # CVaR tail level (worst 5%)
        "H": h,
        "r_FABN": r_fabn,
        "D_FABN": d_fabn,
        "C_curr": p.C_curr,
        "C_min": p.C_min,
        "RBC_bar": p.RBC_bar,
        "dt": p.dt,
        "gamma_w": p.gamma_w,
        "beta_w": p.beta_w,
        "alpha_w": p.alpha_w,
        "lambda_w": p.lambda_w,
        "eps_D": p.eps_D,
        "phi_cvar": p.phi_cvar,
    }
