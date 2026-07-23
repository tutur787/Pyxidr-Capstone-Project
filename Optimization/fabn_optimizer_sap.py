"""fabn_optimizer_sap — FABN SAP (Statutory Accounting Principles) optimizer.

Reformulates the FABN bond allocation around the SAP objective:

    max  Σ(y_i - r_FABN)·h_i  -  λ_cap·Σ(θ_i·h_i)
         - Σ τ_i·(tc⁺_i + tc⁻_i)  +  r_save·dt_q·Σ B[q]
         + swap NII - swap capital cost

where y_i = book yield (coupon + amortization), λ_cap = cost_of_capital × RBC_bar.
Risk is governed by a CVaR tail-loss limit (Rockafellar-Uryasev linearization over
historical rate/spread shock scenarios) rather than a PV-shortfall cap or a tight
duration band; the swap overlay is pay-fixed (subtracts duration, hedges the
now-open post-FABN-maturity bond universe) rather than receive-fixed.

Mirrors FABN_Optimizer_SAP_Shadow_SWAP.ipynb (Shadow & SWAP Analysis) exactly,
including the swap overlay, the FABN-maturity quarterly-grid truncation, the CVaR
risk constraint, and the shadow-price / reservation-price analysis (Sections 3B,
3B-ii, 3B-iii, 3C). One deliberate deviation: RBC_bar is 3.0 here (not the
notebook's 1.5) — a business decision already made for this codebase; everything
else matches.

Usage (standalone)::

    python fabn_optimizer_sap.py

Or with a specific date::

    runpy.run_path("fabn_optimizer_sap.py",
                   init_globals={"optimization_date": pd.Timestamp("2025-03-31")})
"""

import sys
import os
import runpy

import matplotlib
matplotlib.use("Agg")   # headless — no display required
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter

import numpy as np
import pandas as pd

# =============================================================================
# Date Selection  --  change this date, then re-run
# =============================================================================
# optimization_date may be injected by the caller via runpy init_globals.
try:
    optimization_date
except NameError:
    optimization_date = pd.Timestamp("2025-01-15")

_FABN_ISSUE    = pd.Timestamp("2022-09-06")
_FABN_MATURITY = pd.Timestamp("2027-09-06")
assert optimization_date <= pd.Timestamp.today(), "Date is in the future -- no market data."
assert optimization_date > _FABN_ISSUE,  f"Date must be after FABN issue ({_FABN_ISSUE.date()})."
assert optimization_date < _FABN_MATURITY, f"Date must be before FABN maturity ({_FABN_MATURITY.date()})."
# print(f"Optimization date selected : {optimization_date.date()}")

FABN_MATURITY = _FABN_MATURITY

# =============================================================================
# Section 0 — Pipeline Run & Imports
# =============================================================================
_this_dir     = os.path.dirname(os.path.abspath(__file__))
pipeline_path = os.path.join(_this_dir, "fabn_data_pipeline.py")

_ns      = runpy.run_path(pipeline_path, init_globals={"optimization_date": optimization_date})
pipeline = _ns["pipeline"]

import gurobipy as gp
from gurobipy import GRB

import fabn_finance as ff

# =============================================================================
# Section 1A — Unpack Pipeline
# =============================================================================
N           = pipeline["N"]
CUSIPS      = pipeline["CUSIPS"]

book_yield  = pipeline["book_yield"]    # y_i = coupon_inc + amort_inc
coupon_inc  = pipeline["coupon_inc"]    # statutory C_i (coupon yield, per $)
amort_inc   = pipeline["amort_inc"]     # statutory A_i (amortization, per $)
spread      = pipeline["spread"]        # OAS spread (kept for reporting)
durs        = pipeline["durs"]          # modified duration (years)
theta       = pipeline["theta"]         # RBC factor f_i (C-1)
tau         = pipeline["tau"] * 10      # bid-ask half-spread ×10 (notebook convention)
price       = pipeline["price"]         # mid price per 100 face
h_curr      = pipeline["h_curr"]        # current allocation ($)

qtr_bond_cf = pipeline["qtr_bond_cf"]  # (Q, N) asset cash flows per $1 face
qtr_fabn_cf = pipeline["qtr_fabn_cf"]  # (Q,)  FABN liability cash flows
qtr_idx     = pipeline["qtr_idx"]

# Truncate quarterly grid to FABN maturity horizon. Without this, Q spans however
# far the bond universe's cashflows run (driven by long bonds already excluded via
# post_fabn_mask below), and the facility balance keeps compounding "savings_income"
# for phantom quarters after the FABN liability itself has matured.
_fabn_qtr   = pd.Period(_FABN_MATURITY, freq="Q")
_keep       = qtr_idx <= _fabn_qtr
qtr_bond_cf = qtr_bond_cf[_keep]
qtr_fabn_cf = qtr_fabn_cf[_keep]
qtr_idx     = qtr_idx[_keep]
Q_full      = pipeline["Q"]
Q           = len(qtr_idx)

H           = pipeline["H"]            # total budget ($)
r_FABN      = pipeline["r_FABN"]       # FABN funding rate (annual)
D_FABN      = pipeline["D_FABN"]       # liability modified duration (yrs)
RBC_bar     = pipeline["RBC_bar"]      # required-capital multiplier on RBC
eps_D       = pipeline["eps_D"]        # duration band tolerance (yrs)
cvar_relloss = pipeline["cvar_relloss"]  # (S,N) per-$ forced-sale loss coeffs (Step 4)
cvar_d_rate  = pipeline["cvar_d_rate"]   # (S,) per-scenario rate shock (swap MV)
cvar_alpha   = pipeline["cvar_alpha"]    # CVaR tail level (worst 5%)

# print(f"Pipeline loaded: N={N}, Q={Q_full} -> {Q} (truncated to {qtr_idx[-1]})  |  date {optimization_date.date()}")
# print(f"Book yield mean {book_yield.mean()*100:.2f}%  |  tau mean {tau.mean()*1e4:.1f} bps")

# =============================================================================
# Section 1B — SAP Objective Parameters
# =============================================================================
cost_of_capital = 0.15              # insurer WACC on required capital (annual)
lambda_cap      = cost_of_capital * RBC_bar

eta             = 1.0               # (reporting only since Step 1: liq penalty removed from objective; hard PV cap still binds)

r_save          = 0.0               # Step 3 (no free parking): facility surplus earns 0 -- kills phantom savings income (matches backtest)
r_borrow        = 0.05              # rate paid on any drawn shortfall (informational; eta drives the penalty)
phi_sf          = 1                 # DEPRECATED (Step 4): PV-shortfall cap removed; CVaR governs risk
dt_q            = 0.25              # quarter length in years

# CVaR tail-loss control (Step 4): replaces the duration band as primary risk control
use_cvar        = True              # True: CVaR on book-vs-market forced-sale loss governs risk; band relaxed to inert
phi_cvar        = 0.01              # CVaR limit: worst-(1-alpha) tail loss <= phi_cvar * H

delta           = 0.05              # max 5% of budget per issuer

income_basis    = "net"
nii_rate = (book_yield - r_FABN) if income_basis == "net" else book_yield.copy()

# print(f"lambda_cap = {lambda_cap:.4f}  (cost_of_capital {cost_of_capital:.1%} x RBC_bar {RBC_bar})")
# print(f"eta        = {eta}   |   income basis = {income_basis}")
# print(f"NII rate   : {nii_rate.min()*100:.2f}% – {nii_rate.max()*100:.2f}%  "
      # f"(mean {nii_rate.mean()*100:.2f}%)")

# =============================================================================
# Section 1C — Swap Universe Parameters
# =============================================================================
use_swaps        = True
swap_maturities  = [1.0, 2.0, 3.0]           # pay-fixed swap tenors (years)
r_float          = 0.0435                     # SOFR proxy: ~3M Treasury on optimization_date
swap_rates_k     = [r_float] * len(swap_maturities)  # at-the-money (Step 1): pure hedge, zero carry/CF
mu_swap          = 0.002                      # C-3 RBC capital charge on swap notional
swap_cap_pct     = 0.20                       # max total swap notional as % of H
K                = len(swap_maturities) if use_swaps else 0

if use_swaps and K > 0:
    D_swap  = -np.array([ff.swap_fixed_leg_duration(m, c, r_float, settlement_freq=2)
                         for m, c in zip(swap_maturities, swap_rates_k)])   # pay-fixed (Step 1): negative duration
    cf_swap = np.array([ff.swap_quarterly_cashflows(c, r_float, m, Q, settlement_freq=2)
                        for m, c in zip(swap_maturities, swap_rates_k)])   # shape (K, Q)
    # print(f"Swap overlay: K={K} tenors  |  cap={swap_cap_pct:.0%}xH = ${swap_cap_pct*H:,.0f}")
    for k in range(K):
        nz = cf_swap[k][cf_swap[k] != 0]
        settle_str = f"{nz[0]*1e4:.1f} bps/period" if len(nz) else "no settlements in window"
        # print(f"  Swap {k+1}: {swap_maturities[k]:.0f}yr  fixed={swap_rates_k[k]:.3%}  "
              # f"D_swap={D_swap[k]:.4f}yr  net={settle_str}")
