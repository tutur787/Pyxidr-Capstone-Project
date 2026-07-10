"""fabn_optimizer_sap — FABN SAP (Statutory Accounting Principles) optimizer.

Reformulates the FABN bond allocation around the SAP objective:

    max  Σ(y_i - r_FABN)·h_i  -  λ_cap·Σ(θ_i·h_i)  -  η·PV(shortfall)
         - Σ τ_i·(tc⁺_i + tc⁻_i)  +  r_save·dt_q·Σ B[q]

where y_i = book yield (coupon + amortization), λ_cap = cost_of_capital × RBC_bar.

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
print(f"Optimization date selected : {optimization_date.date()}")

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

# =============================================================================
# Section 1A — Unpack Pipeline
# =============================================================================
N           = pipeline["N"]
Q           = pipeline["Q"]
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

H           = pipeline["H"]            # total budget ($)
r_FABN      = pipeline["r_FABN"]       # FABN funding rate (annual)
D_FABN      = pipeline["D_FABN"]       # liability modified duration (yrs)
RBC_bar     = pipeline["RBC_bar"]      # required-capital multiplier on RBC
eps_D       = pipeline["eps_D"]        # duration band tolerance (yrs)

print(f"Pipeline loaded: N={N}, Q={Q}  |  date {optimization_date.date()}")
print(f"Book yield mean {book_yield.mean()*100:.2f}%  |  tau mean {tau.mean()*1e4:.1f} bps")

# =============================================================================
# Section 1B — SAP Objective Parameters
# =============================================================================
cost_of_capital = 0.15              # insurer WACC on required capital (annual)
lambda_cap      = cost_of_capital * RBC_bar    # = 0.225

eta             = 1.0               # weight on PV(lending-facility shortfall)

r_save          = r_FABN            # rate earned on facility surplus (reinvestment)
r_borrow        = 0.05              # rate on drawn shortfall (informational only)
phi_sf          = 0.01              # PV shortfall hard cap, fraction of PV(FABN)
dt_q            = 0.25              # quarter length in years

delta           = 0.05              # max 5% of budget per issuer

income_basis    = "net"
nii_rate = (book_yield - r_FABN) if income_basis == "net" else book_yield.copy()

print(f"lambda_cap = {lambda_cap:.4f}  (cost_of_capital {cost_of_capital:.1%} x RBC_bar {RBC_bar})")
print(f"eta        = {eta}   |   income basis = {income_basis}")
print(f"NII rate   : {nii_rate.min()*100:.2f}% – {nii_rate.max()*100:.2f}%  "
      f"(mean {nii_rate.mean()*100:.2f}%)")

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

# Discount factors at r_FABN
t_quarters = [dt_q * (q + 1) for q in range(Q)]
df_q       = [(1.0 + r_FABN) ** (-t) for t in t_quarters]

# Hold-to-maturity exclusion: bonds maturing after FABN cannot fund it
_maturity = pd.to_datetime(
    pipeline["fixed"].set_index("CUSIP").loc[CUSIPS, "maturity"]
).values.astype("datetime64[ns]")
post_fabn_mask = _maturity > np.datetime64(FABN_MATURITY)
for i in range(N):
    if post_fabn_mask[i]:
        h[i].ub = 0.0
print(f"Hold-to-maturity: {int(post_fabn_mask.sum())}/{N} bonds excluded "
      f"(maturity > {FABN_MATURITY.date()})")

# 2C. Objective: Statutory NII - lambda*RBC - eta*Liquidity - tau*Turnover + savings
NII            = gp.quicksum(nii_rate[i] * h[i]              for i in range(N))
RBC            = gp.quicksum(theta[i]    * h[i]              for i in range(N))
capital_cost   = lambda_cap * RBC
turnover_cost  = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
liq_penalty    = eta * gp.quicksum(df_q[q] * s_net[q]       for q in range(Q))
savings_income = r_save * dt_q * gp.quicksum(B[q]           for q in range(Q - 1))

SAP = NII - capital_cost - turnover_cost - liq_penalty + savings_income
model.setObjective(SAP, GRB.MAXIMIZE)

# 2D. Constraints
# Budget
model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")

# Duration alignment band
model.addConstr(
    gp.quicksum(durs[i] * h[i] for i in range(N)) - D_FABN * H == d_pos - d_neg,
    name="dur_gap_decomp",
)
model.addConstr(d_pos <= eps_D * H, name="dur_upper")
model.addConstr(d_neg <= eps_D * H, name="dur_lower")

# Turnover decomposition
for i in range(N):
    model.addConstr(h[i] - h_curr[i] == tc_plus[i] - tc_minus[i], name=f"tc_decomp_{i}")

# Lending-facility balance dynamics (direct qtr_bond_cf; no aug_bond_cf needed)
for q in range(Q):
    CF_A_q = gp.quicksum(qtr_bond_cf[q, i] * h[i] for i in range(N))
    CF_L_q = float(qtr_fabn_cf[q])
    if q == 0:
        model.addConstr(B[q] - s_net[q] == CF_A_q - CF_L_q, name=f"facility_{q}")
    else:
        model.addConstr(
            B[q] - s_net[q] == (1.0 + r_save * dt_q) * B[q - 1] + CF_A_q - CF_L_q,
            name=f"facility_{q}",
        )

# PV shortfall hard cap
PV_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))
model.addConstr(
    gp.quicksum(df_q[q] * s_net[q] for q in range(Q)) <= phi_sf * PV_liability,
    name="pv_shortfall_limit",
)
print(f"PV(FABN liability) = ${PV_liability:,.2f}   shortfall cap = ${phi_sf*PV_liability:,.2f}")

# Issuer concentration cap (first 6 CUSIP chars = issuer)
issuer_groups: dict[str, list[int]] = {}
for idx, cusip in enumerate(CUSIPS):
    issuer_groups.setdefault(cusip[:6], []).append(idx)
for issuer, bidx in issuer_groups.items():
    model.addConstr(
        gp.quicksum(h[i] for i in bidx) <= delta * H, name=f"conc_{issuer}"
    )

# 2E. Solve
model.optimize()

# =============================================================================
# Section 3 — Results
# =============================================================================
if model.Status == GRB.OPTIMAL:
    h_opt = np.array([h[i].X for i in range(N)])

    nii_val          = float(sum(nii_rate[i]  * h_opt[i] for i in range(N)))
    coupon_val       = float(sum(coupon_inc[i] * h_opt[i] for i in range(N)))
    amort_val        = float(sum(amort_inc[i]  * h_opt[i] for i in range(N)))
    RBC_val          = float(sum(theta[i]      * h_opt[i] for i in range(N)))
    capital_cost_val = lambda_cap * RBC_val
    turnover_val     = float(sum(tau[i] * (tc_plus[i].X + tc_minus[i].X) for i in range(N)))
    B_vals           = [B[q].X     for q in range(Q)]
    s_net_vals       = [s_net[q].X for q in range(Q)]
    liq_val          = eta * float(sum(df_q[q] * s_net_vals[q] for q in range(Q)))
    savings_val      = r_save * dt_q * float(sum(B_vals[q] for q in range(Q - 1)))
    sap_val          = model.ObjVal

    D_avg        = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    req_cap      = RBC_bar * RBC_val
    earn_per_cap = nii_val / req_cap if req_cap > 0 else float("nan")

    print("=" * 60)
    print(f"  SAP OBJECTIVE            : ${sap_val:>14,.2f}")
    print(f"  (1) Statutory NII        : ${nii_val:>14,.2f}")
    print(f"      - coupon income      : ${coupon_val:>14,.2f}")
    print(f"      - amortization       : ${amort_val:>14,.2f}")
    print(f"  (2) Savings income       : ${savings_val:>14,.2f}")
    print(f"  (3) Capital cost lambda*RBC: ${capital_cost_val:>12,.2f}")
    print(f"  (4) Liquidity penalty     : ${liq_val:>13,.2f}")
    print(f"  (5) Turnover cost         : ${turnover_val:>13,.2f}")
    print("=" * 60)
    print(f"  RBC (Sum f_i h_i)        : ${RBC_val:,.2f}   required capital ${req_cap:,.2f}")
    print(f"  Statutory earnings / req. capital : {earn_per_cap:.4f}")
    print(f"  Portfolio D_avg          : {D_avg:.4f} yrs  (target {D_FABN:.4f} +/- {eps_D})")
    print("=" * 60)

    pv_short = float(sum(df_q[q] * s_net_vals[q] for q in range(Q)))
    constraints_df = pd.DataFrame({
        "Constraint": [
            "Budget (Sum h = H)",
            "Duration (|D_avg-D_FABN|<=eps_D)",
            "PV shortfall (<= phi_sf*PV_liab)",
        ],
        "Value": [h_opt.sum(), abs(D_avg - D_FABN), pv_short],
        "Bound": [H, eps_D, phi_sf * PV_liability],
        "Pass":  [
            "PASS" if abs(h_opt.sum() - H) < 1.0 else "FAIL",
            "PASS" if abs(D_avg - D_FABN) <= eps_D + 1e-6 else "FAIL",
            "PASS" if pv_short <= phi_sf * PV_liability + 1.0 else "FAIL",
        ],
    })
    print(constraints_df.to_string())

elif model.Status == GRB.INFEASIBLE:
    print("INFEASIBLE -- computing IIS")
    model.computeIIS()
    model.write("infeasible_sap.ilp")
else:
    print(f"Solver status {model.Status} -- no optimal solution.")

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
            "Liquidity penalty", "Turnover cost", "SAP OBJECTIVE",
        ],
        "Value ($)": [
            nii_val, coupon_val, amort_val, savings_val,
            -capital_cost_val, -liq_val, -turnover_val, sap_val,
        ],
    })
    print(sap_summary.to_string())

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
    print(analytics.to_string())

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
    print(f"Non-zero allocations: {len(alloc_nonzero)} / {N} bonds")
    print(alloc_nonzero.to_string())

    # 4D. Charts (saved to disk; no GUI required)
    fig, ax = plt.subplots(figsize=(8, 4))
    comp = [nii_val, savings_val, -capital_cost_val, -liq_val, -turnover_val]
    lab  = ["Statutory NII", "Savings", "Capital cost", "Liquidity", "Turnover"]
    ax.bar(lab, comp, color=["#2ecc71" if v >= 0 else "#e74c3c" for v in comp], edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("SAP Objective Decomposition")
    ax.set_ylabel("$ value")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    plt.tight_layout()
    plt.savefig("sap_decomposition.png", dpi=100)
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
    plt.savefig("sap_book_yield_vs_alloc.png", dpi=100)
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(["Coupon income", "Amortization/accretion"], [coupon_val, amort_val],
           color=["#3498db", "#9b59b6"], edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Statutory NII: Coupon vs Amortization")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    plt.tight_layout()
    plt.savefig("sap_nii_decomp.png", dpi=100)
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
    plt.savefig("sap_sector_alloc.png", dpi=100)
    plt.close()

    # 4E. Capital-cost sensitivity: SAP objective vs cost_of_capital (20 LP solves)
    def _solve_sap(coc=cost_of_capital, eta_=eta, eps_D_=eps_D, delta_=delta):
        lam = coc * RBC_bar
        m   = gp.Model("sap_sens")
        m.Params.LogToConsole = 0
        m.Params.OutputFlag   = 0
        h2 = m.addVars(N, lb=0.0)
        for i in range(N):
            if post_fabn_mask[i]:
                h2[i].ub = 0.0
        dp  = m.addVar(lb=0.0)
        dn  = m.addVar(lb=0.0)
        tp  = m.addVars(N, lb=0.0)
        tm  = m.addVars(N, lb=0.0)
        B2  = m.addVars(Q, lb=0.0)
        sn  = m.addVars(Q, lb=0.0)
        nii = gp.quicksum(nii_rate[i] * h2[i] for i in range(N))
        rbc = gp.quicksum(theta[i]    * h2[i] for i in range(N))
        txn = gp.quicksum(tau[i] * (tp[i] + tm[i]) for i in range(N))
        liq = eta_ * gp.quicksum(df_q[q] * sn[q] for q in range(Q))
        sav = r_save * dt_q * gp.quicksum(B2[q] for q in range(Q - 1))
        m.setObjective(nii - lam * rbc - txn - liq + sav, GRB.MAXIMIZE)
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
        m.addConstr(gp.quicksum(df_q[q] * sn[q] for q in range(Q)) <= phi_sf * PV_liability)
        m.optimize()
        return m.ObjVal if m.Status == GRB.OPTIMAL else float("nan")

    coc_range = np.linspace(0.0, 0.20, 20)
    print("Sweeping cost_of_capital -- 20 LP solves ...")
    sap_coc = [_solve_sap(coc=c) for c in coc_range]
    print("Done.")

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
    plt.savefig("sap_sensitivity.png", dpi=100)
    plt.close()

    print("Charts saved: sap_decomposition.png, sap_book_yield_vs_alloc.png, "
          "sap_nii_decomp.png, sap_sector_alloc.png, sap_sensitivity.png")
