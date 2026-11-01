#!/usr/bin/env python3
"""
Generate synthetic traffic dataset for ML training using the ACTUAL simulation engine.

This ensures training data matches the inference distribution exactly.
"""

import argparse
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.simulation.engine import SimulationEngine, SimulationConfig
from app.graph.graph import RoadGraph
from app.simulation.demand_model import DemandModel, TimeProvider
from app.simulation.congestion import calculate_congestion, classify_congestion
from app.simulation.incident_simulator import IncidentSimulator, WeatherSimulator
from app.simulation.vehicle_engine import VehicleEngine
from scripts.generate_city import CityGenerator


class DatasetGenerator:
    """Generates synthetic traffic dataset by running the actual simulation engine."""

    def __init__(
        self,
        seed: int = 42,
        num_roads: int = 50,
        num_days: int = 1,
        tick_interval_min: int = 1,
        num_vehicles_visible: int = 200,
    ):
        self.seed = seed
        self.num_roads = num_roads
        self.num_days = num_days
        self.tick_interval_min = tick_interval_min
        self.num_vehicles_visible = num_vehicles_visible
        
        # Load or generate city
        self.city_generator = CityGenerator(seed=seed)
        self.nodes, self.edges = self.city_generator.generate(grid_size=15)
        self.roads_list = self.edges[:num_roads]
        
        # Build graph
        self.graph = RoadGraph()
        for node in self.nodes:
            self.graph.add_node(node.id, node.latitude, node.longitude, node.node_type)
        for edge in self.edges:
            self.graph.add_edge(edge.id, edge.source, edge.target, edge.distance_km, edge.speed_limit, edge.capacity, edge.road_type)
        
        # Create simulation engine components
        self.demand_model = DemandModel(seed=seed)
        self.weather_simulator = WeatherSimulator(seed=seed)
        self.incident_simulator = IncidentSimulator(self.graph, seed=seed)
        self.vehicle_engine = VehicleEngine(self.graph)
        
        # Congestion engine for calculations
        from app.simulation.congestion import CongestionEngine
        self.congestion_engine = CongestionEngine(self.graph)
        
        # Road lookup
        self.road_map = {r.id: r for r in self.roads_list}

    def _get_roads_dict(self) -> Dict:
        """Convert graph edges to road-like objects for simulation."""
        roads = {}
        for edge in self.graph.edges.values():
            # Create a simple object with required attributes
            class RoadObj:
                def __init__(self, edge):
                    self.id = edge.id
                    self.source = edge.source
                    self.target = edge.target
                    self.distance_km = edge.distance_km
                    self.speed_limit_kmh = edge.speed_limit_kmh
                    self.capacity_vph = edge.capacity_vph
                    self.road_type = edge.road_type
                    self.geometry = edge.geometry
                    self.vehicle_count = 0
                    self.avg_speed = edge.speed_limit_kmh
                    self.current_congestion = 0.0
                    self.congestion_level = "free"
                    self.incident_penalty = 0.0
                    self.weather_penalty = 0.0
                    
            roads[edge.id] = RoadObj(edge)
        return roads

    async def generate(self) -> pd.DataFrame:
        """Generate the full dataset by running the simulation engine."""
        # Initialize roads
        roads = self._get_roads_dict()
        
        # Select subset of roads for dataset
        road_ids = list(roads.keys())[:self.num_roads]
        roads = {k: roads[k] for k in road_ids}
        
        # Initialize entry buffers
        for road in roads.values():
            road._entry_buffer = [0] * 2  # will resize
        
        # Initialize weather simulator with start time
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        self.weather_simulator.update(start_time)
        
        records = []
        total_ticks = self.num_days * 24 * 60  # 1 tick per minute
        
        print(f"Generating {total_ticks} time steps for {len(roads)} roads...")
        print(f"Total records: {total_ticks * len(roads):,}")
        
        for tick in range(total_ticks):
            # Advance simulation time
            current_time = start_time + timedelta(minutes=tick)
            current_hour = current_time.hour + current_time.minute / 60.0
            is_weekend = TimeProvider.is_weekend(current_time)
            
            # Weather
            self.weather_simulator.update(current_time)
            weather_mod = self.weather_simulator.get_speed_modifier()
            current_weather = self.weather_simulator.current_weather.value
            
            # Incidents
            # Use a dummy roads dict for incident updates (they modify road.incident_penalty)
            dummy_roads = {rid: type('obj', (object,), {'incident_penalty': 0.0})() for rid in self.graph.edges.keys()}
            self.incident_simulator.update(dummy_roads, tick)
            
            # Generate traffic for each road
            for road in roads.values():
                road_type = getattr(road, 'road_type', 'major')
                
                # Get base demand
                base_demand = self.demand_model.interpolate_demand(road_type, current_hour, is_weekend)
                
                # Apply weather modifier
                weather_mod = self.weather_simulator.get_speed_modifier()
                
                # Apply incident modifier
                incident_mod = 1.0 - getattr(road, 'incident_penalty', 0.0)
                
                # Convert hourly demand to per-minute entry rate
                entry_rate = (base_demand / 60.0) * weather_mod * incident_mod
                
                # Travel time in minutes (at free flow speed)
                free_flow_speed = road.speed_limit_kmh * self.weather_simulator.get_speed_modifier()
                free_flow_speed = max(free_flow_speed, 5.0)
                travel_time_min = max(1, int((road.distance_km / free_flow_speed) * 60))
                
                # Initialize delay buffer if not exists
                if not hasattr(road, '_entry_buffer') or len(road._entry_buffer) != travel_time_min + 1:
                    road._entry_buffer = [0] * (travel_time_min + 1)
                
                # Vehicles entering now
                vehicles_entering = entry_rate
                
                # Vehicles exiting (entered travel_time_min minutes ago)
                if travel_time_min < len(road._entry_buffer):
                    vehicles_exiting = road._entry_buffer[travel_time_min]
                else:
                    vehicles_exiting = 0
                
                # Shift buffer
                road._entry_buffer = [vehicles_entering] + road._entry_buffer[:-1]
                
                # Update vehicle count
                current = getattr(road, 'vehicle_count', 0)
                net_change = vehicles_entering - vehicles_exiting
                new_count = current + net_change
                
                # Clamp to reasonable bounds
                jam_density = road.capacity_vph / (road.speed_limit_kmh / 3.6)
                max_vehicles = int(jam_density * road.distance_km * 1.5)
                road.vehicle_count = max(0, min(int(new_count), max_vehicles))
                
                # Calculate congestion
                congestion = calculate_congestion(road, road.vehicle_count, road.avg_speed)
                road.current_congestion = congestion
                road.congestion_level = classify_congestion(congestion)
                
                # Calculate average speed based on congestion
                speed_limit = road.speed_limit_kmh
                road.avg_speed = speed_limit * (1 - congestion * 0.7) * self.weather_simulator.get_speed_modifier()
                road.avg_speed = max(5.0, road.avg_speed)
                
                # Calculate derived features
                density = road.vehicle_count / max(road.distance_km, 0.1)
                occupancy = (road.vehicle_count / max(road.capacity_vph, 1)) * 100
                
                record = {
                    'timestamp': current_time.isoformat(),
                    'road_id': road.id,
                    'day_of_week': current_time.weekday(),
                    'hour': current_time.hour,
                    'is_weekend': int(is_weekend),
                    'is_rush_hour': int(((7 <= current_time.hour <= 9) or (16 <= current_time.hour <= 19))),
                    'minutes_since_midnight': current_time.hour * 60 + current_time.minute,
                    'vehicle_count': road.vehicle_count,
                    'avg_speed_kmh': round(road.avg_speed, 1),
                    'density': round(density, 2),
                    'occupancy_pct': round(occupancy, 2),
                    'congestion_score': round(congestion, 4),
                    'weather_condition': self.weather_simulator.current_weather.value,
                    'temperature_c': round(self.weather_simulator.current_temperature, 1),
                    'rain_intensity': 0.0,
                    'visibility_km': 20.0,
                    'incident_count': 0,
                    'max_incident_severity': 0.0,
                    'capacity_reduction_pct': 0.0,
                    'target_congestion_5m': 0.0,
                    'target_congestion_15m': 0.0,
                    'target_congestion_30m': 0.0,
                    'target_congestion_60m': 0.0,
                }
                records.append(record)
            
            if tick % 1000 == 0:
                print(f"  Completed tick {tick}/{total_ticks}")
        
        # Post-process: compute targets by shifting congestion forward
        df = pd.DataFrame(records)
        
        # Sort by road_id and timestamp
        df = df.sort_values(['road_id', 'timestamp']).reset_index(drop=True)
        
        # Compute targets by shifting
        for road_id in df['road_id'].unique():
            mask = df['road_id'] == road_id
            for horizon, col in [(5, 'target_congestion_5m'), (15, 'target_congestion_15m'), (30, 'target_congestion_30m'), (60, 'target_congestion_60m')]:
                df.loc[mask, col] = df.loc[mask, 'congestion_score'].shift(-horizon).fillna(0)
        
        return df


async def main():
    parser = argparse.ArgumentParser(description="Generate synthetic traffic dataset using simulation engine")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--roads", type=int, default=50, help="Number of roads")
    parser.add_argument("--days", type=int, default=1, help="Number of days to simulate")
    parser.add_argument("--interval", type=int, default=1, help="Tick interval in minutes")
    parser.add_argument("--output", type=str, default="traffic_dataset.parquet", help="Output file")
    parser.add_argument("--dev", action="store_true", help="Generate development-sized dataset")
    
    args = parser.parse_args()
    
    if args.dev:
        args.roads = 50
        args.days = 1
        args.output = "traffic_dataset_dev.parquet"
    
    generator = DatasetGenerator(
        seed=args.seed,
        num_roads=args.roads,
        num_days=args.days,
        tick_interval_min=args.interval,
    )
    
    df = await generator.generate()
    
    print(f"\nDataset shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nCongestion score stats:")
    print(df['congestion_score'].describe())
    print(f"\nTarget congestion (15m) stats:")
    print(df['target_congestion_15m'].describe())
    
    df.to_parquet(args.output, index=False)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())