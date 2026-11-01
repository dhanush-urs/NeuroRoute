from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class CongestionLevel(str, Enum):
    FREE = "free"
    MODERATE = "moderate"
    HEAVY = "heavy"
    CONGESTED = "congested"
    SEVERE = "severe"
    CLOSED = "closed"

    @classmethod
    def from_score(cls, score: float) -> "CongestionLevel":
        if score < 0.30:
            return cls.FREE
        elif score < 0.50:
            return cls.MODERATE
        elif score < 0.70:
            return cls.HEAVY
        elif score < 0.90:
            return cls.CONGESTED
        elif score <= 1.0:
            return cls.SEVERE
        else:
            return cls.SEVERE


class RoadTrafficState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    road_id: str
    vehicle_count: int = 0
    avg_speed_kmh: Optional[float] = None
    density_veh_km: Optional[float] = None
    occupancy_pct: Optional[float] = None
    congestion_score: Optional[float] = None
    congestion_level: Optional[CongestionLevel] = None
    travel_time_sec: Optional[int] = None
    weather_condition: Optional[str] = None
    incident_count: int = 0
    timestamp: datetime


class TrafficSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    road_id: str
    tick: int
    sim_time: datetime
    vehicle_count: int
    avg_speed_kmh: Optional[float] = None
    congestion_score: Optional[float] = None
    congestion_level: Optional[CongestionLevel] = None
    travel_time_sec: Optional[int] = None


class TrafficSummaryResponse(BaseModel):
    total_roads: int
    total_vehicles: int
    avg_speed_kmh: Optional[float] = None
    congestion_distribution: dict[CongestionLevel, int]
    active_incidents: int
    timestamp: datetime