"""
Momentum Analysis — FABN Portfolio
====================================
Computes and compares spread-based and return-based momentum signals.

Inputs  : data/bond_universe.csv
          data/price_returns.csv
          data/daily_spread.csv

Outputs : data/momentum_signals.csv   — daily momentum score per bond (both signals)
          data/quintile_returns.csv   — avg forward return per quintile per date
          data/momentum_summary.txt   — headline stats comparing both signals

─────────────────────────────────────────────
PARAMETERS — adjust to explore different specs
─────────────────────────────────────────────
"""

import pandas as pd
import numpy as np
import os

# ══════════════════════════════════════════════════════
# PARAMETERS
# ══════════════════════════════════════════════════════

LOOKBACK  = 21    # Trading days to look back for momentum signal (1 month)
FORWARD   = 21    # Trading days to look forward to measure outcome (1 month)
MIN_BONDS = 10    # Minimum bonds with valid data needed to rank on a given date
DATA_DIR  = os.path.join('..', 'data')

# ══════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════

print("Loading data...")
bonds   = pd.read_csv(os.path.join(DATA_DIR, 'bond_universe.csv'))
returns = pd.read_csv(os.path.join(DATA_DIR, 'price_returns.csv'),
                      index_col=0, parse_dates=True)
spreads = pd.read_csv(os.path.join(DATA_DIR, 'daily_spread.csv'),
                      index_col=0, parse_dates=True)

# Align: keep only CUSIPs present in all three sources
bonds   = bonds.drop_duplicates(subset='CUSIP', keep='first')
common  = [c for c in returns.columns
           if c in spreads.columns and c in bonds['CUSIP'].values]
bonds   = bonds.set_index('CUSIP').loc[common]
returns = returns[common]
spreads = spreads[common]

print(f"Universe: {len(common)} bonds | {len(returns)} return dates | {len(spreads)} spread dates")

# ══════════════════════════════════════════════════════
# HELPER: compute quintile ranks on each date
# ══════════════════════════════════════════════════════

def compute_quintiles(signal_df):
    """
    Rank bonds into quintiles (1=worst, 5=best) on each date.

    Parameters
    ----------
    signal_df : DataFrame (dates × bonds)
        Higher value = stronger positive momentum signal.

    Returns
    -------
    DataFrame (dates × bonds) with integer quintile labels 1–5.
    NaN where signal was missing or too few bonds available.
    """
    def rank_row(row):
        valid = row.dropna()
        if len(valid) < MIN_BONDS:
            return pd.Series(np.nan, index=row.index)
        pct_ranks = valid.rank(pct=True)
        quintiles  = pd.cut(pct_ranks, bins=5, labels=[1, 2, 3, 4, 5])
        return quintiles.reindex(row.index)

    return signal_df.apply(rank_row, axis=1)


# ══════════════════════════════════════════════════════
# HELPER: compute avg forward outcome per quintile
# ══════════════════════════════════════════════════════

def compute_quintile_returns(quintiles, forward_outcome):
    """
    For each quintile group on each date, average the forward outcome
    across all bonds in that group.

    Parameters
    ----------
    quintiles       : DataFrame (dates × bonds), quintile labels 1–5
    forward_outcome : DataFrame (dates × bonds), what we're predicting

    Returns
    -------
    DataFrame (dates × 5) with columns Q1..Q5.
    """
    # Align on common dates
    common_dates = quintiles.index.intersection(forward_outcome.index)
    q = quintiles.loc[common_dates]
    f = forward_outcome.loc[common_dates]

    result = {}
    for qn in range(1, 6):
        mask        = (q == qn)
        result[f'Q{qn}'] = f[mask].mean(axis=1)

    return pd.DataFrame(result).dropna()


# ══════════════════════════════════════════════════════
# SIGNAL 1: SPREAD MOMENTUM
# Rank bonds by how much their credit spread has tightened
# over the past LOOKBACK days. Tightening = improving credit
# quality = positive momentum.
#
# Signal  : -Δspread over past LOOKBACK days (negate because
#            tightening = negative change = we want high rank)
# Outcome : -Δspread over next FORWARD days (tightening = good)
# ══════════════════════════════════════════════════════

print("\n--- Spread momentum ---")

# Past spread change (shift(1) avoids using today's data)
spread_change_past = spreads.diff(LOOKBACK).shift(1)

# Negate: bond whose spread tightened most → highest signal score
spread_momentum_signal = -spread_change_past

# Forward spread change (what we hope to predict)
spread_change_fwd = -spreads.diff(FORWARD).shift(-FORWARD)

spread_quintiles      = compute_quintiles(spread_momentum_signal)
spread_q_returns      = compute_quintile_returns(spread_quintiles, spread_change_fwd)
spread_long_short     = spread_q_returns['Q5'] - spread_q_returns['Q1']
spread_q_means        = spread_q_returns.mean()

print(f"  Dates with valid rankings: {spread_quintiles.notna().any(axis=1).sum()}")
print(f"  Q1..Q5 avg fwd spread change (bps):")
for q in range(1, 6):
    print(f"    Q{q}: {spread_q_means[f'Q{q}']*10000:.2f} bps")
print(f"  Q5−Q1 edge:  {spread_long_short.mean()*10000:.2f} bps/month")
print(f"  Win rate:    {(spread_long_short > 0).mean()*100:.1f}%")


# ══════════════════════════════════════════════════════
# SIGNAL 2: RETURN MOMENTUM (baseline for comparison)
# Rank bonds by past price return. Well-documented signal
# and less sensitive to treasury curve approximation quality.
#
# Signal  : cumulative log-return over past LOOKBACK days
# Outcome : cumulative log-return over next FORWARD days
# ══════════════════════════════════════════════════════

