"""
Optimizer service — wraps Optimization/fabn_data_pipeline.py + SAP Gurobi solve.

Usage:
    result = run(date, gamma_w, lambda_w, eps_D, w_max, n_min, phi_cvar=phi_cvar)

    gamma_w  = cost_of_capital (insurer WACC, e.g. 0.15 = 15%)
    lambda_w = lending-facility reinvestment rate scalar (r_save = r_FABN × lambda_w).
               NOTE: r_FABN's base is 0.0 (facility surplus earns nothing, matching
               the notebook's Step 3 "no free parking"), so lambda_w is currently a
               functional no-op — kept wired for forward compatibility.
    eps_D    = duration gap tolerance (years). Relaxed to an inert 100yr band
               whenever the CVaR risk constraint is active (always, currently).
    w_max    = max single-bond weight fraction
    n_min    = min distinct bonds (enforced via effective_delta)
    phi_cvar = CVaR risk budget: worst-5% tail forced-sale loss <= phi_cvar * H.
               Primary risk control (replaces the old PV-shortfall cap).

The pipeline is cached per date (max 5 entries, LRU eviction).
Each call to `run` is expected to come from asyncio.to_thread so it never
blocks the FastAPI event loop.
"""

from __future__ import annotations

import logging
import os
import runpy
import threading
from collections import OrderedDict

import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from services import risk_service

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# backend/services/optimizer_service.py → ../../ = project root
PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PIPELINE_PATH = os.path.join(PROJECT_ROOT, 'Optimization', 'fabn_data_pipeline.py')

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# fabn_finance lives in Optimization/ — add to path so it can be imported directly
_OPT_DIR = os.path.join(PROJECT_ROOT, 'Optimization')
if _OPT_DIR not in sys.path:
    sys.path.insert(0, _OPT_DIR)
import fabn_finance as ff

# ── FABN date range ────────────────────────────────────────────────────────────
_FABN_ISSUE    = pd.Timestamp("2022-09-06")
_FABN_MATURITY = pd.Timestamp("2027-09-06")

# ── Pipeline cache ─────────────────────────────────────────────────────────────
_pipeline_cache: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX  = 5
_cache_lock = threading.Lock()  # guards multi-step OrderedDict mutations under asyncio.to_thread

# ── Applied portfolio state ────────────────────────────────────────────────────
# Maps CUSIP -> h_opt dollars for trades the user has explicitly applied.
# Persists across dates; cleared only by reset_portfolio().
_applied_portfolio: dict[str, float] = {}


def apply_trade(cusip: str, h_opt_value: float) -> None:
    """Store a single trade as applied; overrides h_curr for that CUSIP."""
    _applied_portfolio[cusip] = float(h_opt_value)


def apply_trades(trades: list[tuple[str, float]]) -> None:
    """Apply multiple trades atomically — rolls back all writes on any exception."""
    snapshot = {cusip: _applied_portfolio.get(cusip) for cusip, _ in trades}
    try:
        for cusip, h_opt in trades:
            _applied_portfolio[cusip] = float(h_opt)
    except Exception:
        for cusip, prev in snapshot.items():
            if prev is None:
                _applied_portfolio.pop(cusip, None)
            else:
                _applied_portfolio[cusip] = prev
        raise


def reset_portfolio() -> None:
    """Clear all applied trades, reverting to the equal-weight baseline."""
    _applied_portfolio.clear()


def get_applied_count() -> int:
    return len(_applied_portfolio)


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline loading
# ═════════════════════════════════════════════════════════════════════════════

def _get_pipeline(date: str) -> dict:
    """Return the pipeline dict for the given date string (YYYY-MM-DD)."""
    ts = pd.Timestamp(date)
    if ts <= _FABN_ISSUE:
        raise ValueError(f"Date {date} must be after FABN issue ({_FABN_ISSUE.date()})")
    if ts >= _FABN_MATURITY:
        raise ValueError(f"Date {date} must be before FABN maturity ({_FABN_MATURITY.date()})")

    with _cache_lock:
        if date in _pipeline_cache:
            _pipeline_cache.move_to_end(date)
            logger.info("Pipeline cache hit for %s", date)
            return _pipeline_cache[date]

    logger.info("Running pipeline for %s (cache miss — BigQuery queries in progress)…", date)
    ns = runpy.run_path(PIPELINE_PATH, init_globals={"optimization_date": ts})
    pipeline = ns["pipeline"]

    with _cache_lock:
        if date not in _pipeline_cache:  # double-check: another thread may have populated it
            _pipeline_cache[date] = pipeline
            _pipeline_cache.move_to_end(date)
            if len(_pipeline_cache) > _CACHE_MAX:
                evicted = _pipeline_cache.popitem(last=False)
                logger.info("Evicted pipeline cache entry: %s", evicted[0])
        else:
            _pipeline_cache.move_to_end(date)
        return _pipeline_cache[date]


