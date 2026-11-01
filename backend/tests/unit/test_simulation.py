import pytest
from app.simulation.demand_model import DemandModel
from app.simulation.engine import SimulationEngine, SimulationConfig
from app.graph.graph import RoadGraph


class TestDemandModel:
    def setup_method(self):
        self.demand_model = DemandModel()

    def test_base_demand_highway(self):
        demand = self.demand_model.get_base_demand("highway", 7, False)
        assert demand == 1000  # Morning rush (reduced from 1200 to avoid gridlock)
        
        demand = self.demand_model.get_base_demand("highway", 3, False)
        assert demand == 30  # Night
        
        demand = self.demand_model.get_base_demand("highway", 18, False)
        assert demand == 1100  # Evening rush (reduced from 1400)

    def test_base_demand_weekend(self):
        demand = self.demand_model.get_base_demand("highway", 7, True)
        assert demand == 1000 * 0.4  # Weekend morning reduced
        
        demand = self.demand_model.get_base_demand("highway", 14, True)
        assert demand > 800  # Weekend midday increased

    def test_base_demand_interpolation(self):
        # Test interpolation between defined hours
        demand_7 = self.demand_model.get_base_demand("highway", 7, False)
        demand_8 = self.demand_model.get_base_demand("highway", 8, False)
        demand_9 = self.demand_model.get_base_demand("highway", 9, False)
        
        # Morning rush peaks at 8 AM (1200), then drops at 9 AM (800)
        assert demand_7 < demand_8  # 7 AM < 8 AM (rush building)
        assert demand_8 > demand_9  # 8 AM > 9 AM (rush peak)

    def test_all_road_types(self):
        for road_type in ["highway", "major", "minor", "local"]:
            demand = self.demand_model.get_base_demand(road_type, 12, False)
            assert demand > 0


class TestSimulationEngine:
    def setup_method(self):
        # Create a minimal graph for testing
        graph = RoadGraph()
        graph.add_node("A", 0.0, 0.0)
        graph.add_node("B", 0.001, 0.0)
        graph.add_edge("R1", "A", "B", 1.0, 50, 900, "major")
        graph.add_edge("R2", "B", "A", 1.0, 50, 900, "major")
        
        config = SimulationConfig(seed=42)
        self.engine = SimulationEngine(graph=graph, config=config)

    def test_engine_initialization(self):
        assert self.engine.config.seed == 42
        assert self.engine.state.current_tick == 0
        assert self.engine.config.speed_multiplier == 1

    def test_tick_advances(self):
        initial_tick = self.engine.state.current_tick
        # Use asyncio to run the async _process_tick
        import asyncio
        asyncio.run(self.engine._process_tick())
        assert self.engine.state.current_tick == initial_tick + 1

    def test_speed_multiplier(self):
        self.engine.config.speed_multiplier = 5
        assert self.engine.config.speed_multiplier == 5
        
        # Multiple ticks should advance simulation time faster
        initial_time = self.engine.state.simulation_time
        import asyncio
        for _ in range(5):
            asyncio.run(self.engine._process_tick())
        # With 5x speed, 5 ticks = 5 simulated minutes
        assert self.engine.state.simulation_time > initial_time


if __name__ == "__main__":
    pytest.main([__file__, "-v"])