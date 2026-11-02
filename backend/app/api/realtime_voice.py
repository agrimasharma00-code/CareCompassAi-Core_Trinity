"""Low-latency microphone bridge: browser PCM -> Sarvam Realtime STT -> care route."""

import asyncio
import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sarvamai import AsyncSarvamAI, RealtimeAudioInput

from app.api.care import pipeline
from app.api.auth import verify_demo_token
from app.api.voice import _sarvam_audio_reply
from app.api.ws import hub
from app.config import settings
from app.core.live import create_alert
from app.core.patient_records import apply_skin_priority, get_patient_record
from app.core.voice_agent import conversational_reply, general_reply, is_health_concern, language_from_text, resolved_language, route_from_understanding, understand_voice_turn
from app.schemas.care import CareRequest, ConversationTurn, Language, Location


router = APIRouter(prefix="/api/v1/voice", tags=["voice"])
logger = logging.getLogger(__name__)


@router.websocket("/realtime")
async def realtime_voice(socket: WebSocket) -> None:
    """Keep the API key server-side while forwarding 16-kHz mono linear16 PCM.

    The default is the medical Niramaya agent.  The virtual-phone experience
    opts into ``?assistant=nova``; it shares the same real Sarvam STT/TTS
    transport but has a separate, general-conversation personality.
    """
    await socket.accept()
    subject = None
    token = socket.query_params.get("token")
    if token:
        try:
            claims = verify_demo_token(token)
            if claims.get("role") == "patient": subject = str(claims["sub"])
        except Exception:
            await socket.send_json({"type": "error", "message": "Your patient session expired. Sign in again to continue."})
            await socket.close(code=1008)
            return
    if not settings.sarvam_api_key:
        await socket.send_json({"type": "error", "message": "Voice is not configured on the server."})
        await socket.close(code=1011)
        return
    is_nova = socket.query_params.get("assistant", "").lower() == "nova"
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
            prompt=(
                "NOVA multilingual virtual phone assistant. It can discuss ordinary topics in English, Hindi, or Hinglish."
                if is_nova
                else "Niramaya healthcare access routing; terms include fever, cough, breathing difficulty, ambulance."
            ),
        ) as stream:
            greeting = (
                "Hello! You've reached NOVA, your AI assistant. It's great to have you here. What would you like to talk about today?"
                if is_nova
                else "Hello, I am Niramaya. Tell me what is happening, and I will help you find the right next step."
            )
            greeting_audio = await _sarvam_audio_reply(greeting, "en-IN")
            await socket.send_json({
                "type": "ready",
                "text": greeting,
                "audio_base64": greeting_audio,
                "audio_mime_type": "audio/wav" if greeting_audio else None,
            })

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
                        history.append(ConversationTurn(role="user", content=transcript))
                        if is_nova:
                            result = None
                            reply_language = language_from_text(transcript, language)
                            spoken_text = await general_reply(history[:-1], transcript, reply_language)
                        else:
                            care_turn = is_health_concern(history[:-1], transcript)
                            decision = await understand_voice_turn(history[:-1], transcript) if care_turn else None
                            reply_language = resolved_language(decision.language, language) if decision else language_from_text(transcript, language)
                            if care_turn:
                                request = CareRequest(
                                    user_input=transcript,
                                    language=language,
                                    location=Location(lat=28.545, lng=77.192),
                                    conversation_history=history[:-1],
                                )
                                provisional = pipeline.run(request)
                                result = apply_skin_priority(route_from_understanding(provisional, decision, request, language), subject)
                                record = get_patient_record(subject) if subject else {"medications": []}
                                spoken_text = await conversational_reply(history[:-1], transcript, result, reply_language, record.get("medications", []))
                            else:
                                result = None
                                spoken_text = await general_reply(history[:-1], transcript, reply_language)
                        history.append(ConversationTurn(role="assistant", content=spoken_text))
                        audio = await _sarvam_audio_reply(spoken_text, "hi-IN" if reply_language == Language.HI else "en-IN")
                        alert = None
                        if result and result.urgency and result.urgency.value == "immediate":
                            alert = create_alert({
                                "patient_name": "Voice demo patient",
                                "summary": result.handoff_summary or result.reasoning,
                                "red_flags": result.red_flags,
                                "latitude": 28.545,
                                "longitude": 77.192,
                            })
                            await hub.publish("dispatch", {"type": "alert.created", "alert": alert})
                        await socket.send_json({
                            "type": "final",
                            "transcript": transcript,
                            "response": result.model_dump(mode="json") if result else None,
                            "agent_reply": spoken_text,
                            "audio_base64": audio,
                            "audio_mime_type": "audio/wav" if audio else None,
                            "alert": alert,
                        })
                    elif event.event == "error":
                        await socket.send_json({"type": "error", "message": event.message})

            await asyncio.gather(send_audio(), receive_events())
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Niramaya real-time speech connection failed")
        try:
            await socket.send_json({
                "type": "error",
                "message": "Speech recognition stopped. Check the Sarvam key, account access or quota, and internet connection, then reconnect.",
            })
            await socket.close(code=1011)
        except RuntimeError:
            pass
