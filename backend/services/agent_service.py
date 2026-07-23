"""
Agent orchestration service — adapts src/agent/ (colleague's NL orchestration
design) onto our actual working optimizer, since the pipeline modules it was
originally written against (fabn_pipeline.py, fabn_job.py, fabn_sap_solve.py,
agent_cli.py) were never committed to this repo.

Reused as-is from src/agent/: schemas.py (RunRequest/SelectRequest/AgentTurn),
validators.py, prompts.py, qwen_translator.py, contribution_analysis.py — all
of these are self-contained (no missing imports). Only the mapping/dispatch
layer (mapper.py, orchestrator.py, catalog.py) is reimplemented here, against
optimizer_service.run()'s dict output instead of the missing FabnJobResult.

budget_usd on RunRequest has no home in our pipeline — H (facility budget) is
fixed by the FABN data pipeline, not a solver hyperparameter — so it is
accepted (the LLM may still emit it) but ignored, with a note back to the user.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent.contribution_analysis import analyze_contributions, to_agent_context  # noqa: E402
from agent.schemas import AgentTurn, ExplainRequest, RunRequest, SelectRequest  # noqa: E402
from agent.validators import (  # noqa: E402
    ValidationError,
    validate_explain_request,
    validate_run_request,
    validate_select_request,
)

from services import optimizer_service  # noqa: E402

__all__ = [
    "AgentSession",
    "AgentResponse",
    "AgentTurn",
    "ExplainRequest",
    "RunRequest",
    "SelectRequest",
    "ValidationError",
    "get_session",
    "handle_turn",
    "translate_user_message",
]


@dataclass
class AgentResponse:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSession:
    """Holds the last optimizer result for SELECT queries and Qwen chat history."""

    last_result: dict[str, Any] | None = None
    chat_history: list[dict[str, str]] = field(default_factory=list)

    def record_chat(self, user_message: str, assistant_text: str) -> None:
        self.chat_history.append({"role": "user", "content": user_message})
        self.chat_history.append({"role": "assistant", "content": assistant_text})
        # Cap history so the HF context stays small.
        self.chat_history = self.chat_history[-12:]


# Single in-process session (this dashboard is single-user, same pattern as
# optimizer_service's module-level _applied_portfolio state).
_session = AgentSession()


def get_session() -> AgentSession:
    return _session


def set_context(result: dict[str, Any]) -> bool:
    """Adopt an already-computed optimizer result (e.g. from the dashboard's own
    GET /api/optimize call) as the session's last result, so chat SELECT queries
    reflect exactly what's on screen without a redundant re-solve via chat.
    Returns False (no-op) for non-optimal results — those aren't queryable."""
    if result.get("status") != "optimal":
        return False
    _session.last_result = result
    return True


def _run_kwargs_from_request(req: RunRequest) -> dict[str, Any]:
    """Map RunRequest fields onto optimizer_service.run() kwargs (only fields our
    solver actually accepts; budget_usd is not one of them, see module docstring)."""
    kwargs: dict[str, Any] = {"date": str(req.optimization_date)}
    if req.cost_of_capital is not None:
        kwargs["gamma_w"] = req.cost_of_capital
    if req.savings_rate_scalar is not None:
        kwargs["lambda_w"] = req.savings_rate_scalar
    if req.duration_band_years is not None:
        kwargs["eps_D"] = req.duration_band_years
    if req.w_max is not None:
        kwargs["w_max"] = req.w_max
    if req.n_min is not None:
        kwargs["n_min"] = req.n_min
    return kwargs


def _handle_run(req: RunRequest, *, session: AgentSession) -> AgentResponse:
    try:
        validate_run_request(req, today=date_cls.today())
    except ValidationError as exc:
        return AgentResponse(ok=False, message=str(exc))

    kwargs = _run_kwargs_from_request(req)
    ignored_note = (
        " (note: budget_usd isn't configurable in this deployment — the FABN "
        "facility budget is fixed by the data pipeline, not a solver input.)"
        if req.budget_usd is not None else ""
    )

    if not req.confirm:
        preview = {
            "optimization_date": str(req.optimization_date),
            "cost_of_capital": kwargs.get("gamma_w"),
            "savings_rate_scalar": kwargs.get("lambda_w"),
            "duration_band_years": kwargs.get("eps_D"),
            "w_max": kwargs.get("w_max"),
            "n_min": kwargs.get("n_min"),
        }
        return AgentResponse(
            ok=True,
            message="Preview ready. Re-submit the same request with confirm=true to execute." + ignored_note,
            data={"preview": preview, "awaiting_confirm": True},
        )

    result = optimizer_service.run(**kwargs)
    if result.get("status") != "optimal":
        return AgentResponse(
            ok=False,
            message=f"Optimization did not complete: {result.get('error', result.get('status'))}",
            data=result,
        )

    session.last_result = result
    return AgentResponse(
        ok=True,
        message="Optimization finished." + ignored_note,
        data=_summary_metrics(result),
    )


