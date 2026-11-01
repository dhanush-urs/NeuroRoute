from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class Node:
    """Graph node representing a junction/intersection."""
    id: str
    latitude: float
    longitude: float
    node_type: str = "intersection"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, Node):
            return self.id == other.id
        return False