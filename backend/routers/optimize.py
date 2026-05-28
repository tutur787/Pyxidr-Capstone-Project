"""
GET /api/optimize — run the FABN Gurobi optimizer for a given date and params.

The solver is CPU-bound (~30s first run, <1s cached).  asyncio.to_thread
keeps the FastAPI event loop responsive while it runs.
"""

import asyncio

from fastapi import APIRouter

from services import optimizer_service

router = APIRouter(prefix="/api/optimize", tags=["optimize"])


@router.get("")
async def run_optimizer(
    date:     str   = "2025-01-15",
    gamma_w:  float = 1.0,
    lambda_w: float = 1.0,
    eps_D:    float = 0.5,
    w_max:    float = 0.05,
    n_min:    int   = 20,
):
    """
    Run the FABN portfolio optimizer and return the full result dict.

    Query params
    ------------
    date      YYYY-MM-DD optimization date (must be in 2022-09-07 … 2027-09-05)
    gamma_w   Capital cost weight (C1 + C3)  — default 1.0
    lambda_w  Lending facility rate scalar (r_lend = r_FABN * lambda_w) — default 1.0
    eps_D     Duration gap tolerance in years — default 0.5
    w_max     Max single-bond weight (fraction) — default 0.05
    n_min     Minimum number of bonds — default 20
    """
    result = await asyncio.to_thread(
        optimizer_service.run,
        date, gamma_w, lambda_w, eps_D, w_max, n_min,
    )
    return result
