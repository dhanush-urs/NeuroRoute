#!/usr/bin/env python3
"""
Seed the database with initial city data and development dataset.
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
from app.models import Base
from scripts.generate_city import CityGenerator, export_to_json


async def seed_database():
    settings = get_settings()
    
    # Create engine
    engine = create_async_engine(settings.database_url, echo=True)
    
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created")
        
        # Generate city
        print("Generating city...")
        generator = CityGenerator(seed=42)
        nodes, edges = generator.generate(grid_size=15)
        
        # Export for frontend
        export_to_json(nodes, edges, "city_data.json")
        
        # Insert nodes
        print(f"Inserting {len(nodes)} nodes...")
        for node in nodes:
            await conn.execute(text("""
                INSERT INTO nodes (id, node_id, latitude, longitude, node_type)
                VALUES (:id, :node_id, :lat, :lon, :type)
                ON CONFLICT (node_id) DO UPDATE SET
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    node_type = EXCLUDED.node_type
            """), {
                "id": str(uuid4()),
                "node_id": node.id,
                "lat": node.latitude,
                "lon": node.longitude,
                "type": node.node_type
            })
        
        # Insert roads
        print(f"Inserting {len(edges)} roads...")
        for edge in edges:
            await conn.execute(text("""
                INSERT INTO roads (id, source_node, target_node, distance_km, speed_limit_kmh, 
                                 capacity_vph, road_type, geometry, num_lanes)
                VALUES (:id, :source, :target, :dist, :speed, :cap, :type, :geom, :lanes)
                ON CONFLICT (source_node, target_node) DO UPDATE SET
                    distance_km = EXCLUDED.distance_km,
                    speed_limit_kmh = EXCLUDED.speed_limit_kmh,
                    capacity_vph = EXCLUDED.capacity_vph,
                    road_type = EXCLUDED.road_type,
                    geometry = EXCLUDED.geometry,
                    num_lanes = EXCLUDED.num_lanes
            """), {
                "id": str(uuid4()),
                "source": edge.source,
                "target": edge.target,
                "dist": edge.distance_km,
                "speed": edge.speed_limit,
                "cap": edge.capacity,
                "type": edge.road_type,
                "geom": json.dumps(edge.geometry),
                "lanes": 2
            })
        
        print("Database seeded successfully!")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())