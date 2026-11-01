#!/usr/bin/env python3
"""
Import authentic OpenStreetMap road network for Lower Manhattan into PostgreSQL.

Features:
- Parses official OSM XML tiles
- Extracts real intersection nodes and road segments
- Preserves full LineString geometry for every road edge
- Computes true Haversine distance along curved roads
- Extracts largest strongly connected component (SCC) to ensure full reachability
- Inserts nodes and roads into PostgreSQL database
- Generates city_data.json
"""

import asyncio
import glob
import json
import math
import os
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
from app.models import Base

DRIVABLE_HIGHWAYS = {
    'motorway', 'motorway_link',
    'trunk', 'trunk_link',
    'primary', 'primary_link',
    'secondary', 'secondary_link',
    'tertiary', 'tertiary_link',
    'residential', 'unclassified', 'living_street'
}

SPEED_LIMITS = {
    'motorway': 65,
    'motorway_link': 50,
    'trunk': 65,
    'trunk_link': 50,
    'primary': 50,
    'primary_link': 40,
    'secondary': 40,
    'secondary_link': 35,
    'tertiary': 40,
    'tertiary_link': 35,
    'residential': 30,
    'unclassified': 30,
    'living_street': 25,
}

CAPACITY_PER_LANE = {
    'motorway': 1800,
    'motorway_link': 1200,
    'trunk': 1600,
    'trunk_link': 1100,
    'primary': 1000,
    'primary_link': 800,
    'secondary': 800,
    'secondary_link': 700,
    'tertiary': 700,
    'tertiary_link': 600,
    'residential': 500,
    'unclassified': 500,
    'living_street': 400,
}

