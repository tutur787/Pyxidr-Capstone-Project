from fastapi import APIRouter

router = APIRouter(prefix="/api/news", tags=["news"])

STUB_NEWS = [
    {"headline": "Fed signals pause in rate hikes amid cooling inflation data", "source": "Reuters", "sentiment": "positive", "score": 0.71, "issuer": "Macro"},
    {"headline": "Royal Bank of Canada reports Q1 earnings beat on strong credit performance", "source": "Bloomberg", "sentiment": "positive", "score": 0.84, "issuer": "RBC"},
    {"headline": "NAIC updates RBC C1 factor tables for 2024 reporting cycle", "source": "Insurance Journal", "sentiment": "neutral", "score": 0.02, "issuer": "Regulatory"},
    {"headline": "Investment-grade spreads tighten 8 bps on risk-on sentiment", "source": "FT", "sentiment": "positive", "score": 0.65, "issuer": "Macro"},
    {"headline": "JPMorgan warns of elevated duration risk in long-end bonds", "source": "WSJ", "sentiment": "negative", "score": -0.48, "issuer": "JPM"},
    {"headline": "Funding agreement-backed note issuance hits record in Q1 2024", "source": "Bloomberg", "sentiment": "positive", "score": 0.58, "issuer": "FABN"},
    {"headline": "MetLife increases FABN program by $2B amid strong demand", "source": "Reuters", "sentiment": "positive", "score": 0.73, "issuer": "MET"},
    {"headline": "Credit quality of IG corporates stable despite macro headwinds", "source": "Moody's", "sentiment": "neutral", "score": 0.11, "issuer": "Macro"},
]


@router.get("")
def get_news(date: str = "2024-03-01"):
    return [{"date": date, **item} for item in STUB_NEWS]
