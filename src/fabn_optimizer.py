"""
FABN Portfolio Optimizer + Backtest
=====================================
Reads outputs from fabn_pipeline.py and runs:
  1. Static baseline  — optimise once on day 0, hold forever
  2. Dynamic strategy — re-optimise on each volatility trigger date

Outputs:
  backtest_results.csv   — daily portfolio value, spread, weights for both strategies
  rebalance_log.csv      — one row per rebalance event (trigger date, TC paid, spread change)
  backtest_summary.txt   — headline metrics comparison

─────────────────────────────────────────────────────────────
TEAM INPUTS  ← swap these placeholders before production run
─────────────────────────────────────────────────────────────
"""

import numpy as np
import pandas as pd
import cvxpy as cp

# ══════════════════════════════════════════════════════════════
# TEAM INPUTS — replace with actual values from your FABN design
# ══════════════════════════════════════════════════════════════

D_LIAB        = 2.5      # Duration of FABN liabilities (years)
                          # → derive from your FABN payment schedule

R_FABN        = 0.045    # Coupon rate owed to FABN investors (4.5%)
                          # → set by your FABN term sheet

V             = 1.0      # Portfolio value (normalised to 1)
                          # → scale to actual $ if needed; RBC limits scale with it

RBC_C1_LIMIT  = 0.008    # Max C1 capital charge as fraction of V (0.8%)
                          # → from your internal risk framework

RBC_C3_LIMIT  = 0.020    # Max C3 capital charge as fraction of V (2.0%)
                          # → from your internal risk framework

DUR_TOL       = 0.25     # Allowed duration mismatch (±0.25 years)
                          # → tighten for stricter ALM, loosen for more yield flexibility

LAMBDA        = 10.0     # Transaction cost penalty weight
                          # → higher = fewer, smaller rebalances
                          # → lower  = more aggressive rebalancing

# ══════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════

print("Loading data...")
bonds   = pd.read_csv('../data/bond_universe.csv')
returns = pd.read_csv('../data/price_returns.csv',   index_col=0, parse_dates=True)
spreads = pd.read_csv('../data/daily_spread.csv',    index_col=0, parse_dates=True)
triggers = pd.read_csv('../data/volatility_triggers.csv', parse_dates=['date'])

# Remove duplicate CUSIPs (keep first), align to returns column order
bonds = bonds.drop_duplicates(subset='CUSIP', keep='first')
bonds = bonds.set_index('CUSIP').loc[returns.columns]
cusips = bonds.index.tolist()
n = len(cusips)

# Static bond features (used for baseline and as starting point for dynamic)
Y_STATIC  = bonds['current_yield'].values     # yields at snapshot date
D_STATIC  = bonds['duration'].values          # durations
C1        = bonds['c1_factor'].values         # C1 RBC factors (fixed — rating-based)
C3        = bonds['c3_factor'].values         # C3 RBC factors (fixed — duration bucket)

trigger_dates = set(pd.to_datetime(triggers['date']))

print(f"Universe: {n} bonds | {len(returns)} trading days | {len(trigger_dates)} trigger dates")

# ══════════════════════════════════════════════════════════════
# CORE OPTIMIZER
# ══════════════════════════════════════════════════════════════