def _summary_metrics(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_id": "summary_metrics",
        "optimization_date": result["date"],
        "status": result["status"],
        "sap_objective_usd": result["nev"],
        "statutory_nii_usd": result["spread_income"],
        "capital_cost_usd": result["capital_cost"],
        "savings_income_usd": result["c3_cost"],
        "turnover_cost_usd": result["txn_cost"],
        "rbc_usd": result["c1_cost"],
        "earnings_per_required_capital": result["rbc_ratio"],
        "duration_avg_years": result["duration"],
        "n_bonds_selected": result["n_bonds_selected"],
    }


def _top_holdings_delta(result: dict[str, Any], *, limit: int) -> dict[str, Any]:
    rows = sorted(result["allocations"], key=lambda a: -abs(a["delta_usd"]))[:limit]
    return {
        "query_id": "top_holdings_delta",
        "rows": [
            {
                "bond": r["cusip"],
                "h_opt_usd": r["h_opt"],
                "h_curr_usd": r["h_curr"],
                "delta_usd": r["delta_usd"],
                "spread_bps": r["spread_bps"],
                "book_yield_pct": round(r["score_bps"] / 100, 4),
            }
            for r in rows
        ],
    }


def _recommended_trades(result: dict[str, Any], *, limit: int) -> dict[str, Any]:
    return {
        "query_id": "recommended_trades",
        "optimization_date": result["date"],
        "rows": result["trades"][:limit],
    }


def _contribution_analysis(result: dict[str, Any]) -> dict[str, Any]:
    records = [
        {
            "CUSIP": a["cusip"],
            "Sector": a["sector"] or "Unclassified",
            "Rating": a["rating"] or "NR",
            "h_opt_usd": a["h_opt"],
            "book_yield_pct": round(a["score_bps"] / 100, 4),
            "spread_bps": a["spread_bps"],
            "duration_yrs": a["duration"],
            "rbc_factor_pct": a["rbc_factor_pct"],
        }
        for a in result["allocations"]
    ]
    out = analyze_contributions(
        records,
        optimization_date=result["date"],
        optimizer_summary_rbc_usd=result["c1_cost"],
    )
    data = to_agent_context(out)
    data["query_id"] = "contribution_analysis"
    return data


def _handle_select(req: SelectRequest, *, session: AgentSession) -> AgentResponse:
    try:
        validate_select_request(req, has_last_job=session.last_result is not None)
    except ValidationError as exc:
        return AgentResponse(ok=False, message=str(exc))

    result = session.last_result
    assert result is not None
    if req.query_id == "summary_metrics":
        data = _summary_metrics(result)
    elif req.query_id == "top_holdings_delta":
        data = _top_holdings_delta(result, limit=req.limit)
    elif req.query_id == "recommended_trades":
        data = _recommended_trades(result, limit=req.limit)
    elif req.query_id == "contribution_analysis":
        data = _contribution_analysis(result)
        if "by_sector" in data:
            try:
                from agent.qwen_translator import generate_narrative
                data["narrative"] = generate_narrative(json.dumps(data))
            except Exception as exc:  # noqa: BLE001 — narrative is a nice-to-have, never block the query
                data["narrative"] = None
                data["narrative_error"] = str(exc)
    else:
        return AgentResponse(ok=False, message=f"unknown query_id: {req.query_id}")

    return AgentResponse(ok=True, message=f"Query {req.query_id} complete.", data=data)


def _handle_explain(req: ExplainRequest, *, session: AgentSession) -> AgentResponse:
    try:
        validate_explain_request(req)
    except ValidationError as exc:
        return AgentResponse(ok=False, message=str(exc))

    live_context = _summary_metrics(session.last_result) if session.last_result is not None else None

    from agent.qwen_translator import answer_explain_question

    try:
        answer = answer_explain_question(req.question, json.dumps(live_context))
    except Exception as exc:  # noqa: BLE001 — surface translator/LLM errors to the chat UI
        return AgentResponse(ok=False, message=f"Couldn't answer that: {exc}")

    return AgentResponse(ok=True, message=answer, data={"query_id": "explain", "question": req.question})


def handle_turn(turn: AgentTurn, *, session: AgentSession) -> AgentResponse:
    if turn.intent == "unsupported":
        return AgentResponse(
            ok=False,
            message="I can only help with running the optimizer, querying the last run's results, or "
                    "explaining how the model works.",
        )
    if turn.intent == "run":
        if turn.run is None:
            return AgentResponse(ok=False, message="intent=run requires a run payload")
        return _handle_run(turn.run, session=session)
    if turn.intent == "select":
        if turn.select is None:
            return AgentResponse(ok=False, message="intent=select requires a select payload")
        return _handle_select(turn.select, session=session)
    if turn.intent == "explain":
        if turn.explain is None:
            return AgentResponse(ok=False, message="intent=explain requires an explain payload")
        return _handle_explain(turn.explain, session=session)
    return AgentResponse(ok=False, message=f"unknown intent: {turn.intent}")


def translate_user_message(user_message: str, *, history: list[dict[str, str]] | None = None) -> AgentTurn:
    """NL -> AgentTurn via Hugging Face Inference API (Qwen2.5), reusing
    src/agent/qwen_translator.py + prompts.py verbatim."""
    from agent.qwen_translator import TranslationError, translate_with_qwen

    try:
        return translate_with_qwen(user_message, history=history)
    except TranslationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(str(exc)) from exc


def hf_token_configured() -> bool:
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"))
