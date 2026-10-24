import time

from fastapi import APIRouter

from app.config import get_settings
from app.integrations.sarvam_client import chat_text_result, is_configured

router = APIRouter(prefix="/api/v1/sarvam", tags=["sarvam"])

@router.get("/ping")
def ping():
    cfg = get_settings()
    configured = is_configured()
    if not configured:
        return {"configured": False, "reachable": False, "model": cfg.sarvam_convo_model, "latency_ms": 0, "error": "SARVAM_API_KEY is not configured"}
    started = time.perf_counter()
    content, error = chat_text_result([{"role": "user", "content": "Reply with OK."}])
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {"configured": True, "reachable": bool(content and content.strip()), "model": cfg.sarvam_convo_model, "latency_ms": latency_ms, "error": error or (None if content and content.strip() else "Sarvam returned empty content")}
