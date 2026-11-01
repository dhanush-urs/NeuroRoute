from dataclasses import dataclass, field
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.routing.router import RoutingWeights


@dataclass
class Edge:
    """Graph edge representing a road segment."""
    id: str
    source: str
    target: str
    distance_km: float
    speed_limit_kmh: int
    capacity_vph: int
    road_type: str
    geometry: Optional[Dict[str, Any]] = None
    
    # Dynamic properties (updated each simulation tick)
    current_congestion: float = 0.0
    predicted_congestion_5m: float = 0.0
    predicted_congestion_15m: float = 0.0
    predicted_congestion_30m: float = 0.0
    predicted_congestion_60m: float = 0.0
    incident_penalty: float = 0.0
    weather_penalty: float = 0.0
    
    # For vehicle tracking
    vehicle_count: float = 0.0
    avg_speed: float = 0.0
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, Edge):
            return self.id == other.id
        return False
    
    def travel_time_current(self) -> float:
        """Current travel time in seconds."""
        effective_speed = self.speed_limit_kmh * (1 - self.current_congestion * 0.7)
        effective_speed = max(effective_speed, 1.0)
        return (self.distance_km / effective_speed) * 3600
    
    def travel_time_predicted(self, horizon: int = 15) -> float:
        """Predicted travel time at given horizon in seconds."""
        pred_attr = f'predicted_congestion_{horizon}m'
        pred_congestion = getattr(self, pred_attr, self.current_congestion)
        effective_speed = self.speed_limit_kmh * (1 - pred_congestion * 0.7)
        effective_speed = max(effective_speed, 1.0)
        return (self.distance_km / effective_speed) * 3600
    
    def route_cost(self, weights: "RoutingWeights") -> float:
        """Calculate route cost for this edge."""
        travel_time = self.travel_time_predicted(15)
        return (
            weights.travel_time * travel_time +
            weights.congestion * self.predicted_congestion_15m * 300 +
            weights.incident * self.incident_penalty * 600 +
            weights.risk * self.weather_penalty * 100
        )