"""Fixed SELECT query catalog — no LLM-generated pandas/SQL."""

from __future__ import annotations

from typing import Any

import numpy as np

from agent.schemas import SelectRequest

# Gurobi status codes (avoid importing gurobipy in lightweight paths)
_GRB_OPTIMAL = 2
_GRB_INFEASIBLE = 3
_GRB_UNBOUNDED = 5


def execute_select(req: SelectRequest, job: Any) -> dict[str, Any]:
    if req.query_id == "summary_metrics":
        return _summary_metrics(job)
    if req.query_id == "top_holdings_delta":
        return _top_holdings_delta(job, limit=req.limit)
    raise ValueError(f"unknown query_id: {req.query_id}")


def _summary_metrics(job: Any) -> dict[str, Any]:
    s = job.solve
    status_name = {
        _GRB_OPTIMAL: "optimal",
        _GRB_INFEASIBLE: "infeasible",
        _GRB_UNBOUNDED: "unbounded",
    }.get(s.status, f"status_{s.status}")
    return {
        "query_id": "summary_metrics",
        "optimization_date": str(job.params.optimization_date.date()),
        "status": status_name,
        "is_optimal": job.is_optimal,
        "nev_usd": s.nev_val,
        "rbc_ratio": s.RBC_val,
        "duration_avg_years": s.D_avg,
        "output_dir": job.output_dir,
    }


def _top_holdings_delta(job: Any, *, limit: int) -> dict[str, Any]:
    if not job.is_optimal:
        return {
            "query_id": "top_holdings_delta",
            "rows": [],
            "message": "no optimal holdings; run did not produce h_opt",
        }
    p = job.pipeline
    h_opt = job.solve.h_opt
    h_curr = p["h_curr"]
    cusips: list[str] = p["CUSIPS"]
    spread = p["spread"]
    delta = h_opt - h_curr
    order = np.argsort(-np.abs(delta))[:limit]
    rows = [
        {
            "bond": cusips[i],
            "h_opt_usd": float(h_opt[i]),
            "h_curr_usd": float(h_curr[i]),
            "delta_usd": float(delta[i]),
            "spread_bps": float(spread[i] * 10_000),
        }
        for i in order
    ]
    return {"query_id": "top_holdings_delta", "rows": rows}
