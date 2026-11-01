from typing import Dict, Set, List, Optional
from collections import defaultdict
from dataclasses import dataclass

from app.graph.graph import RoadGraph
from app.graph.edge import Edge


@dataclass
class CongestionThresholds:
    FREE: float = 0.30
    MODERATE: float = 0.50
    HEAVY: float = 0.70
    CONGESTED: float = 0.90
    SEVERE: float = 1.0


CONGESTION_THRESHOLDS = CongestionThresholds()


def calculate_congestion(
    road,
    vehicles: float,
    avg_speed: float,
    capacity_vph: Optional[int] = None,
    speed_limit_kmh: Optional[int] = None,
    distance_km: Optional[float] = None
) -> float:
    """
    Calculate congestion score 0.0-1.0 for a road.
    
    Combines density ratio (60%) and speed ratio (40%).
    """
    # Use provided values or fall back to road attributes
    cap = capacity_vph or getattr(road, 'capacity_vph', 900)
    speed_limit = speed_limit_kmh or getattr(road, 'speed_limit_kmh', 50)
    dist = distance_km or getattr(road, 'distance_km', 1.0)
    incident_penalty = getattr(road, 'incident_penalty', 0.0)
    weather_penalty = getattr(road, 'weather_penalty', 0.0)
    
    if incident_penalty > 0:
        cap = max(50, int(cap * (1.0 - incident_penalty * 0.75)))
        speed_limit = max(5, int(speed_limit * (1.0 - incident_penalty * 0.6)))
    
    if weather_penalty > 0:
        cap = max(50, int(cap * (1.0 - weather_penalty * 0.5)))
        speed_limit = max(5, int(speed_limit * (1.0 - weather_penalty * 0.4)))
    
    if dist <= 0:
        dist = 1.0
    if speed_limit <= 0:
        speed_limit = 50
    if cap <= 0:
        cap = 900
    
    # Density-based component (veh/km / jam density)
    density = vehicles / dist
    jam_density = cap / (speed_limit / 3.6)  # veh/km at capacity
    density_ratio = density / max(jam_density, 1.0)
    
    # Speed-based component (ratio to free flow)
    speed_ratio = avg_speed / max(speed_limit, 1.0)
    
    # Weighted combination
    congestion = 0.6 * density_ratio + 0.4 * (1.0 - speed_ratio)
    
    return max(0.0, min(1.0, congestion))


def classify_congestion(score: float) -> str:
    """Classify congestion score into level."""
    if score < CONGESTION_THRESHOLDS.FREE:
        return "free"
    elif score < CONGESTION_THRESHOLDS.MODERATE:
        return "moderate"
    elif score < CONGESTION_THRESHOLDS.HEAVY:
        return "heavy"
    elif score < CONGESTION_THRESHOLDS.CONGESTED:
        return "congested"
    elif score <= CONGESTION_THRESHOLDS.SEVERE:
        return "severe"
    else:
        return "severe"


def get_congestion_color(level: str) -> str:
    """Get color for congestion level (for frontend)."""
    colors = {
        "free": "#22c55e",      # green-500
        "moderate": "#eab308",  # yellow-500
        "heavy": "#f97316",     # orange-500
        "congested": "#ef4444", # red-500
        "severe": "#991b1b",    # red-900
        "closed": "#374151",    # gray-700
    }
    return colors.get(level, colors["free"])


