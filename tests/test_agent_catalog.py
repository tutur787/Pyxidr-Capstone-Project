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
    }
    solve = SimpleNamespace(
        status=_GRB_OPTIMAL,
        nev_val=1_000_000.0,
        h_opt=h_opt,
        RBC_val=1.6,
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
    assert out["nev_usd"] == 1_000_000.0
    assert out["rbc_ratio"] == 1.6


def test_top_holdings_delta_orders_by_abs_delta(synthetic_job: SimpleNamespace) -> None:
    out = execute_select(
        SelectRequest(query_id="top_holdings_delta", limit=2),
        synthetic_job,
    )
    rows = out["rows"]
    assert len(rows) == 2
    assert rows[0]["bond"] == "C"
    assert rows[0]["delta_usd"] == pytest.approx(-2.5)
