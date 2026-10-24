"""Runtime configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
