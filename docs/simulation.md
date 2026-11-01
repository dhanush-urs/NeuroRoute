# Traffic Simulation Engine

## Overview

The simulation engine is the **heart of NeuroRoute** — it generates realistic, deterministic traffic patterns that drive the entire system. Every component (ML, routing, incidents, dashboard) consumes simulation output.

## Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    SIMULATION ENGINE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐            │
│  │  DEMAND     │   │  TRAFFIC    │   │  VEHICLE    │            │
│  │  MODEL      │──▶│  GENERATOR  │──▶│  ENGINE     │            │
│  │             │   │             │   │             │            │
│  │ • Temporal  │   │ • Vehicles  │   │ • Positions │            │
│  │ • Road Type │   │ • Speeds    │   │ • States    │            │
│  │ • Weather   │   │ • Densities │   │ • Sampling  │            │
│  └─────────────┘   └──────┬──────┘   └─────────────┘            │
│                           │                                       │
│                           ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              TRAFFIC STATE ENGINE                        │     │
│  │  • Aggregate per road                                    │     │
│  │  • Congestion calculation                                │     │
│  │  • Congestion propagation                                │     │
│  │  • Snapshot persistence                                  │     │
│  └─────────────────────────────────────────────────────────┘     │
│                           │                                       │
│                           ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              INCIDENT SIMULATOR                          │     │
│  │  • Random incidents (configurable rate)                  │     │
│  │  • Manual incidents (demo control)                       │     │
│  │  • Impact calculation                                    │     │
│  └─────────────────────────────────────────────────────────┘     │
│                           │                                       │
│                           ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              WEATHER SIMULATOR                           │     │
│  │  • Seasonal patterns                                     │     │
│  │  • Dynamic conditions                                    │     │
│  │  • Speed/capacity modifiers                              │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Simulation Clock

### Time Mapping

```
1 real second = 1 simulated minute (configurable)

Speed multipliers:
├── 1x   : 1 real sec = 1 sim min  = 1,440× real-time
├── 5x   : 1 real sec = 5 sim min  = 7,200× real-time
├── 10x  : 1 real sec = 10 sim min = 14,400× real-time
├── 30x  : 1 real sec = 30 sim min = 43,200× real-time
└── 60x  : 1 real sec = 60 sim min = 86,400× real-time (1 day/sec)
```

### Clock State

```python
class SimulationClock:
    tick: int = 0                    # Monotonically increasing
    simulation_time: datetime        # Wall-clock equivalent
    speed_multiplier: int = 1        # 1, 5, 10, 30, 60
    tick_interval_sec: float = 1.0   # Real seconds between ticks
    is_running: bool = False
```

### Time-Driven Patterns

The clock drives:
- **Demand patterns** (rush hours, night, weekends)
- **Weather transitions** (seasonal, daily)
- **Incident durations** (start_tick, end_tick)
- **Prediction horizons** (relative to current tick)

---

## Demand Model

### Base Demand by Road Type

```python
BASE_DEMAND = {
    'highway': {
        0: 100,  6: 400,   7: 1200,  9: 800,
        12: 800, 16: 1000, 17: 1500, 19: 900,
        20: 600, 22: 200,  23: 150
    },
    'major': {
        0: 50,   6: 200,  7: 800,   9: 400,
        12: 350, 16: 500,  17: 850,  19: 400,
        20: 250, 22: 100,  23: 60
    },
    'minor': {
        0: 20,   6: 80,   7: 300,   9: 150,
        12: 140, 16: 200,  17: 350,  19: 160,
        20: 100, 22: 35,   23: 20
    },
    'local': {
        0: 5,    6: 20,   7: 80,    9: 40,
        12: 35,  16: 60,  17: 100,  19: 40,
        20: 25,  22: 10,  23: 5
    }
}
```

### Weekend Adjustment