else:
    K = 0; D_swap = np.array([]); cf_swap = np.empty((0, Q))
    # print("Swap overlay: disabled (use_swaps=False or K=0)")

# =============================================================================
# Section 2 — Gurobi Optimization Model
# =============================================================================
model = gp.Model("FABN_SAP_Optimizer")
model.Params.LogToConsole = 1

# 2A. Decision variables
h        = model.addVars(N, lb=0.0, name="h")

# 2B. Auxiliary variables (linearization)
d_pos    = model.addVar(lb=0.0, name="d_pos")
d_neg    = model.addVar(lb=0.0, name="d_neg")
tc_plus  = model.addVars(N, lb=0.0, name="tc_plus")
tc_minus = model.addVars(N, lb=0.0, name="tc_minus")
B        = model.addVars(Q, lb=0.0, name="B")
s_net    = model.addVars(Q, lb=0.0, name="s_net")

# 2B-swap. Swap notional variables (receive-fixed, one per candidate tenor)
if use_swaps and K > 0:
    v = model.addVars(K, lb=0.0, name="v")

# Discount factors at r_FABN
t_quarters = [dt_q * (q + 1) for q in range(Q)]
df_q       = [(1.0 + r_FABN) ** (-t) for t in t_quarters]

# Step 2 open universe: post-FABN-maturity bonds admissible (was HTM exclusion).
# A bond whose maturity falls AFTER the FABN cannot be relied on to fund it.
_maturity = pd.to_datetime(
    pipeline["fixed"].set_index("CUSIP").loc[CUSIPS, "maturity"]
).values.astype("datetime64[ns]")
post_fabn_mask = _maturity > np.datetime64(FABN_MATURITY)
# Step 2: post-FABN bonds are NOT excluded — the pay-fixed swap hedges their sale-price rate risk.
# print(f"Step 2 open universe: {int(post_fabn_mask.sum())}/{N} post-FABN-maturity bonds "
      # f"now admissible (maturity > {FABN_MATURITY.date()})")

# 2C. Objective: Statutory NII - lambda*RBC - tau*Turnover + savings + swaps
NII            = gp.quicksum(nii_rate[i] * h[i]              for i in range(N))
RBC            = gp.quicksum(theta[i]    * h[i]              for i in range(N))
capital_cost   = lambda_cap * RBC
turnover_cost  = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
liq_penalty    = eta * gp.quicksum(df_q[q] * s_net[q]       for q in range(Q))
savings_income = r_save * dt_q * gp.quicksum(B[q]           for q in range(Q - 1))

if use_swaps and K > 0:
    swap_nii      = gp.quicksum((swap_rates_k[k] - r_float) * v[k] for k in range(K))
    swap_cap_cost = lambda_cap * mu_swap * gp.quicksum(v[k] for k in range(K))
else:
    swap_nii = 0.0
    swap_cap_cost = 0.0

SAP = NII - capital_cost - turnover_cost + savings_income + swap_nii - swap_cap_cost  # Step 4: CF-matching (penalty + hard cap) removed; CVaR governs risk
model.setObjective(SAP, GRB.MAXIMIZE)

# 2D. Constraints
# Budget
model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")

# Duration alignment band: |D_avg - D_FABN| <= eps_D  (bonds + swap overlay)
_dur_bonds = gp.quicksum(durs[i] * h[i] for i in range(N))
_dur_swaps = gp.quicksum(float(D_swap[k]) * v[k] for k in range(K)) if (use_swaps and K > 0) else 0.0
model.addConstr(_dur_bonds + _dur_swaps - D_FABN * H == d_pos - d_neg,
                name="dur_gap_decomp")
# Under CVaR (Step 4) the band is relaxed to inert (eps_D_eff huge) so CVaR governs risk
eps_D_eff = 100.0 if use_cvar else eps_D
model.addConstr(d_pos <= eps_D_eff * H, name="dur_upper")
model.addConstr(d_neg <= eps_D_eff * H, name="dur_lower")

# Turnover decomposition
for i in range(N):
    model.addConstr(h[i] - h_curr[i] == tc_plus[i] - tc_minus[i], name=f"tc_decomp_{i}")

# Lending-facility balance dynamics (bonds + swap quarterly settlements)
for q in range(Q):
    CF_A_q  = gp.quicksum(qtr_bond_cf[q, i] * h[i] for i in range(N))
    CF_sw_q = gp.quicksum(float(cf_swap[k, q]) * v[k] for k in range(K)) if (use_swaps and K > 0) else 0.0
    CF_L_q  = float(qtr_fabn_cf[q])
    if q == 0:
        model.addConstr(B[q] - s_net[q] == CF_A_q + CF_sw_q - CF_L_q, name=f"facility_{q}")
    else:
        model.addConstr(B[q] - s_net[q] == (1.0 + r_save * dt_q) * B[q - 1] + CF_A_q + CF_sw_q - CF_L_q,
                        name=f"facility_{q}")

# Step 4: PV-shortfall hard cap REMOVED -- CVaR governs risk; facility retained as buffer.
PV_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))
# print(f"PV(FABN liability) = ${PV_liability:,.2f}   (no shortfall cap -- CVaR governs)")

# Swap notional cap
if use_swaps and K > 0:
    model.addConstr(gp.quicksum(v[k] for k in range(K)) <= swap_cap_pct * H, name="swap_cap")
    # print(f"Swap notional cap  = ${swap_cap_pct*H:,.2f}  ({swap_cap_pct:.0%} of H)")

# Issuer concentration cap (first 6 CUSIP chars = issuer)
issuer_groups: dict[str, list[int]] = {}
for idx, cusip in enumerate(CUSIPS):
    issuer_groups.setdefault(cusip[:6], []).append(idx)
for issuer, bidx in issuer_groups.items():
    model.addConstr(gp.quicksum(h[i] for i in bidx) <= delta * H, name=f"conc_{issuer}")

# -- CVaR tail-loss limit (Step 4) -- governs rate/spread risk; replaces the band --
if use_cvar:
    S_scen    = cvar_relloss.shape[0]
    cvar_zeta = model.addVar(lb=-GRB.INFINITY, name="cvar_zeta")          # VaR level
    cvar_z    = model.addVars(S_scen, lb=0.0, name="cvar_z")              # tail excess
    for s in range(S_scen):
        loss_s = gp.quicksum(float(cvar_relloss[s, i]) * h[i] for i in range(N))
        if use_swaps and K > 0:                                           # swap offsets rate loss
            loss_s = loss_s + gp.quicksum(float(D_swap[k]) * float(cvar_d_rate[s]) * v[k] for k in range(K))
        model.addConstr(cvar_z[s] >= loss_s - cvar_zeta, name=f"cvar_excess_{s}")
    cvar_expr = cvar_zeta + (1.0 / ((1.0 - cvar_alpha) * S_scen)) * gp.quicksum(cvar_z[s] for s in range(S_scen))
    model.addConstr(cvar_expr <= phi_cvar * H, name="cvar_limit")
    # print(f"CVaR limit: worst-{1-cvar_alpha:.0%} tail forced-sale loss <= {phi_cvar:.1%} of H "
          # f"(${phi_cvar*H:,.0f}); {S_scen} scenarios")

# 2E. Solve
model.optimize()

