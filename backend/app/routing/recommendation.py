from typing import List, Optional, Dict
from dataclasses import dataclass, field

from app.routing.types import RouteCandidate, AlgorithmType


@dataclass
class RouteComparison:
    """Comparison between two routes."""
    route_a: "RouteCandidate"
    route_b: "RouteCandidate"
    time_saved_sec: int
    distance_diff_km: float
    risk_improvement: str
    recommendation: str


class RouteRecommender:
    """Selects and explains the best route."""
    
    def __init__(self):
        pass
    
    def rank_and_recommend(
        self,
        candidates: List["RouteCandidate"]
    ) -> List["RouteCandidate"]:
        """Rank candidates and mark the best as recommended."""
        if not candidates:
            return candidates
        
        # Sort by score (descending)
        candidates.sort(key=lambda c: c.score, reverse=True)
        
        # Assign ranks
        for i, candidate in enumerate(candidates):
            candidate.rank = i + 1
            candidate.is_recommended = (i == 0)
        
        return candidates
    
    def compare_routes(
        self,
        route_a: "RouteCandidate",
        route_b: "RouteCandidate"
    ) -> RouteComparison:
        """Compare two routes and generate recommendation."""
        time_saved = route_a.predicted_eta_sec - route_b.predicted_eta_sec
        distance_diff = route_b.distance_km - route_a.distance_km
        
        # Risk comparison
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        risk_a = risk_order.get(route_a.congestion_risk, 0)
        risk_b = risk_order.get(route_b.congestion_risk, 0)
        risk_diff = risk_a - risk_b
        
        if risk_diff > 0:
            risk_improvement = f"{route_a.congestion_risk} -> {route_b.congestion_risk}"
        elif risk_diff < 0:
            risk_improvement = f"{route_a.congestion_risk} -> {route_b.congestion_risk} (worse)"
        else:
            risk_improvement = f"Same ({route_a.congestion_risk})"
        
        # Generate recommendation
        if time_saved > 60:  # More than 1 minute saved
            recommendation = (
                f"Route {route_b.route_id} saves {time_saved // 60} min {time_saved % 60} sec "
                f"with {risk_improvement.lower()} risk"
            )
        elif time_saved < -60:
            recommendation = (
                f"Route {route_a.route_id} is faster by {abs(time_saved) // 60} min "
                f"but has {risk_improvement.lower()} risk"
            )
        else:
            recommendation = (
                f"Routes similar in time. {route_b.route_id} has {risk_improvement.lower()} risk"
            )
        
        return RouteComparison(
            route_a=route_a,
            route_b=route_b,
            time_saved_sec=time_saved,
            distance_diff_km=round(distance_diff, 2),
            risk_improvement=risk_improvement,
            recommendation=recommendation
        )
    
    def generate_explanation_facts(
        self,
        recommended: "RouteCandidate",
        alternatives: List["RouteCandidate"],
        incident: Optional[Dict] = None
    ) -> Dict:
        """Generate structured facts for AI explanation."""
        facts = {
            "recommended_route": recommended.route_id,
            "recommended_algorithm": recommended.algorithm.value,
            "distance_km": recommended.distance_km,
            "current_eta_min": round(recommended.current_eta_sec / 60, 1),
            "predicted_eta_min": round(recommended.predicted_eta_sec / 60, 1),
            "congestion_risk": recommended.congestion_risk,
            "alternatives": []
        }
        
        for alt in alternatives[:2]:  # Top 2 alternatives
            facts["alternatives"].append({
                "route_id": alt.route_id,
                "distance_km": alt.distance_km,
                "current_eta_min": round(alt.current_eta_sec / 60, 1),
                "predicted_eta_min": round(alt.predicted_eta_sec / 60, 1),
                "congestion_risk": alt.congestion_risk,
                "algorithm": alt.algorithm.value
            })
        
        if incident:
            facts["incident"] = incident
        
        return facts
    
    def get_recommendation_reason(
        self,
        recommended: "RouteCandidate",
        alternatives: List["RouteCandidate"]
    ) -> str:
        """Generate human-readable reason for recommendation."""
        if not alternatives:
            return "Only one route available."
        
        best_alt = alternatives[0]
        time_diff = recommended.predicted_eta_sec - best_alt.predicted_eta_sec
        
        reasons = []
        
        if time_diff < -30:
            reasons.append(
                f"Saves {abs(time_diff) // 60} min {abs(time_diff) % 60} sec vs {best_alt.route_id}"
            )
        elif time_diff > 30:
            reasons.append(
                f"{best_alt.route_id} is faster by {time_diff // 60} min but higher risk"
            )
        else:
            reasons.append("Similar travel time")
        
        if recommended.congestion_risk != best_alt.congestion_risk:
            risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            if risk_order.get(recommended.congestion_risk, 0) < risk_order.get(best_alt.congestion_risk, 0):
                reasons.append(f"Lower risk ({recommended.congestion_risk} vs {best_alt.congestion_risk})")
            else:
                reasons.append(f"Higher risk ({recommended.congestion_risk} vs {best_alt.congestion_risk})")
        
        return " ".join(reasons)