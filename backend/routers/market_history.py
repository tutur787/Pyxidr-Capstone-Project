from fastapi import APIRouter
from services import fabn_market_service

router = APIRouter(prefix="/api", tags=["market-history"])


@router.get("/fabn-market-history")
def get_fabn_market_history():
    return fabn_market_service.get_history()
