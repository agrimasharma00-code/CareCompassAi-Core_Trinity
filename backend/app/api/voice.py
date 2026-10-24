"""Server-side Sarvam speech bridge; API credentials never reach the browser."""

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.care import pipeline
from app.config import settings
from app.schemas.care import CareRequest, CareResponse, Language, Location


router = APIRouter(prefix="/api/v1/voice", tags=["voice"])
SARVAM_BASE_URL = "https://api.sarvam.ai"


async def _sarvam_audio_reply(text: str, language_code: str) -> str | None:
    """Synthesize a short route summary; TTS failure must not block routing."""
    if not settings.sarvam_api_key:
        return None


@router.post("/speak")
async def speak_reply(payload: dict[str, str]) -> dict[str, str | None]:
    """Generate a private, server-authenticated Sarvam voice response."""
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")
    audio = await _sarvam_audio_reply(text, payload.get("language_code", "en-IN"))
    return {"audio_base64": audio, "audio_mime_type": "audio/wav" if audio else None}
    payload = {
        "text": text[:2500],
        "language_code": language_code if language_code in {"en-IN", "hi-IN"} else "en-IN",
        "model": "bulbul:v4-flash",
        "output_audio_codec": "wav",
        "speaker": "anushka",
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                f"{SARVAM_BASE_URL}/text-to-speech",
                headers={"api-subscription-key": settings.sarvam_api_key},
                json=payload,
            )
            response.raise_for_status()
            return response.json().get("audios", [None])[0]
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None


@router.post("/respond")
async def voice_respond(
    audio: UploadFile = File(...),
    lat: float = 28.545,
    lng: float = 77.192,
) -> dict[str, object]:
    """Transcribe a <=30s WAV/MP3/AAC/FLAC/OGG clip, route it, and speak the reply."""
    if not settings.sarvam_api_key:
        raise HTTPException(status_code=503, detail="Voice is not configured. Set SARVAM_API_KEY on the backend.")
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="The audio recording is empty.")
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            transcription = await client.post(
                f"{SARVAM_BASE_URL}/speech-to-text",
                headers={"api-subscription-key": settings.sarvam_api_key},
                data={"model": "saaras:v4", "mode": "transcribe"},
                files={"file": (audio.filename or "care-request.wav", content, audio.content_type or "audio/wav")},
            )
            transcription.raise_for_status()
            speech = transcription.json()
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail="Sarvam could not transcribe this recording.") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Sarvam voice service is unavailable.") from error
    transcript = str(speech.get("transcript", "")).strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech was detected. Please try again.")
    detected = str(speech.get("language_code") or "en-IN")
    language = Language.HI if detected.startswith("hi") else Language.EN
    result: CareResponse = pipeline.run(
        CareRequest(user_input=transcript, language=language, location=Location(lat=lat, lng=lng))
    )
    spoken_text = result.follow_up_question or result.reasoning
    audio_base64 = await _sarvam_audio_reply(spoken_text, detected)
    return {
        "transcript": transcript,
        "response": result.model_dump(mode="json"),
        "audio_base64": audio_base64,
        "audio_mime_type": "audio/wav" if audio_base64 else None,
    }
