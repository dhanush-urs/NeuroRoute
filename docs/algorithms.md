# Algorithms Documentation

## Graph Representation

The road network is represented as a **weighted directed graph** G = (V, E):

- **V**: Set of nodes (junctions/intersections)
- **E**: Set of directed edges (road segments)
- Each edge e ∈ E has attributes:
  - `distance_km`: Physical length
  - `speed_limit_kmh`: Maximum legal speed
  - `capacity_vph`: Vehicles per hour (theoretical max)
  - `road_type`: highway | major | minor | local
  - **Dynamic weights** (updated each simulation tick):
    - `current_congestion`: 0.0–1.0
    - `predicted_congestion_5m/15m/30m/60m`: 0.0–1.0
    - `incident_penalty`: 0.0+
    - `weather_penalty`: 0.0+

## Pathfinding Algorithms

### Dijkstra's Algorithm

**Purpose**: Shortest-distance baseline (static weights)

**Complexity**: O((V + E) log V) with binary heap

**Implementation** (`backend/app/graph/dijkstra.py`):

```python
def dijkstra(graph: RoadGraph, source: str, target: str) -> Optional[Path]:
    dist = {node: inf for node in graph.nodes}
    dist[source] = 0
    prev = {}
    pq = [(0, source)]
    
    while pq:
        d, u = heappop(pq)
        if d > dist[u]: continue
        if u == target: break
        
        for edge in graph.get_neighbors(u):
            v = edge.target
            weight = edge.distance_km  # Static distance weight
            alt = d + weight
            if alt < dist[v]:
                dist[v] = alt
                prev[v] = u
                heappush(pq, (alt, v))
    
    return reconstruct_path(prev, source, target)
```

**Use Case**: Baseline comparison, static routing

---

### A* Algorithm

**Purpose**: Current fastest / Predicted fastest (dynamic weights with heuristic)

**Complexity**: O((V + E) log V) — same as Dijkstra but explores fewer nodes with good heuristic

**Heuristic**: Haversine distance / max_speed_limit

```python
def haversine(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km"""
    R = 6371.0
    φ1, φ2 = radians(lat1), radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)
    a = sin(Δφ/2)² + cos(φ1)*cos(φ2)*sin(Δλ/2)²
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

def astar_heuristic(graph, node, target):
    node_coords = graph.nodes[node]
    target_coords = graph.nodes[target]
    straight_line = haversine(node_coords.lat, node_coords.lon, 
                               target_coords.lat, target_coords.lon)
    # Admissible: assume max speed (optimistic)
    return straight_line / (120 / 3.6)  # time in seconds at 120 km/h
```

**Edge Weight Function**:

```python
def edge_weight(edge: Edge, weights: RoutingWeights, horizon: int = 15) -> float:
    """Dynamic cost combining multiple factors"""
    
    # Predicted travel time at horizon
    pred_congestion = getattr(edge, f'predicted_congestion_{horizon}m', edge.current_congestion)
    effective_speed = edge.speed_limit_kmh * (1 - pred_congestion * 0.7)
    travel_time = (edge.distance_km / max(effective_speed, 1.0)) * 3600  # seconds
    
    # Weighted combination
    cost = (
        weights.travel_time * travel_time +
        weights.congestion * pred_congestion * 300 +      # 5 min penalty per 0.1 congestion
        weights.incident * edge.incident_penalty * 600 +  # 10 min per incident
        weights.risk * edge.weather_penalty * 100
    )
    return cost
```

**Use Cases**:
- **Current fastest**: `horizon=0`, `weights=RoutingWeights(travel_time=1.0, congestion=0.5)`
- **Predicted fastest**: `horizon=15`, `weights=RoutingWeights(travel_time=1.0, congestion=1.0, incident=1.0)`

---

### NeuroRoute Algorithm

**Purpose**: Production recommendation with dynamic cost function

**Algorithm**: A* with **predicted congestion weights** + **rerouting awareness**

```python
NEUROROUTE_WEIGHTS = RoutingWeights(
    travel_time=1.0,
    congestion=1.0,      # Full weight on predicted congestion
    incident=1.5,        # Higher incident penalty
    risk=0.5             # Weather risk
)

def neuro_route(graph, origin, destination):
    # Use 15-minute predicted congestion
    return astar(graph, origin, destination, 
                 weights=NEUROROUTE_WEIGHTS,
                 horizon=15)
```

**Key Difference from A***: Uses predicted (not current) congestion for edge weights, enabling proactive rerouting.

---

## Dynamic Edge Weights

### Travel Time Calculation

```python
def travel_time(edge: Edge, congestion: float) -> float:
    """Seconds to traverse edge at given congestion level"""
    # Speed drops linearly with congestion (max 70% reduction at 1.0)
    effective_speed = edge.speed_limit_kmh * (1 - congestion * 0.7)
    effective_speed = max(effective_speed, 5.0)  # Minimum 5 km/h
    return (edge.distance_km / effective_speed) * 3600
```

### Congestion-Aware Weight

