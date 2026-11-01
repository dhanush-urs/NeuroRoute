from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime, timezone

from app.core.dependencies import get_db
from app.state import get_simulation_engine
from app.schemas.traffic import TrafficSnapshotResponse, TrafficSummaryResponse, CongestionLevel
from app.models.road import Road, Node

router = APIRouter(prefix="/traffic", tags=["traffic"])


@router.get("/vehicles")
async def get_vehicle_positions(db: AsyncSession = Depends(get_db)):
    """Get current visible vehicle positions as lat/lon for map rendering."""
    engine = get_simulation_engine()
    # Ensure node coordinate cache is populated
    if not engine.vehicle_engine._node_coords:
        engine.vehicle_engine._build_node_cache()
    vehicles = engine.vehicle_engine.get_visible_vehicles_lnglat()
    return {"vehicles": vehicles, "count": len(vehicles)}


_geometry_cache = None
_nodes_cache = None


@router.get("/geometry")
async def get_road_geometry(db: AsyncSession = Depends(get_db)):
    """Get road geometry in WGS84 format for map rendering."""
    global _geometry_cache
    if _geometry_cache is not None:
        return _geometry_cache

    # Get all nodes for coordinate lookup
    nodes_result = await db.execute(select(Node))
    node_coords = {row.node_id: (row.latitude, row.longitude) for row in nodes_result.scalars().all()}
    
    # Get all roads
    roads_result = await db.execute(select(Road))
    roads = roads_result.scalars().all()
    
    features = []
    for road in roads:
        src_coord = node_coords.get(road.source_node)
        tgt_coord = node_coords.get(road.target_node)
        
        # Use authentic road geometry LineString when available
        if road.geometry and isinstance(road.geometry, dict) and "coordinates" in road.geometry:
            coords = road.geometry.get("coordinates")
            if coords and isinstance(coords, list) and len(coords) >= 2:
                coordinates = coords
            elif src_coord and tgt_coord:
                coordinates = [
                    [src_coord[1], src_coord[0]],
                    [tgt_coord[1], tgt_coord[0]]
                ]
            else:
                continue
        elif src_coord and tgt_coord:
            # GeoJSON uses [longitude, latitude] order
            coordinates = [
                [src_coord[1], src_coord[0]],  # [longitude, latitude]
                [tgt_coord[1], tgt_coord[0]]
            ]
        else:
            continue
            
        features.append({
            "type": "Feature",
            "properties": {
                "road_id": str(road.id),
                "road_type": road.road_type,
                "source_node": road.source_node,
                "target_node": road.target_node,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            }
        })
    
    result = {
        "type": "FeatureCollection",
        "features": features
    }
    _geometry_cache = result
    return result


@router.get("/nodes")
async def get_nodes(db: AsyncSession = Depends(get_db)):
    """Get all nodes with their coordinates for map rendering."""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache

    nodes_result = await db.execute(select(Node))
    nodes = nodes_result.scalars().all()
    
    result = {
        "nodes": [
            {
                "node_id": node.node_id,
                "latitude": node.latitude,
                "longitude": node.longitude,
                "node_type": node.node_type,
            }
            for node in nodes
        ]
    }
    _nodes_cache = result
    return result


