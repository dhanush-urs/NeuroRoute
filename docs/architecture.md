# NeuroRoute Architecture

## System Overview

NeuroRoute follows a clean, modular architecture with strict separation of concerns. Each major responsibility has its own module with well-defined interfaces.

## Module Boundaries

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NEUROROUTE SYSTEM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  SIMULATION  │  │    GRAPH     │  │  PREDICTION  │             │
│  │   MODULE     │  │   MODULE     │  │   MODULE     │             │
│  │              │  │              │  │              │             │
│  │ • Engine     │  │ • Nodes      │  │ • Features   │             │
│  │ • Demand     │  │ • Edges      │  │ • Dataset    │             │
│  │ • Vehicles   │  │ • Dijkstra   │  │ • Baseline   │             │
│  │ • Weather    │  │ • A*         │  │ • RF         │             │
│  │ • Incidents  │  │ • Weights    │  │ • XGBoost    │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                      │
│         ▼                 ▼                 ▼                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    ROUTING MODULE                            │  │
│  │  • Router (multi-algorithm)                                 │  │
│  │  • Route Scorer (configurable weights)                      │  │
│  │  • Dynamic Router (rerouting logic)                         │  │
│  │  • Recommendation (explanation facts)                       │  │
│  └────────────────────────────┬────────────────────────────────┘  │
│                               │                                    │
│         ┌─────────────────────┼─────────────────────┐             │
│         ▼                     ▼                     ▼             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│  │  INCIDENTS   │    │  ANALYTICS   │    │      AI      │        │
│  │   MODULE     │    │   MODULE     │    │   MODULE     │        │
│  │              │    │              │    │              │        │
│  │ • Manager    │    │ • Congestion │    │ • Provider   │        │
│  │ • Impact     │    │ • Statistics │    │ • Local LLM  │        │
│  │ • Propagation│    │ • Metrics    │    │ • Templates  │        │
│  └──────────────┘    └──────────────┘    └──────────────┘        │
│         │                     │                     │              │
│         └─────────────────────┼─────────────────────┘              │
│                               ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                      API LAYER                               │  │
│  │  • REST Endpoints (versioned)                               │  │
│  │  • WebSocket Handlers                                       │  │
│  │  • Request/Response Validation                              │  │
│  └────────────────────────────┬────────────────────────────────┘  │
│                               │                                    │
│                               ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                  FRONTEND (React)                            │  │
│  │  • Map Visualization (MapLibre GL)                          │  │
│  │  • Panels (Traffic, Routing, Predictions, Incidents, AI)    │  │
│  │  • Controls (Simulation, Scenarios, Incidents)              │  │
│  │  • Real-time WebSocket Client                               │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Simulation Tick Loop

```
Timer (1s real = 1min sim)
    │
    ▼
DemandModel.get_base_demand(road_type, hour, is_weekend)
    │
    ▼
TrafficGenerator.generate_vehicles(road, base_demand)
    │
    ▼
VehicleEngine.update_positions()
    │
    ▼
TrafficStateEngine.aggregate(road_id) → TrafficSnapshot
    │
    ▼
CongestionEngine.calculate(snapshot) → congestion_score
    │
    ▼
CongestionPropagation.propagate(congested_roads) → downstream_impacts
    │
    ▼
FeatureEngineering.build_features(snapshot, history, weather, incidents)
    │
    ▼
PredictionService.predict(features) → future_congestion
    │
    ▼
GraphWeightUpdater.update(edges, predicted_congestion)
    │
    ▼
Router.recalculate_if_needed(origin, destination)
    │
    ▼
WebSocket.broadcast(traffic_update, route_update, incident_update)
```

### 2. Route Calculation

