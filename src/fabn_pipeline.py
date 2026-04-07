"""
FABN Portfolio Optimization — Data Pipeline
============================================
Inputs  : Bloomberg_first_batch.xlsx
Outputs : bond_universe.csv        — one row per bond, all static features + time-avg TC
          price_returns.csv        — daily log-returns matrix (dates x CUSIPs)
          daily_spread.csv         — daily bid-ask spread matrix (dates x CUSIPs)
          volatility_triggers.csv  — dates where cross-sectional vol exceeds threshold
          data_quality.txt         — audit log of every cleaning decision
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
# STEP 6: Daily bid-ask spread matrix
#         This is the dynamic transaction cost input for the optimizer
# ─────────────────────────────────────────────
note("\n=== STEP 6: Daily bid-ask spread ===")

# Align indices — all three series should share the same dates
common_dates = price_clean.index.intersection(bid_clean.index).intersection(ask_clean.index)
common_cols  = [c for c in kept_cusips
                if c in bid_clean.columns and c in ask_clean.columns]

price_final = price_clean.loc[common_dates, common_cols]
bid_final   = bid_clean.loc[common_dates, common_cols]
ask_final   = ask_clean.loc[common_dates, common_cols]

# Daily spread: ask - bid (in price points per $100 face)
daily_spread = ask_final - bid_final

# As a percentage of mid price — this is the round-trip TC rate
mid = (ask_final + bid_final) / 2
daily_tc_pct = daily_spread / mid

note(f"Daily spread matrix: {daily_spread.shape}")
note(f"Mean bid-ask spread (price pts): {daily_spread.mean().mean():.4f}")
note(f"Spread on high-vol days vs normal days:")

# ─────────────────────────────────────────────
# STEP 7: Log returns and volatility trigger
# ─────────────────────────────────────────────
note("\n=== STEP 7: Returns and volatility trigger ===")

log_returns = np.log(price_final / price_final.shift(1)).iloc[1:]
note(f"Log returns: {log_returns.shape[0]} days x {log_returns.shape[1]} bonds")
note(f"Date range: {log_returns.index[0].date()} to {log_returns.index[-1].date()}")

# Rolling 20-day cross-sectional volatility (annualised)
rolling_vol   = log_returns.rolling(window=20).std() * np.sqrt(252)
mean_vol      = rolling_vol.mean(axis=1)
vol_threshold = mean_vol.mean() + 1.5 * mean_vol.std()
trigger_dates = mean_vol[mean_vol > vol_threshold].index
note(f"Vol trigger threshold: {vol_threshold:.4f}")
note(f"Trigger dates identified: {len(trigger_dates)}")

# Compare spread on trigger vs non-trigger dates
trigger_spread = daily_spread.loc[daily_spread.index.isin(trigger_dates)].mean().mean()
normal_spread  = daily_spread.loc[~daily_spread.index.isin(trigger_dates)].mean().mean()
note(f"  Mean spread on trigger dates:     {trigger_spread:.4f} price pts")
note(f"  Mean spread on non-trigger dates: {normal_spread:.4f} price pts")
note(f"  Spread widens by: {((trigger_spread/normal_spread)-1)*100:.1f}% during high-vol events")

# ─────────────────────────────────────────────
# STEP 8: Align metadata universe with final CUSIP set
# ─────────────────────────────────────────────
note("\n=== STEP 8: Final universe alignment ===")

bonds['Bid Price snapshot'] = bonds['Bid Price']
bonds['Ask Price snapshot'] = bonds['Ask Price']

# Add time-averaged TC from daily spread (more robust than single-day snapshot)
avg_tc = daily_tc_pct.mean().rename('tc_pct_avg')
bonds = bonds.merge(avg_tc.reset_index().rename(columns={'index':'CUSIP'}),
                    on='CUSIP', how='left')

# Also keep snapshot bid-ask spread for reference
bonds['bid_ask_spread_snapshot'] = bonds['Ask Price'] - bonds['Bid Price']

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
# STEP 9: Summary stats
# ─────────────────────────────────────────────
note("\n=== STEP 9: Summary ===")
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

trigger_df = pd.DataFrame({
    'date': trigger_dates,
    'cross_sectional_vol': mean_vol[trigger_dates].values,
    'mean_spread_that_day': daily_spread.loc[daily_spread.index.isin(trigger_dates)].mean(axis=1).values
})
trigger_df.to_csv(os.path.join('..', 'data', 'volatility_triggers.csv'), index=False)

with open(os.path.join('..', 'data', 'data_quality.txt'), 'w') as f:
    f.write('\n'.join(log))

print("\nDone.")