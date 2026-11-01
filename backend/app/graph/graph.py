from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.graph.node import Node
from app.graph.edge import Edge


@dataclass
class RoadGraph:
    """Road network graph representation."""
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    
    # Adjacency lists for fast traversal
    _outgoing: Dict[str, List[Edge]] = field(default_factory=dict)
    _incoming: Dict[str, List[Edge]] = field(default_factory=dict)
    
    def add_node(self, node_id: str, latitude: float = 0.0, longitude: float = 0.0, node_type: str = "intersection") -> None:
        """Add a node to the graph."""
        from app.graph.node import Node
        node = Node(id=node_id, latitude=latitude, longitude=longitude, node_type=node_type)
        self.nodes[node.id] = node
        if node.id not in self._outgoing:
            self._outgoing[node.id] = []
        if node.id not in self._incoming:
            self._incoming[node.id] = []
    
    def add_edge(self, edge_id: str, source: str, target: str, distance_km: float, speed_limit_kmh: int, capacity_vph: int, road_type: str = "major") -> None:
        """Add an edge to the graph."""
        from app.graph.edge import Edge
        edge = Edge(
            id=edge_id,
            source=source,
            target=target,
            distance_km=distance_km,
            speed_limit_kmh=speed_limit_kmh,
            capacity_vph=capacity_vph,
            road_type=road_type
        )
        self.edges[edge.id] = edge
        
        # Update adjacency
        if edge.source not in self._outgoing:
            self._outgoing[edge.source] = []
        self._outgoing[edge.source].append(edge)
        
        if edge.target not in self._incoming:
            self._incoming[edge.target] = []
        self._incoming[edge.target].append(edge)
        
        # Ensure nodes exist
        if edge.source not in self._outgoing:
            self._outgoing[edge.source] = []
        if edge.target not in self._incoming:
            self._incoming[edge.target] = []
    
    def get_node(self, node_id: str) -> Optional["Node"]:
        """Get node by ID."""
        return self.nodes.get(node_id)
    
    def get_edge(self, edge_id: str) -> Optional["Edge"]:
        """Get edge by ID."""
        return self.edges.get(edge_id)
    
    def get_neighbors(self, node_id: str) -> List["Edge"]:
        """Get outgoing edges from a node."""
        return self._outgoing.get(node_id, [])
    
    def get_predecessors(self, node_id: str) -> List["Edge"]:
        """Get incoming edges to a node."""
        return self._incoming.get(node_id, [])
    
    def get_downstream_roads(self, road_id: str) -> List["Edge"]:
        """Get all roads downstream of a given road."""
        edge = self.edges.get(road_id)
        if not edge:
            return []
        
        # Get edges starting from the target node of this road
        return self._outgoing.get(edge.target, [])
    
    def get_upstream_roads(self, road_id: str) -> List["Edge"]:
        """Get all roads upstream of a given road."""
        edge = self.edges.get(road_id)
        if not edge:
            return []
        
        # Get edges ending at the source node of this road
        return self._incoming.get(edge.source, [])
    
    def get_road(self, road_id: str) -> Optional["Edge"]:
        """Get road by ID (alias for get_edge)."""
        return self.edges.get(road_id)
    
    async def load_from_database(self, session_factory) -> None:
        """Load graph from database."""
        from sqlalchemy import select
        from app.models.road import Road, Node
        
        async with session_factory() as session:
            # Load nodes
            result = await session.execute(select(Node))
            for node in result.scalars().all():
                self.nodes[node.node_id] = node
            
            # Load edges
            result = await session.execute(select(Road))
            for road in result.scalars().all():
                # Convert UUID to string for consistent lookup
                road_id = str(road.id)
                edge = Edge(
                    id=road_id,
                    source=road.source_node,
                    target=road.target_node,
                    distance_km=road.distance_km,
                    speed_limit_kmh=road.speed_limit_kmh,
                    capacity_vph=road.capacity_vph,
                    road_type=road.road_type,
                    geometry=road.geometry
                )
                self.edges[edge.id] = edge
        
        # Rebuild adjacency lists
        self._outgoing = {}
        self._incoming = {}
        for edge in self.edges.values():
            if edge.source not in self._outgoing:
                self._outgoing[edge.source] = []
            self._outgoing[edge.source].append(edge)
            
            if edge.target not in self._incoming:
                self._incoming[edge.target] = []
            self._incoming[edge.target].append(edge)
        
        # Ensure all nodes have entries
        for node_id in self.nodes:
            if node_id not in self._outgoing:
                self._outgoing[node_id] = []
            if node_id not in self._incoming:
                self._incoming[node_id] = []


# Import Optional at top
from typing import Optional