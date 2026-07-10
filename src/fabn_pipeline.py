"""
FABN optimizer data pipeline — BigQuery → numpy/pandas arrays.

Ported from Optimization/FABN_Data_Pipeline.ipynb.
"""

from __future__ import annotations

import logging
import os
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandas_datareader.data as web
from google.cloud import bigquery
from scipy.interpolate import interp1d

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


@dataclass
class FabnPipelineParams:
    """Parameters for building the FABN pipeline dict."""

    project_id: str = "insurance-backed-securities"
    dataset: str = "Securities"
    optimization_date: pd.Timestamp = pd.Timestamp("2025-01-15")

    FABN_ISSUE: pd.Timestamp = pd.Timestamp("2022-09-06")
    FABN_MATURITY: pd.Timestamp = pd.Timestamp("2027-09-06")
    FABN_COUPON: float = 0.03205

    H: float = 500_000_000.0
    C_curr: float = 50_000_000.0
    C_min: float = 1_000_000.0
    RBC_bar: float = 1.5
    dt: float = 1.0

    gamma_w: float = 1.0
    beta_w: float = 0.0
    alpha_w: float = 0.0
    lambda_w: float = 1.0
    eps_D: float = 0.5

    @classmethod
    def from_env(cls) -> FabnPipelineParams:
        date_str = os.environ.get("FABN_OPTIMIZATION_DATE", "2025-01-15")
        return cls(
            project_id=os.environ.get("GCP_PROJECT_ID", "insurance-backed-securities"),
            dataset=os.environ.get("BIGQUERY_DATASET", "Securities"),
            optimization_date=pd.Timestamp(date_str),
        )


C1_SP = {
    "AAA": 0.00158,
    "AA+": 0.00271,
    "AA": 0.00419,
    "AA-": 0.00523,
    "A+": 0.00657,
    "A": 0.00816,
    "A-": 0.01016,
    "BBB+": 0.01261,
    "BBB": 0.01523,
    "BBB-": 0.02168,
    "BB+": 0.03151,
    "BB": 0.04537,
    "BB-": 0.06017,
    "B+": 0.07386,
    "B": 0.09535,
    "B-": 0.12428,
    "CCC+": 0.16942,
    "CCC": 0.23798,
    "CCC-": 0.32975,
    "D": 0.30000,
}

C1_MOODYS = {
    "Aaa": 0.00158,
    "Aa1": 0.00271,
    "Aa2": 0.00419,
    "Aa3": 0.00523,
    "A1": 0.00657,
    "A2": 0.00816,
    "A3": 0.01016,
    "Baa1": 0.01261,
    "Baa2": 0.01523,
    "Baa3": 0.02168,
    "Ba1": 0.03151,
    "Ba2": 0.04537,
    "Ba3": 0.06017,
    "B1": 0.07386,
    "B2": 0.09535,
    "B3": 0.12428,
    "Caa1": 0.16942,
    "Caa2": 0.23798,
    "Caa3": 0.32975,
    "Ca": 0.30000,
    "C": 0.30000,
}

DEFAULT_C1 = C1_SP["BBB"]

MATURITIES_YRS = [1 / 12, 3 / 12, 6 / 12, 1, 2, 3, 5, 7, 10, 20, 30]
FRED_TICKERS = [
    "DGS1MO",
    "DGS3MO",
    "DGS6MO",
    "DGS1",
    "DGS2",
    "DGS3",
    "DGS5",
    "DGS7",
    "DGS10",
    "DGS20",
    "DGS30",
]


def lookup_c1(sp_rating, moodys_rating) -> float:
    if pd.notna(sp_rating) and str(sp_rating).strip() in C1_SP:
        return C1_SP[str(sp_rating).strip()]
    if pd.notna(moodys_rating) and str(moodys_rating).strip() in C1_MOODYS:
        return C1_MOODYS[str(moodys_rating).strip()]
    return DEFAULT_C1


def mac_dur_bond(cf_col: np.ndarray, t_vec: np.ndarray, y: float) -> float:
    if y <= -1 or cf_col.sum() == 0:
        return np.nan
    discount = (1 + y) ** (-t_vec)
    pv_cf = cf_col * discount
    total_pv = pv_cf.sum()
    if total_pv == 0:
        return np.nan
    return float((t_vec * pv_cf).sum() / total_pv)


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
    all_pass = True
    for name, ok in checks:
        if not ok:
            all_pass = False
            logger.warning("pipeline check FAIL: %s", name)
        else:
            logger.debug("pipeline check PASS: %s", name)
    if all_pass:
        logger.info("pipeline validation: all checks passed")
    else:
        logger.warning(
            "pipeline validation: some checks failed — review before optimizing"
        )


