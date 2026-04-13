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
    common_dates = quintiles.index.intersection(forward_outcome.index)
    q = quintiles.loc[common_dates]
    f = forward_outcome.loc[common_dates]

    result = {}
    for qn in range(1, 6):
        mask = (q == qn)
        result[f'Q{qn}'] = f[mask].mean(axis=1)

    return pd.DataFrame(result).dropna()


def verdict_spread(edge_bps, win_rate):
    """
    Classify spread momentum signal direction and strength.
    Checks sign explicitly — negative edge = mean reversion, not momentum.
    """
    if edge_bps > 1.0 and win_rate > 0.55:
        return "MOMENTUM — bonds that tightened keep tightening"
    elif edge_bps < -1.0 and win_rate < 0.45:
        return "MEAN REVERSION — recent tighteners give it back (negative edge)"
    else:
        return "WEAK / INCONCLUSIVE — no reliable directional signal"


def verdict_return(edge_bps, win_rate):
    """Classify return momentum signal."""
    if edge_bps > 5.0 and win_rate > 0.55:
        return "STRONG — clear monotonic quintile pattern"
    elif edge_bps > 1.0:
        return "MODERATE — present but modest"
    else:
        return "WEAK"


# ══════════════════════════════════════════════════════
# SIGNAL 1: SPREAD MOMENTUM (21-day)
# Rank bonds by how much their credit spread has tightened
# over the past LOOKBACK days. Tightening = improving credit
# quality = positive momentum signal.
#
# Signal  : -Δspread over past LOOKBACK days (negate so that
#            tightening = positive = high rank)
# Outcome : -Δspread over next FORWARD days (tightening = good)
# ══════════════════════════════════════════════════════

print("\n--- Spread momentum (21-day) ---")

spread_change_past     = spreads.diff(LOOKBACK).shift(1)
spread_momentum_signal = -spread_change_past          # negate: tightening → high rank
spread_change_fwd      = -spreads.diff(FORWARD).shift(-FORWARD)

spread_quintiles  = compute_quintiles(spread_momentum_signal)
spread_q_returns  = compute_quintile_returns(spread_quintiles, spread_change_fwd)
spread_long_short = spread_q_returns['Q5'] - spread_q_returns['Q1']
spread_q_means    = spread_q_returns.mean()
spread_edge_bps   = spread_long_short.mean() * 10000
spread_win_rate   = (spread_long_short > 0).mean()

print(f"  Dates with valid rankings: {spread_quintiles.notna().any(axis=1).sum()}")
print(f"  Q1..Q5 avg fwd spread change (bps):")
for q in range(1, 6):
    print(f"    Q{q}: {spread_q_means[f'Q{q}']*10000:.2f} bps")
print(f"  Q5−Q1 edge:  {spread_edge_bps:.2f} bps/month")
print(f"  Win rate:    {spread_win_rate*100:.1f}%")
print(f"  Verdict:     {verdict_spread(spread_edge_bps, spread_win_rate)}")


# ══════════════════════════════════════════════════════
# SIGNAL 1B: SPREAD MOMENTUM (7-day)
# Shorter lookback to test weekly-horizon persistence,
# motivated by the positive autocorrelation at lag 7.
# ══════════════════════════════════════════════════════

print("\n--- Spread momentum (7-day) ---")

SHORT_WINDOW = 7
spread_signal_7d  = -(spreads.diff(SHORT_WINDOW).shift(1))
spread_fwd_7d     = -(spreads.diff(SHORT_WINDOW).shift(-SHORT_WINDOW))

spread_q5_7d      = compute_quintiles(spread_signal_7d)
spread_qr_7d      = compute_quintile_returns(spread_q5_7d, spread_fwd_7d)
spread_ls_7d      = spread_qr_7d['Q5'] - spread_qr_7d['Q1']
spread_means_7d   = spread_qr_7d.mean()
edge_7d_bps       = spread_ls_7d.mean() * 10000
win_rate_7d       = (spread_ls_7d > 0).mean()

print(f"  Dates with valid rankings: {spread_q5_7d.notna().any(axis=1).sum()}")
print(f"  Q1..Q5 avg fwd spread change (bps):")
for q in range(1, 6):
    print(f"    Q{q}: {spread_means_7d[f'Q{q}']*10000:.2f} bps")
print(f"  Q5−Q1 edge:  {edge_7d_bps:.2f} bps/month")
print(f"  Win rate:    {win_rate_7d*100:.1f}%")
print(f"  Verdict:     {verdict_spread(edge_7d_bps, win_rate_7d)}")


# ══════════════════════════════════════════════════════
# SIGNAL 2: RETURN MOMENTUM (baseline for comparison)
# Rank bonds by past price return. Less sensitive to
# treasury curve quality — useful as a stable benchmark.
#
# Signal  : cumulative log-return over past LOOKBACK days
# Outcome : cumulative log-return over next FORWARD days
# ══════════════════════════════════════════════════════

print("\n--- Return momentum (21-day) ---")

return_momentum_signal = returns.rolling(LOOKBACK).sum().shift(1)
return_fwd             = returns.rolling(FORWARD).sum().shift(-FORWARD)

return_quintiles   = compute_quintiles(return_momentum_signal)
return_q_returns   = compute_quintile_returns(return_quintiles, return_fwd)
return_long_short  = return_q_returns['Q5'] - return_q_returns['Q1']
return_q_means     = return_q_returns.mean()
return_edge_bps    = return_long_short.mean() * 10000
return_win_rate    = (return_long_short > 0).mean()

print(f"  Dates with valid rankings: {return_quintiles.notna().any(axis=1).sum()}")
print(f"  Q1..Q5 avg fwd return (bps):")
for q in range(1, 6):
    print(f"    Q{q}: {return_q_means[f'Q{q}']*10000:.2f} bps")