# ═════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═════════════════════════════════════════════════════════════════════════════

def run(
    date:     str,
    gamma_w:  float = 0.15,   # cost_of_capital (WACC), matches pipeline calibration
    lambda_w: float = 1.0,    # lending-facility rate scalar (currently a no-op, see module docstring)
    eps_D:    float = 0.3,    # duration gap tolerance (years) — relaxed while CVaR governs
    w_max:    float = 0.05,
    n_min:    int   = 20,
    vol_percentile: float = risk_service.DEFAULT_PERCENTILE,  # trading-signal threshold percentile
    phi_cvar: float = 0.01,   # CVaR risk budget: worst-5% tail loss <= phi_cvar * H
) -> dict:
    """Run the FABN SAP optimizer for a given date and hyperparameters."""
    try:
        return _solve(date, gamma_w, lambda_w, eps_D, w_max, n_min, vol_percentile, phi_cvar)
    except Exception as exc:
        logger.exception("Optimizer failed for date=%s", date)
        return {"status": "error", "date": date, "error": str(exc)}


# ═════════════════════════════════════════════════════════════════════════════
# Core SAP solve
# ═════════════════════════════════════════════════════════════════════════════

def _solve(
    date:     str,
    gamma_w:  float,   # cost_of_capital / WACC
    lambda_w: float,   # r_save = r_FABN * lambda_w (r_FABN base is 0.0, see module docstring)
    eps_D:    float,
    w_max:    float,
    n_min:    int,
    vol_percentile: float = risk_service.DEFAULT_PERCENTILE,
    phi_cvar: float = 0.01,
) -> dict:
    import gurobipy as gp
    from gurobipy import GRB

    pipeline = _get_pipeline(date)

    # ── 1. Inject applied-trade overrides into h_curr ─────────────────────
    if _applied_portfolio:
        h_curr_raw = pipeline["h_curr"].copy()
        for i, c in enumerate(pipeline["CUSIPS"]):
            if c in _applied_portfolio:
                h_curr_raw[i] = _applied_portfolio[c]
        pipeline = {**pipeline, "h_curr": h_curr_raw}

    # ── 1A. Unpack pipeline ────────────────────────────────────────────────
    N           = pipeline["N"]
    CUSIPS      = pipeline["CUSIPS"]
    book_yield  = pipeline["book_yield"]   # (N,) effective-interest yield
    coupon_inc  = pipeline["coupon_inc"]   # (N,) statutory coupon yield
    amort_inc   = pipeline["amort_inc"]    # (N,) amortization/accretion yield
    spread      = pipeline["spread"]       # (N,) OAS spread (for reporting)
    durs        = pipeline["durs"]         # (N,) modified duration
    theta       = pipeline["theta"]        # (N,) C-1 RBC factor
    tau_raw     = pipeline["tau"]          # (N,) bid-ask half-spread (raw)
    h_curr      = pipeline["h_curr"]       # (N,) current allocation ($)
    price       = pipeline["price"]        # (N,) mid price per 100 face
    qtr_bond_cf = pipeline["qtr_bond_cf"]  # (Q, N)
    qtr_fabn_cf = pipeline["qtr_fabn_cf"]  # (Q,)
    qtr_idx     = pipeline["qtr_idx"]
    H           = pipeline["H"]
    r_FABN      = pipeline["r_FABN"]
    D_FABN      = pipeline["D_FABN"]
    RBC_bar     = pipeline["RBC_bar"]
    fixed_df    = pipeline["fixed"].set_index("CUSIP")
    cvar_relloss = pipeline["cvar_relloss"]  # (S,N) per-$ forced-sale loss coeffs (Step 4)
    cvar_d_rate  = pipeline["cvar_d_rate"]   # (S,) per-scenario rate shock (swap MV)
    cvar_alpha   = pipeline["cvar_alpha"]    # CVaR tail level (worst 5%)

    # Truncate the quarterly grid to the FABN's own maturity horizon. Without this,
    # Q spans however far the bond universe's cashflows run (driven by long-maturity
    # bonds already excluded from holding via post_fabn_mask below), and the facility
    # balance keeps compounding "savings_income" for phantom quarters after the FABN
    # liability itself has matured — inflating the SAP objective. Matches the
    # notebook's Section 1A truncation exactly.
    _fabn_qtr   = pd.Period(_FABN_MATURITY, freq="Q")
    _keep       = qtr_idx <= _fabn_qtr
    qtr_bond_cf = qtr_bond_cf[_keep]
    qtr_fabn_cf = qtr_fabn_cf[_keep]
    qtr_idx     = qtr_idx[_keep]
    Q           = len(qtr_idx)

    # ── 1B. SAP parameters from user inputs ───────────────────────────────
    # gamma_w is cost_of_capital (insurer WACC); lambda_cap = WACC * RBC_bar
    cost_of_capital = gamma_w
    lambda_cap      = cost_of_capital * RBC_bar

    # Lending-facility reinvestment rate. Base r_FABN is forced to 0.0 (Step 3:
    # "no free parking" — facility surplus earns nothing), so r_save is always 0.0
    # regardless of lambda_w; lambda_w is kept as a wired-but-inert parameter.
    r_save = 0.0 * lambda_w

    # effective_delta: tighter per-issuer cap forces at least n_min bonds
    effective_delta = min(w_max, 1.0 / max(n_min, 1))

    # Bid-ask half-spread ×10 (same scaling convention as SAP notebook)
    tau = tau_raw * 10

    eta    = 1.0    # (reporting only — liq penalty removed from objective, no hard PV cap)
    phi_sf = 1      # DEPRECATED: PV-shortfall cap removed; CVaR governs risk
    dt_q   = 0.25   # quarter length in years

    # CVaR tail-loss control: replaces the duration band as primary risk control
    use_cvar = True

    # Net NII rate: book_yield - r_FABN
    nii_rate = book_yield - r_FABN

    # ── 1C. Swap universe parameters ──────────────────────────────────────
    K          = 3
    swap_tenor = np.array([1.0, 2.0, 3.0])                          # pay-fixed tenors (years)
    r_float    = 0.0435                                              # SOFR proxy: ~3M Treasury
    c_swap     = np.full(K, r_float)                                 # at-the-money: pure hedge, zero carry/CF
    swp_dur    = -np.array([ff.swap_fixed_leg_duration(swap_tenor[k], c_swap[k], r_float)
                            for k in range(K)])                      # pay-fixed: negative duration
    mu_swap    = 0.002                                               # C3 RBC factor per $1 notional
    v_max_frac = 0.20                                                # max 20% of H in swaps

    # Pre-compute swap quarterly settlement schedules (per $1 notional)
    swap_cf_sched = np.array([
        ff.swap_quarterly_cashflows(c_swap[k], r_float, swap_tenor[k], Q)
        for k in range(K)
    ])  # shape: (K, Q)

    # ── 2. Build Gurobi model ──────────────────────────────────────────────
    model = gp.Model("FABN_SAP_Optimizer")
    model.Params.LogToConsole = 0
    model.Params.OutputFlag   = 0

    # 2A. Decision variables
    h        = model.addVars(N, lb=0.0, name="h")

    # 2B. Auxiliary variables
    d_pos    = model.addVar(lb=0.0, name="d_pos")
    d_neg    = model.addVar(lb=0.0, name="d_neg")
    tc_plus  = model.addVars(N, lb=0.0, name="tc_plus")
    tc_minus = model.addVars(N, lb=0.0, name="tc_minus")
    B        = model.addVars(Q, lb=0.0, name="B")
    s_net    = model.addVars(Q, lb=0.0, name="s_net")

    # 2B-swap. Swap notional variables
    v = model.addVars(K, lb=0.0, name="v")

    # Discount factors at r_FABN
    t_quarters = [dt_q * (q + 1) for q in range(Q)]
    df_q       = [(1.0 + r_FABN) ** (-t) for t in t_quarters]

    # 2C. Step 2 open universe: post-FABN-maturity bonds admissible (was HTM
    # exclusion) — the pay-fixed swap hedges their sale-price rate risk instead.
    _maturity = pd.to_datetime(
        pipeline["fixed"].set_index("CUSIP").loc[CUSIPS, "maturity"]
    ).values.astype("datetime64[ns]")
    post_fabn_mask = _maturity > np.datetime64(_FABN_MATURITY)

    # 2D. SAP Objective
    NII            = gp.quicksum(nii_rate[i] * h[i]              for i in range(N))
    RBC            = gp.quicksum(theta[i]    * h[i]              for i in range(N))
    capital_cost   = lambda_cap * RBC
    turnover_cost  = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
    liq_penalty    = eta * gp.quicksum(df_q[q] * s_net[q]       for q in range(Q))
    savings_income = r_save * dt_q * gp.quicksum(B[q]           for q in range(Q - 1))

    swap_NII  = gp.quicksum((c_swap[k] - r_float) * v[k] for k in range(K))
    swap_RBC  = lambda_cap * mu_swap * gp.quicksum(v[k] for k in range(K))
    SAP = NII - capital_cost - turnover_cost + savings_income + swap_NII - swap_RBC  # liq_penalty removed — CVaR governs risk
    model.setObjective(SAP, GRB.MAXIMIZE)

    # 2E. Constraints
    # Budget
    model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")

    # Duration alignment band (bonds + swaps jointly). Relaxed to an inert 100yr
    # band while CVaR governs risk (matches the notebook's eps_D_eff pattern).
    model.addConstr(
        gp.quicksum(durs[i] * h[i] for i in range(N))
        + gp.quicksum(swp_dur[k] * v[k] for k in range(K))
        - D_FABN * H == d_pos - d_neg,
        name="dur_gap_decomp",
    )
    eps_D_eff = 100.0 if use_cvar else eps_D
    model.addConstr(d_pos <= eps_D_eff * H, name="dur_upper")
    model.addConstr(d_neg <= eps_D_eff * H, name="dur_lower")

    # Turnover decomposition
    for i in range(N):
        model.addConstr(h[i] - h_curr[i] == tc_plus[i] - tc_minus[i], name=f"tc_decomp_{i}")

    # Lending-facility dynamics (bonds + swap quarterly settlements)
    for q in range(Q):
        CF_A_q    = gp.quicksum(qtr_bond_cf[q, i] * h[i] for i in range(N))
        swap_cf_q = gp.quicksum(swap_cf_sched[k, q] * v[k] for k in range(K))
        CF_L_q    = float(qtr_fabn_cf[q])
        if q == 0:
            model.addConstr(B[q] - s_net[q] == CF_A_q + swap_cf_q - CF_L_q, name=f"facility_{q}")
        else:
            model.addConstr(
                B[q] - s_net[q] == (1.0 + r_save * dt_q) * B[q - 1] + CF_A_q + swap_cf_q - CF_L_q,
                name=f"facility_{q}",
            )

    # PV-shortfall hard cap REMOVED — CVaR governs risk; facility retained as buffer.
    PV_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))

    # Issuer concentration cap
    issuer_groups: dict[str, list[int]] = {}
    for idx, cusip in enumerate(CUSIPS):
        issuer_groups.setdefault(cusip[:6], []).append(idx)
    for issuer, bond_indices in issuer_groups.items():
        model.addConstr(
            gp.quicksum(h[i] for i in bond_indices) <= effective_delta * H,
            name=f"concentration_{issuer}",
        )

    # Swap notional cap
    model.addConstr(
        gp.quicksum(v[k] for k in range(K)) <= v_max_frac * H,
        name="swap_cap",
    )

    # CVaR tail-loss limit — governs rate/spread risk; replaces the duration band
    # and PV-shortfall cap. Rockafellar-Uryasev linearization over historical
    # rate/spread shock scenarios generated in the pipeline.
    if use_cvar:
        S_scen    = cvar_relloss.shape[0]
        cvar_zeta = model.addVar(lb=-GRB.INFINITY, name="cvar_zeta")
        cvar_z    = model.addVars(S_scen, lb=0.0, name="cvar_z")
        for s in range(S_scen):
            loss_s = gp.quicksum(float(cvar_relloss[s, i]) * h[i] for i in range(N))
            loss_s = loss_s + gp.quicksum(float(swp_dur[k]) * float(cvar_d_rate[s]) * v[k] for k in range(K))
            model.addConstr(cvar_z[s] >= loss_s - cvar_zeta, name=f"cvar_excess_{s}")
        cvar_expr = cvar_zeta + (1.0 / ((1.0 - cvar_alpha) * S_scen)) * gp.quicksum(cvar_z[s] for s in range(S_scen))
        model.addConstr(cvar_expr <= phi_cvar * H, name="cvar_limit")

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
    v_opt = np.array([v[k].X for k in range(K)])

    sap_val          = model.ObjVal
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

    D_avg        = float(sum(durs[i] * h_opt[i] for i in range(N))) / H
    req_cap      = RBC_bar * RBC_val
    earn_per_cap = nii_val / req_cap if req_cap > 0 else 0.0

    # Weighted-average book yield and OAS spread
    selected_mask     = h_opt > 1.0
    wtd_book_yield    = float(sum(book_yield[i] * h_opt[i] for i in range(N))) / H
    wtd_spread        = float(sum(spread[i] * h_opt[i] for i in range(N))) / H
    pv_shortfall_val  = float(sum(s_net_vals[q] * df_q[q] for q in range(Q)))  # diagnostic only, no cap

    # Honest realized CVaR tail loss (not the LP's zeta artifact)
    cvar_S     = cvar_relloss.shape[0]
    cvar_ntail = int(np.ceil((1.0 - cvar_alpha) * cvar_S))
    cvar_loss  = cvar_relloss @ h_opt
    cvar_loss  = cvar_loss + (np.asarray(cvar_d_rate)[:, None] * (np.asarray(swp_dur) * v_opt)[None, :]).sum(axis=1)
    cvar_realized = float(np.sort(cvar_loss)[-cvar_ntail:].mean())

    # Constraints
    constraints = [
        {
            "label": "Budget",
            "value": round(float(h_opt.sum()), 2),
            "bound": round(float(H), 2),
            "pass":  bool(abs(h_opt.sum() - H) < 1.0),
        },
        {
            "label": f"CVaR worst-{1 - cvar_alpha:.0%} tail loss",
            "value": round(cvar_realized, 2),
            "bound": round(phi_cvar * H, 2),
            "pass":  bool(cvar_realized <= phi_cvar * H + 1.0),
        },
        {
            "label": "Duration Gap (relaxed — CVaR governs)",
            "value": round(float(abs(D_avg - D_FABN)), 4),
            "bound": None,
            "pass":  True,
        },
        {
            "label": f"HtM bonds no longer excluded ({int(post_fabn_mask.sum())} eligible)",
            "value": int(post_fabn_mask.sum()),
            "bound": N,
            "pass":  True,
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
            "score_bps":    round(float(book_yield[i] * 1e4), 2),  # book yield in bps
            "mid_price":    round(float(price[i]), 4),              # per $100 face
            "reduced_cost": round(float(h[i].RC), 6),              # Gurobi reduced cost: SAP δ per $
            "rbc_factor_pct": round(float(theta[i] * 100), 4),     # C-1 RBC factor, pct of face
        })
    alloc_list.sort(key=lambda x: x["h_opt"], reverse=True)

    # Trades: top 15 BUYs + top 15 SELLs, ranked by SAP contribution rate per dollar.
    # sap_score = (book_yield_i - r_FABN) - lambda_cap * theta_i  [per $ invested]
    # BUYs: highest sap_score first (best NEV additions).
    # SELLs: lowest sap_score first (worst NEV contributors = best to exit).
    buys_raw:  list[dict] = []
    sells_raw: list[dict] = []
    for i in range(N):
        delta_usd = float(h_opt[i] - h_curr[i])
        if abs(delta_usd) <= 100_000:
            continue
        cusip  = CUSIPS[i]
        sector = str(fixed_df.loc[cusip, "sector"]).strip() if cusip in fixed_df.index else ""
        rating = str(fixed_df.loc[cusip, "rating_sp"]).strip() if cusip in fixed_df.index else ""
        sap_rate = float(nii_rate[i] - lambda_cap * theta[i])   # net SAP $ per $ held
        entry = {
            "cusip":            cusip,
            "sector":           sector,
            "rating":           rating,
            "action":           "BUY" if delta_usd > 0 else "SELL",
            "delta_weight_pct": round(delta_usd / H * 100, 3),
            "delta_usd":        round(delta_usd, 2),
            "h_opt":            round(float(h_opt[i]), 2),
            "spread_bps":       round(float(spread[i] * 1e4), 2),
            "duration":         round(float(durs[i]), 4),
            "sap_score_bps":    round(sap_rate * 1e4, 2),  # bps of net SAP per $ invested
            "mid_price":        round(float(price[i]), 4),  # market price per $100 face
        }
        if delta_usd > 0:
            buys_raw.append(entry)
        else:
            sells_raw.append(entry)

    buys_raw.sort(key=lambda x: x["sap_score_bps"], reverse=True)  # best NEV first
    sells_raw.sort(key=lambda x: x["sap_score_bps"])               # worst NEV first (best to exit)
    trades = buys_raw[:15] + sells_raw[:15]

    # Cashflows (quarters where FABN CF > 0)
    CF_A_vals = [
        float(sum(qtr_bond_cf[q, i] * h_opt[i] for i in range(N)))
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
            "shortfall_net": round(float(s_net_vals[q]), 2),
            "facility_bal":  round(float(B_vals[q]), 2),
        })

    # ── 4. Shadow prices (dual values of key constraints) ─────────────────
    def _safe_pi(name: str) -> float | None:
        try:
            return round(model.getConstrByName(name).Pi, 6)
        except Exception:
            return None

    dur_upper_pi = _safe_pi("dur_upper") or 0.0
    dur_lower_pi = _safe_pi("dur_lower") or 0.0
    cvar_pi      = _safe_pi("cvar_limit") or 0.0
    budget_pi    = _safe_pi("budget")

    shadow_prices = [
        {
            "label": "Budget (per $1 extra capital)",
            "dual":  budget_pi,
            "unit":  "$/$ ",
        },
        {
            "label": "Duration gap — upper (relaxed, CVaR governs)",
            "dual":  round(dur_upper_pi * H * 0.1, 2),
            "unit":  "$",
        },
        {
            "label": "Duration gap — lower (relaxed, CVaR governs)",
            "dual":  round(dur_lower_pi * H * 0.1, 2),
            "unit":  "$",
        },
        {
            "label": "CVaR tail-loss cap (per $1M relaxed)",
            "dual":  round(cvar_pi * 1e6, 2),
            "unit":  "$",
        },
        {
            "label": "Swap notional cap (per $1M relaxed)",
            "dual":  round((_safe_pi("swap_cap") or 0.0) * 1e6, 2),
            "unit":  "$",
        },
    ]

    # ── 4b. Swap overlay allocations ──────────────────────────────────────
    swap_allocations = [
        {
            "tenor_years": float(swap_tenor[k]),
            "notional":    round(float(v_opt[k]), 2),
            "fixed_rate":  round(float(c_swap[k]), 4),
            "net_income":  round(float((c_swap[k] - r_float) * v_opt[k]), 2),
            "dur_contrib": round(float(swp_dur[k] * v_opt[k] / H), 4),
        }
        for k in range(K)
    ]
    swap_notional_total = float(v_opt.sum())
    swap_cap_notional    = float(v_max_frac * H)
    swap_c3_capital_cost = float(lambda_cap * mu_swap * swap_notional_total)

    # ── 4c. Shadow-price analytics (matches notebook Section 3B / 3B-ii) ────
    # Cheap additions only: one extra re-solve for the issuer-cap-relaxed marginal
    # dollar, plus reading duals/reduced-costs already available from the base
    # solve. The notebook's Section 3B-iii budget-H sensitivity sweep (~120 extra
    # LP solves) is NOT ported here — it's an offline research tool, not viable
    # inside a synchronous API request; it stays in fabn_optimizer_sap.py only.
    rc = np.array([h[i].RC for i in range(N)])

    _m_unconstr = model.copy()
    _m_unconstr.Params.OutputFlag = 0
    for issuer in issuer_groups:
        _m_unconstr.getConstrByName(f"concentration_{issuer}").RHS = GRB.INFINITY
    _m_unconstr.optimize()
    marginal_dollar_unconstrained = (
        round(float(_m_unconstr.getConstrByName("budget").Pi), 6)
        if _m_unconstr.Status == GRB.OPTIMAL else None
    )

    pi_facility = [
        {"period": str(qtr_idx[q]), "dual": _safe_pi(f"facility_{q}") or 0.0}
        for q in range(Q)
    ]
    pi_issuer = sorted(
        (
            {"issuer": issuer, "dual": _safe_pi(f"concentration_{issuer}") or 0.0}
            for issuer in issuer_groups
        ),
        key=lambda x: abs(x["dual"]), reverse=True,
    )
    pi_issuer_binding = [row for row in pi_issuer if abs(row["dual"]) > 1e-6][:10]

    # Per-bond reservation price P*_i = PV(bond cashflows @ hurdle yield r*_i),
    # r*_i = book_yield_i - reduced_cost_i. Gap = P* - market price: positive
    # means the bond is worth more to this portfolio than its market price.
    r_star = book_yield - rc
    t_q_arr = np.array(t_quarters)
    reservation_prices: list[dict] = []
    for i in range(N):
        if post_fabn_mask[i]:
            continue
        cfs = qtr_bond_cf[:, i]
        if cfs.sum() < 1e-12 or r_star[i] <= -1:
            continue
        p_star = float((cfs * (1.0 + r_star[i]) ** (-t_q_arr)).sum()) * 100.0
        gap = p_star - float(price[i])
        reservation_prices.append({
            "cusip":           CUSIPS[i],
            "mkt_price":       round(float(price[i]), 3),
            "reservation_price": round(p_star, 3),
            "gap":             round(gap, 3),
            "gap_pct":         round(gap / float(price[i]) * 100, 3) if price[i] else 0.0,
            "hurdle_rate":     round(float(r_star[i]) * 100, 4),
            "selected":        bool(h_opt[i] > 1.0),
        })
    reservation_prices.sort(key=lambda x: x["gap"], reverse=True)

    # ── 5. IMR schedule ────────────────────────────────────────────────────
    # For each SELL trade, realized gain enters the IMR and amortizes over
    # the sold bond's remaining life. book_price = 100 (par) since h_curr is
    # an equal-weight placeholder with no real cost basis.
    ledger = ff.IMRLedger()
    imr_contributions: list[dict] = []
    for i in range(N):
        delta = float(h_opt[i] - h_curr[i])
        if delta < -100_000:
            sale_bv = abs(delta)
            gain    = ff.realized_gain_on_sale(sale_bv, float(price[i]), 100.0)
            rem_yrs = max(float(durs[i]), 0.25)
            ledger.add_realized(gain, rem_yrs)
            if abs(gain) > 1.0:
                cusip = CUSIPS[i]
                imr_contributions.append({
                    "cusip":         cusip,
                    "sale_usd":      round(sale_bv, 2),
                    "mid_price":     round(float(price[i]), 2),
                    "realized_gain": round(float(gain), 2),
                })

    imr_schedule: list[dict] = []
    for q in range(Q):
        released = ledger.accrue(dt_q)
        imr_schedule.append({
            "period":      str(qtr_idx[q]),
            "imr_balance": round(ledger.balance, 2),
            "imr_release": round(float(released), 2),
        })
    imr_total_gain = round(sum(c["realized_gain"] for c in imr_contributions), 2)

    # ── 6. Static benchmark (equal-weight across eligible bonds) ──────────
    eligible   = ~post_fabn_mask
    n_eligible = int(eligible.sum())
    h_static   = np.where(eligible, H / max(n_eligible, 1), 0.0)

    static_nii      = float((nii_rate * h_static).sum())
    static_rbc      = float((theta * h_static).sum())
    static_cap_cost = lambda_cap * static_rbc
    static_dur      = float((durs * h_static).sum()) / H
    static_sap      = static_nii - static_cap_cost

    static_comparison = {
        "nii":          round(static_nii, 2),
        "capital_cost": round(static_cap_cost, 2),
        "sap":          round(static_sap, 2),
        "duration":     round(static_dur, 4),
        "n_bonds":      n_eligible,
    }

    # ── 7. Risk analytics — CVaR + trading signal, both from the FABN YTM history ──
    cvar           = risk_service.compute_cvar(date, float(D_avg))
    trading_signal = risk_service.compute_trading_signal(date, percentile=vol_percentile)

    sector_weights: dict[str, float] = {}
    for a in alloc_list:
        key = a["sector"] or "Unclassified"
        sector_weights[key] = sector_weights.get(key, 0.0) + a["weight"]
    sector_breakdown = sorted(
        ({"sector": s, "weight_pct": round(w * 100, 2)} for s, w in sector_weights.items()),
        key=lambda x: -x["weight_pct"],
    )
    sector_concentration = {
        "top_sector":     sector_breakdown[0]["sector"] if sector_breakdown else "",
        "top_weight_pct": sector_breakdown[0]["weight_pct"] if sector_breakdown else 0.0,
        "breakdown":      sector_breakdown,
    }

    return {
        "status":           "optimal",
        "date":             date,
        # Portfolio KPIs
        "n_bonds_universe": int(N),
        "n_bonds_selected": int(selected_mask.sum()),
        "spread_bps":       round(float(wtd_spread * 1e4), 2),
        "duration":         round(float(D_avg), 4),
        "yield_pct":        round(float(wtd_book_yield * 100), 3),   # wtd-avg book yield
        "rbc_c1_usage":     round(float(RBC_val / H), 4),
        "rbc_ratio":        round(float(earn_per_cap), 4),           # statutory earnings / req. capital
        # SAP objective decomposition (mapped to existing frontend keys)
        "nev":              round(float(sap_val), 2),                # SAP objective value
        "spread_income":    round(float(nii_val), 2),                # Statutory NII
        "capital_cost":     round(float(capital_cost_val), 2),       # lambda_cap * RBC
        "c1_cost":          round(float(RBC_val), 2),                # Sum theta_i * h_i
        "c3_cost":          round(float(savings_val), 2),            # savings income
        "txn_cost":         round(float(turnover_val), 2),
        "duration_gap":     round(float(abs(D_avg - D_FABN)), 4),
        "duration_target":  round(float(D_FABN), 4),
        "r_FABN":           round(float(r_FABN), 6),
        "r_float":          round(float(r_float), 6),
        "rbc_bar":          round(float(RBC_bar), 4),
        "cvar_pct":         cvar["cvar_pct"],
        "cvar_var_pct":     cvar["var_pct"],
        "cvar_n_obs":       cvar["n_obs"],
        "cvar_degraded":    cvar["degraded"],
        "cvar_method":      cvar["method"],
        "cvar_histogram":   cvar["histogram"],
        "trading_signal":   trading_signal,
        "sector_concentration": sector_concentration,
        # Detail arrays
        "allocations":      alloc_list,
        "trades":           trades,
        "constraints":      constraints,
        "cashflows":        cashflows,
        # Strategy Tracking
        "shadow_prices":      shadow_prices,
        "imr_schedule":       imr_schedule,
        "imr_total_gain":     imr_total_gain,
        "imr_contributions":  imr_contributions,
        "static_comparison":  static_comparison,
        "swap_allocations":   swap_allocations,
        "swap_notional_total":  round(swap_notional_total, 2),
        "swap_cap_notional":    round(swap_cap_notional, 2),
        "swap_c3_capital_cost": round(swap_c3_capital_cost, 2),
        # Shadow-price / reservation-price analytics (notebook Section 3B / 3B-ii)
        "marginal_dollar_unconstrained": marginal_dollar_unconstrained,
        "pi_facility":         pi_facility,
        "pi_issuer_binding":   pi_issuer_binding,
        # Top 25 (most underpriced for us) + bottom 25 (most overpriced) by gap,
        # matching the notebook's Table 3 top-20/bottom-20 — full N-bond list isn't
        # needed by the UI and would bloat the payload.
        "reservation_prices":  reservation_prices[:25] + reservation_prices[-25:],
    }