def build_pipeline(
    client: bigquery.Client,
    params: FabnPipelineParams | None = None,
) -> dict:
    """
    Query BigQuery, build cashflow/duration/C1 inputs, return the pipeline dict
    consumed by the Gurobi model.
    """
    p = params or FabnPipelineParams()
    optimization_date = p.optimization_date
    pid, ds = p.project_id, p.dataset

    logger.info(
        "optimization_date=%s FABN_issue=%s FABN_maturity=%s H=%s r_FABN=%.4f",
        optimization_date.date(),
        p.FABN_ISSUE.date(),
        p.FABN_MATURITY.date(),
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

    CUSIPS = fixed["CUSIP"].tolist()
    N = len(CUSIPS)

    sql_spread = f"""
    WITH ranked AS (
        SELECT
            CUSIP,
            Spread,
            Date,
            ROW_NUMBER() OVER (
                PARTITION BY CUSIP
                ORDER BY ABS(DATE_DIFF(Date, DATE '{optimization_date.date()}', DAY))
            ) AS rn
        FROM `{pid}.{ds}.Agg_Spread_Long`
        WHERE Date BETWEEN DATE_SUB(DATE '{optimization_date.date()}', INTERVAL 5 DAY)
                       AND DATE_ADD(DATE '{optimization_date.date()}', INTERVAL 5 DAY)
    )
    SELECT CUSIP, Spread, Date
    FROM ranked
    WHERE rn = 1
    """
    spread_df = client.query(sql_spread).to_dataframe()
    spread_map = spread_df.set_index("CUSIP")["Spread"]
    spread_bps = np.array([spread_map.get(c, np.nan) for c in CUSIPS])
    spread = spread_bps / 10_000.0
    missing_spread = np.isnan(spread).sum()
    logger.info(
        "bigquery project=%s universe_N=%d spread_missing=%d",
        client.project,
        N,
        int(missing_spread),
    )

    sql_cf = f"""
    SELECT PaymentDate, CUSIP, Payment, Type
    FROM `{pid}.{ds}.Asset_Cashflows`
    WHERE PaymentDate > @opt_date
      AND CUSIP IN UNNEST(@cusips)
    """
    job_cf = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("opt_date", "DATE", optimization_date.date()),
            bigquery.ArrayQueryParameter("cusips", "STRING", CUSIPS),
        ]
    )
    cf_raw = client.query(sql_cf, job_config=job_cf).to_dataframe()
    cf_raw["PaymentDate"] = pd.to_datetime(cf_raw["PaymentDate"])
    logger.info("cashflow rows loaded: %d", len(cf_raw))

    cf_agg = (
        cf_raw.groupby(["PaymentDate", "CUSIP"])["Payment"].sum().reset_index()
    )
    cf_pivot = cf_agg.pivot(
        index="PaymentDate", columns="CUSIP", values="Payment"
    ).fillna(0.0)
    cf_pivot = cf_pivot.reindex(columns=CUSIPS, fill_value=0.0)

    bond_cf = cf_pivot.values
    t_dates = cf_pivot.index
    t_vec = (t_dates - optimization_date).days.values / 365.25
    T = len(t_dates)
    logger.info("bond_cf shape=%s T=%d N=%d", bond_cf.shape, T, N)

    cf_agg["Quarter"] = cf_agg["PaymentDate"].dt.to_period("Q")
    qtr_pivot = (
        cf_agg.groupby(["Quarter", "CUSIP"])["Payment"]
        .sum()
        .unstack(fill_value=0.0)
        .reindex(columns=CUSIPS, fill_value=0.0)
    )
    qtr_bond_cf = qtr_pivot.values
    qtr_idx = qtr_pivot.index
    Q = len(qtr_idx)
    logger.info("qtr_bond_cf shape=%s Q=%d N=%d", qtr_bond_cf.shape, Q, N)

    rf_raw = web.DataReader(
        FRED_TICKERS,
        "fred",
        start=optimization_date - pd.Timedelta(days=7),
        end=optimization_date + pd.Timedelta(days=7),
    )
    rf_raw.columns = MATURITIES_YRS
    rf_clean = rf_raw.dropna(how="all")
    day_diff = np.abs((rf_clean.index - optimization_date).days)
    rf_row = rf_clean.iloc[day_diff.argmin()]
    logger.info("treasury_curve_asof=%s", rf_row.name.date())

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

    mac_dur_calc = np.array(
        [
            mac_dur_bond(
                bond_cf[:, i],
                t_vec,
                yield_per_bond[i]
                if not np.isnan(yield_per_bond[i])
                else rf_per_bond[i],
            )
            for i in range(N)
        ]
    )
    mod_dur_calc = np.where(
        ~np.isnan(mac_dur_calc),
        mac_dur_calc
        / (1 + np.where(np.isnan(yield_per_bond), rf_per_bond, yield_per_bond)),
        np.nan,
    )
    bbg_dur = fixed["mac_dur_bbg"].values
    durs = np.where(np.isnan(mod_dur_calc), bbg_dur, mod_dur_calc)

    theta = np.array(
        [
            lookup_c1(
                fixed.loc[fixed["CUSIP"] == c, "rating_sp"].values[0],
                fixed.loc[fixed["CUSIP"] == c, "rating_moodys"].values[0],
            )
            for c in CUSIPS
        ]
    )

    H = p.H
    h_curr = np.full(N, H / N)
    tau = np.zeros(N)
    signal = np.zeros(N)

    semi_coupon = p.FABN_COUPON / 2
    face = 100.0
    fabn_dates = [
        p.FABN_ISSUE + pd.DateOffset(months=6 * k) for k in range(1, 11)
    ]
    fabn_dates = pd.DatetimeIndex(fabn_dates)
    fabn_cf_full = pd.DataFrame(
        {
            "date": fabn_dates,
            "coupon": semi_coupon * face,
            "principal": [0.0] * (len(fabn_dates) - 1) + [face],
        }
    )
    fabn_cf_full["total"] = fabn_cf_full["coupon"] + fabn_cf_full["principal"]

    fabn_future = fabn_cf_full[fabn_cf_full["date"] > optimization_date].copy()
    fabn_future["t_years"] = (
        fabn_future["date"] - optimization_date
    ).dt.days / 365.25
    total_pv = fabn_future["total"].sum()
    mac_D_FABN = (fabn_future["t_years"] * fabn_future["total"]).sum() / total_pv
    r_FABN = p.FABN_COUPON
    D_FABN = mac_D_FABN / (1 + r_FABN / 2)

    fabn_future["quarter"] = fabn_future["date"].dt.to_period("Q")
    fabn_qtr_series = fabn_future.groupby("quarter")["total"].sum()
    qtr_fabn_cf = np.array(
        [fabn_qtr_series.get(q, 0.0) * (H / face) for q in qtr_idx]
    )

    beta_w = p.beta_w
    score = spread + beta_w * signal

    _run_validation(
        bond_cf=bond_cf,
        qtr_bond_cf=qtr_bond_cf,
        durs=durs,
        theta=theta,
        spread=spread,
        h_curr=h_curr,
        score=score,
        qtr_fabn_cf=qtr_fabn_cf,
        N=N,
        T=T,
        Q=Q,
    )

    sector_map = fixed.set_index("CUSIP")["sector"]
    spread_series = pd.Series(spread, index=CUSIPS)
    sector_medians = spread_series.groupby(sector_map).transform("median")
    spread_clean = spread_series.fillna(sector_medians).fillna(
        spread_series.median()
    ).values
    score_clean = spread_clean + beta_w * signal

    n_filled = int(np.isnan(spread).sum())
    logger.info("spread NaN filled (sector median): %d", n_filled)

    pipeline = {
        "optimization_date": optimization_date,
        "N": N,
        "T": T,
        "Q": Q,
        "CUSIPS": CUSIPS,
        "fixed": fixed,
        "spread": spread_clean,
        "durs": durs,
        "theta": theta,
        "tau": tau,
        "signal": signal,
        "score": score_clean,
        "h_curr": h_curr,
        "bond_cf": bond_cf,
        "qtr_bond_cf": qtr_bond_cf,
        "qtr_fabn_cf": qtr_fabn_cf,
        "qtr_idx": qtr_idx,
        "t_vec": t_vec,
        "H": H,
        "r_FABN": r_FABN,
        "D_FABN": D_FABN,
        "C_curr": p.C_curr,
        "C_min": p.C_min,
        "RBC_bar": p.RBC_bar,
        "dt": p.dt,
        "gamma_w": p.gamma_w,
        "beta_w": p.beta_w,
        "alpha_w": p.alpha_w,
        "lambda_w": p.lambda_w,
        "eps_D": p.eps_D,
        "FABN_ISSUE": p.FABN_ISSUE,
        "FABN_MATURITY": p.FABN_MATURITY,
        "FABN_COUPON": p.FABN_COUPON,
    }

    logger.info(
        "pipeline ready: N=%d T=%d Q=%d spread_mean_bps=%.1f dur_mean=%.4f "
        "theta_mean_pct=%.4f D_FABN=%.6f H_MUSD=%.3f",
        N,
        T,
        Q,
        spread_clean.mean() * 10000,
        float(durs.mean()),
        float(theta.mean() * 100),
        float(D_FABN),
        H / 1e6,
    )

    return pipeline
