from fastapi import APIRouter

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/kpis")
def get_kpis(date: str = "2024-03-01"):
    return {
        "value": 250_000_000,
        "total_return": 1.52,
        "yield_pct": 5.83,
        "duration": 4.21,
        "cvar_pct": 2.87,
        "sharpe": 1.34,
        "n_bonds": 104,
        "ytd_return": 3.41,
        "spread_bps": 71,
        "rbc_c1_usage": 0.62,
    }
