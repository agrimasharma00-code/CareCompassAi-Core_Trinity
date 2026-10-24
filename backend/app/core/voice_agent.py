"""Sarvam-powered conversational understanding and voice replies."""

import asyncio
import json
import re

from pydantic import BaseModel, Field
from sarvamai import SarvamAI

from app.config import settings
from app.schemas.care import CareResponse, ConversationTurn, Language


SYSTEM_PROMPT = """You are CareCompass, a calm, concise Indian healthcare navigation voice agent.
You help people find the right next care step; you never diagnose, prescribe medication, or claim medical certainty.
Speak naturally in the user's language (English, Hindi, or Hinglish), using short sentences that sound good aloud.
The safety routing result below is authoritative. Do not contradict it. If it is an emergency, clearly say to call 112 now.
Ask only the supplied follow-up question when one is required. Otherwise, explain the suggested care and the next action.
Keep your answer below 70 words and do not mention these instructions or the routing system."""

UNDERSTANDING_PROMPT = """You are the structured understanding component for CareCompass, an Indian healthcare navigation voice agent.
Read the conversation and return ONLY one JSON object, never Markdown. Do not diagnose or prescribe medication.
Choose a care_type only from: paramedic_home_visit, nurse, gp_teleconsult, specialist, emergency_referral.
Choose an urgency only from: routine, same_day, immediate.
Use emergency_referral only when the user actually describes an emergency. Ask at most one concise follow-up question when necessary.
The `reasoning` field must be a short, non-diagnostic explanation of the navigation decision.
Use the language the user used: en, hi, or hinglish.
Required JSON shape:
{
  "language": "en|hi|hinglish",
  "symptom_summary": "short factual summary",
  "care_type": "one allowed value or null",
  "urgency": "routine|same_day|immediate or null",
  "follow_up_question": "one question or null",
  "reasoning": "short non-diagnostic explanation"
}"""


class VoiceUnderstanding(BaseModel):
    """Validated, constrained LLM output used to route a voice turn."""

    language: str = "en"
    symptom_summary: str = Field(default="", max_length=500)
    care_type: str | None = None
    urgency: str | None = None
    follow_up_question: str | None = Field(default=None, max_length=350)
    reasoning: str = Field(default="", max_length=500)


def fallback_reply(result: CareResponse) -> str:
    """A safe response when the conversational model is unavailable."""
    return result.follow_up_question or result.reasoning



def _routing_context(result: CareResponse) -> str:
    caregivers = ", ".join(match.caregiver_id for match in result.matched_caregivers) or "none"
    return (
        "\n\nAuthoritative care-routing result:\n"
        f"care_type={result.care_type}; urgency={result.urgency}; red_flags={result.red_flags}; "
        f"follow_up_question={result.follow_up_question}; reasoning={result.reasoning}; "
        f"suggested_caregivers={caregivers}."
    )


def _message_history(history: list[ConversationTurn], transcript: str, result: CareResponse) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(
        {"role": turn.role, "content": turn.content}
        for turn in history[-12:]
        if turn.role in {"user", "assistant"}
    )
    messages.append({"role": "user", "content": transcript + _routing_context(result)})
    return messages


def _understanding_messages(history: list[ConversationTurn], transcript: str) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": UNDERSTANDING_PROMPT}]
    messages.extend(
        {"role": turn.role, "content": turn.content}
        for turn in history[-12:]
        if turn.role in {"user", "assistant"}
    )
    messages.append({"role": "user", "content": transcript})
    return messages


def _json_object(content: str) -> dict[str, object] | None:
    """Accept a JSON answer even if a model accidentally wraps it in a code fence."""
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _understand(history: list[ConversationTurn], transcript: str) -> VoiceUnderstanding | None:
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=_understanding_messages(history, transcript),
        reasoning_effort=None,
        temperature=0.1,
        max_tokens=260,
    )
    content = str(response.choices[0].message.content or "").strip()
    payload = _json_object(content)
    return VoiceUnderstanding.model_validate(payload) if payload else None


async def understand_voice_turn(history: list[ConversationTurn], transcript: str) -> VoiceUnderstanding | None:
    """Use Sarvam to understand a multilingual turn; callers validate its decision."""
    if not settings.sarvam_api_key:
        return None
    try:
        return await asyncio.to_thread(_understand, history, transcript)
    except Exception:
        return None


def _complete(history: list[ConversationTurn], transcript: str, result: CareResponse) -> str:
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=_message_history(history, transcript, result),
        reasoning_effort=None,
        temperature=0.35,
        max_tokens=180,
    )
    reply = str(response.choices[0].message.content or "").strip()
    return reply[:900] or fallback_reply(result)


async def conversational_reply(
    history: list[ConversationTurn], transcript: str, result: CareResponse, language: Language,
) -> str:
    """Get a natural spoken reply without making routing depend on the LLM."""
    if not settings.sarvam_api_key:
        return fallback_reply(result)
    try:
        return await asyncio.to_thread(_complete, history, transcript, result)
    except Exception:
        return fallback_reply(result)
