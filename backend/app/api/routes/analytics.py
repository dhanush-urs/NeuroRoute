from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def get_analytics_overview(db: AsyncSession = Depends(get_db)):
    return {"message": "Not implemented yet"}


@router.get("/congestion")
async def get_congestion_analytics(db: AsyncSession = Depends(get_db)):
    return {"message": "Not implemented yet"}


@router.get("/routing")
async def get_routing_analytics(db: AsyncSession = Depends(get_db)):
    return {"message": "Not implemented yet"}


@router.get("/predictions")
async def get_prediction_analytics(db: AsyncSession = Depends(get_db)):
    return {"message": "Not implemented yet"}