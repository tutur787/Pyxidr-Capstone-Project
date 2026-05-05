from fastapi import APIRouter
import random, math

router = APIRouter(prefix="/api/rates", tags=["rates"])


def _sine_series(start: float, amplitude: float, n: int, period: int = 60) -> list[float]:
    return [round(start + amplitude * math.sin(2 * math.pi * i / period) + random.gauss(0, 0.02), 3) for i in range(n)]


@router.get("")
def get_rates(date: str = "2024-03-01"):
    n = 90
    dates = []
    from datetime import date as dt, timedelta
    d = dt.fromisoformat(date) - timedelta(days=n)
    for i in range(n):
        dates.append((d + timedelta(days=i)).isoformat())
    rate_2y = _sine_series(5.1, 0.3, n, 40)
    rate_10y = _sine_series(4.3, 0.2, n, 60)
    return [{"date": dates[i], "rate_2y": rate_2y[i], "rate_10y": rate_10y[i]} for i in range(n)]
