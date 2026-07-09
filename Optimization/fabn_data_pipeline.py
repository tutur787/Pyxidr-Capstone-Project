"""fabn_data_pipeline — Data pipeline for the FABN SAP optimizer.

Builds every input array the optimizer needs from three BigQuery tables:
- Asset_Cashflows  -- cashflow schedule per CUSIP
- Agg_Spread_Long  -- daily spread per CUSIP
- Agg_Fixed_Field  -- static bond attributes

Outputs are stored in ``pipeline`` dict (see Section 10).

Can be run standalone or via runpy::

    runpy.run_path(path, init_globals={"optimization_date": pd.Timestamp("2025-01-15")})

When invoked via runpy the caller's ``optimization_date`` value takes precedence.
"""

import sys
import os
import datetime
import time

# Allow `import fabn_finance as ff` when Optimization/ is not on sys.path
# (e.g. when invoked via runpy from the backend service).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.cloud import bigquery
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import fabn_finance as ff

PROJECT_ID = "insurance-backed-securities"
DATASET    = "Securities"

client = bigquery.Client(project=PROJECT_ID)
# print(f"Connected: {client.project}")

# =============================================================================
# 1 — Parameters
# =============================================================================

# optimization_date may be injected by the caller via runpy init_globals.
# Fall back to the notebook default when running standalone.
try:
    optimization_date
except NameError:
    optimization_date = pd.Timestamp("2025-01-15")

FABN_ISSUE    = pd.Timestamp("2022-09-06")
FABN_MATURITY = pd.Timestamp("2027-09-06")
FABN_COUPON   = 0.03205   # 3.205% annual, paid semi-annually

H       = 500_000_000.0   # total capital budget ($)
r_FABN  = FABN_COUPON     # funding agreement crediting rate (annual, decimal)
C_curr  = 5_000_000.0     # current regulatory capital ($)
C_min   = 1_000_000.0     # minimum required capital ($)
RBC_bar = 3.0             # minimum RBC solvency ratio
dt      = 1.0             # time scaling factor (1 = annual)

gamma_w  = 0.15  # γ : weight on capital cost (C1 + C3)
beta_w   = 0.0   # β : weight on signal  (0 until signal is ready)
alpha_w  = 0.0   # α : C3 duration mismatch scaling (0 until C3 is active)
lambda_w = 0.05  # λ : CF shortfall penalty weight
eps_D    = 0.3   # duration tolerance band (years)

# print(f"Optimization date  : {optimization_date.date()}")
# print(f"FABN issue/maturity: {FABN_ISSUE.date()} → {FABN_MATURITY.date()}")
# print(f"Budget H           : ${H:,.0f}")
# print(f"r_FABN             : {r_FABN*100:.3f}%")

# =============================================================================
# 2 — Bond Universe from Agg_Fixed_Field
# =============================================================================
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
FROM `{PROJECT_ID}.{DATASET}.Agg_Fixed_Field`
WHERE CUSIP IS NOT NULL
  AND Maturity > '{optimization_date.date()}'
"""

fixed = client.query(sql_fixed).to_dataframe()
fixed["maturity"] = pd.to_datetime(fixed["maturity"])
fixed = fixed.drop_duplicates(subset="CUSIP").reset_index(drop=True)

CUSIPS    = fixed["CUSIP"].tolist()
N         = len(CUSIPS)
cusip_idx = {c: i for i, c in enumerate(CUSIPS)}

# print(f"Universe size N = {N} bonds")
# print(fixed.head())

# =============================================================================
# 3 — Spreads from Agg_Spread_Long
# =============================================================================
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
    FROM `{PROJECT_ID}.{DATASET}.Agg_Spread_Long`
    WHERE Date BETWEEN DATE_SUB(DATE '{optimization_date.date()}', INTERVAL 5 DAY)
                   AND DATE_ADD(DATE '{optimization_date.date()}', INTERVAL 5 DAY)
)
SELECT CUSIP, Spread, Date
FROM ranked
WHERE rn = 1
"""

spread_df  = client.query(sql_spread).to_dataframe()
spread_map = spread_df.set_index("CUSIP")["Spread"]

spread_bps = np.array([spread_map.get(c, np.nan) for c in CUSIPS])
spread     = spread_bps / 10_000.0

