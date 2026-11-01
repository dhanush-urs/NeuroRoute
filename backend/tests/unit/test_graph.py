import pytest
from app.graph.graph import RoadGraph
from app.graph.node import Node
from app.graph.edge import Edge


class TestNode:
    def test_node_creation(self):
        node = Node(id="N01", latitude=40.7128, longitude=-74.0060)
        assert node.id == "N01"
        assert node.latitude == 40.7128
        assert node.longitude == -74.0060

    def test_node_equality(self):
        node1 = Node(id="N01", latitude=40.7128, longitude=-74.0060)
        node2 = Node(id="N01", latitude=40.7128, longitude=-74.0060)
        node3 = Node(id="N02", latitude=40.7128, longitude=-74.0060)
        assert node1 == node2
        assert node1 != node3


class TestEdge:
    def test_edge_creation(self):
        edge = Edge(
            id="R01",
            source="N01",
            target="N02",
            distance_km=1.5,
            speed_limit_kmh=50,
            capacity_vph=900,
            road_type="major"
        )
        assert edge.id == "R01"
        assert edge.source == "N01"
        assert edge.target == "N02"

    def test_travel_time_current(self):
        edge = Edge(
            id="R01",
            source="N01",
            target="N02",
            distance_km=1.5,
            speed_limit_kmh=50,
            capacity_vph=900,
            road_type="major"
        )
        edge.current_congestion = 0.0
        # At 50 km/h, 1.5 km takes 1.5/50 * 3600 = 108 seconds
        assert edge.travel_time_current() == pytest.approx(108, rel=0.1)

    def test_travel_time_with_congestion(self):
        edge = Edge(
            id="R01",
            source="N01",
            target="N02",
            distance_km=1.5,
            speed_limit_kmh=50,
            capacity_vph=900,
            road_type="major"
        )
        edge.current_congestion = 0.5
        # 50% congestion -> 50 * (1 - 0.5 * 0.7) = 32.5 km/h effective
        # 1.5/32.5 * 3600 = 166 seconds
        expected = 1.5 / (50 * (1 - 0.5 * 0.7)) * 3600
        assert edge.travel_time_current() == pytest.approx(expected, rel=0.1)


class TestRoadGraph:
    def setup_method(self):
        self.graph = RoadGraph()
        # Create a simple graph: N01 -> N02 -> N03
        self.graph.add_node("N01", 40.7128, -74.0060)
        self.graph.add_node("N02", 40.7138, -74.0050)
        self.graph.add_node("N03", 40.7148, -74.0040)
        
        self.graph.add_edge("R01", "N01", "N02", 1.0, 50, 900, "major")
        self.graph.add_edge("R02", "N02", "N03", 1.5, 50, 900, "major")
        self.graph.add_edge("R03", "N01", "N03", 3.0, 50, 900, "minor")  # Longer direct route

    def test_add_node(self):
        assert "N01" in self.graph.nodes
        assert "N02" in self.graph.nodes
        assert "N03" in self.graph.nodes

    def test_add_edge(self):
        assert "R01" in self.graph.edges
        assert "R02" in self.graph.edges
        assert "R03" in self.graph.edges

    def test_get_neighbors(self):
        neighbors = self.graph.get_neighbors("N01")
        assert len(neighbors) == 2  # R01 to N02, R03 to N03
        neighbor_ids = {n.target for n in neighbors}
        assert "N02" in neighbor_ids
        assert "N03" in neighbor_ids

    def test_get_edge(self):
        edge = self.graph.get_edge("R01")
        assert edge is not None
        assert edge.source == "N01"
        assert edge.target == "N02"

    def test_get_downstream_roads(self):
        downstream = self.graph.get_downstream_roads("R01")
        assert len(downstream) == 1
        assert downstream[0].id == "R02"