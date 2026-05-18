# FABN Optimizer — Data Pipeline
#
# Builds every input array the optimizer needs from the three BigQuery tables:
# - Asset_Cashflows  — cashflow schedule per CUSIP
# - Agg_Spread_Long  — daily spread per CUSIP
# - Agg_Fixed_Field  — static bond attributes (rating, duration, sector, …)
#
# Outputs (all stored in `pipeline` dict at the bottom):
#
# | Key           | Shape  | Description                          |
# |---------------|--------|--------------------------------------|
# | CUSIPS        | (N,)   | ordered bond universe                |
# | spread        | (N,)   | OAS spread in decimal (bps / 10 000) |
# | durs          | (N,)   | modified duration (years)            |
# | theta         | (N,)   | C-1 RBC charge factor                |
# | h_curr        | (N,)   | current equal-weight allocation      |
# | bond_cf       | (T, N) | daily cashflow matrix                |
# | qtr_bond_cf   | (Q, N) | quarterly cashflow matrix            |
# | qtr_idx       | (Q,)   | quarter labels                       |
# | t_vec         | (T,)   | time in years from optimization date |
#
# Deferred (set to zeros for now, plug in later):
# - tau    — transaction costs
# - signal — composite signal
# - score  — recomputed once signal is ready


# =============================================================================
# 0 — Imports & Connection
# =============================================================================

from google.cloud import bigquery
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

PROJECT_ID = "insurance-backed-securities"
DATASET    = "Securities"
BQ         = f"`{PROJECT_ID}.{DATASET}"

client = bigquery.Client(project=PROJECT_ID)
print(f"Connected: {client.project}")


# =============================================================================
# 1 — Parameters
#
# Set the optimization date and the FABN liability parameters here.
# Everything downstream is derived from `optimization_date`.
# =============================================================================

import datetime

# ── Optimization date ──────────────────────────────────────────────────────
# If this script is called via runpy from the optimizer, the caller can
# pre-set `optimization_date` before running — this block respects that value.
# When run standalone, the default date below is used.
try:
    optimization_date   # already defined by the caller
except NameError:
    optimization_date = pd.Timestamp("2025-01-15")

# ── FABN terms ─────────────────────────────────────────────────────────────
FABN_ISSUE    = pd.Timestamp("2022-09-06")
FABN_MATURITY = pd.Timestamp("2027-09-06")
FABN_COUPON   = 0.03205   # 3.205% annual, paid semi-annually

# ── FABN / liability parameters (Athene-sourced) ──────────────────────────
H       = 500_000_000.0   # total capital budget ($) — CONFIRM WITH ATHENE
r_FABN  = FABN_COUPON     # funding agreement crediting rate (annual, decimal)
# D_FABN is computed in Section 8 from the actual cashflow schedule
C_curr  = 50_000_000.0     # current regulatory capital ($) — CONFIRM WITH ATHENE
C_min   = 1_000_000.0     # minimum required capital ($)   — CONFIRM WITH ATHENE
RBC_bar = 1.5             # minimum RBC solvency ratio      — CONFIRM WITH ATHENE
dt      = 1.0             # time scaling factor (1 = annual)

# ── Optimizer penalty weights (tune later) ────────────────────────────────
gamma_w  = 0.15  # γ : weight on capital cost (C1 + C3)
beta_w   = 0.0   # β : weight on signal  (0 until signal is ready)
alpha_w  = 0.0   # α : C3 duration mismatch scaling (0 until C3 is active)
lambda_w = 0.05   # λ : CF shortfall penalty weight
eps_D    = 0.3   # duration tolerance band (years)

print(f"Optimization date  : {optimization_date.date()}")
print(f"FABN issue/maturity: {FABN_ISSUE.date()} → {FABN_MATURITY.date()}")
print(f"Budget H           : ${H:,.0f}")
print(f"r_FABN             : {r_FABN*100:.3f}%")

# gamma_w = 0.15  (inspection cell)


# =============================================================================
# 2 — Bond Universe from `Agg_Fixed_Field`
#
# Defines the bond index i = 0 … N-1.
# Every downstream array is aligned to this CUSIP list.
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

