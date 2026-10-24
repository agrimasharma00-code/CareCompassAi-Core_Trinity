"""Private-in-browser wellness companion; only chat turns reach Sarvam."""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sarvamai import SarvamAI

from app.api.voice import _sarvam_audio_reply
from app.config import settings
from app.core.red_flags import find_red_flags
from app.core.voice_agent import language_from_text
from app.schemas.care import ConversationTurn, Language

router = APIRouter(prefix="/api/v1/wellness", tags=["wellness"])


class WellnessMessage(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    language: Language = Language.AUTO


PROMPT = """You are SereneMind, a warm, concise wellness companion for India.
Reply naturally in the user's English, Hindi, or Hinglish. Validate feelings without diagnosing,
labelling a condition, prescribing medication, or claiming to be a therapist. Offer one gentle,
practical next step such as breathing, journaling, rest, or reaching out to someone. Keep replies
under 70 words. If safety risk is mentioned, the application handles emergency support; do not
minimise it or provide self-harm instructions."""


def _reply(history: list[ConversationTurn], text: str) -> str:
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    messages = [{"role": "system", "content": PROMPT}]
    messages.extend({"role": turn.role, "content": turn.content} for turn in history[-10:] if turn.role in {"user", "assistant"})
    messages.append({"role": "user", "content": text})
    response = client.chat.completions(model="sarvam-105b-conversations", messages=messages, temperature=0.45, max_tokens=160)
    return str(response.choices[0].message.content or "").strip()


@router.post("/chat")
async def wellness_chat(payload: WellnessMessage) -> dict[str, object]:
    text = payload.text.strip()
    if "Suicidal intent" in find_red_flags(text):
        return {"reply": "You deserve immediate support. Please call 112 now or Tele-MANAS at 14416 (free, 24×7). If you can, stay with someone you trust.", "kind": "emergency", "audio_base64": None}
    language = language_from_text(text, payload.language)
    if not settings.sarvam_api_key:
        reply = "I’m here with you. Would a slow breath, a short journal note, or talking about what feels heaviest help right now?"
    else:
        try:
            reply = await asyncio.to_thread(_reply, payload.conversation_history, text)
        except Exception:
            reply = "Thank you for sharing that. We can take this one small step at a time—what feels most present for you right now?"
    audio = await _sarvam_audio_reply(reply, "hi-IN" if language == Language.HI else "en-IN")
    suggestion = "breathing" if any(word in text.lower() for word in ("anxious", "anxiety", "panic", "overwhelm", "घबर")) else "journal" if any(word in text.lower() for word in ("sleep", "lonely", "alone", "sad", "stress", "नींद", "अकेल")) else "none"
    return {"reply": reply, "kind": "wellness", "suggestion": suggestion, "audio_base64": audio, "audio_mime_type": "audio/wav" if audio else None}
