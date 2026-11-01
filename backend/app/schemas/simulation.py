from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class SimulationStartRequest(BaseModel):
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")
    scenario_name: Optional[str] = Field(None, description="Predefined scenario to run")
    speed_multiplier: int = Field(1, ge=1, le=60, description="Simulation speed multiplier")
    config: Optional[dict] = Field(default_factory=dict)


class SimulationStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seed: int
    scenario_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    speed_multiplier: int
    current_tick: int
    sim_time: datetime
    status: str
    config: dict


class SimulationControlRequest(BaseModel):
    action: str = Field(..., description="Action: start, pause, resume, reset, speed")
    speed_multiplier: Optional[int] = Field(None, ge=1, le=60)


class ScenarioRequest(BaseModel):
    scenario_name: str = Field(..., description="Scenario to execute")
    modifications: dict = Field(default_factory=dict)


class ScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scenario_name: str
    base_tick: int
    modifications: dict
    results: Optional[dict] = None
    executed_at: datetime
    status: str