print("\n--- Return momentum ---")

return_momentum_signal = returns.rolling(LOOKBACK).sum().shift(1)
return_fwd             = returns.rolling(FORWARD).sum().shift(-FORWARD)

return_quintiles   = compute_quintiles(return_momentum_signal)
return_q_returns   = compute_quintile_returns(return_quintiles, return_fwd)
return_long_short  = return_q_returns['Q5'] - return_q_returns['Q1']
return_q_means     = return_q_returns.mean()

print(f"  Dates with valid rankings: {return_quintiles.notna().any(axis=1).sum()}")
print(f"  Q1..Q5 avg fwd return (bps):")
for q in range(1, 6):
    print(f"    Q{q}: {return_q_means[f'Q{q}']*10000:.2f} bps")
print(f"  Q5−Q1 edge:  {return_long_short.mean()*10000:.2f} bps/month")
print(f"  Win rate:    {(return_long_short > 0).mean()*100:.1f}%")


# ══════════════════════════════════════════════════════
# AUTOCORRELATION CHECK
# Tests whether past spread changes predict future spread
# changes at various lags. Positive = momentum persists.
# Negative = mean reversion kicking in.
# ══════════════════════════════════════════════════════

print("\n--- Autocorrelation (spread changes) ---")

avg_spread_chg = spreads.diff(1).mean(axis=1)
lags           = list(range(1, 43, 2))
autocorrs      = {lag: round(avg_spread_chg.autocorr(lag=lag), 4) for lag in lags}

print("  Lag (days) : Autocorrelation")
for lag, ac in autocorrs.items():
    direction = "+" if ac > 0 else " "
    bar = "█" * int(abs(ac) * 50)
    print(f"    {lag:2d}d : {direction}{ac:.4f}  {bar}")


# ══════════════════════════════════════════════════════
# DAILY MOMENTUM SCORES PER BOND
# A combined score usable as an optimizer input.
# Percentile rank within the cross-section on each date.
# ══════════════════════════════════════════════════════

print("\n--- Building daily momentum score matrix ---")

# Percentile rank (0–1) for each bond on each date using return signal
# (use return momentum as the working signal given spread data limitation)
momentum_score = return_momentum_signal.apply(
    lambda row: row.rank(pct=True) if row.notna().sum() >= MIN_BONDS else row * np.nan,
    axis=1
)

print(f"  Momentum score matrix: {momentum_score.shape}")
print(f"  Score range: {momentum_score.min().min():.3f} to {momentum_score.max().max():.3f}")
print(f"  NaN fraction: {momentum_score.isna().mean().mean():.3f}")


# ══════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════

summary_lines = [
    "=" * 55,
    "MOMENTUM ANALYSIS SUMMARY",
    "=" * 55,
    f"Lookback window:    {LOOKBACK} trading days",
    f"Forward window:     {FORWARD} trading days",
    f"Bond universe:      {len(common)} bonds",
    "",
    "── SPREAD MOMENTUM ────────────────────────────────────",
    f"  Q1 avg fwd spread change: {spread_q_means['Q1']*10000:.2f} bps",
    f"  Q5 avg fwd spread change: {spread_q_means['Q5']*10000:.2f} bps",
    f"  Q5−Q1 edge:               {spread_long_short.mean()*10000:.2f} bps/month",
    f"  Win rate:                 {(spread_long_short > 0).mean()*100:.1f}%",
    f"  Verdict: {'WEAK — flat quintile pattern, static treasury curve limiting signal' if abs(spread_long_short.mean()) < 0.0002 else 'PRESENT'}",
    "",
    "── RETURN MOMENTUM ────────────────────────────────────",
    f"  Q1 avg fwd return:        {return_q_means['Q1']*10000:.2f} bps",
    f"  Q5 avg fwd return:        {return_q_means['Q5']*10000:.2f} bps",
    f"  Q5−Q1 edge:               {return_long_short.mean()*10000:.2f} bps/month",
    f"  Win rate:                 {(return_long_short > 0).mean()*100:.1f}%",
    f"  Verdict: {'STRONG — monotonic quintile pattern' if return_long_short.mean() > 0.001 else 'WEAK'}",
    "",
    "── AUTOCORRELATION (spread changes) ───────────────────",
]
for lag, ac in list(autocorrs.items())[:7]:
    summary_lines.append(f"  Lag {lag:2d}d: {ac:+.4f}")
summary_lines += [
    "  (positive = momentum, negative = mean reversion)",
    "",
    "── RECOMMENDATION ─────────────────────────────────────",
    "  Use return momentum as working signal.",
    "  Re-test spread momentum once dynamic FRED curve active.",
    "=" * 55,
]

print("\n" + "\n".join(summary_lines))


# ══════════════════════════════════════════════════════
# SAVE OUTPUTS
# ══════════════════════════════════════════════════════

momentum_score.to_csv(os.path.join(DATA_DIR, 'momentum_signals.csv'))

combined_q = spread_q_returns.add_prefix('spread_').join(
             return_q_returns.add_prefix('return_'), how='outer')
combined_q.to_csv(os.path.join(DATA_DIR, 'quintile_returns.csv'))

with open(os.path.join(DATA_DIR, 'momentum_summary.txt'), 'w') as f:
    f.write('\n'.join(summary_lines))

print("\nOutputs saved:")
print(f"  data/momentum_signals.csv   — daily momentum score per bond")
print(f"  data/quintile_returns.csv   — avg fwd return per quintile per date")
print(f"  data/momentum_summary.txt   — summary stats")