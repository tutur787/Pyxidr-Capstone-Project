"""Business-rule validation for agent requests (fail closed)."""

from __future__ import annotations

from datetime import date

from agent.schemas import RunRequest, SelectRequest


class ValidationError(Exception):
    """Raised when a request fails schema or business checks."""


def validate_run_request(req: RunRequest, *, today: date | None = None) -> None:
    ref = today or date.today()
    if req.optimization_date > ref:
        raise ValidationError("optimization_date cannot be in the future")
    if req.budget_usd is not None and req.budget_usd <= 0:
        raise ValidationError("budget_usd must be positive")
    if req.duration_band_years is not None and req.duration_band_years <= 0:
        raise ValidationError("duration_band_years must be positive")
    if req.rbc_target is not None and req.rbc_target < 1.0:
        raise ValidationError("rbc_target must be >= 1.0")
    for name, val in (
        ("cf_penalty_weight", req.cf_penalty_weight),
        ("capital_cost_weight", req.capital_cost_weight),
    ):
        if val is not None and val < 0:
            raise ValidationError(f"{name} must be non-negative")


def validate_select_request(req: SelectRequest, *, has_last_job: bool) -> None:
    if not has_last_job:
        raise ValidationError("no completed job in session; run an optimization first")
