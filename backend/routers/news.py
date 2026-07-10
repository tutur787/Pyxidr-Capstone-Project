import logging
from fastapi import APIRouter
from services.alpaca_service import fetch_news, _score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/news", tags=["news"])

_STUB_HEADLINES = [
    ("Fed signals pause in rate hikes amid cooling inflation data",      "Reuters",          "Macro"),
    ("Royal Bank of Canada reports Q1 earnings beat on strong credit",   "Bloomberg",        "RY"),
    ("NAIC updates RBC C1 factor tables for 2024 reporting cycle",       "Insurance Journal","Regulatory"),
    ("IG spreads tighten 8 bps on risk-on sentiment",                    "FT",               "Macro"),
    ("JPMorgan warns of elevated duration risk in long-end bonds",        "WSJ",              "JPM"),
    ("FABN issuance hits record Q1 2024",                                "Bloomberg",        "FABN"),
    ("MetLife increases FABN program by $2B amid strong demand",         "Reuters",          "MET"),
    ("Credit quality of IG corporates stable despite macro headwinds",   "Moody's",          "Macro"),
]

STUB_NEWS = [
    {"date": "", "headline": h, "source": s, "issuer": i, "url": "", **_score(h)}
    for h, s, i in _STUB_HEADLINES
]


@router.get("")
def get_news(date: str = "2025-01-15"):
    articles = fetch_news(date)
    if articles:
        return articles
    logger.warning("Alpaca news unavailable for date=%s — returning stubs", date)
    return [{**item, "date": date} for item in STUB_NEWS]
