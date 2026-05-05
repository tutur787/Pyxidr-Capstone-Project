"""
FABN NEV portfolio optimizer — Gurobi LP.

Ported from Optimization/FABN_Optimizer_Gurobi.ipynb (model + export).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import gurobipy as gp
import numpy as np
import pandas as pd
from gurobipy import GRB

logger = logging.getLogger(__name__)


@dataclass
class FabnSolveResult:
    """Outcome of `solve_fabn_nev`."""

    status: int
    nev_val: float | None = None
    h_opt: np.ndarray | None = None
    spread_income_val: float | None = None
    capital_cost_val: float | None = None
    C1_val: float | None = None
    C3_val: float | None = None
    txn_cost_val: float | None = None
    cf_penalty_val: float | None = None
    D_avg: float | None = None
    RBC_val: float | None = None
    shortfall_total: float | None = None


def solve_fabn_nev(
    pipeline: dict[str, Any],
    *,
    log_to_console: int = 1,
) -> tuple[gp.Model, FabnSolveResult]:
    """
    Build the Gurobi LP from a pipeline dict (from `fabn_pipeline.build_pipeline`),
    optimize, and return the model plus a summary result object.
    """
    N = pipeline["N"]
    Q = pipeline["Q"]

    spread = pipeline["spread"]
    durs = pipeline["durs"]
    theta = pipeline["theta"]
    tau = pipeline["tau"]
    score = pipeline["score"]
    h_curr = pipeline["h_curr"]

    qtr_bond_cf = pipeline["qtr_bond_cf"]
    qtr_fabn_cf = pipeline["qtr_fabn_cf"]

    H = pipeline["H"]
    D_FABN = pipeline["D_FABN"]
    C_curr = pipeline["C_curr"]
    C_min = pipeline["C_min"]
    RBC_bar = pipeline["RBC_bar"]
    dt = pipeline["dt"]

    gamma_w = pipeline["gamma_w"]
    alpha_w = pipeline["alpha_w"]
    lambda_w = pipeline["lambda_w"]
    eps_D = pipeline["eps_D"]

    model = gp.Model("FABN_NEV_Optimizer")
    model.Params.LogToConsole = log_to_console

    h = model.addVars(N, lb=0.0, name="h")

    d_pos = model.addVar(lb=0.0, name="d_pos")
    d_neg = model.addVar(lb=0.0, name="d_neg")

    tc_plus = model.addVars(N, lb=0.0, name="tc_plus")
    tc_minus = model.addVars(N, lb=0.0, name="tc_minus")

    s = model.addVars(Q, lb=0.0, name="s")

    spread_income = gp.quicksum(score[i] * h[i] for i in range(N))
    C1 = gp.quicksum(theta[i] * h[i] for i in range(N))
    C3 = alpha_w * (d_pos + d_neg)
    capital_cost = gamma_w * (C1 + C3)
    txn_cost = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
    cf_shortfall_penalty = lambda_w * gp.quicksum(s[q] for q in range(Q))

    NEV_obj = spread_income - capital_cost - txn_cost - cf_shortfall_penalty
    model.setObjective(NEV_obj, GRB.MAXIMIZE)

    model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")

    rbc_rhs = (RBC_bar * C_min - C_curr) / dt
    model.addConstr(
        gp.quicksum(spread[i] * h[i] for i in range(N)) >= rbc_rhs,
        name="solvency",
    )

    model.addConstr(
        gp.quicksum(durs[i] * h[i] for i in range(N)) - D_FABN * H == d_pos - d_neg,
        name="dur_gap_decomp",
    )
    model.addConstr(d_pos <= eps_D * H, name="dur_upper")
    model.addConstr(d_neg <= eps_D * H, name="dur_lower")

    for i in range(N):
        model.addConstr(
            h[i] - h_curr[i] == tc_plus[i] - tc_minus[i],
            name=f"tc_decomp_{i}",
        )

    for q in range(Q):
        CF_A_q = gp.quicksum(qtr_bond_cf[q, i] * h[i] for i in range(N))
        CF_L_q = float(qtr_fabn_cf[q])
        model.addConstr(s[q] >= CF_L_q - CF_A_q, name=f"cf_shortfall_{q}")

    model.optimize()

    result = FabnSolveResult(status=model.Status)

    if model.Status != GRB.OPTIMAL:
        logger.warning("gurobi finished with status=%s (not optimal)", model.Status)
        return model, result

    h_opt = np.array([h[i].X for i in range(N)])
    nev_val = float(model.ObjVal)
    spread_income_val = float(sum(score[i] * h_opt[i] for i in range(N)))
    C1_val = float(sum(theta[i] * h_opt[i] for i in range(N)))
    C3_val = alpha_w * (d_pos.X + d_neg.X)
    capital_cost_val = gamma_w * (C1_val + C3_val)
    txn_cost_val = float(
        sum(tau[i] * (tc_plus[i].X + tc_minus[i].X) for i in range(N))
    )
    shortfall_total = float(sum(s[q].X for q in range(Q)))
    cf_penalty_val = lambda_w * shortfall_total

    D_avg = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    RBC_val = (
        C_curr + float(sum(spread[i] * h_opt[i] for i in range(N))) * dt
    ) / C_min

    result.nev_val = nev_val
    result.h_opt = h_opt
    result.spread_income_val = spread_income_val
    result.capital_cost_val = capital_cost_val
    result.C1_val = C1_val
    result.C3_val = C3_val
    result.txn_cost_val = txn_cost_val
    result.cf_penalty_val = cf_penalty_val
    result.D_avg = D_avg
    result.RBC_val = RBC_val
    result.shortfall_total = shortfall_total

    logger.info(
        "solve optimal NEV=%.2f spread_income=%.2f capital_cost=%.2f "
        "txn_cost=%.2f cf_penalty=%.2f C1=%.2f C3=%.2f D_avg=%.6f "
        "D_FABN=%.6f eps_D=%.6f RBC_ratio=%.4f",
        nev_val,
        spread_income_val,
        capital_cost_val,
        txn_cost_val,
        cf_penalty_val,
        C1_val,
        C3_val,
        D_avg,
        D_FABN,
        eps_D,
        RBC_val,
    )

    return model, result


def export_fabn_results(
    pipeline: dict[str, Any],
    result: FabnSolveResult,
    output_dir: str | None = None,
) -> None:
    """Write CSV outputs for an optimal solution."""
    if result.status != GRB.OPTIMAL or result.h_opt is None:
        logger.info("export skipped (no optimal solution)")
        return

    out = output_dir or os.environ.get("DATA_OUTPUT_DIR", "/app/data/output")
    os.makedirs(out, exist_ok=True)

    CUSIPS: list[str] = pipeline["CUSIPS"]
    spread = pipeline["spread"]
    score = pipeline["score"]
    h_curr = pipeline["h_curr"]
    theta = pipeline["theta"]
    h_opt = result.h_opt

    results_df = pd.DataFrame(
        {
            "Bond": CUSIPS,
            "h_opt ($)": h_opt,
            "h_curr ($)": h_curr,
            "Delta ($)": h_opt - h_curr,
            "Spread (bps)": spread * 10_000,
            "Score": score,
            "C1 charge ($)": theta * h_opt,
        }
    )
    csv_path = os.path.join(out, "optimizer_results.csv")
    results_df.to_csv(csv_path, index=False)
    logger.info("wrote %s", csv_path)

    summary = pd.Series(
        {
            "NEV ($)": result.nev_val,
            "Spread Income ($)": result.spread_income_val,
            "Capital Cost ($)": result.capital_cost_val,
            "Transaction Costs ($)": result.txn_cost_val,
            "CF Shortfall Penalty ($)": result.cf_penalty_val,
            "D_avg (yrs)": result.D_avg,
            "RBC Ratio (x)": result.RBC_val,
        }
    )
    summary_csv = (
        summary.to_frame("value").rename_axis("metric").reset_index()
    )
    summary_path = os.path.join(out, "nev_summary.csv")
    summary_csv.to_csv(summary_path, index=False)
    logger.info("wrote %s", summary_path)
