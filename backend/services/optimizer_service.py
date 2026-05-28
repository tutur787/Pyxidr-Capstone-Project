"""
Optimizer service — wraps fabn_data_pipeline.py + Gurobi LP solve.

Usage:
    result = run(date, gamma_w, lambda_w, eps_D, w_max, n_min)

The pipeline is cached per date (max 5 entries, LRU eviction).
Each call to `run` is expected to come from asyncio.to_thread so it never
blocks the FastAPI event loop.
"""

from __future__ import annotations

import logging
import os
import runpy
from collections import OrderedDict

import numpy as np
import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# backend/services/optimizer_service.py → ../../ = project root
PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PIPELINE_PATH = os.path.join(PROJECT_ROOT, 'fabn_data_pipeline.py')

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# ── FABN date range ────────────────────────────────────────────────────────────
_FABN_ISSUE    = pd.Timestamp("2022-09-06")
_FABN_MATURITY = pd.Timestamp("2027-09-06")

# ── Pipeline cache ─────────────────────────────────────────────────────────────
_pipeline_cache: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 5


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline loading
# ═════════════════════════════════════════════════════════════════════════════

def _get_pipeline(date: str) -> dict:
    """
    Return the pipeline dict for the given date string (YYYY-MM-DD).
    Validates the date, checks the LRU cache, and runs fabn_data_pipeline.py
    via runpy if not cached.
    """
    ts = pd.Timestamp(date)
    if ts <= _FABN_ISSUE:
        raise ValueError(
            f"Date {date} must be after FABN issue ({_FABN_ISSUE.date()})"
        )
    if ts >= _FABN_MATURITY:
        raise ValueError(
            f"Date {date} must be before FABN maturity ({_FABN_MATURITY.date()})"
        )

    if date in _pipeline_cache:
        _pipeline_cache.move_to_end(date)
        logger.info("Pipeline cache hit for %s", date)
        return _pipeline_cache[date]

    logger.info("Running pipeline for %s (cache miss — BigQuery queries in progress)…", date)
    ns = runpy.run_path(PIPELINE_PATH, init_globals={"optimization_date": ts})
    pipeline = ns["pipeline"]

    _pipeline_cache[date] = pipeline
    _pipeline_cache.move_to_end(date)
    if len(_pipeline_cache) > _CACHE_MAX:
        evicted = _pipeline_cache.popitem(last=False)
        logger.info("Evicted pipeline cache entry: %s", evicted[0])

    return pipeline


# ═════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═════════════════════════════════════════════════════════════════════════════

def run(
    date:     str,
    gamma_w:  float = 1.0,
    lambda_w: float = 1.0,
    eps_D:    float = 0.5,
    w_max:    float = 0.05,
    n_min:    int   = 20,
) -> dict:
    """
    Run the FABN optimizer for a given date and hyperparameters.
    Always returns a dict with at least {"status": …, "date": …}.
    """
    try:
        return _solve(date, gamma_w, lambda_w, eps_D, w_max, n_min)
    except Exception as exc:
        logger.exception("Optimizer failed for date=%s", date)
        return {"status": "error", "date": date, "error": str(exc)}


# ═════════════════════════════════════════════════════════════════════════════
# Core solve
# ═════════════════════════════════════════════════════════════════════════════

