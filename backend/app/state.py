"""Global state accessors for NeuroRoute."""
from typing import Optional

# These will be set during app initialization
_simulation_engine = None
_road_graph = None


def set_simulation_engine(engine):
    """Set the global simulation engine instance."""
    global _simulation_engine
    _simulation_engine = engine


def get_simulation_engine():
    """Get the global simulation engine instance."""
    if _simulation_engine is None:
        raise RuntimeError("Simulation engine not initialized")
    return _simulation_engine


def set_road_graph(graph):
    """Set the global road graph instance."""
    global _road_graph
    _road_graph = graph


def get_road_graph():
    """Get the global road graph instance."""
    if _road_graph is None:
        raise RuntimeError("Road graph not initialized")
    return _road_graph