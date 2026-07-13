"""
Structured agent contract (v1).

User-facing chat is translated into these models before any solver work runs.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """RUN — configure and execute a FABN SAP optimization job."""

    optimization_date: date
    budget_usd: Optional[float] = Field(default=None, description="Portfolio budget H")
    duration_band_years: Optional[float] = Field(
        default=None, description="Duration band tolerance eps_D (years)"
    )
    rbc_target: Optional[float] = Field(
        default=None, description="Required-capital multiplier RBC_bar"
    )
    cost_of_capital: Optional[float] = Field(
        default=None,
        description="Insurer WACC (gamma_w); lambda_cap = cost_of_capital × RBC_bar",
    )
    savings_rate_scalar: Optional[float] = Field(
        default=None,
        description="Lending-facility reinvestment scalar (lambda_w); r_save = r_FABN × scalar",
    )
    w_max: Optional[float] = Field(
        default=None, description="Max single-issuer weight fraction"
    )
    n_min: Optional[int] = Field(
        default=None, description="Minimum distinct bonds (via concentration cap)"
    )
    confirm: bool = False


class SelectRequest(BaseModel):
    """SELECT — read-only query against the last completed job."""

    query_id: Literal["summary_metrics", "top_holdings_delta", "recommended_trades", "contribution_analysis"]
    limit: int = Field(default=10, ge=1, le=100)


class ExplainRequest(BaseModel):
    """EXPLAIN — conceptual Q&A grounded in the duration/swaps and optimization reference docs."""

    question: str


class AgentTurn(BaseModel):
    """Single orchestration turn from user or LLM translator."""

    intent: Literal["run", "select", "explain", "unsupported"]
    run: Optional[RunRequest] = None
    select: Optional[SelectRequest] = None
    explain: Optional[ExplainRequest] = None
    user_message: str = ""