```python
def get_base_demand(road_type: str, hour: int, is_weekend: bool) -> float:
    base = interpolate(BASE_DEMAND[road_type], hour)
    
    if is_weekend:
        if 7 <= hour <= 9:      # Morning rush reduced
            base *= 0.4
        elif 10 <= hour <= 18:  # Midday increased
            base *= 1.15
        elif 19 <= hour <= 22:  # Evening extended
            base *= 1.2
    
    return base
```

### Demand Noise

```python
vehicles = int(base_demand * random.uniform(0.8, 1.2))
```

---

## Vehicle Simulation

### Aggregate Flow (Backend)

**Why not individual vehicles?** 
- 200 roads × 1000+ vehicles = 200K+ objects per tick
- Simulation would be too slow
- Frontend only needs visual representation

**Approach**: Simulate **aggregate flows** per road, render **sampled vehicles** (max 200) on frontend.

```python
class VehicleEngine:
    def update_flows(self, roads: List[Road], tick: int):
        for road in roads:
            # Flow conservation: inflow = outflow + accumulation
            inflow = self.calculate_inflow(road)
            outflow = self.calculate_outflow(road)
            
            road.vehicle_count = max(0, road.vehicle_count + inflow - outflow)
            
            # Speed from congestion
            road.avg_speed = self.calculate_speed(road)
```

### Vehicle States (Frontend Visualization)

| State | Description | Visual |
|-------|-------------|--------|
| `MOVING` | Normal flow | Green arrow |
| `SLOWING` | Approaching congestion | Yellow arrow |
| `STOPPED` | Queue/stopped | Red square |
| `REROUTING` | Calculating new path | Blue curved arrow |
| `ARRIVED` | At destination | Disappears |

### Position Interpolation

```python
def interpolate_position(vehicle, tick_progress: float) -> (lat, lon):
    """tick_progress ∈ [0, 1] within current edge"""
    source = vehicle.current_edge.source_node
    target = vehicle.current_edge.target_node
    
    lat = source.lat + (target.lat - source.lat) * tick_progress
    lon = source.lon + (target.lon - source.lon) * tick_progress
    return lat, lon
```

---

## Congestion Model

### Calculation

```python
def calculate_congestion(road: Road, vehicles: int, avg_speed: float) -> float:
    """Returns congestion score 0.0–1.0"""
    
    # Density-based (veh/km)
    density = vehicles / max(road.distance_km, 0.1)
    jam_density = road.capacity_vph / (road.speed_limit_kmh / 3.6)
    density_ratio = density / max(jam_density, 1)
    
    # Speed-based (ratio to free flow)
    speed_ratio = avg_speed / max(road.speed_limit_kmh, 1)
    
    # Weighted combination
    congestion = 0.6 * density_ratio + 0.4 * (1.0 - speed_ratio)
    
    return clamp(congestion, 0.0, 1.0)
```

### Classification Thresholds

| Score Range | Level | Color |
|-------------|-------|-------|
| 0.00–0.30 | FREE | 🟢 #22c55e |
| 0.30–0.50 | MODERATE | 🟡 #eab308 |
| 0.50–0.70 | HEAVY | 🟠 #f97316 |
| 0.70–0.90 | CONGESTED | 🔴 #ef4444 |
| 0.90–1.00 | SEVERE | 🟤 #991b1b |
| N/A (closed) | CLOSED | ⚫ #374151 |

---

## Congestion Propagation

### Algorithm

```python
def propagate_congestion(graph: RoadGraph, congested_roads: Set[str]) -> Dict[str, float]:
    """Calculate downstream impact of upstream congestion"""
    impacts = defaultdict(float)
    
    for road_id in congested_roads:
        road = graph.get_road(road_id)
        
        # Throughput loss = capacity × congestion × factor
        throughput_loss = road.capacity_vph * road.congestion_score * 0.7
        
        # Find downstream roads
        downstream = graph.get_downstream_roads(road_id)
        
        for ds_road in downstream:
            # Equal split (simplified turning model)
            share = throughput_loss / len(downstream)
            
            # 30% propagates downstream (dampening)
            impacts[ds_road.id] += share * 0.3
    
    return impacts
```