missing_spread = np.isnan(spread).sum()
# print(f"Spread coverage : {N - missing_spread}/{N} bonds  ({missing_spread} missing)")
# print(f"Spread range    : {spread_bps[~np.isnan(spread_bps)].min():.1f} – "
      # f"{spread_bps[~np.isnan(spread_bps)].max():.1f} bps")

# =============================================================================
# 4 — Cashflow Matrix from Asset_Cashflows
# =============================================================================
sql_cf = f"""
SELECT PaymentDate, CUSIP, Payment, Type
FROM `{PROJECT_ID}.{DATASET}.Asset_Cashflows`
WHERE PaymentDate > '{optimization_date.date()}'
  AND CUSIP IN UNNEST({CUSIPS})
"""

cf_raw = client.query(sql_cf).to_dataframe()
cf_raw["PaymentDate"] = pd.to_datetime(cf_raw["PaymentDate"])

# print(f"Cashflow rows loaded : {len(cf_raw):,}")
# print(f"Date range           : {cf_raw['PaymentDate'].min().date()} → {cf_raw['PaymentDate'].max().date()}")

# Daily cashflow matrix (T × N)
cf_agg = (
    cf_raw
    .groupby(["PaymentDate", "CUSIP"])["Payment"]
    .sum()
    .reset_index()
)

cf_pivot = cf_agg.pivot(index="PaymentDate", columns="CUSIP", values="Payment").fillna(0.0)
cf_pivot = cf_pivot.reindex(columns=CUSIPS, fill_value=0.0)

bond_cf = cf_pivot.values
t_dates = cf_pivot.index
t_vec   = (t_dates - optimization_date).days.values / 365.25
T       = len(t_dates)

# print(f"bond_cf shape : {bond_cf.shape}  (T={T} payment dates × N={N} bonds)")

# Quarterly cashflow matrix (Q × N)
cf_agg["Quarter"] = cf_agg["PaymentDate"].dt.to_period("Q")

qtr_pivot = (
    cf_agg
    .groupby(["Quarter", "CUSIP"])["Payment"]
    .sum()
    .unstack(fill_value=0.0)
    .reindex(columns=CUSIPS, fill_value=0.0)
)

qtr_bond_cf = qtr_pivot.values
qtr_idx     = qtr_pivot.index
Q           = len(qtr_idx)
fabn_q      = int(qtr_idx.get_loc(pd.Period(FABN_MATURITY, freq="Q")) + 1)  # quarters through FABN maturity (reinvestment horizon)

# print(f"qtr_bond_cf shape : {qtr_bond_cf.shape}  (Q={Q} quarters × N={N} bonds)")

# Convert from per-$100 face to per-$1 face
bond_cf     = bond_cf     / 100.0
qtr_bond_cf = qtr_bond_cf / 100.0

# print(f"Quarter range     : {qtr_idx[0]} → {qtr_idx[-1]}")

# =============================================================================
# 5 — Duration
# =============================================================================
import pandas_datareader.data as web
from scipy.interpolate import interp1d

MATURITIES_YRS = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 20, 30]
FRED_TICKERS   = ["DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2",
                   "DGS3", "DGS5", "DGS7", "DGS10", "DGS20", "DGS30"]

# Static fallback curve (%), used only if FRED is unreachable.
# Source: U.S. Treasury par yields near 2025-01-15.
FRED_FALLBACK = [4.40, 4.35, 4.26, 4.19, 4.27, 4.34, 4.45, 4.55, 4.66, 4.95, 4.88]


def _fetch_treasury_curve(n_retries=3):
    """Fetch Treasury curve from FRED with retries; fall back to static curve."""
    last_err = None
    for attempt in range(1, n_retries + 1):
        try:
            raw = web.DataReader(
                FRED_TICKERS, "fred",
                start=optimization_date - pd.Timedelta(days=7),
                end=optimization_date + pd.Timedelta(days=7),
            )
            raw.columns = MATURITIES_YRS
            raw = raw.dropna(how="all")
            if raw.empty:
                raise ValueError("FRED returned no rows in the date window")
            day_diff = np.abs((raw.index - optimization_date).days)
            row = raw.iloc[day_diff.argmin()]
            # print(f"Treasury curve date used : {row.name.date()}  (FRED, attempt {attempt})")
            return row
        except Exception as e:
            last_err = e
            # print(f"  FRED fetch attempt {attempt}/{n_retries} failed: {type(e).__name__}")
            if attempt < n_retries:
                time.sleep(2 * attempt)
    # print(f"  WARNING: FRED unreachable ({type(last_err).__name__}). "
          # f"Using STATIC fallback Treasury curve (~2025-01-15).")
    return pd.Series(FRED_FALLBACK, index=MATURITIES_YRS, name=optimization_date)


