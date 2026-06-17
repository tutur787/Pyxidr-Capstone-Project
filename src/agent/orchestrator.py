"""
Agent orchestration — validate structured turns and dispatch to job/query layers.

NL → JSON via agent.qwen_translator (HF Inference API); or structured JSON via agent_cli.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent.catalog import execute_select
from agent.mapper import run_request_to_params
from agent.schemas import AgentTurn, RunRequest, SelectRequest
from agent.validators import ValidationError, validate_run_request, validate_select_request
from fabn_job import FabnJobResult, run_fabn_job
from fabn_pipeline import FabnPipelineParams


@dataclass
class AgentResponse:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSession:
    """Holds last job result for SELECT queries and chat history for Qwen."""

    last_job: FabnJobResult | None = None
    base_params: FabnPipelineParams = field(default_factory=FabnPipelineParams)
    chat_history: list[dict[str, str]] = field(default_factory=list)

    def handle(self, turn: AgentTurn) -> AgentResponse:
        return handle_turn(turn, session=self)

    def record_chat(self, user_message: str, assistant_payload: str) -> None:
        self.chat_history.append({"role": "user", "content": user_message})
        self.chat_history.append({"role": "assistant", "content": assistant_payload})


def handle_turn(turn: AgentTurn, *, session: AgentSession) -> AgentResponse:
    if turn.intent == "unsupported":
        return AgentResponse(
            ok=False,
            message="Request not supported in v1. Use RUN or SELECT via structured JSON.",
        )
    if turn.intent == "run":
        if turn.run is None:
            return AgentResponse(ok=False, message="intent=run requires a run payload")
        return _handle_run(turn.run, session=session)
    if turn.intent == "select":
        if turn.select is None:
            return AgentResponse(ok=False, message="intent=select requires a select payload")
        return _handle_select(turn.select, session=session)
    return AgentResponse(ok=False, message=f"unknown intent: {turn.intent}")


def _handle_run(req: RunRequest, *, session: AgentSession) -> AgentResponse:
    try:
        validate_run_request(req)
    except ValidationError as exc:
        return AgentResponse(ok=False, message=str(exc))

    params = run_request_to_params(req, base=session.base_params)

    if not req.confirm:
        preview = {
            "optimization_date": str(req.optimization_date),
            "budget_usd": params.H,
            "duration_band_years": params.eps_D,
            "rbc_target": params.RBC_bar,
            "cost_of_capital": params.gamma_w,
            "savings_rate_scalar": params.lambda_w,
            "w_max": params.w_max,
            "n_min": params.n_min,
        }
        return AgentResponse(
            ok=True,
            message="Preview ready. Re-submit the same RunRequest with confirm=true to execute.",
            data={"preview": preview, "awaiting_confirm": True},
        )

    try:
        job = run_fabn_job(params, log_to_console=0)
    except Exception as exc:  # noqa: BLE001 — scaffold: surface pipeline errors to user
        return AgentResponse(ok=False, message=f"job failed: {exc}")

    session.last_job = job
    return AgentResponse(
        ok=job.is_optimal,
        message="Optimization finished." if job.is_optimal else "Optimization finished (not optimal).",
        data=execute_select(
            SelectRequest(query_id="summary_metrics"),
            job,
        ),
    )


def _handle_select(req: SelectRequest, *, session: AgentSession) -> AgentResponse:
    try:
        validate_select_request(req, has_last_job=session.last_job is not None)
    except ValidationError as exc:
        return AgentResponse(ok=False, message=str(exc))

    assert session.last_job is not None
    data = execute_select(req, session.last_job)
    return AgentResponse(ok=True, message=f"Query {req.query_id} complete.", data=data)


def parse_turn_json(raw: str) -> AgentTurn:
    return AgentTurn.model_validate_json(raw)


def translate_user_message(
    user_message: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> AgentTurn:
    """NL → AgentTurn via Hugging Face Inference API (Qwen2.5-7B-Instruct)."""
    from agent.qwen_translator import TranslationError, translate_with_qwen

    try:
        return translate_with_qwen(user_message, history=history)
    except TranslationError:
        raise
    except Exception as exc:
        raise TranslationError(str(exc)) from exc


def format_response(resp: AgentResponse) -> str:
    payload = {"ok": resp.ok, "message": resp.message, "data": resp.data}
    return json.dumps(payload, indent=2, default=str)