### Application

```python
def apply_propagation(roads, impacts):
    for road_id, additional_vehicles in impacts.items():
        road = roads[road_id]
        # Add to existing vehicles (capped at capacity)
        road.vehicle_count = min(
            road.capacity_vph * 1.5,  # Allow temporary oversaturation
            road.vehicle_count + additional_vehicles
        )
```

---

## Incident System

### Incident Types

| Type | Capacity Reduction | Duration | Severity |
|------|-------------------|----------|----------|
| ACCIDENT | 50–80% | 15–60 min | 0.6–0.9 |
| ROAD_CLOSURE | 100% | 30–180 min | 1.0 |
| ROAD_WORK | 20–60% | 60–480 min | 0.3–0.6 |
| FLOOD | 70–100% | 120–1440 min | 0.7–1.0 |
| HEAVY_RAIN | 15–30% | 30–240 min | 0.3–0.5 |
| SPECIAL_EVENT | 20–50% | 60–300 min | 0.4–0.7 |

### Incident Impact

```python
def calculate_impact(incident: Incident, road: Road) -> IncidentImpact:
    # Direct capacity reduction
    capacity_reduction = incident.capacity_reduction_pct
    
    # Speed reduction
    speed_reduction = capacity_reduction * 0.8
    
    # Downstream propagation
    downstream_impact = propagate_from_incident(incident, road)
    
    return IncidentImpact(
        capacity_reduction_pct=capacity_reduction,
        speed_reduction_pct=speed_reduction,
        downstream_impacts=downstream_impact,
        estimated_duration_ticks=incident.expected_duration
    )
```

### Random Incidents (Configurable)

```python
INCIDENT_RATE_PER_HOUR = {
    'accident': 0.02,      # 2% chance per hour per road
    'road_work': 0.005,    # 0.5% chance
    'heavy_rain': 0.01,    # Weather-driven
}
```

---

## Weather Model

### Seasonal Patterns

```python
SEASONAL_WEATHER = {
    'winter': {   # Dec-Feb
        'weights': [0.30, 0.30, 0.20, 0.15, 0.05],
        'temp_range': (-5, 10)
    },
    'spring': {   # Mar-May
        'weights': [0.45, 0.25, 0.18, 0.09, 0.03],
        'temp_range': (8, 22)
    },
    'summer': {   # Jun-Aug
        'weights': [0.60, 0.20, 0.10, 0.07, 0.03],
        'temp_range': (18, 32)
    },
    'fall': {     # Sep-Nov
        'weights': [0.45, 0.25, 0.18, 0.09, 0.03],
        'temp_range': (8, 22)
    }
}
```

### Weather Effects on Traffic

| Condition | Speed Factor | Capacity Factor | Visibility |
|-----------|--------------|-----------------|------------|
| CLEAR | 1.00 | 1.00 | 20 km |
| CLOUDY | 0.98 | 1.00 | 15 km |
| LIGHT_RAIN | 0.85 | 0.90 | 8 km |
| HEAVY_RAIN | 0.70 | 0.75 | 3 km |
| FOG | 0.75 | 0.85 | 1 km |

---

## Simulation Tick Loop