```
weight = travel_time + congestion_penalty + incident_penalty + risk_penalty

Where:
- travel_time = predicted travel time at horizon H
- congestion_penalty = predicted_congestion_H * penalty_factor
- incident_penalty = incident_severity * capacity_reduction * factor
- risk_penalty = weather_severity * factor
```

### Default Weights (Configurable)

| Weight | Value | Description |
|--------|-------|-------------|
| `travel_time` | 1.0 | Base travel time in seconds |
| `congestion` | 0.5–1.0 | Congestion penalty (higher for predicted) |
| `incident` | 1.0–1.5 | Incident impact |
| `risk` | 0.3–0.5 | Weather/other risks |

---

## Congestion Propagation

### Algorithm

When road R becomes congested, traffic redistributes to downstream roads:

```python
def propagate_congestion(graph: RoadGraph, congested_roads: Set[str]) -> Dict[str, float]:
    impacts = defaultdict(float)
    
    for road_id in congested_roads:
        road = graph.get_road(road_id)
        # Throughput reduction proportional to congestion
        throughput_loss = road.capacity_vph * road.congestion_score * 0.7
        
        # Distribute to downstream roads
        downstream = graph.get_downstream_roads(road_id)
        for ds_road in downstream:
            # Simplified: equal split among downstream
            share = throughput_loss / len(downstream)
            # 30% of lost throughput propagates downstream
            impacts[ds_road.id] += share * 0.3
    
    return impacts
```

### Properties

- **Single-hop propagation** by default (configurable depth)
- **Dampening factor** (0.3) prevents runaway propagation
- **Downstream only** — congestion flows with traffic direction
- **Additive** — multiple upstream sources accumulate

---

## Route Scoring

### Scoring Formula

```python
def score_route(route: Route, weights: RoutingWeights) -> float:
    # Lower is better (cost), so negate for score
    total_cost = sum(edge.route_cost(weights) for edge in route.edges)
    
    # Normalize to 0-100 scale (100 = best)
    # Reference: free-flow travel time
    free_flow_time = sum(e.distance_km / (e.speed_limit_kmh / 3.6) for e in route.edges)
    score = max(0, 100 * (1 - (total_cost - free_flow_time) / free_flow_time))
    
    return round(score, 1)
```

### Risk Classification

| Predicted Congestion | Risk Level |
|---------------------|------------|
| < 0.30 | LOW |
| 0.30–0.50 | MEDIUM |
| 0.50–0.70 | HIGH |
| ≥ 0.70 | CRITICAL |

### Explanation Facts (Structured for LLM)

```python
explanation_facts = {
    "recommended_route": "Route B",
    "routes": [
        {"name": "Route A (Shortest)", "distance_km": 7.8, 
         "current_eta_min": 19, "predicted_eta_min": 31, "risk": "HIGH"},
        {"name": "Route B (NeuroRoute)", "distance_km": 9.2,
         "current_eta_min": 22, "predicted_eta_min": 23, "risk": "LOW"},
    ],
    "incident": {"type": "accident", "road": "R102", "capacity_reduction": 70},
    "prediction_confidence": 0.91,
    "horizon_min": 15
}
```

---

## Rerouting Logic

### Trigger Conditions

Reroute when **any** condition met:

```python
SHOULD_REROUTE = (
    # Significant ETA improvement
    (new_predicted_eta < current_predicted_eta - REROUTE_THRESHOLD_SEC) OR
    
    # Current route becomes high risk
    (current_route_risk >= "HIGH") OR
    
    # New incident on current route
    (new_incident_on_current_route)
)

REROUTE_THRESHOLD_SEC = 120  # 2 minutes minimum savings
```

### Rerouting Process

1. Detect route degradation (monitor every 30s)
2. Recalculate all candidate routes with current weights
3. Compare new best vs current route
4. If threshold met, emit `route_update` via WebSocket
5. Frontend smoothly transitions route visualization

---

## Complexity Analysis

| Operation | Time | Space | Notes |
|-----------|------|-------|-------|
| Dijkstra | O((V+E) log V) | O(V) | V≈200, E≈500 → ~3ms |
| A* | O((V+E) log V) | O(V) | Better with heuristic |
| NeuroRoute | O((V+E) log V) | O(V) | Same as A* |
| Congestion Prop | O(E) | O(V) | Single pass |
| ML Inference | O(T×D) | O(T×D) | T=trees, D=features |
| Full Tick | O(V+E+T×D) | O(V) | ~38ms target |

---

## Why Not Distance Alone?

```
Route A: 7.8 km, free flow 9 min → but predicted 31 min (accident ahead)
Route B: 9.2 km, free flow 11 min → predicted 12 min (stable)

Shortest distance = Route A (wrong choice)
Current fastest = Route A (wrong — doesn't predict accident)
NeuroRoute = Route B (correct — uses prediction)
```

Distance minimization ignores:
- Time-varying congestion
- Incident impacts
- Weather effects
- Downstream propagation
- Predictive intelligence