from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.dependencies import get_engine, get_session_factory
from app.simulation.engine import SimulationEngine, SimulationConfig, create_simulation_engine
from app.graph.graph import RoadGraph
from app.simulation.demand_model import DemandModel
from app.simulation.congestion import CongestionEngine
from app.simulation.vehicle_engine import VehicleEngine
from app.simulation.traffic_state import TrafficStateEngine
from app.simulation.incident_simulator import IncidentSimulator, WeatherSimulator
from app.api.websocket import get_websocket_manager
from app.state import set_simulation_engine, set_road_graph
from app.auth import init_default_users
from app.prediction.inference import get_model_service
from app.routing.router import Router

settings = get_settings()
logger = get_logger(__name__)


def extract_hosts(origins: list[str]) -> list[str]:
    """Extract host:port from origin URLs for WebSocket allowed_hosts."""
    hosts = []
    for origin in origins:
        # Remove protocol
        if "://" in origin:
            origin = origin.split("://", 1)[1]
        # Remove path
        origin = origin.split("/")[0]
        hosts.append(origin)
    return hosts


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.log_level)
    logger.info("Starting NeuroRoute API", version="0.1.0", env=settings.app_env)

    # Initialize database
    db_engine = get_engine()
    session_factory = get_session_factory()

    # Load road graph from database
    road_graph = RoadGraph()
    await road_graph.load_from_database(session_factory)
    logger.info(f"Loaded road graph: {len(road_graph.nodes)} nodes, {len(road_graph.edges)} edges")

    # Store in global state
    set_road_graph(road_graph)

    # Initialize simulation engine
    config = SimulationConfig(
        seed=settings.simulation_seed,
        tick_interval_sec=settings.simulation_tick_interval_sec,
        speed_multiplier=settings.simulation_default_speed,
        max_vehicles_visible=settings.simulation_max_vehicles_visible,
        prediction_horizons=settings.prediction_horizon_list,
    )

    # Get websocket manager
    ws_manager = get_websocket_manager()

    # Initialize prediction service
    try:
        prediction_service = get_model_service()
    except Exception as e:
        logger.warning(f"Could not load prediction service: {e}")
        prediction_service = None

    # Initialize router
    router = Router(graph=road_graph)

    # Create simulation engine
    simulation_engine = create_simulation_engine(
        graph=road_graph,
        config=config,
        db_session_factory=session_factory,
        websocket_manager=ws_manager,
        prediction_service=prediction_service,
        router=router
    )

    # Store in global state
    set_simulation_engine(simulation_engine)

    # Initialize default users for authentication
    if settings.auth_enabled:
        init_default_users()
        logger.info("Default users initialized")

    logger.info("NeuroRoute API started successfully")
    yield

    # Shutdown
    if simulation_engine.is_running:
        await simulation_engine.pause()

    logger.info("Shutting down NeuroRoute API")


app = FastAPI(
    title="NeuroRoute API",
    description="AI Traffic Brain - Dynamic Route Optimization Platform",
    version="0.1.0",
    lifespan=lifespan,
)

class WebSocketAllowedHostsMiddleware:
    """Middleware to set allowed_hosts for WebSocket connections."""
    
    def __init__(self, app, allowed_hosts: list[str]):
        self.app = app
        # For development, don't set allowed_hosts (None = no validation)
        # In production, use the provided allowed_hosts
        self.allowed_hosts = None if settings.app_env == "development" else allowed_hosts

    async def __call__(self, scope, receive, send):
        # Set allowed_hosts for WebSocket connections
        if scope.get("type") == "websocket" and self.allowed_hosts is not None:
            scope["allowed_hosts"] = self.allowed_hosts
            print(f"DEBUG: WebSocket middleware setting allowed_hosts: {self.allowed_hosts}")
        await self.app(scope, receive, send)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add WebSocket allowed hosts middleware (must be added after CORSMiddleware to run first for WebSocket)
app.add_middleware(WebSocketAllowedHostsMiddleware, allowed_hosts=extract_hosts(settings.cors_origins_list))

app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "service": "neuroroute", "version": "0.1.0"}


@app.get("/health/ready")
async def readiness_check() -> dict:
    return {"status": "ready", "service": "neuroroute"}


@app.get("/health/live")
async def liveness_check() -> dict:
    return {"status": "alive", "service": "neuroroute"}


@app.get("/api/v1")
async def api_root() -> dict:
    return {
        "name": "NeuroRoute API",
        "version": "0.1.0",
        "description": "AI Traffic Brain - Dynamic Route Optimization Platform",
        "endpoints": {
            "traffic": "/api/v1/traffic",
            "routing": "/api/v1/routes",
            "simulation": "/api/v1/simulation",
            "incidents": "/api/v1/incidents",
            "predictions": "/api/v1/predictions",
            "analytics": "/api/v1/analytics",
            "websocket": "/api/v1/ws",
        },
    }


@app.get("/v1/models")
async def get_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": settings.nvidia_nim_model,
                "object": "model",
                "owned_by": "nvidia",
            }
        ],
    }