# Deduplicate — keep one row per CUSIP
fixed = fixed.drop_duplicates(subset="CUSIP").reset_index(drop=True)

CUSIPS = fixed["CUSIP"].tolist()
N      = len(CUSIPS)
cusip_idx = {c: i for i, c in enumerate(CUSIPS)}   # fast reverse lookup

print(f"Universe size N = {N} bonds")
print(fixed.head())


# =============================================================================
# 3 — Spreads from `Agg_Spread_Long`
#
# Pull the spread for each CUSIP on (or nearest to) `optimization_date`.
# Spread is stored in basis points — we convert to decimal for the optimizer.
# =============================================================================

# ── Diagnóstico: ¿Qué fechas hay en Agg_Spread_Long? ────────────────────
# Esto muestra la granularidad real de los datos de spread.
# Si solo hay 1-2 fechas por año, la optimización no puede variar dentro del año.
sql_available = f"""
SELECT DISTINCT Date
FROM `{PROJECT_ID}.{DATASET}.Agg_Spread_Long`
WHERE Date <= DATE '{optimization_date.date()}'
ORDER BY Date DESC
LIMIT 30
"""
available_dates_df = client.query(sql_available).to_dataframe()
available_dates_df["Date"] = pd.to_datetime(available_dates_df["Date"])

print(f"Fechas disponibles en Agg_Spread_Long (≤ {optimization_date.date()}, últimas 30):")
print(available_dates_df["Date"].dt.date.to_string(index=False))
print()

# ── Pull del spread más reciente disponible ≤ optimization_date ───────────
sql_spread = f"""
WITH ranked AS (
    SELECT
        CUSIP,
        Spread,
        Date,
        ROW_NUMBER() OVER (
            PARTITION BY CUSIP
            ORDER BY Date DESC
        ) AS rn
    FROM `{PROJECT_ID}.{DATASET}.Agg_Spread_Long`
    WHERE Date <= DATE '{optimization_date.date()}'
)
SELECT CUSIP, Spread, Date
FROM ranked
WHERE rn = 1
"""

spread_df = client.query(sql_spread).to_dataframe()
spread_df["Date"] = pd.to_datetime(spread_df["Date"])
spread_map      = spread_df.set_index("CUSIP")["Spread"]
spread_date_map = spread_df.set_index("CUSIP")["Date"]

# Align to CUSIP order; convert bps → decimal
spread_bps = np.array([spread_map.get(c, np.nan) for c in CUSIPS])
spread     = spread_bps / 10_000.0

missing_spread = np.isnan(spread).sum()
print(f"Spread coverage : {N - missing_spread}/{N} bonds  ({missing_spread} missing)")
print(f"Spread range    : {spread_bps[~np.isnan(spread_bps)].min():.1f} – "
      f"{spread_bps[~np.isnan(spread_bps)].max():.1f} bps")

if not spread_df.empty:
    actual_dates = spread_df["Date"].dropna()
    n_unique     = actual_dates.nunique()
    staleness    = (pd.Timestamp(optimization_date) - actual_dates).dt.days
    print(f"Fechas únicas usadas    : {n_unique}  ({actual_dates.min().date()} – {actual_dates.max().date()})")
    print(f"Staleness (días atrás)  : min {staleness.min()}  /  media {staleness.mean():.0f}  /  max {staleness.max()}")
    if staleness.mean() > 180:
        print("  ⚠  Media >180 días → datos anuales. La optimización no varía dentro del año.")


# =============================================================================
# 4 — Cashflow Matrix from `Asset_Cashflows`
#
# Builds two aligned matrices:
# - bond_cf     (T × N) — daily cashflow grid used to compute duration
# - qtr_bond_cf (Q × N) — quarterly cashflow grid used in the CF shortfall constraint
#
# Cashflows in Asset_Cashflows are expressed per 100 face value.
# =============================================================================

