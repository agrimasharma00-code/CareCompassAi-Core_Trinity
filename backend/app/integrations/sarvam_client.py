import base64
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Type

from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=4)

def is_configured() -> bool:
    return bool(get_settings().sarvam_api_key)

def _client():
    if not is_configured():
        return None
    from sarvamai import SarvamAI
    return SarvamAI(api_subscription_key=get_settings().sarvam_api_key)

def _safe_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    key = get_settings().sarvam_api_key
    if key:
        message = message.replace(key, "[redacted]")
    return message[:240]

def _retry(fn):
    timeout = get_settings().sarvam_timeout_s
    for attempt in range(2):
        try:
            return _pool.submit(fn).result(timeout=timeout), None
        except FutureTimeout:
            return None, f"Sarvam request timed out after {timeout:g}s"
        except Exception as exc:
            if attempt == 0 and "429" in str(exc):
                time.sleep(.25)
                continue
            return None, _safe_error(exc)
    return None, "Sarvam request failed"

def _message_result(response):
    try:
        choice = response.choices[0]
        message = choice.message
        return getattr(message, "content", None), getattr(choice, "finish_reason", None)
    except Exception:
        return None, None

def _chat_text_result(messages, *, model, max_tokens, reasoning_effort_marker=False):
    if not is_configured():
        return None, "SARVAM_API_KEY is not configured"
    try:
        client = _client()
    except Exception as exc:
        return None, _safe_error(exc)
    cfg = get_settings()
    for attempt in range(2):
        kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens * (2 if attempt else 1)}
        if reasoning_effort_marker:
            kwargs.update({"reasoning_effort": None, "temperature": 0.2})
        response, error = _retry(lambda: client.chat.completions(**kwargs))
        if error:
            return None, error
        content, finish_reason = _message_result(response)
        if content is not None and finish_reason != "length":
            return content, None
        if attempt == 0:
            logger.warning("Sarvam chat returned incomplete content (finish_reason=%s); retrying with max_tokens=%d", finish_reason, max_tokens * 2)
        else:
            logger.warning("Sarvam chat returned incomplete content after retry (finish_reason=%s)", finish_reason)
    return None, "Sarvam returned incomplete content after retry"

def chat_json(system: str, user: str, schema: Type[BaseModel]) -> dict | None:
    cfg = get_settings()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    content, _error = _chat_text_result(messages, model=cfg.sarvam_chat_model, max_tokens=cfg.sarvam_max_tokens, reasoning_effort_marker=True)
    if content is None:
        return None
    try:
        cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.I | re.M).strip()
        value = json.loads(cleaned)
        return schema.model_validate(value).model_dump()
    except Exception:
        logger.warning("Sarvam chat response failed JSON/schema validation")
        return None

def chat_text(messages: list[dict]) -> str | None:
    """Send conversational messages with the Sarvam conversations model."""
    cfg = get_settings()
    content, _error = _chat_text_result(messages, model=cfg.sarvam_convo_model, max_tokens=cfg.sarvam_max_tokens)
    return content

def chat_text_result(messages: list[dict]) -> tuple[str | None, str | None]:
    """Internal status-bearing variant used by the live connectivity ping."""
    cfg = get_settings()
    return _chat_text_result(messages, model=cfg.sarvam_convo_model, max_tokens=cfg.sarvam_max_tokens)

def transcribe(data: bytes, filename: str) -> str | None:
    try:
        client = _client()
        if not client:
            return None
        import io
        response, _error = _retry(lambda: client.speech_to_text.transcribe(file=(filename, io.BytesIO(data)), model=get_settings().sarvam_stt_model, mode="transcribe"))
        return getattr(response, "transcript", None) if response else None
    except Exception:
        return None

def speak(text: str, lang: str) -> bytes | None:
    try:
        client = _client()
        if not client:
            return None
        cfg = get_settings()
        args = {"text": text, "language_code": "hi-IN" if lang in ("Hindi", "Hinglish") else "en-IN", "model": cfg.sarvam_tts_model}
        if cfg.sarvam_tts_speaker:
            args["speaker"] = cfg.sarvam_tts_speaker
        response, _error = _retry(lambda: client.text_to_speech.convert(**args))
        return base64.b64decode(response.audios[0]) if response and response.audios else None
    except Exception:
        return None