def solve(y, D, c1, c3, w0, tc_spread):
    """
    Solve the portfolio optimisation problem.

    Parameters
    ----------
    y          : (n,) yield vector for each bond
    D          : (n,) duration vector
    c1         : (n,) C1 RBC factor per bond
    c3         : (n,) C3 RBC factor per bond
    w0         : (n,) current portfolio weights (used to compute TC)
    tc_spread  : (n,) bid-ask spread for each bond on this date (as fraction)

    Returns
    -------
    w_opt   : (n,) optimal weights, or w0 if problem is infeasible
    net_spread : float, spread earned minus r_fabn minus TC
    status  : str, solver status
    """
    w = cp.Variable(n)
    t = cp.Variable(n)          # auxiliary: t[i] >= |w[i] - w0[i]|
                                 # LP reformulation of weighted L1 TC cost
    tc = (tc_spread / 2) @ t    # half-spread per unit traded (one-way cost)

    objective = cp.Maximize(y @ w - R_FABN - LAMBDA * tc)

    constraints = [
        cp.sum(w) == 1,                          # fully invested
        w >= 0,                                  # long only
        t >= w - w0,                             # |w - w0| upper bound (positive side)
        t >= -(w - w0),                          # |w - w0| upper bound (negative side)
        cp.abs(D @ w - D_LIAB) <= DUR_TOL,       # ALM duration match
        c1 @ w * V <= RBC_C1_LIMIT,              # C1 capital constraint
        c3 @ w * V <= RBC_C3_LIMIT,              # C3 capital constraint
    ]

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.CLARABEL, verbose=False)

    if prob.status in ('optimal', 'optimal_inaccurate') and w.value is not None:
        w_opt = np.clip(w.value, 0, 1)
        w_opt /= w_opt.sum()     # re-normalise to handle tiny numerical drift
        net_spread = float(y @ w_opt) - R_FABN
        return w_opt, net_spread, prob.status
    else:
        # Infeasible / solver failure — hold current portfolio
        net_spread = float(y @ w0) - R_FABN
        return w0.copy(), net_spread, prob.status


def get_tc_spread(date):
    """
    Look up bid-ask spread for a given date.
    Falls back to nearest available date if exact date missing.
    Returns spread as a decimal fraction (not price points).
    """
    sp_raw = spreads[cusips].asof(date).values / 100
    sp = np.where(np.isnan(sp_raw), np.nanmean(sp_raw), sp_raw)
    return sp


def get_yield_duration(date, price_series):
    """
    Approximate updated yield and duration on a given rebalance date.

    Yield: adjusted by price change since snapshot
      y_new ≈ y_static * (P_static / P_current)
      Rationale: if price falls, yield rises proportionally (rough approximation).
      For production, replace with a proper YTM calculation.

    Duration: adjusted by time elapsed (duration shortens as bonds age)
      D_new ≈ D_static - years_elapsed
    """
    if date not in price_series.index:
        return Y_STATIC.copy(), D_STATIC.copy()

    # Price relative to first date in price series (used as proxy for "snapshot" price)
    p0   = price_series.iloc[0].values
    p_t  = price_series.loc[date].values
    p0   = np.where(p0 == 0, 1, p0)    # avoid div by zero

    y_t = Y_STATIC * (p0 / p_t)
    y_t = np.clip(y_t, 0.001, 0.20)    # bound to sensible yield range

    years_elapsed = (date - price_series.index[0]).days / 365.25
    d_t = np.clip(D_STATIC - years_elapsed, 0.01, None)

    return y_t, d_t


# ══════════════════════════════════════════════════════════════
# STRATEGY 1: STATIC BASELINE
# Solve once on day 0, hold those weights for the full 2 years
# ══════════════════════════════════════════════════════════════

print("\n--- Static baseline ---")

w_equal    = np.ones(n) / n          # equal-weight starting point
tc_day0    = get_tc_spread(returns.index[0])

w_static, _, status_static = solve(Y_STATIC, D_STATIC, C1, C3, w_equal, tc_day0)
print(f"  Status: {status_static}")
print(f"  Yield:    {float(Y_STATIC @ w_static):.4f}")
print(f"  Duration: {float(D_STATIC @ w_static):.4f}  (target {D_LIAB})")
print(f"  C1 charge:{float(C1 @ w_static):.5f}  (limit {RBC_C1_LIMIT})")
print(f"  C3 charge:{float(C3 @ w_static):.5f}  (limit {RBC_C3_LIMIT})")
print(f"  Net spread (day 0): {float(Y_STATIC @ w_static) - R_FABN:.4f}")
print(f"  Nonzero positions:  {(w_static > 0.001).sum()}")

# ══════════════════════════════════════════════════════════════
# STRATEGY 2: DYNAMIC REOPTIMISATION
# Re-solve on each volatility trigger date using updated yields/durations/spreads
# ══════════════════════════════════════════════════════════════

print("\n--- Dynamic strategy ---")

price_df = pd.read_csv('../data/price_returns.csv', index_col=0, parse_dates=True)
# Reconstruct price levels from returns (base = 100 at first date)
# We need price levels for yield/duration updating
price_levels = 100 * (1 + price_df[cusips]).cumprod()
price_levels.iloc[0] = 100      # set base

