"""
Deterministic FABN job runner — pipeline build, solve, export.

All logic lives under ``src/`` (self-contained for Docker).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from gurobipy import GRB

from fabn_optimizer_sap import (
    FabnSolveResult,
    export_fabn_results,
    load_pipeline,
    solve_fabn_sap,
)
from fabn_pipeline import FabnPipelineParams

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _default_output_dir() -> str:
    """Docker sets DATA_OUTPUT_DIR=/app/data/output; local runs use ./data/output."""
    return os.environ.get(
        "DATA_OUTPUT_DIR",
        os.path.join(_PROJECT_ROOT, "data", "output"),
    )


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
    output_dir: str | None = None,
    log_to_console: int = 1,
) -> FabnJobResult:
    """Build pipeline, solve SAP LP, and export CSVs when optimal."""
    pipeline = load_pipeline(params)
    solve = solve_fabn_sap(pipeline, params, log_to_console=log_to_console)
    out = output_dir or _default_output_dir()
    export_fabn_results(pipeline, solve, output_dir=out)
    return FabnJobResult(
        params=params,
        pipeline=pipeline,
        solve=solve,
        output_dir=out,
    )
