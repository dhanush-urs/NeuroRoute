from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.graph.graph import RoadGraph
from app.routing.router import Router, AlgorithmType, RouteCandidate
from app.state import get_road_graph
from app.api.websocket import get_websocket_manager, broadcast_route_update

router = APIRouter(prefix="/routes", tags=["routing"])


def get_router() -> Router:
    """Get router instance with current graph."""
    graph = get_road_graph()
    return Router(graph=graph)


@router.get("/calculate")
async def calculate_route(
    origin: str = Query(..., description="Origin node ID"),
    destination: str = Query(..., description="Destination node ID"),
    algorithm: AlgorithmType = Query(AlgorithmType.NEURO_ROUTE, description="Routing algorithm"),
) -> dict:
    """Calculate a single route using specified algorithm."""
    graph = get_road_graph()
    router = Router(graph=graph)
    
    candidate = router.calculate_route(origin, destination, algorithm)
    
    if not candidate:
        raise HTTPException(status_code=404, detail="No route found")
    
    route_data = {
        "route_id": candidate.route_id,
        "algorithm": candidate.algorithm.value,
        "nodes": candidate.nodes,
        "edges": candidate.edges,
        "distance_km": candidate.distance_km,
        "current_eta_sec": candidate.current_eta_sec,
        "predicted_eta_sec": candidate.predicted_eta_sec,
        "congestion_risk": candidate.congestion_risk,
        "score": candidate.score,
        "explanation_facts": candidate.explanation_facts,
    }
    
    # Broadcast route update via WebSocket
    ws_manager = get_websocket_manager()
    await broadcast_route_update(route_data)
    
    return route_data


@router.get("/calculate-all")
async def calculate_all_routes(
    origin: str = Query(..., description="Origin node ID"),
    destination: str = Query(..., description="Destination node ID"),
) -> List[dict]:
    """Calculate routes using all algorithms."""
    graph = get_road_graph()
    router = Router(graph=graph)
    
    candidates = router.calculate_all_algorithms(origin, destination)
    
    routes_data = [
        {
            "route_id": c.route_id,
            "algorithm": c.algorithm.value,
            "nodes": c.nodes,
            "edges": c.edges,
            "distance_km": c.distance_km,
            "current_eta_sec": c.current_eta_sec,
            "predicted_eta_sec": c.predicted_eta_sec,
            "congestion_risk": c.congestion_risk,
            "score": c.score,
            "rank": c.rank,
            "is_recommended": c.is_recommended,
            "explanation_facts": c.explanation_facts,
        }
        for c in candidates
    ]
    
    # Broadcast route updates via WebSocket
    ws_manager = get_websocket_manager()
    for route_data in routes_data:
        await broadcast_route_update(route_data)
    
    return routes_data


@router.get("/recommend")
async def recommend_route(
    origin: str = Query(..., description="Origin node ID"),
    destination: str = Query(..., description="Destination node ID"),
) -> dict:
    """Get recommended route with alternatives."""
    graph = get_road_graph()
    router = Router(graph=graph)
    
    recommended, alternatives = router.calculate_recommendation(origin, destination)
    
    if not recommended:
        raise HTTPException(status_code=404, detail="No route found")
    
    recommended_data = {
        "route_id": recommended.route_id,
        "algorithm": recommended.algorithm.value,
        "nodes": recommended.nodes,
        "edges": recommended.edges,
        "distance_km": recommended.distance_km,
        "current_eta_sec": recommended.current_eta_sec,
        "predicted_eta_sec": recommended.predicted_eta_sec,
        "congestion_risk": recommended.congestion_risk,
        "score": recommended.score,
        "explanation_facts": recommended.explanation_facts,
    }
    
    alternatives_data = [
        {
            "route_id": c.route_id,
            "algorithm": c.algorithm.value,
            "nodes": c.nodes,
            "edges": c.edges,
            "distance_km": c.distance_km,
            "current_eta_sec": c.current_eta_sec,
            "predicted_eta_sec": c.predicted_eta_sec,
            "congestion_risk": c.congestion_risk,
            "score": c.score,
            "rank": c.rank,
            "explanation_facts": c.explanation_facts,
        }
        for c in alternatives
    ]
    
    # Broadcast route updates via WebSocket
    ws_manager = get_websocket_manager()
    await broadcast_route_update(recommended_data)
    for alt_data in alternatives_data:
        await broadcast_route_update(alt_data)
    
    return {
        "recommended": recommended_data,
        "alternatives": alternatives_data,
    }


@router.get("/{route_id}")
async def get_route(route_id: str) -> dict:
    """Get route by ID."""
    return {"message": "Route retrieval by ID not implemented yet", "route_id": route_id}


@router.post("/compare")
async def compare_routes() -> dict:
    """Compare multiple routes."""
    return {"message": "Not implemented yet"}