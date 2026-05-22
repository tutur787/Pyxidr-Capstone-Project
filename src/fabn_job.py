"""
Deterministic FABN job runner — pipeline build, solve, export.

Used by `optimization.py` and the agent orchestration layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery
from gurobipy import GRB

from fabn_optimizer import FabnSolveResult, export_fabn_results, solve_fabn_nev
from fabn_pipeline import FabnPipelineParams, build_pipeline


@dataclass
class FabnJobResult:
    """Outcome of a full FABN optimization job."""

    params: FabnPipelineParams
    pipeline: dict[str, Any]
    solve: FabnSolveResult
    output_dir: str

    @property
    def is_optimal(self) -> bool:
        return self.solve.status == GRB.OPTIMAL and self.solve.h_opt is not None


def run_fabn_job(
    params: FabnPipelineParams,
    *,
    client: bigquery.Client | None = None,
    output_dir: str | None = None,
    log_to_console: int = 1,
) -> FabnJobResult:
    """Build pipeline, solve LP, and export CSVs when optimal."""
    bq = client or bigquery.Client(project=params.project_id)
    pipeline = build_pipeline(bq, params)
    _, solve = solve_fabn_nev(pipeline, log_to_console=log_to_console)
    out = output_dir or os.environ.get("DATA_OUTPUT_DIR", "/app/data/output")
    export_fabn_results(pipeline, solve, output_dir=out)
    return FabnJobResult(
        params=params,
        pipeline=pipeline,
        solve=solve,
        output_dir=out,
    )
