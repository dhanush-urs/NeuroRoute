# NeuroRoute Demo Guide

## Quick Demo (5 minutes)

### Prerequisites

```bash
# 1. Start services
docker-compose up -d

# 2. Wait for health checks
docker-compose ps
# All services should show "healthy"

# 3. Seed database
docker-compose exec backend python scripts/seed_database.py

# 4. Open dashboard
open http://localhost:3000
```

### Core Demo Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEUROROUTE DEMO                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. START SIMULATION                                            │
│     → Click "▶ Start" (top right)                               │
│     → Watch clock: SIM 00:00 AM → 08:27 AM (MORNING RUSH)      │
│     → Roads change color: green → yellow → orange → red        │
│                                                                  │
│  2. SELECT ROUTE                                                │
│     → Click origin node (green marker appears)                  │
│     → Click destination node (red marker appears)               │
│     → Panel shows: "Calculate Routes" button                    │
│                                                                  │
│  3. VIEW RECOMMENDATION                                         │
│     → Click "Calculate Routes"                                  │
│     → Three routes appear:                                      │
│       • Shortest (7.8 km, 19→31 min, HIGH risk)                │
│       • Current Fastest (8.2 km, 18→22 min, MEDIUM)            │
│       • ★ NeuroRoute (9.2 km, 22→23 min, LOW risk) ★           │
│     → Blue line = recommended route                             │
│     → Gray lines = alternatives                                 │
│                                                                  │
│  4. TRIGGER ACCIDENT                                            │
│     → In Incident panel, click "🚗 Accident"                    │
│     → Click on recommended route (blue line)                    │
│     → Accident icon appears, road turns SEVERE (dark red)      │
│                                                                  │
│  5. WATCH PROPAGATION                                           │
│     → Downstream roads turn HEAVY/CONGESTED                     │
│     → Prediction chart shows congestion rising                  │
│     → NeuroRoute recalculates...                                │
│                                                                  │
│  6. SEE REROUTE                                                 │
│     → Route switches from Route A to Route B                    │
│     → WebSocket pushes update instantly                         │
│     → AI Insight explains: "Route A predicted 31 min,           │
│        Route B stable at 23 min"                                │
│                                                                  │
│  7. RUN WHAT-IF                                                 │
│     → Click "Traffic +30%" in Scenario panel                    │
│     → Comparison shows:                                         │
│       • 15 more roads congested                                 │
│       • Average ETA +8 min                                      │
│       • New optimal route highlighted                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Detailed Scenario Walkthroughs

### Scenario 1: Normal Day
**Seed**: 42 | **Time**: 10:00 AM
- Free flow on most roads
- Light congestion on minor roads
- All routes similar ETA
- **Expected**: NeuroRoute picks shortest (no prediction advantage)

### Scenario 2: Morning Rush Hour
**Seed**: 123 | **Time**: 07:30 → 09:00
- Start simulation at 07:00
- Watch highways go FREE → MODERATE → HEAVY
- Major arterials bottleneck first
- **Expected**: NeuroRoute avoids highways early, uses arterials

### Scenario 3: Major Traffic Jam
**Seed**: 456 | **Time**: 08:15
- Pre-configured bottleneck on R100 (highway)
- 90% capacity reduction
- **Trigger**: Accident on R100 at tick 15
- **Watch**: Congestion propagates R100 → R101 → R105 → R106
- **Expected**: Route switches from highway to parallel arterial

### Scenario 4: Accident
**Seed**: 789 | **Time**: 08:30
1. Calculate route A→B (uses highway R102)
2. Trigger **Accident** on R102 (70% capacity loss)
3. **Immediate**: R102 turns SEVERE
4. **30 sec later**: R101, R103 turn HEAVY (propagation)
5. **Prediction**: R102 congestion 0.35 → 0.85 in 15 min
6. **Reroute**: NeuroRoute switches to arterial Route B
7. **AI Insight**: "Accident on R102 reduces capacity 70%. Route A ETA increases from 19 to 31 min. Route B remains 23 min."

### Scenario 5: Road Closure
**Seed**: 101 | **Time**: 14:00
1. Normal traffic
2. Trigger **Road Closure** on R200 (major arterial)
3. **Immediate**: R200 turns CLOSED (dashed gray)
4. Traffic redistributes to R199, R201, R205
5. **Watch**: Secondary roads go MODERATE → HEAVY
6. **Expected**: Multiple reroutes as system finds new equilibrium