print(f"  Q5−Q1 edge:  {return_edge_bps:.2f} bps/month")
print(f"  Win rate:    {return_win_rate*100:.1f}%")
print(f"  Verdict:     {verdict_return(return_edge_bps, return_win_rate)}")


# ══════════════════════════════════════════════════════
# AUTOCORRELATION CHECK
# Tests whether past spread changes predict future ones
# at various lags. Positive = momentum. Negative = reversion.
# The strong -0.41 at lag 1 is bid-ask bounce (microstructure
# noise), not a tradeable signal. Focus on lags 5+.
# ══════════════════════════════════════════════════════

print("\n--- Autocorrelation (spread changes) ---")

avg_spread_chg = spreads.diff(1).mean(axis=1)
lags           = list(range(1, 43, 2))
autocorrs      = {lag: round(avg_spread_chg.autocorr(lag=lag), 4) for lag in lags}

print("  Lag (days) : Autocorrelation")
for lag, ac in autocorrs.items():
    sign = "+" if ac > 0 else " "
    bar  = "█" * int(abs(ac) * 50)
    note = " ← bid-ask bounce (ignore)" if lag == 1 and ac < -0.3 else \
           " ← weekly momentum" if lag == 7 and ac > 0.1 else ""
    print(f"    {lag:2d}d : {sign}{ac:.4f}  {bar}{note}")


# ══════════════════════════════════════════════════════
# DAILY MOMENTUM SCORES PER BOND
# Percentile rank (0–1) per bond per date.
# Uses return momentum as the primary working signal —
# spread mean reversion at 21d makes spread-based ranking
# counterproductive at that horizon.
# ══════════════════════════════════════════════════════

print("\n--- Building daily momentum score matrix ---")

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

# Determine working signal recommendation
if return_edge_bps > 5.0 and return_win_rate > 0.55:
    working_signal = "Return momentum (21-day) — strong, stable signal"
elif edge_7d_bps > 1.0 and win_rate_7d > 0.55:
    working_signal = "Spread momentum (7-day) — weekly persistence detected"
else:
    working_signal = "Return momentum (21-day) — best available signal"

summary_lines = [
    "=" * 57,
    "MOMENTUM ANALYSIS SUMMARY",
    "=" * 57,
    f"Lookback window (primary): {LOOKBACK} trading days",
    f"Forward window (primary):  {FORWARD} trading days",
    f"Short window (7-day test): {SHORT_WINDOW} trading days",
    f"Bond universe:             {len(common)} bonds",
    "",
    "── SPREAD MOMENTUM (21-day) ───────────────────────────",
    f"  Q1 avg fwd spread change: {spread_q_means['Q1']*10000:.2f} bps",
    f"  Q5 avg fwd spread change: {spread_q_means['Q5']*10000:.2f} bps",
    f"  Q5−Q1 edge:               {spread_edge_bps:.2f} bps/month",
    f"  Win rate:                 {spread_win_rate*100:.1f}%",
    f"  Verdict: {verdict_spread(spread_edge_bps, spread_win_rate)}",
    "",
    "── SPREAD MOMENTUM (7-day) ────────────────────────────",
    f"  Q1 avg fwd spread change: {spread_means_7d['Q1']*10000:.2f} bps",
    f"  Q5 avg fwd spread change: {spread_means_7d['Q5']*10000:.2f} bps",
    f"  Q5−Q1 edge:               {edge_7d_bps:.2f} bps/month",
    f"  Win rate:                 {win_rate_7d*100:.1f}%",
    f"  Verdict: {verdict_spread(edge_7d_bps, win_rate_7d)}",
    "",
    "── RETURN MOMENTUM (21-day) ───────────────────────────",
    f"  Q1 avg fwd return:        {return_q_means['Q1']*10000:.2f} bps",
    f"  Q5 avg fwd return:        {return_q_means['Q5']*10000:.2f} bps",
    f"  Q5−Q1 edge:               {return_edge_bps:.2f} bps/month",
    f"  Win rate:                 {return_win_rate*100:.1f}%",
    f"  Verdict: {verdict_return(return_edge_bps, return_win_rate)}",
    "",
    "── AUTOCORRELATION NOTE ───────────────────────────────",
    "  Lag-1 autocorr near -0.41 = bid-ask bounce, not signal.",
    "  Focus on lags 5+ for tradeable persistence.",
    f"  Lag-7 autocorr: {autocorrs.get(7, 'N/A'):+.4f}",
    "",
    "── WORKING SIGNAL ─────────────────────────────────────",
    f"  {working_signal}",
    "  Spread mean reversion at 21d: avoid using spread",
    "  tightening as a buy signal at monthly horizon.",
    "=" * 57,
]

print("\n" + "\n".join(summary_lines))


# ══════════════════════════════════════════════════════
# SAVE OUTPUTS
# ══════════════════════════════════════════════════════

momentum_score.to_csv(os.path.join(DATA_DIR, 'momentum_signals.csv'))

combined_q = (spread_q_returns.add_prefix('spread21_')
              .join(spread_qr_7d.add_prefix('spread7_'),  how='outer')
              .join(return_q_returns.add_prefix('return_'), how='outer'))
combined_q.to_csv(os.path.join(DATA_DIR, 'quintile_returns.csv'))

with open(os.path.join(DATA_DIR, 'momentum_summary.txt'), 'w') as f:
    f.write('\n'.join(summary_lines))

print("\nOutputs saved:")
print(f"  data/momentum_signals.csv   — daily momentum score per bond")
print(f"  data/quintile_returns.csv   — avg fwd return per quintile (all 3 signals)")
print(f"  data/momentum_summary.txt   — summary stats")