# =============================================================================
# Section 3 — Results
# =============================================================================
if model.Status == GRB.OPTIMAL:
    h_opt = np.array([h[i].X for i in range(N)])

    # Swap optimal notionals
    if use_swaps and K > 0:
        v_opt         = np.array([v[k].X for k in range(K)])
        swap_nii_val  = float(sum((swap_rates_k[k] - r_float) * v_opt[k] for k in range(K)))
        swap_cap_val  = lambda_cap * mu_swap * float(v_opt.sum())
        swap_fv       = np.array([ff.swap_fair_value(swap_rates_k[k], r_float, swap_maturities[k])
                                   for k in range(K)])
    else:
        v_opt = np.zeros(0); swap_nii_val = 0.0; swap_cap_val = 0.0; swap_fv = np.zeros(0)

    # Objective decomposition
    nii_val       = float(sum(nii_rate[i] * h_opt[i] for i in range(N)))
    coupon_val    = float(sum(coupon_inc[i] * h_opt[i] for i in range(N)))
    amort_val     = float(sum(amort_inc[i]  * h_opt[i] for i in range(N)))
    RBC_val       = float(sum(theta[i] * h_opt[i] for i in range(N)))
    capital_cost_val = lambda_cap * RBC_val
    turnover_val  = float(sum(tau[i] * (tc_plus[i].X + tc_minus[i].X) for i in range(N)))
    B_vals        = [B[q].X     for q in range(Q)]
    s_net_vals    = [s_net[q].X for q in range(Q)]
    liq_val       = eta * float(sum(df_q[q] * s_net_vals[q] for q in range(Q)))
    savings_val   = r_save * dt_q * float(sum(B_vals[q] for q in range(Q - 1)))
    sap_val       = model.ObjVal

    D_avg     = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    _swap_dur = float(sum(D_swap[k] * v_opt[k] for k in range(K))) if (use_swaps and K > 0) else 0.0
    D_eff     = (float(sum(durs[i] * h_opt[i] for i in range(N))) + _swap_dur) / H
    req_cap   = RBC_bar * RBC_val
    earn_per_cap = nii_val / req_cap if req_cap > 0 else float("nan")

    # print("=" * 60)
    # print(f"  SAP OBJECTIVE            : ${sap_val:>14,.2f}")
    # print(f"  (1) Statutory NII        : ${nii_val:>14,.2f}")
    # print(f"      - coupon income      : ${coupon_val:>14,.2f}")
    # print(f"      - amortization       : ${amort_val:>14,.2f}")
    # print(f"  (2) Savings income       : ${savings_val:>14,.2f}")
    # print(f"  (3) Capital cost lambda*RBC: ${capital_cost_val:>12,.2f}")
    # print(f"  (4) Turnover cost         : ${turnover_val:>13,.2f}")
    if use_swaps and K > 0 and v_opt.sum() > 1.0:
        pass
        # print(f"  (5) Swap NII              : ${swap_nii_val:>13,.2f}")
        # print(f"  (6) Swap capital cost     : ${swap_cap_val:>13,.2f}")
    # print("-" * 60)
    # print(f"  [diag] PV shortfall used  : ${liq_val:>13,.2f}   (no cap -- CVaR governs; not in objective)")
    # print("=" * 60)
    # print(f"  RBC (Sum f_i h_i)        : ${RBC_val:,.2f}   required capital ${req_cap:,.2f}")
    # print(f"  Statutory earnings / req. capital : {earn_per_cap:.4f}")
    # print(f"  Portfolio D_avg (bonds)  : {D_avg:.4f} yrs")
    if use_swaps and K > 0:
        pass
        # print(f"  Portfolio D_eff (+swaps) : {D_eff:.4f} yrs  (target {D_FABN:.4f} +/- {eps_D})")
    else:
        pass
        # print(f"  Portfolio D_avg          : {D_avg:.4f} yrs  (target {D_FABN:.4f} +/- {eps_D})")
    # print("=" * 60)

    # Constraint status
    pv_short = float(sum(df_q[q] * s_net_vals[q] for q in range(Q)))
    _dur_chk = abs(D_eff - D_FABN) if (use_swaps and K > 0) else abs(D_avg - D_FABN)
    _rows = [("Budget (Sum h = H)", h_opt.sum(), H, abs(h_opt.sum()-H) < 1.0)]
    if use_cvar:
        _S = cvar_relloss.shape[0]
        _ntail = int(np.ceil((1.0 - cvar_alpha) * _S))              # worst-5% scenario count
        _loss  = cvar_relloss @ h_opt                               # per-scenario portfolio loss ($)
        if use_swaps and K > 0 and v_opt.sum() > 0:                 # swap offsets rate loss
            _loss = _loss + (np.asarray(cvar_d_rate)[:, None]
                             * (np.asarray(D_swap) * v_opt)[None, :]).sum(axis=1)
        cvar_val = float(np.sort(_loss)[-_ntail:].mean())           # HONEST realized tail loss (not zeta-artifact)
        _rows.append((f"CVaR worst-{1-cvar_alpha:.0%} tail loss (<= phi_cvar*H)",
                      cvar_val, phi_cvar*H, cvar_val <= phi_cvar*H + 1.0))
        _rows.append(("Duration band (relaxed -- CVaR governs)", _dur_chk, float("nan"), True))
    else:
        _rows.append(("Duration (|D_eff-D_FABN|<=eps_D)", _dur_chk, eps_D, _dur_chk <= eps_D + 1e-6))
    constraints_df = pd.DataFrame({
        "Constraint": [r[0] for r in _rows],
        "Value":  [r[1] for r in _rows],
        "Bound":  [r[2] for r in _rows],
        "Pass":   ["PASS" if r[3] else "FAIL" for r in _rows],
    })
    # print(constraints_df.to_string())

    # Swap Overlay Report
    if use_swaps and K > 0:
        swap_rows = []
        for k in range(K):
            dur_contrib = D_swap[k] * v_opt[k] / H
            swap_rows.append({
                "Tenor": f"{swap_maturities[k]:.0f}yr",
                "Fixed Rate": f"{swap_rates_k[k]:.3%}",
                "Float (SOFR)": f"{r_float:.3%}",
                "Net Spread": f"{(swap_rates_k[k] - r_float)*1e4:+.1f} bps",
                "Notional ($M)": f"{v_opt[k]/1e6:.2f}",
                "Dur Contrib (yr)": f"{dur_contrib:.4f}",
                "Mark-to-Mkt ($)": f"{swap_fv[k]*v_opt[k]:+,.0f}",
            })
        swap_df = pd.DataFrame(swap_rows)
        # print()
        # print("  SWAP OVERLAY REPORT")
        # print("=" * 60)
        # print(swap_df.to_string())
        tot_notional = v_opt.sum()
        tot_dur = sum(D_swap[k] * v_opt[k] for k in range(K)) / H
        # print(f"  Total notional : ${tot_notional/1e6:.2f}M  ({tot_notional/H:.1%} of H  |  cap={swap_cap_pct:.0%})")
        # print(f"  Bond dur       : {D_avg:.4f} yr   Swap dur contrib: {tot_dur:.4f} yr   Eff D: {D_eff:.4f} yr")
        # print(f"  Swap NII       : ${swap_nii_val:,.2f}   Swap cap cost: ${swap_cap_val:,.2f}")
elif model.Status == GRB.INFEASIBLE:
    # print("INFEASIBLE -- computing IIS")
    model.computeIIS()
    model.write("infeasible_sap.ilp")
else:
    pass
    # print(f"Solver status {model.Status} -- no optimal solution.")

# =============================================================================
# Section 3B — Shadow Price Analysis  (always run after Section 3)
# =============================================================================
if model.Status != GRB.OPTIMAL:
    pass
    # print("Shadow price analysis requires an optimal solution -- skipping.")
