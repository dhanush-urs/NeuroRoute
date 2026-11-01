from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import uuid

from app.core.dependencies import get_db
from app.state import get_simulation_engine
from app.api.websocket import get_websocket_manager
from app.auth import require_operator, optional_auth


router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationStartRequest(BaseModel):
    seed: Optional[int] = None
    scenario_name: Optional[str] = None
    speed_multiplier: int = 1
    config: Optional[Dict[str, Any]] = None


class SimulationControlRequest(BaseModel):
    action: str  # start, pause, resume, reset, speed
    speed_multiplier: Optional[int] = None
    seed: Optional[int] = None


class SimulationStatusResponse(BaseModel):
    session_id: Optional[str]
    seed: int
    current_tick: int
    simulation_time: str
    speed_multiplier: int
    status: str
    is_running: bool
    demand_multiplier: Optional[float] = 1.0
    weather: Optional[str] = "clear"
    weather_locked: Optional[bool] = False
    active_incidents: Optional[int] = 0


class ScenarioRequest(BaseModel):
    scenario_name: str
    modifications: Dict[str, Any] = {}


class ScenarioResponse(BaseModel):
    scenario_name: str
    base_tick: int
    modifications: Dict[str, Any]
    results: Optional[Dict[str, Any]] = None
    status: str


class WhatIfScenarioRequest(BaseModel):
    scenario_type: str = Field(..., description="Type of scenario: accident, road_closure, weather, traffic_surge, event")
    scenario_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the scenario")
    steps: int = Field(default=60, ge=1, le=500, description="Number of simulation ticks to advance")


class WhatIfScenarioResponse(BaseModel):
    scenario_type: str
    scenario_params: Dict[str, Any]
    steps_simulated: int
    baseline: Dict[str, Any]
    scenario: Dict[str, Any]
    comparison: Dict[str, Any]
    simulation_time: str
    ticks_advanced: int


class WhatIfComparisonRequest(BaseModel):
    scenario_type: str = Field(..., description="Type of scenario: accident, road_closure, weather, traffic_surge, event")
    scenario_params: Dict[str, Any] = Field(default_factory=dict)
    steps: int = Field(default=60, ge=1, le=500)
    baseline_tick: Optional[int] = None


@router.post("/test-broadcast")
async def test_broadcast(db: AsyncSession = Depends(get_db), _: str = Depends(require_operator)):
    """Test WebSocket broadcast."""
    ws_manager = get_websocket_manager()
    await ws_manager.broadcast("traffic", {
        "type": "traffic_update",
        "timestamp": "2024-01-01T00:00:00Z",
        "data": [{"road_id": "test", "vehicle_count": 100, "congestion_score": 0.5}]
    })
    await ws_manager.broadcast("simulation", {
        "type": "simulation_tick",
        "timestamp": "2024-01-01T00:00:00Z",
        "data": {"tick": 1, "sim_time": "2024-01-01T00:00:00", "speed_multiplier": 1, "status": "running"}
    })
    return {"message": "Broadcast test sent"}


@router.post("/start")
async def start_simulation(
    request: SimulationStartRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_operator)
):
    """Start a new simulation."""
    engine = get_simulation_engine()
    
    if engine.state.is_running:
        return {"message": "Simulation already running", "status": engine.state.status}
    
    seed = request.seed
    config = engine.config
    if seed is not None:
        config.seed = seed
    config.speed_multiplier = max(1, min(60, request.speed_multiplier))
    if request.config:
        config.__dict__.update(request.config)
    
    session_id = str(uuid.uuid4())
    await engine.start(session_id=session_id)
    
    # Persist session to database
    from app.models.simulation import SimulationSession
    from sqlalchemy import text
    
    session = SimulationSession(
        id=session_id,
        seed=config.seed,
        scenario_name=request.scenario_name,
        speed_multiplier=config.speed_multiplier,
        config=config.__dict__,
        status="running"
    )
    db.add(session)
    await db.commit()
    
    return {
        "message": "Simulation started",
        "session_id": session_id,
        "seed": config.seed,
        "speed_multiplier": config.speed_multiplier
    }


@router.post("/pause")
async def pause_simulation(db: AsyncSession = Depends(get_db), _: str = Depends(require_operator)):
    """Pause the simulation."""
    engine = get_simulation_engine()
    await engine.pause()
    return {"message": "Simulation paused", "status": engine.state.status}


