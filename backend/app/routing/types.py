from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid


class AlgorithmType(str, Enum):
    DIJKSTRA = "dijkstra"
    ASTAR_CURRENT = "astar_current"
    ASTAR_PREDICTED = "astar_predicted"
    NEURO_ROUTE = "neuro_route"


@dataclass
class RouteCandidate:
    """A candidate route with all metadata."""
    route_id: str
    algorithm: AlgorithmType
    nodes: List[str]
    edges: List[str]
    distance_km: float
    current_eta_sec: int
    predicted_eta_sec: int
    congestion_risk: str  # low, medium, high, critical
    score: float
    rank: int = 0
    is_recommended: bool = False
    explanation_facts: Dict = field(default_factory=dict)


__all__ = ["AlgorithmType", "RouteCandidate"]