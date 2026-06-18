"""
Optimizer service — wraps Optimization/fabn_data_pipeline.py + SAP Gurobi solve.

Usage:
    result = run(date, gamma_w, lambda_w, eps_D, w_max, n_min)

    gamma_w  = cost_of_capital (insurer WACC, e.g. 0.15 = 15%)
    lambda_w = lending-facility reinvestment rate scalar (r_save = r_FABN × lambda_w)
    eps_D    = duration gap tolerance (years)
    w_max    = max single-bond weight fraction
    n_min    = min distinct bonds (enforced via effective_delta)

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
    lambda_w: float = 1.0,    # lending-facility rate scalar
    eps_D:    float = 0.3,    # duration gap tolerance (years)
    w_max:    float = 0.05,
    n_min:    int   = 20,
) -> dict:
    """Run the FABN SAP optimizer for a given date and hyperparameters."""
    try:
        return _solve(date, gamma_w, lambda_w, eps_D, w_max, n_min)
    except Exception as exc:
        logger.exception("Optimizer failed for date=%s", date)
        return {"status": "error", "date": date, "error": str(exc)}


# ═════════════════════════════════════════════════════════════════════════════
# Core SAP solve
# ═════════════════════════════════════════════════════════════════════════════

def _solve(
    date:     str,
    gamma_w:  float,   # cost_of_capital / WACC
    lambda_w: float,   # r_save = r_FABN * lambda_w
    eps_D:    float,
    w_max:    float,
    n_min:    int,
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
    Q           = pipeline["Q"]
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

    # ── 1B. SAP parameters from user inputs ───────────────────────────────
    # gamma_w is cost_of_capital (insurer WACC); lambda_cap = WACC * RBC_bar
    cost_of_capital = gamma_w
    lambda_cap      = cost_of_capital * RBC_bar

    # Lending-facility reinvestment rate
    r_save = r_FABN * lambda_w

    # effective_delta: tighter per-issuer cap forces at least n_min bonds
    effective_delta = min(w_max, 1.0 / max(n_min, 1))

    # Bid-ask half-spread ×10 (same scaling convention as SAP notebook)
    tau = tau_raw * 10

    eta    = 1.0    # liquidity penalty weight
    phi_sf = 0.01   # PV shortfall hard cap (1% of PV liability)
    dt_q   = 0.25   # quarter length in years

    # Net NII rate: book_yield - r_FABN
    nii_rate = book_yield - r_FABN

    # ── 1C. Swap universe parameters ──────────────────────────────────────
    K          = 3
    swap_tenor = np.array([1.0, 2.0, 3.0])                          # years
    c_swap     = np.array([0.043, 0.044, 0.045])                     # receive-fixed rates
    r_float    = float(pipeline.get("r_float", 0.0435))              # 3M Treasury / SOFR proxy
    swp_dur    = np.array([ff.swap_fixed_leg_duration(swap_tenor[k], c_swap[k], r_float)
                           for k in range(K)])
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

    # 2C. Hold-to-maturity exclusion: bonds maturing after FABN cannot fund it
    _maturity = pd.to_datetime(
        pipeline["fixed"].set_index("CUSIP").loc[CUSIPS, "maturity"]
    ).values.astype("datetime64[ns]")
    post_fabn_mask = _maturity > np.datetime64(_FABN_MATURITY)
    for i in range(N):
        if post_fabn_mask[i]:
            h[i].ub = 0.0

    # 2D. SAP Objective
    NII            = gp.quicksum(nii_rate[i] * h[i]              for i in range(N))
    RBC            = gp.quicksum(theta[i]    * h[i]              for i in range(N))
    capital_cost   = lambda_cap * RBC
    turnover_cost  = gp.quicksum(tau[i] * (tc_plus[i] + tc_minus[i]) for i in range(N))
    liq_penalty    = eta * gp.quicksum(df_q[q] * s_net[q]       for q in range(Q))
    savings_income = r_save * dt_q * gp.quicksum(B[q]           for q in range(Q - 1))

    swap_NII  = gp.quicksum((c_swap[k] - r_float) * v[k] for k in range(K))
    swap_RBC  = lambda_cap * mu_swap * gp.quicksum(v[k] for k in range(K))
    SAP = NII - capital_cost - turnover_cost - liq_penalty + savings_income + swap_NII - swap_RBC
    model.setObjective(SAP, GRB.MAXIMIZE)

    # 2E. Constraints
    # Budget
    model.addConstr(gp.quicksum(h[i] for i in range(N)) == H, name="budget")

    # Duration alignment band (bonds + swaps jointly)
    model.addConstr(
        gp.quicksum(durs[i] * h[i] for i in range(N))
        + gp.quicksum(swp_dur[k] * v[k] for k in range(K))
        - D_FABN * H == d_pos - d_neg,
        name="dur_gap_decomp",
    )
    model.addConstr(d_pos <= eps_D * H, name="dur_upper")
    model.addConstr(d_neg <= eps_D * H, name="dur_lower")

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

    # PV shortfall hard cap
    PV_liability = float(sum(float(qtr_fabn_cf[q]) * df_q[q] for q in range(Q)))
    model.addConstr(
        gp.quicksum(df_q[q] * s_net[q] for q in range(Q)) <= phi_sf * PV_liability,
        name="pv_shortfall_limit",
    )

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
    pv_shortfall_val  = float(sum(s_net_vals[q] * df_q[q] for q in range(Q)))
    pv_sf_cap         = phi_sf * PV_liability

    # Constraints
    constraints = [
        {
            "label": "Budget",
            "value": round(float(h_opt.sum()), 2),
            "bound": round(float(H), 2),
            "pass":  bool(abs(h_opt.sum() - H) < 1.0),
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
        {
            "label": f"HtM Excluded ({int(post_fabn_mask.sum())} bonds)",
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
            "score_bps":  round(float(book_yield[i] * 1e4), 2),  # book yield in bps
            "mid_price":  round(float(price[i]), 4),              # per $100 face
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
    pv_sf_pi     = _safe_pi("pv_shortfall_limit") or 0.0
    budget_pi    = _safe_pi("budget")

    shadow_prices = [
        {
            "label": "Budget (per $1 extra capital)",
            "dual":  budget_pi,
            "unit":  "$/$ ",
        },
        {
            "label": "Duration gap — upper (per 0.1yr wider band)",
            "dual":  round(dur_upper_pi * H * 0.1, 2),
            "unit":  "$",
        },
        {
            "label": "Duration gap — lower (per 0.1yr wider band)",
            "dual":  round(dur_lower_pi * H * 0.1, 2),
            "unit":  "$",
        },
        {
            "label": "PV Shortfall cap (per $1M relaxed)",
            "dual":  round(pv_sf_pi * 1e6, 2),
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
    }
