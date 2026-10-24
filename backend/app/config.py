from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    sarvam_api_key: str = ""
    use_llm: bool = False
    sarvam_chat_model: str = "sarvam-105b"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v4-flash"
    sarvam_tts_speaker: str = ""
    sarvam_timeout_s: float = 6
    emergency_threshold: float = 0.25
    followup_threshold: float = 0.5
    max_followups: int = 3
    match_top_k: int = 3
    red_flag_label_mode: str = "correct"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings(): return Settings()
