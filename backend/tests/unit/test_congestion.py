import pytest
from app.analytics.congestion import calculate_congestion, classify_congestion, propagate_congestion
from app.graph.graph import RoadGraph
from app.graph.edge import Edge


class TestCongestionCalculation:
    def test_free_flow(self):
        # Low vehicles, high speed
        road = type('Road', (), {
            'distance_km': 1.0,
            'speed_limit_kmh': 50,
            'capacity_vph': 900
        })()
        
        congestion = calculate_congestion(road, vehicles=50, avg_speed=48)
        assert congestion < 0.3  # FREE

    def test_moderate_congestion(self):
        road = type('Road', (), {
            'distance_km': 1.0,
            'speed_limit_kmh': 50,
            'capacity_vph': 900
        })()
        
        congestion = calculate_congestion(road, vehicles=300, avg_speed=35)
        assert 0.3 <= congestion < 0.5  # MODERATE

    def test_heavy_congestion(self):
        road = type('Road', (), {
            'distance_km': 1.0,
            'speed_limit_kmh': 50,
            'capacity_vph': 900
        })()
        
        congestion = calculate_congestion(road, vehicles=600, avg_speed=20)
        assert 0.5 <= congestion < 0.7  # HEAVY

    def test_severe_congestion(self):
        road = type('Road', (), {
            'distance_km': 1.0,
            'speed_limit_kmh': 50,
            'capacity_vph': 900
        })()
        
        congestion = calculate_congestion(road, vehicles=900, avg_speed=10)
        assert 0.9 <= congestion <= 1.0  # SEVERE

    def test_congestion_bounds(self):
        road = type('Road', (), {
            'distance_km': 1.0,
            'speed_limit_kmh': 50,
            'capacity_vph': 900
        })()
        
        # Extreme values should be clamped
        congestion = calculate_congestion(road, vehicles=0, avg_speed=50)
        assert congestion >= 0.0
        
        congestion = calculate_congestion(road, vehicles=2000, avg_speed=1)
        assert congestion <= 1.0


class TestCongestionClassification:
    def test_classification_boundaries(self):
        assert classify_congestion(0.0) == "free"
        assert classify_congestion(0.15) == "free"
        assert classify_congestion(0.29) == "free"
        assert classify_congestion(0.30) == "moderate"
        assert classify_congestion(0.40) == "moderate"
        assert classify_congestion(0.49) == "moderate"
        assert classify_congestion(0.50) == "heavy"
        assert classify_congestion(0.60) == "heavy"
        assert classify_congestion(0.69) == "heavy"
        assert classify_congestion(0.70) == "congested"
        assert classify_congestion(0.80) == "congested"
        assert classify_congestion(0.89) == "congested"
        assert classify_congestion(0.90) == "severe"
        assert classify_congestion(0.95) == "severe"
        assert classify_congestion(1.0) == "severe"
        assert classify_congestion(1.1) == "severe"  # Clamped


class TestCongestionPropagation:
    def test_propagation_basic(self):
        graph = RoadGraph()
        
        # Create a chain: A -> B -> C -> D
        for node_id in ["A", "B", "C", "D"]:
            graph.add_node(node_id, 0.0, 0.0)
        
        graph.add_edge("R1", "A", "B", 1.0, 50, 900, "major")
        graph.add_edge("R2", "B", "C", 1.0, 50, 900, "major")
        graph.add_edge("R3", "C", "D", 1.0, 50, 900, "major")
        
        # Set congestion on R1
        graph.edges["R1"].current_congestion = 0.8
        graph.edges["R1"].congestion_score = 0.8
        
        impacts = propagate_congestion(graph, {"R1"})
        
        # R2 should receive some impact
        assert "R2" in impacts
        assert impacts["R2"] > 0
        
        # R3 might receive less (propagation dampens)
        # Depending on implementation, might not propagate beyond 1 hop

    def test_propagation_multiple_sources(self):
        graph = RoadGraph()
        
        for node_id in ["A", "B", "C", "D"]:
            graph.add_node(node_id, 0.0, 0.0)
        
        graph.add_edge("R1", "A", "B", 1.0, 50, 900, "major")
        graph.add_edge("R2", "B", "C", 1.0, 50, 900, "major")
        graph.add_edge("R3", "A", "C", 1.5, 50, 900, "major")
        
        graph.edges["R1"].current_congestion = 0.8
        graph.edges["R1"].congestion_score = 0.8
        graph.edges["R3"].current_congestion = 0.6
        graph.edges["R3"].congestion_score = 0.6
        
        impacts = propagate_congestion(graph, {"R1", "R3"})
        
        # R2 should receive impact from both R1 and R3
        assert "R2" in impacts
        assert impacts["R2"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])