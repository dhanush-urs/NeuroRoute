from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.prediction import Prediction
    from app.models.traffic import TrafficSnapshot


class Road(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "roads"

    source_node: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_node: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    distance_km: Mapped[float] = mapped_column(nullable=False)
    speed_limit_kmh: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity_vph: Mapped[int] = mapped_column(Integer, nullable=False)
    road_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=True)
    num_lanes: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # Relationships
    traffic_snapshots: Mapped[list["TrafficSnapshot"]] = relationship(
        "TrafficSnapshot",
        back_populates="road",
        lazy="dynamic",
    )
    incidents: Mapped[list["Incident"]] = relationship(
        "Incident",
        back_populates="road",
        lazy="dynamic",
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        "Prediction",
        back_populates="road",
        lazy="dynamic",
    )

    __table_args__ = (
        UniqueConstraint("source_node", "target_node", name="uq_road_source_target"),
    )

    def __repr__(self) -> str:
        return f"<Road {self.id} {self.source_node}->{self.target_node}>"


class Node(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "nodes"

    node_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, default="junction")

    def __repr__(self) -> str:
        return f"<Node {self.node_id} ({self.latitude}, {self.longitude})>"