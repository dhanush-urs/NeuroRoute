from dataclasses import dataclass
from typing import Optional


@dataclass
class RoutingWeights:
    """Configurable weights for route cost calculation."""
    travel_time: float = 1.0      # Base travel time weight
    congestion: float = 0.5       # Congestion penalty weight
    incident: float = 1.0         # Incident penalty weight
    risk: float = 0.3             # Weather/other risk weight
    
    @classmethod
    def from_settings(cls) -> "RoutingWeights":
        """Create from environment settings."""
        import os
        return cls(
            travel_time=float(os.getenv("ROUTING_WEIGHTS_TRAVEL_TIME", "1.0")),
            congestion=float(os.getenv("ROUTING_WEIGHTS_CONGESTION", "0.5")),
            incident=float(os.getenv("ROUTING_WEIGHTS_INCIDENT", "1.0")),
            risk=float(os.getenv("ROUTING_WEIGHTS_RISK", "0.3")),
        )
    
    @classmethod
    def neuro_route(cls) -> "RoutingWeights":
        """NeuroRoute recommended weights (predictive)."""
        return cls(
            travel_time=1.0,
            congestion=1.0,   # Full weight on predicted congestion
            incident=1.5,     # Higher incident penalty
            risk=0.5
        )
    
    @classmethod
    def current_fastest(cls) -> "RoutingWeights":
        """Current fastest (reactive) weights."""
        return cls(
            travel_time=1.0,
            congestion=0.5,
            incident=1.0,
            risk=0.3
        )
    
    @classmethod
    def shortest_distance(cls) -> "RoutingWeights":
        """Shortest distance (static) weights."""
        return cls(
            travel_time=1.0,
            congestion=0.0,
            incident=0.0,
            risk=0.0
        )