from fastapi import APIRouter

from app.api.routes import health, traffic, routing, simulation, incidents, predictions, analytics, explanations
from app.api import websocket
from app.api import auth as auth_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(auth_router.router)
api_router.include_router(traffic.router)
api_router.include_router(routing.router)
api_router.include_router(simulation.router)
api_router.include_router(incidents.router)
api_router.include_router(predictions.router)
api_router.include_router(analytics.router)
api_router.include_router(explanations.router)
api_router.include_router(websocket.router)