else:
    def _safe_pi(cname):
        try:
            return model.getConstrByName(cname).Pi
        except Exception:
            return None

    # 1. Extract dual values (shadow prices) of all named constraints
    pi_budget    = model.getConstrByName("budget").Pi
    pi_dur_upper = model.getConstrByName("dur_upper").Pi
    pi_dur_lower = model.getConstrByName("dur_lower").Pi
    pi_facility  = np.array([model.getConstrByName(f"facility_{q}").Pi for q in range(Q)])
    pi_issuer    = {iss: model.getConstrByName(f"conc_{iss}").Pi for iss in issuer_groups}

    # 2. Reduced costs of bond allocation variables h[i]
    rc = np.array([h[i].RC for i in range(N)])

    # 2b. Marginal $ with NO issuer/diversification caps — relax ONLY the issuer
    #     concentration caps. KEEP the CVaR limit (duration band relaxed;
    #     PV-shortfall cap removed), so the risk-relief value that makes the
    #     budget dollar worth pi_budget is preserved — only diversification is freed.
    _m2 = model.copy()
    _m2.Params.OutputFlag = 0
    for _iss in issuer_groups:
        _m2.getConstrByName(f"conc_{_iss}").RHS = GRB.INFINITY
    _m2.optimize()
    if _m2.Status == GRB.OPTIMAL:
        pi_unconstr  = _m2.getConstrByName("budget").Pi
        _h2          = np.array([_m2.getVarByName(f"h[{i}]").X for i in range(N)])
        best_i       = int(np.argmax(_h2 - h_opt))
        _best_status = "held" if h_opt[best_i] > 1.0 else "new (was capped out)"
    else:
        pi_unconstr  = float("nan"); best_i = 0; _best_status = "re-solve failed"

    # 3. TABLE 1: Constraint Shadow Price Report
    def _yn(v): return "Yes" if abs(v) > 1e-6 else "No"

    t1 = pd.DataFrame([
        {
            "Constraint"   : "Budget  (Sum h_i = H)",
            "Shadow price" : f"${pi_budget:+,.4f} / $1",
            "Binding?"     : "Equality",
            "Reading"      : f"$1 more capital -> ${pi_budget:,.4f} more net NII",
        },
        {
            "Constraint"   : "Marginal $  (no issuer/diversification caps)",
            "Shadow price" : f"${pi_unconstr:+,.4f} / $1",
            "Binding?"     : "n/a",
            "Reading"      : (f"vs ${pi_budget:.4f} constrained -> dropping issuer caps is worth "
                              f"${pi_unconstr - pi_budget:+,.4f}/$1; freed $ -> {CUSIPS[best_i]} [{_best_status}]"),
        },
        {
            "Constraint"   : ("Duration upper  (relaxed -- CVaR governs)" if use_cvar else f"Duration upper  (<= {eps_D} yr x H)"),
            "Shadow price" : f"${pi_dur_upper:+,.4f} / yr-$",
            "Binding?"     : _yn(pi_dur_upper),
            "Reading"      : (
                f"Binding -- widen band by 0.1 yr -> +${abs(pi_dur_upper)*0.1*H:,.0f} NII"
                if abs(pi_dur_upper) > 1e-6 else
                "Not binding -- portfolio fits naturally within upper limit"
            ),
        },
        {
            "Constraint"   : ("Duration lower  (relaxed -- CVaR governs)" if use_cvar else f"Duration lower  (<= {eps_D} yr x H)"),
            "Shadow price" : f"${pi_dur_lower:+,.4f} / yr-$",
            "Binding?"     : _yn(pi_dur_lower),
            "Reading"      : (
                f"Binding -- widen band by 0.1 yr -> +${abs(pi_dur_lower)*0.1*H:,.0f} NII"
                if abs(pi_dur_lower) > 1e-6 else
                "Not binding -- portfolio fits naturally within lower limit"
            ),
        },
    ])
    # print("=" * 68)
    # print("  TABLE 1 -- CONSTRAINT SHADOW PRICE REPORT")
    # print("=" * 68)
    # print(t1.to_string())

    # 4. Binding issuer concentration caps
    bind_iss = sorted(
        [(iss, pi) for iss, pi in pi_issuer.items() if abs(pi) > 1e-6],
        key=lambda x: abs(x[1]), reverse=True,
    )
    # print(f"\nIssuer concentration caps: {len(bind_iss)} of {len(issuer_groups)} are binding.")
    if bind_iss:
        pass
        # print("Top 10 binding issuers (optimizer wants more than the 5% cap allows):")
        # print(pd.DataFrame([
            # {
                # "Issuer (6-char CUSIP)"   : iss,
                # "Shadow price"            : f"${pi:+,.4f} / $1",
                # "NII gain if cap +1pp ($)": f"${abs(pi) * 0.01 * H:,.0f}",
            # }
            # for iss, pi in bind_iss[:10]
        # ]).to_string())

    # 5. Chart A: Facility quarter shadow prices
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.bar(
        range(Q), pi_facility,
        color=["#e74c3c" if p < 0 else "#27ae60" for p in pi_facility],
        edgecolor="white", width=0.85,
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(0, Q, 4))
    ax.set_xticklabels([str(qtr_idx[q]) for q in range(0, Q, 4)], rotation=45, ha="right")
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Shadow price ($ per $1 of facility balance)")
    ax.set_title(
        "Fig 5 -- Facility Shadow Prices by Quarter\n"
        "Negative = quarter where facility balance is most urgently needed to cover FABN payments"
    )
    plt.tight_layout()
    # plt.savefig("fig5_facility_shadow_prices.png", dpi=100)
    plt.close()

    tightest_q = int(np.argmin(pi_facility))
    # print(f"Tightest funding quarter: {qtr_idx[tightest_q]}  "
          # f"(shadow price {pi_facility[tightest_q]:.4f})")

    # 6. TABLE 2: Near-miss bonds (excluded, ranked by reduced cost)
    eligible = ~post_fabn_mask
    excluded = (h_opt < 1.0) & eligible
    excl_idx = np.where(excluded)[0]
    order    = np.argsort(-rc[excl_idx])

    _pf = pipeline["fixed"].set_index("CUSIP")
    t2_rows = []
    for rank, pos in enumerate(order[:20]):
        i   = excl_idx[pos]
        cid = CUSIPS[i]
        t2_rows.append({
            "Rank"              : rank + 1,
            "CUSIP"             : cid,
            "Sector"            : str(_pf.loc[cid, "sector"]),
            "Rating"            : str(_pf.loc[cid, "rating_sp"]).strip(),
            "Book yield (%)"    : f"{book_yield[i]*100:.3f}",
            "Duration (yr)"     : f"{durs[i]:.3f}",
            "RBC theta_i (%)"   : f"{theta[i]*100:.3f}",
            "tau_i (bps)"       : f"{tau[i]*1e4:.1f}",
            "Reduced cost"      : f"{rc[i]:+.5f}",
            "Gap to entry (bps)": f"{abs(rc[i])*1e4:.1f}",
            "Price gap ($/100)" : f"{durs[i] * rc[i] * price[i]:+.2f}",
        })
    # print("\n" + "=" * 68)
    # print("  TABLE 2 -- NEAR-MISS BONDS")
    # print("  Ranked by reduced cost: y_i - r*_hurdle (positive -> reservation price > market price).")
    # print("  'Price gap': RC * MD * Price ($/100 face) -- value above market price to us.")
    # print("=" * 68)
    # print(pd.DataFrame(t2_rows).to_string())

    # 7. Chart B: RC distribution + book yield vs RC scatter
    rc_excl = rc[excl_idx]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].hist(rc_excl * 1e4, bins=40, color="#3498db", edgecolor="white")
    axes[0].axvline(0, color="red", ls="--", lw=1.2, label="Entry threshold (RC = 0)")
    axes[0].set_xlabel("Reduced cost  (x 10^4, bps-equivalent)")
    axes[0].set_ylabel("Number of bonds")
    axes[0].set_title(
        "Fig 6 -- Reduced Cost Distribution\n"
        "(excluded eligible bonds; closer to 0 = nearest to entering portfolio)"
    )
    axes[0].legend()

    sel_mask = h_opt > 1.0
    axes[1].scatter(book_yield[excl_idx] * 100, rc_excl * 1e4,
                    alpha=0.5, color="#7f8c8d", s=18, label="Excluded")
    axes[1].scatter(book_yield[sel_mask] * 100, rc[sel_mask] * 1e4,
                    alpha=0.85, color="#e74c3c", s=40, label="Selected  (RC ~ 0)")
    axes[1].axhline(0, color="red", ls="--", lw=1.0, label="Entry threshold")
    axes[1].set_xlabel("Book yield (%)")
    axes[1].set_ylabel("Reduced cost  (x 10^4, bps-equivalent)")
    axes[1].set_title(
        "Fig 7 -- Book Yield vs Reduced Cost\n"
        "Bonds near RC = 0 are borderline; large gap = excluded by structure, not yield"
    )
    axes[1].legend()
    plt.tight_layout()
    # plt.savefig("fig6_7_reduced_cost.png", dpi=100)
    plt.close()

    # 8. Shadow-augmented facility fit score
    fac_bonus  = np.array([
        sum(float(pi_facility[q]) * float(qtr_bond_cf[q, i]) for q in range(Q))
        for i in range(N)
    ])
    shadow_nii = nii_rate + fac_bonus

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(
        nii_rate[~sel_mask & eligible] * 100,
        shadow_nii[~sel_mask & eligible] * 100,
        alpha=0.4, color="grey", s=15, label="Excluded",
    )
    ax.scatter(
        nii_rate[sel_mask] * 100,
        shadow_nii[sel_mask] * 100,
        alpha=0.85, color="#e74c3c", s=40, label="Selected",
    )
    _lo = min(nii_rate[eligible].min(), shadow_nii[eligible].min()) * 100 * 0.99
    _hi = max(nii_rate[eligible].max(), shadow_nii[eligible].max()) * 100 * 1.01
    ax.plot([_lo, _hi], [_lo, _hi], "k:", lw=0.8, label="Score = raw yield (45 line)")
    ax.set_xlabel("Raw NII rate  (%, net of r_FABN)")
    ax.set_ylabel("Shadow-augmented NII rate  (%)")
    ax.set_title(
        "Fig 8 -- Raw Yield vs Shadow-Augmented Score\n"
        "Above 45-line: undervalued by raw yield (cash flows align with FABN payment schedule)\n"
        "Below 45-line: overvalued by raw yield (cash flows land in low-demand quarters)"
    )
    ax.legend()
    plt.tight_layout()
    # plt.savefig("fig8_shadow_augmented_score.png", dpi=100)
    plt.close()

    # print("\n[Shadow score = book_yield_net + sum_q pi_facility[q] * CF_bond[q,i]]")
    # print("Bonds above the 45-degree line contribute more than their yield implies because")
    # print("their cash flows land in quarters where the lending facility needs them most.")

