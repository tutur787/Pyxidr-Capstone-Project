"""Fixed SELECT query catalog — no LLM-generated pandas/SQL."""

from __future__ import annotations

from typing import Any

import numpy as np

from agent.contribution_analysis import analyze_contributions, to_agent_context
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
    if req.query_id == "recommended_trades":
        return _recommended_trades(job, limit=req.limit)
    if req.query_id == "contribution_analysis":
        return _contribution_analysis(job)
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


def _recommended_trades(job: Any, *, limit: int) -> dict[str, Any]:
    opt_date = str(job.params.optimization_date.date())
    if not job.is_optimal:
        return {
            "query_id": "recommended_trades",
            "optimization_date": opt_date,
            "rows": [],
            "message": "no optimal holdings; run did not produce trades",
        }
    raw = getattr(job.solve, "raw", None) or {}
    trades: list[dict[str, Any]] = list(raw.get("trades") or [])
    return {
        "query_id": "recommended_trades",
        "optimization_date": opt_date,
        "rows": trades[:limit],
    }


def _contribution_analysis(job: Any) -> dict[str, Any]:
    opt_date = str(job.params.optimization_date.date())
    if not job.is_optimal:
        return {
            "query_id": "contribution_analysis",
            "optimization_date": opt_date,
            "message": "no optimal holdings; contribution analysis requires h_opt",
        }

    p = job.pipeline
    cusips: list[str] = p["CUSIPS"]
    h_opt = job.solve.h_opt
    book_yield = p["book_yield"]   # fraction, multiply by 100 for pct
    theta = p["theta"]             # rbc_factor as fraction; *100 for pct
    spread = p["spread"]
    fixed = p["fixed"]             # DataFrame with CUSIP, sector, rating_sp, mac_dur_bbg

    fixed_indexed = fixed.set_index("CUSIP")

    records = []
    for i, cusip in enumerate(cusips):
        row = fixed_indexed.loc[cusip] if cusip in fixed_indexed.index else {}
        records.append({
            "CUSIP": cusip,
            "Sector": row["sector"] if hasattr(row, "__getitem__") and "sector" in row else "Unknown",
            "Rating": row["rating_sp"] if hasattr(row, "__getitem__") and "rating_sp" in row else "NR",
            "h_opt_usd": float(h_opt[i]),
            "book_yield_pct": float(book_yield[i]) * 100,
            "spread_bps": float(spread[i]) * 10_000,
            "duration_yrs": float(row["mac_dur_bbg"]) if hasattr(row, "__getitem__") and "mac_dur_bbg" in row else 0.0,
            "rbc_factor_pct": float(theta[i]) * 100,
        })

    result = analyze_contributions(
        records,
        optimization_date=opt_date,
        optimizer_summary_rbc_usd=job.solve.RBC_val,
    )
    data = to_agent_context(result)
    data["query_id"] = "contribution_analysis"
    return data