@router.post("/resume")
async def resume_simulation(db: AsyncSession = Depends(get_db), _: str = Depends(require_operator)):
    """Resume the simulation."""
    engine = get_simulation_engine()
    await engine.resume()
    return {"message": "Simulation resumed", "status": engine.state.status}


@router.post("/reset")
async def reset_simulation(
    seed: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_operator)
):
    """Reset the simulation."""
    engine = get_simulation_engine()
    await engine.reset(seed=seed)
    return {"message": "Simulation reset", "status": engine.state.status}


@router.post("/control")
async def control_simulation(
    request: SimulationControlRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_operator)
):
    """Control simulation (start, pause, resume, reset, speed)."""
    engine = get_simulation_engine()
    
    if request.action == "pause":
        await engine.pause()
    elif request.action == "resume":
        await engine.resume()
    elif request.action == "reset":
        await engine.reset(seed=request.seed)
    elif request.action == "speed":
        if request.speed_multiplier is None:
            raise HTTPException(status_code=400, detail="speed_multiplier required")
        await engine.set_speed(request.speed_multiplier)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")
    
    return {"message": f"Action {request.action} executed", "status": engine.state.status}


@router.get("/status", response_model=SimulationStatusResponse)
async def get_simulation_status():
    """Get current simulation status."""
    engine = get_simulation_engine()
    return engine.get_status()


class SpeedMultiplierRequest(BaseModel):
    speed_multiplier: Optional[int] = None


@router.post("/speed")
async def set_simulation_speed(
    speed_multiplier: Optional[int] = Query(None),
    body: Optional[SpeedMultiplierRequest] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_operator)
):
    """Set simulation speed multiplier (1-60)."""
    val = speed_multiplier if speed_multiplier is not None else (body.speed_multiplier if body and body.speed_multiplier is not None else 1)
    engine = get_simulation_engine()
    multiplier = max(1, min(60, val))
    await engine.set_speed(multiplier)
    return {"message": f"Speed set to {multiplier}x", "speed_multiplier": multiplier}


# Predefined scenario modifications
SCENARIO_MODIFICATIONS = {
    "normal": {
        "traffic_multiplier": 1.0,
        "weather": "clear",
    },
    "rush_hour": {
        "traffic_multiplier": 1.8,
        "weather": "clear",
    },
    "major_jam": {
        "traffic_multiplier": 2.2,
        "weather": "clear",
        "incidents": [
            {"type": "accident", "severity": 0.9, "road_type": "highway"},
            {"type": "road_work", "severity": 0.75, "road_type": "highway_bottleneck"},
        ],
    },
    "accident": {
        "traffic_multiplier": 1.0,
        "weather": "clear",
        "incidents": [
            {"type": "accident", "severity": 0.85, "road_type": "highway"},
        ],
    },
    "road_closure": {
        "traffic_multiplier": 1.0,
        "weather": "clear",
        "incidents": [
            {"type": "road_closure", "road_type": "highway"},
        ],
    },
    "heavy_rain": {
        "traffic_multiplier": 1.0,
        "weather": "heavy_rain",
    },
    "traffic_surge": {
        "traffic_multiplier": 1.30,
        "weather": "clear",
    },
    "major_event": {
        "traffic_multiplier": 1.0,
        "weather": "clear",
        "incidents": [
            {"type": "special_event", "severity": 0.7, "road_type": "major"},
        ],
    },
}