### Scenario 6: Heavy Rain
**Seed**: 202 | **Time**: 16:00
1. Trigger **Heavy Rain**
2. **Global effects**:
   - All speeds ×0.70
   - All capacities ×0.75
   - Visibility reduced
3. **Prediction**: Congestion rises city-wide
4. **Routing**: Longer routes become relatively better (less speed penalty)
5. **AI Insight**: "Heavy rain reduces speeds 30% city-wide. Route A (highway) now 28 min vs Route B (arterial) 25 min. Arterial recommended."

### Scenario 7: 30% Traffic Surge
**Seed**: 303 | **Time**: 12:00
1. Normal midday traffic
2. Trigger **Traffic +30%** (demand multiplier)
3. **Watch**: Free roads → MODERATE, Moderate → HEAVY
4. **Bottlenecks form** at intersections
5. **What-if**: Run "Traffic +30%" scenario from current state
6. **Comparison**: 22 more roads congested, avg ETA +6 min

### Scenario 8: Major Event
**Seed**: 404 | **Time**: 19:00
- Event zone: nodes N0707, N0708, N0807, N0808 (stadium area)
- 5× demand multiplier in zone
- **Watch**: Radial roads from event zone congest
- **Routing**: Avoid event zone, use ring roads
- **AI Insight**: "Event at Stadium generates 5× demand. Radial roads R301-R308 congested. Ring road R400 remains clear. Recommended: Use ring road bypass."

---

## Manual Controls Reference

### Simulation Control (Top Bar)

| Control | Action |
|---------|--------|
| ▶ Start / ⏸ Pause | Start/stop simulation loop |
| ↻ Reset | Full reset (seed, tick, state) |
| Speed: 1x/5x/10x/30x | Simulation speed multiplier |

### Incident Controls (Incident Panel)

| Button | Effect |
|--------|--------|
| 🚗 Accident | Random road, 50-80% capacity loss |
| 🚫 Road Closure | Random road, 100% capacity loss |
| 🚧 Road Work | Random road, 20-60% capacity loss |
| 🌧️ Heavy Rain | Global weather change |
| 🎪 Event | Demand spike in zone |

### Scenario Selector

| Scenario | Description |
|----------|-------------|
| Normal Day | Baseline free flow |
| Morning Rush | Rush hour buildup |
| Major Jam | Pre-configured bottleneck |
| Accident | Inject accident on route |
| Road Closure | Close major road |
| Heavy Rain | Weather degradation |
| Traffic +30% | Demand surge |
| Major Event | Stadium event |

### Route Planner (Sidebar)

| Element | Description |
|---------|-------------|
| Origin | Green marker, click on map |
| Destination | Red marker, click on map |
| Calculate Routes | Computes 3 algorithms |
| Clear | Reset selection |

---

## Dashboard Panels Explained

### 1. Traffic Map (Main)
- **Roads**: Color-coded by congestion level
- **Nodes**: Blue circles (clickable)
- **Vehicles**: Animated arrows (sampled 200 max)
- **Incidents**: Icons with severity
- **Routes**: Blue (recommended), Gray (alternatives)
- **Origin/Dest**: Green/Red markers

### 2. Traffic Status Panel (Sidebar)
- Total vehicles, avg speed, congestion distribution
- Bar chart: FREE/MODERATE/HEAVY/CONGESTED/SEVERE percentages

### 3. Route Planner (Sidebar)
- Origin/Destination selection
- Route comparison table (distance, current ETA, predicted ETA, risk)
- ★ = Recommended route

### 4. Prediction Panel (Sidebar)
- Line chart: Current + 5/15/30 min predictions
- Model info: name, version, confidence, MAE

### 5. Incident Panel (Sidebar)
- Active incidents list with severity
- Manual trigger buttons

### 6. AI Insights Panel (Sidebar)
- Natural language explanations
- Generated from structured facts
- Fallback: template-based if LLM unavailable