sql_cf = f"""
SELECT PaymentDate, CUSIP, Payment, Type
FROM `{PROJECT_ID}.{DATASET}.Asset_Cashflows`
WHERE PaymentDate > '{optimization_date.date()}'
  AND CUSIP IN UNNEST({CUSIPS})
"""

cf_raw = client.query(sql_cf).to_dataframe()
cf_raw["PaymentDate"] = pd.to_datetime(cf_raw["PaymentDate"])

print(f"Cashflow rows loaded : {len(cf_raw):,}")
print(f"Date range           : {cf_raw['PaymentDate'].min().date()} → {cf_raw['PaymentDate'].max().date()}")
print(cf_raw.head())

# ── Daily cashflow matrix (T × N) ─────────────────────────────────────────
# Sum COUPON + PRINCIPAL on same date for the same CUSIP
cf_agg = (
    cf_raw
    .groupby(["PaymentDate", "CUSIP"])["Payment"]
    .sum()
    .reset_index()
)

cf_pivot = cf_agg.pivot(index="PaymentDate", columns="CUSIP", values="Payment").fillna(0.0)

# Reindex columns to match CUSIPS order; add zeros for CUSIPs with no CF data
cf_pivot = cf_pivot.reindex(columns=CUSIPS, fill_value=0.0)

bond_cf = cf_pivot.values                                          # shape (T, N)
t_dates = cf_pivot.index                                           # DatetimeIndex length T
t_vec   = (t_dates - optimization_date).days.values / 365.25      # years from today
T       = len(t_dates)

print(f"bond_cf shape : {bond_cf.shape}  (T={T} payment dates × N={N} bonds)")

# ── Quarterly cashflow matrix (Q × N) ─────────────────────────────────────
cf_agg["Quarter"] = cf_agg["PaymentDate"].dt.to_period("Q")

qtr_pivot = (
    cf_agg
    .groupby(["Quarter", "CUSIP"])["Payment"]
    .sum()
    .unstack(fill_value=0.0)
    .reindex(columns=CUSIPS, fill_value=0.0)
)

qtr_bond_cf = qtr_pivot.values     # shape (Q, N)
qtr_idx     = qtr_pivot.index      # PeriodIndex length Q
Q           = len(qtr_idx)

print(f"qtr_bond_cf shape : {qtr_bond_cf.shape}  (Q={Q} quarters × N={N} bonds)")
# Convert from "per $100 face" to "per $1 face" so that h[i] * CF gives dollars
bond_cf     = bond_cf     / 100.0
qtr_bond_cf = qtr_bond_cf / 100.0
print(f"Quarter range     : {qtr_idx[0]} → {qtr_idx[-1]}")


# =============================================================================
# 5 — Duration
#
# Compute Macaulay duration using each bond's own yield as the discount rate:
#
#   y_i = rf(T_i) + spread_i
#
# where rf(T_i) is the interpolated Treasury rate at bond i's maturity tenor.
# This is the standard approach — r_FABN is the liability funding rate and
# must not be used here.
#
# Fallback to Bloomberg `Mac Dur _Ask_` for bonds with no cashflow data.
# =============================================================================

import pandas_datareader.data as web
from scipy.interpolate import interp1d

# ── Pull Treasury curve on optimization_date (±5 day fallback) ────────────
MATURITIES_YRS = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 20, 30]
FRED_TICKERS   = ["DGS1MO","DGS3MO","DGS6MO","DGS1","DGS2",
                   "DGS3","DGS5","DGS7","DGS10","DGS20","DGS30"]

rf_raw = web.DataReader(
    FRED_TICKERS, "fred",
    start = optimization_date - pd.Timedelta(days=7),
    end   = optimization_date + pd.Timedelta(days=7),
)
rf_raw.columns = MATURITIES_YRS
rf_clean = rf_raw.dropna(how="all")
day_diff = np.abs((rf_clean.index - optimization_date).days)
rf_row   = rf_clean.iloc[day_diff.argmin()]

print(f"Treasury curve date used : {rf_row.name.date()}")
print(rf_row.rename(lambda t: f"{t:.3f}yr").to_string())

