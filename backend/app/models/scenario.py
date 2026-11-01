from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ScenarioExecution(Base, UUIDMixin):
    __tablename__ = "scenario_executions"

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    scenario_name: Mapped[str] = mapped_column(String(64), nullable=False)
    base_tick: Mapped[int] = mapped_column(nullable=False)
    modifications: Mapped[dict] = mapped_column(JSONB, nullable=False)
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")

    def __repr__(self) -> str:
        return f"<ScenarioExecution {self.scenario_name} tick={self.base_tick}>"


class ModelRegistry(Base, UUIDMixin):
    __tablename__ = "model_registry"

    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    training_dataset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    training_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    feature_list: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    model_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<ModelRegistry {self.model_name} v{self.version} {self.algorithm}>"


class SystemMetric(Base, UUIDMixin):
    __tablename__ = "system_metrics"

    session_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(nullable=False)
    metric_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<SystemMetric {self.metric_name}={self.metric_value} {self.metric_unit or ''}>"