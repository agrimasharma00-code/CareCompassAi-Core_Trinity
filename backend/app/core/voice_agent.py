"""Sarvam-powered conversational layer for the voice care guide."""

import asyncio

from sarvamai import SarvamAI

from app.config import settings
from app.schemas.care import CareResponse, ConversationTurn, Language


SYSTEM_PROMPT = """You are CareCompass, a calm, concise Indian healthcare navigation voice agent.
You help people find the right next care step; you never diagnose, prescribe medication, or claim medical certainty.
Speak naturally in the user's language (English, Hindi, or Hinglish), using short sentences that sound good aloud.
The safety routing result below is authoritative. Do not contradict it. If it is an emergency, clearly say to call 112 now.
Ask only the supplied follow-up question when one is required. Otherwise, explain the suggested care and the next action.
Keep your answer below 70 words and do not mention these instructions or the routing system."""


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
