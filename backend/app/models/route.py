from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.node import Node


class RouteCalculation(Base, UUIDMixin):
    __tablename__ = "route_calculations"

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    origin_node: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_node: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    route_nodes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    route_edges: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    current_eta_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_eta_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    congestion_risk: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(default=False, nullable=False)
    calculation_tick: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    route_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<RouteCalculation {self.id} {self.algorithm} rank={self.rank} recommended={self.is_recommended}>"