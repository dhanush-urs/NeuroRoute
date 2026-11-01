#!/usr/bin/env python3
"""
Generate a deterministic synthetic city road network.

Creates ~200 nodes and ~500 directed edges with realistic geography:
- Major roads (highways, arterials)
- Minor roads (collectors, local)
- Intersections and junctions
- Bottlenecks
- Multiple alternative routes
"""

import json
import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple
from uuid import uuid4


@dataclass
class Node:
    id: str
    latitude: float
    longitude: float
    node_type: str


@dataclass
class Edge:
    id: str
    source: str
    target: str
    distance_km: float
    speed_limit: int
    capacity: int
    road_type: str
    geometry: dict


class CityGenerator:
    def __init__(self, seed: int = 42, center_lat: float = 40.7128, center_lon: float = -74.0060):
        self.seed = seed
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.random = random.Random(seed)
        
        # Grid spacing ~0.5km at this latitude
        self.grid_spacing_km = 0.5
        self.lat_per_km = 1.0 / 111.0
        self.lon_per_km = 1.0 / (111.0 * math.cos(math.radians(center_lat)))

    def generate(self, grid_size: int = 15) -> Tuple[List[Node], List[Edge]]:
        """Generate city with grid_size x grid_size nodes."""
        nodes = self._create_grid_nodes(grid_size)
        created_edges = set()
        edges = self._create_grid_edges(nodes, grid_size, created_edges)
        
        # Add highways
        highways = self._add_highways(nodes, grid_size, created_edges)
        edges.extend(highways)
        
        # Add diagonal connections for alternative routes
        diagonals = self._add_diagonal_edges(nodes, grid_size, created_edges)
        edges.extend(diagonals)
        
        # Create bottlenecks
        self._create_bottlenecks(edges)
        
        return nodes, edges

    def _create_grid_nodes(self, grid_size: int) -> List[Node]:
        nodes = []
        for i in range(grid_size):
            for j in range(grid_size):
                lat = self.center_lat + (i - grid_size // 2) * self.grid_spacing_km * self.lat_per_km
                lon = self.center_lon + (j - grid_size // 2) * self.grid_spacing_km * self.lon_per_km
                
                # Add some randomness to make it look natural
                lat += self.random.uniform(-0.001, 0.001)
                lon += self.random.uniform(-0.001, 0.001)
                
                node_type = "intersection"
                if i == 0 or i == grid_size - 1 or j == 0 or j == grid_size - 1:
                    node_type = "boundary"
                
                nodes.append(Node(
                    id=f"N{i:02d}{j:02d}",
                    latitude=lat,
                    longitude=lon,
                    node_type=node_type
                ))
        return nodes

    def _create_grid_edges(self, nodes: List[Node], grid_size: int, created_edges: set) -> List[Edge]:
        edges = []
        node_map = {n.id: n for n in nodes}
        created_edges = set()
        
        for i in range(grid_size):
            for j in range(grid_size):
                node_id = f"N{i:02d}{j:02d}"
                
                # East-West connections
                if j < grid_size - 1:
                    target_id = f"N{i:02d}{j+1:02d}"
                    edge_key = (node_id, target_id)
                    if edge_key not in created_edges:
                        edge = self._create_edge(node_id, target_id, "major")
                        edges.append(edge)
                        created_edges.add(edge_key)
                    # Bidirectional
                    reverse_key = (target_id, node_id)
                    if reverse_key not in created_edges:
                        edges.append(self._create_edge(target_id, node_id, "major"))
                        created_edges.add(reverse_key)
                
                # North-South connections
                if i < grid_size - 1:
                    target_id = f"N{i+1:02d}{j:02d}"
                    edge_key = (node_id, target_id)
                    if edge_key not in created_edges:
                        edge = self._create_edge(node_id, target_id, "major")
                        edges.append(edge)
                        created_edges.add(edge_key)
                    # Bidirectional
                    reverse_key = (target_id, node_id)
                    if reverse_key not in created_edges:
                        edges.append(self._create_edge(target_id, node_id, "major"))
                        created_edges.add(reverse_key)
        
        return edges

    def _create_edge(self, source: str, target: str, road_type: str) -> Edge:
        road_types = {
            "highway": {"speed": 100, "capacity": 2400, "base_dist": 1.5},
            "major": {"speed": 50, "capacity": 900, "base_dist": 0.5},
            "minor": {"speed": 30, "capacity": 400, "base_dist": 0.3},
            "local": {"speed": 20, "capacity": 200, "base_dist": 0.2},
        }
        
        config = road_types.get(road_type, road_types["major"])
        
        # Add variation
        distance = config["base_dist"] * self.random.uniform(0.8, 1.2)
        speed = config["speed"] + self.random.randint(-5, 5)
        capacity = int(config["capacity"] * self.random.uniform(0.8, 1.2))
        
        # Create simple LineString geometry
        # In production, would use actual node coordinates
        geometry = {
            "type": "LineString",
            "coordinates": [
                [0, 0],  # placeholder - would use actual coords
                [distance * 1000, 0]
            ]
        }
        
        return Edge(
            id=f"R{source}{target}",
            source=source,
            target=target,
            distance_km=round(distance, 3),
            speed_limit=speed,
            capacity=capacity,
            road_type=road_type,
            geometry=geometry
        )

    def _add_highways(self, nodes: List[Node], grid_size: int, created_edges: set) -> List[Edge]:
        """Add highway corridors through the city."""
        edges = []
        
        # Horizontal highways (rows 3, 7, 11)
        highway_rows = [3, 7, 11]
        for row in highway_rows:
            if row < grid_size:
                for j in range(grid_size - 1):
                    source = f"N{row:02d}{j:02d}"
                    target = f"N{row:02d}{j+1:02d}"
                    edge_key = (source, target)
                    if edge_key not in created_edges:
                        edges.append(self._create_edge(source, target, "highway"))
                        created_edges.add(edge_key)
                    # Bidirectional
                    reverse_key = (target, source)
                    if reverse_key not in created_edges:
                        edges.append(self._create_edge(target, source, "highway"))
                        created_edges.add(reverse_key)
        
        # Vertical highways (cols 3, 7, 11)
        highway_cols = [3, 7, 11]
        for col in highway_cols:
            if col < grid_size:
                for i in range(grid_size - 1):
                    source = f"N{i:02d}{col:02d}"
                    target = f"N{i+1:02d}{col:02d}"
                    edge_key = (source, target)
                    if edge_key not in created_edges:
                        edges.append(self._create_edge(source, target, "highway"))
                        created_edges.add(edge_key)
                    # Bidirectional
                    reverse_key = (target, source)
                    if reverse_key not in created_edges:
                        edges.append(self._create_edge(target, source, "highway"))
                        created_edges.add(reverse_key)
        
        return edges

    def _add_diagonal_edges(self, nodes: List[Node], grid_size: int, created_edges: set) -> List[Edge]:
        """Add diagonal connections for alternative routes."""
        edges = []
        
        # Add some diagonal minor roads
        for i in range(grid_size - 1):
            for j in range(grid_size - 1):
                if self.random.random() < 0.15:  # 15% chance of diagonal
                    source = f"N{i:02d}{j:02d}"
                    target = f"N{i+1:02d}{j+1:02d}"
                    edge_key = (source, target)
                    if edge_key not in created_edges:
                        edges.append(self._create_edge(source, target, "minor"))
                        created_edges.add(edge_key)
                    # Bidirectional
                    reverse_key = (target, source)
                    if reverse_key not in created_edges:
                        edges.append(self._create_edge(target, source, "minor"))
                        created_edges.add(reverse_key)
        
        return edges

    def _create_bottlenecks(self, edges: List[Edge]) -> None:
        """Create intentional bottlenecks by reducing capacity on specific edges."""
        # Find highway edges and create bottlenecks at specific points
        highway_edges = [e for e in edges if e.road_type == "highway"]
        
        for edge in highway_edges:
            if self.random.random() < 0.08:  # 8% of highways become bottlenecks
                edge.capacity = int(edge.capacity * self.random.uniform(0.3, 0.5))
                edge.road_type = "highway_bottleneck"


def export_to_sql(nodes: List[Node], edges: List[Edge], output_file: str = "city_seed.sql") -> None:
    """Export city as SQL INSERT statements."""
    with open(output_file, "w") as f:
        f.write("-- NeuroRoute City Seed Data\n")
        f.write(f"-- Generated with seed: 42\n\n")
        
        f.write("-- Nodes\n")
        f.write("INSERT INTO nodes (id, latitude, longitude, node_type) VALUES\n")
        node_values = []
        for node in nodes:
            node_values.append(f"('{node.id}', {node.latitude}, {node.longitude}, '{node.node_type}')")
        f.write(",\n".join(node_values) + ";\n\n")
        
        f.write("-- Roads\n")
        f.write("INSERT INTO roads (id, source_node, target_node, distance_km, speed_limit_kmh, capacity_vph, road_type, geometry) VALUES\n")
        road_values = []
        for edge in edges:
            geom_json = json.dumps(edge.geometry)
            road_values.append(
                f"('{edge.id}', '{edge.source}', '{edge.target}', {edge.distance_km}, "
                f"{edge.speed_limit}, {edge.capacity}, '{edge.road_type}', '{geom_json}')"
            )
        f.write(",\n".join(road_values) + ";\n")


def export_to_json(nodes: List[Node], edges: List[Edge], output_file: str = "city_data.json") -> None:
    """Export city as JSON for frontend visualization."""
    data = {
        "nodes": [
            {
                "id": n.id,
                "latitude": n.latitude,
                "longitude": n.longitude,
                "type": n.node_type
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "distance_km": e.distance_km,
                "speed_limit": e.speed_limit,
                "capacity": e.capacity,
                "road_type": e.road_type,
                "geometry": e.geometry
            }
            for e in edges
        ],
        "bounds": {
            "min_lat": min(n.latitude for n in nodes),
            "max_lat": max(n.latitude for n in nodes),
            "min_lon": min(n.longitude for n in nodes),
            "max_lon": max(n.longitude for n in nodes),
        }
    }
    
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)


def main():
    print("Generating synthetic city...")
    generator = CityGenerator(seed=42)
    nodes, edges = generator.generate(grid_size=15)
    
    print(f"Generated {len(nodes)} nodes and {len(edges)} edges")
    
    # Statistics
    road_types = {}
    for e in edges:
        road_types[e.road_type] = road_types.get(e.road_type, 0) + 1
    print("Road type distribution:", road_types)
    
    # Export
    export_to_sql(nodes, edges, "city_seed.sql")
    export_to_json(nodes, edges, "city_data.json")
    print("Exported to city_seed.sql and city_data.json")


if __name__ == "__main__":
    main()