# ── Build interpolator: tenor (years) → risk-free rate (decimal) ──────────
valid = rf_row.dropna()
rf_interp = interp1d(
    valid.index.astype(float),
    valid.values / 100.0,      # FRED reports in %, convert to decimal
    kind="linear",
    fill_value="extrapolate",
)

# ── Bond maturity tenor for each CUSIP ────────────────────────────────────
mat_years = ((fixed["maturity"] - optimization_date).dt.days / 365.25).values
mat_years = np.clip(mat_years, MATURITIES_YRS[0], MATURITIES_YRS[-1])

rf_per_bond    = rf_interp(mat_years)        # shape (N,) — risk-free rate per bond
yield_per_bond = rf_per_bond + spread        # y_i = rf(T_i) + spread_i

# ── Macaulay duration: Σ t·PV(CF_t) / Σ PV(CF_t) ─────────────────────────
def mac_dur_bond(cf_col, t_vec, y):
    if y <= -1 or cf_col.sum() == 0:
        return np.nan
    discount = (1 + y) ** (-t_vec)
    pv_cf    = cf_col * discount
    total_pv = pv_cf.sum()
    if total_pv == 0:
        return np.nan
    return (t_vec * pv_cf).sum() / total_pv

mac_dur_calc = np.array([
    mac_dur_bond(bond_cf[:, i], t_vec,
                 yield_per_bond[i] if not np.isnan(yield_per_bond[i]) else rf_per_bond[i])
    for i in range(N)
])

# Modified duration: mac / (1 + y)
mod_dur_calc = np.where(
    ~np.isnan(mac_dur_calc),
    mac_dur_calc / (1 + np.where(np.isnan(yield_per_bond), rf_per_bond, yield_per_bond)),
    np.nan,
)

# ── Fallback to Bloomberg duration for bonds with no cashflow data ─────────
bbg_dur = fixed["mac_dur_bbg"].values
durs    = np.where(np.isnan(mod_dur_calc), bbg_dur, mod_dur_calc)

n_computed = (~np.isnan(mod_dur_calc)).sum()
n_fallback = np.isnan(mod_dur_calc).sum()
print(f"\nDuration computed from cashflows : {n_computed}")
print(f"Duration from BBG fallback       : {n_fallback}")
print(f"Duration range                   : {np.nanmin(durs):.2f} – {np.nanmax(durs):.2f} yrs")
print(f"Mean bond yield used             : {np.nanmean(yield_per_bond)*100:.3f}%")


# =============================================================================
# 6 — C1 Capital Factor (theta)
#
# Match each bond's S&P composite rating → NAIC C-1 charge factor θ_i.
#
# Fallback chain: BBG Composite (S&P) → Moody's → default IG factor.
# =============================================================================

# ── C1 lookup table (from C1_table =.py) ──────────────────────────────────
C1_SP = {
    "AAA": 0.00158, "AA+": 0.00271, "AA": 0.00419,  "AA-": 0.00523,
    "A+":  0.00657, "A":   0.00816, "A-": 0.01016,
    "BBB+":0.01261, "BBB": 0.01523, "BBB-":0.02168,
    "BB+": 0.03151, "BB":  0.04537, "BB-": 0.06017,
    "B+":  0.07386, "B":   0.09535, "B-":  0.12428,
    "CCC+":0.16942, "CCC": 0.23798, "CCC-":0.32975,
    "D":   0.30000,
}

C1_MOODYS = {
    "Aaa": 0.00158, "Aa1": 0.00271, "Aa2": 0.00419, "Aa3": 0.00523,
    "A1":  0.00657, "A2":  0.00816, "A3":  0.01016,
    "Baa1":0.01261, "Baa2":0.01523, "Baa3":0.02168,
    "Ba1": 0.03151, "Ba2": 0.04537, "Ba3": 0.06017,
    "B1":  0.07386, "B2":  0.09535, "B3":  0.12428,
    "Caa1":0.16942, "Caa2":0.23798, "Caa3":0.32975,
    "Ca":  0.30000, "C":   0.30000,
}