w_dynamic = w_equal.copy()      # start equal-weight, same as baseline
rebalance_log = []

for tdate in sorted(trigger_dates):
    if tdate not in returns.index:
        continue

    y_t, d_t  = get_yield_duration(tdate, price_levels)
    tc_t      = get_tc_spread(tdate)
    w_prev    = w_dynamic.copy()

    w_new, net_spread, status = solve(y_t, d_t, C1, C3, w_prev, tc_t)

    # Actual TC paid this rebalance (half spread × turnover)
    turnover   = float(np.sum(np.abs(w_new - w_prev)))
    tc_paid    = float((tc_t / 2) @ np.abs(w_new - w_prev))
    spread_old = float(y_t @ w_prev) - R_FABN
    spread_new = float(y_t @ w_new)  - R_FABN

    rebalance_log.append({
        'date':          tdate,
        'status':        status,
        'spread_before': round(spread_old, 6),
        'spread_after':  round(spread_new, 6),
        'spread_gain':   round(spread_new - spread_old, 6),
        'turnover':      round(turnover, 4),
        'tc_paid':       round(tc_paid, 6),
        'net_gain':      round(spread_new - spread_old - tc_paid, 6),
        'n_positions':   int((w_new > 0.001).sum()),
        'duration':      round(float(d_t @ w_new), 4),
        'c1_charge':     round(float(C1 @ w_new), 6),
        'c3_charge':     round(float(C3 @ w_new), 6),
    })

    w_dynamic = w_new

print(f"  Rebalances executed: {len(rebalance_log)}")
rebalance_df = pd.DataFrame(rebalance_log)
if len(rebalance_df):
    print(f"  Avg spread gain per rebalance: {rebalance_df['spread_gain'].mean():.5f}")
    print(f"  Avg TC paid per rebalance:     {rebalance_df['tc_paid'].mean():.5f}")
    print(f"  Rebalances with net_gain > 0:  {(rebalance_df['net_gain'] > 0).sum()}/{len(rebalance_df)}")

# ══════════════════════════════════════════════════════════════
# BACKTEST: simulate daily P&L for both strategies
# ══════════════════════════════════════════════════════════════

print("\n--- Backtest simulation ---")

# Reconstruct dynamic weight history: weights are constant between rebalances
# Build a dict of {rebalance_date: weights} then forward-fill
weight_history = {returns.index[0]: w_equal.copy()}   # both start equal-weight
w_running = w_equal.copy()
for row in rebalance_log:
    weight_history[row['date']] = w_running
    # apply new weights after this date
    idx = rebalance_log.index(row)
    # get updated weights from rebalance (re-solve to recover them)
    tdate = row['date']
    y_t, d_t = get_yield_duration(tdate, price_levels)
    tc_t = get_tc_spread(tdate)
    w_new, _, _ = solve(y_t, d_t, C1, C3, w_running, tc_t)
    w_running = w_new

daily_records = []
w_dyn_current = w_equal.copy()
rebalance_dates = {r['date'] for r in rebalance_log}

for i, date in enumerate(returns.index):
    r = returns.loc[date, cusips].values      # daily log returns

    # Update weights by return (weights drift with price moves)
    if i > 0:
        price_growth = np.exp(r)
        w_static_drifted  = w_static * price_growth
        w_static_drifted /= w_static_drifted.sum()

        w_dyn_drifted  = w_dyn_current * price_growth
        w_dyn_drifted /= w_dyn_drifted.sum()
    else:
        w_static_drifted = w_static.copy()
        w_dyn_drifted    = w_dyn_current.copy()

    # If this is a rebalance date, snap dynamic weights to reoptimised weights
    if date in rebalance_dates:
        y_t, d_t = get_yield_duration(date, price_levels)
        tc_t     = get_tc_spread(date)
        w_dyn_current, _, _ = solve(y_t, d_t, C1, C3, w_dyn_drifted, tc_t)
    else:
        w_dyn_current = w_dyn_drifted.copy()

    # Daily spread earned: w · y (using snapshot yields as proxy)
    static_spread  = float(Y_STATIC @ w_static_drifted) - R_FABN
    dynamic_spread = float(Y_STATIC @ w_dyn_current)    - R_FABN

    # TC drag on rebalance days
    static_tc  = 0.0
    dynamic_tc = 0.0
    if date in rebalance_dates:
        row = next(r for r in rebalance_log if r['date'] == date)
        dynamic_tc = row['tc_paid']

    daily_records.append({
        'date':             date,
        'static_spread':    round(static_spread,  6),
        'dynamic_spread':   round(dynamic_spread, 6),
        'spread_advantage': round(dynamic_spread - static_spread, 6),
        'static_tc':        0.0,
        'dynamic_tc':       round(dynamic_tc, 6),
        'is_trigger':       date in trigger_dates,
    })

