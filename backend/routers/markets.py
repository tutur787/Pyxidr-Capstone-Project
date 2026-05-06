import logging
from fastapi import APIRouter
from services.alpaca_service import fetch_market_quotes, MARKET_SYMBOLS, SYMBOL_NAMES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/markets", tags=["markets"])

# Stub prices loosely based on early-2025 levels
_STUB = [
    {"symbol": "SPY",  "name": "S&P 500 ETF",   "price": 478.32, "change":  2.14, "change_pct":  0.45, "direction": "up"},
    {"symbol": "AAPL", "name": "Apple Inc.",     "price": 182.63, "change": -0.87, "change_pct": -0.47, "direction": "down"},
    {"symbol": "MSFT", "name": "Microsoft",      "price": 374.51, "change":  1.92, "change_pct":  0.52, "direction": "up"},
    {"symbol": "NVDA", "name": "NVIDIA",         "price": 621.44, "change":  8.33, "change_pct":  1.36, "direction": "up"},
    {"symbol": "JPM",  "name": "JPMorgan Chase", "price": 196.87, "change": -1.23, "change_pct": -0.62, "direction": "down"},
]


@router.get("")
def get_markets(date: str = "2025-01-15"):
    quotes = fetch_market_quotes(date)
    if quotes:
        return quotes
    logger.warning("Alpaca market quotes unavailable for date=%s — returning stubs", date)
    return [{**s, "date": date} for s in _STUB]
