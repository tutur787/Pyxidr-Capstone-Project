"""Map validated RunRequest → FabnPipelineParams (deterministic)."""

from __future__ import annotations

import pandas as pd

from agent.schemas import RunRequest
from fabn_pipeline import FabnPipelineParams


def run_request_to_params(
    req: RunRequest,
    base: FabnPipelineParams | None = None,
) -> FabnPipelineParams:
    """Overlay RunRequest fields onto pipeline params defaults."""
    p = base or FabnPipelineParams()
    updates: dict = {"optimization_date": pd.Timestamp(req.optimization_date)}
    if req.budget_usd is not None:
        updates["H"] = req.budget_usd
    if req.duration_band_years is not None:
        updates["eps_D"] = req.duration_band_years
    if req.rbc_target is not None:
        updates["RBC_bar"] = req.rbc_target
    if req.cf_penalty_weight is not None:
        updates["lambda_w"] = req.cf_penalty_weight
    if req.capital_cost_weight is not None:
        updates["gamma_w"] = req.capital_cost_weight
    return FabnPipelineParams(
        project_id=p.project_id,
        dataset=p.dataset,
        FABN_ISSUE=p.FABN_ISSUE,
        FABN_MATURITY=p.FABN_MATURITY,
        FABN_COUPON=p.FABN_COUPON,
        C_curr=p.C_curr,
        C_min=p.C_min,
        dt=p.dt,
        beta_w=p.beta_w,
        alpha_w=p.alpha_w,
        **updates,
    )
