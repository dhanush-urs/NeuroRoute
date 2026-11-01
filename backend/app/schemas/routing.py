from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class RouteScore(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    route_id: str
    edges: list[str]
    distance_km: float
    current_eta_sec: int
    predicted_eta_sec: int
    congestion_risk: str
    score: float
    rank: int
    is_recommended: bool
    explanation_facts: dict


class RouteRequest(BaseModel):
    origin_node: str = Field(..., description="Origin node ID")
    destination_node: str = Field(..., description="Destination node ID")
    algorithm: Optional[str] = Field("neuro_route", description="Routing algorithm: dijkstra, astar, neuro_route")
    consider_predictions: bool = Field(True, description="Whether to use predicted congestion")


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_node: str
    destination_node: str
    algorithm: str
    route_nodes: list[str]
    route_edges: list[str]
    distance_km: float
    current_eta_sec: int
    predicted_eta_sec: int
    congestion_risk: str
    score: float
    rank: int
    is_recommended: bool
    calculation_tick: int
    created_at: datetime


class RouteComparisonRequest(BaseModel):
    origin_node: str
    destination_node: str
    algorithms: list[str] = Field(default=["dijkstra", "astar", "neuro_route"])


class RouteComparisonResponse(BaseModel):
    routes: list[RouteResponse]
    recommended_route_id: Optional[str] = None


class RouteRecommendationResponse(BaseModel):
    recommended_route: RouteResponse
    alternative_routes: list[RouteResponse]
    explanation: str
    facts: dict