results = pd.DataFrame(daily_records).set_index('date')

# Cumulative spread captured (annualised daily spread × 1/252)
results['static_cumspread']  = (results['static_spread']  / 252).cumsum()
results['dynamic_cumspread'] = (results['dynamic_spread'] / 252 - results['dynamic_tc']).cumsum()
results['cumspread_gap']     = results['dynamic_cumspread'] - results['static_cumspread']

# ══════════════════════════════════════════════════════════════
# SUMMARY METRICS
# ══════════════════════════════════════════════════════════════

T = len(results)
summary_lines = [
    "=" * 55,
    "FABN BACKTEST SUMMARY",
    "=" * 55,
    f"Period:             {results.index[0].date()} to {results.index[-1].date()}",
    f"Trading days:       {T}",
    f"Bond universe:      {n} bonds",
    "",
    "── ASSUMPTIONS (placeholders — update before production) ──",
    f"  D_liab:           {D_LIAB} years",
    f"  r_FABN:           {R_FABN:.1%}",
    f"  RBC C1 limit:     {RBC_C1_LIMIT:.1%} of V",
    f"  RBC C3 limit:     {RBC_C3_LIMIT:.1%} of V",
    f"  Duration tol:     ±{DUR_TOL} years",
    f"  Lambda (TC wt):   {LAMBDA}",
    "",
    "── STATIC BASELINE ────────────────────────────────────────",
    f"  Avg daily spread: {results['static_spread'].mean():.4f}",
    f"  Annualised spread:{results['static_spread'].mean() * 252:.4f}",
    f"  Cumulative spread:{results['static_cumspread'].iloc[-1]:.4f}",
    f"  Rebalances:       0",
    f"  Total TC paid:    0.0000",
    "",
    "── DYNAMIC STRATEGY ────────────────────────────────────────",
    f"  Avg daily spread: {results['dynamic_spread'].mean():.4f}",
    f"  Annualised spread:{results['dynamic_spread'].mean() * 252:.4f}",
    f"  Cumulative spread:{results['dynamic_cumspread'].iloc[-1]:.4f}",
    f"  Rebalances:       {len(rebalance_log)}",
    f"  Total TC paid:    {results['dynamic_tc'].sum():.4f}",
    f"  Net cum. spread:  {results['dynamic_cumspread'].iloc[-1]:.4f}",
    "",
    "── COMPARISON ──────────────────────────────────────────────",
    f"  Spread advantage: {results['spread_advantage'].mean():.4f} (avg daily)",
    f"  Cum. gap:         {results['cumspread_gap'].iloc[-1]:.4f}",
    f"  Trigger dates:    {len(trigger_dates)}",
    f"  Rebalances with net_gain > 0: "
    f"{(rebalance_df['net_gain'] > 0).sum() if len(rebalance_df) else 0}/{len(rebalance_log)}",
    "=" * 55,
]

print("\n" + "\n".join(summary_lines))

# ══════════════════════════════════════════════════════════════
# SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════

results.to_csv('../data/backtest_results.csv')
rebalance_df.to_csv('../data/rebalance_log.csv', index=False)

with open('../data/backtest_summary.txt', 'w') as f:
    f.write('\n'.join(summary_lines))

print("\nOutputs saved: ../data/backtest_results.csv, ../data/rebalance_log.csv, ../data/backtest_summary.txt")