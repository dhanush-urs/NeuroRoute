from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.road import Road


class Prediction(Base, UUIDMixin):
    __tablename__ = "predictions"

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
    prediction_tick: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    predicted_congestion_score: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_avg_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    road: Mapped["Road"] = relationship("Road", back_populates="predictions")

    def __repr__(self) -> str:
        return f"<Prediction road={self.road_id} tick={self.prediction_tick} horizon={self.horizon_minutes}min>"