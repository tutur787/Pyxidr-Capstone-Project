import logging
from fastapi import APIRouter
from services.alpaca_service import fetch_bond_rates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/markets", tags=["markets"])

_STUB = [
    {"symbol": "US3M",  "name": "US T-Bill 3M",  "yield_pct": 5.25, "change_bps":  2, "direction": "up"},
    {"symbol": "US1Y",  "name": "US Treasury 1Y", "yield_pct": 5.10, "change_bps": -1, "direction": "down"},
    {"symbol": "US5Y",  "name": "US Treasury 5Y", "yield_pct": 4.35, "change_bps":  3, "direction": "up"},
    {"symbol": "GILTS", "name": "UK Gilts 10Y",   "yield_pct": 4.20, "change_bps": -2, "direction": "down"},
    {"symbol": "CAD5Y", "name": "CAD Govt 5Y",    "yield_pct": 3.75, "change_bps":  1, "direction": "up"},
]


@router.get("")
def get_markets(date: str = "2025-01-15"):
    rates = fetch_bond_rates(date)
    if rates:
        return rates
    logger.warning("Bond rates unavailable for date=%s — returning stubs", date)
    return _STUB
