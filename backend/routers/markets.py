import logging
from fastapi import APIRouter
from services.alpaca_service import BOND_STUB, fetch_bond_rates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/markets", tags=["markets"])


@router.get("")
def get_markets(date: str = "2025-01-15"):
    rates = fetch_bond_rates(date)
    if rates:
        return rates
    logger.warning("Bond rates unavailable for date=%s — returning stubs", date)
    return BOND_STUB
