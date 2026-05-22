"""
Structured agent contract (v1).

User-facing chat is translated into these models before any solver work runs.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """RUN — configure and execute an optimization job."""

    optimization_date: date
    budget_usd: Optional[float] = Field(default=None, description="Portfolio budget H")
    duration_band_years: Optional[float] = Field(
        default=None, description="Duration band eps_D"
    )
    rbc_target: Optional[float] = Field(default=None, description="RBC_bar target ratio")
    cf_penalty_weight: Optional[float] = Field(default=None, description="lambda_w")
    capital_cost_weight: Optional[float] = Field(default=None, description="gamma_w")
    confirm: bool = False


class SelectRequest(BaseModel):
    """SELECT — read-only query against the last completed job."""

    query_id: Literal["summary_metrics", "top_holdings_delta"]
    limit: int = Field(default=10, ge=1, le=100)


class AgentTurn(BaseModel):
    """Single orchestration turn from user or LLM translator."""

    intent: Literal["run", "select", "unsupported"]
    run: Optional[RunRequest] = None
    select: Optional[SelectRequest] = None
    user_message: str = ""
