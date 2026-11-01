# NeuroRoute — AI Traffic Brain

> An AI-powered traffic intelligence and dynamic route optimization platform.

NeuroRoute does not simply ask "Which route is shortest?"  
It asks **"Which route is expected to be fastest and safest given how traffic is likely to evolve?"**

## Overview

NeuroRoute is a complete, locally runnable simulation and optimization platform that demonstrates:

- **Realistic traffic simulation** with temporal demand patterns, congestion propagation, and incident impacts
- **ML-based traffic prediction** using Random Forest and XGBoost models trained on synthetic data
- **Dynamic routing** with Dijkstra, A*, and NeuroRoute algorithms using predicted congestion
- **What-if scenario analysis** for traffic planning and incident response
- **Live dashboard** with real-time WebSocket updates
- **AI explanations** for routing decisions (using local LLM or deterministic templates)

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Traffic         │     │ Feature          │     │ ML Prediction   │
│ Simulation      │────▶│ Engineering      │────▶│ (RF, XGBoost)   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                         │
┌─────────────────┐     ┌──────────────────┐            │
│ Dynamic         │     │ Graph Weight     │            │
│ Routing         │◀───│ Update           │◀───────────┘
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ What-If         │     │ AI Explanation   │
│ Simulation      │     │ (Local LLM)      │
└─────────────────┘     └──────────────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
            ┌─────────────────┐
            │ FastAPI + WS    │
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ React Dashboard │
            └─────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL |
| **ML** | scikit-learn, XGBoost, NumPy, Pandas |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **Map** | MapLibre GL JS (OpenStreetMap) |
| **Charts** | Recharts |
| **Real-time** | WebSockets |
| **Infrastructure** | Docker Compose |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Run with Docker

```bash
# Clone and enter directory
git clone <repo-url>
cd neuro-route

# Copy environment config
cp .env.example .env

# Start all services
docker-compose up -d

# Wait for services to be healthy, then seed database
docker-compose exec backend python scripts/seed_database.py

# Access dashboard
open http://localhost:3000
```

### Run Locally (Development)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Start PostgreSQL (via Docker)
docker run -d --name neuroroute-postgres \
  -e POSTGRES_USER=neuroroute \
  -e POSTGRES_PASSWORD=neuroroute \
  -e POSTGRES_DB=neuro_route \
  -p 5432:5432 \
  postgres:16-alpine

# Seed database
python scripts/seed_database.py

# Start API
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

## Demo Scenarios

The dashboard includes 8 reproducible demo scenarios:

| Scenario | Description |
|----------|-------------|
| **Normal Day** | Low-to-normal traffic, free flow |
| **Morning Rush** | Gradual buildup on major arteries |
| **Major Jam** | Severe bottleneck formation |
| **Accident** | High-severity incident with capacity reduction |
| **Road Closure** | Major road closed, traffic redistributes |
| **Heavy Rain** | Speed/capacity reductions across network |
| **Traffic Surge** | 30% demand increase city-wide |
| **Major Event** | Unusual demand around venue |

Each scenario runs with a fixed seed for reproducibility.

## Core Demo Flow

1. **Start simulation** — Watch traffic evolve in real-time
2. **Select origin/destination** — Click nodes on map
3. **Calculate routes** — See Shortest, Current Fastest, and NeuroRoute predictions
4. **Trigger accident** — Click "Accident" on recommended route
5. **Watch propagation** — Congestion spreads, predictions update
6. **See reroute** — NeuroRoute switches recommendation automatically
7. **Run what-if** — Test "Traffic +30%" scenario from current state

## Project Structure

```
neuro-route/
├── backend/
│   ├── app/
│   │   ├── api/           # REST + WebSocket endpoints
│   │   ├── core/          # Config, logging, dependencies
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── simulation/    # Traffic simulation engine
│   │   ├── graph/         # Road graph + pathfinding
│   │   ├── prediction/    # ML pipeline
│   │   ├── routing/       # Dynamic routing
│   │   ├── incidents/     # Incident management
│   │   ├── analytics/     # Metrics & statistics
│   │   └── ai/            # LLM explanation layer
│   ├── scripts/           # Data generation, training
│   └── tests/             # Unit, integration, E2E tests
├── frontend/
│   └── src/
│       ├── components/    # React components
│       ├── features/      # Feature modules
│       ├── hooks/         # Custom hooks
│       ├── services/      # API + WebSocket
│       └── types/         # TypeScript types
├── data/                  # Generated data, models
├── docs/                  # Documentation
└── docker-compose.yml
```

## API Endpoints

### Traffic
- `GET /api/v1/traffic/current` — Current state of all roads
- `GET /api/v1/traffic/{road_id}` — Single road state
- `GET /api/v1/traffic/summary` — Aggregate statistics

