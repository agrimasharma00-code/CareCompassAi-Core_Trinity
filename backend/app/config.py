"""Runtime configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Keep secrets in the repository-root .env regardless of where Uvicorn starts.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    sarvam_api_key: str | None = None
    sarvam_chat_model: str = "sarvam-105b-conversations"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v4-flash"
    sarvam_tts_speaker: str | None = None
    sarvam_timeout_s: float = 25.0
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'niramaya.db'}"
    demo_password: str | None = None
    use_llm: bool = False
    immediate_threshold: float = 0.25
    max_distance_km: float = 15.0
    skill_weight: float = 0.35
    distance_weight: float = 0.25
    availability_weight: float = 0.20
    language_weight: float = 0.10
    rating_weight: float = 0.10


settings = Settings()


def get_settings() -> Settings:
    """Compatibility accessor for optional persistence and assistant modules."""
    return settings
