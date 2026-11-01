from typing import Dict, List, Optional, Tuple
import random
import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum


class VehicleState(Enum):
    MOVING = "moving"
    SLOWING = "slowing"
    STOPPED = "stopped"
    REROUTING = "rerouting"
    ARRIVED = "arrived"


@dataclass
class Vehicle:
    vehicle_id: str
    road_id: str
    position: float  # 0.0 to 1.0 along road
    speed: float
    state: VehicleState = VehicleState.MOVING
    destination: Optional[str] = None
    route: List[str] = field(default_factory=list)


def _interpolate_position(
    src_lat: float, src_lon: float,
    tgt_lat: float, tgt_lon: float,
    t: float  # 0.0 = source, 1.0 = target
) -> Tuple[float, float]:
    """Linearly interpolate between two lat/lon coordinates.
    Returns (longitude, latitude) in GeoJSON convention.
    """
    t = max(0.0, min(1.0, t))
    lat = src_lat + (tgt_lat - src_lat) * t
    lon = src_lon + (tgt_lon - src_lon) * t
    return (lon, lat)


def _bearing(src_lat: float, src_lon: float, tgt_lat: float, tgt_lon: float) -> float:
    """Compute compass bearing in degrees from source to target."""
    d_lon = math.radians(tgt_lon - src_lon)
    lat1 = math.radians(src_lat)
    lat2 = math.radians(tgt_lat)
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _interpolate_linestring(
    coords: List[List[float]],
    t: float
) -> Tuple[float, float, float]:
    """Interpolate position and calculate local bearing along a GeoJSON LineString coordinates list.
    coords: list of [lon, lat]
    t: 0.0 (start) to 1.0 (end)
    Returns (longitude, latitude, bearing)
    """
    if not coords:
        return (0.0, 0.0, 0.0)
    if len(coords) == 1:
        return (coords[0][0], coords[0][1], 0.0)

    t = max(0.0, min(1.0, t))

    # Calculate sub-segment distances
    seg_dists = []
    total_dist = 0.0
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        # Haversine distance in meters
        R = 6371000.0
        phi1 = math.radians(p1[1])
        phi2 = math.radians(p2[1])
        delta_phi = math.radians(p2[1] - p1[1])
        delta_lambda = math.radians(p2[0] - p1[0])
        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        d = R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        seg_dists.append(d)
        total_dist += d

    if total_dist <= 1e-6:
        p1 = coords[0]
        p2 = coords[-1]
        b = _bearing(p1[1], p1[0], p2[1], p2[0]) if len(coords) > 1 else 0.0
        return (p1[0], p1[1], b)

    target_d = t * total_dist
    accum_d = 0.0

    for i, seg_d in enumerate(seg_dists):
        if accum_d + seg_d >= target_d or i == len(seg_dists) - 1:
            seg_t = (target_d - accum_d) / seg_d if seg_d > 1e-6 else 0.0
            seg_t = max(0.0, min(1.0, seg_t))
            p1 = coords[i]
            p2 = coords[i + 1]
            lon = p1[0] + (p2[0] - p1[0]) * seg_t
            lat = p1[1] + (p2[1] - p1[1]) * seg_t
            bearing = _bearing(p1[1], p1[0], p2[1], p2[0])
            return (lon, lat, bearing)
        accum_d += seg_d

    last = coords[-1]
    prev = coords[-2]
    return (last[0], last[1], _bearing(prev[1], prev[0], last[1], last[0]))


