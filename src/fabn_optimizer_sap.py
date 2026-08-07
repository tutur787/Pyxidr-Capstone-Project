"""
SAP Gurobi solve, result types, and CSV export.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from google.cloud import bigquery
from gurobipy import GRB

from fabn_pipeline import FabnPipelineParams, build_pipeline
from fabn_sap_solve import solve_sap

logger = logging.getLogger(__name__)

_FABN_ISSUE = pd.Timestamp("2022-09-06")
_FABN_MATURITY = pd.Timestamp("2027-09-06")


@dataclass
class FabnSolveResult:
    """Outcome of a SAP Gurobi solve."""

    status: int
    h_opt: np.ndarray | None
    sap_val: float | None = None
    nii_val: float | None = None
    capital_cost_val: float | None = None
    savings_val: float | None = None
    turnover_val: float | None = None
    liq_val: float | None = None
    RBC_val: float | None = None
    D_avg: float | None = None
    earn_per_cap: float | None = None
    cvar_realized: float | None = None
    swap_notional_total: float | None = None
    raw: dict[str, Any] | None = None

    @property
    def nev_val(self) -> float | None:
        """Backward-compatible alias."""
        return self.sap_val

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> FabnSolveResult:
        gurobi = int(raw.get("gurobi_status", GRB.INFEASIBLE))
        h_opt = raw.get("h_opt")
        if h_opt is not None and not isinstance(h_opt, np.ndarray):
            h_opt = np.asarray(h_opt, dtype=float)
        return cls(
            status=gurobi,
            h_opt=h_opt,
            sap_val=raw.get("sap_val"),
            nii_val=raw.get("nii_val"),
            capital_cost_val=raw.get("capital_cost_val"),
            savings_val=raw.get("savings_val"),
            turnover_val=raw.get("turnover_val"),
            liq_val=raw.get("liq_val"),
            RBC_val=raw.get("RBC_val"),
            D_avg=raw.get("D_avg"),
            earn_per_cap=raw.get("earn_per_cap"),
            cvar_realized=raw.get("cvar_realized"),
            swap_notional_total=raw.get("swap_notional_total"),
            raw=raw,
        )


def _validate_date(ts: pd.Timestamp) -> None:
    if ts <= _FABN_ISSUE:
        raise ValueError(f"optimization_date must be after FABN issue ({_FABN_ISSUE.date()})")
    if ts >= _FABN_MATURITY:
        raise ValueError(
            f"optimization_date must be before FABN maturity ({_FABN_MATURITY.date()})"
        )
    if ts > pd.Timestamp.today():
        raise ValueError("optimization_date cannot be in the future")


def load_pipeline(
    params: FabnPipelineParams,
    *,
    client: bigquery.Client | None = None,
) -> dict[str, Any]:
    """Build the SAP pipeline dict from BigQuery."""
    _validate_date(params.optimization_date)
    bq = client or bigquery.Client(project=params.project_id)
    logger.info("building pipeline date=%s", params.optimization_date.date())
    return build_pipeline(bq, params)


def solve_fabn_sap(
    pipeline: dict[str, Any],
    params: FabnPipelineParams,
    *,
    log_to_console: int = 0,
) -> FabnSolveResult:
    """Solve the SAP LP for the given pipeline."""
    opt_date = str(params.optimization_date.date())
    logger.info("solving SAP date=%s", opt_date)
    raw = solve_sap(
        pipeline,
        cost_of_capital=params.gamma_w,
        lambda_w=params.lambda_w,
        eps_D=params.eps_D,
        w_max=params.w_max,
        n_min=params.n_min,
        phi_cvar=params.phi_cvar,
        log_to_console=log_to_console,
        optimization_date=opt_date,
    )
    return FabnSolveResult.from_raw(raw)


def export_fabn_results(
    pipeline: dict[str, Any],
    solve: FabnSolveResult,
    *,
    output_dir: str,
) -> None:
    """Write per-bond allocations and SAP summary CSVs when optimal."""
    os.makedirs(output_dir, exist_ok=True)
    if solve.status != GRB.OPTIMAL or solve.h_opt is None:
        logger.info("skip export: status=%s (not optimal)", solve.status)
        return

    cusips: list[str] = pipeline["CUSIPS"]
    fixed = pipeline["fixed"].set_index("CUSIP")
    h_opt = solve.h_opt
    book_yield = pipeline["book_yield"]
    spread = pipeline["spread"]
    durs = pipeline["durs"]
    theta = pipeline["theta"]

    rows = []
    for i, cusip in enumerate(cusips):
        if h_opt[i] <= 1.0:
            continue
        sector = ""
        rating = ""
        if cusip in fixed.index:
            sector = str(fixed.loc[cusip, "sector"])
            rating = str(fixed.loc[cusip, "rating_sp"]).strip()
        rows.append({
            "CUSIP": cusip,
            "Sector": sector,
            "Rating": rating,
            "h_opt_usd": round(float(h_opt[i]), 2),
            "book_yield_pct": round(float(book_yield[i] * 100), 4),
            "spread_bps": round(float(spread[i] * 10_000), 2),
            "duration_yrs": round(float(durs[i]), 4),
            "rbc_factor_pct": round(float(theta[i] * 100), 4),
        })

    alloc_path = os.path.join(output_dir, "optimizer_results.csv")
    if rows:
        with open(alloc_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        logger.info("wrote %s (%d bonds)", alloc_path, len(rows))

    summary_path = os.path.join(output_dir, "sap_summary.csv")
    summary_rows = [
        ("SAP objective ($)", solve.sap_val),
        ("Statutory NII ($)", solve.nii_val),
        ("Capital cost ($)", solve.capital_cost_val),
        ("Savings income ($)", solve.savings_val),
        ("Turnover cost ($)", solve.turnover_val),
        ("Liquidity penalty ($)", solve.liq_val),
        ("RBC ($)", solve.RBC_val),
        ("D_avg (yrs)", solve.D_avg),
        ("Earnings / req. capital", solve.earn_per_cap),
        ("CVaR realized tail loss ($)", solve.cvar_realized),
        ("Swap notional total ($)", solve.swap_notional_total),
    ]
    with open(summary_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for metric, value in summary_rows:
            writer.writerow([metric, value])
    logger.info("wrote %s", summary_path)
