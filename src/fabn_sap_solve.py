"""FABN SAP Gurobi solve."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

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
      log_to_console: int = 0,
      optimization_date: str | None = None,
) -> dict[str, Any]:
    """Build and solve the FABN SAP LP; return a result dict."""
    import gurobipy as gp
    from gurobipy import GRB

    date = optimization_date or str(pipeline.get("optimization_date", ""))[:10]

    N = pipeline["N"]
    Q = pipeline["Q"]
    CUSIPS = pipeline["CUSIPS"]
    book_yield = pipeline["book_yield"]
    coupon_inc = pipeline["coupon_inc"]
    amort_inc = pipeline["amort_inc"]
    spread = pipeline["spread"]
    durs = pipeline["durs"]
    theta = pipeline["theta"]
    tau_raw = pipeline["tau"]
    h_curr = pipeline["h_curr"]
    qtr_bond_cf = pipeline["qtr_bond_cf"]
    qtr_fabn_cf = pipeline["qtr_fabn_cf"]
    qtr_idx = pipeline["qtr_idx"]
    H = pipeline["H"]
    r_FABN = pipeline["r_FABN"]
    D_FABN = pipeline["D_FABN"]
    RBC_bar = pipeline["RBC_bar"]
    fixed_df = pipeline["fixed"].set_index("CUSIP")

    lambda_cap = cost_of_capital * RBC_bar
    r_save = r_FABN * lambda_w
    effective_delta = min(w_max, 1.0 / max(n_min, 1))
    tau = tau_raw * 10

    eta = 1.0
    phi_sf = 0.01
    dt_q = 0.25
    nii_rate = book_yield - r_FABN

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

    t_quarters = [dt_q * (q + 1) for q in range(Q)]
    df_q = [(1.0 + r_FABN) ** (-t) for t in t_quarters]

    maturity = pd.to_datetime(
      pipeline["fixed"].set_index("CUSIP").loc[CUSIPS, "maturity"]
    ).values.astype("datetime64[ns]")
    post_fabn_mask = maturity > np.datetime64(_FABN_MATURITY)
    for i in range(N):
      if post_fabn_mask[i]:
        h[i].ub = 0.0

    NII = gp.quicksum(nii_rate[i] * h[i] for i in range(N))
    RBC = gp.quicksum(theta[i] * h[i] for i in range(N))
    capital_cost = lambda_cap * RBC
    turnover_cost = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
    liq_penalty = eta * gp.quicksum(df_q[q] * s_net[q] for q in range(Q))
    savings_income = r_save * dt_q * gp.quicksum(B[q] for q in range(Q - 1))

    SAP = NII - capital_cost - turnover_cost - liq_penalty + savings_income
    model.setObjective(SAP, GRB.MAXIMIZE)

    model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")
    model.addConstr(
      gp.quicksum(durs[i] * h[i] for i in range(N)) - D_FABN * H == d_pos - d_neg,
      name="dur_gap_decomp",
    )
    model.addConstr(d_pos <= eps_D * H, name="dur_upper")
    model.addConstr(d_neg <= eps_D * H, name="dur_lower")

    for i in range(N):
      model.addConstr(h[i] - h_curr[i] == tc_plus[i] - tc_minus[i], name=f"tc_decomp_{i}")

    for q in range(Q):
      cf_a_q = gp.quicksum(qtr_bond_cf[q, i] * h[i] for i in range(N))
      cf_l_q = float(qtr_fabn_cf[q])
      if q == 0:
        model.addConstr(B[q] - s_net[q] == cf_a_q - cf_l_q, name=f"facility_{q}")
      else:
        model.addConstr(
          B[q] - s_net[q] == (1.0 + r_save * dt_q) * B[q - 1] + cf_a_q - cf_l_q,
          name=f"facility_{q}",
        )

    pv_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))
    model.addConstr(
      gp.quicksum(df_q[q] * s_net[q] for q in range(Q)) <= phi_sf * pv_liability,
      name="pv_shortfall_limit",
    )

    issuer_groups: dict[str, list[int]] = {}
    for idx, cusip in enumerate(CUSIPS):
      issuer_groups.setdefault(cusip[:6], []).append(idx)
    for issuer, bond_indices in issuer_groups.items():
      model.addConstr(
        gp.quicksum(h[i] for i in bond_indices) <= effective_delta * H,
        name=f"concentration_{issuer}",
      )

    model.optimize()
    gurobi_status = int(model.Status)

    if model.Status == GRB.INFEASIBLE:
      logger.warning(
        "SAP model INFEASIBLE date=%s params=(%s,%s,%s,%s,%s)",
        date,
        cost_of_capital,
        lambda_w,
        eps_D,
        w_max,
        n_min,
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
    pv_shortfall_val = float(sum(s_net_vals[q] * df_q[q] for q in range(Q)))
    pv_sf_cap = phi_sf * pv_liability

    constraints = [
      {
        "label": "Budget",
        "value": round(float(h_opt.sum()), 2),
        "bound": round(float(H), 2),
        "pass": bool(abs(h_opt.sum() - H) < 1.0),
      },
      {
        "label": "Duration Gap",
        "value": round(float(abs(d_avg - D_FABN)), 4),
        "bound": round(float(eps_D), 4),
        "pass": bool(abs(d_avg - D_FABN) <= eps_D),
      },
      {
        "label": "PV Shortfall",
        "value": round(float(pv_shortfall_val), 2),
        "bound": round(float(pv_sf_cap), 2),
        "pass": bool(pv_shortfall_val <= pv_sf_cap),
      },
      {
        "label": f"HtM Excluded ({int(post_fabn_mask.sum())} bonds)",
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
      })
    alloc_list.sort(key=lambda x: x["h_opt"], reverse=True)

    buys_raw: list[dict] = []
    sells_raw: list[dict] = []
    for i in range(N):
      delta_usd = float(h_opt[i] - h_curr[i])
      if abs(delta_usd) <= 100_000:
        continue
      cusip = CUSIPS[i]
      sector = str(fixed_df.loc[cusip, "sector"]).strip() if cusip in fixed_df.index else ""
      rating = str(fixed_df.loc[cusip, "rating_sp"]).strip() if cusip in fixed_df.index else ""
      entry = {
        "cusip": cusip,
        "sector": sector,
        "rating": rating,
        "action": "BUY" if delta_usd > 0 else "SELL",
        "delta_weight_pct": round(delta_usd / H * 100, 3),
        "delta_usd": round(delta_usd, 2),
        "spread_bps": round(float(spread[i] * 1e4), 2),
        "duration": round(float(durs[i]), 4),
      }
      if delta_usd > 0:
        buys_raw.append(entry)
      else:
        sells_raw.append(entry)

    buys_raw.sort(key=lambda x: x["delta_usd"], reverse=True)
    sells_raw.sort(key=lambda x: x["delta_usd"])
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

    return {
      "status": "optimal",
      "gurobi_status": gurobi_status,
      "date": date,
      "h_opt": h_opt,
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
      "allocations": alloc_list,
      "trades": trades,
      "constraints": constraints,
      "cashflows": cashflows,
    }
