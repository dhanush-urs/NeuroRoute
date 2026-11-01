import heapq
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.graph.graph import RoadGraph


@dataclass
class PathResult:
    """Result of pathfinding algorithm."""
    nodes: List[str]
    edges: List[str]
    distance: float
    travel_time: float
    found: bool = True


def dijkstra(graph: RoadGraph, source: str, target: str) -> Optional[PathResult]:
    """
    Dijkstra's algorithm for shortest path by distance.
    Returns PathResult or None if no path exists.
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
    
    # Distance from source to each node
    distances: Dict[str, float] = {node_id: float('inf') for node_id in graph.nodes}
    distances[source] = 0.0
    
    # Previous node in optimal path
    previous: Dict[str, str] = {}
    previous_edges: Dict[str, str] = {}
    
    # Priority queue: (distance, node_id)
    pq: List[Tuple[float, str]] = [(0.0, source)]
    visited: set = set()
    
    while pq:
        current_dist, current = heapq.heappop(pq)
        
        if current in visited:
            continue
        visited.add(current)
        
        if current == target:
            break
        
        if current_dist > distances[current]:
            continue
        
        # Explore neighbors
        for edge in graph.get_neighbors(current):
            # Skip closed roads
            if getattr(edge, 'incident_penalty', 0.0) >= 0.95 or getattr(edge, 'congestion_level', '') == 'closed':
                continue

            neighbor = edge.target
            weight = edge.distance_km  # Static distance weight
            
            if neighbor in visited:
                continue
            
            new_dist = current_dist + weight
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                previous[neighbor] = current
                previous_edges[neighbor] = edge.id
                heapq.heappush(pq, (new_dist, neighbor))
    
    if distances[target] == float('inf'):
        return None
    
    # Reconstruct path
    path_nodes = []
    path_edges = []
    current = target
    total_travel_time = 0.0
    
    while current != source:
        path_nodes.append(current)
        edge_id = previous_edges.get(current)
        if edge_id:
            path_edges.append(edge_id)
            edge = graph.edges.get(edge_id)
            if edge:
                total_travel_time += edge.travel_time_current()
        current = previous.get(current, source)
    
    path_nodes.append(source)
    path_nodes.reverse()
    path_edges.reverse()
    
    return PathResult(
        nodes=path_nodes,
        edges=path_edges,
        distance=distances[target],
        travel_time=total_travel_time
    )


def dijkstra_multi_source(
    graph: RoadGraph,
    sources: List[str],
    targets: List[str]
) -> Dict[str, PathResult]:
    """Run Dijkstra from multiple sources to multiple targets."""
    results = {}
    for source in sources:
        for target in targets:
            if source != target:
                result = dijkstra(graph, source, target)
                if result:
                    results[f"{source}->{target}"] = result
    return results