# =============================================================================
# Section 3B-ii — Per-Bond Reservation Price (Shadow Price)  (always run after 3B)
# =============================================================================
if model.Status == GRB.OPTIMAL:
    # 1. Hurdle yield and reservation price for every eligible bond
    r_star = book_yield - rc
    P_star = np.full(N, np.nan)
    t_q_arr = np.array(t_quarters)
    for i in range(N):
        cfs = qtr_bond_cf[:, i]
        if cfs.sum() < 1e-12 or r_star[i] <= -1:
            continue
        P_star[i] = float((cfs * (1.0 + r_star[i]) ** (-t_q_arr)).sum()) * 100.0

    gap = P_star - price

    # 2. TABLE 3: full bond list sorted by gap
    _pf = pipeline["fixed"].set_index("CUSIP")
    t3_rows = []
    for i in range(N):
        if post_fabn_mask[i] or np.isnan(P_star[i]):
            continue
        cid = CUSIPS[i]
        t3_rows.append({
            "CUSIP"               : cid,
            "Sector"              : str(_pf.loc[cid, "sector"]),
            "Rating"              : str(_pf.loc[cid, "rating_sp"]).strip(),
            "Mkt Price ($/100)"   : round(price[i], 3),
            "Shadow Price P*"     : round(P_star[i], 3),
            "Gap (P*−P)"          : round(gap[i], 3),
            "Gap (%)"             : round(gap[i] / price[i] * 100, 2),
            "Book Yield (%)"      : round(book_yield[i] * 100, 3),
            "Hurdle r* (%)"       : round(r_star[i] * 100, 3),
            "Duration (yr)"       : round(durs[i], 3),
            "Selected"            : "YES" if h_opt[i] > 1.0 else "",
        })
    t3_df = pd.DataFrame(t3_rows).sort_values("Gap (P*−P)", ascending=False).reset_index(drop=True)

    n_pos = int((t3_df["Gap (P*−P)"] > 0.001).sum())
    n_neg = int((t3_df["Gap (P*−P)"] < -0.001).sum())
    n_par = len(t3_df) - n_pos - n_neg

    # print("=" * 72)
    # print("  TABLE 3 — PER-BOND RESERVATION PRICE (SHADOW PRICE)")
    # print("  P*_i = PV(bond CFs at hurdle yield r*_i).  Gap = P* − Market Price.")
    # print("  Gap > 0 → bond is cheap for us.  Gap < 0 → bond is expensive for us.")
    # print("=" * 72)
    # print(f"  Bonds with P* > P (underpriced for portfolio) : {n_pos}")
    # print(f"  Bonds with P* ≈ P (at the margin)            : {n_par}")
    # print(f"  Bonds with P* < P (overpriced for portfolio)  : {n_neg}")
    # print(f"\n  TOP 20 — highest shadow-price premium (bonds the optimizer values most):")
    # print(t3_df.head(20).to_string())
    # print(f"\n  BOTTOM 20 — largest shadow-price discount (bonds furthest from entering):")
    # print(t3_df.tail(20).to_string())

    # 3. Charts: Market Price vs Shadow Price + Gap distribution
    elig_fin = ~post_fabn_mask & np.isfinite(P_star)
    P_e   = price[elig_fin]
    PS_e  = P_star[elig_fin]
    sel_e = h_opt[elig_fin] > 1.0
    gap_e = gap[elig_fin]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].scatter(P_e[~sel_e], PS_e[~sel_e], alpha=0.4, color="grey", s=15, label="Excluded")
    axes[0].scatter(P_e[sel_e],  PS_e[sel_e],  alpha=0.85, color="#e74c3c", s=40, label="Selected")
    _lo = min(P_e.min(), PS_e.min()) * 0.998
    _hi = max(P_e.max(), PS_e.max()) * 1.002
    axes[0].plot([_lo, _hi], [_lo, _hi], "k:", lw=0.8, label="P* = P  (45°)")
    axes[0].set_xlabel("Market Price  ($/100 face)")
    axes[0].set_ylabel("Shadow Price P*  ($/100 face)")
    axes[0].set_title("Market Price vs Shadow Price\nAbove 45° line → worth more to us than market price")
    axes[0].legend(fontsize=8)

    axes[1].hist(gap_e, bins=40, color="#3498db", edgecolor="white")
    axes[1].axvline(0, color="red", ls="--", lw=1.2, label="P* = P  (fair)")
    axes[1].set_xlabel("Shadow Price Gap  P* − P  ($/100 face)")
    axes[1].set_ylabel("Number of bonds")
    axes[1].set_title("Shadow Price Gap Distribution\nPositive → underpriced for us;  Negative → overpriced")
    axes[1].legend(fontsize=8)
    plt.tight_layout()
    # plt.savefig("fig910_reservation_price.png", dpi=100)
    plt.close()

    # print(f"\nShadow price gap stats (eligible bonds, $/100 face):")
    # print(f"  Mean gap   : {gap_e.mean():+.3f}")
    # print(f"  Median gap : {np.median(gap_e):+.3f}")
    # print(f"  Max (most underpriced) : {gap_e.max():+.3f}  (bond {CUSIPS[np.where(elig_fin)[0][np.argmax(gap_e)]]})")
    # print(f"  Min (most overpriced)  : {gap_e.min():+.3f}  (bond {CUSIPS[np.where(elig_fin)[0][np.argmin(gap_e)]]})")
else:
    pass
    # print("Reservation price analysis requires an optimal solution -- skipping.")

# =============================================================================
# Section 3B-iii — Marginal Dollar: Range, Breakdown & Diversification Gap
# =============================================================================
# Pure budget RHS-ranging: only the "budget" RHS moves; duration target, issuer
# caps and swap cap stay at their base-case (H) levels. "unconstr" additionally
# drops the issuer caps only (keeps the duration band), exactly as Section 3B does.
if model.Status != GRB.OPTIMAL:
    pass
    # print("3B-iii requires an optimal base solution -- skipping.")