def apply_scenario_to_engine(engine, scenario_name: str) -> Dict[str, Any]:
    """Execute scenario-specific modifications deterministically on the engine."""
    from app.simulation.incident_simulator import IncidentType, WeatherType
    
    # 1. Clean slate reset of previous scenario state (prevents effect accumulation)
    engine.demand_model.reset_demand()
    engine.weather_simulator.clear_weather_override()
    engine.incident_simulator.clear_all_incidents(engine.roads)
    for road in engine.roads.values():
        road.incident_penalty = 0.0
        road.weather_penalty = 0.0
        if getattr(road, 'congestion_level', None) == 'closed':
            road.congestion_level = 'free'
    
    current_hour = engine.state.simulation_time.hour + engine.state.simulation_time.minute / 60.0
    is_weekend = False
    modifications: Dict[str, Any] = {}

    if scenario_name == "normal":
        # Baseline demand, clear weather, 0 incidents, 0 closures
        modifications = {
            "traffic_multiplier": 1.0,
            "weather": "clear",
            "active_incidents": 0,
            "closed_roads": 0,
            "description": "Baseline traffic conditions restored"
        }

    elif scenario_name == "rush_hour":
        # Morning Rush: Peak hour traffic buildup (1.8x demand multiplier)
        multiplier = 1.8
        engine.demand_model.set_demand_multiplier(multiplier)
        modifications = {
            "traffic_multiplier": multiplier,
            "weather": "clear",
            "active_incidents": 0,
            "description": "Morning rush hour traffic buildup across major corridors"
        }

    elif scenario_name == "major_jam":
        # Major Jam: Severe bottleneck formation (2.2x demand + severe bottlenecks)
        multiplier = 2.2
        engine.demand_model.set_demand_multiplier(multiplier)
        
        # Select bottleneck roads
        bottleneck_roads = [
            rid for rid, r in engine.roads.items()
            if getattr(r, 'road_type', '') in ('highway_bottleneck', 'highway')
        ]
        if not bottleneck_roads:
            bottleneck_roads = list(engine.roads.keys())
        
        jam_road_1 = bottleneck_roads[0]
        jam_road_2 = bottleneck_roads[min(1, len(bottleneck_roads) - 1)]
        
        inc1 = engine.incident_simulator.spawn_incident(
            incident_type=IncidentType.ACCIDENT,
            current_tick=engine.state.current_tick,
            road_id=jam_road_1
        )
        if inc1:
            inc1.severity = 0.90
            inc1.capacity_reduction_pct = 85.0
            inc1.description = "Major highway multi-vehicle bottleneck"
            inc1.end_tick = engine.state.current_tick + 240
            road1 = engine.roads.get(jam_road_1)
            if road1:
                road1.incident_penalty = 0.85

        if jam_road_2 != jam_road_1:
            inc2 = engine.incident_simulator.spawn_incident(
                incident_type=IncidentType.ROAD_WORK,
                current_tick=engine.state.current_tick,
                road_id=jam_road_2
            )
            if inc2:
                inc2.severity = 0.75
                inc2.capacity_reduction_pct = 70.0
                inc2.description = "Emergency lane restriction"
                inc2.end_tick = engine.state.current_tick + 240
                road2 = engine.roads.get(jam_road_2)
                if road2:
                    road2.incident_penalty = 0.70

        modifications = {
            "traffic_multiplier": multiplier,
            "weather": "clear",
            "bottlenecks": [jam_road_1, jam_road_2],
            "description": "Major gridlock with critical highway bottlenecks"
        }

    elif scenario_name == "accident":
        # Accident: High-severity incident with capacity reduction on primary road
        multiplier = 1.0
        engine.demand_model.set_demand_multiplier(multiplier)
        highway_roads = [
            rid for rid, r in engine.roads.items()
            if getattr(r, 'road_type', '') in ('highway', 'major')
        ]
        target_road_id = highway_roads[0] if highway_roads else list(engine.roads.keys())[0]
        
        inc = engine.incident_simulator.spawn_incident(
            incident_type=IncidentType.ACCIDENT,
            current_tick=engine.state.current_tick,
            road_id=target_road_id
        )
        if inc:
            inc.severity = 0.85
            inc.capacity_reduction_pct = 75.0
            inc.description = "Multi-vehicle collision on primary corridor"
            inc.end_tick = engine.state.current_tick + 180
            target_road = engine.roads.get(target_road_id)
            if target_road:
                target_road.incident_penalty = 0.75

        modifications = {
            "traffic_multiplier": multiplier,
            "weather": "clear",
            "incident": {
                "incident_id": inc.incident_id if inc else "unknown",
                "type": "accident",
                "road_id": target_road_id,
                "severity": 0.85,
                "capacity_reduction_pct": 75.0
            },
            "description": "High-severity accident on primary corridor"
        }

    elif scenario_name == "road_closure":
        # Road Closure: Major road closed completely, traffic redistributes
        multiplier = 1.0
        engine.demand_model.set_demand_multiplier(multiplier)
        major_roads = [
            rid for rid, r in engine.roads.items()
            if getattr(r, 'road_type', '') in ('highway', 'major')
        ]
        target_road_id = major_roads[0] if major_roads else list(engine.roads.keys())[0]

        inc = engine.incident_simulator.spawn_incident(
            incident_type=IncidentType.ROAD_CLOSURE,
            current_tick=engine.state.current_tick,
            road_id=target_road_id
        )
        if inc:
            inc.severity = 1.0
            inc.capacity_reduction_pct = 100.0
            inc.description = "Emergency road closure — police detour in effect"
            inc.end_tick = engine.state.current_tick + 240
            target_road = engine.roads.get(target_road_id)
            if target_road:
                target_road.incident_penalty = 1.0
                target_road.current_congestion = 1.0
                target_road.congestion_level = "closed"
                target_road.avg_speed = 0.0
                target_road.vehicle_count = 0.0

        modifications = {
            "traffic_multiplier": multiplier,
            "weather": "clear",
            "road_closure": {
                "incident_id": inc.incident_id if inc else "unknown",
                "road_id": target_road_id,
                "status": "closed"
            },
            "description": "Major road closed completely, traffic redistributes"
        }

    elif scenario_name == "heavy_rain":
        # Heavy Rain: Speed and capacity reductions network-wide
        engine.weather_simulator.set_weather(WeatherType.HEAVY_RAIN, temperature=13.0, locked=True)
        engine._apply_weather_effects()
        for road in engine.roads.values():
            speed_mod = engine.weather_simulator.get_speed_modifier()
            road.avg_speed = max(5.0, road.speed_limit_kmh * (1 - road.current_congestion * 0.7) * speed_mod)
        modifications = {
            "weather": "heavy_rain",
            "speed_modifier": 0.70,
            "capacity_modifier": 0.75,
            "temperature": 13.0,
            "description": "Network-wide heavy rain with reduced visibility and slick roads"
        }

    elif scenario_name == "traffic_surge":
        # Traffic Surge: Exactly 30% demand increase city-wide
        multiplier = 1.30
        engine.demand_model.set_demand_multiplier(multiplier)
        modifications = {
            "traffic_multiplier": multiplier,
            "demand_increase_pct": 30,
            "weather": "clear",
            "description": "City-wide 30% traffic demand surge"
        }

    elif scenario_name == "major_event":
        # Major Event: Spatially localized demand around a defined event venue
        venue_node = "N1210"
        venue_roads = [
            eid for eid, edge in engine.roads.items()
            if edge.source == venue_node or edge.target == venue_node
        ]
        if not venue_roads:
            venue_roads = list(engine.roads.keys())[:10]
        
        # Apply 2.8x localized demand specifically to the venue access roads
        engine.demand_model.set_localized_demand({rid: 2.8 for rid in venue_roads})
        
        primary_venue_road = venue_roads[0]
        inc = engine.incident_simulator.spawn_incident(
            incident_type=IncidentType.SPECIAL_EVENT,
            current_tick=engine.state.current_tick,
            road_id=primary_venue_road
        )
        if inc:
            inc.severity = 0.70
            inc.capacity_reduction_pct = 40.0
            inc.description = "Major Arena Event in progress — localized congestion around venue"
            inc.end_tick = engine.state.current_tick + 240
            road = engine.roads.get(primary_venue_road)
            if road:
                road.incident_penalty = 0.40

        modifications = {
            "scenario": "major_event",
            "venue_node": venue_node,
            "venue_roads_count": len(venue_roads),
            "localized_demand_multiplier": 2.8,
            "primary_road": primary_venue_road,
            "description": "High localized demand around Midtown Event Arena"
        }

    # Step simulation state forward to reflect scenario immediately
    engine._generate_traffic(current_hour, is_weekend)
    engine.congestion_engine.calculate_all(engine.roads)

    return modifications


