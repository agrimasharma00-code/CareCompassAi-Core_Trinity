import base64, json, re, time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Type
from pydantic import BaseModel, ValidationError
from app.config import get_settings

def is_configured() -> bool: return bool(get_settings().sarvam_api_key)

def _client():
    if not is_configured(): return None
    from sarvamai import SarvamAI
    return SarvamAI(api_subscription_key=get_settings().sarvam_api_key)

_pool = ThreadPoolExecutor(max_workers=4)

def _retry(fn):
    timeout = get_settings().sarvam_timeout_s
    for attempt in range(2):
        try:
            return _pool.submit(fn).result(timeout=timeout)
        except FutureTimeout:
            return None
        except Exception as exc:
            if attempt or "429" not in str(exc): return None
            time.sleep(.25)
    return None

def chat_json(system: str, user: str, schema: Type[BaseModel]) -> dict | None:
    try:
        client=_client()
        if not client: return None
        res=_retry(lambda: client.chat.completions(model=get_settings().sarvam_chat_model,messages=[{"role":"system","content":system},{"role":"user","content":user}]))
        if res is None:return None
        content=res.choices[0].message.content
        content=re.sub(r"^```(?:json)?|```$","",content.strip(),flags=re.I|re.M).strip()
        obj=json.loads(content); return schema.model_validate(obj).model_dump()
    except (Exception, ValidationError): return None

def transcribe(data: bytes, filename: str) -> str | None:
    try:
        client=_client()
        if not client:return None
        import io
        res=_retry(lambda: client.speech_to_text.transcribe(file=(filename,io.BytesIO(data)),model=get_settings().sarvam_stt_model,mode="transcribe"))
        return getattr(res,"transcript",None) if res else None
    except Exception:return None

def speak(text: str, lang: str) -> bytes | None:
    try:
        client=_client()
        if not client:return None
        cfg=get_settings(); args={"text":text,"language_code":"hi-IN" if lang in ("Hindi","Hinglish") else "en-IN","model":cfg.sarvam_tts_model}
        if cfg.sarvam_tts_speaker:args["speaker"]=cfg.sarvam_tts_speaker
        res=_retry(lambda: client.text_to_speech.convert(**args))
        return base64.b64decode(res.audios[0]) if res and res.audios else None
    except Exception:return None