```python
async def simulation_loop(self):
    while self.is_running:
        tick_start = time.time()
        
        # 1. Advance clock
        self.current_tick += 1
        self.simulation_time += timedelta(minutes=1)
        
        # 2. Update demand
        self.demand_model.update(self.simulation_time)
        
        # 3. Generate traffic
        self.traffic_generator.generate(self.roads, self.demand_model)
        
        # 3. Update vehicle positions
        self.vehicle_engine.update(self.roads)
        
        # 4. Calculate congestion
        self.congestion_engine.calculate(self.roads)
        
        # 5. Propagate congestion
        impacts = self.congestion_engine.propagate(self.roads)
        self.apply_propagation(impacts)
        
        # 6. Update incidents
        self.incident_simulator.update(self.roads, self.current_tick)
        
        # 7. Update weather
        self.weather_simulator.update(self.simulation_time)
        
        # 8. Persist snapshot
        self.snapshot_writer.write(self.roads, self.current_tick)
        
        # 9. Generate predictions
        self.prediction_service.predict(self.roads, self.current_tick)
        
        # 10. Check rerouting
        self.router.check_reroute(self.current_tick)
        
        # 11. Broadcast WebSocket updates
        self.websocket_manager.broadcast_updates()
        
        # 12. Sleep to maintain tick rate
        elapsed = time.time() - tick_start
        sleep_time = max(0, self.tick_interval_sec / self.speed_multiplier - elapsed)
        await asyncio.sleep(sleep_time)
```

---

## Deterministic Reproducibility

### Seed-Based Generation

```python
def create_simulation(seed: int = 42) -> SimulationEngine:
    """Same seed = same simulation"""
    return SimulationEngine(
        seed=seed,
        demand_model=DemandModel(seed=seed),
        traffic_generator=TrafficGenerator(seed=seed),
        vehicle_engine=VehicleEngine(seed=seed),
        incident_simulator=IncidentSimulator(seed=seed),
        weather_simulator=WeatherSimulator(seed=seed),
    )
```

### What's Deterministic

| Component | Deterministic? | Notes |
|-----------|----------------|-------|
| Road network | ✅ | Fixed grid + seed |
| Demand patterns | ✅ | Fixed formulas + seed |
| Vehicle counts | ✅ | Seeded RNG |
| Incident occurrence | ✅ | Seeded RNG |
| Weather | ✅ | Seeded RNG |
| ML predictions | ✅ | Fixed model + features |

### What's NOT Deterministic

- WebSocket timing (network dependent)
- Frontend rendering (browser dependent)
- Exact vehicle positions (sampled for visualization)

---

## Scenario System

### Predefined Scenarios

| Scenario | Seed | Modifications |
|----------|------|---------------|
| Normal Day | 42 | Base config |
| Morning Rush | 123 | Start at 07:00, high demand |
| Major Jam | 456 | Bottleneck on R100 |
| Accident | 789 | Accident on main artery |
| Road Closure | 101 | Close highway |
| Heavy Rain | 202 | Rain condition |
| Traffic Surge | 303 | 1.3× demand multiplier |
| Major Event | 404 | Event zone demand spike |

### What-If Execution

```python
async def run_scenario(base_session_id: str, scenario: Scenario) -> ScenarioResult:
    # 1. Clone base simulation state at tick T
    base_state = await snapshot_reader.get_state(base_session_id, scenario.base_tick)
    
    # 2. Apply modifications
    modified_state = scenario.apply(base_state)
    
    # 3. Run simulation forward (headless)
    scenario_engine = SimulationEngine.from_state(modified_state)
    for _ in range(scenario.horizon_ticks):
        scenario_engine.tick()
    
    # 4. Compare results
    comparison = compare_scenarios(base_state, scenario_engine.get_state())
    
    return ScenarioResult(
        scenario_name=scenario.name,
        base_tick=scenario.base_tick,
        modifications=scenario.modifications,
        results=comparison
    )
```

---

## Performance Optimization

### Target Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Tick duration | < 50ms | ~38ms |
| Memory/road | < 10 KB | ~8 KB |
| Snapshot write | < 5ms | ~3ms |
| Prediction batch | < 50ms | ~24ms |

### Optimizations

1. **Vectorized operations** — NumPy for batch calculations
2. **Object pooling** — Reuse vehicle/road objects
3. **Lazy evaluation** — Only compute what's needed
4. **Batch DB writes** — Accumulate snapshots, flush per 10 ticks
5. **WebSocket throttling** — Max 1 update/500ms per client