else:
    _terms = ["NII", "Savings", "Capital", "Turnover", "SwapNII", "SwapCap"]

    def _resolve_budget(H_new, drop_caps=False):
        m = model.copy(); m.Params.OutputFlag = 0
        m.getConstrByName("budget").RHS = float(H_new)
        if drop_caps:
            for _iss in issuer_groups:
                m.getConstrByName(f"conc_{_iss}").RHS = GRB.INFINITY
        m.optimize()
        return m

    def _pi_of(m):
        return m.getConstrByName("budget").Pi if m.Status == GRB.OPTIMAL else float("nan")

    def _components(m):
        """Objective decomposition of a solved (copied) model, signed as in SAP."""
        if m.Status != GRB.OPTIMAL:
            return {k: float("nan") for k in _terms + ["SAP"]}
        hv  = np.array([m.getVarByName(f"h[{i}]").X       for i in range(N)])
        Bv  = np.array([m.getVarByName(f"B[{q}]").X       for q in range(Q)])
        snv = np.array([m.getVarByName(f"s_net[{q}]").X   for q in range(Q)])
        tpv = np.array([m.getVarByName(f"tc_plus[{i}]").X for i in range(N)])
        tmv = np.array([m.getVarByName(f"tc_minus[{i}]").X for i in range(N)])
        nii = float((nii_rate * hv).sum())
        cap = lambda_cap * float((theta * hv).sum())
        txn = float((tau * (tpv + tmv)).sum())
        liq = eta * float((np.array(df_q) * snv).sum())
        sav = r_save * dt_q * float(Bv[:Q - 1].sum())
        if use_swaps and K > 0:
            vv  = np.array([m.getVarByName(f"v[{k}]").X for k in range(K)])
            sni = float(sum((swap_rates_k[k] - r_float) * vv[k] for k in range(K)))
            sca = lambda_cap * mu_swap * float(vv.sum())
        else:
            sni = 0.0; sca = 0.0
        return {"NII": nii, "Savings": sav, "Capital": -cap, "Turnover": -txn,
                "Liquidity": -liq, "SwapNII": sni, "SwapCap": -sca, "SAP": m.ObjVal}

    # (1) Parametric budget sweep
    H_grid = np.unique(np.concatenate([
        H * np.linspace(0.5, 1.6, 23),
        np.linspace(H * 0.90, H * 1.10, 41),
        [float(H)],
    ]))
    # print(f"Sweeping budget H over {len(H_grid)} points x2 (constrained + no-caps) ...")
    pi_con = np.array([_pi_of(_resolve_budget(Hn, drop_caps=False)) for Hn in H_grid])
    pi_unc = np.array([_pi_of(_resolve_budget(Hn, drop_caps=True))  for Hn in H_grid])
    # print("Done.")

    def _valid_range(grid, pis, pi_here):
        j = int(np.argmin(np.abs(grid - H))); lo = hi = grid[j]; k = j
        while k - 1 >= 0 and np.isfinite(pis[k-1]) and abs(pis[k-1] - pi_here) <= 1e-4:
            k -= 1; lo = grid[k]
        k = j
        while k + 1 < len(grid) and np.isfinite(pis[k+1]) and abs(pis[k+1] - pi_here) <= 1e-4:
            k += 1; hi = grid[k]
        return lo, hi

    seg_lo,  seg_hi  = _valid_range(H_grid, pi_con, pi_budget)
    segu_lo, segu_hi = _valid_range(H_grid, pi_unc, pi_unconstr)

    try:
        sarhs_lo = model.getConstrByName("budget").SARHSLow
        sarhs_hi = model.getConstrByName("budget").SARHSUp
    except Exception:
        sarhs_lo = sarhs_hi = float("nan")

    # (2) Term-by-term breakdown
    def _breakdown(drop_caps):
        base = _resolve_budget(H, drop_caps=drop_caps)
        lo, hi = _valid_range(H_grid, pi_unc if drop_caps else pi_con, _pi_of(base))
        dH = min(1.0e6, 0.4 * (hi - H)) if hi > H + 1.0 else 1.0e5
        up = _resolve_budget(H + dH, drop_caps=drop_caps)
        c0, c1 = _components(base), _components(up)
        return {k: (c1[k] - c0[k]) / dH for k in _terms}, _pi_of(base), dH

    bd_con, _pc, dH_con = _breakdown(False)
    bd_unc, _pu, dH_unc = _breakdown(True)
    bd_gap = {k: bd_unc[k] - bd_con[k] for k in _terms}

    # TABLE 4: shadow price & valid range
    rng = pd.DataFrame([
        {"Marginal dollar": "Under all constraints",
         "Shadow price ($/$1)": f"${pi_budget:,.4f}",
         "Valid H range (sweep)": f"${seg_lo/1e6:,.0f}M - ${seg_hi/1e6:,.0f}M",
         "Valid H range (Gurobi SARHS)":
            (f"${sarhs_lo/1e6:,.0f}M - ${sarhs_hi/1e6:,.0f}M" if np.isfinite(sarhs_lo) else "n/a (no basis)")},
        {"Marginal dollar": "No issuer/diversification caps",
         "Shadow price ($/$1)": f"${pi_unconstr:,.4f}",
         "Valid H range (sweep)": f"${segu_lo/1e6:,.0f}M - ${segu_hi/1e6:,.0f}M",
         "Valid H range (Gurobi SARHS)": "-"},
    ])
    # print("=" * 72)
    # print("  TABLE 4 -- MARGINAL DOLLAR: SHADOW PRICE & VALID RANGE OF H")
    # print("=" * 72)
    # print(rng.to_string())
    # print(f"  Diversification-cap gap (pi_unconstr - pi_budget): "
          # f"${pi_unconstr - pi_budget:+,.4f} / $1")
    # print(f"  -> at H=${H/1e6:,.0f}M the issuer caps hold back "
          # f"${pi_unconstr - pi_budget:.4f} of value per marginal dollar.")

    # TABLE 5: breakdown by objective term
    _lbl = {"NII": "NII (spread over funding)", "Savings": "Savings (principal reinvest)",
            "Capital": "Capital cost (lambda*theta)", "Turnover": "Turnover",
            "Liquidity": "Liquidity", "SwapNII": "Swap NII", "SwapCap": "Swap capital"}
    bd = pd.DataFrame([
        {"Term": _lbl[k], "pi_budget ($/$1)": f"{bd_con[k]:+.4f}",
         "pi_unconstr ($/$1)": f"{bd_unc[k]:+.4f}", "Gap contribution": f"{bd_gap[k]:+.4f}"}
        for k in _terms
    ])
    bd.loc[len(bd)] = ["TOTAL (= shadow price)",
                       f"{sum(bd_con[k] for k in _terms):+.4f}",
                       f"{sum(bd_unc[k] for k in _terms):+.4f}",
                       f"{sum(bd_gap[k] for k in _terms):+.4f}"]
    # print("\n" + "=" * 72)
    # print("  TABLE 5 -- SHADOW PRICE BREAKDOWN BY OBJECTIVE TERM ($ per $1)")
    # print(f"  (finite-difference dH: constrained ${dH_con:,.0f}, no-caps ${dH_unc:,.0f};")
    # print(f"   TOTAL should match pi_budget {pi_budget:+.4f} / pi_unconstr {pi_unconstr:+.4f})")
    # print("=" * 72)
    # print(bd.to_string())

    # Charts
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].step(H_grid / 1e6, pi_con, where="mid", color="#2980b9", lw=1.7,
                 label="Under all constraints")
    axes[0].step(H_grid / 1e6, pi_unc, where="mid", color="#e67e22", lw=1.7,
                 label="No issuer caps")
    axes[0].axvline(H / 1e6, color="k", ls="--", lw=1.0, label=f"Current H=${H/1e6:.0f}M")
    axes[0].axvspan(seg_lo / 1e6, seg_hi / 1e6, color="#2980b9", alpha=0.10,
                    label="pi_budget valid range")
    axes[0].set_xlabel("Budget H ($M)"); axes[0].set_ylabel(r"Budget shadow price (\$ / \$1)")
    axes[0].set_title("Fig 11 -- Marginal value of capital vs budget\n"
                      "(diminishing returns; gap = cost of issuer caps)")
    axes[0].legend(fontsize=8); axes[0].grid(alpha=0.25)

    gap_curve = pi_unc - pi_con
    axes[1].step(H_grid / 1e6, gap_curve, where="mid", color="#8e44ad", lw=1.8)
    axes[1].axvline(H / 1e6, color="k", ls="--", lw=1.0)
    axes[1].axhline(0, color="k", lw=0.6)
    axes[1].set_xlabel("Budget H ($M)")
    axes[1].set_ylabel(r"pi_unconstr - pi_budget (\$ / \$1)")
    axes[1].set_title("Fig 12 -- Cost of issuer/diversification caps vs budget\n"
                      "(value held back per marginal dollar)")
    axes[1].grid(alpha=0.25)
    _xlo, _xhi = 500.0, 700.0
    _win = (H_grid / 1e6 >= _xlo) & (H_grid / 1e6 <= _xhi)
    _fmt = FuncFormatter(lambda v, _: f"${v:.4f}")
    for _ax, _yd in ((axes[0], np.concatenate([pi_con[_win], pi_unc[_win]])),
                     (axes[1], gap_curve[_win])):
        _ax.set_xlim(_xlo, _xhi)
        _yv = _yd[np.isfinite(_yd)]
        if _yv.size:
            _pad = max((_yv.max() - _yv.min()) * 0.10, 5e-4)
            _ax.set_ylim(_yv.min() - _pad, _yv.max() + _pad)
        _ax.yaxis.set_major_formatter(_fmt)
    plt.tight_layout()
    # plt.savefig("fig11_12_marginal_dollar.png", dpi=100)
    plt.close()

    x = np.arange(len(_terms)); wb = 0.38
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - wb/2, [bd_con[k] for k in _terms], wb, label="pi_budget", color="#2980b9")
    ax.bar(x + wb/2, [bd_unc[k] for k in _terms], wb, label="pi_unconstr (no caps)", color="#e67e22")
    ax.axhline(0, color="k", lw=0.7)
    ax.set_xticks(x); ax.set_xticklabels([_lbl[k] for k in _terms], rotation=30, ha="right")
    ax.set_ylabel(r"\$ per \$1 of marginal capital")
    ax.set_title("Fig 13 -- What the marginal dollar is made of, by objective term")
    ax.legend()
    plt.tight_layout()
    # plt.savefig("fig13_marginal_dollar_breakdown.png", dpi=100)
    plt.close()

    # print("\nReading:")
    # print(f"  - pi_budget = ${pi_budget:+.4f}/$1, valid while H in "
          # f"[${seg_lo/1e6:.0f}M, ${seg_hi/1e6:.0f}M].")
    # print(f"  - Dropping issuer caps lifts it to ${pi_unconstr:+.4f}/$1 "
          # f"(gap ${pi_unconstr - pi_budget:+.4f}).")
    # print(f"  - Composition: NII {bd_con['NII']:+.4f} + Savings {bd_con['Savings']:+.4f} "
          # f"+ Capital {bd_con['Capital']:+.4f} (+ small terms) per $1.")

