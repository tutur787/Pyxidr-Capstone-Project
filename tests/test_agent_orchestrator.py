"""Unit tests for the explain intent (no live HF API calls, no Gurobi)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pandas as pd
import pytest

from agent.orchestrator import AgentSession
from agent.schemas import AgentTurn, ExplainRequest
from fabn_pipeline import FabnPipelineParams


@dataclass
class _StubJob:
    params: FabnPipelineParams
    solve: SimpleNamespace
    is_optimal: bool
    output_dir: str
    pipeline: dict


def _stub_job() -> _StubJob:
    solve = SimpleNamespace(
        status=2,
        sap_val=1_000_000.0,
        nii_val=2_000_000.0,
        capital_cost_val=500_000.0,
        savings_val=10_000.0,
        turnover_val=5_000.0,
        liq_val=0.0,
        RBC_val=750_000_000.0,
        earn_per_cap=0.02,
        D_avg=2.9,
    )
    return _StubJob(
        params=FabnPipelineParams(optimization_date=pd.Timestamp("2025-01-15")),
        solve=solve,
        is_optimal=True,
        output_dir="/tmp/out",
        pipeline={},
    )


def test_agent_turn_explain_roundtrip() -> None:
    raw = json.dumps(
        {"intent": "explain", "explain": {"question": "why is duration hedged?"}}
    )
    turn = AgentTurn.model_validate_json(raw)
    assert turn.intent == "explain"
    assert turn.explain is not None
    assert turn.explain.question == "why is duration hedged?"


def test_handle_explain_rejects_empty_question() -> None:
    session = AgentSession(base_params=FabnPipelineParams())
    turn = AgentTurn(intent="explain", explain=ExplainRequest(question="   "))
    resp = session.handle(turn)
    assert not resp.ok
    assert "question" in resp.message


def test_handle_explain_no_last_job(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_answer(question: str, live_context_json: str) -> str:
        captured["question"] = question
        captured["live_context"] = json.loads(live_context_json)
        return "duration is hedged because ..."

    monkeypatch.setattr(
        "agent.qwen_translator.answer_explain_question", fake_answer
    )

    session = AgentSession(base_params=FabnPipelineParams())
    turn = AgentTurn(
        intent="explain", explain=ExplainRequest(question="why is duration hedged?")
    )
    resp = session.handle(turn)

    assert resp.ok
    assert resp.message == "duration is hedged because ..."
    assert captured["question"] == "why is duration hedged?"
    assert captured["live_context"]["last_run_summary"] is None
    assert "note" in captured["live_context"]
    assert resp.data["live_context"]["last_run_summary"] is None


def test_handle_explain_with_last_job(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_answer(question: str, live_context_json: str) -> str:
        captured["live_context"] = json.loads(live_context_json)
        return "your duration gap is small"

    monkeypatch.setattr(
        "agent.qwen_translator.answer_explain_question", fake_answer
    )

    session = AgentSession(base_params=FabnPipelineParams())
    session.last_job = _stub_job()
    turn = AgentTurn(
        intent="explain",
        explain=ExplainRequest(question="how close is the book to D_FABN?"),
    )
    resp = session.handle(turn)

    assert resp.ok
    summary = captured["live_context"]["last_run_summary"]
    assert summary is not None
    assert summary["sap_objective_usd"] == 1_000_000.0
    assert summary["duration_avg_years"] == 2.9


def test_handle_explain_llm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_answer(question: str, live_context_json: str) -> str:
        raise RuntimeError("HF API down")

    monkeypatch.setattr(
        "agent.qwen_translator.answer_explain_question", fake_answer
    )

    session = AgentSession(base_params=FabnPipelineParams())
    turn = AgentTurn(intent="explain", explain=ExplainRequest(question="why?"))
    resp = session.handle(turn)

    assert not resp.ok
    assert "explain failed" in resp.message
