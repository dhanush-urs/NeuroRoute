from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    road_id: str
    prediction_tick: int
    horizon_minutes: int
    predicted_congestion_score: float
    predicted_vehicle_count: int
    predicted_avg_speed_kmh: float
    confidence: float
    model_version: str
    created_at: datetime


class PredictionBatchRequest(BaseModel):
    road_ids: list[str]
    horizons: list[int] = [5, 15, 30, 60]


class ModelInfoResponse(BaseModel):
    model_name: str
    version: str
    algorithm: str
    metrics: dict
    is_active: bool
    registered_at: datetime