rf_row = _fetch_treasury_curve()
# print(rf_row.rename(lambda t: f"{t:.3f}yr").to_string())

valid     = rf_row.dropna()
rf_interp = interp1d(
    valid.index.astype(float),
    valid.values / 100.0,
    kind="linear",
    fill_value="extrapolate",
)

mat_years = ((fixed["maturity"] - optimization_date).dt.days / 365.25).values
mat_years = np.clip(mat_years, MATURITIES_YRS[0], MATURITIES_YRS[-1])

rf_per_bond    = rf_interp(mat_years)
yield_per_bond = rf_per_bond + spread

disc_yield   = np.where(np.isnan(yield_per_bond), rf_per_bond, yield_per_bond)
bbg_dur      = fixed["mac_dur_bbg"].values
mod_dur_calc = ff.modified_durations(bond_cf, t_vec, disc_yield)
durs         = np.where(np.isnan(mod_dur_calc), bbg_dur, mod_dur_calc)

n_computed = int((~np.isnan(mod_dur_calc)).sum())
n_fallback = int(np.isnan(mod_dur_calc).sum())
# print(f"\nDuration computed from cashflows : {n_computed}")
# print(f"Duration from BBG fallback       : {n_fallback}")
# print(f"Duration range                   : {np.nanmin(durs):.2f} – {np.nanmax(durs):.2f} yrs")
# print(f"Mean bond yield used             : {np.nanmean(yield_per_bond)*100:.3f}%")

# =============================================================================
# 6 — C1 Capital Factor (theta)
# =============================================================================
theta = ff.c1_factors(fixed["rating_sp"].values, fixed["rating_moodys"].values)

n_sp = int(fixed["rating_sp"].apply(lambda r: ff._clean_rating(r) in ff.C1_SP).sum())
n_default = int(sum(
    ff._clean_rating(s) not in ff.C1_SP and ff._clean_rating(m) not in ff.C1_MOODYS
    for s, m in zip(fixed["rating_sp"].values, fixed["rating_moodys"].values)
))

# print(f"theta range : {theta.min():.5f} – {theta.max():.5f}")
# print(f"Mean C1     : {theta.mean():.5f}  ({theta.mean()*100:.3f}%)")
# print(f"Rating source : {n_sp} S&P, {theta.size - n_sp - n_default} Moody's fallback, "
      # f"{n_default} BBB default")

# =============================================================================
# 7 — Current Allocations, Signal, Transaction Costs
# =============================================================================
# Equal-weight current allocation (placeholder until real portfolio is loaded)
h_curr = np.full(N, H / N)

# Deferred — replaced in Section 9.5
tau    = np.zeros(N)
signal = np.zeros(N)

# print(f"h_curr (equal-weight) : ${H/N:,.2f} per bond")

# =============================================================================
# 8 — FABN Liability Cashflow Schedule & D_FABN
# =============================================================================
semi_coupon = FABN_COUPON / 2
face        = 100.0

n_periods  = round((FABN_MATURITY - FABN_ISSUE).days / 365.25 * 2)
fabn_dates = pd.DatetimeIndex(
    [FABN_ISSUE + pd.DateOffset(months=6 * k) for k in range(1, n_periods + 1)]
)

fabn_cf_full = pd.DataFrame({
    "date":      fabn_dates,
    "coupon":    semi_coupon * face,
    "principal": [0.0] * (len(fabn_dates) - 1) + [face],
})
fabn_cf_full["total"] = fabn_cf_full["coupon"] + fabn_cf_full["principal"]

# print("Full FABN schedule (per 100 face):")
# print(fabn_cf_full.to_string(index=False))

fabn_future = fabn_cf_full[fabn_cf_full["date"] > optimization_date].copy()
fabn_future["t_years"] = (fabn_future["date"] - optimization_date).dt.days / 365.25

# print(f"\nFuture payments from {optimization_date.date()}:")
# print(fabn_future[["date", "coupon", "principal", "total", "t_years"]].to_string(index=False))

