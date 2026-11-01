from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    return {"status": "healthy", "service": "neuroroute"}


@router.get("/ready")
async def readiness_check():
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    return {"status": "alive"}