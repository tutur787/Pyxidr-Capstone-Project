"""FABN SAP Gurobi solve.

Current-generation SAP LP: pay-fixed interest-rate swap overlay (hedges bonds
maturing after the FABN instead of excluding them) + a CVaR tail-loss limit
(Rockafellar-Uryasev, historical rate/spread shock scenarios from the pipeline)
that replaces the older PV-shortfall hard cap as the primary risk control. See
``Optimization/CLAUDE.md`` for the full derivation this was ported from.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

import fabn_finance as ff

logger = logging.getLogger(__name__)

_FABN_MATURITY = pd.Timestamp("2027-09-06")


def solve_sap(
    pipeline: dict[str, Any],
    *,
    cost_of_capital: float = 0.15,
    lambda_w: float = 1.0,
    eps_D: float = 0.3,
    w_max: float = 0.05,
    n_min: int = 20,
    phi_cvar: float = 0.01,
    log_to_console: int = 0,
    optimization_date: str | None = None,
) -> dict[str, Any]:
    """Build and solve the FABN SAP LP; return a result dict."""
    import gurobipy as gp
    from gurobipy import GRB

    date = optimization_date or str(pipeline.get("optimization_date", ""))[:10]

    N = pipeline["N"]
    CUSIPS = pipeline["CUSIPS"]
    book_yield = pipeline["book_yield"]
    coupon_inc = pipeline["coupon_inc"]
    amort_inc = pipeline["amort_inc"]
    spread = pipeline["spread"]
    durs = pipeline["durs"]
    theta = pipeline["theta"]
    tau_raw = pipeline["tau"]
    h_curr = pipeline["h_curr"]
    price = pipeline["price"]
    qtr_bond_cf = pipeline["qtr_bond_cf"]
    qtr_fabn_cf = pipeline["qtr_fabn_cf"]
    qtr_idx = pipeline["qtr_idx"]
    H = pipeline["H"]
    r_FABN = pipeline["r_FABN"]
    D_FABN = pipeline["D_FABN"]
    RBC_bar = pipeline["RBC_bar"]
    fixed_df = pipeline["fixed"].set_index("CUSIP")
    cvar_relloss = pipeline["cvar_relloss"]  # (S,N) per-$ forced-sale loss coeffs (Step 4)
    cvar_d_rate = pipeline["cvar_d_rate"]    # (S,) per-scenario rate shock (swap MV)
    cvar_alpha = pipeline["cvar_alpha"]      # CVaR tail level (worst 5%)

    # Truncate the quarterly grid to the FABN's own maturity horizon. Without this,
    # Q spans however far the bond universe's cashflows run (driven by long-maturity
    # bonds admissible via the swap overlay below), and the facility balance keeps
    # compounding phantom quarters after the liability itself has matured.
    _fabn_qtr = pd.Period(_FABN_MATURITY, freq="Q")
    _keep = qtr_idx <= _fabn_qtr
    qtr_bond_cf = qtr_bond_cf[_keep]
    qtr_fabn_cf = qtr_fabn_cf[_keep]
    qtr_idx = qtr_idx[_keep]
    Q = len(qtr_idx)

    lambda_cap = cost_of_capital * RBC_bar
    # Facility "no free parking": r_FABN's base is forced to 0.0 for reinvestment
    # purposes, so lambda_w is currently a functional no-op — kept for compatibility.
    r_save = 0.0 * lambda_w
    effective_delta = min(w_max, 1.0 / max(n_min, 1))
    tau = tau_raw * 10

    eta = 1.0
    dt_q = 0.25
    nii_rate = book_yield - r_FABN

    # CVaR tail-loss control replaces the duration band + PV-shortfall cap as the
    # primary risk control (see module docstring).
    use_cvar = True

    # ── Swap universe parameters ────────────────────────────────────────────
    K = 3
    swap_tenor = np.array([1.0, 2.0, 3.0])                            # pay-fixed tenors (years)
    r_float = 0.0435                                                  # SOFR proxy: ~3M Treasury
    c_swap = np.full(K, r_float)                                      # at-the-money: pure hedge, zero carry/CF
    swp_dur = -np.array([ff.swap_fixed_leg_duration(swap_tenor[k], c_swap[k], r_float)
                         for k in range(K)])                          # pay-fixed: negative duration
    mu_swap = 0.002                                                   # C3 RBC factor per $1 notional
    v_max_frac = 0.20                                                 # max 20% of H in swaps

    swap_cf_sched = np.array([
        ff.swap_quarterly_cashflows(c_swap[k], r_float, swap_tenor[k], Q)
        for k in range(K)
    ])  # shape: (K, Q)

    model = gp.Model("FABN_SAP_Optimizer")
    model.Params.LogToConsole = log_to_console
    model.Params.OutputFlag = log_to_console

    h = model.addVars(N, lb=0.0, name="h")
    d_pos = model.addVar(lb=0.0, name="d_pos")
    d_neg = model.addVar(lb=0.0, name="d_neg")
    tc_plus = model.addVars(N, lb=0.0, name="tc_plus")
    tc_minus = model.addVars(N, lb=0.0, name="tc_minus")
    B = model.addVars(Q, lb=0.0, name="B")
    s_net = model.addVars(Q, lb=0.0, name="s_net")
    v = model.addVars(K, lb=0.0, name="v")

    t_quarters = [dt_q * (q + 1) for q in range(Q)]
    df_q = [(1.0 + r_FABN) ** (-t) for t in t_quarters]

    # Open universe: bonds maturing after the FABN are admissible (the swap
    # overlay hedges their sale-price rate risk instead of excluding them).
    maturity = pd.to_datetime(
        pipeline["fixed"].set_index("CUSIP").loc[CUSIPS, "maturity"]
    ).values.astype("datetime64[ns]")
    post_fabn_mask = maturity > np.datetime64(_FABN_MATURITY)

    NII = gp.quicksum(nii_rate[i] * h[i] for i in range(N))
    RBC = gp.quicksum(theta[i] * h[i] for i in range(N))
    capital_cost = lambda_cap * RBC
    turnover_cost = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
    savings_income = r_save * dt_q * gp.quicksum(B[q] for q in range(Q - 1))
    swap_NII = gp.quicksum((c_swap[k] - r_float) * v[k] for k in range(K))
    swap_RBC = lambda_cap * mu_swap * gp.quicksum(v[k] for k in range(K))

    SAP = NII - capital_cost - turnover_cost + savings_income + swap_NII - swap_RBC
    model.setObjective(SAP, GRB.MAXIMIZE)

    model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")

    model.addConstr(
        gp.quicksum(durs[i] * h[i] for i in range(N))
        + gp.quicksum(swp_dur[k] * v[k] for k in range(K))
        - D_FABN * H == d_pos - d_neg,
        name="dur_gap_decomp",
    )
    eps_D_eff = 100.0 if use_cvar else eps_D
    model.addConstr(d_pos <= eps_D_eff * H, name="dur_upper")
    model.addConstr(d_neg <= eps_D_eff * H, name="dur_lower")

    for i in range(N):
        model.addConstr(h[i] - h_curr[i] == tc_plus[i] - tc_minus[i], name=f"tc_decomp_{i}")

    for q in range(Q):
        cf_a_q = gp.quicksum(qtr_bond_cf[q, i] * h[i] for i in range(N))
        swap_cf_q = gp.quicksum(swap_cf_sched[k, q] * v[k] for k in range(K))
        cf_l_q = float(qtr_fabn_cf[q])
        if q == 0:
            model.addConstr(B[q] - s_net[q] == cf_a_q + swap_cf_q - cf_l_q, name=f"facility_{q}")
        else:
            model.addConstr(
                B[q] - s_net[q] == (1.0 + r_save * dt_q) * B[q - 1] + cf_a_q + swap_cf_q - cf_l_q,
                name=f"facility_{q}",
            )

    # PV-shortfall hard cap removed — CVaR governs risk; facility retained as buffer.
    pv_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))

    issuer_groups: dict[str, list[int]] = {}
    for idx, cusip in enumerate(CUSIPS):
        issuer_groups.setdefault(cusip[:6], []).append(idx)
    for issuer, bond_indices in issuer_groups.items():
        model.addConstr(
            gp.quicksum(h[i] for i in bond_indices) <= effective_delta * H,
            name=f"concentration_{issuer}",
        )

    model.addConstr(gp.quicksum(v[k] for k in range(K)) <= v_max_frac * H, name="swap_cap")

    # CVaR tail-loss limit — Rockafellar-Uryasev linearization over historical
    # rate/spread shock scenarios generated in the pipeline.
    if use_cvar:
        S_scen = cvar_relloss.shape[0]
        cvar_zeta = model.addVar(lb=-GRB.INFINITY, name="cvar_zeta")
        cvar_z = model.addVars(S_scen, lb=0.0, name="cvar_z")
        for s in range(S_scen):
            loss_s = gp.quicksum(float(cvar_relloss[s, i]) * h[i] for i in range(N))
            loss_s = loss_s + gp.quicksum(float(swp_dur[k]) * float(cvar_d_rate[s]) * v[k] for k in range(K))
            model.addConstr(cvar_z[s] >= loss_s - cvar_zeta, name=f"cvar_excess_{s}")
        cvar_expr = cvar_zeta + (1.0 / ((1.0 - cvar_alpha) * S_scen)) * gp.quicksum(cvar_z[s] for s in range(S_scen))
        model.addConstr(cvar_expr <= phi_cvar * H, name="cvar_limit")

    model.optimize()
    gurobi_status = int(model.Status)

    if model.Status == GRB.INFEASIBLE:
        logger.warning(
            "SAP model INFEASIBLE date=%s params=(%s,%s,%s,%s,%s,%s)",
            date, cost_of_capital, lambda_w, eps_D, w_max, n_min, phi_cvar,
        )
        return {
            "status": "infeasible",
            "gurobi_status": gurobi_status,
            "date": date,
            "h_opt": None,
        }

    if model.Status != GRB.OPTIMAL:
        return {
            "status": "error",
            "gurobi_status": gurobi_status,
            "date": date,
            "error": f"Gurobi status code {model.Status}",
            "h_opt": None,
        }

    h_opt = np.array([h[i].X for i in range(N)])
    v_opt = np.array([v[k].X for k in range(K)])

    sap_val = model.ObjVal
    nii_val = float(sum(nii_rate[i] * h_opt[i] for i in range(N)))
    coupon_val = float(sum(coupon_inc[i] * h_opt[i] for i in range(N)))
    amort_val = float(sum(amort_inc[i] * h_opt[i] for i in range(N)))
    rbc_val = float(sum(theta[i] * h_opt[i] for i in range(N)))
    capital_cost_val = lambda_cap * rbc_val
    turnover_val = float(sum(tau[i] * (tc_plus[i].X + tc_minus[i].X) for i in range(N)))
    b_vals = [B[q].X for q in range(Q)]
    s_net_vals = [s_net[q].X for q in range(Q)]
    liq_val = eta * float(sum(df_q[q] * s_net_vals[q] for q in range(Q)))
    savings_val = r_save * dt_q * float(sum(b_vals[q] for q in range(Q - 1)))

    d_avg = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    req_cap = RBC_bar * rbc_val
    earn_per_cap = nii_val / req_cap if req_cap > 0 else 0.0

    selected_mask = h_opt > 1.0
    wtd_book_yield = float(sum(book_yield[i] * h_opt[i] for i in range(N))) / H
    wtd_spread = float(sum(spread[i] * h_opt[i] for i in range(N))) / H
    pv_shortfall_val = float(sum(s_net_vals[q] * df_q[q] for q in range(Q)))  # diagnostic only, no cap

    # Honest realized CVaR tail loss (not the LP's zeta artifact).
    cvar_S = cvar_relloss.shape[0]
    cvar_ntail = int(np.ceil((1.0 - cvar_alpha) * cvar_S))
    cvar_loss = cvar_relloss @ h_opt
    cvar_loss = cvar_loss + (np.asarray(cvar_d_rate)[:, None] * (np.asarray(swp_dur) * v_opt)[None, :]).sum(axis=1)
    cvar_realized = float(np.sort(cvar_loss)[-cvar_ntail:].mean())

    constraints = [
        {
            "label": "Budget",
            "value": round(float(h_opt.sum()), 2),
            "bound": round(float(H), 2),
            "pass": bool(abs(h_opt.sum() - H) < 1.0),
        },
        {
            "label": f"CVaR worst-{1 - cvar_alpha:.0%} tail loss",
            "value": round(cvar_realized, 2),
            "bound": round(phi_cvar * H, 2),
            "pass": bool(cvar_realized <= phi_cvar * H + 1.0),
        },
        {
            "label": "Duration Gap (relaxed — CVaR governs)",
            "value": round(float(abs(d_avg - D_FABN)), 4),
            "bound": None,
            "pass": True,
        },
        {
            "label": f"HtM bonds no longer excluded ({int(post_fabn_mask.sum())} eligible)",
            "value": int(post_fabn_mask.sum()),
            "bound": N,
            "pass": True,
        },
    ]

    alloc_list: list[dict] = []
    for i in range(N):
        if not selected_mask[i]:
            continue
        cusip = CUSIPS[i]
        sector = str(fixed_df.loc[cusip, "sector"]).strip() if cusip in fixed_df.index else ""
        rating = str(fixed_df.loc[cusip, "rating_sp"]).strip() if cusip in fixed_df.index else ""
        alloc_list.append({
            "cusip": cusip,
            "sector": sector,
            "rating": rating,
            "h_opt": round(float(h_opt[i]), 2),
            "h_curr": round(float(h_curr[i]), 2),
            "delta_usd": round(float(h_opt[i] - h_curr[i]), 2),
            "weight": round(float(h_opt[i] / H), 6),
            "spread_bps": round(float(spread[i] * 1e4), 2),
            "duration": round(float(durs[i]), 4),
            "score_bps": round(float(book_yield[i] * 1e4), 2),
            "mid_price": round(float(price[i]), 4),
            "reduced_cost": round(float(h[i].RC), 6),
            "rbc_factor_pct": round(float(theta[i] * 100), 4),
        })
    alloc_list.sort(key=lambda x: x["h_opt"], reverse=True)

    # Trades: top 15 BUYs + top 15 SELLs, ranked by SAP contribution rate per dollar
    # (net SAP $ per $ held), matching how the LP itself values a bond.
    buys_raw: list[dict] = []
    sells_raw: list[dict] = []
    for i in range(N):
        delta_usd = float(h_opt[i] - h_curr[i])
        if abs(delta_usd) <= 100_000:
            continue
        cusip = CUSIPS[i]
        sector = str(fixed_df.loc[cusip, "sector"]).strip() if cusip in fixed_df.index else ""
        rating = str(fixed_df.loc[cusip, "rating_sp"]).strip() if cusip in fixed_df.index else ""
        sap_rate = float(nii_rate[i] - lambda_cap * theta[i])
        entry = {
            "cusip": cusip,
            "sector": sector,
            "rating": rating,
            "action": "BUY" if delta_usd > 0 else "SELL",
            "delta_weight_pct": round(delta_usd / H * 100, 3),
            "delta_usd": round(delta_usd, 2),
            "spread_bps": round(float(spread[i] * 1e4), 2),
            "duration": round(float(durs[i]), 4),
            "sap_score_bps": round(sap_rate * 1e4, 2),
            "mid_price": round(float(price[i]), 4),
        }
        if delta_usd > 0:
            buys_raw.append(entry)
        else:
            sells_raw.append(entry)

    buys_raw.sort(key=lambda x: x["sap_score_bps"], reverse=True)
    sells_raw.sort(key=lambda x: x["sap_score_bps"])
    trades = buys_raw[:15] + sells_raw[:15]

    cf_a_vals = [
        float(sum(qtr_bond_cf[q, i] * h_opt[i] for i in range(N)))
        for q in range(Q)
    ]
    cashflows: list[dict] = []
    for q in range(Q):
        fabn_cf_q = float(qtr_fabn_cf[q])
        if fabn_cf_q <= 0:
            continue
        asset_cf_q = cf_a_vals[q]
        cashflows.append({
            "period": str(qtr_idx[q]),
            "fabn_cf": round(fabn_cf_q, 2),
            "asset_cf": round(asset_cf_q, 2),
            "surplus": round(asset_cf_q - fabn_cf_q, 2),
            "shortfall_net": round(float(s_net_vals[q]), 2),
            "facility_bal": round(float(b_vals[q]), 2),
        })

    swap_allocations = [
        {
            "tenor_years": float(swap_tenor[k]),
            "notional": round(float(v_opt[k]), 2),
            "fixed_rate": round(float(c_swap[k]), 4),
            "net_income": round(float((c_swap[k] - r_float) * v_opt[k]), 2),
            "dur_contrib": round(float(swp_dur[k] * v_opt[k] / H), 4),
        }
        for k in range(K)
    ]
    swap_notional_total = float(v_opt.sum())
    swap_cap_notional = float(v_max_frac * H)
    swap_c3_capital_cost = float(lambda_cap * mu_swap * swap_notional_total)

    return {
        "status": "optimal",
        "gurobi_status": gurobi_status,
        "date": date,
        "h_opt": h_opt,
        "v_opt": v_opt,
        "n_bonds_universe": int(N),
        "n_bonds_selected": int(selected_mask.sum()),
        "spread_bps": round(float(wtd_spread * 1e4), 2),
        "duration": round(float(d_avg), 4),
        "yield_pct": round(float(wtd_book_yield * 100), 3),
        "rbc_c1_usage": round(float(rbc_val / H), 4),
        "rbc_ratio": round(float(earn_per_cap), 4),
        "nev": round(float(sap_val), 2),
        "spread_income": round(float(nii_val), 2),
        "capital_cost": round(float(capital_cost_val), 2),
        "c1_cost": round(float(rbc_val), 2),
        "c3_cost": round(float(savings_val), 2),
        "txn_cost": round(float(turnover_val), 2),
        "duration_gap": round(float(abs(d_avg - D_FABN)), 4),
        "sap_val": round(float(sap_val), 2),
        "nii_val": round(float(nii_val), 2),
        "coupon_val": round(float(coupon_val), 2),
        "amort_val": round(float(amort_val), 2),
        "RBC_val": round(float(rbc_val), 2),
        "capital_cost_val": round(float(capital_cost_val), 2),
        "turnover_val": round(float(turnover_val), 2),
        "liq_val": round(float(liq_val), 2),
        "savings_val": round(float(savings_val), 2),
        "D_avg": round(float(d_avg), 4),
        "earn_per_cap": round(float(earn_per_cap), 4),
        "cvar_realized": round(float(cvar_realized), 2),
        "pv_shortfall_val": round(float(pv_shortfall_val), 2),
        "allocations": alloc_list,
        "trades": trades,
        "constraints": constraints,
        "cashflows": cashflows,
        "swap_allocations": swap_allocations,
        "swap_notional_total": round(swap_notional_total, 2),
        "swap_cap_notional": round(swap_cap_notional, 2),
        "swap_c3_capital_cost": round(swap_c3_capital_cost, 2),
    }
