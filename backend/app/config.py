"""Runtime configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Support the repository-root .env and the documented backend/.env. Values
    # in backend/.env override root values when non-empty; empty template
    # assignments are ignored so they cannot mask a configured root secret.
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"), env_ignore_empty=True, extra="ignore")

    sarvam_api_key: str | None = None
    sarvam_chat_model: str = "sarvam-105b-conversations"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v4-flash"
    sarvam_tts_speaker: str | None = None
    sarvam_timeout_s: float = 25.0
    # PathoVision never uses Sarvam's text-only chat model for images. Configure
    # one of these optional vision providers on the server when image analysis is needed.
    openai_api_key: str | None = None
    # Google Gemini's OpenAI-compatible endpoint is supported by setting
    # OPENAI_BASE=https://generativelanguage.googleapis.com/v1beta/openai.
    openai_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    openai_vision_model: str | None = None
    pathovision_timeout_s: float = 50.0
    anthropic_api_key: str | None = None
    anthropic_vision_model: str = "claude-3-5-haiku-latest"
    ocr_engine: str = "tesseract"
    tesseract_cmd: str | None = None
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
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    sms_enabled: bool = False
    sms_default_country_code: str = "+91"
    ml_service_url: str = "http://127.0.0.1:8001"


settings = Settings()


def get_settings() -> Settings:
    """Compatibility accessor for optional persistence and assistant modules."""
    return settings