@router.get("/current", response_model=List[TrafficSnapshotResponse])
async def get_current_traffic(
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get current traffic state for all roads."""
    engine = get_simulation_engine()
    roads = engine.roads
    
    if not roads:
        return []
    
    # Get current tick snapshots
    tick = engine.state.current_tick
    
    results = []
    for road in list(roads.values())[offset:offset+limit]:
        cl_str = getattr(road, 'congestion_level', None)
        cl_enum = CongestionLevel(cl_str) if cl_str else None
        # vehicle_count is stored as float internally, convert to int for API
        vehicle_count = int(getattr(road, 'vehicle_count', 0.0))
        snapshot = TrafficSnapshotResponse(
            road_id=str(road.id),
            tick=engine.state.current_tick,
            sim_time=engine.state.simulation_time,
            vehicle_count=vehicle_count,
            avg_speed_kmh=getattr(road, 'avg_speed', None),
            congestion_score=getattr(road, 'current_congestion', None),
            congestion_level=cl_enum,
            travel_time_sec=None
        )
        if snapshot.avg_speed_kmh and snapshot.avg_speed_kmh > 0:
            snapshot.travel_time_sec = int((road.distance_km / snapshot.avg_speed_kmh) * 3600)
        results.append(snapshot)
    
    return results


@router.get("/summary", response_model=TrafficSummaryResponse)
async def get_traffic_summary(db = Depends(get_db)):
    """Get aggregate traffic statistics."""
    engine = get_simulation_engine()
    roads = engine.roads
    
    if not roads:
        return TrafficSummaryResponse(
            total_roads=0,
            total_vehicles=0,
            avg_speed_kmh=None,
            congestion_distribution={level: 0 for level in CongestionLevel},
            active_incidents=0,
            timestamp=datetime.now(timezone.utc)
        )
    
    total_vehicles = sum(int(getattr(r, 'vehicle_count', 0.0)) for r in roads.values())
    speeds = [getattr(r, 'avg_speed', 0) for r in roads.values() if getattr(r, 'avg_speed', 0) > 0]
    avg_speed = sum(speeds) / len(speeds) if speeds else None
    
    dist = {level: 0 for level in CongestionLevel}
    for road in roads.values():
        level = getattr(road, 'congestion_level', 'free')
        if level in dist:
            dist[level] += 1
        else:
            dist['free'] += 1
    
    active_incidents = len(engine.incident_simulator.active_incidents)
    
    return TrafficSummaryResponse(
        total_roads=len(roads),
        total_vehicles=total_vehicles,
        avg_speed_kmh=round(avg_speed, 1) if avg_speed else None,
        congestion_distribution=dist,
        active_incidents=active_incidents,
        timestamp=datetime.now(timezone.utc)
    )


@router.get("/{road_id}", response_model=TrafficSnapshotResponse)
async def get_road_traffic(road_id: str, db = Depends(get_db)):
    """Get current traffic state for a specific road."""
    engine = get_simulation_engine()
    road = engine.roads.get(road_id)
    
    if not road:
        raise HTTPException(status_code=404, detail=f"Road {road_id} not found")
    
    cl_str = getattr(road, 'congestion_level', None)
    cl_enum = CongestionLevel(cl_str) if cl_str else None
    
    # vehicle_count is stored as float internally, convert to int for API
    vehicle_count = int(getattr(road, 'vehicle_count', 0.0))
    
    snapshot = TrafficSnapshotResponse(
        road_id=str(road.id),
        tick=engine.state.current_tick,
        sim_time=engine.state.simulation_time,
        vehicle_count=vehicle_count,
        avg_speed_kmh=getattr(road, 'avg_speed', None),
        congestion_score=getattr(road, 'current_congestion', None),
        congestion_level=cl_enum,
        travel_time_sec=None
    )
    
    if snapshot.avg_speed_kmh and snapshot.avg_speed_kmh > 0:
        snapshot.travel_time_sec = int((road.distance_km / snapshot.avg_speed_kmh) * 3600)
    
    return snapshot


@router.get("/history/{road_id}", response_model=List[TrafficSnapshotResponse])
async def get_road_history(
    road_id: str, 
    limit: int = Query(default=100, le=1000),
    db = Depends(get_db)
):
    """Get historical traffic snapshots for a road."""
    engine = get_simulation_engine()
    
    # Return empty for now - would need DB query
    return []


@router.get("/incidents/active")
async def get_active_incidents(db = Depends(get_db)):
    """Get all active incidents."""
    engine = get_simulation_engine()
    incidents = []
    for inc in engine.incident_simulator.active_incidents.values():
        incidents.append({
            "incident_id": inc.incident_id,
            "incident_type": inc.incident_type.value,
            "road_id": inc.road_id,
            "severity": inc.severity,
            "start_tick": inc.start_tick,
            "capacity_reduction_pct": inc.capacity_reduction_pct,
            "description": inc.description
        })
    return {"incidents": incidents, "count": len(incidents)}