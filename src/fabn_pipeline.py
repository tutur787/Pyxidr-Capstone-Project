"""
FABN Portfolio Optimization — Data Pipeline
============================================
Inputs  : Bloomberg_first_batch.xlsx
Outputs : bond_universe.csv        — one row per bond, all static features + time-avg TC
          price_returns.csv        — daily log-returns matrix (dates x CUSIPs)
          daily_spread.csv         — daily credit spread matrix (dates x CUSIPs)
          data_quality.txt         — audit log of every cleaning decision
          bid.csv                  — daily bid prices matrix (dates x CUSIPs)
          ask.csv                  — daily ask prices matrix (dates x CUSIPs)
          price.csv                — daily mid prices matrix (dates x CUSIPs)
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

excel_file = os.path.join('..', 'data', 'Bloomberg_first_batch.xlsx')
xl = pd.ExcelFile(excel_file)
log = []

def note(msg):
    log.append(msg)
    print(msg)

note(f"Pipeline run: {datetime.now().isoformat()}")

# ─────────────────────────────────────────────
# STEP 1: Load static metadata
# ─────────────────────────────────────────────
note("\n=== STEP 1: Load metadata ===")

s1 = pd.read_excel(xl, sheet_name='Sheet1', header=0)
s1['CUSIP'] = s1['CUSIP'].astype(str).str.strip()
note(f"Sheet1: {len(s1)} bonds")

ff = pd.read_excel(xl, sheet_name='Fixed fields', header=0)
ff['CUSIP'] = ff['CUSIP'].astype(str).str.strip()
note(f"Fixed fields: {len(ff)} bonds")

# Merge on CUSIP — left join keeps all 237 from Sheet1
bonds = s1.merge(
    ff[['CUSIP', 'RTG_MOODY', 'BICS_LEVEL_1_SECTOR_NAME',
        'BICS_LEVEL_2_INDUSTRY_GROUP_NAME', 'DUR_ADJ_MID']],
    on='CUSIP', how='left'
)
note(f"After merge: {len(bonds)} bonds, "
     f"{bonds['RTG_MOODY'].isna().sum()} missing Moody's rating")

# ─────────────────────────────────────────────
# STEP 2: Standardise and derive static features
# ─────────────────────────────────────────────
note("\n=== STEP 2: Feature engineering ===")

bonds['Maturity'] = pd.to_datetime(bonds['Maturity'], errors='coerce')
valuation_date = pd.Timestamp('2024-03-01')
bonds['years_to_maturity'] = (bonds['Maturity'] - valuation_date).dt.days / 365.25
note(f"Maturity parse failures: {bonds['years_to_maturity'].isna().sum()}")

# Current yield proxy: coupon / ask price (both in %)
bonds['current_yield'] = bonds['Cpn'] / bonds['Ask Price']
note(f"Current yield range: "
     f"{bonds['current_yield'].min():.4f} to {bonds['current_yield'].max():.4f}")

# Duration: prefer DUR_ADJ_MID from Fixed fields, else Mac Dur (Ask)
bonds['duration'] = bonds['DUR_ADJ_MID'].fillna(bonds['Mac Dur (Ask)'])
note(f"Duration missing after fallback: {bonds['duration'].isna().sum()}")

# ─────────────────────────────────────────────
# STEP 3: RBC factor mapping
# ─────────────────────────────────────────────
note("\n=== STEP 3: RBC factor mapping ===")

# NAIC RBC C1 factors for corporate bonds
# Required capital as % of bond value, by S&P-equivalent rating
C1_FACTORS = {
    'AAA': 0.0030, 'AA+': 0.0030, 'AA': 0.0030, 'AA-': 0.0030,
    'A+':  0.0030, 'A':   0.0030, 'A-': 0.0030,
    'BBB+':0.0100, 'BBB': 0.0100, 'BBB-':0.0130,
    'BB+': 0.0230, 'BB':  0.0230, 'BB-': 0.0230,
    'B+':  0.0460, 'B':   0.0460, 'B-':  0.0460,
    'CCC+':0.1000, 'CCC': 0.1000, 'CCC-':0.1000,
    'NR':  0.0230,   # unrated treated as BB per NAIC guidance
}

# NAIC C3 factors by duration bucket (interest rate risk)
def c3_factor(duration):
    if pd.isna(duration):   return np.nan
    if duration < 1:        return 0.0065
    elif duration < 2:      return 0.0130
    elif duration < 3:      return 0.0190
    elif duration < 4:      return 0.0250
    elif duration < 5:      return 0.0310
    elif duration < 7:      return 0.0400
    elif duration < 10:     return 0.0490
    else:                   return 0.0580

bonds['c1_factor'] = bonds['BBG Composite'].map(C1_FACTORS)
bonds['c3_factor'] = bonds['duration'].apply(c3_factor)

missing_c1 = bonds['c1_factor'].isna().sum()
note(f"C1 factor: {missing_c1} unmapped ratings")
if missing_c1 > 0:
    unmapped = bonds[bonds['c1_factor'].isna()]['BBG Composite'].unique()
    note(f"  Unmapped ratings: {unmapped}")
    bonds['c1_factor'] = bonds['c1_factor'].fillna(C1_FACTORS['NR'])
    note(f"  Filled with NR factor ({C1_FACTORS['NR']})")
note(f"C3 factor missing: {bonds['c3_factor'].isna().sum()}")

# ─────────────────────────────────────────────
# STEP 4: Determine which CUSIPs to keep
#         (driven by PRICE data quality — same
#          filter applied to BID, ASK, and metadata)
# ─────────────────────────────────────────────
note("\n=== STEP 4: PRICE cleaning — determine kept CUSIPs ===")

price_raw = pd.read_excel(xl, sheet_name='PRICE', header=0, index_col=0)
price_raw.index = pd.to_datetime(price_raw.index, errors='coerce')
price_raw = price_raw[price_raw.index.notna()].sort_index()
price_raw.columns = price_raw.columns.astype(str).str.strip()
note(f"Raw PRICE: {price_raw.shape[0]} dates x {price_raw.shape[1]} bonds")

# PRIMARY FILTER: drop any bond whose last valid price is not the final date.
# Bonds that go dark before the end would produce fake zero-returns if forward-filled.
last_date = price_raw.index[-1]
cols_to_keep = [col for col in price_raw.columns
                if price_raw[col].last_valid_index() == last_date]
drop_early = [col for col in price_raw.columns if col not in cols_to_keep]
price_clean = price_raw[cols_to_keep]
note(f"Primary filter (last valid date != {last_date.date()}): "
     f"dropped {len(drop_early)} bonds, {len(price_clean.columns)} remain")

# SECONDARY FILTER: drop bonds with >20% missing prices in their active window.
# Catches bonds with large internal gaps that still happen to end on the last date.
nan_pct = price_clean.isna().mean()
drop_sparse = nan_pct[nan_pct > 0.20].index.tolist()
price_clean = price_clean.drop(columns=drop_sparse)
note(f"Secondary filter (>20% missing): "
     f"dropped {len(drop_sparse)} more bonds, {len(price_clean.columns)} remain")

# Forward-fill short gaps (e.g. bank holidays), cap at 5 days
price_clean = price_clean.ffill(limit=5)

# Drop any bond still containing NaNs after fill (should be none at this point)
still_nan = price_clean.columns[price_clean.isna().any()].tolist()
if still_nan:
    price_clean = price_clean.drop(columns=still_nan)
    note(f"Tertiary filter (unfillable gaps): dropped {len(still_nan)} more bonds")
note(f"Final PRICE matrix: {price_clean.shape[0]} dates x {price_clean.shape[1]} bonds")

# This is the authoritative kept set — applied identically to BID and ASK
kept_cusips = list(price_clean.columns)

# ─────────────────────────────────────────────
# STEP 5: BID and ASK time series
#         Apply same CUSIP filter, fix negatives in ASK
# ─────────────────────────────────────────────
note("\n=== STEP 5: BID / ASK time series ===")

def load_ts(sheet_name):
    df = pd.read_excel(xl, sheet_name=sheet_name, header=0, index_col=0)
    df.index = pd.to_datetime(df.index, errors='coerce')
    df = df[df.index.notna()].sort_index()
    df.columns = df.columns.astype(str).str.strip()
    return df

bid_raw = load_ts('BID')
ask_raw = load_ts('ASK')

# Apply same CUSIP filter as PRICE
bid_clean = bid_raw[[c for c in kept_cusips if c in bid_raw.columns]]
ask_clean = ask_raw[[c for c in kept_cusips if c in ask_raw.columns]]
note(f"BID after CUSIP filter: {bid_clean.shape}")
note(f"ASK after CUSIP filter: {ask_clean.shape}")

# Fix ASK negatives — confirmed sign-flip errors:
# abs(negative ASK) == BID for same bond/date
neg_count_before = (ask_clean < 0).sum().sum()
ask_clean = ask_clean.abs()
note(f"ASK: corrected {neg_count_before} negative values with abs()")

# Sanity check: ask should be >= bid after fix
violations = (ask_clean < bid_clean).sum().sum()
note(f"ASK < BID violations after fix: {violations}")

# Forward-fill any remaining NaNs (same logic as PRICE, capped at 5 days)
bid_clean = bid_clean.ffill(limit=5)
ask_clean = ask_clean.ffill(limit=5)
note(f"BID NaNs after ffill: {bid_clean.isna().sum().sum()}")
note(f"ASK NaNs after ffill: {ask_clean.isna().sum().sum()}")

# ─────────────────────────────────────────────
# STEP 6: Credit spread, log returns, and transaction costs
# ─────────────────────────────────────────────
note("\n=== STEP 6: Credit spread, log returns, and transaction costs ===")

# Align indices — all three series should share the same dates
common_dates = price_clean.index.intersection(bid_clean.index).intersection(ask_clean.index)
common_cols  = [c for c in kept_cusips
                if c in bid_clean.columns and c in ask_clean.columns]

price_final = price_clean.loc[common_dates, common_cols]
bid_final   = bid_clean.loc[common_dates, common_cols]
ask_final   = ask_clean.loc[common_dates, common_cols]

# --- Daily YTM approximation ---
# YTM ≈ [Cpn + (100 - Price) / n] / [(100 + Price) / 2]
# Cpn in % (e.g. 4.0 = 4%), Price per 100 face, n in years → result in decimal
bonds_dedup = bonds.drop_duplicates(subset='CUSIP').set_index('CUSIP')
cusip_cpn = bonds_dedup['Cpn'].reindex(common_cols)
cusip_mat = bonds_dedup['Maturity'].reindex(common_cols)

ytm_years = pd.DataFrame(
    {c: (cusip_mat[c] - price_final.index).days / 365.25 for c in common_cols},
    index=price_final.index
)
ytm_years = ytm_years.clip(lower=0.01)

cpn_vals = cusip_cpn.values
ytm_approx = (cpn_vals + (100 - price_final) / ytm_years) / ((100 + price_final) / 2)

note(f"YTM matrix: {ytm_approx.shape}")
note(f"Mean YTM: {ytm_approx.mean().mean():.4f}")

# --- Credit spread = YTM - interpolated Treasury yield ---
# Daily US Treasury constant-maturity yields from FRED (2024-03-01 to 2026-02-26).
# Series: DGS6MO, DGS1, DGS2, DGS3, DGS5, DGS7, DGS10, DGS20, DGS30
# Source: Federal Reserve Bank of St. Louis, https://fred.stlouisfed.org
# Units: percent per annum → divided by 100 to get decimal
# If FRED is unavailable, falls back to the static March 2024 snapshot below.
TREASURY_TENORS = np.array([0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0])
FRED_SERIES     = ['DGS6MO', 'DGS1', 'DGS2', 'DGS3', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30']
STATIC_FALLBACK = np.array([0.0532, 0.0502, 0.0462, 0.0440, 0.0421, 0.0424, 0.0419, 0.0446, 0.0435])

def fetch_fred_series(series_id, start, end):
    """Fetch a single FRED series as a dated Series via the public CSV endpoint."""
    import requests, io
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv"
           f"?id={series_id}&vintage_date={end.strftime('%Y-%m-%d')}")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), encoding_errors='replace')
    # Normalise column names: strip BOM, whitespace, uppercase
    df.columns = [c.encode('ascii', 'ignore').decode().strip().upper() for c in df.columns]
    # Date column may be 'DATE' or 'OBSERVATION_DATE' depending on FRED endpoint
    date_col = next(c for c in df.columns if 'DATE' in c)
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df.columns = [series_id]
    df = df[(df.index >= start) & (df.index <= end)]
    df = df.replace('.', np.nan).astype(float) / 100   # FRED uses '.' for missing
    return df[series_id]

try:
    start = price_final.index[0] - pd.Timedelta(days=7)
    end   = price_final.index[-1]
    tsy_frames = [fetch_fred_series(s, start, end) for s in FRED_SERIES]
    tsy_raw = pd.concat(tsy_frames, axis=1)
    tsy_raw.columns = TREASURY_TENORS
    tsy_raw = tsy_raw.ffill().bfill()                  # fill weekends/holidays
    tsy_daily = tsy_raw.reindex(price_final.index, method='ffill')
    note(f"Treasury curve: loaded daily FRED data ({tsy_daily.shape[0]} dates)")

    # For each bond×date, interpolate the risk-free rate at that bond's remaining maturity
    treasury_rf_vals = np.zeros_like(ytm_years.values)
    for i, date in enumerate(ytm_years.index):
        row_tenors = ytm_years.iloc[i].values           # remaining maturities per bond
        row_yields = tsy_daily.loc[date].values          # that day's treasury curve
        treasury_rf_vals[i] = np.interp(row_tenors, TREASURY_TENORS, row_yields)

    treasury_rf = pd.DataFrame(treasury_rf_vals,
                               index=ytm_years.index,
                               columns=ytm_years.columns)
    note("Treasury curve: interpolated per bond per date using daily FRED curve")

except Exception as e:
    note(f"Treasury curve: FRED fetch failed ({e})")
    note("Treasury curve: using static March 2024 fallback — update when FRED available")
    treasury_rf = pd.DataFrame(
        np.interp(ytm_years.values, TREASURY_TENORS, STATIC_FALLBACK),
        index=ytm_years.index, columns=ytm_years.columns
    )

daily_spread = ytm_approx - treasury_rf

note(f"Credit spread matrix: {daily_spread.shape}")
note(f"Mean credit spread: {daily_spread.mean().mean():.4f}")
note(f"Credit spread range: {daily_spread.min().min():.4f} to {daily_spread.max().max():.4f}")

# --- Log returns ---
log_returns = np.log(price_final / price_final.shift(1)).iloc[1:]
note(f"Log returns: {log_returns.shape[0]} days x {log_returns.shape[1]} bonds")
note(f"Date range: {log_returns.index[0].date()} to {log_returns.index[-1].date()}")

# --- Bid-ask transaction cost (kept separate from credit spread) ---
# IMPORTANT: these two quantities serve different roles in the optimizer:
#   daily_spread  → credit spread (OAS proxy) — goes in the OBJECTIVE as the
#                   quantity to maximize: maximize Σ wᵢ · credit_spreadᵢ
#   daily_tc_pct  → bid-ask spread as % of mid — goes in the TC PENALTY term:
#                   subtract λ · Σ (bid_ask_i/2) · |wᵢ - w⁰ᵢ|
# Never substitute one for the other in the optimizer.
mid = (ask_final + bid_final) / 2
daily_tc_pct = (ask_final - bid_final) / mid
note(f"Mean bid-ask TC: {daily_tc_pct.mean().mean():.4f}")

# ─────────────────────────────────────────────
# STEP 7: Align metadata universe with final CUSIP set
# ─────────────────────────────────────────────
note("\n=== STEP 7: Final universe alignment ===")

bonds['Bid Price snapshot'] = bonds['Bid Price']
bonds['Ask Price snapshot'] = bonds['Ask Price']

# Add time-averaged TC from daily spread (more robust than single-day snapshot)
avg_tc = daily_tc_pct.mean().rename('tc_pct_avg')
bonds = bonds.merge(avg_tc.reset_index().rename(columns={'index':'CUSIP'}),
                    on='CUSIP', how='left')

# Also keep snapshot bid-ask spread for reference
bonds['bid_ask_spread_snapshot'] = bonds['Ask Price'] - bonds['Bid Price']

# Deduplicate metadata — keep first occurrence of each CUSIP.
# Duplicates exist for some bonds (e.g. Westpac NZ listed under two CUSIPs
# that appear identical — same issuer, coupon, maturity). Keeping both would
# cause a shape mismatch when aligning with the returns/spread matrices.
bonds = bonds.drop_duplicates(subset='CUSIP', keep='first')
note(f"Metadata after dedup: {len(bonds)} bonds")

# Intersection of metadata CUSIPs and price CUSIPs — the fully aligned universe
aligned_cusips = [c for c in common_cols if c in set(bonds['CUSIP'])]

bonds_final   = bonds[bonds['CUSIP'].isin(aligned_cusips)].copy().reset_index(drop=True)
returns_final = log_returns[aligned_cusips]
spread_final  = daily_spread[aligned_cusips]
bid_final     = bid_final[aligned_cusips]
ask_final     = ask_final[aligned_cusips]

note(f"Dropped {len(common_cols) - len(aligned_cusips)} bonds missing metadata from price/spread matrices")
note(f"Final bond universe:  {len(bonds_final)} bonds")
note(f"Returns matrix:       {returns_final.shape}")
note(f"Spread matrix:        {spread_final.shape}")

# ─────────────────────────────────────────────
# STEP 8: Summary stats
# ─────────────────────────────────────────────
note("\n=== STEP 8: Summary ===")
note(f"Duration range: {bonds_final['duration'].min():.2f} to {bonds_final['duration'].max():.2f} yrs")
note(f"Yield range: {bonds_final['current_yield'].min():.4f} to {bonds_final['current_yield'].max():.4f}")
note(f"C1 factor range: {bonds_final['c1_factor'].min():.4f} to {bonds_final['c1_factor'].max():.4f}")
note(f"C3 factor range: {bonds_final['c3_factor'].min():.4f} to {bonds_final['c3_factor'].max():.4f}")
note(f"Rating distribution:\n{bonds_final['BBG Composite'].value_counts().to_string()}")
note(f"Sector distribution:\n{bonds_final['BICS_LEVEL_1_SECTOR_NAME'].value_counts().to_string()}")

# ─────────────────────────────────────────────
# SAVE OUTPUTS
# ─────────────────────────────────────────────
OUT_COLS = [
    'CUSIP', 'Issuer Name', 'Ticker', 'Cpn', 'Maturity', 'years_to_maturity',
    'Bid Price snapshot', 'Ask Price snapshot',
    'bid_ask_spread_snapshot', 'tc_pct_avg',
    'current_yield', 'duration', 'BBG Composite', 'RTG_MOODY',
    'BICS_LEVEL_1_SECTOR_NAME', 'BICS_LEVEL_2_INDUSTRY_GROUP_NAME',
    'c1_factor', 'c3_factor', 'Amt Out', 'Mty Type'
]
bonds_final[OUT_COLS].to_csv(os.path.join('..', 'data', 'bond_universe.csv'), index=False)
returns_with_date = returns_final.copy()
returns_with_date.insert(0, 'date', returns_with_date.index)
returns_with_date.to_csv(os.path.join('..', 'data', 'price_returns.csv'), index=False)

spread_with_date = spread_final.copy()
spread_with_date.insert(0, 'date', spread_with_date.index)
spread_with_date.to_csv(os.path.join('..', 'data', 'daily_spread.csv'), index=False)

# Save BID, ASK, PRICE sheets with date column
bid_final_with_date = bid_final.copy()
ask_final_with_date = ask_final.copy()
price_final_with_date = price_final.copy()

# Assume that the original date index should become a column called 'date'
bid_final_with_date.insert(0, 'date', bid_final_with_date.index)
ask_final_with_date.insert(0, 'date', ask_final_with_date.index)
price_final_with_date.insert(0, 'date', price_final_with_date.index)

bid_final_with_date.to_csv(os.path.join('..', 'data', 'bid.csv'), index=False)
ask_final_with_date.to_csv(os.path.join('..', 'data', 'ask.csv'), index=False)
price_final_with_date.to_csv(os.path.join('..', 'data', 'price.csv'), index=False)

with open(os.path.join('..', 'data', 'data_quality.txt'), 'w') as f:
    f.write('\n'.join(log))

print("\nDone.")