from io import BytesIO
import asyncio
import wave

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import ValidationError

from app.api import voice
from app.integrations import sarvam_client
from app.core.pipeline import run
from app.core.intake import prepare
from app.schemas.care import IntakeRequest, Location


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

    def fake_transcribe(data, filename, language_code):
        seen.update(data=data, filename=filename, language_code=language_code)
        return sarvam_client.Transcription("नमस्ते", "hi-IN")

    monkeypatch.setattr(sarvam_client, "transcribe", fake_transcribe)
    response = run_stt(voice.stt(FakeUpload(wav_bytes()), "hi-IN"))
    assert response == {"transcript": "नमस्ते", "language_code": "hi-IN"}
    assert seen["filename"] == "request.wav" and seen["data"].startswith(b"RIFF") and seen["language_code"] == "hi-IN"


def test_transcribe_uses_configured_mode_and_explicit_language(monkeypatch):
    class Speech:
        def transcribe(self, **kwargs):
            seen.update(kwargs)
            return type("Response", (), {"transcript": "पापा को दो दिन से bukhar है", "language_code": "hi-IN"})()

    class Client:
        speech_to_text = Speech()

    from types import SimpleNamespace
    seen = {}
    monkeypatch.setattr(sarvam_client, "_client", lambda: Client())
    monkeypatch.setattr(sarvam_client, "get_settings", lambda: SimpleNamespace(sarvam_stt_model="saaras:v4", sarvam_stt_mode="codemix", sarvam_timeout_s=6, sarvam_api_key=""))
    result = sarvam_client.transcribe(wav_bytes(), "request.wav", "hi-IN")
    assert str(result) == "पापा को दो दिन से bukhar है"
    assert result.language_code == "hi-IN"
    assert seen["mode"] == "codemix" and seen["language_code"] == "hi-IN"


def test_transliterate_uses_sarvam_with_devanagari_target(monkeypatch):
    from types import SimpleNamespace
    seen = {}

    class Text:
        def transliterate(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(transliterated_text="मेरे सिर में दर्द है")

    monkeypatch.setattr(sarvam_client, "_client", lambda: SimpleNamespace(text=Text()))
    monkeypatch.setattr(sarvam_client, "_retry", lambda fn: (fn(), None))
    assert sarvam_client.transliterate("ਮੇਰੇ ਸਿਰ ਦਰਦ ਹੈ", "pa-IN") == "मेरे सिर में दर्द है"
    assert seen == {"input": "ਮੇਰੇ ਸਿਰ ਦਰਦ ਹੈ", "source_language_code": "pa-IN", "target_language_code": "hi-IN"}


@pytest.mark.parametrize("transcript", ["पापा को दो दिन से बुखार है", "पापा को दो दिन से bukhar है"])
def test_hindi_stt_transcripts_reach_pipeline_unchanged(monkeypatch, transcript):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: True)
    monkeypatch.setattr(sarvam_client, "transcribe", lambda data, filename, language_code: sarvam_client.Transcription(transcript, language_code))
    payload = run_stt(voice.stt(FakeUpload(wav_bytes()), "hi-IN"))
    assert payload == {"transcript": transcript, "language_code": "hi-IN"}
    request = IntakeRequest(user_input=payload["transcript"], language=payload["language_code"], location=Location(lat=28.54, lng=77.27))
    prepared, language, _ = prepare(request)
    assert request.user_input == transcript
    assert language == "Hindi"
    assert run(request)["care_type"] == "paramedic_home_visit"


def test_stt_rejects_invalid_wav(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: True)
    with pytest.raises(HTTPException) as err:
        run_stt(voice.stt(FakeUpload(b"not wav"), "hi-IN"))
    assert err.value.status_code == 400


def test_voice_endpoints_return_503_without_sarvam(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: False)
    with pytest.raises(HTTPException) as stt_err:
        run_stt(voice.stt(FakeUpload(wav_bytes()), "hi-IN"))
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


def test_sarvam_default_tts_voice_is_priya(monkeypatch):
    from types import SimpleNamespace
    seen = {}

    class TTS:
        def convert(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(audios=["aGVsbG8="])

    monkeypatch.setattr(sarvam_client, "_client", lambda: SimpleNamespace(text_to_speech=TTS()))
    monkeypatch.setattr(sarvam_client, "get_settings", lambda: SimpleNamespace(sarvam_tts_model="bulbul:v4-flash", sarvam_tts_speaker="", sarvam_timeout_s=6))
    monkeypatch.setattr(sarvam_client, "_retry", lambda fn: (fn(), None))
    assert sarvam_client.speak("नमस्ते", "Hindi") == b"hello"
    assert seen["speaker"] == "priya_hi_recovery"