DEFAULT_LANES = {
    'motorway': 3,
    'motorway_link': 1,
    'trunk': 3,
    'trunk_link': 1,
    'primary': 2,
    'primary_link': 1,
    'secondary': 2,
    'secondary_link': 1,
    'tertiary': 2,
    'tertiary_link': 1,
    'residential': 1,
    'unclassified': 1,
    'living_street': 1,
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in kilometers between two points."""
    R = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def parse_speed_limit(val: str, default_speed: int) -> int:
    if not val:
        return default_speed
    val = val.lower().strip()
    try:
        if 'mph' in val:
            mph = float(val.replace('mph', '').strip())
            return int(round(mph * 1.60934))
        if 'km/h' in val or 'kmh' in val:
            return int(round(float(val.replace('km/h', '').replace('kmh', '').strip())))
        return int(round(float(val)))
    except Exception:
        return default_speed


def parse_lanes(val: str, default_lanes: int) -> int:
    if not val:
        return default_lanes
    try:
        lanes = int(val.strip().split(';')[0])
        return max(1, min(lanes, 6))
    except Exception:
        return default_lanes


def build_osm_network(tile_dir: str = "data/raw"):
    files = sorted(glob.glob(f"{tile_dir}/tile*.xml"))
    if not files:
        raise FileNotFoundError(f"No OSM tile XML files found in {tile_dir}")

    print(f"Reading {len(files)} OSM tiles: {files}...")
    nodes: Dict[str, Tuple[float, float]] = {}  # id -> (lat, lon)
    ways = []

    for fpath in files:
        tree = ET.parse(fpath)
        root = tree.getroot()
        for n in root.findall('node'):
            nid = n.attrib['id']
            nodes[nid] = (float(n.attrib['lat']), float(n.attrib['lon']))

        for w in root.findall('way'):
            wid = w.attrib['id']
            tags = {t.attrib['k']: t.attrib['v'] for t in w.findall('tag')}
            hw = tags.get('highway')
            if hw in DRIVABLE_HIGHWAYS and tags.get('access') not in ('no', 'private'):
                refs = [nd.attrib['ref'] for nd in w.findall('nd')]
                valid_refs = [r for r in refs if r in nodes]
                if len(valid_refs) >= 2:
                    oneway = tags.get('oneway', 'no')
                    if hw in ('motorway', 'motorway_link') and tags.get('oneway') != 'no':
                        oneway = 'yes'
                    if tags.get('junction') == 'roundabout':
                        oneway = 'yes'
                    ways.append((wid, hw, oneway, valid_refs, tags))

    print(f"Loaded {len(nodes)} OSM nodes and {len(ways)} drivable ways.")

    # Identify intersections
    node_use = defaultdict(int)
    for wid, hw, oneway, refs, tags in ways:
        for r in refs:
            node_use[r] += 1
        node_use[refs[0]] += 1
        node_use[refs[-1]] += 1

    intersections: Set[str] = {r for r, cnt in node_use.items() if cnt > 1}
    print(f"Identified {len(intersections)} intersection nodes.")

    # Segment ways between intersections
    edge_map = {}  # (src, tgt) -> (coords, dist_km, hw, tags)

    for wid, hw, oneway, refs, tags in ways:
        sub = [refs[0]]
        for r in refs[1:]:
            sub.append(r)
            if r in intersections:
                src = sub[0]
                tgt = sub[-1]
                if src != tgt:
                    coords = [[nodes[n][1], nodes[n][0]] for n in sub]  # [lon, lat]
                    dist = sum(
                        haversine(nodes[sub[i]][0], nodes[sub[i]][1], nodes[sub[i + 1]][0], nodes[sub[i + 1]][1])
                        for i in range(len(sub) - 1)
                    )
                    dist = max(0.015, dist)

                    candidates = []
                    if oneway == '-1':
                        candidates.append((tgt, src, list(reversed(coords))))
                    elif oneway in ('yes', '1', 'true'):
                        candidates.append((src, tgt, coords))
                    else:
                        candidates.append((src, tgt, coords))
                        candidates.append((tgt, src, list(reversed(coords))))

                    for s, t, c in candidates:
                        key = (s, t)
                        if key not in edge_map or dist < edge_map[key][1]:
                            edge_map[key] = (c, dist, hw, tags)
                sub = [r]

    print(f"Constructed {len(edge_map)} directed edge segments.")

    # Extract Largest Strongly Connected Component (Tarjan's algorithm)
    adj = defaultdict(list)
    for s, t in edge_map:
        adj[s].append(t)

    index = 0
    indices = {}
    lowlink = {}
    on_stack = set()
    stack = []
    sccs = []

    for n in list(adj.keys()):
        if n not in indices:
            call_stack = [(n, 0)]
            while call_stack:
                u, pi = call_stack[-1]
                if pi == 0:
                    indices[u] = index
                    lowlink[u] = index
                    index += 1
                    stack.append(u)
                    on_stack.add(u)
                neighbors = adj[u]
                advanced = False
                while pi < len(neighbors):
                    v = neighbors[pi]
                    pi += 1
                    call_stack[-1] = (u, pi)
                    if v not in indices:
                        call_stack.append((v, 0))
                        advanced = True
                        break
                    elif v in on_stack:
                        lowlink[u] = min(lowlink[u], indices[v])
                if advanced:
                    continue
                if len(call_stack) > 1:
                    parent = call_stack[-2][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[u])
                if lowlink[u] == indices[u]:
                    scc = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        scc.append(w)
                        if w == u:
                            break
                    sccs.append(scc)
                call_stack.pop()

    sccs.sort(key=len, reverse=True)
    largest_scc_nodes = set(sccs[0])
    scc_edges = {k: v for k, v in edge_map.items() if k[0] in largest_scc_nodes and k[1] in largest_scc_nodes}

    print(f"Largest SCC: {len(largest_scc_nodes)} nodes, {len(scc_edges)} directed edges.")
    return nodes, largest_scc_nodes, scc_edges


async def import_to_database():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    nodes_coords, scc_nodes, scc_edges = build_osm_network("data/raw")

    # Map OSM node IDs to clean node_id string
    # We can use 'n_' + osm_id or simple deterministic keys
    node_id_map = {osm_id: f"node_{osm_id}" for osm_id in scc_nodes}

    async with engine.begin() as conn:
        print("Clearing old graph and simulation data...")
        await conn.execute(text("DELETE FROM traffic_snapshots;"))
        await conn.execute(text("DELETE FROM predictions;"))
        await conn.execute(text("DELETE FROM incidents;"))
        await conn.execute(text("DELETE FROM roads;"))
        await conn.execute(text("DELETE FROM nodes;"))

        print(f"Inserting {len(scc_nodes)} real intersection nodes...")
        node_records = []
        for osm_id in scc_nodes:
            lat, lon = nodes_coords[osm_id]
            node_records.append({
                "id": str(uuid.uuid4()),
                "node_id": node_id_map[osm_id],
                "lat": round(lat, 7),
                "lon": round(lon, 7),
                "type": "intersection"
            })

        # Batch insert nodes in chunks of 500
        for i in range(0, len(node_records), 500):
            chunk = node_records[i:i + 500]
            await conn.execute(text("""
                INSERT INTO nodes (id, node_id, latitude, longitude, node_type)
                VALUES (:id, :node_id, :lat, :lon, :type)
            """), chunk)

        print(f"Inserting {len(scc_edges)} real OSM road segments with actual LineStrings...")
        road_records = []
        city_edges_json = []

        for (src_osm, tgt_osm), (coords, dist_km, hw, tags) in scc_edges.items():
            speed_limit = parse_speed_limit(tags.get('maxspeed', ''), SPEED_LIMITS.get(hw, 40))
            lanes = parse_lanes(tags.get('lanes', ''), DEFAULT_LANES.get(hw, 2))
            capacity = lanes * CAPACITY_PER_LANE.get(hw, 800)
            road_type = hw.replace('_link', '')
            geom = {
                "type": "LineString",
                "coordinates": [[round(pt[0], 7), round(pt[1], 7)] for pt in coords]
            }
            road_id = str(uuid.uuid4())
            src_node = node_id_map[src_osm]
            tgt_node = node_id_map[tgt_osm]

            road_records.append({
                "id": road_id,
                "source": src_node,
                "target": tgt_node,
                "dist": round(dist_km, 4),
                "speed": speed_limit,
                "cap": capacity,
                "type": road_type,
                "geom": json.dumps(geom),
                "lanes": lanes
            })

            city_edges_json.append({
                "id": road_id,
                "source": src_node,
                "target": tgt_node,
                "distance_km": round(dist_km, 4),
                "speed_limit": speed_limit,
                "capacity": capacity,
                "road_type": road_type,
                "geometry": geom
            })

        for i in range(0, len(road_records), 500):
            chunk = road_records[i:i + 500]
            await conn.execute(text("""
                INSERT INTO roads (id, source_node, target_node, distance_km, speed_limit_kmh,
                                 capacity_vph, road_type, geometry, num_lanes)
                VALUES (:id, :source, :target, :dist, :speed, :cap, :type, :geom, :lanes)
            """), chunk)

        print("Database seeded with real OSM road network successfully!")

    await engine.dispose()

    # Also update city_data.json
    city_nodes_json = [
        {
            "id": r["node_id"],
            "latitude": r["lat"],
            "longitude": r["lon"],
            "type": r["type"]
        }
        for r in node_records
    ]

    city_data = {
        "nodes": city_nodes_json,
        "edges": city_edges_json,
        "bounds": {
            "min_lat": min(r["lat"] for r in node_records),
            "max_lat": max(r["lat"] for r in node_records),
            "min_lon": min(r["lon"] for r in node_records),
            "max_lon": max(r["lon"] for r in node_records),
        }
    }

    with open("city_data.json", "w") as f:
        json.dump(city_data, f, indent=2)
    print(f"Exported {len(city_nodes_json)} nodes and {len(city_edges_json)} edges to city_data.json")


if __name__ == "__main__":
    asyncio.run(import_to_database())
