"""
Mean Reversion Analysis — CIR Model
=====================================
Simulates and analyzes interest rate mean reversion using the
Cox-Ingersoll-Ross (CIR) model in the context of FABN portfolio optimization.

Parameters defined in PARAMETERS section below.
All outputs are printed/displayed inline — no external files saved.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ══════════════════════════════════════════════════════
# PARAMETERS
# ══════════════════════════════════════════════════════

KAPPA       = 0.20      # Speed of mean reversion (NAIC typical: 0.15-0.25)
THETA       = 0.045     # Long-run mean (MRP) — 4.5% annualized
SIGMA       = 0.015     # Volatility — 1.5% annualized
R0          = 0.055     # Initial rate — 5.5% (above theta to show reversion)
N_SCENARIOS = 50        # Number of scenarios (NAIC C3 uses 50)
N_MONTHS    = 360       # Simulation horizon in months (30 years)
DT          = 1 / 12   # Monthly time step
FLOOR       = 0.0001   # Minimum rate floor (NAIC convention)
SEED        = 42        # Random seed for reproducibility

# ══════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════

def simulate_cir(kappa, theta, sigma, r0, n_scenarios, n_months, dt, floor, seed=None):
    """
    Simulate interest rate paths using the CIR model.

    Monthly discretization:
        r_{t+dt} = r_t + kappa*(theta - r_t)*dt
                       + sigma*sqrt(r_t)*sqrt(dt)*Z_t

    Parameters
    ----------
    kappa       : float — speed of mean reversion
    theta       : float — long-run mean level
    sigma       : float — volatility
    r0          : float — initial rate
    n_scenarios : int   — number of paths to simulate
    n_months    : int   — number of monthly steps
    dt          : float — time step (1/12 for monthly)
    floor       : float — minimum rate (NAIC floor)
    seed        : int   — random seed

    Returns
    -------
    rates : ndarray (n_months+1, n_scenarios)
    times : ndarray (n_months+1,) in years
    """
    if seed is not None:
        np.random.seed(seed)

    rates      = np.zeros((n_months + 1, n_scenarios))
    rates[0,:] = r0
    sqrt_dt    = np.sqrt(dt)

    for t in range(1, n_months + 1):
        r_prev = rates[t - 1, :]
        Z      = np.random.standard_normal(n_scenarios)
        dr     = (kappa * (theta - r_prev) * dt +
                  sigma * np.sqrt(np.maximum(r_prev, 0)) * sqrt_dt * Z)
        rates[t, :] = np.maximum(r_prev + dr, floor)

    times = np.arange(n_months + 1) * dt
    return rates, times


def check_feller(kappa, theta, sigma):
    """Check Feller condition: 2*kappa*theta >= sigma^2"""
    lhs = 2 * kappa * theta
    rhs = sigma ** 2
    return lhs >= rhs, lhs, rhs


def compute_halflife(kappa):
    """Theoretical half-life in years: ln(2) / kappa"""
    return np.log(2) / kappa


def compute_empirical_halflife(rates, theta, times):
    """
    Estimate empirical half-life from simulated paths.
    First time the average path is within 50% of initial deviation.
    """
    avg_path    = rates.mean(axis=1)
    initial_dev = abs(avg_path[0] - theta)
    half_dev    = initial_dev / 2
    for i, t in enumerate(times):
        if abs(avg_path[i] - theta) <= half_dev:
            return t
    return None


# ══════════════════════════════════════════════════════
# STEP 1 — FELLER CONDITION
# ══════════════════════════════════════════════════════

print("=" * 55)
print("CIR MODEL — MEAN REVERSION ANALYSIS")
print("=" * 55)

satisfied, lhs, rhs = check_feller(KAPPA, THETA, SIGMA)
halflife_theoretical = compute_halflife(KAPPA)

print(f"\nFeller Condition: 2κθ ≥ σ²")
print(f"  2 × {KAPPA} × {THETA} = {lhs:.6f}")
print(f"  σ²  = {SIGMA}² = {rhs:.6f}")
print(f"  Satisfied: {'YES ✓ — rates guaranteed positive' if satisfied else 'NO ✗ — rates may hit zero'}")
print(f"\nTheoretical half-life: ln(2) / {KAPPA} = {halflife_theoretical:.2f} years")

# ══════════════════════════════════════════════════════
# STEP 2 — SIMULATE BASE SCENARIOS
# ══════════════════════════════════════════════════════

print(f"\nSimulating {N_SCENARIOS} CIR scenarios...")
print(f"  κ={KAPPA}, θ={THETA:.1%}, σ={SIGMA:.1%}, r0={R0:.1%}")
print(f"  Horizon: {N_MONTHS} months ({N_MONTHS//12} years)")

rates, times = simulate_cir(
    KAPPA, THETA, SIGMA, R0,
    N_SCENARIOS, N_MONTHS, DT, FLOOR, SEED
)

avg_path  = rates.mean(axis=1)
std_path  = rates.std(axis=1)
p5_path   = np.percentile(rates, 5, axis=1)
p95_path  = np.percentile(rates, 95, axis=1)
final_avg = avg_path[-1]
final_std = std_path[-1]

empirical_hl = compute_empirical_halflife(rates, THETA, times)

print(f"\nResults at t=0:")
print(f"  Initial rate r₀:   {R0:.2%}")
print(f"  Long-run mean θ:   {THETA:.2%}")
print(f"  Initial deviation: {abs(R0 - THETA):.2%}")

print(f"\nResults at t={N_MONTHS//12} years:")
print(f"  Avg final rate:    {final_avg:.2%}")
print(f"  Std final rate:    {final_std:.2%}")
print(f"  Min final rate:    {rates[-1,:].min():.2%}")
print(f"  Max final rate:    {rates[-1,:].max():.2%}")

print(f"\nMean Reversion:")
print(f"  Theoretical half-life: {halflife_theoretical:.2f} years")
if empirical_hl:
    print(f"  Empirical half-life:   {empirical_hl:.2f} years")
print(f"  Final avg vs θ:        {abs(final_avg - THETA):.4%} difference")

# ══════════════════════════════════════════════════════
# STEP 3 — KAPPA COMPARISON
# ══════════════════════════════════════════════════════

print("\nSimulating κ comparison...")

kappa_configs = {
    'Slow  (κ=0.05)': 0.05,
    'Base  (κ=0.20)': 0.20,
    'Fast  (κ=0.50)': 0.50,
}

kappa_results = {}
for label, k in kappa_configs.items():
    r, t = simulate_cir(k, THETA, SIGMA, R0,
                        N_SCENARIOS, N_MONTHS, DT, FLOOR, SEED)
    hl = compute_halflife(k)
    kappa_results[label] = {
        'rates':    r,
        'times':    t,
        'avg':      r.mean(axis=1),
        'std':      r.std(axis=1),
        'halflife': hl,
    }
    print(f"  {label}: half-life = {hl:.2f} years, "
          f"final avg = {r.mean(axis=1)[-1]:.2%}")

# ══════════════════════════════════════════════════════
# STEP 4 — AUTOCORRELATION
# ══════════════════════════════════════════════════════

print("\n--- Autocorrelation (monthly rate changes) ---")
print("  Negative = mean reversion | Positive = momentum")
print()

avg_monthly_chg = pd.Series(np.diff(avg_path))
lags = list(range(1, 13))
autocorrs = {lag: round(avg_monthly_chg.autocorr(lag=lag), 4)
             for lag in lags}

print(f"  {'Lag':>6}  {'Autocorr':>9}  {'Bar'}")
print(f"  {'─'*6}  {'─'*9}  {'─'*30}")
for lag, ac in autocorrs.items():
    direction = "+" if ac > 0 else "-"
    bar_len   = int(abs(ac) * 40)
    bar       = "█" * bar_len
    print(f"  {lag:>4}m    {direction}{abs(ac):.4f}  {bar}")

# ══════════════════════════════════════════════════════
# STEP 5 — SUMMARY TABLE
# ══════════════════════════════════════════════════════

print("\n" + "=" * 55)
print("SUMMARY")
print("=" * 55)

print(f"""
── MODEL PARAMETERS ────────────────────────────────────
  κ (speed of mean reversion):  {KAPPA}
  θ (long-run mean / MRP):      {THETA:.2%}
  σ (volatility):               {SIGMA:.2%}
  r₀ (initial rate):            {R0:.2%}
  Scenarios:                    {N_SCENARIOS}
  Horizon:                      {N_MONTHS} months ({N_MONTHS//12} years)

── FELLER CONDITION ─────────────────────────────────────
  2κθ = {lhs:.6f}
  σ²  = {rhs:.6f}
  {'✓ Satisfied — rates guaranteed positive' if satisfied else '✗ Not satisfied — rates may touch zero'}

── MEAN REVERSION ───────────────────────────────────────
  Theoretical half-life:   {halflife_theoretical:.2f} years
  Empirical half-life:     {f'{empirical_hl:.2f} years' if empirical_hl else 'not reached'}
  Final avg rate:          {final_avg:.2%}
  Final avg vs θ:          {abs(final_avg - THETA):.4%} difference

── KAPPA COMPARISON ─────────────────────────────────────""")

for label, res in kappa_results.items():
    print(f"  {label}: HL={res['halflife']:.2f} yrs, "
          f"final avg={res['avg'][-1]:.2%}")

print(f"""
── AUTOCORRELATION (first 6 lags) ──────────────────────""")
for lag, ac in list(autocorrs.items())[:6]:
    print(f"  Lag {lag:2d}m: {ac:+.4f}")
print("  (negative = mean reversion, positive = momentum)")
print("=" * 55)

# ══════════════════════════════════════════════════════
# STEP 6 — PLOT 1: SCENARIO PATHS
# ══════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(12, 6))

for i in range(N_SCENARIOS):
    ax.plot(times, rates[:, i],
            color='steelblue', alpha=0.15, linewidth=0.8)

ax.plot(times, avg_path,
        color='navy', linewidth=2.5, label='Mean path', zorder=5)
ax.fill_between(times, p5_path, p95_path,
                alpha=0.2, color='steelblue',
                label='5th–95th percentile')
ax.axhline(THETA, color='red', linewidth=1.5, linestyle='--',
           label=f'Long-run mean θ = {THETA:.1%}')
ax.axhline(R0, color='orange', linewidth=1.2, linestyle=':',
           label=f'Initial rate r₀ = {R0:.1%}')
ax.axvline(halflife_theoretical, color='green', linewidth=1.2,
           linestyle='-.', alpha=0.8,
           label=f'Half-life = {halflife_theoretical:.1f} yrs')

ax.set_xlabel('Time (years)', fontsize=12)
ax.set_ylabel('Interest rate', fontsize=12)
ax.set_title(
    f'CIR Model — {N_SCENARIOS} Interest Rate Scenarios\n'
    f'κ={KAPPA}, θ={THETA:.1%}, σ={SIGMA:.1%}, r₀={R0:.1%}',
    fontsize=13
)
ax.yaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f'{x:.1%}'))
ax.legend(loc='upper right', fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# ══════════════════════════════════════════════════════
# STEP 7 — PLOT 2: CONVERGENCE TO THETA
# ══════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
ax.plot(times, avg_path, color='navy', linewidth=2,
        label='Mean path')
ax.fill_between(times,
                avg_path - std_path,
                avg_path + std_path,
                alpha=0.2, color='steelblue', label='±1 std dev')
ax.axhline(THETA, color='red', linewidth=1.5, linestyle='--',
           label=f'θ = {THETA:.1%}')
ax.axvline(halflife_theoretical, color='green', linewidth=1.2,
           linestyle='-.', alpha=0.8,
           label=f'Half-life = {halflife_theoretical:.1f} yrs')
ax.set_title('Convergence of Mean Path to θ', fontsize=12)
ax.set_xlabel('Time (years)')
ax.set_ylabel('Interest rate')
ax.yaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f'{x:.1%}'))
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

ax = axes[1]
deviation = np.abs(avg_path - THETA)
ax.plot(times, deviation * 100, color='darkorange', linewidth=2)
ax.axvline(halflife_theoretical, color='green', linewidth=1.2,
           linestyle='-.', alpha=0.8,
           label=f'Half-life = {halflife_theoretical:.1f} yrs')
ax.axhline(deviation[0] * 50, color='gray', linewidth=1,
           linestyle=':', label='50% of initial deviation')
ax.set_title('Absolute Deviation from θ Over Time', fontsize=12)
ax.set_xlabel('Time (years)')
ax.set_ylabel('|Mean rate − θ| (%)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

plt.suptitle('Mean Reversion — Convergence Analysis',
             fontsize=13, y=1.02)
plt.tight_layout()
plt.show()

# ══════════════════════════════════════════════════════
# STEP 8 — PLOT 3: KAPPA COMPARISON
# ══════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
colors = ['tomato', 'steelblue', 'seagreen']

ax = axes[0]
for (label, res), color in zip(kappa_results.items(), colors):
    ax.plot(res['times'], res['avg'],
            color=color, linewidth=2,
            label=f'{label} — HL={res["halflife"]:.1f} yrs')
ax.axhline(THETA, color='black', linewidth=1.5, linestyle='--',
           label=f'θ = {THETA:.1%}')
ax.axhline(R0, color='gray', linewidth=1, linestyle=':',
           label=f'r₀ = {R0:.1%}')
ax.set_title('Mean Path by Reversion Speed κ', fontsize=12)
ax.set_xlabel('Time (years)')
ax.set_ylabel('Interest rate')
ax.yaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f'{x:.1%}'))
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

ax = axes[1]
for (label, res), color in zip(kappa_results.items(), colors):
    ax.plot(res['times'], res['std'] * 100,
            color=color, linewidth=2, label=label)
ax.set_title('Rate Dispersion (Std Dev) by κ', fontsize=12)
ax.set_xlabel('Time (years)')
ax.set_ylabel('Std dev of rates (%)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

plt.suptitle('Impact of Mean Reversion Speed κ on Rate Dynamics',
             fontsize=13, y=1.02)
plt.tight_layout()
plt.show()