# =============================================================================
# Section 3C — Swap Overlay Analytics: Duration Attribution & CF Contribution
# =============================================================================
if model.Status == GRB.OPTIMAL and use_swaps and K > 0 and v_opt.sum() > 1.0:
    fig = plt.figure(figsize=(14, 10))
    gs  = gridspec.GridSpec(2, 2, hspace=0.45, wspace=0.35)

    # 3C-1: Duration attribution (stacked bar)
    ax1 = fig.add_subplot(gs[0, 0])
    dur_bond_contrib = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    dur_swap_contrib = float(sum(D_swap[k] * v_opt[k] for k in range(K))) / H
    vals   = [dur_bond_contrib, dur_swap_contrib, D_eff]
    colors = ["#2196F3", "#FF9800", "#4CAF50"]
    labels = ["Bonds", "Swap Overlay", "Combined"]
    bars = ax1.bar(labels, vals, color=colors, edgecolor="k", linewidth=0.7)
    ax1.axhline(D_FABN, color="red", linestyle="--", linewidth=1.5, label=f"FABN D={D_FABN:.4f}")
    ax1.axhline(D_FABN + eps_D, color="red", linestyle=":", linewidth=1, alpha=0.5)
    ax1.axhline(D_FABN - eps_D, color="red", linestyle=":", linewidth=1, alpha=0.5)
    for bar, val in zip(bars, vals):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                 f"{val:.4f}", ha="center", va="bottom", fontsize=9)
    ax1.set_ylabel("Modified Duration (yr)")
    ax1.set_title("Duration Attribution")
    ax1.legend(fontsize=8)
    ax1.set_ylim(0, max(vals) * 1.20)

    # 3C-2: Swap notional by tenor
    ax2 = fig.add_subplot(gs[0, 1])
    tenors_str = [f"{swap_maturities[k]:.0f}yr\n({swap_rates_k[k]:.3%})" for k in range(K)]
    bars2 = ax2.bar(tenors_str, v_opt / 1e6, color="#FF9800", edgecolor="k", linewidth=0.7)
    cap_line = swap_cap_pct * H / 1e6
    ax2.axhline(cap_line, color="red", linestyle="--", linewidth=1.5,
                label=f"Cap={swap_cap_pct:.0%}xH=${cap_line:.0f}M")
    for bar, val in zip(bars2, v_opt / 1e6):
        if val > 0.5:
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                     f"${val:.1f}M", ha="center", va="bottom", fontsize=9)
    ax2.set_ylabel("Notional ($M)")
    ax2.set_title("Swap Notional by Tenor")
    ax2.legend(fontsize=8)

    # 3C-3: Quarterly cash flows (bonds + swap vs liability) across all quarters
    ax3 = fig.add_subplot(gs[1, :])
    q_dates = [optimization_date + pd.DateOffset(months=3*(q+1)) for q in range(Q)]
    cf_bonds_q = np.array([float(sum(qtr_bond_cf[q, i] * h_opt[i] for i in range(N)))
                            for q in range(Q)])
    cf_swap_q  = np.array([float(sum(cf_swap[k, q] * v_opt[k] for k in range(K)))
                            for q in range(Q)])
    cf_liab_q  = np.array([float(qtr_fabn_cf[q]) for q in range(Q)])
    ax3.fill_between(q_dates, cf_bonds_q / 1e6, alpha=0.45, color="#2196F3",
                     label="Bond CF ($M)")
    ax3.fill_between(q_dates, cf_swap_q / 1e6,  alpha=0.65, color="#FF9800",
                     label="Swap Net CF ($M)")
    ax3.plot(q_dates, cf_liab_q / 1e6, color="red", linewidth=1.5, linestyle="--",
             label="FABN Liability CF ($M)")
    ax3.set_xlabel("Quarter")
    ax3.set_ylabel("Cash Flow ($M)")
    ax3.set_title("Quarterly CFs: Bonds + Swap Overlay vs FABN Liability")
    ax3.legend(fontsize=8)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.suptitle("Section 3C — Swap Overlay Analytics", fontsize=13, fontweight="bold")
    plt.tight_layout()
    # plt.savefig("fig_swap_overlay.png", dpi=100)
    plt.close()
    # print("Saved: fig_swap_overlay.png")
else:
    pass
    # print("Swap overlay not active (use_swaps=False or optimizer allocated zero notional).")