DEFAULT_C1 = C1_SP["BBB"]   # conservative IG default for missing ratings

def lookup_c1(sp_rating, moodys_rating):
    if pd.notna(sp_rating) and str(sp_rating).strip() in C1_SP:
        return C1_SP[str(sp_rating).strip()]
    if pd.notna(moodys_rating) and str(moodys_rating).strip() in C1_MOODYS:
        return C1_MOODYS[str(moodys_rating).strip()]
    return DEFAULT_C1

theta = np.array([
    lookup_c1(fixed.loc[fixed["CUSIP"] == c, "rating_sp"].values[0],
              fixed.loc[fixed["CUSIP"] == c, "rating_moodys"].values[0])
    for c in CUSIPS
])

print(f"theta range : {theta.min():.5f} – {theta.max():.5f}")
print(f"Mean C1     : {theta.mean():.5f}  ({theta.mean()*100:.3f}%)")


# =============================================================================
# 7 — Current Allocations, Signal, Transaction Costs
#
# - h_curr : equal-weight for now (placeholder until real portfolio is loaded)
# - tau    : set to 0 (deferred)
# - signal : set to 0 (deferred)
# =============================================================================

# Equal-weight current allocation
h_curr = np.full(N, H / N)

# Deferred — set to zero until ready
tau    = np.zeros(N)   # transaction cost per bond
signal = np.zeros(N)   # composite signal per bond

print(f"h_curr (equal-weight) : ${H/N:,.2f} per bond")


# =============================================================================
# 8 — FABN Liability Cashflow Schedule & D_FABN
#
# Build the exact semi-annual payment schedule from the FABN terms:
# - Issue: 2022-09-06 | Maturity: 2027-09-06
# - Coupon: 3.205% annual, paid semi-annually → 1.6025% per period
# - Principal: repaid in full at maturity
#
# Only future payments (after `optimization_date`) enter the optimizer.
# =============================================================================

# ── Build full semi-annual payment schedule ───────────────────────────────
semi_coupon = FABN_COUPON / 2          # 1.6025% per period
face        = 100.0                    # per 100 face value

# Generate coupon dates: every 6 months from issue until maturity
fabn_dates = pd.date_range(
    start  = FABN_ISSUE + pd.DateOffset(months=6),
    end    = FABN_MATURITY,
    freq   = "6MS",    # 6-month start frequency anchored to issue day
)
# Snap to actual monthly offsets to respect the Sep-6 / Mar-6 anniversary
fabn_dates = [FABN_ISSUE + pd.DateOffset(months=6 * k) for k in range(1, len(fabn_dates) + 2)]
fabn_dates = pd.DatetimeIndex(fabn_dates)

fabn_cf_full = pd.DataFrame({
    "date":      fabn_dates,
    "coupon":    semi_coupon * face,
    "principal": [0.0] * (len(fabn_dates) - 1) + [face],
})
fabn_cf_full["total"] = fabn_cf_full["coupon"] + fabn_cf_full["principal"]

print("Full FABN schedule (per 100 face):")
print(fabn_cf_full.to_string(index=False))

# ── Keep only future payments (after optimization_date) ───────────────────
fabn_future = fabn_cf_full[fabn_cf_full["date"] > optimization_date].copy()
fabn_future["t_years"] = (fabn_future["date"] - optimization_date).dt.days / 365.25

print(f"\nFuture payments from {optimization_date.date()}:")
print(fabn_future[["date", "coupon", "principal", "total", "t_years"]].to_string(index=False))

# ── Compute D_FABN (Macaulay → Modified duration) ─────────────────────────
total_pv   = fabn_future["total"].sum()
mac_D_FABN = (fabn_future["t_years"] * fabn_future["total"]).sum() / total_pv
D_FABN     = mac_D_FABN / (1 + r_FABN / 2)   # semi-annual compounding convention

print(f"\nMacaulay D_FABN : {mac_D_FABN:.4f} yrs")
print(f"Modified D_FABN : {D_FABN:.4f} yrs  ← used in optimizer")

