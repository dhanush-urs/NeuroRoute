import heapq
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.graph.graph import RoadGraph


@dataclass
class PathResult:
    """Result of pathfinding algorithm."""
    nodes: List[str]
    edges: List[str]
    distance: float
    travel_time: float
    found: bool = True


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    R = 6371.0  # Earth radius in km
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def astar_heuristic(graph, node_id: str, target_id: str) -> float:
    """
    A* heuristic: straight-line distance / max speed.
    Admissible (never overestimates).
    """
    source_node = graph.nodes.get(node_id)
    target_node = graph.nodes.get(target_id)
    
    if not source_node or not target_node:
        return 0.0
    
    straight_line_km = haversine(
        source_node.latitude, source_node.longitude,
        target_node.latitude, target_node.longitude
    )
    
    # Assume max speed 120 km/h for admissibility
    max_speed_kmh = 120.0
    return (straight_line_km / max_speed_kmh) * 3600  # seconds


def astar(
    graph: "RoadGraph",
    source: str,
    target: str,
    use_predictions: bool = True,
    horizon: int = 15
) -> Optional[PathResult]:
    """
    A* algorithm with dynamic edge weights.
    
    Args:
        graph: Road graph
        source: Source node ID
        target: Target node ID
        use_predictions: Use predicted congestion (True) or current (False)
        horizon: Prediction horizon in minutes (5, 15, 30, 60)
    """
    if source not in graph.nodes or target not in graph.nodes:
        return None
    
    if source == target:
        return PathResult(
            nodes=[source],
            edges=[],
            distance=0.0,
            travel_time=0.0
        )
    
    # g-score: cost from start to node
    g_score: Dict[str, float] = {node_id: float('inf') for node_id in graph.nodes}
    g_score[source] = 0.0
    
    # f-score: g + heuristic
    f_score: Dict[str, float] = {node_id: float('inf') for node_id in graph.nodes}
    f_score[source] = astar_heuristic(graph, source, target)
    
    # Previous node/edge in optimal path
    previous: Dict[str, str] = {}
    previous_edges: Dict[str, str] = {}
    
    # Priority queue: (f_score, node_id)
    pq: List[Tuple[float, str]] = [(f_score[source], source)]
    visited: set = set()
    
    while pq:
        current_f, current = heapq.heappop(pq)
        
        if current in visited:
            continue
        visited.add(current)
        
        if current == target:
            break
        
        if current_f > f_score[current]:
            continue
        
        # Explore neighbors
        for edge in graph.get_neighbors(current):
            # Skip closed roads
            if getattr(edge, 'incident_penalty', 0.0) >= 0.95 or getattr(edge, 'congestion_level', '') == 'closed':
                continue

            neighbor = edge.target
            
            if neighbor in visited:
                continue
            
            # Calculate edge weight (dynamic)
            if use_predictions:
                pred_attr = f'predicted_congestion_{horizon}m'
                pred_congestion = getattr(edge, pred_attr, edge.current_congestion)
                effective_speed = edge.speed_limit_kmh * (1 - pred_congestion * 0.7)
            else:
                effective_speed = edge.speed_limit_kmh * (1 - edge.current_congestion * 0.7)
            
            effective_speed = max(effective_speed, 1.0)
            weight = (edge.distance_km / effective_speed) * 3600  # seconds
            
            # Add incident/weather penalties
            weight += edge.incident_penalty * 600  # 10 min per incident unit
            weight += edge.weather_penalty * 100   # weather penalty
            
            tentative_g = g_score[current] + weight
            
            if tentative_g < g_score[neighbor]:
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + astar_heuristic(graph, neighbor, target)
                previous[neighbor] = current
                previous_edges[neighbor] = edge.id
                heapq.heappush(pq, (f_score[neighbor], neighbor))
    
    if g_score[target] == float('inf'):
        return None
    
    # Reconstruct path
    path_nodes = []
    path_edges = []
    current = target
    total_distance = 0.0
    total_travel_time = 0.0
    
    while current != source:
        path_nodes.append(current)
        edge_id = previous_edges.get(current)
        if edge_id:
            path_edges.append(edge_id)
            edge = graph.edges.get(edge_id)
            if edge:
                total_distance += edge.distance_km
                total_travel_time += edge.travel_time_current()
        current = previous.get(current, source)
    
    path_nodes.append(source)
    path_nodes.reverse()
    path_edges.reverse()
    
    return PathResult(
        nodes=path_nodes,
        edges=path_edges,
        distance=total_distance,
        travel_time=total_travel_time
    )


def astar_multi_target(
    graph: "RoadGraph",
    source: str,
    targets: List[str],
    use_predictions: bool = True,
    horizon: int = 15
) -> Dict[str, PathResult]:
    """Run A* from one source to multiple targets."""
    results = {}
    for target in targets:
        if source != target:
            result = astar(graph, source, target, use_predictions, horizon)
            if result:
                results[target] = result
    return results