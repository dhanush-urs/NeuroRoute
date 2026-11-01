from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
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


class Incident(Base, UUIDMixin):
    __tablename__ = "incidents"

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    incident_type: Mapped[str] = mapped_column(String(32), nullable=False)
    road_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    start_tick: Mapped[int] = mapped_column(Integer, nullable=False)
    end_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_reduction_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    affected_radius_km: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    # Relationships
    road: Mapped["Road"] = relationship("Road", back_populates="incidents")

    def __repr__(self) -> str:
        return f"<Incident {self.id} type={self.incident_type} road={self.road_id} status={self.status}>"