from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class IncidentType(str, Enum):
    ACCIDENT = "accident"
    ROAD_CLOSURE = "road_closure"
    ROAD_WORK = "road_work"
    FLOOD = "flood"
    HEAVY_RAIN = "heavy_rain"
    SPECIAL_EVENT = "special_event"


class IncidentCreate(BaseModel):
    incident_type: IncidentType
    road_id: str
    severity: float = Field(0.5, ge=0.0, le=1.0)
    capacity_reduction_pct: float = Field(0.0, ge=0.0, le=100.0)
    affected_radius_km: float = Field(0.0, ge=0.0)
    description: Optional[str] = None


class IncidentUpdate(BaseModel):
    severity: Optional[float] = Field(None, ge=0.0, le=1.0)
    capacity_reduction_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    affected_radius_km: Optional[float] = Field(None, ge=0.0)
    description: Optional[str] = None
    status: Optional[str] = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    incident_type: str
    road_id: str
    severity: float
    start_tick: int
    end_tick: Optional[int] = None
    capacity_reduction_pct: float
    affected_radius_km: float
    description: Optional[str] = None
    status: str
    created_at: datetime