def _solve(
    date:     str,
    gamma_w:  float,
    lambda_w: float,
    eps_D:    float,
    w_max:    float,
    n_min:    int,
) -> dict:
    import gurobipy as gp
    from gurobipy import GRB

    pipeline = _get_pipeline(date)

    # ── 1A. Unpack pipeline ────────────────────────────────────────────────
    N           = pipeline["N"]
    Q           = pipeline["Q"]
    CUSIPS      = pipeline["CUSIPS"]
    spread      = pipeline["spread"]       # (N,) decimal, NaN-filled
    durs        = pipeline["durs"]         # (N,) modified duration
    theta       = pipeline["theta"]        # (N,) C-1 RBC factor
    h_curr      = pipeline["h_curr"]       # (N,) current allocation
    qtr_bond_cf = pipeline["qtr_bond_cf"]  # (Q, N) quarterly CF per $1 face
    qtr_fabn_cf = pipeline["qtr_fabn_cf"]  # (Q,)  FABN liability CF
    qtr_idx     = pipeline["qtr_idx"]
    H           = pipeline["H"]            # total budget ($)
    r_FABN      = pipeline["r_FABN"]       # FABN funding rate (annual)
    D_FABN      = pipeline["D_FABN"]       # liability modified duration
    C_curr      = pipeline["C_curr"]       # current regulatory capital
    C_min       = pipeline["C_min"]        # minimum required capital
    RBC_bar     = pipeline["RBC_bar"]      # minimum solvency ratio
    dt          = pipeline["dt"]           # time scaling (annual)
    alpha_w     = pipeline["alpha_w"]      # C3 duration scaling
    tau         = pipeline["tau"]          # transaction cost per bond
    score       = pipeline["score"]        # spread + beta*signal
    fixed_df    = pipeline["fixed"].set_index("CUSIP")

    # ── 1B. Parameter overrides from user ──────────────────────────────────
    # lambda_w controls the lending facility rate: 1.0 → r_lend = r_FABN (default)
    r_lend = r_FABN * lambda_w

    # effective_delta: tighter per-issuer cap ensures at least n_min bonds
    effective_delta = min(w_max, 1.0 / max(n_min, 1))

    phi_sf = 0.01    # PV shortfall hard cap (1 % of PV liability)
    dt_q   = 0.25    # one quarter = 0.25 yrs

    # ── 2. Build Gurobi model ──────────────────────────────────────────────
    model = gp.Model("FABN_NEV_Optimizer")
    model.Params.LogToConsole = 0
    model.Params.OutputFlag   = 0

    # 2A. Decision variables
    h = model.addVars(N, lb=0.0, name="h")

    # 2B. Auxiliary variables
    d_pos    = model.addVar(lb=0.0, name="d_pos")
    d_neg    = model.addVar(lb=0.0, name="d_neg")
    tc_plus  = model.addVars(N, lb=0.0, name="tc_plus")
    tc_minus = model.addVars(N, lb=0.0, name="tc_minus")
    B        = model.addVars(Q, lb=0.0, name="B")
    s_net    = model.addVars(Q, lb=0.0, name="s_net")

    # 2C. Objective — maximize NEV
    spread_income = gp.quicksum(score[i] * h[i] for i in range(N))
    C1            = gp.quicksum(theta[i] * h[i] for i in range(N))
    C3            = alpha_w * (d_pos + d_neg)
    capital_cost  = gamma_w * (C1 + C3)
    txn_cost      = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
    NEV           = spread_income - capital_cost - txn_cost
    model.setObjective(NEV, GRB.MAXIMIZE)

    # 2D. Core constraints
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

    # Bond liquidation at FABN maturity: discount future CFs of long bonds
    fabn_last_q = max(q for q in range(Q) if float(qtr_fabn_cf[q]) > 0)
    aug_bond_cf = qtr_bond_cf.copy().astype(float)
    for _i in range(N):
        for _q in range(fabn_last_q + 1, Q):
            _dt_q = (_q - fabn_last_q) * dt_q
            aug_bond_cf[fabn_last_q, _i] += qtr_bond_cf[_q, _i] * (1.0 + r_FABN) ** (-_dt_q)
            aug_bond_cf[_q, _i] = 0.0

    # Discount factors for PV shortfall constraint
    t_quarters = [dt_q * (q + 1) for q in range(Q)]
    df_q = [(1.0 + r_FABN) ** (-t) for t in t_quarters]

    # Lending facility balance dynamics
    for q in range(Q):
        CF_A_q = gp.quicksum(aug_bond_cf[q, i] * h[i] for i in range(N))
        CF_L_q = float(qtr_fabn_cf[q])
        if q == 0:
            model.addConstr(
                B[q] - s_net[q] == CF_A_q - CF_L_q,
                name=f"facility_balance_{q}",
            )
        else:
            model.addConstr(
                B[q] - s_net[q] == (1.0 + r_lend * dt_q) * B[q - 1] + CF_A_q - CF_L_q,
                name=f"facility_balance_{q}",
            )

    # PV shortfall hard cap
    PV_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))
    model.addConstr(
        gp.quicksum(df_q[q] * s_net[q] for q in range(Q)) <= phi_sf * PV_liability,
        name="pv_shortfall_limit",
    )

    # 2E. Issuer concentration constraint (always active; effective_delta from params)
    issuer_groups: dict[str, list[int]] = {}
    for idx, cusip in enumerate(CUSIPS):
        issuer_groups.setdefault(cusip[:6], []).append(idx)
    for issuer, bond_indices in issuer_groups.items():
        model.addConstr(
            gp.quicksum(h[i] for i in bond_indices) <= effective_delta * H,
            name=f"concentration_{issuer}",
        )

    # ── 2F. Solve ──────────────────────────────────────────────────────────
    model.optimize()

    if model.Status == GRB.INFEASIBLE:
        logger.warning("Model INFEASIBLE for date=%s params=(%s,%s,%s,%s,%s)",
                       date, gamma_w, lambda_w, eps_D, w_max, n_min)
        return {"status": "infeasible", "date": date}

    if model.Status != GRB.OPTIMAL:
        return {"status": "error", "date": date,
                "error": f"Gurobi status code {model.Status}"}

    # ── 3. Extract results ─────────────────────────────────────────────────
    h_opt = np.array([h[i].X for i in range(N)])

    nev_val           = model.ObjVal
    C1_val            = float(sum(theta[i] * h_opt[i] for i in range(N)))
    C3_val            = float(alpha_w * (d_pos.X + d_neg.X))
    capital_cost_val  = float(gamma_w * (C1_val + C3_val))
    spread_income_val = float(sum(score[i] * h_opt[i] for i in range(N)))
    txn_cost_val      = float(sum(tau[i] * (tc_plus[i].X + tc_minus[i].X) for i in range(N)))

    D_avg   = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    RBC_val = (C_curr + float(sum(spread[i] * h_opt[i] for i in range(N))) * dt) / C_min

    weighted_avg_spread = float(sum(spread[i] * h_opt[i] for i in range(N))) / H
    yield_pct_val = (r_FABN + weighted_avg_spread) * 100

    pv_shortfall_val = float(sum(s_net[q].X * df_q[q] for q in range(Q)))
    pv_sf_cap        = phi_sf * PV_liability

    selected_mask = h_opt > 1.0

    # Constraints
    constraints = [
        {
            "label": "Budget",
            "value": round(float(h_opt.sum()), 2),
            "bound": round(float(H), 2),
            "pass":  bool(abs(h_opt.sum() - H) < 1.0),
        },
        {
            "label": "Solvency (RBC)",
            "value": round(float(RBC_val), 4),
            "bound": round(float(RBC_bar), 4),
            "pass":  bool(RBC_val >= RBC_bar),
        },
        {
            "label": "Duration Gap",
            "value": round(float(abs(D_avg - D_FABN)), 4),
            "bound": round(float(eps_D), 4),
            "pass":  bool(abs(D_avg - D_FABN) <= eps_D),
        },
        {
            "label": "PV Shortfall",
            "value": round(float(pv_shortfall_val), 2),
            "bound": round(float(pv_sf_cap), 2),
            "pass":  bool(pv_shortfall_val <= pv_sf_cap),
        },
    ]

    # Allocations (bonds with h_opt > $1, sorted by h_opt desc)
    alloc_list: list[dict] = []
    for i in range(N):
        if not selected_mask[i]:
            continue
        cusip  = CUSIPS[i]
        sector = str(fixed_df.loc[cusip, "sector"]).strip() if cusip in fixed_df.index else ""
        rating = str(fixed_df.loc[cusip, "rating_sp"]).strip() if cusip in fixed_df.index else ""
        alloc_list.append({
            "cusip":      cusip,
            "sector":     sector,
            "rating":     rating,
            "h_opt":      round(float(h_opt[i]), 2),
            "h_curr":     round(float(h_curr[i]), 2),
            "delta_usd":  round(float(h_opt[i] - h_curr[i]), 2),
            "weight":     round(float(h_opt[i] / H), 6),
            "spread_bps": round(float(spread[i] * 1e4), 2),
            "duration":   round(float(durs[i]), 4),
            "score_bps":  round(float(score[i] * 1e4), 2),
        })
    alloc_list.sort(key=lambda x: x["h_opt"], reverse=True)

    # Trades (|delta_usd| > $100k).
    # Return top 15 BUYs + top 15 SELLs separately so neither side crowds out
    # the other — sorted by magnitude within each group, BUYs first.
    buys_raw:  list[dict] = []
    sells_raw: list[dict] = []
    for i in range(N):
        delta_usd = float(h_opt[i] - h_curr[i])
        if abs(delta_usd) <= 100_000:
            continue
        cusip  = CUSIPS[i]
        sector = str(fixed_df.loc[cusip, "sector"]).strip() if cusip in fixed_df.index else ""
        rating = str(fixed_df.loc[cusip, "rating_sp"]).strip() if cusip in fixed_df.index else ""
        entry = {
            "cusip":            cusip,
            "sector":           sector,
            "rating":           rating,
            "action":           "BUY" if delta_usd > 0 else "SELL",
            "delta_weight_pct": round(delta_usd / H * 100, 3),
            "delta_usd":        round(delta_usd, 2),
            "spread_bps":       round(float(spread[i] * 1e4), 2),
            "duration":         round(float(durs[i]), 4),
        }
        if delta_usd > 0:
            buys_raw.append(entry)
        else:
            sells_raw.append(entry)

    buys_raw.sort(key=lambda x: x["delta_usd"], reverse=True)          # largest buy first
    sells_raw.sort(key=lambda x: x["delta_usd"])                       # largest sell (most negative) first
    trades = buys_raw[:15] + sells_raw[:15]

    # Cashflows (quarters where FABN CF > 0 only)
    CF_A_vals = [
        float(sum(aug_bond_cf[q, i] * h_opt[i] for i in range(N)))
        for q in range(Q)
    ]
    cashflows: list[dict] = []
    for q in range(Q):
        fabn_cf_q = float(qtr_fabn_cf[q])
        if fabn_cf_q <= 0:
            continue
        asset_cf_q = CF_A_vals[q]
        cashflows.append({
            "period":        str(qtr_idx[q]),
            "fabn_cf":       round(fabn_cf_q, 2),
            "asset_cf":      round(asset_cf_q, 2),
            "surplus":       round(asset_cf_q - fabn_cf_q, 2),
            "shortfall_net": round(float(s_net[q].X), 2),
            "facility_bal":  round(float(B[q].X), 2),
        })

    return {
        "status":           "optimal",
        "date":             date,
        # KPIs
        "n_bonds_universe": int(N),
        "n_bonds_selected": int(selected_mask.sum()),
        "spread_bps":       round(float(weighted_avg_spread * 1e4), 2),
        "duration":         round(float(D_avg), 4),
        "yield_pct":        round(float(yield_pct_val), 3),
        "rbc_c1_usage":     round(float(C1_val / H), 4),
        "rbc_ratio":        round(float(RBC_val), 2),
        "nev":              round(float(nev_val), 2),
        "spread_income":    round(float(spread_income_val), 2),
        "capital_cost":     round(float(capital_cost_val), 2),
        "c1_cost":          round(float(C1_val), 2),
        "c3_cost":          round(float(C3_val), 2),
        "txn_cost":         round(float(txn_cost_val), 2),
        "duration_gap":     round(float(abs(D_avg - D_FABN)), 4),
        # Detail arrays
        "allocations":      alloc_list,
        "trades":           trades,
        "constraints":      constraints,
        "cashflows":        cashflows,
    }