### Routing
- `POST /api/v1/routes/calculate` — Calculate routes
- `GET /api/v1/routes/recommend` — Get recommendation with explanation

### Simulation
- `POST /api/v1/simulation/start` — Start new simulation
- `POST /api/v1/simulation/pause|resume|reset` — Control simulation
- `POST /api/v1/simulation/scenario` — Run what-if scenario

### Predictions
- `GET /api/v1/predictions/{road_id}` — Multi-horizon predictions
- `GET /api/v1/predictions/models` — Model info and metrics

### WebSocket
- `WS /api/v1/ws/traffic` — Real-time traffic updates
- `WS /api/v1/ws/routing` — Route changes
- `WS /api/v1/ws/incidents` — Incident notifications
- `WS /api/v1/ws/simulation` — Clock and status

## ML Pipeline

### Dataset Generation
```bash
# Development dataset (1 day, 50 roads)
python scripts/generate_dataset.py --dev

# Full dataset (7 days, 200 roads)
python scripts/generate_dataset.py --days 7 --roads 200
```

### Model Training
```bash
# Train baseline, Random Forest, XGBoost
python scripts/train_model.py --data traffic_dataset.parquet

# Compare models
python scripts/train_model.py --compare
```

### Features
- Temporal: hour, day_of_week, is_rush_hour, minutes_since_midnight
- Road static: distance, speed_limit, capacity, road_type
- Traffic state: vehicle_count, avg_speed, density, occupancy, congestion
- Historical: rolling averages, lag features
- Spatial: upstream/downstream congestion
- Weather: temperature, rain, visibility
- Incidents: count, severity, capacity reduction

### Targets
- `congestion_5m`, `congestion_15m`, `congestion_30m`, `congestion_60m`

## Configuration

Key environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATION_SEED` | 42 | Random seed for reproducibility |
| `SIMULATION_TICK_INTERVAL_SEC` | 1.0 | Real seconds per simulation tick |
| `PREDICTION_HORIZONS` | 5,15,30,60 | Prediction horizons in minutes |
| `ROUTING_WEIGHTS_*` | Various | Cost function weights |
| `LLM_PROVIDER` | template | template\|local\|none |
| `LLM_LOCAL_URL` | http://localhost:11434 | Ollama/vLLM endpoint |

## Testing

```bash
# Backend tests
cd backend
pytest tests/ -v --cov=app

# Frontend tests
cd frontend
npm test

# E2E tests
cd frontend
npx playwright test
```

### Critical Regression Test

The core test validates the complete demo flow:

```python
def test_regression_accident_reroute():
    # 1. Start simulation
    # 2. Select origin A -> destination B
    # 3. Calculate routes (Shortest, Current, NeuroRoute)
    # 4. Inject accident on recommended route
    # 5. Run simulation ticks
    # 6. Verify congestion increases
    # 7. Verify alternate route considered
    # 8. Verify recommendation changes
    # 9. Verify frontend receives WebSocket updates
```

## Development

### Adding a New ML Model

1. Implement in `backend/app/prediction/{model_name}.py`
2. Add to `backend/app/prediction/inference.py` model registry
3. Update training script `scripts/train_model.py`
4. Document in `docs/ml.md`

### Adding a New Incident Type

1. Add to `IncidentType` enum in `backend/app/schemas/incident.py`
2. Update `IncidentManager` in `backend/app/incidents/manager.py`
3. Add impact logic in `backend/app/incidents/impact.py`
4. Add UI button in `frontend/src/components/panels/IncidentPanel.tsx`

### Extending the Graph

The road graph is in `backend/app/graph/`. To add new algorithms:

1. Implement in new file under `backend/app/graph/`
2. Add to routing service in `backend/app/routing/router.py`
3. Expose via API in `backend/app/api/routes/routing.py`

## Documentation

- [Architecture](docs/architecture.md)
- [API Reference](docs/api.md)
- [Algorithms](docs/algorithms.md)
- [ML Pipeline](docs/ml.md)
- [Simulation](docs/simulation.md)
- [Demo Guide](docs/demo.md)

## Performance Targets

| Metric | Target |
|--------|--------|
| Simulation tick | < 50ms |
| Route calculation | < 100ms |
| Prediction inference | < 50ms |
| WebSocket latency | < 500ms |
| Map render (60fps) | < 16ms/frame |

## License

MIT License — See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run full test suite
5. Submit PR with description

## Acknowledgments

- OpenStreetMap for map tiles
- MapLibre GL for map rendering
- scikit-learn/XGBoost for ML
- FastAPI for the backend framework