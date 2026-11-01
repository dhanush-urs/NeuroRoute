from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import random


class IncidentType(str, Enum):
    ACCIDENT = "accident"
    ROAD_CLOSURE = "road_closure"
    ROAD_WORK = "road_work"
    FLOOD = "flood"
    HEAVY_RAIN = "heavy_rain"
    SPECIAL_EVENT = "special_event"


@dataclass
class Incident:
    incident_id: str
    incident_type: IncidentType
    road_id: str
    severity: float  # 0.0 - 1.0
    start_tick: int
    end_tick: Optional[int]
    capacity_reduction_pct: float
    affected_radius_km: float
    description: Optional[str] = None
    status: str = "active"  # active, resolved, expired


class IncidentSimulator:
    """Simulates incidents on the road network."""
    
    INCIDENT_CONFIG = {
        IncidentType.ACCIDENT: {
            "base_rate": 0.0002,  # per road per tick
            "severity_range": (0.5, 0.9),
            "capacity_reduction": (50, 80),
            "duration_ticks": (15, 60),
            "description": "Traffic accident"
        },
        IncidentType.ROAD_WORK: {
            "base_rate": 0.00005,
            "severity_range": (0.3, 0.6),
            "capacity_reduction": (20, 60),
            "duration_ticks": (60, 480),
            "description": "Road maintenance"
        },
        IncidentType.ROAD_CLOSURE: {
            "base_rate": 0.00001,
            "severity_range": (1.0, 1.0),
            "capacity_reduction": (100, 100),
            "duration_ticks": (30, 180),
            "description": "Road closed"
        },
        IncidentType.FLOOD: {
            "base_rate": 0.00002,
            "severity_range": (0.7, 1.0),
            "capacity_reduction": (70, 100),
            "duration_ticks": (120, 1440),
            "description": "Flooding"
        },
        IncidentType.HEAVY_RAIN: {
            "base_rate": 0.00001,
            "severity_range": (0.3, 0.5),
            "capacity_reduction": (15, 30),
            "duration_ticks": (30, 240),
            "description": "Heavy rain"
        },
        IncidentType.SPECIAL_EVENT: {
            "base_rate": 0.000005,
            "severity_range": (0.4, 0.7),
            "capacity_reduction": (20, 50),
            "duration_ticks": (60, 300),
            "description": "Special event"
        }
    }
    
    def __init__(self, graph: "RoadGraph", seed: int = 42):
        self.graph = graph
        self.random = random.Random(seed)
        self.active_incidents: Dict[str, Incident] = {}
        self.incident_counter = 0
    
    def update(self, roads: Dict[str, "Road"], current_tick: int) -> None:
        """Update incidents - spawn new ones, expire old ones."""
        # Spawn random incidents
        self._maybe_spawn_incident(current_tick)
        
        # Update active incidents
        expired = []
        for incident_id, incident in self.active_incidents.items():
            # Apply incident effect to road
            road = roads.get(incident.road_id)
            if road:
                road.incident_penalty = incident.capacity_reduction_pct / 100.0
            
            # Check expiration
            if incident.end_tick is not None and current_tick >= incident.end_tick:
                incident.status = "expired"
                expired.append(incident_id)
        
        # Remove expired incidents
        for incident_id in expired:
            incident = self.active_incidents.pop(incident_id)
            # Clear road penalty
            road = roads.get(incident.road_id)
            if road:
                road.incident_penalty = 0.0
    
    def _maybe_spawn_incident(self, current_tick: int) -> None:
        """Randomly spawn an incident based on rates."""
        for incident_type, config in self.INCIDENT_CONFIG.items():
            if self.random.random() < config["base_rate"] * len(self.graph.edges):
                self.spawn_incident(incident_type, current_tick)
    
    def spawn_incident(
        self,
        incident_type: IncidentType,
        current_tick: int,
        road_id: Optional[str] = None
    ) -> Optional[Incident]:
        """Manually spawn an incident on a specific road."""
        config = self.INCIDENT_CONFIG[incident_type]
        
        # Pick road if not specified
        if road_id is None:
            eligible_roads = list(self.graph.edges.keys())
            if not eligible_roads:
                return None
            road_id = self.random.choice(eligible_roads)
        
        # Create incident
        self.incident_counter += 1
        incident_id = f"INC-{self.incident_counter:04d}"
        
        severity = self.random.uniform(*config["severity_range"])
        capacity_reduction = self.random.randint(*config["capacity_reduction"])
        duration = self.random.randint(*config["duration_ticks"])
        end_tick = current_tick + duration
        
        incident = Incident(
            incident_id=incident_id,
            incident_type=incident_type,
            road_id=road_id,
            severity=severity,
            start_tick=current_tick,
            end_tick=end_tick,
            capacity_reduction_pct=capacity_reduction,
            affected_radius_km=0.5,
            description=config["description"]
        )
        
        self.active_incidents[incident_id] = incident
        
        # Apply immediately
        road = self.graph.edges.get(road_id)
        if road:
            road.incident_penalty = capacity_reduction / 100.0
        
        return incident
    
    def resolve_incident(self, incident_id: str, roads: Dict[str, "Road"]) -> bool:
        """Manually resolve an incident."""
        if incident_id not in self.active_incidents:
            return False
        
        incident = self.active_incidents.pop(incident_id)
        incident.status = "resolved"
        
        # Clear road penalty
        road = roads.get(incident.road_id)
        if road:
            road.incident_penalty = 0.0
        
        return True
    
    def clear_all_incidents(self, roads: Dict[str, "Road"]) -> int:
        """Clear all active incidents and reset road penalties."""
        count = len(self.active_incidents)
        for incident in list(self.active_incidents.values()):
            road = roads.get(incident.road_id)
            if road:
                road.incident_penalty = 0.0
                if getattr(road, 'congestion_level', None) == 'closed':
                    road.congestion_level = 'free'
        self.active_incidents.clear()
        return count

    def get_active_incidents(self) -> List[Incident]:
        """Get all active incidents."""
        return list(self.active_incidents.values())
    
    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Get incident by ID."""
        return self.active_incidents.get(incident_id)


class WeatherType(str, Enum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    LIGHT_RAIN = "light_rain"
    HEAVY_RAIN = "heavy_rain"
    FOG = "fog"
    SNOW = "snow"


class WeatherSimulator:
    """Simulates weather conditions affecting traffic."""
    
    SEASONAL_WEATHER = {
        "winter": {  # Dec-Feb
            "weights": [0.30, 0.30, 0.20, 0.15, 0.05, 0.0],
            "temp_range": (-5, 10)
        },
        "spring": {  # Mar-May
            "weights": [0.45, 0.25, 0.18, 0.09, 0.03, 0.0],
            "temp_range": (8, 22)
        },
        "summer": {  # Jun-Aug
            "weights": [0.60, 0.20, 0.10, 0.07, 0.03, 0.0],
            "temp_range": (18, 32)
        },
        "fall": {  # Sep-Nov
            "weights": [0.45, 0.25, 0.18, 0.09, 0.03, 0.0],
            "temp_range": (8, 22)
        }
    }
    
    WEATHER_TYPES = [
        WeatherType.CLEAR,
        WeatherType.CLOUDY,
        WeatherType.LIGHT_RAIN,
        WeatherType.HEAVY_RAIN,
        WeatherType.FOG,
        WeatherType.SNOW
    ]
    
    WEATHER_EFFECTS = {
        WeatherType.CLEAR: {"speed_mod": 1.00, "capacity_mod": 1.00},
        WeatherType.CLOUDY: {"speed_mod": 0.98, "capacity_mod": 1.00},
        WeatherType.LIGHT_RAIN: {"speed_mod": 0.85, "capacity_mod": 0.90},
        WeatherType.HEAVY_RAIN: {"speed_mod": 0.70, "capacity_mod": 0.75},
        WeatherType.FOG: {"speed_mod": 0.75, "capacity_mod": 0.85},
        WeatherType.SNOW: {"speed_mod": 0.60, "capacity_mod": 0.70},
    }
    
    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)
        self.current_weather = WeatherType.CLEAR
        self.current_temperature = 20.0
        self._last_change_tick = 0
        self.locked = False
    
    def update(self, sim_time: datetime) -> None:
        """Update weather based on simulation time."""
        if self.locked:
            return

        # Determine season
        month = sim_time.month
        if month in [12, 1, 2]:
            season = "winter"
        elif month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        else:
            season = "fall"
        
        config = self.SEASONAL_WEATHER[season]
        
        # Change weather occasionally (every ~2-6 hours)
        if self._should_change_weather():
            self.current_weather = self.random.choices(
                self.WEATHER_TYPES, weights=config["weights"]
            )[0]
            self.current_temperature = self.random.uniform(*config["temp_range"])
            self._last_change_tick = 0
    
    def _should_change_weather(self) -> bool:
        # Change weather with ~5% chance per tick
        return self.random.random() < 0.05
    
    def get_speed_modifier(self) -> float:
        """Get speed modifier for current weather."""
        return self.WEATHER_EFFECTS[self.current_weather]["speed_mod"]
    
    def get_capacity_modifier(self) -> float:
        """Get capacity modifier for current weather."""
        return self.WEATHER_EFFECTS[self.current_weather]["capacity_mod"]
    
    def get_weather_info(self) -> Dict:
        return {
            "condition": self.current_weather.value,
            "temperature": round(self.current_temperature, 1),
            "speed_modifier": self.get_speed_modifier(),
            "capacity_modifier": self.get_capacity_modifier()
        }
    
    def set_weather(self, weather: WeatherType, temperature: Optional[float] = None, locked: bool = False) -> None:
        """Manually set weather (for demos)."""
        self.current_weather = weather
        self.locked = locked
        if temperature is not None:
            self.current_temperature = temperature
        elif weather == WeatherType.HEAVY_RAIN:
            self.current_temperature = 14.0

    def clear_weather_override(self) -> None:
        """Clear weather override and restore clear baseline."""
        self.locked = False
        self.current_weather = WeatherType.CLEAR
        self.current_temperature = 20.0