class VehicleEngine:
    """Simulates vehicle movement through the road network."""

    def __init__(self, graph: "RoadGraph", max_visible: int = 200, seed: int = 42):
        self.graph = graph
        self.max_visible = max_visible
        self.random = random.Random(seed)

        # Aggregate vehicle counts per road (for simulation)
        self.road_vehicle_counts: Dict[str, float] = defaultdict(float)

        # Sampled vehicles for visualization (max 200)
        self.visible_vehicles: List[Vehicle] = []

        # Vehicle ID counter
        self._vehicle_id_counter = 0

        # Node coordinate cache: node_id -> (lat, lon)
        self._node_coords: Dict[str, Tuple[float, float]] = {}

    def _build_node_cache(self) -> None:
        """Build a cache of node_id -> (lat, lon) from graph nodes."""
        self._node_coords = {}
        for node_id, node in self.graph.nodes.items():
            lat = getattr(node, 'latitude', None)
            lon = getattr(node, 'longitude', None)
            if lat is not None and lon is not None:
                self._node_coords[node_id] = (lat, lon)

    def update(self, roads: Dict[str, "Road"]) -> None:
        """Update vehicle positions and states for one tick."""
        # Build node cache on first call (or if empty)
        if not self._node_coords:
            self._build_node_cache()

        # Update aggregate counts from road vehicle counts
        for road_id, road in roads.items():
            self.road_vehicle_counts[road_id] = getattr(road, 'vehicle_count', 0.0)

        # Update visible vehicles for frontend
        self._update_visible_vehicles(roads)

    def _update_visible_vehicles(self, roads: Dict[str, "Road"]) -> None:
        """Update sampled vehicles for visualization."""
        # 1. Update positions of existing vehicles
        for vehicle in self.visible_vehicles:
            if vehicle.state == VehicleState.ARRIVED:
                continue

            road = roads.get(vehicle.road_id)
            if not road:
                vehicle.state = VehicleState.ARRIVED
                continue

            # Check if road is closed due to incident
            if getattr(road, 'incident_penalty', 0.0) >= 0.95 or getattr(road, 'congestion_level', '') == 'closed':
                vehicle.state = VehicleState.STOPPED
                vehicle.speed = 0.0
                continue

            # Speed based on current road conditions
            road_speed = getattr(road, 'avg_speed', road.speed_limit_kmh)
            vehicle.speed = max(5.0, road_speed)
            distance_km = vehicle.speed / 60.0  # distance traveled in 1 simulated minute
            road_length_km = max(0.1, road.distance_km)

            new_pos = vehicle.position + (distance_km / road_length_km)

            if new_pos < 1.0:
                vehicle.position = new_pos
                if vehicle.speed < road.speed_limit_kmh * 0.3:
                    vehicle.state = VehicleState.SLOWING
                else:
                    vehicle.state = VehicleState.MOVING
            else:
                # Vehicle reached end of current road - advance to downstream road if available
                downstream = self.graph.get_downstream_roads(vehicle.road_id)
                # Filter out closed roads
                open_downstream = [
                    edge for edge in downstream
                    if getattr(edge, 'incident_penalty', 0.0) < 0.95 and getattr(edge, 'congestion_level', '') != 'closed'
                ]

                if open_downstream:
                    # Pick next road deterministically
                    next_road = self.random.choice(open_downstream)
                    vehicle.road_id = next_road.id
                    # Remainder position on new road
                    remainder_km = (new_pos - 1.0) * road_length_km
                    next_len = max(0.1, next_road.distance_km)
                    vehicle.position = min(0.9, max(0.0, remainder_km / next_len))
                    vehicle.speed = getattr(next_road, 'avg_speed', next_road.speed_limit_kmh)
                    vehicle.state = VehicleState.MOVING
                else:
                    # Reached boundary / dead-end
                    vehicle.position = 1.0
                    vehicle.state = VehicleState.ARRIVED

        # 2. Remove arrived vehicles
        self.visible_vehicles = [v for v in self.visible_vehicles if v.state != VehicleState.ARRIVED]

        # 3. Add new vehicles if under limit
        while len(self.visible_vehicles) < self.max_visible:
            # Pick a random road with vehicles
            eligible_roads = [
                (road_id, count) for road_id, count in self.road_vehicle_counts.items()
                if count > 0.5
            ]

            if not eligible_roads:
                break

            total = sum(count for _, count in eligible_roads)
            r = self.random.random() * total
            cumsum = 0.0
            selected_road = eligible_roads[0][0]

            for road_id, count in eligible_roads:
                cumsum += count
                if r <= cumsum:
                    selected_road = road_id
                    break

            road = roads.get(selected_road)
            if not road:
                break

            # Check if road is open
            if getattr(road, 'incident_penalty', 0.0) >= 0.95 or getattr(road, 'congestion_level', '') == 'closed':
                continue

            vehicle = Vehicle(
                vehicle_id=f"V{self._vehicle_id_counter:06d}",
                road_id=selected_road,
                position=self.random.uniform(0.05, 0.85),
                speed=getattr(road, 'avg_speed', road.speed_limit_kmh),
                state=VehicleState.MOVING
            )
            self._vehicle_id_counter += 1
            self.visible_vehicles.append(vehicle)

    def _vehicle_to_lnglat(self, vehicle: Vehicle) -> Optional[Dict]:
        """Convert a vehicle's road+position to GeoJSON [lon, lat] coordinates.
        Uses exact road geometry LineString when available, falling back to node endpoints.
        """
        # Look up the edge in the graph
        edge = self.graph.edges.get(vehicle.road_id)
        if edge is None:
            return None

        # Prefer authentic LineString geometry
        if edge.geometry and isinstance(edge.geometry, dict):
            coords = edge.geometry.get("coordinates")
            if coords and isinstance(coords, list) and len(coords) >= 2:
                lon, lat, bearing = _interpolate_linestring(coords, vehicle.position)
                return {
                    "longitude": round(lon, 6),
                    "latitude": round(lat, 6),
                    "bearing": round(bearing, 1),
                }

        src_coords = self._node_coords.get(edge.source)
        tgt_coords = self._node_coords.get(edge.target)

        if src_coords is None or tgt_coords is None:
            return None

        src_lat, src_lon = src_coords
        tgt_lat, tgt_lon = tgt_coords

        lon, lat = _interpolate_position(src_lat, src_lon, tgt_lat, tgt_lon, vehicle.position)
        bearing = _bearing(src_lat, src_lon, tgt_lat, tgt_lon)

        return {
            "longitude": round(lon, 6),
            "latitude": round(lat, 6),
            "bearing": round(bearing, 1),
        }

    def get_visible_vehicles(self) -> List[Dict]:
        """Get visible vehicles for frontend — road-relative positions only."""
        return [
            {
                "vehicle_id": v.vehicle_id,
                "road_id": v.road_id,
                "position": round(v.position, 4),
                "speed": round(v.speed, 1),
                "state": v.state.value,
            }
            for v in self.visible_vehicles
        ]

    def get_visible_vehicles_lnglat(self) -> List[Dict]:
        """Get visible vehicles with lat/lon coordinates for map rendering.
        Only includes vehicles where node coordinates are resolvable.
        """
        result = []
        for v in self.visible_vehicles:
            if v.state == VehicleState.ARRIVED:
                continue
            coords = self._vehicle_to_lnglat(v)
            if coords is None:
                continue
            result.append({
                "vehicle_id": v.vehicle_id,
                "road_id": v.road_id,
                "longitude": coords["longitude"],
                "latitude": coords["latitude"],
                "bearing": coords["bearing"],
                "speed": round(v.speed, 1),
                "state": v.state.value,
            })
        return result

    def get_vehicle_count(self, road_id: str) -> int:
        """Get aggregate vehicle count for a road."""
        return int(self.road_vehicle_counts.get(road_id, 0.0))

    def inject_vehicles(self, road_id: str, count: int) -> None:
        """Inject additional vehicles onto a road."""
        self.road_vehicle_counts[road_id] += float(count)