```
User selects origin + destination
    │
    ▼
Router.calculate(origin, destination, algorithms=["dijkstra", "astar", "neuro_route"])
    │
    ├── Dijkstra: shortest distance (static weights)
    ├── A*: current fastest (current congestion weights)
    └── NeuroRoute: predicted fastest (predicted congestion weights)
    │
    ▼
RouteScorer.score(routes, weights) → ranked routes
    │
    ▼
RecommendationEngine.select_best(routes) → recommended + explanation_facts
    │
    ▼
AIExplanation.generate(facts) → human-readable explanation
    │
    ▼
Return RouteRecommendationResponse
```

## Database Design

### Core Entities

| Table | Purpose | Key Relationships |
|-------|---------|-------------------|
| `nodes` | Junctions/intersections | Referenced by `roads` |
| `roads` | Directed edges with static properties | `source_node`, `target_node` → `nodes` |
| `simulation_sessions` | Simulation runs | One-to-many with snapshots, incidents, routes |
| `traffic_snapshots` | Aggregated state per road per tick | `session_id` → `simulation_sessions`, `road_id` → `roads` |
| `incidents` | Active incidents | `session_id`, `road_id` |
| `route_calculations` | Computed routes | `session_id`, `origin/destination` → `nodes` |
| `predictions` | ML predictions per road per horizon | `session_id`, `road_id` |
| `scenario_executions` | What-if scenario results | `session_id` |
| `model_registry` | ML model metadata | Independent |
| `system_metrics` | Observability | `session_id` |

### Indexing Strategy

```sql
-- Time-series queries
CREATE INDEX idx_traffic_snapshots_session_road ON traffic_snapshots(session_id, road_id);
CREATE INDEX idx_traffic_snapshots_tick ON traffic_snapshots(tick);

-- Incident lookups
CREATE INDEX idx_incidents_session ON incidents(session_id);
CREATE INDEX idx_incidents_road ON incidents(road_id);

-- Route history
CREATE INDEX idx_routes_session_tick ON route_calculations(session_id, calculation_tick);

-- Predictions
CREATE INDEX idx_predictions_session_road_tick ON predictions(session_id, road_id, prediction_tick);
```

## Concurrency Model

### Backend

- **FastAPI** runs on **uvicorn** with async workers
- **Simulation engine** runs in background task (single-threaded, deterministic)
- **WebSocket manager** handles multiple connections per channel
- **ML inference** uses singleton service with thread-safe predict()
- **Database** uses asyncpg connection pool

### Frontend

- **React Query** manages server state with caching
- **Zustand** for client-only UI state
- **WebSocket** with automatic reconnection and message routing
- **MapLibre GL** runs in WebGL context

## Configuration

All configuration via environment variables (`.env`):

```python
# Core settings in app/core/config.py
class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql://..."
    simulation_seed: int = 42
    prediction_horizons: List[int] = [5, 15, 30, 60]
    routing_weights: RoutingWeights = ...
    llm_provider: str = "template"
```

## Error Handling

| Layer | Strategy |
|-------|----------|
| API | Pydantic validation, HTTPException with structured errors |
| Simulation | Try/catch per tick, log errors, continue |
| ML | Fallback to baseline if model fails |
| WebSocket | Auto-reconnect, message queue during disconnect |
| Frontend | Error boundaries, toast notifications, degraded mode |

## Security

- No secrets in code (`.env` only)
- CORS configured for local development
- SQLAlchemy ORM prevents SQL injection
- Input validation on all API endpoints
- LLM prompts sanitized (structured facts only)
- WebSocket message size limits

## Observability

- Structured logging with `structlog`
- Key metrics in `system_metrics` table
- Health endpoints: `/health`, `/health/ready`, `/health/live`
- WebSocket connection tracking

## Deployment

### Docker Compose (Development)

```yaml
services:
  postgres:     # PostgreSQL 16
  backend:      # FastAPI + uvicorn
  frontend:     # Vite dev server
```

### Production Considerations

- Multi-stage Dockerfiles
- PostgreSQL connection pooling (PgBouncer)
- Redis for WebSocket pub/sub scaling
- Prometheus + Grafana for metrics
- Nginx reverse proxy with SSL
- Model artifacts in S3/MinIO