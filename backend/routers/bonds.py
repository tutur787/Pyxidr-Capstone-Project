import asyncio

from fastapi import APIRouter, HTTPException

from services import bond_service

router = APIRouter(prefix="/api/bonds", tags=["bonds"])


@router.get("")
async def list_bonds(date: str = "2025-01-15"):
    try:
        return await asyncio.to_thread(bond_service.list_bonds, date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{cusip}")
async def get_bond(cusip: str, date: str = "2025-01-15"):
    try:
        detail = await asyncio.to_thread(bond_service.get_bond_detail, date, cusip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"CUSIP {cusip} not found in universe for {date}")
    return detail
