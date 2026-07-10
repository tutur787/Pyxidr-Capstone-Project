import logging
import math
from fastapi import APIRouter
from services.alpaca_service import fetch_rates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rates", tags=["rates"])


def _sine_stubs(date: str, n: int = 90) -> list[dict]:
    """Deterministic sine-wave fallback so the chart never goes blank."""
    from datetime import date as dt, timedelta
    d = dt.fromisoformat(date) - timedelta(days=n)
    return [
        {
            "date": (d + timedelta(days=i)).isoformat(),
            "rate_2y":  round(100 + 2 * math.sin(2 * math.pi * i / 40), 3),
            "rate_10y": round(100 + 1.5 * math.sin(2 * math.pi * i / 60), 3),
        }
        for i in range(n)
    ]


@router.get("")
def get_rates(date: str = "2025-01-15"):
    bars = fetch_rates(date)
    if bars:
        return bars
    logger.warning("Alpaca rates unavailable for date=%s — returning stubs", date)
    return _sine_stubs(date)
