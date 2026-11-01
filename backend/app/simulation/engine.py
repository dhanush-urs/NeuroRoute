import asyncio
import time
import copy
from datetime import datetime, timedelta, timezone
from typing import Dict, Set, Optional, Callable, Any, List
from dataclasses import dataclass, field
from collections import defaultdict

from app.simulation.demand_model import DemandModel, TimeProvider
from app.simulation.congestion import CongestionEngine
from app.simulation.vehicle_engine import VehicleEngine
from app.simulation.incident_simulator import IncidentSimulator, WeatherSimulator
from app.simulation.traffic_state import TrafficStateEngine

if False:  # TYPE_CHECKING
    from app.graph.graph import RoadGraph
    from app.models.road import Road
    from app.models.incident import Incident
    from app.core.dependencies import get_db


@dataclass
class SimulationConfig:
    seed: int = 42
    tick_interval_sec: float = 1.0
    speed_multiplier: int = 1
    max_vehicles_visible: int = 200
    snapshot_interval_ticks: int = 10
    prediction_horizons: list = field(default_factory=lambda: [5, 15, 30, 60])


@dataclass
class SimulationState:
    is_running: bool = False
    current_tick: int = 0
    simulation_time: datetime = field(default_factory=lambda: datetime(2024, 1, 1, 0, 0, 0))
    speed_multiplier: int = 1
    session_id: Optional[str] = None
    status: str = "stopped"  # stopped, running, paused
    config: SimulationConfig = field(default_factory=SimulationConfig)


