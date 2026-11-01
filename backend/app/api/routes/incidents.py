from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.core.dependencies import get_db
from app.state import get_simulation_engine
from app.auth import require_operator

router = APIRouter(prefix="/incidents", tags=["incidents"])


class IncidentCreateRequest(BaseModel):
    incident_type: str = "accident"
    road_id: Optional[str] = None
    severity: Optional[float] = 0.8
    duration_ticks: Optional[int] = 60
    description: Optional[str] = None


@router.get("/active")
async def get_active_incidents(db: AsyncSession = Depends(get_db)):
    engine = get_simulation_engine()
    incidents = []
    for inc in engine.incident_simulator.active_incidents.values():
        incident_type = inc.incident_type.value if hasattr(inc.incident_type, 'value') else str(inc.incident_type)
        incidents.append({
            "incident_id": inc.incident_id,
            "incident_type": incident_type,
            "road_id": inc.road_id,
            "severity": inc.severity,
            "start_tick": inc.start_tick,
            "end_tick": inc.end_tick,
            "capacity_reduction_pct": inc.capacity_reduction_pct,
            "description": inc.description
        })
    return {"incidents": incidents, "count": len(incidents)}


@router.post("")
@router.post("/")
async def create_incident(
    req: Optional[IncidentCreateRequest] = None,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_operator)
):
    engine = get_simulation_engine()
    road_id = req.road_id if req and req.road_id else None
    if not road_id or road_id not in engine.roads:
        roads = list(engine.roads.keys())
        if roads:
            road_id = roads[0]
        else:
            raise HTTPException(status_code=400, detail="No roads available")

    incident_type = req.incident_type if req and req.incident_type else "accident"
    incident = engine.incident_simulator.spawn_incident(
        incident_type=incident_type,
        current_tick=engine.state.current_tick,
        road_id=road_id
    )
    if incident and road_id in engine.roads:
        road = engine.roads[road_id]
        road.incident_penalty = incident.capacity_reduction_pct / 100.0
        engine.congestion_engine.calculate_all(engine.roads)

    return {
        "message": "Incident created",
        "incident_id": incident.incident_id if incident else None,
        "road_id": road_id,
        "incident_type": incident_type,
    }


@router.patch("/{incident_id}")
async def update_incident(incident_id: str, db: AsyncSession = Depends(get_db), _: Any = Depends(require_operator)):
    return {"message": "Updated", "incident_id": incident_id}


@router.delete("/{incident_id}")
async def resolve_incident(incident_id: str, db: AsyncSession = Depends(get_db), _: Any = Depends(require_operator)):
    engine = get_simulation_engine()
    success = engine.incident_simulator.resolve_incident(incident_id, engine.roads)
    if success:
        engine.congestion_engine.calculate_all(engine.roads)
    return {"success": success, "incident_id": incident_id}