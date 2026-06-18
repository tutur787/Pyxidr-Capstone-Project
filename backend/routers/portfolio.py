import logging
from fastapi import APIRouter
from pydantic import BaseModel
from services.bigquery_service import get_portfolio_kpis
from services import optimizer_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/kpis")
def get_kpis(date: str = "2025-01-15"):
    return get_portfolio_kpis(date)


class ApplyTradeRequest(BaseModel):
    cusip: str
    h_opt: float


class TradeItem(BaseModel):
    cusip: str
    h_opt: float


class ApplyTradesRequest(BaseModel):
    trades: list[TradeItem]


@router.post("/apply-trade")
def apply_trade(req: ApplyTradeRequest):
    optimizer_service.apply_trade(req.cusip, req.h_opt)
    return {"status": "ok", "applied_count": optimizer_service.get_applied_count()}


@router.post("/apply-trades")
def apply_trades_batch(req: ApplyTradesRequest):
    optimizer_service.apply_trades([(t.cusip, t.h_opt) for t in req.trades])
    return {"status": "ok", "applied_count": optimizer_service.get_applied_count()}


@router.post("/reset")
def reset_portfolio():
    optimizer_service.reset_portfolio()
    return {"status": "ok"}
