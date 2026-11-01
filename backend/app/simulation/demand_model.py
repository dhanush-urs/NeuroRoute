from typing import Dict
from datetime import datetime


class DemandModel:
    """Temporal demand model for realistic traffic patterns."""
    
    # Base demand per road type per hour (vehicles/hour)
    # Key: hour (0-23), Value: vehicles/hour
    # Peak demand set to ~85% of typical capacity to avoid permanent gridlock
    BASE_DEMAND: Dict[str, Dict[int, float]] = {
        'highway': {
            0: 100,  1: 60,  2: 40,  3: 30,  4: 40,  5: 80,
            6: 400,  7: 1000,  8: 1200,  9: 800,  10: 700,  11: 600,
            12: 700,  13: 600,  14: 700,  15: 800,  16: 900,  17: 1200,
            18: 1100,  19: 700,  20: 500,  21: 350,  22: 200,  23: 120
        },
        'major': {
            0: 45,   1: 27,  2: 18,  3: 14,  4: 18,  5: 36,
            6: 180,  7: 680,  8: 750,  9: 420,  10: 340,  11: 300,
            12: 320,  13: 300,  14: 340,  15: 380,  16: 500,  17: 720,
            18: 600,  19: 340,  20: 220,  21: 135,  22: 90,  23: 54
        },
        'minor': {
            0: 18,   1: 9,   2: 5,   3: 5,   4: 7,   5: 14,
            6: 70,   7: 260,  8: 300,  9: 150,  10: 130,  11: 115,
            12: 120,  13: 115,  14: 130,  15: 150,  16: 190,  17: 300,
            18: 260,  19: 140,  20: 90,   21: 55,   22: 30,   23: 18
        },
        'local': {
            0: 5,    1: 2,   2: 1,   3: 1,   4: 2,   5: 3,
            6: 18,   7: 70,   8: 80,   9: 35,   10: 30,   11: 27,
            12: 30,   13: 27,   14: 30,   15: 40,   16: 55,   17: 90,
            18: 70,   19: 35,   20: 22,   21: 14,   22: 9,   23: 5
        },
        'highway_bottleneck': {
            0: 50,   1: 30,  2: 20,  3: 15,  4: 20,  5: 40,
            6: 200,  7: 500,  8: 600,  9: 400,  10: 350,  11: 300,
            12: 350,  13: 300,  14: 350,  15: 400,  16: 450,  17: 600,
            18: 550,  19: 350,  20: 250,  21: 175,  22: 100,  23: 60
        }
    }
    
    def __init__(self, seed: int = 42):
        import random
        self.random = random.Random(seed)
        self.demand_multiplier: float = 1.0
        self.localized_demand_multipliers: Dict[str, float] = {}
    
    def set_demand_multiplier(self, multiplier: float) -> None:
        """Set global demand multiplier without modifying static BASE_DEMAND."""
        self.demand_multiplier = max(0.1, float(multiplier))
    
    def get_demand_multiplier(self) -> float:
        """Get current demand multiplier."""
        return self.demand_multiplier
    
    def set_localized_demand(self, road_multipliers: Dict[str, float]) -> None:
        """Set localized demand multipliers for specific roads (e.g. major event)."""
        self.localized_demand_multipliers = dict(road_multipliers)
    
    def reset_demand(self) -> None:
        """Reset all demand modifiers back to clean baseline."""
        self.demand_multiplier = 1.0
        self.localized_demand_multipliers.clear()
    
    def get_road_demand(self, road_id: str, road_type: str, hour: float, is_weekend: bool) -> float:
        """Get demand for a specific road considering both global and localized modifiers."""
        base = self.interpolate_demand(road_type, hour, is_weekend)
        road_mult = self.localized_demand_multipliers.get(road_id, 1.0)
        return base * self.demand_multiplier * road_mult
    
    def get_base_demand(self, road_type: str, hour: int, is_weekend: bool) -> float:
        """Get base demand for road type at given hour."""
        demand_map = self.BASE_DEMAND.get(road_type, self.BASE_DEMAND['major'])
        base = demand_map.get(hour, 50)
        
        if is_weekend:
            # Weekend adjustments
            if 7 <= hour <= 9:      # Morning rush reduced
                base *= 0.4
            elif 10 <= hour <= 18:  # Midday increased
                base *= 1.15
            elif 19 <= hour <= 22:  # Evening extended
                base *= 1.2
            else:
                base *= 0.8
        
        return base
    
    def interpolate_demand(self, road_type: str, hour: float, is_weekend: bool) -> float:
        """Interpolate demand between integer hours."""
        hour_int = int(hour)
        next_hour = (hour_int + 1) % 24
        frac = hour - hour_int
        
        demand_1 = self.get_base_demand(road_type, hour_int, is_weekend)
        demand_2 = self.get_base_demand(road_type, next_hour, is_weekend)
        
        return demand_1 + frac * (demand_2 - demand_1)
    
    def get_demand_with_noise(self, road_type: str, hour: float, is_weekend: bool) -> int:
        """Get demand with random noise applied."""
        base = self.interpolate_demand(road_type, hour, is_weekend)
        noise = self.random.uniform(0.8, 1.2)
        return max(0, int(base * noise))


class TimeProvider:
    """Provides time-related utilities for simulation."""
    
    @staticmethod
    def is_weekend(dt: datetime) -> bool:
        return dt.weekday() >= 5  # 5=Saturday, 6=Sunday
    
    @staticmethod
    def is_rush_hour(dt: datetime) -> bool:
        hour = dt.hour
        return (7 <= hour <= 9) or (16 <= hour <= 19)
    
    @staticmethod
    def minutes_since_midnight(dt: datetime) -> int:
        return dt.hour * 60 + dt.minute
    
    @staticmethod
    def hour_of_week(dt: datetime) -> int:
        """0-167 (7 days * 24 hours)"""
        return dt.weekday() * 24 + dt.hour