from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://neuroroute:neuroroute@localhost:5432/neuro_route"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Simulation
    simulation_seed: int = 42
    simulation_tick_interval_sec: float = 1.0
    simulation_default_speed: int = 1
    simulation_max_vehicles_visible: int = 200

    # ML
    model_dir: str = "/app/models"
    active_model_version: str = "latest"
    prediction_horizons: str = "5,15,30,60"
    model_inference_batch_size: int = 100

    @property
    def prediction_horizon_list(self) -> List[int]:
        return [int(h.strip()) for h in self.prediction_horizons.split(",")]

    # Routing
    routing_weights_travel_time: float = 1.0
    routing_weights_congestion: float = 0.5
    routing_weights_incident: float = 1.0
    routing_weights_risk: float = 0.3
    reroute_threshold_sec: int = 120

    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_max_message_size: int = 1048576
    ws_update_throttle_ms: int = 500

    # LLM & NVIDIA NIM
    llm_provider: str = "nvidia_nim"
    llm_local_url: str = "http://localhost:11434"
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    llm_timeout_sec: int = 15
    nvidia_api_key: Optional[str] = None
    nvidia_nim_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    nvidia_nim_timeout: float = 15.0

    # Authentication
    auth_enabled: bool = False
    auth_secret_key: str = "dev-secret-change-in-production"
    auth_algorithm: str = "HS256"
    auth_access_token_expire_minutes: int = 30
    auth_refresh_token_expire_days: int = 7
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()