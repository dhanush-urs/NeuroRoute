import pytest
from app.graph.dijkstra import dijkstra
from app.graph.astar import astar
from app.graph.graph import RoadGraph


def create_test_graph() -> RoadGraph:
    graph = RoadGraph()
    
    # Add nodes in a grid-like pattern
    nodes = {
        "A": (0.0, 0.0),
        "B": (1.0, 0.0),
        "C": (2.0, 0.0),
        "D": (0.0, 1.0),
        "E": (1.0, 1.0),
        "F": (2.0, 1.0),
        "G": (0.0, 2.0),
        "H": (1.0, 2.0),
        "I": (2.0, 2.0),
    }
    
    for node_id, (lat, lon) in nodes.items():
        graph.add_node(node_id, lat, lon)
    
    # Add edges (bidirectional)
    edges = [
        # Row 0
        ("A", "B", 1.0), ("B", "C", 1.0),
        # Row 1
        ("D", "E", 1.0), ("E", "F", 1.0),
        # Row 2
        ("G", "H", 1.0), ("H", "I", 1.0),
        # Columns
        ("A", "D", 1.0), ("D", "G", 1.0),
        ("B", "E", 1.0), ("E", "H", 1.0),
        ("C", "F", 1.0), ("F", "I", 1.0),
        # Diagonals (longer)
        ("A", "E", 1.5), ("E", "I", 1.5),
        ("C", "E", 1.5), ("E", "G", 1.5),
    ]
    
    for i, (src, dst, dist) in enumerate(edges):
        edge_id = f"R{i}"
        graph.add_edge(edge_id, src, dst, dist, 50, 900, "major")
        graph.add_edge(f"{edge_id}_rev", dst, src, dist, 50, 900, "major")
    
    return graph


class TestDijkstra:
    def test_shortest_path_simple(self):
        graph = create_test_graph()
        
        # A to C: A->B->C = 2.0
        path = dijkstra(graph, "A", "C")
        assert path is not None
        assert path.distance == pytest.approx(2.0)
        assert path.nodes == ["A", "B", "C"]

    def test_shortest_path_multiple_routes(self):
        graph = create_test_graph()
        
        # A to I: A->B->E->H->I = 4.0 (or A->E->I = 3.0 via diagonal)
        path = dijkstra(graph, "A", "I")
        assert path is not None
        # Should find A->E->I = 3.0 (shorter)
        assert path.distance == pytest.approx(3.0)
        assert path.nodes == ["A", "E", "I"]

    def test_no_path(self):
        graph = create_test_graph()
        # Remove ALL connections to/from A to make it unreachable
        graph.edges = {k: v for k, v in graph.edges.items() if v.source != "A" and v.target != "A"}
        
        # Also need to rebuild adjacency
        graph._outgoing = {}
        graph._incoming = {}
        for edge in graph.edges.values():
            if edge.source not in graph._outgoing:
                graph._outgoing[edge.source] = []
            graph._outgoing[edge.source].append(edge)
            if edge.target not in graph._incoming:
                graph._incoming[edge.target] = []
            graph._incoming[edge.target].append(edge)
        
        path = dijkstra(graph, "A", "I")
        assert path is None

    def test_same_node(self):
        graph = create_test_graph()
        path = dijkstra(graph, "A", "A")
        assert path is not None
        assert path.distance == 0.0
        assert path.nodes == ["A"]


class TestAStar:
    def test_astar_finds_optimal_path(self):
        graph = create_test_graph()
        
        path = astar(graph, "A", "I")
        assert path is not None
        assert path.distance == pytest.approx(3.0)
        assert path.nodes == ["A", "E", "I"]

    def test_astar_vs_dijkstra_same_result(self):
        graph = create_test_graph()
        
        dijkstra_path = dijkstra(graph, "A", "I")
        astar_path = astar(graph, "A", "I")
        
        assert dijkstra_path is not None
        assert astar_path is not None
        assert dijkstra_path.distance == pytest.approx(astar_path.distance)

    def test_astar_with_congestion(self):
        graph = create_test_graph()
        
        # Add congestion to make direct diagonal slower
        for edge in graph.edges.values():
            if edge.source == "A" and edge.target == "E":
                edge.current_congestion = 0.8  # Heavy congestion
            if edge.source == "E" and edge.target == "I":
                edge.current_congestion = 0.8
        
        path = astar(graph, "A", "I", use_predictions=True)
        assert path is not None
        # Should avoid congested diagonal, take A->B->E->H->I (distance 4.0)
        # Or at minimum, the travel time should be much higher than uncongested
        assert path.travel_time > 200  # Congested route takes much longer
        # If alternative route was chosen, distance would be 4.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])