class CongestionEngine:
    """Handles congestion calculation and propagation."""
    
    def __init__(self, graph: RoadGraph):
        self.graph = graph
        self.thresholds = CONGESTION_THRESHOLDS
    
    def calculate_all(self, roads: Dict[str, "Road"]) -> None:
        """Calculate congestion for all roads."""
        for road in roads.values():
            incident_penalty = getattr(road, 'incident_penalty', 0.0)
            if incident_penalty >= 0.95:
                road.current_congestion = 1.0
                road.congestion_level = "closed"
                road.avg_speed = 0.0
                continue

            if hasattr(road, 'vehicle_count') and hasattr(road, 'avg_speed'):
                road.current_congestion = calculate_congestion(
                    road, road.vehicle_count, road.avg_speed
                )
                road.congestion_level = classify_congestion(road.current_congestion)
    
    def propagate(self, roads: Dict[str, "Road"], congested_road_ids: Set[str]) -> Dict[str, float]:
        """
        Propagate congestion from PHYSICALLY FULL roads to IMMEDIATE upstream road (queue spillback).
        Returns dict of road_id -> additional vehicle impact.
        
        Only propagates from roads at jam density (congestion > 0.95), not just congested.
        Only affects the single immediate upstream road.
        """
        impacts = defaultdict(float)
        
        for road_id in congested_road_ids:
            road = self.graph.get_road(road_id)
            if not road:
                continue
            
            # Only propagate from PHYSICALLY FULL roads (jam density)
            if road.current_congestion < 0.95:
                continue
            
            # Throughput loss - vehicles that can't exit because road is full
            throughput_loss = road.capacity_vph * 0.1  # 10% of capacity backs up per minute
            
            # Find IMMEDIATE upstream roads (single road feeding directly into this one)
            upstream = self.graph.get_upstream_roads(road_id)
            
            if not upstream:
                continue
            
            # Only affect the single most direct upstream road (first one)
            for up_road in upstream[:1]:  # Only first upstream road
                # Very weak propagation: 5% of throughput loss
                impacts[up_road.id] += throughput_loss * 0.05
        
        return impacts
    
    def apply_propagation(self, roads: Dict[str, "Road"], impacts: Dict[str, float]) -> None:
        """Apply propagation impacts to downstream roads."""
        for road_id, additional_vehicles in impacts.items():
            if road_id in roads:
                road = roads[road_id]
                # Calculate physical max vehicles based on jam density
                jam_density = road.capacity_vph / max(road.speed_limit_kmh / 3.6, 1.0)
                max_vehicles = jam_density * road.distance_km * 1.5
                # Add to existing vehicles (allow temporary oversaturation up to 1.5x jam density)
                road.vehicle_count = min(
                    max_vehicles,
                    road.vehicle_count + additional_vehicles
                )
    
    def get_congested_roads(self, roads: Dict[str, "Road"], threshold: float = 0.5) -> Set[str]:
        """Get set of road IDs with congestion above threshold."""
        return {
            road_id for road_id, road in roads.items()
            if road.current_congestion >= threshold
        }


def calculate_travel_time(
    distance_km: float,
    speed_limit_kmh: int,
    congestion: float,
    incident_penalty: float = 0.0,
    weather_penalty: float = 0.0
) -> float:
    """Calculate travel time in seconds."""
    # Speed drops with congestion (max 70% reduction at 1.0)
    effective_speed = speed_limit_kmh * (1 - congestion * 0.7)
    
    # Apply incident penalty (additional speed reduction)
    if incident_penalty > 0:
        effective_speed *= (1 - incident_penalty * 0.5)
    
    # Apply weather penalty
    if weather_penalty > 0:
        effective_speed *= (1 - weather_penalty * 0.3)
    
    effective_speed = max(effective_speed, 5.0)  # Minimum 5 km/h
    
    return (distance_km / effective_speed) * 3600  # seconds


def calculate_route_cost(
    edge: Edge,
    weights: "RoutingWeights",
    horizon: int = 15
) -> float:
    """Calculate dynamic route cost for an edge."""
    pred_attr = f'predicted_congestion_{horizon}m'
    pred_congestion = getattr(edge, pred_attr, edge.current_congestion)
    
    travel_time = calculate_travel_time(
        edge.distance_km,
        edge.speed_limit_kmh,
        pred_congestion,
        edge.incident_penalty,
        edge.weather_penalty
    )
    
    cost = (
        weights.travel_time * travel_time +
        weights.congestion * pred_congestion * 300 +
        weights.incident * edge.incident_penalty * 600 +
        weights.risk * edge.weather_penalty * 100
    )
    
    return cost