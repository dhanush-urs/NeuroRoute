from typing import List, Dict, Optional
from dataclasses import dataclass, field

from app.routing.types import RouteCandidate, AlgorithmType
from app.graph.weights import RoutingWeights


@dataclass
class ScoringConfig:
    """Configuration for route scoring."""
    # Time weights
    base_score: float = 100.0
    time_penalty_per_min: float = 2.0
    
    # Risk penalties
    risk_penalties: Dict[str, float] = field(default_factory=lambda: {
        "low": 0,
        "medium": 5,
        "high": 15,
        "critical": 30
    })
    
    # Algorithm bonuses
    algorithm_bonus: Dict[str, float] = field(default_factory=lambda: {
        "dijkstra": 0,
        "astar_current": 5,
        "neuro_route": 10
    })
    
    # Distance penalty (per km over shortest)
    distance_penalty_per_km: float = 1.0
    
    # Incident penalty
    incident_penalty: float = 20.0


@dataclass
class ScoreBreakdown:
    """Detailed score breakdown for a route."""
    base_score: float
    time_penalty: float
    risk_penalty: float
    algorithm_bonus: float
    distance_penalty: float
    incident_penalty: float
    total_score: float


class RouteScorer:
    """Scores and ranks routes based on multiple criteria."""
    
    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or ScoringConfig()
    
    def score_route(
        self,
        candidate: "RouteCandidate",
        all_candidates: List["RouteCandidate"],
        weights: "RoutingWeights"
    ) -> ScoreBreakdown:
        """Score a single route candidate."""
        
        # Find shortest distance for comparison
        shortest_distance = min(c.distance_km for c in [candidate])
        
        # Time penalty (lower predicted ETA is better)
        # Normalize: 0 penalty for best, max for worst
        min_predicted_eta = min(c.predicted_eta_sec for c in [candidate])
        max_predicted_eta = max(c.predicted_eta_sec for c in [candidate])
        
        if max_predicted_eta > min_predicted_eta:
            time_ratio = (candidate.predicted_eta_sec - min_predicted_eta) / (max_predicted_eta - min_predicted_eta)
            time_penalty = time_ratio * self.config.time_penalty_per_min * 10
        else:
            time_penalty = 0
        
        # Risk penalty
        risk_penalty = self.config.risk_penalties.get(candidate.congestion_risk, 0)
        
        # Algorithm bonus
        algo_bonus = self.config.algorithm_bonus.get(candidate.algorithm.value, 0)
        
        # Distance penalty (compared to shortest)
        distance_diff = candidate.distance_km - shortest_distance
        distance_penalty = max(0, distance_diff) * self.config.distance_penalty_per_km
        
        # Incident penalty (check explanation facts)
        incident_penalty = 0
        if candidate.explanation_facts.get("has_incident"):
            incident_penalty = self.config.incident_penalty
        
        total = (
            self.config.base_score
            - time_penalty
            - risk_penalty
            - distance_penalty
            - incident_penalty
            + algo_bonus
        )
        
        return ScoreBreakdown(
            base_score=self.config.base_score,
            time_penalty=time_penalty,
            risk_penalty=risk_penalty,
            algorithm_bonus=algo_bonus,
            distance_penalty=distance_penalty,
            incident_penalty=incident_penalty,
            total_score=max(0, total)
        )
    
    def score_candidates(
        self,
        candidates: List["RouteCandidate"],
        weights: "RoutingWeights"
    ) -> List["RouteCandidate"]:
        """Score all candidates and update their scores."""
        for candidate in candidates:
            breakdown = self.score_route(candidate, [candidate], weights)
            candidate.score = breakdown.total_score
        return candidates