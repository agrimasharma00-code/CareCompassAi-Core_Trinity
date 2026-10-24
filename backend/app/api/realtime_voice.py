"""Low-latency microphone bridge: browser PCM -> Sarvam Realtime STT -> care route."""

import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sarvamai import AsyncSarvamAI, RealtimeAudioInput

from app.api.care import pipeline
from app.api.voice import _sarvam_audio_reply
from app.config import settings
from app.core.matching import match_caregivers
from app.core.voice_agent import VoiceUnderstanding, conversational_reply, understand_voice_turn
from app.schemas.care import CareRequest, CareResponse, CareType, ConversationTurn, Language, Location, Urgency


router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


def _language(value: str, fallback: Language) -> Language:
    normalized = value.lower().strip()
    if normalized in {"hi", "hindi"}:
        return Language.HI
    if normalized in {"hinglish", "hi-en", "hi_en"}:
        return Language.HINGLISH
    if normalized in {"en", "english"}:
        return Language.EN
    return fallback if fallback != Language.AUTO else Language.EN


def _safe_model_route(
    provisional: CareResponse,
    decision: VoiceUnderstanding | None,
    request: CareRequest,
    language: Language,
) -> CareResponse:
    """Let Sarvam choose normal care routing, while red flags remain a hard safety override."""
    if not decision or provisional.red_flags:
        return provisional
    try:
        care_type = CareType(decision.care_type) if decision.care_type else None
        urgency = Urgency(decision.urgency) if decision.urgency else None
    except ValueError:
        return provisional
    reasoning = decision.reasoning.strip()[:500] or provisional.reasoning
    question = decision.follow_up_question.strip() if decision.follow_up_question else None
    if care_type == CareType.EMERGENCY_REFERRAL:
        return CareResponse(
            care_type=CareType.EMERGENCY_REFERRAL,
            urgency=Urgency.IMMEDIATE,
            red_flags=["Sarvam voice assessment marked this as urgent."],
            reasoning=reasoning,
            matched_caregivers=[],
        )
    if question and care_type is None:
        return CareResponse(follow_up_question=question[:350], reasoning=reasoning)
    if care_type and urgency:
        user_language = _language(decision.language, language)
        matches = match_caregivers(care_type.value, request.location, user_language.value, request.user_input)
        return CareResponse(
            care_type=care_type,
            urgency=urgency,
            reasoning=reasoning,
            matched_caregivers=matches,
        )
    return provisional


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
            greeting = "Hello, I am CareCompass. Tell me what is happening, and I will help you find the right next step."
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
                        request = CareRequest(
                            user_input=transcript,
                            language=language,
                            location=Location(lat=28.545, lng=77.192),
                            conversation_history=history,
                        )
                        provisional = pipeline.run(request)
                        decision = await understand_voice_turn(history, transcript)
                        result = _safe_model_route(provisional, decision, request, language)
                        history.append(ConversationTurn(role="user", content=transcript))
                        spoken_text = await conversational_reply(history[:-1], transcript, result, language)
                        history.append(ConversationTurn(role="assistant", content=spoken_text))
                        audio = await _sarvam_audio_reply(spoken_text, "hi-IN" if language == Language.HI else "en-IN")
                        await socket.send_json({
                            "type": "final",
                            "transcript": transcript,
                            "response": result.model_dump(mode="json"),
                            "agent_reply": spoken_text,
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
