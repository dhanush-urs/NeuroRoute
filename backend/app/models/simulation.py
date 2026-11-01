from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.traffic import TrafficSnapshot
    from app.models.incident import Incident
    from app.models.route import RouteCalculation
    from app.models.prediction import Prediction
    from app.models.scenario import ScenarioExecution, SystemMetric


class SimulationSession(Base, UUIDMixin):
    __tablename__ = "simulation_sessions"

    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    speed_multiplier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")

    def __repr__(self) -> str:
        return f"<SimulationSession {self.id} seed={self.seed} status={self.status}>"