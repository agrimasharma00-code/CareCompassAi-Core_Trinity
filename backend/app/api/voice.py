import io
import wave
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.integrations import sarvam_client

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 30

class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: Literal["hi-IN", "en-IN"]

async def _read_wav(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio must be 10 MB or smaller.")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
            if rate <= 0 or frames / rate > MAX_AUDIO_SECONDS:
                raise HTTPException(status_code=413, detail="Audio must be 30 seconds or shorter.")
    except (wave.Error, EOFError):
        raise HTTPException(status_code=400, detail="Upload a valid WAV audio file.")
    return data, file.filename or "recording.wav"

@router.post("/stt")
async def stt(file: UploadFile = File(...), language_code: Literal["hi-IN", "en-IN"] = Form("hi-IN")):
    if not sarvam_client.is_configured():
        raise HTTPException(status_code=503, detail="Speech transcription is unavailable because Sarvam is not configured.")
    data, filename = await _read_wav(file)
    transcript = sarvam_client.transcribe(data, filename, language_code)
    if not transcript or not str(transcript).strip():
        raise HTTPException(status_code=503, detail="Speech transcription is temporarily unavailable. Please try again or type your request.")
    return {"transcript": str(transcript).strip(), "language_code": getattr(transcript, "language_code", None)}

@router.post("/tts")
def tts(request: TTSRequest):
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="Text must not be empty.")
    if not sarvam_client.is_configured():
        raise HTTPException(status_code=503, detail="Speech playback is unavailable because Sarvam is not configured.")
    audio = sarvam_client.speak(request.text.strip(), request.language)
    if not audio:
        raise HTTPException(status_code=503, detail="Speech playback is temporarily unavailable. Please try again.")
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
