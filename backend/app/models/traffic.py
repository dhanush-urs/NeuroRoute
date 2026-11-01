from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.road import Road


class TrafficSnapshot(Base, UUIDMixin):
    __tablename__ = "traffic_snapshots"

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    road_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tick: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sim_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_veh_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    occupancy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    congestion_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    congestion_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    travel_time_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weather_condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    incident_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)

    # Relationships
    road: Mapped["Road"] = relationship("Road", back_populates="traffic_snapshots")

    def __repr__(self) -> str:
        return f"<TrafficSnapshot session={self.session_id} road={self.road_id} tick={self.tick}>"