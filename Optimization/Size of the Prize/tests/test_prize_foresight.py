"""Unit + identity tests for prize_foresight (the "size of the prize" arc model).

Mirrors the style of ../../tests/test_fabn_finance.py: helpers on top, grouped by
topic, identity / upper-bound / feasibility checks. The pure per-arc economics run
without a solver; the LP tests skip gracefully if gurobipy has no usable license.

Run from the Optimization folder:  pytest "Size of the Prize/tests/" -v
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import prize_foresight as pf  # noqa: E402
import fabn_finance as ff      # noqa: E402

R_FABN = 0.03205


def _gurobi_or_skip():
    """Return a tiny solver callable, or skip the test if Gurobi is unavailable."""
    gp = pytest.importorskip("gurobipy")
    try:
        mdl = gp.Model()
        mdl.Params.OutputFlag = 0
        mdl.addVar()
        mdl.optimize()
    except gp.GurobiError as exc:  # no license / size-limited refusal
        pytest.skip(f"Gurobi unavailable: {exc}")


# ---------------------------------------------------------------------------
# Per-arc economics — single-arc identity vs the backtest's accrual
# ---------------------------------------------------------------------------
def test_single_arc_reconstructs_backtest_net():
    # A trade: buy $D at par, hold 1y of a 5y bond, sell at mid 104. The arc's
    # per-dollar coef * D must equal nii - capital - cost + windowed IMR release.
    D = 10_000_000.0
    y, theta, lam = 0.050, 0.005, 0.15 * 1.5
    tau_m, tau_n = 0.0010, 0.0012
    econ = pf.arc_economics(
        t_m=0.0, t_n=1.0, t_mat=5.0, y_m=y, mid_m=100.0, mid_n=104.0,
        tau_m=tau_m, tau_n=tau_n, theta_i=theta, lam=lam, r_fabn=R_FABN,
        window_end=3.0, sold=True,
    )
    # Independent reconstruction (run_daily algebra, per dollar):
    nii = (y - R_FABN) * 1.0
    cap = lam * theta * 1.0
    cost = tau_m + tau_n
    g = ff.realized_gain_on_sale(1.0, 104.0, 100.0)        # 0.04 per $
    imr_win = g * ((3.0 - 1.0) / (5.0 - 1.0))               # straight-line, in window
    assert econ["coef"] == pytest.approx(nii - cap - cost + imr_win, abs=1e-12)
    assert econ["coef"] * D == pytest.approx(
        (nii - cap) * D - cost * D + imr_win * D, abs=1e-6)


def test_imr_window_matches_ledger_and_conserves():
    # The windowed IMR recognized by the arc must equal what an IMRLedger releases
    # over the same window, and window + post-window must sum to the full gain.
    econ = pf.arc_economics(
        t_m=0.0, t_n=1.0, t_mat=5.0, y_m=0.05, mid_m=100.0, mid_n=106.0,
        tau_m=0.0, tau_n=0.0, theta_i=0.0, lam=0.0, r_fabn=R_FABN,
        window_end=3.0, sold=True,
    )
    g = ff.realized_gain_on_sale(1.0, 106.0, 100.0)
    assert econ["imr_full"] == pytest.approx(g)
    # Ledger: amortize g over remaining life (4y), release the first 2y (window).
    led = ff.IMRLedger()
    led.add_realized(g, remaining_years=5.0 - 1.0)
    assert econ["imr_window"] == pytest.approx(led.accrue(3.0 - 1.0))
    post = econ["imr_full"] - econ["imr_window"]
    assert econ["imr_window"] + post == pytest.approx(g)
    assert econ["imr_window"] < econ["imr_full"]            # only part releases in window


def test_hold_to_maturity_arc_has_no_sell_cost_or_gain():
    # Closed by par redemption (sold=False): only the buy-leg cost, zero IMR,
    # carry = locked spread over the holding span.
    econ = pf.arc_economics(
        t_m=0.0, t_n=5.0, t_mat=5.0, y_m=0.06, mid_m=104.0, mid_n=104.0,
        tau_m=0.0015, tau_n=0.0015, theta_i=0.004, lam=0.225, r_fabn=R_FABN,
        window_end=10.0, sold=False,
    )
    assert econ["cost"] == pytest.approx(0.0015)           # buy leg only
    assert econ["imr_window"] == 0.0 and econ["imr_full"] == 0.0
    assert econ["carry"] == pytest.approx((0.06 - R_FABN) * 5.0)
    assert econ["net_carry"] == pytest.approx((0.06 - R_FABN) * 5.0 - 0.225 * 0.004 * 5.0)


# ---------------------------------------------------------------------------
# A 2-bond × 3-date toy panel for the LP tests
# ---------------------------------------------------------------------------
def _toy_panel(y_bond1_node1=0.06):
    """grid = [0,1,2] at t = [0, .5, 1]; window_end = 1.0; both bonds mature at 5y.

    Bond 0 yields a flat 4%. Bond 1 also yields 4% at node 0 but jumps to
    ``y_bond1_node1`` at node 1 — a foresight-only pickup. Flat mids (no IMR), no
    cost/capital, so the LP isolates the carry-timing value of foresight.
    """
    grid = np.array([0, 1, 2])
    t_grid = np.array([0.0, 0.5, 1.0])
    N = 2
    Y = np.array([[0.04, 0.04],
                  [0.04, y_bond1_node1],
                  [0.04, y_bond1_node1]])
    MID = np.full((3, N), 100.0)
    TAU = np.zeros((3, N))
    THETA = np.zeros(N)
    ELIG = np.ones((3, N), dtype=bool)
    t_mat = np.array([5.0, 5.0])
    arcs = pf.build_arcs(
        grid=grid, t_grid=t_grid, t_mat=t_mat, Y=Y, MID=MID, TAU=TAU,
        THETA=THETA, ELIG=ELIG, lam=0.0, r_fabn=R_FABN, window_end=1.0,
        fabn_mat_yr=10.0, allow_post_fabn=True,
    )
    arcs_static = pf.build_arcs(
        grid=grid, t_grid=t_grid, t_mat=t_mat, Y=Y, MID=MID, TAU=TAU,
        THETA=THETA, ELIG=ELIG, lam=0.0, r_fabn=R_FABN, window_end=1.0,
        fabn_mat_yr=10.0, allow_post_fabn=True, buy_nodes={0},
    )
    return arcs, arcs_static, len(t_grid), N


def test_foresight_beats_static_when_a_pickup_exists():
    _gurobi_or_skip()
    H = 500_000_000.0
    arcs, arcs_static, P, N = _toy_panel(y_bond1_node1=0.06)
    dyn = pf.solve_prize(arcs, H=H, P=P, N=N,
                         enforce_duration=False, enforce_issuer=False)
    sta = pf.solve_prize(arcs_static, H=H, P=P, N=N,
                         enforce_duration=False, enforce_issuer=False)
    assert dyn["status"] == "OPTIMAL" and sta["status"] == "OPTIMAL"
    # Foresight ceiling must beat the foresight-static floor.
    assert dyn["prize_window"] > sta["prize_window"] + 1.0
    # Closed form: static locks 4% for 1y; dynamic locks 4% then 6% for half a year each.
    assert sta["prize_window"] == pytest.approx(H * (0.04 - R_FABN) * 1.0, rel=1e-6)
    assert dyn["prize_window"] == pytest.approx(
        H * ((0.04 - R_FABN) + (0.06 - R_FABN)) * 0.5, rel=1e-6)


def test_flat_path_gives_no_foresight_edge():
    _gurobi_or_skip()
    H = 500_000_000.0
    arcs, arcs_static, P, N = _toy_panel(y_bond1_node1=0.04)  # flat — no pickup
    dyn = pf.solve_prize(arcs, H=H, P=P, N=N,
                         enforce_duration=False, enforce_issuer=False)
    sta = pf.solve_prize(arcs_static, H=H, P=P, N=N,
                         enforce_duration=False, enforce_issuer=False)
    assert dyn["prize_window"] == pytest.approx(sta["prize_window"], rel=1e-6)


def test_facility_block_runs_and_caps_shortfall():
    _gurobi_or_skip()
    H = 500_000_000.0
    arcs, _, P, N = _toy_panel(y_bond1_node1=0.06)
    base = pf.solve_prize(arcs, H=H, P=P, N=N,
                          enforce_duration=False, enforce_issuer=False)
    # Costless, slack facility: recursion holds but adds no income/cost -> inert.
    fac = dict(
        QB_q=np.zeros((2, N)), FB_q=np.array([0.0, 0.0]),
        q_interval=np.array([0, 1]), df=np.array([1.0, 1.0]),
        PV_L=1e9, r_save=0.0, r_borrow=0.0, phi_sf=0.01, dt_q=0.25,
    )
    withfac = pf.solve_prize(arcs, H=H, P=P, N=N, enforce_duration=False,
                             enforce_issuer=False, facility=fac)
    assert withfac["status"] == "OPTIMAL"
    assert withfac["prize_window"] == pytest.approx(base["prize_window"], rel=1e-6)
    assert "facility" in withfac["decomp"]


def test_solution_respects_budget_and_nonnegativity():
    _gurobi_or_skip()
    H = 500_000_000.0
    arcs, _, P, N = _toy_panel(y_bond1_node1=0.06)
    res = pf.solve_prize(arcs, H=H, P=P, N=N,
                         enforce_duration=False, enforce_issuer=False)
    assert res["status"] == "OPTIMAL"
    assert (res["x"] >= -1e-6).all()                       # non-negative flows
    # Book value outstanding never exceeds the budget in any interval.
    assert res["holdings"].sum(axis=1).max() <= H + 1.0
    assert (res["holdings"] >= -1e-6).all()