### 7. System Metrics (Sidebar)
- Tick duration, prediction latency, routing latency
- WebSocket clients, memory, uptime
- Live log stream

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Start/Pause simulation |
| `R` | Reset simulation |
| `1-8` | Load scenario 1-8 |
| `A` | Trigger accident on selected route |
| `C` | Clear route selection |
| `+/-` | Increase/decrease speed |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Map not loading | Check internet (OSM tiles), or VITE_MAP_STYLE_URL |
| WebSocket disconnected | Check backend logs, restart backend |
| No traffic updates | Verify simulation is running (▶) |
| Routes not calculating | Select origin AND destination |
| Predictions not showing | Wait for ML model to load (check logs) |
| Slow performance | Reduce SIMULATION_MAX_VEHICLES_VISIBLE |

---

## Demo Script (For Recording)

```markdown
# NeuroRoute Demo Script (3 min)

## 0:00 - Intro
"NeuroRoute predicts traffic evolution, not just current state."

## 0:15 - Start Simulation
- Click Start
- "Watch: 1 real second = 1 simulated minute"
- "Morning rush building on highways"

## 0:45 - Select Route
- Click origin (downtown)
- Click destination (airport)
- "Three algorithms: Shortest, Current Fastest, NeuroRoute"

## 1:15 - Show Recommendation
- "NeuroRoute picks 9.2 km route over 7.8 km"
- "Why? Predicted congestion on shorter route"

## 1:45 - Trigger Accident
- "Now: accident on recommended route"
- Click Accident on blue route
- "Road capacity -70%"

## 2:15 - Watch Reroute
- "Congestion propagates downstream"
- "Prediction updates: 31 min → 12 min alternative"
- "Route switches automatically"

## 2:45 - What-If
- "What if traffic surges 30%?"
- Click Traffic +30%
- "Comparison shows new optimal route"

## 3:00 - Close
"All running locally. Real ML. Real algorithms. Real-time."
```

---

## API Demo (curl)

```bash
# Start simulation
curl -X POST http://localhost:8000/api/v1/simulation/start \
  -H "Content-Type: application/json" \
  -d '{"seed": 42, "speed_multiplier": 5}'

# Calculate route
curl -X POST http://localhost:8000/api/v1/routes/calculate \
  -H "Content-Type: application/json" \
  -d '{"origin_node": "N0101", "destination_node": "N1414", "algorithm": "neuro_route"}'

# Trigger accident
curl -X POST http://localhost:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{"incident_type": "accident", "road_id": "R0102", "severity": 0.8}'

# Run what-if
curl -X POST http://localhost:8000/api/v1/simulation/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario_name": "traffic_surge", "modifications": {"traffic_multiplier": 1.3}}'

# WebSocket (using wscat)
wscat -c ws://localhost:8000/api/v1/ws/traffic
```

---

## Expected Outputs

### Route Recommendation Response
```json
{
  "recommended_route": {
    "id": "route-123",
    "distance_km": 9.2,
    "current_eta_sec": 1320,
    "predicted_eta_sec": 1380,
    "congestion_risk": "LOW",
    "score": 87.5,
    "is_recommended": true
  },
  "alternative_routes": [...],
  "explanation": "Route B (9.2 km) is recommended over Route A (7.8 km). Although Route A is shorter, predicted congestion on R102-R105 will increase travel time from 19 min to 31 min over the next 15 minutes. Route B maintains a stable 23 min ETA.",
  "facts": {
    "incident": {"type": "accident", "road": "R102", "capacity_reduction": 70},
    "prediction_confidence": 0.91
  }
}
```

### WebSocket Message
```json
{
  "type": "traffic_update",
  "timestamp": "2026-01-15T08:27:00Z",
  "data": {
    "tick": 507,
    "sim_time": "08:27 AM",
    "roads": [
      {"road_id": "R102", "congestion_score": 0.82, "congestion_level": "severe"},
      {"road_id": "R103", "congestion_score": 0.55, "congestion_level": "heavy"}
    ]
  }
}
```

---

## Performance Benchmarks (Demo Machine)

| Metric | Target | Typical |
|--------|--------|---------|
| Simulation tick | < 50ms | 38ms |
| Route calc (A*) | < 100ms | 4ms |
| ML prediction | < 50ms | 24ms |
| WS broadcast | < 100ms | 12ms |
| Map render | 60 fps | 58 fps |
| Memory | < 500 MB | 380 MB |