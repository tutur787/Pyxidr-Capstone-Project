"""Unit tests for agent schemas and mapper (no Gurobi/BigQuery)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from agent.schemas import AgentTurn, RunRequest, SelectRequest
from agent.validators import ValidationError, validate_run_request


def test_run_request_roundtrip_json() -> None:
    raw = json.dumps(
        {
            "optimization_date": "2025-01-15",
            "budget_usd": 400_000_000,
            "confirm": False,
        }
    )
    req = RunRequest.model_validate_json(raw)
    assert req.optimization_date == date(2025, 1, 15)
    assert req.budget_usd == 400_000_000


def test_validate_rejects_future_date() -> None:
    req = RunRequest(optimization_date=date(2099, 1, 1))
    with pytest.raises(ValidationError):
        validate_run_request(req, today=date(2025, 1, 1))


def test_agent_turn_select() -> None:
    turn = AgentTurn(
        intent="select",
        select=SelectRequest(query_id="summary_metrics"),
    )
    assert turn.select is not None
    assert turn.select.query_id == "summary_metrics"
