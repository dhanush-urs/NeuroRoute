from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass

from app.simulation.demand_model import TimeProvider
from app.simulation.congestion import calculate_congestion, classify_congestion


@dataclass
class TrafficSnapshot:
    """Aggregated traffic state for a single road at a tick."""
    road_id: str
    tick: int
    sim_time: datetime
    vehicle_count: int
    avg_speed_kmh: float
    density_veh_km: float
    occupancy_pct: float
    congestion_score: float
    congestion_level: str
    travel_time_sec: int
    weather_condition: str
    incident_count: int = 0


class TrafficStateEngine:
    """Aggregates and manages traffic state across the network."""
    
    def __init__(self):
        self.snapshots: Dict[int, Dict[str, 'TrafficSnapshot']] = {}
        self.current_tick = 0
    
    def update(self, roads: Dict[str, "Road"], tick: int, sim_time: datetime, weather: str) -> None:
        """Update traffic state from current road conditions."""
        self.current_tick = tick
        
        if tick not in self.snapshots:
            self.snapshots[tick] = {}
        
        for road_id, road in roads.items():
            vehicle_count = getattr(road, 'vehicle_count', 0)
            avg_speed = getattr(road, 'avg_speed', road.speed_limit_kmh)
            distance = road.distance_km
            
            # Calculate density
            density = vehicle_count / max(distance, 0.1)
            
            # Calculate occupancy
            occupancy = (vehicle_count / max(road.capacity_vph, 1)) * 100
            
            # Get congestion
            congestion = getattr(road, 'current_congestion', 0.0)
            level = classify_congestion(congestion)
            
            # Travel time
            travel_time = int((distance / max(avg_speed, 1.0)) * 3600)
            
            # Count incidents
            incident_count = 0  # Would be populated from incident simulator
            
            snapshot = TrafficSnapshot(
                road_id=road_id,
                tick=tick,
                sim_time=sim_time,
                vehicle_count=vehicle_count,
                avg_speed_kmh=round(avg_speed, 1),
                density_veh_km=round(density, 2),
                occupancy_pct=round(occupancy, 1),
                congestion_score=round(congestion, 4),
                congestion_level=level,
                travel_time_sec=travel_time,
                weather_condition=weather,
                incident_count=incident_count
            )
            
            self.snapshots[tick][road_id] = snapshot
    
    def get_snapshot(self, tick: int, road_id: str) -> Optional[TrafficSnapshot]:
        """Get snapshot for specific road at tick."""
        return self.snapshots.get(tick, {}).get(road_id)
    
    def get_current_snapshot(self, road_id: str) -> Optional[TrafficSnapshot]:
        """Get latest snapshot for road."""
        return self.get_snapshot(self.current_tick, road_id)
    
    def get_summary(self, tick: int) -> Dict:
        """Get summary statistics for a tick."""
        snapshots = self.snapshots.get(tick, {})
        if not snapshots:
            return {}
        
        total_vehicles = sum(s.vehicle_count for s in snapshots.values())
        avg_speed = sum(s.avg_speed_kmh for s in snapshots.values()) / len(snapshots)
        
        # Congestion distribution
        dist = {"free": 0, "moderate": 0, "heavy": 0, "congested": 0, "severe": 0}
        for s in snapshots.values():
            if s.congestion_level in dist:
                dist[s.congestion_level] += 1
        
        return {
            "total_roads": len(snapshots),
            "total_vehicles": total_vehicles,
            "avg_speed_kmh": round(avg_speed, 1),
            "congestion_distribution": dist,
            "tick": tick,
        }
    
    def get_history(self, road_id: str, max_ticks: int = 100) -> list:
        """Get historical snapshots for a road."""
        history = []
        for tick in sorted(self.snapshots.keys())[-max_ticks:]:
            snap = self.snapshots[tick].get(road_id)
            if snap:
                history.append(snap)
        return history