# =============================================================================
# Section 4 — Analytics (only when optimal)
# =============================================================================
if model.Status == GRB.OPTIMAL:
    fixed_df = pipeline["fixed"].set_index("CUSIP")
    selected = h_opt > 1.0
    w        = h_opt[selected] / h_opt[selected].sum()

    # 4A. Objective decomposition
    sap_summary = pd.DataFrame({
        "Component": [
            "Statutory NII", "  - coupon income", "  - amortization",
            "Savings income", "Capital cost (lambda*RBC)",
            "Turnover cost", "SAP OBJECTIVE",
        ],
        "Value ($)": [
            nii_val, coupon_val, amort_val, savings_val,
            -capital_cost_val, -turnover_val, sap_val,
        ],
    })
    # print(sap_summary.to_string())

    # 4B. Portfolio analytics
    analytics = pd.DataFrame({
        "Metric": [
            "Bonds selected (h>$1)",
            "Wtd avg book yield (%)",
            "Wtd avg coupon yield (%)",
            "Wtd avg amortization (bps)",
            "Wtd avg OAS spread (bps)",
            "Wtd avg duration (yrs)",
            "Wtd avg RBC factor (%)",
            "Statutory earnings / req. capital",
        ],
        "Value": [
            int(selected.sum()),
            f"{(book_yield[selected] * w).sum() * 100:.2f}",
            f"{(coupon_inc[selected] * w).sum() * 100:.2f}",
            f"{(amort_inc[selected]  * w).sum() * 1e4:+.1f}",
            f"{(spread[selected]     * w).sum() * 1e4:.1f}",
            f"{(durs[selected]       * w).sum():.4f}",
            f"{(theta[selected]      * w).sum() * 100:.3f}",
            f"{earn_per_cap:.4f}",
        ],
    })
    # print(analytics.to_string())

    # 4C. Allocation table
    alloc_df = pd.DataFrame({
        "CUSIP":           CUSIPS,
        "Sector":          [str(fixed_df.loc[c, "sector"]) for c in CUSIPS],
        "Rating":          [str(fixed_df.loc[c, "rating_sp"]).strip() for c in CUSIPS],
        "h_opt ($)":       h_opt,
        "Book yield (%)":  book_yield * 100,
        "Coupon (%)":      coupon_inc * 100,
        "Amort (bps)":     amort_inc  * 1e4,
        "Duration (yr)":   durs,
        "RBC f_i (%)":     theta      * 100,
        "tau (bps)":       tau        * 1e4,
    })
    alloc_nonzero = (
        alloc_df[alloc_df["h_opt ($)"] > 1.0]
        .sort_values("h_opt ($)", ascending=False)
        .reset_index(drop=True)
    )
    # print(f"Non-zero allocations: {len(alloc_nonzero)} / {N} bonds")
    # print(alloc_nonzero.to_string())

    # 4D. Charts (saved to disk; no GUI required)
    fig, ax = plt.subplots(figsize=(8, 4))
    comp = [nii_val, savings_val, -capital_cost_val, -turnover_val]
    lab  = ["Statutory NII", "Savings", "Capital cost", "Turnover"]
    ax.bar(lab, comp, color=["#2ecc71" if v >= 0 else "#e74c3c" for v in comp], edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("SAP Objective Decomposition")
    ax.set_ylabel("$ value")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    plt.tight_layout()
    # plt.savefig("sap_decomposition.png", dpi=100)
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(book_yield[~selected] * 100, h_opt[~selected],
               alpha=0.3, color="grey", s=15, label="Not selected")
    ax.scatter(book_yield[selected]  * 100, h_opt[selected],
               alpha=0.85, color="#2980b9", s=40, label="Selected")
    ax.set_xlabel("Book yield (%)")
    ax.set_ylabel("Optimal allocation ($)")
    ax.set_title("Book Yield vs Optimal Allocation")
    ax.legend()
    plt.tight_layout()
    # plt.savefig("sap_book_yield_vs_alloc.png", dpi=100)
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(["Coupon income", "Amortization/accretion"], [coupon_val, amort_val],
           color=["#3498db", "#9b59b6"], edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Statutory NII: Coupon vs Amortization")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    plt.tight_layout()
    # plt.savefig("sap_nii_decomp.png", dpi=100)
    plt.close()

    sector_alloc: dict[str, float] = {}
    for i, c in enumerate(CUSIPS):
        s = str(fixed_df.loc[c, "sector"])
        sector_alloc[s] = sector_alloc.get(s, 0.0) + h_opt[i]
    ss = pd.Series(sector_alloc)
    ss = ss[ss > 0].sort_values()
    fig, ax = plt.subplots(figsize=(9, max(4, len(ss) * 0.4)))
    ss.plot(kind="barh", ax=ax, color="#3498db", edgecolor="white")
    ax.set_title("Portfolio Allocation by Sector")
    ax.set_xlabel("Capital ($)")
    plt.tight_layout()
    # plt.savefig("sap_sector_alloc.png", dpi=100)
    plt.close()

    # 4E. Capital-cost sensitivity: SAP objective vs cost_of_capital (20 LP solves)
    def _solve_sap(coc=cost_of_capital, eta_=eta, eps_D_=eps_D, delta_=delta):
        lam = coc * RBC_bar
        m   = gp.Model("sap_sens")
        m.Params.LogToConsole = 0
        m.Params.OutputFlag   = 0
        h2 = m.addVars(N, lb=0.0)
        # Step 2: post-FABN-maturity bonds admissible (no h2[i].ub=0 exclusion)
        dp  = m.addVar(lb=0.0)
        dn  = m.addVar(lb=0.0)
        tp  = m.addVars(N, lb=0.0)
        tm  = m.addVars(N, lb=0.0)
        B2  = m.addVars(Q, lb=0.0)
        sn  = m.addVars(Q, lb=0.0)
        nii = gp.quicksum(nii_rate[i] * h2[i] for i in range(N))
        rbc = gp.quicksum(theta[i]    * h2[i] for i in range(N))
        txn = gp.quicksum(tau[i] * (tp[i] + tm[i]) for i in range(N))
        sav = r_save * dt_q * gp.quicksum(B2[q] for q in range(Q - 1))
        m.setObjective(nii - lam * rbc - txn + sav, GRB.MAXIMIZE)  # Step 1: no liq penalty (matches main model)
        m.addConstr(gp.quicksum(h2[i] for i in range(N)) == H)
        m.addConstr(gp.quicksum(durs[i] * h2[i] for i in range(N)) - D_FABN * H == dp - dn)
        m.addConstr(dp <= eps_D_ * H)
        m.addConstr(dn <= eps_D_ * H)
        for i in range(N):
            m.addConstr(h2[i] - h_curr[i] == tp[i] - tm[i])
        for iss, bidx in issuer_groups.items():
            m.addConstr(gp.quicksum(h2[i] for i in bidx) <= delta_ * H)
        for q in range(Q):
            cfa = gp.quicksum(qtr_bond_cf[q, i] * h2[i] for i in range(N))
            cfl = float(qtr_fabn_cf[q])
            if q == 0:
                m.addConstr(B2[q] - sn[q] == cfa - cfl)
            else:
                m.addConstr(B2[q] - sn[q] == (1.0 + r_save * dt_q) * B2[q - 1] + cfa - cfl)
        m.optimize()
        return m.ObjVal if m.Status == GRB.OPTIMAL else float("nan")

    coc_range = np.linspace(0.0, 0.20, 20)
    # print("Sweeping cost_of_capital -- 20 LP solves ...")
    sap_coc = [_solve_sap(coc=c) for c in coc_range]
    # print("Done.")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(coc_range * 100, sap_coc, "o-", color="#e74c3c", linewidth=1.8, markersize=4)
    ax.axvline(cost_of_capital * 100, color="red", linestyle="--", linewidth=1.0,
               label=f"Current = {cost_of_capital:.0%}")
    ax.set_xlabel("Cost of capital (%)")
    ax.set_ylabel("SAP objective ($)")
    ax.set_title("SAP Objective vs Cost of Capital (lambda sensitivity)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.legend()
    plt.tight_layout()
    # plt.savefig("sap_sensitivity.png", dpi=100)
    plt.close()

    # =========================================================================
    # CVaR CALIBRATION SWEEP
    # Re-solve on a COPY over a grid of phi_cvar; record how the portfolio
    # responds. Non-destructive: the headline `model` solution is untouched.
    # =========================================================================
    if not use_cvar:
        pass
        # print("use_cvar = False -- sweep skipped.")
    else:
        _ms = model.copy(); _ms.Params.OutputFlag = 0
        _cl = _ms.getConstrByName("cvar_limit")
        _S  = cvar_relloss.shape[0]
        _nt = int(np.ceil((1.0 - cvar_alpha) * _S))          # worst-5% count
        _hs = use_swaps and K > 0
        _Dsw = np.asarray(D_swap) if _hs else np.zeros(0)
        _dr  = np.asarray(cvar_d_rate)

        def _cvar_real(h_o, v_o):
            loss = cvar_relloss @ h_o
            if _hs and v_o.sum() > 0:
                loss = loss + (_dr[:, None] * (_Dsw * v_o)[None, :]).sum(axis=1)
            return float(np.sort(loss)[-_nt:].mean())

        # Fine grid: all the action lives between the INFEAS floor (~0.35% of H) and
        # the free optimum (~1.32% of H). Two loose points retained to show the plateau.
        phis = [round(p, 5) for p in (np.arange(50, 136, 5) / 10000.0)] + [0.015, 0.020]
        rec = []
        for p in phis:
            _cl.RHS = p * H
            _ms.optimize()
            if _ms.Status != GRB.OPTIMAL:
                rec.append(dict(phi=p, feasible=False, SAP=np.nan, NII=np.nan,
                                D_eff=np.nan, notional=np.nan, cvar_real=np.nan,
                                cvar_pi=np.nan, iss_bind=np.nan))
                continue
            h_o = np.array([_ms.getVarByName(f"h[{i}]").X for i in range(N)])
            v_o = np.array([_ms.getVarByName(f"v[{k}]").X for k in range(K)]) if _hs else np.zeros(0)
            d_eff = (float((durs * h_o).sum()) + (float((_Dsw * v_o).sum()) if _hs else 0.0)) / H
            rec.append(dict(
                phi=p, feasible=True, SAP=_ms.ObjVal,
                NII=float(sum(nii_rate[i] * h_o[i] for i in range(N))),
                D_eff=d_eff, notional=float(v_o.sum()) if _hs else 0.0,
                cvar_real=_cvar_real(h_o, v_o), cvar_pi=_cl.Pi,
                iss_bind=sum(1 for iss in issuer_groups
                             if abs(_ms.getConstrByName(f"conc_{iss}").Pi) > 1e-6)))
        sweep_df = pd.DataFrame(rec).sort_values("phi").reset_index(drop=True)
        sweep_df["CVaR governs?"] = np.where(sweep_df["cvar_pi"].abs() > 1e-6, "YES", "no")

        disp = pd.DataFrame({
            "phi_cvar"        : sweep_df.phi.map(lambda x: f"{x*100:.2f}%"),
            "budget $M"       : (sweep_df.phi * H / 1e6).round(1),
            "feas"            : np.where(sweep_df.feasible, "ok", "INFEAS"),
            "SAP $M"          : (sweep_df.SAP / 1e6).round(3),
            "NII $M"          : (sweep_df.NII / 1e6).round(3),
            "D_eff"           : sweep_df.D_eff.round(3),
            "Swap $M"         : (sweep_df.notional / 1e6).round(1),
            "CVaR real $M"    : (sweep_df.cvar_real / 1e6).round(2),
            "CVaR governs?"   : sweep_df["CVaR governs?"],
            "issuer caps bind": sweep_df.iss_bind,
        })
        # print("=" * 78)
        # print("  CVaR CALIBRATION SWEEP  (phi_cvar low = strict risk budget -> high = loose)")
        # print("=" * 78)
        # print(disp.to_string(index=False))
        _first = sweep_df.loc[sweep_df["CVaR governs?"] == "YES", "phi"]
        if len(_first):
            pass
            # print(f"\n  -> CVaR starts GOVERNING at phi_cvar <= {_first.max()*100:.2f}%  "
                  # f"(${_first.max()*H/1e6:.1f}M budget). Above that it is slack.")
        else:
            pass
            # print("\n  -> CVaR never binds on this grid; some other constraint governs throughout.")

        _f = sweep_df[sweep_df.feasible]
        x  = _f.phi * 100
        fig, ax = plt.subplots(2, 2, figsize=(13, 9))
        ax[0, 0].plot(x, _f.NII / 1e6, "o-", color="#2563eb")
        ax[0, 0].set_title("(#3)  NII vs phi_cvar"); ax[0, 0].set_ylabel("NII ($M)")
        ax[0, 1].plot(x, _f.D_eff, "o-", color="#059669")
        ax[0, 1].axhline(D_FABN, ls="--", c="grey", label=f"D_FABN = {D_FABN:.2f}")
        ax[0, 1].set_title("(#4)  Effective duration vs phi_cvar"); ax[0, 1].set_ylabel("D_eff (yr)")
        ax[0, 1].legend(fontsize=8)
        ax[1, 0].plot(x, _f.notional / 1e6, "o-", color="#d97706")
        ax[1, 0].set_title("(#5)  Swap notional vs phi_cvar"); ax[1, 0].set_ylabel("Notional ($M)")
        ax[1, 0].set_xlabel("phi_cvar (%)")
        ax[1, 1].plot(x, _f.cvar_real / 1e6, "o-", color="#dc2626")
        ax[1, 1].plot(x, (_f.phi * H) / 1e6, "k--", lw=1.0, label="phi_cvar budget")
        ax[1, 1].set_title("(#6)  Realized tail loss vs phi_cvar budget"); ax[1, 1].set_ylabel("$M")
        ax[1, 1].set_xlabel("phi_cvar (%)"); ax[1, 1].legend(fontsize=8)
        plt.tight_layout()
        # plt.savefig("cvar_calibration_sweep.png", dpi=100)
        plt.close()

    # print("Charts saved: fig5_facility_shadow_prices.png, fig6_7_reduced_cost.png, "
          # "fig8_shadow_augmented_score.png, fig910_reservation_price.png, "
          # "fig11_12_marginal_dollar.png, fig13_marginal_dollar_breakdown.png, "
          # "fig_swap_overlay.png, sap_decomposition.png, sap_book_yield_vs_alloc.png, "
          # "sap_nii_decomp.png, sap_sector_alloc.png, sap_sensitivity.png, "
          # "cvar_calibration_sweep.png")
