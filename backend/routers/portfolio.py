import logging
from fastapi import APIRouter
from services.bigquery_service import get_portfolio_kpis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/kpis")
def get_kpis(date: str = "2025-01-15"):
    return get_portfolio_kpis(date)
