"""Runtime configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Keep secrets in the repository-root .env regardless of where Uvicorn starts.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    sarvam_api_key: str | None = None
    use_llm: bool = False
    immediate_threshold: float = 0.25
    max_distance_km: float = 15.0
    skill_weight: float = 0.35
    distance_weight: float = 0.25
    availability_weight: float = 0.20
    language_weight: float = 0.10
    rating_weight: float = 0.10


settings = Settings()