total_pv   = fabn_future["total"].sum()
mac_D_FABN = (fabn_future["t_years"] * fabn_future["total"]).sum() / total_pv
D_FABN     = mac_D_FABN / (1 + r_FABN / 2)

# print(f"\nMacaulay D_FABN : {mac_D_FABN:.4f} yrs")
# print(f"Modified D_FABN : {D_FABN:.4f} yrs  ← used in optimizer")

fabn_future["quarter"] = fabn_future["date"].dt.to_period("Q")
fabn_qtr_series = fabn_future.groupby("quarter")["total"].sum()

qtr_fabn_cf = np.array([
    fabn_qtr_series.get(q, 0.0) * (H / face)
    for q in qtr_idx
])

# print(f"\nqtr_fabn_cf (${H/1e6:.0f}M face, non-zero quarters):")
for q, v in zip(qtr_idx, qtr_fabn_cf):
    if v > 0:
        pass
        # print(f"  {q}  ${v:>14,.2f}")

score = spread + beta_w * signal

# print(f"\nscore range : {score[~np.isnan(score)].min()*10000:.1f} – "
      # f"{score[~np.isnan(score)].max()*10000:.1f} bps")

# =============================================================================
# 9 — Validation
# =============================================================================
checks = [
    ("bond_cf shape",      bond_cf.shape == (T, N)),
    ("qtr_bond_cf shape",  qtr_bond_cf.shape == (Q, N)),
    ("durs length",        len(durs) == N),
    ("theta length",       len(theta) == N),
    ("spread length",      len(spread) == N),
    ("h_curr length",      len(h_curr) == N),
    ("score length",       len(score) == N),
    ("qtr_fabn_cf length", len(qtr_fabn_cf) == Q),
    ("no NaN in durs",     not np.isnan(durs).any()),
    ("no NaN in theta",    not np.isnan(theta).any()),
    ("spread coverage",    (~np.isnan(spread)).mean() > 0.8),
]

all_pass = True
for name, result in checks:
    status = "PASS" if result else "FAIL"
    if not result:
        all_pass = False
    # print(f"  [{status}]  {name}")

# print()
if all_pass:
    pass
    # print("All checks passed — pipeline ready.")
else:
    pass
    # print("Some checks FAILED — review before running the optimizer.")

# NaN-fill spreads with sector median before passing to optimizer
sector_map     = fixed.set_index("CUSIP")["sector"]
spread_series  = pd.Series(spread, index=CUSIPS)
sector_medians = spread_series.groupby(sector_map).transform("median")
spread_clean   = spread_series.fillna(sector_medians).fillna(spread_series.median()).values
score_clean    = spread_clean + beta_w * signal

n_filled = np.isnan(spread).sum()
# print(f"NaN spreads filled with sector median : {n_filled}")

# =============================================================================
# 9.5 — Prices, Book Yield, Amortization & Bid-Ask Transaction Costs
# =============================================================================
PRICE_DATASET = {
    "mid": "insurance-backed-securities.Mid_Price.mid_long_raw",
    "bid": "insurance-backed-securities.Bid_Price.bid_long_raw",
    "ask": "insurance-backed-securities.Ask_Price.ask_long_raw",  # stored as STRING
}


def _nearest_price_map(table, cast_float=False):
    """Price per CUSIP nearest to optimization_date within ±10 day window."""
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


mid_map = _nearest_price_map(PRICE_DATASET["mid"])
bid_map = _nearest_price_map(PRICE_DATASET["bid"])
ask_map = _nearest_price_map(PRICE_DATASET["ask"], cast_float=True)

mid_raw = np.array([mid_map.get(c, np.nan) for c in CUSIPS])
bid     = np.array([bid_map.get(c, np.nan) for c in CUSIPS])
ask     = np.array([ask_map.get(c, np.nan) for c in CUSIPS])

# Mid price = book / purchase value; fallback to par (100) where no quote
price = np.where(np.isnan(mid_raw) | (mid_raw <= 0), 100.0, mid_raw)

# Book yield via effective-interest IRR; fallback to rf + spread where IRR fails
annual_coupon  = fixed.set_index("CUSIP").loc[CUSIPS, "coupon"].values / 100.0
fallback_y     = np.nan_to_num(rf_per_bond) + spread_clean

book_yield_raw = ff.book_yields(bond_cf, t_vec, price)
n_irr_fail     = int(np.isnan(book_yield_raw).sum())
book_yield     = np.where(np.isnan(book_yield_raw), fallback_y, book_yield_raw)

