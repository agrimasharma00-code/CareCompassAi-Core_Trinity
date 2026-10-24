from io import BytesIO
import asyncio
import wave

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import ValidationError

from app.api import voice
from app.integrations import sarvam_client


def run_stt(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("fake upload unexpectedly suspended")
def wav_bytes(seconds=0.1):
    stream = BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * int(16000 * seconds))
    return stream.getvalue()


class FakeUpload:
    filename = "request.wav"

    def __init__(self, data):
        self.data = data

    async def read(self, size=-1):
        return self.data[:size]


def test_stt_endpoint_uses_sarvam_transcribe_and_returns_language(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: True)
    seen = {}

    def fake_transcribe(data, filename):
        seen.update(data=data, filename=filename)
        return sarvam_client.Transcription("नमस्ते", "hi-IN")

    monkeypatch.setattr(sarvam_client, "transcribe", fake_transcribe)
    response = run_stt(voice.stt(FakeUpload(wav_bytes())))
    assert response == {"transcript": "नमस्ते", "language_code": "hi-IN"}
    assert seen["filename"] == "request.wav" and seen["data"].startswith(b"RIFF")


def test_stt_rejects_invalid_wav(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: True)
    with pytest.raises(HTTPException) as err:
        run_stt(voice.stt(FakeUpload(b"not wav")))
    assert err.value.status_code == 400


def test_voice_endpoints_return_503_without_sarvam(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: False)
    with pytest.raises(HTTPException) as stt_err:
        run_stt(voice.stt(FakeUpload(wav_bytes())))
    with pytest.raises(HTTPException) as tts_err:
        voice.tts(voice.TTSRequest(text="Hello", language="en-IN"))
    assert stt_err.value.status_code == 503 and tts_err.value.status_code == 503


def test_tts_returns_wav_and_passes_language(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: True)
    seen = {}
    monkeypatch.setattr(sarvam_client, "speak", lambda text, lang: (seen.update(text=text, lang=lang) or b"RIFFfakewav"))
    response = voice.tts(voice.TTSRequest(text="नमस्ते", language="hi-IN"))
    assert isinstance(response, Response) and response.media_type == "audio/wav"
    assert response.body == b"RIFFfakewav" and seen == {"text": "नमस्ते", "lang": "hi-IN"}


def test_tts_caps_text_at_500_characters():
    with pytest.raises(ValidationError):
        voice.TTSRequest(text="x" * 501, language="en-IN")


