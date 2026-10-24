"""Low-latency microphone bridge: browser PCM -> Sarvam Realtime STT -> care route."""

import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sarvamai import AsyncSarvamAI, RealtimeAudioInput

from app.api.care import pipeline
from app.api.voice import _sarvam_audio_reply
from app.config import settings
from app.schemas.care import CareRequest, ConversationTurn, Language, Location


router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


@router.websocket("/realtime")
async def realtime_voice(socket: WebSocket) -> None:
    """Keep the API key server-side while forwarding 16-kHz mono linear16 PCM."""
    await socket.accept()
    if not settings.sarvam_api_key:
        await socket.send_json({"type": "error", "message": "Voice is not configured on the server."})
        await socket.close(code=1011)
        return
    client = AsyncSarvamAI(api_subscription_key=settings.sarvam_api_key)
    history: list[ConversationTurn] = []
    try:
        async with client.speech_to_text_realtime_streaming.connect(
            language_code="auto",
            model="saaras:v4",
            stream_type="fast",
            mode="transcribe",
            encoding="linear16",
            sample_rate=16000,
            endpointing="vad",
            silence_duration_ms=650,
            min_speech_duration_ms=250,
            prompt="CareCompass healthcare access routing; terms include fever, cough, breathing difficulty, ambulance.",
        ) as stream:
            async def send_audio() -> None:
                while True:
                    packet = await socket.receive()
                    if packet.get("bytes"):
                        encoded = base64.b64encode(packet["bytes"]).decode("ascii")
                        await stream.send_realtime_audio_input(RealtimeAudioInput(audio=encoded))
                    elif packet.get("text") == "end":
                        return

            async def receive_events() -> None:
                async for event in stream:
                    if event.event == "transcript.partial":
                        await socket.send_json({"type": "partial", "text": event.text})
                    elif event.event == "transcript.final":
                        transcript = event.text.strip()
                        if not transcript:
                            continue
                        language = Language.HI if str(getattr(event, "language", "")).startswith("hi") else Language.AUTO
                        result = pipeline.run(
                            CareRequest(
                                user_input=transcript,
                                language=language,
                                location=Location(lat=28.545, lng=77.192),
                                conversation_history=history,
                            )
                        )
                        history.append(ConversationTurn(role="user", content=transcript))
                        spoken_text = result.follow_up_question or result.reasoning
                        if result.follow_up_question:
                            history.append(ConversationTurn(role="assistant", content=result.follow_up_question))
                        audio = await _sarvam_audio_reply(spoken_text, "hi-IN" if language == Language.HI else "en-IN")
                        await socket.send_json({
                            "type": "final",
                            "transcript": transcript,
                            "response": result.model_dump(mode="json"),
                            "audio_base64": audio,
                            "audio_mime_type": "audio/wav" if audio else None,
                        })
                    elif event.event == "error":
                        await socket.send_json({"type": "error", "message": event.message})
    except WebSocketDisconnect:
        return
    except Exception:
        await socket.send_json({"type": "error", "message": "The Sarvam voice connection ended unexpectedly."})
        await socket.close(code=1011)