class SimulationEngine:
    """Main traffic simulation engine."""
    
    def __init__(
        self,
        graph: "RoadGraph",
        config: Optional[SimulationConfig] = None,
        db_session_factory: Optional[Callable] = None,
        websocket_manager: Optional[Any] = None,
        prediction_service: Optional[Any] = None,
        router: Optional[Any] = None
    ):
        self.graph = graph
        self.config = config or SimulationConfig()
        self.db_session_factory = db_session_factory
        self.websocket_manager = websocket_manager
        self.prediction_service = prediction_service
        self.router = router
        
        # Initialize sub-components
        self.demand_model = DemandModel(seed=self.config.seed)
        self.vehicle_engine = VehicleEngine(self.graph)
        self.congestion_engine = CongestionEngine(self.graph)
        self.incident_simulator = IncidentSimulator(self.graph, seed=self.config.seed)
        self.weather_simulator = WeatherSimulator(seed=self.config.seed)
        
        # State
        self.state = SimulationState(config=self.config)
        
        # Background task
        self._tick_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks for external systems
        self.on_tick_callbacks: list = []
        self.on_snapshot_callbacks: list = []
    
    @property
    def roads(self) -> Dict[str, "Road"]:
        """Get all roads from graph."""
        return {edge.id: edge for edge in self.graph.edges.values()}
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def start(self, session_id: Optional[str] = None) -> None:
        """Start the simulation."""
        if self._running:
            return
        
        self._running = True
        self.state.is_running = True
        self.state.status = "running"
        if session_id:
            self.state.session_id = session_id
        
        # Start the tick loop
        self._tick_task = asyncio.create_task(self._tick_loop())
    
    async def pause(self) -> None:
        """Pause the simulation."""
        self._running = False
        self.state.is_running = False
        self.state.status = "paused"
        if self.websocket_manager:
            try:
                await self.websocket_manager.broadcast("simulation", {
                    "type": "simulation_tick",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "tick": self.state.current_tick,
                        "sim_time": self.state.simulation_time.isoformat(),
                        "speed_multiplier": self.config.speed_multiplier,
                        "status": "paused",
                        "is_running": False,
                    }
                })
            except Exception:
                pass
    
    async def resume(self) -> None:
        """Resume the simulation."""
        if not self._running:
            self._running = True
            self.state.is_running = True
            self.state.status = "running"
            self._tick_task = asyncio.create_task(self._tick_loop())
            if self.websocket_manager:
                try:
                    await self.websocket_manager.broadcast("simulation", {
                        "type": "simulation_tick",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {
                            "tick": self.state.current_tick,
                            "sim_time": self.state.simulation_time.isoformat(),
                            "speed_multiplier": self.config.speed_multiplier,
                            "status": "running",
                            "is_running": True,
                        }
                    })
                except Exception:
                    pass
    
    async def reset(self, seed: Optional[int] = None) -> None:
        """Reset simulation to initial state."""
        await self.pause()
        
        # Reset state
        self.state = SimulationState(config=self.config)
        if seed is not None:
            self.config.seed = seed
            self.demand_model = DemandModel(seed=seed)
            self.incident_simulator = IncidentSimulator(self.graph, seed=seed)
            self.weather_simulator = WeatherSimulator(seed=seed)
        
        # Reset all roads
        for road in self.roads.values():
            road.vehicle_count = 0
            road.avg_speed = road.speed_limit_kmh
            road.current_congestion = 0.0
            road.congestion_level = "free"
            road.current_congestion_5m = 0.0
            road.current_congestion_15m = 0.0
            road.current_congestion_30m = 0.0
            road.current_congestion_60m = 0.0
            road.incident_penalty = 0.0
            road.weather_penalty = 0.0
    
    async def set_speed(self, multiplier: int) -> None:
        """Set simulation speed multiplier."""
        self.config.speed_multiplier = max(1, min(60, multiplier))
        self.state.speed_multiplier = self.config.speed_multiplier
    
    def add_tick_callback(self, callback: Callable) -> None:
        """Add callback to be called on each tick."""
        self.on_tick_callbacks.append(callback)
    
    def add_snapshot_callback(self, callback: Callable) -> None:
        """Add callback for snapshot persistence."""
        self.on_snapshot_callbacks.append(callback)
    
    async def _tick_loop(self) -> None:
        """Main simulation tick loop."""
        while self._running:
            tick_start = time.time()
            
            try:
                await self._process_tick()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error in simulation tick: {e}")
            
            elapsed = time.time() - tick_start
            sleep_time = max(0, self.config.tick_interval_sec / self.config.speed_multiplier - elapsed)
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    async def _process_tick(self) -> None:
        """Process a single simulation tick."""
        self.state.current_tick += 1
        self.state.simulation_time += timedelta(minutes=1)
        
        is_weekend = TimeProvider.is_weekend(self.state.simulation_time)
        current_hour = self.state.simulation_time.hour + self.state.simulation_time.minute / 60.0
        
        # 1. Generate traffic from demand model
        self._generate_traffic(current_hour, is_weekend)
        
        # 2. Update vehicle positions
        self.vehicle_engine.update(self.roads)
        
        # 3. Calculate congestion per road
        self.congestion_engine.calculate_all(self.roads)
        
        # 4. Propagate congestion upstream (queue spillback) - weak propagation
        congested_ids = self.congestion_engine.get_congested_roads(self.roads, threshold=0.8)
        if congested_ids:
            impacts = self.congestion_engine.propagate(self.roads, congested_ids)
            self.congestion_engine.apply_propagation(self.roads, impacts)
        
        # 5. Update incidents
        self.incident_simulator.update(self.roads, self.state.current_tick)
        
        # 6. Update weather
        self.weather_simulator.update(self.state.simulation_time)
        self._apply_weather_effects()
        
        # 7. Persist snapshot periodically
        if self.state.current_tick % self.config.snapshot_interval_ticks == 0:
            await self._persist_snapshot()
            for callback in self.on_snapshot_callbacks:
                try:
                    await callback(self.state.current_tick, self.roads)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Snapshot callback error: {e}")
        
        # 8. Generate predictions periodically (every 5 ticks) to avoid blocking real-time tick advancement
        if self.prediction_service and (self.state.current_tick % 5 == 0 or self.state.current_tick == 1):
            try:
                await self.prediction_service.predict_batch(self.roads, self.state.current_tick)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Prediction error: {e}")
        
        # 9. Check rerouting
        if self.router:
            try:
                if hasattr(self.router, 'check_reroute_tick'):
                    await self.router.check_reroute_tick(self.state.current_tick)
                else:
                    await self.router.check_reroute(self.state.current_tick)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Reroute check error: {e}")
        
        # 10. Broadcast WebSocket updates
        if self.websocket_manager:
            try:
                await self._broadcast_updates()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"WebSocket broadcast error: {e}")
        
        # 11. Call external callbacks
        for callback in self.on_tick_callbacks:
            try:
                await callback(self.state.current_tick, self.roads, self.state.simulation_time)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Tick callback error: {e}")
    
    def _generate_traffic(self, hour: float, is_weekend: bool) -> None:
        """Generate vehicle counts for each road based on demand using queueing model with travel time delay.
        
        Each tick = 1 simulated minute. Demand is in vehicles/hour, so convert to per-minute.
        Vehicles take travel_time minutes to traverse the road (delay line model).
        """
        for road in self.roads.values():
            road_type = getattr(road, 'road_type', 'major')
            
            # Check if road is closed
            if getattr(road, 'incident_penalty', 0.0) >= 0.95 or getattr(road, 'congestion_level', '') == 'closed':
                road.vehicle_count = 0.0
                road.avg_speed = 0.0
                road.current_congestion = 1.0
                road.congestion_level = "closed"
                continue

            # Get base demand (vehicles/hour) with global and localized modifiers
            base_demand = self.demand_model.get_road_demand(road.id, road_type, hour, is_weekend)
            
            # Apply weather modifier to demand (reduces demand)
            weather_mod = self.weather_simulator.get_speed_modifier()
            
            # Apply incident modifier (reduces effective capacity and demand)
            incident_mod = 1.0 - getattr(road, 'incident_penalty', 0.0)
            
            # Convert hourly demand to per-minute entry rate
            entry_rate = (base_demand / 60.0) * weather_mod * incident_mod
            
            # Travel time in minutes (at free flow speed)
            free_flow_speed = road.speed_limit_kmh * self.weather_simulator.get_speed_modifier()
            free_flow_speed = max(free_flow_speed, 5.0)
            travel_time_min = max(1, int((road.distance_km / free_flow_speed) * 60))
            
            # Initialize delay buffer for this road if not exists
            if not hasattr(road, '_entry_buffer'):
                road._entry_buffer = [0] * (travel_time_min + 1)
            
            # Resize buffer if travel time changed
            if len(road._entry_buffer) != travel_time_min + 1:
                old_buffer = road._entry_buffer
                road._entry_buffer = [0] * (travel_time_min + 1)
                # Copy what we can
                for i in range(min(len(old_buffer), len(road._entry_buffer))):
                    road._entry_buffer[i] = old_buffer[i]
            
            # Vehicles entering now
            vehicles_entering = entry_rate
            
            # Vehicles exiting (entered travel_time_min minutes ago)
            if travel_time_min < len(road._entry_buffer):
                vehicles_exiting = road._entry_buffer[travel_time_min]
            else:
                vehicles_exiting = 0
            
            # Shift buffer (vehicles move one step closer to exit)
            road._entry_buffer = [vehicles_entering] + road._entry_buffer[:-1]
            
            # Update vehicle count
            current = getattr(road, 'vehicle_count', 0.0)
            net_change = vehicles_entering - vehicles_exiting
            new_count = current + net_change
            
            # Clamp to reasonable bounds (0 to 1.5x jam density)
            jam_density = road.capacity_vph / (road.speed_limit_kmh / 3.6)  # veh/km at capacity
            max_vehicles = jam_density * road.distance_km * 1.5
            road.vehicle_count = max(0.0, min(new_count, max_vehicles))
            
            # Calculate average speed based on congestion (RESULT of density)
            congestion = getattr(road, 'current_congestion', 0.0)
            speed_limit = road.speed_limit_kmh
            road.avg_speed = speed_limit * (1 - congestion * 0.7) * self.weather_simulator.get_speed_modifier()
            road.avg_speed = max(5.0, road.avg_speed)
    
    def _apply_weather_effects(self) -> None:
        """Apply weather effects to roads."""
        weather = self.weather_simulator.current_weather
        
        for road in self.roads.values():
            # Reset penalties
            road.weather_penalty = 0.0
            
            if weather == "heavy_rain":
                road.weather_penalty = 0.3
            elif weather == "light_rain":
                road.weather_penalty = 0.15
            elif weather == "fog":
                road.weather_penalty = 0.25
            elif weather == "snow":
                road.weather_penalty = 0.4
    
    async def _persist_snapshot(self) -> None:
        """Persist traffic snapshot to database."""
        if not self.db_session_factory or not self.state.session_id:
            return
        
        try:
            from app.models.traffic import TrafficSnapshot
            from sqlalchemy import insert
            import uuid

            # Get active incidents for this tick
            active_incidents = self.incident_simulator.get_active_incidents()
            road_incidents = {}
            for inc in active_incidents:
                if inc.road_id not in road_incidents:
                    road_incidents[inc.road_id] = []
                road_incidents[inc.road_id].append(inc.incident_id)

            records = []
            sess_uuid = uuid.UUID(self.state.session_id) if isinstance(self.state.session_id, str) else self.state.session_id
            weather_val = self.weather_simulator.current_weather.value if hasattr(self.weather_simulator.current_weather, 'value') else str(self.weather_simulator.current_weather)

            for road in self.roads.values():
                vehicle_count = int(getattr(road, 'vehicle_count', 0.0))
                road_uuid = uuid.UUID(str(road.id)) if isinstance(road.id, str) else road.id
                records.append({
                    "id": uuid.uuid4(),
                    "session_id": sess_uuid,
                    "road_id": road_uuid,
                    "tick": self.state.current_tick,
                    "sim_time": self.state.simulation_time,
                    "vehicle_count": vehicle_count,
                    "avg_speed_kmh": getattr(road, 'avg_speed', None),
                    "density_veh_km": None,
                    "occupancy_pct": None,
                    "congestion_score": getattr(road, 'current_congestion', None),
                    "congestion_level": getattr(road, 'congestion_level', None),
                    "travel_time_sec": None,
                    "weather_condition": weather_val,
                    "incident_ids": road_incidents.get(road.id, []),
                })

            async with self.db_session_factory() as session:
                await session.execute(insert(TrafficSnapshot), records)
                await session.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Snapshot persistence error: {e}")
    
    async def _broadcast_updates(self) -> None:
        """Broadcast updates via WebSocket."""
        if not self.websocket_manager:
            import logging
            logging.getLogger(__name__).warning("WebSocket manager is None, skipping broadcast")
            return
        
        # Debug: log connection counts
        import logging
        logger = logging.getLogger(__name__)
        for channel, conns in self.websocket_manager.active_connections.items():
            logger.info(f"WebSocket channel '{channel}': {len(conns)} connections")
        
        # Prepare traffic update
        traffic_data = []
        for road in self.roads.values():
            traffic_data.append({
                "road_id": road.id,
                "tick": self.state.current_tick,
                "sim_time": self.state.simulation_time.isoformat(),
                # vehicle_count is stored as float internally; send as int for dashboard
                "vehicle_count": int(getattr(road, 'vehicle_count', 0)),
                "avg_speed_kmh": round(getattr(road, 'avg_speed', 0), 1),
                "congestion_score": round(getattr(road, 'current_congestion', 0), 4),
                "congestion_level": getattr(road, 'congestion_level', "free"),
                "weather_condition": self.weather_simulator.current_weather,
            })
        
        logger.info(f"Broadcasting traffic update for tick {self.state.current_tick} with {len(traffic_data)} roads")
        
        await self.websocket_manager.broadcast("traffic", {
            "type": "traffic_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": traffic_data
        })
        
        # Broadcast simulation tick
        await self.websocket_manager.broadcast("simulation", {
            "type": "simulation_tick",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "tick": self.state.current_tick,
                "sim_time": self.state.simulation_time.isoformat(),
                "speed_multiplier": self.config.speed_multiplier,
                "status": self.state.status,
            }
        })
        
        # Broadcast vehicle positions (lat/lon) for map rendering
        try:
            vehicle_data = self.vehicle_engine.get_visible_vehicles_lnglat()
            if vehicle_data:
                await self.websocket_manager.broadcast("traffic", {
                    "type": "vehicle_update",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": vehicle_data
                })
        except Exception as e:
            logger.warning(f"Vehicle broadcast error: {e}")

        # Broadcast incident updates
        active_incidents = self.incident_simulator.get_active_incidents()
        incident_data = []
        for inc in active_incidents:
            incident_data.append({
                "incident_id": inc.incident_id,
                "type": inc.incident_type,  # Already a string
                "road_id": inc.road_id,
                "severity": inc.severity,
                "start_tick": inc.start_tick,
                "end_tick": inc.end_tick,
                "capacity_reduction_pct": inc.capacity_reduction_pct,
                "description": inc.description,
                "status": inc.status,
            })
        
        await self.websocket_manager.broadcast("incidents", {
            "type": "incident_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": incident_data
        })
    
    def get_status(self) -> Dict[str, Any]:
        """Get current simulation status."""
        return {
            "session_id": self.state.session_id,
            "seed": self.config.seed,
            "current_tick": self.state.current_tick,
            "simulation_time": self.state.simulation_time.isoformat(),
            "speed_multiplier": self.config.speed_multiplier,
            "status": self.state.status,
            "is_running": self._running,
            "demand_multiplier": getattr(self.demand_model, 'demand_multiplier', 1.0),
            "weather": self.weather_simulator.current_weather.value if hasattr(self.weather_simulator.current_weather, 'value') else str(self.weather_simulator.current_weather),
            "weather_locked": getattr(self.weather_simulator, 'locked', False),
            "active_incidents": len(self.incident_simulator.active_incidents),
        }

    def clone_state(self) -> "SimulationEngine":
        """Create a deep copy of the simulation engine for what-if scenarios.
        
        This creates a completely independent copy of the simulation state
        that can be used for what-if scenario testing without affecting
        the live simulation.
        """
        from app.graph.graph import RoadGraph
        
        # Create a deep copy of the graph with new Edge objects
        cloned_graph = RoadGraph()
        for node_id, node in self.graph.nodes.items():
            cloned_graph.add_node(node_id, node.latitude, node.longitude, node.node_type)
        
        for edge_id, edge in self.graph.edges.items():
            cloned_graph.add_edge(
                edge_id=edge.id,
                source=edge.source,
                target=edge.target,
                distance_km=edge.distance_km,
                speed_limit_kmh=edge.speed_limit_kmh,
                capacity_vph=edge.capacity_vph,
                road_type=edge.road_type
            )
            # Copy dynamic properties
            cloned_edge = cloned_graph.edges[edge_id]
            cloned_edge.current_congestion = edge.current_congestion
            cloned_edge.predicted_congestion_5m = edge.predicted_congestion_5m
            cloned_edge.predicted_congestion_15m = edge.predicted_congestion_15m
            cloned_edge.predicted_congestion_30m = edge.predicted_congestion_30m
            cloned_edge.predicted_congestion_60m = edge.predicted_congestion_60m
            cloned_edge.incident_penalty = edge.incident_penalty
            cloned_edge.weather_penalty = edge.weather_penalty
            cloned_edge.vehicle_count = edge.vehicle_count
            cloned_edge.avg_speed = edge.avg_speed
            cloned_edge.congestion_level = edge.congestion_level
            if hasattr(edge, '_entry_buffer'):
                cloned_edge._entry_buffer = edge._entry_buffer.copy()
        
        # Create new engine with cloned graph and config
        cloned_engine = SimulationEngine(
            graph=cloned_graph,
            config=SimulationConfig(
                seed=self.config.seed,
                tick_interval_sec=self.config.tick_interval_sec,
                speed_multiplier=self.config.speed_multiplier,
                max_vehicles_visible=self.config.max_vehicles_visible,
                snapshot_interval_ticks=self.config.snapshot_interval_ticks,
                prediction_horizons=self.config.prediction_horizons.copy(),
            ),
            db_session_factory=None,  # No DB for what-if scenarios
            websocket_manager=None,  # No WebSocket for what-if
            prediction_service=None,  # Use main engine's prediction service if needed
            router=self.router  # Share router for route calculations
        )
        
        # Copy the current state
        cloned_engine.state = SimulationState(
            is_running=False,  # What-if scenarios don't run continuously
            current_tick=self.state.current_tick,
            simulation_time=self.state.simulation_time,
            speed_multiplier=self.state.speed_multiplier,
            session_id=None,  # No session for what-if
            status="what-if",
            config=cloned_engine.config
        )
        
        # Copy incident simulator state
        cloned_engine.incident_simulator.active_incidents = {
            k: v for k, v in self.incident_simulator.active_incidents.items()
        }
        cloned_engine.incident_simulator.incident_counter = self.incident_simulator.incident_counter
        
        # Copy weather simulator state
        cloned_engine.weather_simulator.current_weather = self.weather_simulator.current_weather
        cloned_engine.weather_simulator.current_temperature = self.weather_simulator.current_temperature
        cloned_engine.weather_simulator._last_change_tick = self.weather_simulator._last_change_tick
        
        # Copy demand model state (random state)
        cloned_engine.demand_model.random.setstate(self.demand_model.random.getstate())
        
        # Copy vehicle engine state
        cloned_engine.vehicle_engine.road_vehicle_counts = self.vehicle_engine.road_vehicle_counts.copy()
        cloned_engine.vehicle_engine.visible_vehicles = [
            v for v in self.vehicle_engine.visible_vehicles
        ]
        cloned_engine.vehicle_engine._vehicle_id_counter = self.vehicle_engine._vehicle_id_counter
        
        # Copy weather simulator random state
        cloned_engine.weather_simulator.random.setstate(self.weather_simulator.random.getstate())
        
        # Copy incident simulator random state
        cloned_engine.incident_simulator.random.setstate(self.incident_simulator.random.getstate())
        
        return cloned_engine

    def run_what_if_scenario(
        self,
        scenario_type: str,
        scenario_params: Dict[str, Any],
        steps: int = 60
    ) -> Dict[str, Any]:
        """Run a what-if scenario on a cloned simulation state.
        
        Args:
            scenario_type: Type of scenario (accident, road_closure, weather, traffic_surge, event)
            scenario_params: Parameters for the scenario (e.g., road_id, severity, duration)
            steps: Number of simulation ticks to advance (default 60 = 1 hour)
            
        Returns:
            Dictionary with baseline and scenario comparison metrics
        """
        # Clone current state
        cloned_engine = self.clone_state()
        
        # Capture baseline metrics
        baseline_metrics = self._capture_metrics()
        
        # Apply scenario to cloned engine
        self._apply_scenario(cloned_engine, scenario_type, scenario_params)
        
        # Advance simulation for specified steps
        for _ in range(steps):
            # Manually process tick without WebSocket/DB
            current_hour = cloned_engine.state.simulation_time.hour + \
                cloned_engine.state.simulation_time.minute / 60.0
            is_weekend = TimeProvider.is_weekend(cloned_engine.state.simulation_time)
            
            cloned_engine._generate_traffic(current_hour, is_weekend)
            cloned_engine.vehicle_engine.update(cloned_engine.roads)
            cloned_engine.congestion_engine.calculate_all(cloned_engine.roads)
            
            congested_ids = cloned_engine.congestion_engine.get_congested_roads(
                cloned_engine.roads, threshold=0.5
            )
            if congested_ids:
                impacts = cloned_engine.congestion_engine.propagate(
                    cloned_engine.roads, congested_ids
                )
                cloned_engine.congestion_engine.apply_propagation(
                    cloned_engine.roads, impacts
                )
            
            cloned_engine.incident_simulator.update(
                cloned_engine.roads, cloned_engine.state.current_tick
            )
            cloned_engine.weather_simulator.update(cloned_engine.state.simulation_time)
            cloned_engine._apply_weather_effects()
            
            cloned_engine.state.current_tick += 1
            cloned_engine.state.simulation_time += timedelta(minutes=1)
        
        # Capture scenario metrics
        scenario_metrics = cloned_engine._capture_metrics()
        
        # Compare baseline vs scenario
        comparison = self._compare_metrics(baseline_metrics, scenario_metrics)
        
        return {
            "scenario_type": scenario_type,
            "scenario_params": scenario_params,
            "steps_simulated": steps,
            "baseline": baseline_metrics,
            "scenario": scenario_metrics,
            "comparison": comparison,
            "simulation_time": cloned_engine.state.simulation_time.isoformat(),
            "ticks_advanced": steps
        }

    def _capture_metrics(self) -> Dict[str, Any]:
        """Capture current simulation metrics for comparison."""
        total_vehicles = sum(r.vehicle_count for r in self.roads.values())
        congestion_counts = {"free": 0, "moderate": 0, "heavy": 0, "congested": 0, "severe": 0}
        total_congestion = 0.0
        
        for road in self.roads.values():
            congestion_counts[road.congestion_level] = congestion_counts.get(road.congestion_level, 0) + 1
            total_congestion += road.current_congestion
        
        avg_congestion = total_congestion / len(self.roads) if self.roads else 0
        
        # Route metrics if router available
        route_info = None
        if self.router and hasattr(self, '_last_route_check'):
            pass  # Could add route metrics here
        
        return {
            "total_vehicles": total_vehicles,
            "avg_congestion": round(avg_congestion, 4),
            "congestion_distribution": congestion_counts,
            "total_roads": len(self.roads),
            "simulation_time": self.state.simulation_time.isoformat(),
            "current_tick": self.state.current_tick,
            "weather": self.weather_simulator.current_weather.value if hasattr(self.weather_simulator.current_weather, 'value') else str(self.weather_simulator.current_weather),
            "active_incidents": len(self.incident_simulator.active_incidents)
        }

    def _apply_scenario(self, engine: "SimulationEngine", scenario_type: str, params: Dict[str, Any]) -> None:
        """Apply a scenario to the cloned engine."""
        if scenario_type == "accident":
            road_id = params.get("road_id")
            severity = params.get("severity", 0.8)
            duration = params.get("duration", 30)
            if road_id and road_id in engine.roads:
                engine.incident_simulator.spawn_incident(
                    incident_type="accident",
                    current_tick=engine.state.current_tick,
                    road_id=road_id
                )
        
        elif scenario_type == "road_closure":
            road_id = params.get("road_id")
            if road_id and road_id in engine.roads:
                engine.incident_simulator.spawn_incident(
                    incident_type="road_closure",
                    current_tick=engine.state.current_tick,
                    road_id=road_id
                )
        
        elif scenario_type == "weather":
            weather_type = params.get("weather_type", "heavy_rain")
            from app.simulation.incident_simulator import WeatherType
            engine.weather_simulator.set_weather(WeatherType(weather_type))
        
        elif scenario_type == "traffic_surge":
            multiplier = params.get("multiplier", 1.3)
            # Temporarily increase demand
            engine.config.demand_multiplier = multiplier
        
        elif scenario_type == "event":
            road_id = params.get("road_id")
            demand_increase = params.get("demand_increase", 2.0)
            if road_id and road_id in engine.roads:
                # Add temporary demand surge on specific road
                pass  # Implementation would add event demand
        
    def _compare_metrics(self, baseline: Dict, scenario: Dict) -> Dict[str, Any]:
        """Compare baseline and scenario metrics."""
        return {
            "vehicle_change": scenario["total_vehicles"] - baseline["total_vehicles"],
            "congestion_change": round(scenario["avg_congestion"] - baseline["avg_congestion"], 4),
            "congestion_distribution_change": {
                k: scenario["congestion_distribution"].get(k, 0) - baseline["congestion_distribution"].get(k, 0)
                for k in set(baseline["congestion_distribution"]) | set(scenario["congestion_distribution"])
            },
            "incident_change": scenario["active_incidents"] - baseline["active_incidents"],
            "weather_change": scenario["weather"] != baseline["weather"],
            "summary": {
                "congestion_increased": scenario["avg_congestion"] > baseline["avg_congestion"],
                "significant_change": abs(scenario["avg_congestion"] - baseline["avg_congestion"]) > 0.1,
                "vehicle_change_pct": round(
                    (scenario["total_vehicles"] - baseline["total_vehicles"]) / max(baseline["total_vehicles"], 1) * 100, 2
                )
            }
        }


# Factory function for creating engine with all dependencies
def create_simulation_engine(
    graph: "RoadGraph",
    db_session_factory: Optional[Callable] = None,
    websocket_manager: Optional[Any] = None,
    prediction_service: Optional[Any] = None,
    router: Optional[Any] = None,
    config: Optional[SimulationConfig] = None
) -> SimulationEngine:
    """Create simulation engine with all dependencies."""
    return SimulationEngine(
        graph=graph,
        config=config,
        db_session_factory=db_session_factory,
        websocket_manager=websocket_manager,
        prediction_service=prediction_service,
        router=router
    )