# ── Map FABN cashflows to the quarterly grid (aligned with qtr_bond_cf) ───
fabn_future["quarter"] = fabn_future["date"].dt.to_period("Q")

# Build Series indexed by the same quarter labels as qtr_idx
fabn_qtr_series = fabn_future.groupby("quarter")["total"].sum()

# Scale from per-100 to actual dollars using H
# (bond CFs are also per-100 and scaled inside the optimizer via h_i)
qtr_fabn_cf = np.array([
    fabn_qtr_series.get(q, 0.0) * (H / face)
    for q in qtr_idx
])

print(f"\nqtr_fabn_cf (${H/1e6:.0f}M face, non-zero quarters):")
for q, v in zip(qtr_idx, qtr_fabn_cf):
    if v > 0:
        print(f"  {q}  ${v:>14,.2f}")

# ── Score ──────────────────────────────────────────────────────────────────
score = spread + beta_w * signal

print(f"\nscore range : {score[~np.isnan(score)].min()*10000:.1f} – "
      f"{score[~np.isnan(score)].max()*10000:.1f} bps")


# =============================================================================
# 9 — Validation
#
# Check shapes, NaN coverage, and key alignment before handing off to the optimizer.
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
    print(f"  [{status}]  {name}")

print()
if all_pass:
    print("All checks passed — pipeline ready.")
else:
    print("Some checks FAILED — review before running the optimizer.")

# Fill any remaining NaN spreads with sector median before passing to optimizer
sector_map = fixed.set_index("CUSIP")["sector"]
spread_series = pd.Series(spread, index=CUSIPS)
sector_medians = spread_series.groupby(sector_map).transform("median")
spread_clean = spread_series.fillna(sector_medians).fillna(spread_series.median()).values
score_clean  = spread_clean + beta_w * signal

n_filled = np.isnan(spread).sum()
print(f"NaN spreads filled with sector median : {n_filled}")


# =============================================================================
# 10 — Pipeline Output
#
# All optimizer inputs collected in a single `pipeline` dict.
# Import or run this script from the optimizer to access them.
# =============================================================================

pipeline = {
    # ── dimensions ──────────────────────────────────────────────────────────
    "N":              N,
    "T":              T,
    "Q":              Q,
    "CUSIPS":         CUSIPS,
    "fixed":          fixed,           # full DataFrame for inspection

    # ── per-bond arrays (shape N) ────────────────────────────────────────────
    "spread":         spread_clean,    # OAS spread in decimal
    "durs":           durs,            # modified duration (years)
    "theta":          theta,           # C-1 RBC charge factor
    "tau":            tau,             # transaction cost (deferred → 0)
    "signal":         signal,          # composite signal (deferred → 0)
    "score":          score_clean,     # spread + β*signal
    "h_curr":         h_curr,          # current allocation

    # ── cashflow matrices ────────────────────────────────────────────────────
    "bond_cf":        bond_cf,         # (T, N)
    "qtr_bond_cf":    qtr_bond_cf,     # (Q, N)
    "qtr_fabn_cf":    qtr_fabn_cf,     # (Q,)  — placeholder, replace with Athene data
    "qtr_idx":        qtr_idx,

    "t_vec":          t_vec,           # (T,) years from optimization_date

    # ── scalar params ────────────────────────────────────────────────────────
    "H":              H,
    "r_FABN":         r_FABN,
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

# Quick summary table
summary = pd.DataFrame([
    ["Universe size (N)",          N,            ""],
    ["Payment dates (T)",          T,            ""],
    ["Quarterly periods (Q)",      Q,            ""],
    ["Spread mean (bps)",          f"{spread_clean.mean()*10000:.1f}", ""],
    ["Duration mean (yrs)",        f"{durs.mean():.2f}",              ""],
    ["C1 charge mean (%)",         f"{theta.mean()*100:.3f}",         ""],
    ["FABN D target (yrs)",        D_FABN,       ""],
    ["Budget H ($M)",              H/1e6,        ""],
], columns=["Metric", "Value", "Notes"])

print(summary.to_string())
print("\npipeline dict ready.")
