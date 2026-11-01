from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Set
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "traffic": set(),
            "routing": set(),
            "incidents": set(),
            "simulation": set(),
        }

    async def connect(self, websocket: WebSocket, channel: str):
        # WebSocket is already accepted in the route handler
        self.active_connections[channel].add(websocket)
        logger.info(f"WebSocket connected to channel '{channel}'. Total connections: {len(self.active_connections[channel])}")

    def disconnect(self, websocket: WebSocket, channel: str):
        self.active_connections[channel].discard(websocket)
        logger.info(f"WebSocket disconnected from channel '{channel}'. Total connections: {len(self.active_connections[channel])}")

    async def broadcast(self, channel: str, message: dict):
        logger.debug(f"Broadcasting to channel '{channel}' with {len(self.active_connections[channel])} connections")
        # Create a copy of connections to avoid "Set changed size during iteration"
        connections = list(self.active_connections[channel])
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection in channel '{channel}': {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn, channel)


manager = ConnectionManager()


def get_websocket_manager() -> ConnectionManager:
    """Get the global websocket connection manager."""
    return manager


allowed_hosts = ["localhost:3000", "127.0.0.1:3000", "localhost:3001", "127.0.0.1:3001", "localhost:8000", "127.0.0.1:8000"]


@router.websocket("/traffic")
async def websocket_traffic(websocket: WebSocket):
    logger.info("WebSocket connection attempt to /traffic")
    print(f"DEBUG: websocket.scope.get('allowed_hosts') before accept: {websocket.scope.get('allowed_hosts')}")
    print(f"DEBUG: websocket.headers.get('origin'): {websocket.headers.get('origin')}")
    await websocket.accept()
    await manager.connect(websocket, "traffic")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error in /traffic: {e}")
        return
    finally:
        manager.disconnect(websocket, "traffic")


@router.websocket("/routing")
async def websocket_routing(websocket: WebSocket):
    logger.info("WebSocket connection attempt to /routing")
    await websocket.accept()
    await manager.connect(websocket, "routing")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error in /routing: {e}")
        return
    finally:
        manager.disconnect(websocket, "routing")


@router.websocket("/incidents")
async def websocket_incidents(websocket: WebSocket):
    logger.info("WebSocket connection attempt to /incidents")
    await websocket.accept()
    await manager.connect(websocket, "incidents")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error in /incidents: {e}")
        return
    finally:
        manager.disconnect(websocket, "incidents")


@router.websocket("/simulation")
async def websocket_simulation(websocket: WebSocket):
    logger.info("WebSocket connection attempt to /simulation")
    await websocket.accept()
    await manager.connect(websocket, "simulation")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error in /simulation: {e}")
        return
    finally:
        manager.disconnect(websocket, "simulation")


async def broadcast_traffic_update(data: dict):
    await manager.broadcast("traffic", {"type": "traffic_update", "data": data})


async def broadcast_route_update(data: dict):
    await manager.broadcast("routing", {"type": "route_update", "data": data})


async def broadcast_incident_update(data: dict):
    await manager.broadcast("incidents", {"type": "incident_update", "data": data})


async def broadcast_simulation_tick(data: dict):
    await manager.broadcast("simulation", {"type": "simulation_tick", "data": data})