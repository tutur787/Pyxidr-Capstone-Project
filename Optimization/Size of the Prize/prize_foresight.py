"""prize_foresight — perfect-foresight ("size of the prize") upper bound for FABN.

Purpose
-------
A McKinsey reviewer asked for the *size of the prize*: if we knew the next two
years of prices **perfectly**, what is the maximum cumulative SAP / NII we could
earn — carry **plus** realized trading gains, net of bid-ask/2 cost — by trading
as much as it is worth? The answer is a **ceiling** (not a deployable strategy):
the gap between it and the realistic dynamic backtest tells us whether this
problem has tradeable upside worth engineering toward.

Method — time-expanded "trade-arc" LP
-------------------------------------
The trick that keeps SAP book-yield *locking* **linear** under perfect foresight:
enumerate trade arcs ``a = (bond i, buy node m, close node n)``. With the whole
price path known, each arc has a **constant** per-dollar profit:

    coef_a = net_carry_a + imr_window_a - cost_a

    net_carry_a = ((Y[m,i] - r_FABN) - lam*theta_i) * (t_n - t_m)   # locked carry net of capital
    imr_window_a = realized rate-driven gain on the sale at n, the portion an
                   IMR releases *within the measurement window* (0 if held to
                   maturity / never sold — par redemption books no gain)
    cost_a       = TAU[m,i] (+ TAU[n,i] if sold before maturity)    # bid-ask/2 both legs

Decision ``x_a >= 0`` = dollars of **book value** routed through arc ``a``. Book
value is conserved (the backtest's ``sum h_i == H`` invariant): a dollar enters at
``m`` and leaves at ``n``; the rate-driven gain trickles into income via the IMR
and is **never** added back to redeployable principal — that is exactly the
discipline that forbids the "discounted future cashflows as sale proceeds" trick.

This module is pure (numpy + a *lazy* gurobipy import) so the per-arc economics
are unit-testable without a solver. It reuses ``fabn_finance`` for every financial
primitive (amortized cost, realized gain, IMR semantics).

Conventions match ``FABN_Optimizer_SAP_Backtest.ipynb``: prices per 100 face,
``Y``/``TAU``/``theta`` decimals, times in years, dollars = book value.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fabn_finance as ff  # noqa: E402  (single source of truth for the math)


# ---------------------------------------------------------------------------
# Gurobi licensing — the arc LP is large (~50k vars); the free size-limited
# license caps at 2000. The repo's WLS credentials live in the root .env but
# nothing loads them (the daily backtest's per-solve model is small enough to
# fit the free license, so it never needed them). Load them here so this model
# uses the unlimited WLS license.
# ---------------------------------------------------------------------------
def load_dotenv_creds(path=None):
    """Read ``GRB_WLS*`` keys from a ``.env`` and **return** them (does not touch
    ``os.environ``).

    Searches upward from this file for ``.env`` (the repo root) if ``path`` is None.
    We deliberately do NOT export these into the environment: if the creds are
    invalid/expired, having ``GRB_WLSACCESSID`` set would make even the *default*
    license resolution attempt WLS and fail — masking a valid local/academic
    ``gurobi.lic``. They are only used to build an explicit WLS env, with fallback.
    """
    if path is None:
        d = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            cand = os.path.join(d, ".env")
            if os.path.exists(cand):
                path = cand
                break
            d = os.path.dirname(d)
    creds = {}
    if path and os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k.startswith("GRB_") and v:
                    creds[k] = v
    return creds


def make_gurobi_env(creds=None, verbose=False):
    """Return the best available Gurobi ``Env``, preferring a working license.

    Order of preference:
      1. The **default** license (a local/academic ``gurobi.lic`` or a WLS
         ``gurobi.env``) — unlimited for academic named-user licenses.
      2. If the default is the free **size-limited** license *and* ``creds`` carry
         WLS credentials, try an explicit WLS env.

    Whichever yields an unrestricted license wins; a working academic ``gurobi.lic``
    is never masked by stale ``.env`` WLS creds. Returns ``(env, kind)`` where
    ``kind`` is one of ``'default'`` / ``'wls'`` / ``'size-limited'``.
    """
    import gurobipy as gp

    def _quiet(env):
        if not verbose:
            env.setParam("OutputFlag", 0)
        return env

    # 1) default license
    try:
        env = gp.Env(empty=True)
        if not verbose:
            env.setParam("OutputFlag", 0)
        env.start()
        # probe whether it's the size-limited license by trying >2000 vars
        m = gp.Model(env=env)
        m.Params.OutputFlag = 0
        m.addVars(2100)
        m.update()
        try:
            m.optimize()
            return env, "default"          # unlimited (academic / full)
        except gp.GurobiError:
            pass                            # size-limited; try WLS below
    except gp.GurobiError:
        pass

    # 2) explicit WLS from creds
    creds = creds or {}
    aid, sec, lid = (creds.get("GRB_WLSACCESSID"),
                     creds.get("GRB_WLSSECRET"), creds.get("GRB_LICENSEID"))
    if aid and sec and lid:
        try:
            params = {"WLSACCESSID": aid, "WLSSECRET": sec, "LICENSEID": int(lid)}
            if not verbose:
                params["OutputFlag"] = 0
            return gp.Env(params=params), "wls"
        except gp.GurobiError:
            pass

    return _quiet(gp.Env()), "size-limited"   # last resort: free license


# ---------------------------------------------------------------------------
# Per-arc economics (pure, unit-testable — no solver)
# ---------------------------------------------------------------------------
def arc_economics(
    *,
    t_m,
    t_n,
    t_mat,
    y_m,
    mid_m,
    mid_n,
    tau_m,
    tau_n,
    theta_i,
    lam,
    r_fabn,
    window_end,
    sold,
):
    """Per-dollar economics of one trade arc (buy at ``t_m``, close at ``t_n``).

    Mirrors the backtest's accrual: income at the **locked** purchase yield
    ``y_m``, capital charged at ``lam*theta`` over the holding span, bid-ask/2 on
    each traded leg, and the realized rate-driven gain recognized through an IMR
    (straight-line over the sold bond's remaining life) — only the part releasing
    before ``window_end`` counts in the headline (windowed) figure.

    Parameters
    ----------
    t_m, t_n, t_mat : float
        Buy time, close time, and the bond's maturity (years from the start).
    y_m, mid_m, mid_n : float
        Locked book yield and mid price (per 100) at buy; mid price (per 100) at
        close. ``mid_n`` is ignored when ``sold`` is False.
    tau_m, tau_n : float
        Bid-ask half-spread (decimal) at the buy and close dates.
    theta_i, lam, r_fabn : float
        C-1 factor, capital-cost coefficient (``cost_of_capital*RBC_bar``), funding rate.
    window_end : float
        End of the measurement horizon (years from the start).
    sold : bool
        True  -> sold in the secondary market at ``t_n`` (pays sell-leg cost, books
                 a rate-driven IMR gain/loss).
        False -> closed by par redemption at maturity or by the window cutoff
                 (no sell cost, no gain — amortized cost lands on par).

    Returns
    -------
    dict
        ``carry`` (gross income spread), ``capital`` (capital cost),
        ``net_carry`` = carry - capital, ``cost`` (both legs), ``imr_window`` and
        ``imr_full`` (windowed vs ultimate gain recognition), and ``coef`` =
        net_carry + imr_window - cost (the LP objective coefficient).
    """
    dt = max(float(t_n) - float(t_m), 0.0)
    carry = (float(y_m) - float(r_fabn)) * dt
    capital = float(lam) * float(theta_i) * dt
    net_carry = carry - capital

    cost = float(tau_m)
    imr_window = 0.0
    imr_full = 0.0
    if sold:
        cost += float(tau_n)
        # Amortized-cost basis at the sale date (premium/discount glided toward
        # par over the holding span); the gap vs market mid is the rate-driven gain.
        cb = float(ff.amortize_price_to_par(float(mid_m), dt, max(float(t_mat) - float(t_m), 1e-9)))
        g = ff.realized_gain_on_sale(1.0, float(mid_n), cb)  # per $1 of book value
        rem_after = max(float(t_mat) - float(t_n), 1e-9)     # IMR amortization horizon
        frac_window = float(np.clip((float(window_end) - float(t_n)) / rem_after, 0.0, 1.0))
        imr_window = g * frac_window
        imr_full = g

    return {
        "carry": carry,
        "capital": capital,
        "net_carry": net_carry,
        "cost": cost,
        "imr_window": imr_window,
        "imr_full": imr_full,
        "coef": net_carry + imr_window - cost,
    }


# ---------------------------------------------------------------------------
# Arc enumeration over the rebalance grid
# ---------------------------------------------------------------------------
def build_arcs(
    *,
    grid,
    t_grid,
    t_mat,
    Y,
    MID,
    TAU,
    THETA,
    ELIG,
    lam,
    r_fabn,
    window_end,
    fabn_mat_yr,
    allow_post_fabn=True,
    buy_nodes=None,
    max_hold_nodes=None,
):
    """Enumerate every (bond, buy node, close node) arc with its profit coefficient.

    ``grid`` are daily indices (sorted, ``grid[0]==0``) used as rebalance points;
    ``t_grid`` the matching times in years. Per bond ``i`` and eligible buy node
    ``p``, an arc closes either by an intermediate **sell** at a later node ``q``
    (``t_grid[q] < min(t_mat, window_end)``) or by a single **terminal** close at
    ``min(t_mat[i], window_end)`` (par redemption if it matures in-window, else the
    window cutoff). ``buy_nodes`` optionally restricts where buys may originate
    (e.g. ``{0}`` reproduces a foresight *static* book — the upper-bound floor).

    Returns a dict of parallel numpy arrays: ``i, p_buy, p_close, sold`` and the
    economics ``carry, capital, cost, imr_window, imr_full, coef``. ``p_close`` is
    the grid-node index the arc's life is snapped to for holding/duration coverage
    (the node at or before the close time).
    """
    grid = np.asarray(grid)
    t_grid = np.asarray(t_grid, dtype=float)
    P = len(grid)
    N = Y.shape[1]
    if buy_nodes is not None:
        buy_nodes = set(int(b) for b in buy_nodes)

    cols = {k: [] for k in
            ("i", "p_buy", "p_close", "sold",
             "carry", "capital", "cost", "imr_window", "imr_full", "coef")}

    def _emit(i, p_buy, p_close, sold, econ):
        cols["i"].append(i)
        cols["p_buy"].append(p_buy)
        cols["p_close"].append(p_close)
        cols["sold"].append(sold)
        for k in ("carry", "capital", "cost", "imr_window", "imr_full", "coef"):
            cols[k].append(econ[k])

    for i in range(N):
        mat = float(t_mat[i])
        if (not allow_post_fabn) and mat > fabn_mat_yr:
            continue
        t_close_terminal = min(mat, float(window_end))
        for p in range(P):
            if buy_nodes is not None and p not in buy_nodes:
                continue
            d_m = grid[p]
            if not ELIG[d_m, i] or t_grid[p] >= t_close_terminal:
                continue
            y_m = float(Y[d_m, i])
            mid_m = float(MID[d_m, i])
            tau_m = float(TAU[d_m, i])

            # (a) intermediate sells at later eligible grid nodes (before close).
            # ``max_hold_nodes`` caps how many grid steps after the buy a sell may
            # occur (a bond is flipped within that window OR held to the terminal
            # close); this turns arc growth from O(N*P^2) into O(N*P*max_hold),
            # making fine grids (e.g. daily) tractable on the full universe.
            q_hi = P if max_hold_nodes is None else min(P, p + 1 + int(max_hold_nodes))
            for q in range(p + 1, q_hi):
                d_n = grid[q]
                if t_grid[q] >= t_close_terminal:
                    break
                if not ELIG[d_n, i]:
                    continue
                econ = arc_economics(
                    t_m=t_grid[p], t_n=t_grid[q], t_mat=mat, y_m=y_m,
                    mid_m=mid_m, mid_n=float(MID[d_n, i]), tau_m=tau_m,
                    tau_n=float(TAU[d_n, i]), theta_i=float(THETA[i]),
                    lam=lam, r_fabn=r_fabn, window_end=window_end, sold=True,
                )
                _emit(i, p, q, True, econ)

            # (b/c) one terminal close: par redemption (in-window) or window cutoff
            econ = arc_economics(
                t_m=t_grid[p], t_n=t_close_terminal, t_mat=mat, y_m=y_m,
                mid_m=mid_m, mid_n=mid_m, tau_m=tau_m, tau_n=0.0,
                theta_i=float(THETA[i]), lam=lam, r_fabn=r_fabn,
                window_end=window_end, sold=False,
            )
            # snap terminal close to the last grid node at or before the close time
            p_close = int(np.searchsorted(t_grid, t_close_terminal, side="right") - 1)
            p_close = max(p_close, p + 1) if p + 1 < P else P  # cover at least one interval
            _emit(i, p, min(p_close, P), False, econ)

    arcs = {k: np.asarray(v) for k, v in cols.items()}
    arcs["i"] = arcs["i"].astype(int)
    arcs["p_buy"] = arcs["p_buy"].astype(int)
    arcs["p_close"] = arcs["p_close"].astype(int)
    arcs["sold"] = arcs["sold"].astype(bool)
    arcs["n_arcs"] = len(arcs["i"])
    return arcs


# ---------------------------------------------------------------------------
# The LP (lazy gurobi import so the module imports without a license)
# ---------------------------------------------------------------------------
def solve_prize(
    arcs,
    *,
    H,
    P,
    N,
    DUR_grid=None,
    d_fabn_grid=None,
    issuer_groups=None,
    eps_D=0.30,
    dur_pen=1.0,
    delta_iss=0.05,
    enforce_duration=True,
    enforce_issuer=True,
    facility=None,
    env=None,
    time_limit=None,
    verbose=False,
):
    """Solve the perfect-foresight arc LP. Returns a result dict.

    ``arcs`` is the output of :func:`build_arcs`. Holdings during grid interval
    ``p`` are ``Hold[p,i] = sum of x_a over arcs of i covering p`` (``p_buy <= p <
    p_close``). Constraints: book-value conservation across nodes (a dollar freed
    when an arc closes can only then fund a new buy), a **soft** duration band per
    interval (``DUR_grid``, ``d_fabn_grid``; breach penalized at ``dur_pen`` so the
    LP is always feasible), and an issuer concentration cap per interval. Capital
    is priced into ``arcs['coef']`` (objective), matching the backtest.

    ``facility`` (optional dict) adds the quarterly lending-facility recursion and
    the PV-shortfall cap — the liquidity guardrail that forces enough in-time
    maturities to fund the final FABN payment (and forbids piling into long bonds).
    Expected keys: ``QB_q`` (Q, N) quarterly bond CF per $1 face, ``FB_q`` (Q,)
    quarterly FABN liability $, ``q_interval`` (Q,) grid interval whose holdings
    drive each quarter, ``df`` (Q,) discount factors, ``PV_L`` float, ``r_save``,
    ``r_borrow``, ``phi_sf``, ``dt_q`` (default 0.25). Surplus interest is credited
    structurally in the recursion; the objective carries only the borrowing cost,
    and the PV-shortfall is hard-capped.

    Returns ``status``, ``prize_window`` / ``prize_full`` ($ cumulative net
    statutory income, windowed vs ultimate IMR recognition), the arc solution
    ``x``, a ``decomp`` of carry / capital / cost / imr, and per-interval holdings.
    """
    import gurobipy as gp
    from gurobipy import GRB

    na = arcs["n_arcs"]
    m = gp.Model("size_of_prize", env=env) if env is not None else gp.Model("size_of_prize")
    if not verbose:
        m.Params.OutputFlag = 0
    m.Params.DualReductions = 0  # report INFEASIBLE vs UNBOUNDED unambiguously
    if time_limit is not None:
        m.Params.TimeLimit = float(time_limit)

    x = m.addVars(na, lb=0.0, name="x")

    # --- book-value conservation (time-expanded flow) ---------------------
    # cash_0 = H; buys at a node may not exceed cash on hand; closing an arc frees
    # its book value at its close node for redeployment.
    buys_at = [gp.LinExpr() for _ in range(P)]
    frees_at = [gp.LinExpr() for _ in range(P + 1)]
    for a in range(na):
        buys_at[arcs["p_buy"][a]] += x[a]
        cl = int(arcs["p_close"][a])
        if cl <= P:
            frees_at[min(cl, P)] += x[a]
    cash = [None] * (P + 1)
    cash[0] = float(H)
    # node 0: deploy at most H
    m.addConstr(buys_at[0] <= cash[0], name="cash_0")
    running = cash[0] - buys_at[0]
    for p in range(1, P):
        running = running + frees_at[p]
        m.addConstr(buys_at[p] <= running, name=f"cash_{p}")
        running = running - buys_at[p]

    # --- per-interval holdings --------------------------------------------
    # Hold[p,i] = sum of x_a over arcs of bond i alive across interval p.
    cover = [[] for _ in range(P)]  # cover[p] -> list of arc indices
    for a in range(na):
        for p in range(int(arcs["p_buy"][a]), min(int(arcs["p_close"][a]), P)):
            cover[p].append(a)

    def hold_expr(p, idx_mask=None):
        e = gp.LinExpr()
        for a in cover[p]:
            if idx_mask is None or idx_mask[arcs["i"][a]]:
                e += x[a]
        return e

    # --- soft duration band per interval ----------------------------------
    breach_terms = gp.LinExpr()
    if enforce_duration and DUR_grid is not None and d_fabn_grid is not None:
        for p in range(P):
            dur_dollars = gp.LinExpr()
            for a in cover[p]:
                dur_dollars += DUR_grid[p, arcs["i"][a]] * x[a]
            dp = m.addVar(lb=0.0)
            dn = m.addVar(lb=0.0)
            ep = m.addVar(lb=0.0)
            en = m.addVar(lb=0.0)
            m.addConstr(dur_dollars - d_fabn_grid[p] * H == dp - dn)
            m.addConstr(dp <= eps_D * H + ep)
            m.addConstr(dn <= eps_D * H + en)
            breach_terms += ep + en

    # --- issuer concentration cap per interval ----------------------------
    if enforce_issuer and issuer_groups:
        for p in range(P):
            present = {}
            for a in cover[p]:
                present.setdefault(arcs["i"][a], []).append(a)
            for grp, members in issuer_groups.items():
                e = gp.LinExpr()
                hit = False
                for i in members:
                    if i in present:
                        hit = True
                        for a in present[i]:
                            e += x[a]
                if hit:
                    m.addConstr(e <= delta_iss * H)

    # --- quarterly lending facility + PV-shortfall cap (liquidity guardrail) --
    facility_adj = gp.LinExpr()
    if facility is not None:
        QB_q = np.asarray(facility["QB_q"], dtype=float)
        FB_q = np.asarray(facility["FB_q"], dtype=float)
        q_interval = np.asarray(facility["q_interval"], dtype=int)
        df = np.asarray(facility["df"], dtype=float)
        Qn = len(FB_q)
        dt_q = float(facility.get("dt_q", 0.25))
        r_save = float(facility.get("r_save", 0.0))
        r_borrow = float(facility.get("r_borrow", 0.0))
        Bv = m.addVars(Qn, lb=0.0)   # surplus carried in the facility
        SNv = m.addVars(Qn, lb=0.0)  # residual shortfall (borrowing)
        for q in range(Qn):
            p = int(q_interval[q])
            cfa = gp.LinExpr()
            for a in cover[p]:
                cfa += QB_q[q, arcs["i"][a]] * x[a]
            cfl = float(FB_q[q])
            if q == 0:
                m.addConstr(Bv[q] - SNv[q] == cfa - cfl)
            else:
                m.addConstr(Bv[q] - SNv[q] == (1.0 + r_save * dt_q) * Bv[q - 1] + cfa - cfl)
        m.addConstr(gp.quicksum(df[q] * SNv[q] for q in range(Qn)) <= facility["phi_sf"] * facility["PV_L"])
        # Lending interest on surplus is credited *structurally* by the recursion's
        # (1 + r_save*dt)*B_{q-1} term (it lowers future shortfall). We do NOT also
        # reward B in the objective: that would double-count and — because surplus
        # can be inflated against the recursion — make the LP unbounded. Only the
        # borrowing cost enters the objective; the shortfall is hard-capped.
        facility_adj = -(r_borrow * dt_q) * gp.quicksum(SNv[q] for q in range(Qn))

    # --- objective: maximize windowed cumulative net statutory income -----
    obj = gp.quicksum(float(arcs["coef"][a]) * x[a] for a in range(na))
    m.setObjective(obj + facility_adj - dur_pen * breach_terms, GRB.MAXIMIZE)
    m.optimize()

    if m.Status != GRB.OPTIMAL and m.Status != GRB.SUBOPTIMAL:
        return {"status": f"GRB_{m.Status}", "prize_window": None}

    xv = np.array([x[a].X for a in range(na)])
    facility_net = float(facility_adj.getValue()) if facility is not None else 0.0
    decomp = {
        "carry": float(np.sum(arcs["carry"] * xv)),
        "capital": float(np.sum(arcs["capital"] * xv)),
        "cost": float(np.sum(arcs["cost"] * xv)),
        "imr_window": float(np.sum(arcs["imr_window"] * xv)),
        "imr_full": float(np.sum(arcs["imr_full"] * xv)),
        "facility": facility_net,
    }
    base = decomp["carry"] - decomp["capital"] - decomp["cost"] + facility_net
    prize_window = base + decomp["imr_window"]
    prize_full = base + decomp["imr_full"]
    holdings = np.zeros((P, N))
    for p in range(P):
        for a in cover[p]:
            holdings[p, arcs["i"][a]] += xv[a]

    return {
        "status": "OPTIMAL",
        "prize_window": prize_window,
        "prize_full": prize_full,
        "decomp": decomp,
        "x": xv,
        "holdings": holdings,
        "traded_notional": float(np.sum(xv[arcs["sold"]])) if na else 0.0,
        "objective": float(m.ObjVal),
    }