# Coupon / amortization decomposition (statutory C_i + A_i, per $ invested)
coupon_inc, amort_inc = ff.coupon_amort_split(book_yield, annual_coupon, price)

# Bid-ask half-spread as relative transaction cost; median-fill missing quotes
with np.errstate(invalid="ignore", divide="ignore"):
    tau = (ask - bid) / (2.0 * price)
tau_valid  = np.isfinite(tau) & (tau > 0)
n_tau_fill = int((~tau_valid).sum())
tau = np.where(tau_valid, tau, np.nan)
tau = np.where(np.isnan(tau), np.nanmedian(tau), tau)

n_mid = int((~np.isnan(mid_raw)).sum())
# print(f"Mid price coverage : {n_mid}/{N} bonds  ({N - n_mid} filled at par)")
# print(f"Book yield IRR     : {N - n_irr_fail}/{N} solved  ({n_irr_fail} fell back to rf+spread)")
# print(f"Bid-ask tau        : {N - n_tau_fill}/{N} from quotes  ({n_tau_fill} median-filled)")
# print(f"Book yield         : {np.nanmin(book_yield)*100:.2f}% – {np.nanmax(book_yield)*100:.2f}%  "
      # f"(mean {np.nanmean(book_yield)*100:.2f}%)")
# print(f"Coupon yield mean  : {np.nanmean(coupon_inc)*100:.2f}%   "
      # f"Amort yield mean : {np.nanmean(amort_inc)*100:+.3f}%")
# print(f"Bid-ask tau        : {np.nanmin(tau)*1e4:.1f} – {np.nanmax(tau)*1e4:.1f} bps  "
      # f"(mean {np.nanmean(tau)*1e4:.1f} bps)")

# =============================================================================
# 10 — Pipeline Output
# =============================================================================
pipeline = {
    # dimensions
    "N":              N,
    "T":              T,
    "Q":              Q,
    "fabn_q":         fabn_q,        # quarters through FABN maturity (reinvestment horizon)
    "CUSIPS":         CUSIPS,
    "fixed":          fixed,

    # per-bond arrays (shape N)
    "spread":         spread_clean,
    "durs":           durs,
    "theta":          theta,
    "tau":            tau,
    "signal":         signal,
    "score":          score_clean,
    "h_curr":         h_curr,

    # SAP statutory-accounting arrays (shape N) — from Section 9.5
    "price":          price,
    "book_yield":     book_yield,
    "coupon_inc":     coupon_inc,
    "amort_inc":      amort_inc,

    # cashflow matrices
    "bond_cf":        bond_cf,
    "qtr_bond_cf":    qtr_bond_cf,
    "qtr_fabn_cf":    qtr_fabn_cf,
    "qtr_idx":        qtr_idx,
    "t_vec":          t_vec,

    # scalar params
    "H":              H,
    "r_FABN":         r_FABN,
    "r_float":        float(rf_interp(0.25)),   # 3M Treasury rate — SOFR proxy for swap pricing
    "D_FABN":         D_FABN,
    "C_curr":         C_curr,
    "C_min":          C_min,
    "RBC_bar":        RBC_bar,
    "dt":             dt,
    "gamma_w":        gamma_w,
    "beta_w":         beta_w,
    "alpha_w":        alpha_w,
    "lambda_w":       lambda_w,
    "eps_D":          eps_D,
}

summary = pd.DataFrame([
    ["Universe size (N)",          N,                                  ""],
    ["Payment dates (T)",          T,                                  ""],
    ["Quarterly periods (Q)",      Q,                                  ""],
    ["Spread mean (bps)",          f"{spread_clean.mean()*10000:.1f}", ""],
    ["Book yield mean (%)",        f"{np.nanmean(book_yield)*100:.2f}",""],
    ["Bid-ask tau mean (bps)",     f"{np.nanmean(tau)*1e4:.1f}",       ""],
    ["Duration mean (yrs)",        f"{durs.mean():.2f}",               ""],
    ["C1 charge mean (%)",         f"{theta.mean()*100:.3f}",          ""],
    ["FABN D target (yrs)",        D_FABN,                             ""],
    ["Budget H ($M)",              H / 1e6,                            ""],
], columns=["Metric", "Value", "Notes"])

# print(summary.to_string())
# print("\npipeline dict ready.")
