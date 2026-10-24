"""Private-in-browser wellness companion; only chat turns reach Sarvam."""

import asyncio
import re

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


PROMPT = """You are SereneMind, a warm, emotionally attuned wellness companion for India.
You are ONLY a mental-wellbeing companion. Do not answer maths, coding, homework, trivia,
news, weather, product, legal, medical-diagnosis, or general-knowledge questions. For any
unrelated request, briefly say that this is outside SereneMind's role and warmly redirect the
person to feelings, stress, sleep, relationships, or coping. Do not give the requested factual
answer, calculation, code, or explanation before redirecting.
Reply naturally in the user's English, Hindi, or Hinglish. Validate feelings without diagnosing,
labelling a condition, prescribing medication, or claiming to be a therapist. First reflect the
specific feeling and context the person named. Then ask one gentle, relevant follow-up question
or offer one small practical next step. Do not give generic filler. Keep replies under 90 words.
If safety risk is mentioned, the application handles emergency support; do not minimise it or
provide self-harm instructions."""


_MATH_ONLY = re.compile(
    r"^\s*(?:(?:what(?:'s| is)|calculate|solve|answer)\s+)?[\d.]+\s*[+\-*/x×÷^]\s*[\d.]+(?:\s*[+\-*/x×÷^]\s*[\d.]+)*\s*[?=]?\s*$",
    re.IGNORECASE,
)
_OFF_TOPIC_TERMS = (
    "write code", "python code", "javascript", "programming", "debug this", "capital of ",
    "weather", "temperature in ", "cricket score", "football score", "stock price", "bitcoin",
    "recipe", "translate ", "who is the president", "homework", "solve this equation",
)


def _is_out_of_scope(text: str) -> bool:
    """Keep obvious non-wellness tasks out of the companion before they reach the LLM."""
    lowered = text.casefold().strip()
    return bool(_MATH_ONLY.fullmatch(lowered)) or any(term in lowered for term in _OFF_TOPIC_TERMS)


def _scope_reply(language: Language) -> str:
    if language == Language.HI:
        return "माफ़ कीजिए, मैं केवल मानसिक स्वास्थ्य और भावनात्मक सहारे के लिए हूँ, इसलिए गणित या दूसरे सामान्य सवाल हल नहीं कर सकती। अगर आप चाहें तो हम इस बारे में बात कर सकते हैं कि आप अभी कैसा महसूस कर रहे हैं।"
    if language == Language.HINGLISH:
        return "Sorry, main sirf mental wellbeing aur emotional support ke liye hoon, isliye maths ya general questions solve nahi karti. Agar aap chahein, hum baat kar sakte hain ki aap abhi kaisa feel kar rahe hain."
    return "Sorry, I’m a mental-wellbeing companion, so I can’t solve maths or general questions. I can stay with you and talk about how you’re feeling, stress, sleep, relationships, or a small next step that may help."


def _fallback_for(text: str) -> str:
    """A useful response is better than a blank turn if the upstream model is unavailable."""
    lowered = text.lower()
    if any(word in lowered for word in ("sleep", "insomnia", "नींद")):
        return "That sounds exhausting—poor sleep can make everything feel heavier. For the next ten minutes, could you dim the screen, take a sip of water, and tell me what usually keeps your mind awake?"
    if any(word in lowered for word in ("anxious", "anxiety", "panic", "worried", "घबर")):
        return "That sounds really intense. Let’s make the next moment smaller: put both feet on the floor and take one slow breath out longer than the breath in. Is there something specific that started this anxious feeling?"
    if any(word in lowered for word in ("low", "sad", "lonely", "alone", "miss home", "stress", "overwhelm", "दुख", "अकेल")):
        return "I’m sorry this feels so heavy. You do not have to solve all of it right now. What has been the hardest part of today—your thoughts, a situation, or feeling alone with it?"
    return "Thank you for telling me. I’m here to listen without judgment. What feels most important for me to understand about how this has been affecting you?"


def _reply(history: list[ConversationTurn], text: str) -> str:
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    messages = [{"role": "system", "content": PROMPT}]
    messages.extend({"role": turn.role, "content": turn.content} for turn in history[-10:] if turn.role in {"user", "assistant"})
    messages.append({"role": "user", "content": text})
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=messages,
        reasoning_effort=None,
        temperature=0.45,
        max_tokens=180,
    )
    return str(response.choices[0].message.content or "").strip()


@router.post("/chat")
async def wellness_chat(payload: WellnessMessage) -> dict[str, object]:
    text = payload.text.strip()
    if "Suicidal intent" in find_red_flags(text):
        reply = "I’m really glad you said this. You deserve immediate support right now—please call 112 or Tele-MANAS at 14416 (free, 24×7). If you can, move near someone you trust and do not stay alone."
        return {"reply": reply, "kind": "emergency", "suggestion": "emergency", "audio_base64": None, "audio_mime_type": None}
    language = language_from_text(text, payload.language)
    if _is_out_of_scope(text):
        reply = _scope_reply(language)
    elif not settings.sarvam_api_key:
        reply = "I’m here with you. Would a slow breath, a short journal note, or talking about what feels heaviest help right now?"
    else:
        try:
            reply = await asyncio.to_thread(_reply, payload.conversation_history, text)
            if not reply:
                reply = _fallback_for(text)
        except Exception:
            reply = _fallback_for(text)
    audio = await _sarvam_audio_reply(reply, "hi-IN" if language == Language.HI else "en-IN")
    suggestion = "breathing" if any(word in text.lower() for word in ("anxious", "anxiety", "panic", "overwhelm", "घबर")) else "journal" if any(word in text.lower() for word in ("sleep", "lonely", "alone", "sad", "stress", "नींद", "अकेल")) else "none"
    return {"reply": reply, "kind": "wellness", "suggestion": suggestion, "audio_base64": audio, "audio_mime_type": "audio/wav" if audio else None}