@router.post("/scenario")
async def run_scenario(
    request: ScenarioRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_operator)
):
    """Execute a predefined scenario from current simulation state."""
    engine = get_simulation_engine()
    
    if not engine._running:
        if engine.state.current_tick > 0:
            await engine.resume()
        else:
            await engine.start(session_id=str(uuid.uuid4()))
    
    scenario_name = request.scenario_name
    if scenario_name not in SCENARIO_MODIFICATIONS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario_name}")
    
    modifications = apply_scenario_to_engine(engine, scenario_name)
    await engine._broadcast_updates()
    
    return {
        "message": f"Scenario {scenario_name} executed",
        "scenario": scenario_name,
        "modifications": modifications,
        "status": "applied"
    }


@router.post("/what-if")
async def run_what_if_scenario(
    request: WhatIfScenarioRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_operator)
):
    """Run a what-if scenario simulation on a cloned state.
    
    This creates a cloned simulation state, applies the scenario, 
    runs the simulation for specified steps, and returns comparison metrics.
    """
    engine = get_simulation_engine()
    
    try:
        result = engine.run_what_if_scenario(
            scenario_type=request.scenario_type,
            scenario_params=request.scenario_params,
            steps=request.steps
        )
        return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"What-if scenario error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scenario execution failed: {str(e)}")