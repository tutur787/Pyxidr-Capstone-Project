"""Unit tests for SELECT catalog (no Gurobi/BigQuery)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from agent.catalog import execute_select
from agent.schemas import SelectRequest

_GRB_OPTIMAL = 2


@pytest.fixture
def synthetic_job() -> SimpleNamespace:
    from datetime import date

    params = SimpleNamespace(
        optimization_date=SimpleNamespace(date=lambda: date(2025, 1, 15))
    )
    h_curr = np.array([1.0, 2.0, 3.0])
    h_opt = np.array([1.5, 2.0, 0.5])
    pipeline = {
        "CUSIPS": ["A", "B", "C"],
        "h_curr": h_curr,
        "spread": np.array([0.01, 0.02, 0.03]),
        "book_yield": np.array([0.04, 0.05, 0.06]),
    }
    solve = SimpleNamespace(
        status=_GRB_OPTIMAL,
        sap_val=1_000_000.0,
        nii_val=800_000.0,
        capital_cost_val=200_000.0,
        savings_val=50_000.0,
        turnover_val=10_000.0,
        liq_val=5_000.0,
        h_opt=h_opt,
        RBC_val=1_600_000.0,
        earn_per_cap=0.5,
        D_avg=4.2,
    )
    return SimpleNamespace(
        params=params,
        pipeline=pipeline,
        solve=solve,
        output_dir="/tmp/out",
        is_optimal=True,
    )


def test_summary_metrics(synthetic_job: SimpleNamespace) -> None:
    out = execute_select(
        SelectRequest(query_id="summary_metrics"),
        synthetic_job,
    )
    assert out["status"] == "optimal"
    assert out["sap_objective_usd"] == 1_000_000.0
    assert out["statutory_nii_usd"] == 800_000.0
    assert out["earnings_per_required_capital"] == 0.5
    assert out["duration_avg_years"] == 4.2


def test_top_holdings_delta_orders_by_abs_delta(synthetic_job: SimpleNamespace) -> None:
    out = execute_select(
        SelectRequest(query_id="top_holdings_delta", limit=2),
        synthetic_job,
    )
    rows = out["rows"]
    assert len(rows) == 2
    assert rows[0]["bond"] == "C"
    assert rows[0]["delta_usd"] == pytest.approx(-2.5)
    assert rows[0]["book_yield_pct"] == pytest.approx(6.0)
