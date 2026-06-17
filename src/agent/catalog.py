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
        "sap_objective_usd": s.sap_val,
        "statutory_nii_usd": s.nii_val,
        "capital_cost_usd": s.capital_cost_val,
        "savings_income_usd": s.savings_val,
        "turnover_cost_usd": s.turnover_val,
        "liquidity_penalty_usd": s.liq_val,
        "rbc_usd": s.RBC_val,
        "earnings_per_required_capital": s.earn_per_cap,
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
    book_yield = p.get("book_yield")
    delta = h_opt - h_curr
    order = np.argsort(-np.abs(delta))[:limit]
    rows = []
    for i in order:
        row = {
            "bond": cusips[i],
            "h_opt_usd": float(h_opt[i]),
            "h_curr_usd": float(h_curr[i]),
            "delta_usd": float(delta[i]),
            "spread_bps": float(spread[i] * 10_000),
        }
        if book_yield is not None:
            row["book_yield_pct"] = round(float(book_yield[i] * 100), 4)
        rows.append(row)
    return {"query_id": "top_holdings_delta", "rows": rows}
