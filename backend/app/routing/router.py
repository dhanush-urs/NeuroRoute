from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid

from app.graph.graph import RoadGraph
from app.graph.dijkstra import dijkstra
from app.graph.astar import astar
from app.graph.weights import RoutingWeights
from app.routing.route_scorer import RouteScorer
from app.routing.recommendation import RouteRecommender
from app.routing.types import AlgorithmType, RouteCandidate


class AlgorithmType(str, Enum):
    DIJKSTRA = "dijkstra"
    ASTAR_CURRENT = "astar_current"
    ASTAR_PREDICTED = "astar_predicted"
    NEURO_ROUTE = "neuro_route"


@dataclass
class RouteCandidate:
    """A candidate route with all metadata."""
    route_id: str
    algorithm: "AlgorithmType"
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


class Router:
    """Multi-algorithm router with dynamic weights."""
    
    def __init__(
        self,
        graph: "RoadGraph",
        weights: Optional[RoutingWeights] = None,
        reroute_threshold_sec: int = 120
    ):
        self.graph = graph
        self.weights = weights or RoutingWeights.neuro_route()
        self.reroute_threshold_sec = reroute_threshold_sec
        
        self.scorer = RouteScorer()
        self.recommender = RouteRecommender()
    
    def calculate_route(
        self,
        origin: str,
        destination: str,
        algorithm: "AlgorithmType" = AlgorithmType.NEURO_ROUTE,
        consider_predictions: bool = True
    ) -> Optional["RouteCandidate"]:
        """Calculate a single route using specified algorithm."""
        
        if origin not in self.graph.nodes or destination not in self.graph.nodes:
            return None
        
        if origin == destination:
            return self._create_same_location_candidate(origin, AlgorithmType.NEURO_ROUTE)
        
        # Run the appropriate algorithm
        if algorithm == AlgorithmType.DIJKSTRA:
            result = dijkstra(self.graph, origin, destination)
        elif algorithm == AlgorithmType.ASTAR_CURRENT:
            result = astar(self.graph, origin, destination, use_predictions=False)
        elif algorithm == AlgorithmType.ASTAR_PREDICTED:
            result = astar(self.graph, origin, destination, use_predictions=True, horizon=15)
        elif algorithm == AlgorithmType.NEURO_ROUTE:
            result = astar(self.graph, origin, destination, use_predictions=True, horizon=15)
        else:
            return None
        
        if not result or not result.found:
            return None
        
        return self._create_candidate(result, algorithm)
    
    def calculate_all_algorithms(
        self,
        origin: str,
        destination: str
    ) -> List["RouteCandidate"]:
        """Calculate routes using all three algorithms."""
        candidates = []
        
        algorithms = [
            AlgorithmType.DIJKSTRA,
            AlgorithmType.ASTAR_CURRENT,
            AlgorithmType.NEURO_ROUTE
        ]
        
        for algo in algorithms:
            candidate = self.calculate_route(origin, destination, algo)
            if candidate:
                candidates.append(candidate)
        
        # Score and rank all candidates
        candidates = self.scorer.score_candidates(candidates, self.weights)
        candidates = self.recommender.rank_and_recommend(candidates)
        
        return candidates
    
    def calculate_recommendation(
        self,
        origin: str,
        destination: str
    ) -> Tuple[Optional["RouteCandidate"], List["RouteCandidate"]]:
        """Get recommended route with alternatives."""
        candidates = self.calculate_all_algorithms(origin, destination)
        
        if not candidates:
            return None, []
        
        recommended = next((c for c in candidates if c.is_recommended), candidates[0])
        alternatives = [c for c in candidates if c.route_id != recommended.route_id]
        
        return recommended, alternatives
    
    def check_reroute(
        self,
        current_route: "RouteCandidate",
        current_tick: int
    ) -> Tuple[bool, Optional["RouteCandidate"]]:
        """
        Check if rerouting is beneficial for a specific route.
        
        Returns (should_reroute, new_route_candidate)
        """
        # Recalculate current route with current conditions
        current_recalc = self.calculate_route(
            current_route.nodes[0],
            current_route.nodes[-1],
            AlgorithmType.NEURO_ROUTE
        )
        
        if not current_recalc:
            return False, None
        
        # Check if predicted ETA improved significantly
        eta_improvement = current_route.predicted_eta_sec - current_recalc.predicted_eta_sec
        
        if eta_improvement >= self.reroute_threshold_sec:
            return True, current_recalc
        
        # Check if current route risk became critical
        if current_recalc.congestion_risk == "critical" and current_route.congestion_risk != "critical":
            return True, current_recalc
        
        return False, None

    async def check_reroute_tick(self, current_tick: int) -> None:
        """
        Check for reroutes across all active routes (called each tick).
        This is a simplified version that the simulation engine calls.
        """
        # In a full implementation, this would track active routes and check each
        # For now, we just log that the check ran
        import logging
        logging.getLogger(__name__).debug(f"Reroute check at tick {current_tick}")
        # The actual reroute logic would go here if we tracked active routes
        pass
    
    def _create_same_location_candidate(
        self, 
        node_id: str, 
        algorithm: "AlgorithmType"
    ) -> "RouteCandidate":
        """Create candidate for same origin/destination."""
        return RouteCandidate(
            route_id=str(uuid.uuid4())[:8],
            algorithm=algorithm,
            nodes=[node_id],
            edges=[],
            distance_km=0.0,
            current_eta_sec=0,
            predicted_eta_sec=0,
            congestion_risk="low",
            score=100.0,
            explanation_facts={
                "type": "same_location",
                "message": "Origin and destination are the same"
            }
        )
    
    def _create_candidate(self, result, algorithm: "AlgorithmType") -> "RouteCandidate":
        """Create RouteCandidate from pathfinding result."""
        if not result or not result.found:
            return None
        
        # Calculate ETAs
        current_eta = int(result.travel_time)
        predicted_eta = current_eta  # Simplified - would use predicted weights
        
        # Determine congestion risk
        max_congestion = 0.0
        for edge_id in result.edges:
            edge = self.graph.edges.get(edge_id)
            if edge:
                max_congestion = max(max_congestion, edge.current_congestion)
        
        if max_congestion < 0.3:
            risk = "low"
        elif max_congestion < 0.5:
            risk = "medium"
        elif max_congestion < 0.7:
            risk = "high"
        else:
            risk = "critical"
        
        route_id = str(uuid.uuid4())[:8]
        
        return RouteCandidate(
            route_id=route_id,
            algorithm=algorithm,
            nodes=result.nodes,
            edges=result.edges,
            distance_km=round(result.distance, 2),
            current_eta_sec=current_eta,
            predicted_eta_sec=predicted_eta,
            congestion_risk=risk,
            score=0.0,  # Will be set by scorer
            explanation_facts={
                "algorithm": algorithm.value,
                "distance_km": round(result.distance, 2),
                "max_congestion": round(max_congestion, 2),
                "num_edges": len(result.edges)
            }
        )