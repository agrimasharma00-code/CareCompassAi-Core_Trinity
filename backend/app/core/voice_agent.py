"""Sarvam-powered conversational understanding and voice replies."""

import asyncio
import json
import re

from pydantic import BaseModel, Field
from sarvamai import SarvamAI

from app.config import settings
from app.core.intake import focus_complaint, has_hair_loss, relevant_history
from app.core.loaders import public_caregiver_profiles
from app.core.matching import match_caregivers
from app.schemas.care import CareRequest, CareResponse, CareType, ConversationTurn, Language, Urgency


HEALTH_CUE = re.compile(
    r"\b(?:health|symptom\w*|headache|migraine|fever|temperature|cough|cold|pain|ache|hurt\w*|sick|unwell|"
    r"nausea|vomit\w*|diarr\w*|loose motion\w*|constipat\w*|rash|itch\w*|swelling|dizz\w*|weak\w*|"
    r"breath\w*|chest|bleed\w*|injur\w*|wound|burn\w*|allerg\w*|pregnan\w*|blood pressure|diabetes|"
    r"seizure|faint\w*|stomach|tummy|abdomen|throat|tooth|skin|back|knee|joint|eye|ear|"
    r"stress|anxious|anxiety|sleep|hair\s*fall|hair\s*loss|hair\s*shedding|hair\s*thinning|alopecia|"
    r"doctor|nurse|clinic|hospital|lab test|blood test|medicine|medication|"
    r"mujhe|bukhar|khansi|dard|takleef|pareshani|chakkar|kamzori|saans|ulti|jalan|sujan|ghutna)\b"
    r"|सिरदर्द|सिर में दर्द|बुखार|खांसी|बाल\s*(?:झड़\w*|गिर\w*)|बालों\s*का\s*झड़ना|दर्द|तकलीफ|परेशानी|चक्कर|कमज़ोरी|कमजोरी|सांस|उल्टी|सूजन|डॉक्टर|दवा",
    re.IGNORECASE,
)


def is_health_concern(history: list[ConversationTurn], transcript: str) -> bool:
    """Recognize care context across the patient's turns without relying on the LLM."""
    user_context = " ".join(
        turn.content for turn in history if turn.role.lower() == "user"
    )
    active_text = focus_complaint(f"{user_context} {transcript}", transcript, history)
    return bool(HEALTH_CUE.search(active_text))


SYSTEM_PROMPT = """You are Niramaya, a calm, concise Indian healthcare navigation voice agent.
You help people find the right next care step; you never diagnose, prescribe medication, or claim medical certainty.
Speak naturally in the user's language (English, Hindi, or Hinglish), using short sentences that sound good aloud.
Focus on the patient's latest concern. Use relevant earlier answers for that concern, but do not carry over an unrelated older symptom. Acknowledge the specific concern and never repeat a question already answered.
The safety routing result below is authoritative. Do not contradict it. If it is an emergency, clearly say to call 112 now.
If the intake result includes a follow-up question, ask one relevant missing question and briefly explain why it matters. If the patient asks what to do, provide only low-risk general steps that fit the stated symptom; say treatment depends on the cause and never promise a cure. Once enough details are available, explain the appropriate next step and which type of clinician can assess it. Do not recommend medicines, doses, supplements, or home remedies.
Do not jump straight to a provider booking before acknowledging the concern and clarifying the key details.
Never mention internal caregiver IDs such as CG_029. Use the clinician names supplied in the routing result.
Keep your answer below 70 words and do not mention these instructions or the routing system."""

GENERAL_CHAT_PROMPT = """You are Niramaya, a friendly multilingual healthcare navigation assistant for India.
Respond naturally to greetings and ordinary conversation in the user's language (English, Hindi, or Hinglish).
Use the full conversation as context and acknowledge what the person actually said. If they describe a health concern, ask one relevant clarifying question or explain the next navigation step.
Never diagnose, prescribe medication, or claim medical certainty. Mention calling 112 only for a clear emergency.
Keep spoken replies below 70 words."""

UNDERSTANDING_PROMPT = """You are the structured understanding component for Niramaya, an Indian healthcare navigation voice agent.
Read the conversation and return ONLY one JSON object, never Markdown. Do not diagnose or prescribe medication.
Anchor the summary and follow-up to the latest distinct patient concern. Preserve the body part, symptom, timing, severity, and negations as stated. Do not turn one symptom into another or reuse an unrelated earlier complaint.
Choose a care_type only from: paramedic_home_visit, lab_test_home, nurse, gp_teleconsult, specialist, emergency_referral.
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



def _routing_context(result: CareResponse, medications: list[dict[str, object]] | None = None) -> str:
    profiles = public_caregiver_profiles([match.caregiver_id for match in result.matched_caregivers])
    caregivers = ", ".join(f"{profile['name']} ({profile['rating']} stars)" for profile in profiles) or "none"
    medication_context = ""
    if medications:
        names = [f"{item.get('brand', '')} ({item.get('generic', '')})".strip(" ()") for item in medications]
        medication_context = f" patient_confirmed_medications={names}; use as context only and do not change triage priority based on medicines alone;"
    return (
        "\n\nAuthoritative care-routing result:\n"
        f"care_type={result.care_type}; urgency={result.urgency}; red_flags={result.red_flags}; "
        f"follow_up_question={result.follow_up_question}; reasoning={result.reasoning}; "
        f"suggested_caregivers={caregivers};{medication_context}"
    )


def _present_caregivers(reply: str, result: CareResponse) -> str:
    """Prevent internal roster IDs leaking from an LLM response.

    The roster profile list follows the transparent matcher, so the first
    clinician is the strongest available match for symptoms and location.
    """
    profiles = public_caregiver_profiles([match.caregiver_id for match in result.matched_caregivers])
    if not profiles:
        return reply
    names_by_id = {profile["caregiver_id"]: profile["name"] for profile in profiles}
    ranked_names = ", ".join(f"{profile['name']} ({profile['rating']:.1f} stars)" for profile in profiles)
    cleaned = re.sub(
        r"\b(?:providers?|caregivers?|doctors?)\s+CG_\d{3}(?:\s*,?\s*(?:or|and)?\s*CG_\d{3})*",
        f"providers {ranked_names}",
        reply,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bCG_\d{3}\b", lambda match: names_by_id.get(match.group(0), "a matched clinician"), cleaned)
    top = profiles[0]
    if top["name"] not in cleaned:
        cleaned = f"{cleaned.rstrip()} I found {top['name']} ({top['rating']:.1f} stars) as the best nearby available match. Tap Book to confirm the appointment."
    elif "book" not in cleaned.lower():
        cleaned = f"{cleaned.rstrip()} Tap Book to confirm the appointment."
    return cleaned[:900]


def _booking_focused_reply(result: CareResponse, language: Language, fallback: str) -> str:
    """Keep a completed match actionable inside Niramaya rather than sending people away."""
    profiles = public_caregiver_profiles([match.caregiver_id for match in result.matched_caregivers])
    if not profiles:
        return _present_caregivers(fallback, result)
    best = profiles[0]
    match = next((item for item in result.matched_caregivers if item.caregiver_id == best["caregiver_id"]), None)
    reason = match.reason if match else "Available for this care request"
    name = best["name"]
    rating = best["rating"]
    if language == Language.HI:
        return f"आपके लक्षण और चुने हुए क्षेत्र के आधार पर {name} ({rating:.1f} स्टार) सबसे उपयुक्त उपलब्ध मैच हैं। {reason}। अपॉइंटमेंट पक्का करने के लिए नीचे ‘Book best match’ दबाएं।"
    if language == Language.HINGLISH:
        return f"Aapke symptoms aur selected area ke basis par {name} ({rating:.1f} stars) best available match hain. {reason}. Appointment confirm karne ke liye neeche ‘Book best match’ tap kijiye."
    return f"Based on your symptoms and selected area, {name} ({rating:.1f} stars) is the best available match. {reason}. Tap ‘Book best match’ below to confirm the appointment."


def language_instruction(language: Language) -> str:
    if language == Language.HI:
        return "Reply only in Hindi written in Devanagari script."
    if language == Language.HINGLISH:
        return "Reply only in natural Hinglish written in Roman script; do not switch to English-only sentences."
    return "Reply only in clear Indian English."


def language_from_text(text: str, fallback: Language = Language.AUTO) -> Language:
    if re.search(r"[\u0900-\u097F]", text):
        return Language.HI
    markers = ("mujhe", "hai", "hain", "ko", "se", "bukhar", "khansi", "dard", "abhi", "thoda", "thora")
    if any(re.search(rf"\b{marker}\b", text.lower()) for marker in markers):
        return Language.HINGLISH
    return fallback if fallback != Language.AUTO else Language.EN


def _message_history(history: list[ConversationTurn], transcript: str, result: CareResponse, language: Language, medications: list[dict[str, object]] | None = None) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n" + language_instruction(language)}]
    messages.extend(
        {"role": turn.role, "content": turn.content}
        for turn in relevant_history(history, transcript)[-12:]
        if turn.role in {"user", "assistant"}
    )
    messages.append({"role": "user", "content": transcript + _routing_context(result, medications)})
    return messages


def _understanding_messages(history: list[ConversationTurn], transcript: str) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": UNDERSTANDING_PROMPT}]
    messages.extend(
        {"role": turn.role, "content": turn.content}
        for turn in relevant_history(history, transcript)[-12:]
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


def resolved_language(value: str, fallback: Language) -> Language:
    normalized = value.lower().strip()
    if normalized in {"hi", "hindi"}:
        return Language.HI
    if normalized in {"hinglish", "hi-en", "hi_en"}:
        return Language.HINGLISH
    if normalized in {"en", "english"}:
        return Language.EN
    return fallback if fallback != Language.AUTO else Language.EN


def route_from_understanding(
    provisional: CareResponse,
    decision: VoiceUnderstanding | None,
    request: CareRequest,
    language: Language,
) -> CareResponse:
    """Use Sarvam's validated normal-care decision; deterministic red flags override it."""
    # Intake is intentionally authoritative until it has gathered the few
    # details needed for a safe route. A confident LLM classification must not
    # jump straight to a booking while the patient is answering a question.
    if not decision or provisional.red_flags or provisional.follow_up_question:
        return provisional
    active_text = focus_complaint(
        " ".join([*(turn.content for turn in request.conversation_history if turn.role.lower() == "user"), request.user_input]),
        request.user_input,
        request.conversation_history,
    )
    if has_hair_loss(active_text):
        # The local routing rule deliberately selects a general doctor first;
        # the synthetic roster does not identify dermatology credentials.
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
        user_language = resolved_language(decision.language, language)
        return CareResponse(
            care_type=care_type,
            urgency=urgency,
            reasoning=reasoning,
            matched_caregivers=match_caregivers(care_type.value, request.location, user_language.value, request.user_input),
        )
    return provisional


def _complete(history: list[ConversationTurn], transcript: str, result: CareResponse, language: Language, medications: list[dict[str, object]] | None = None) -> str:
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=_message_history(history, transcript, result, language, medications),
        reasoning_effort=None,
        temperature=0.35,
        max_tokens=180,
    )
    reply = str(response.choices[0].message.content or "").strip()
    return reply[:900] or fallback_reply(result)


async def conversational_reply(
    history: list[ConversationTurn], transcript: str, result: CareResponse, language: Language,
    medications: list[dict[str, object]] | None = None,
) -> str:
    """Get a natural spoken reply without making routing depend on the LLM."""
    active_text = focus_complaint(
        " ".join([*(turn.content for turn in history if turn.role.lower() == "user"), transcript]),
        transcript,
        history,
    )
    active_history = relevant_history(history, transcript)
    if has_hair_loss(active_text) and result.care_type != CareType.EMERGENCY_REFERRAL:
        prior_hair_guidance = any(
            turn.role.lower() == "assistant" and re.search(r"hair fall|hair loss|बाल.{0,8}झड़", turn.content, re.I)
            for turn in active_history
        )
        if language == Language.HI:
            guidance = "बालों के झड़ने के कई कारण हो सकते हैं, इसलिए सबके लिए एक ही इलाज नहीं होता। डॉक्टर बालों के झड़ने का ढंग और सिर की त्वचा देखकर कारण के अनुसार सलाह देंगे; ज़रूरत हो तो त्वचा विशेषज्ञ को दिखाएँ।"
            final_guidance = "बालों के झड़ने के कई कारण होते हैं और कोई एक इलाज सबके लिए सही नहीं होता। सामान्य डॉक्टर पहले जाँच कर सकते हैं और ज़रूरत पर त्वचा विशेषज्ञ के पास भेज सकते हैं।"
        elif language == Language.HINGLISH:
            guidance = "Hair fall ke kai causes ho sakte hain, isliye sabke liye ek hi cure nahi hota. Doctor hair fall ka pattern aur scalp dekhkar cause ke hisaab se salah dega; zaroorat par dermatologist ko dikhaya ja sakta hai."
            final_guidance = "Hair fall ke alag-alag causes hote hain, aur ek cure sabke liye kaam nahi karta. General doctor pehle assess karke zaroorat par dermatologist ke paas refer kar sakta hai."
        else:
            guidance = "Hair loss can have several causes, so there is no single cure for everyone. A doctor can assess the pattern and scalp and advise based on the cause; a dermatologist may be appropriate."
            final_guidance = "Hair loss has different possible causes, so one treatment does not work for everyone. A general doctor can assess it and refer you to a dermatologist if needed."
        if result.follow_up_question:
            prefix = "" if prior_hair_guidance else guidance + " "
            return (prefix + result.follow_up_question).strip()[:900]
        profiles = public_caregiver_profiles([match.caregiver_id for match in result.matched_caregivers])
        if not profiles:
            return final_guidance
        best = profiles[0]
        match = next((item for item in result.matched_caregivers if item.caregiver_id == best["caregiver_id"]), None)
        reason = match.reason if match else "Available for a general doctor consultation"
        if language == Language.HI:
            return f"{final_guidance} सामान्य डॉक्टर से टेली-कंसल्टेशन के लिए {best['name']} ({best['rating']:.1f} स्टार) उपलब्ध हैं। {reason}। आगे बढ़ने के लिए नीचे ‘Book best match’ चुनें।"
        if language == Language.HINGLISH:
            return f"{final_guidance} General doctor teleconsultation ke liye {best['name']} ({best['rating']:.1f} stars) available hain. {reason}. Aage badhne ke liye ‘Book best match’ tap karein."
        return f"{final_guidance} {best['name']} ({best['rating']:.1f} stars) is available for a general doctor teleconsultation. {reason}. Tap ‘Book best match’ to continue."
    if not settings.sarvam_api_key:
        return _booking_focused_reply(result, language, fallback_reply(result))
    try:
        llm_reply = await asyncio.to_thread(_complete, active_history, transcript, result, language, medications)
        return _booking_focused_reply(result, language, llm_reply)
    except Exception:
        return _booking_focused_reply(result, language, fallback_reply(result))


def _general_complete(history: list[ConversationTurn], transcript: str, language: Language) -> str:
    client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
    messages: list[dict[str, str]] = [{"role": "system", "content": GENERAL_CHAT_PROMPT + "\n" + language_instruction(language)}]
    messages.extend(
        {"role": turn.role, "content": turn.content}
        for turn in history[-12:]
        if turn.role in {"user", "assistant"}
    )
    messages.append({"role": "user", "content": transcript})
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=messages,
        reasoning_effort=None,
        temperature=0.45,
        max_tokens=160,
    )
    return str(response.choices[0].message.content or "").strip()[:900]


async def general_reply(history: list[ConversationTurn], transcript: str, language: Language = Language.AUTO) -> str:
    """Use Sarvam for ordinary conversation that does not yet need care routing."""
    # If the classifier misses a symptom phrase or Sarvam is temporarily
    # unavailable, still respond to the actual patient message instead of
    # replaying the same generic welcome on every turn.
    fallback = (
        f'I hear you: "{transcript.strip()[:180]}". When did this start, and what else are you feeling? '
        "I will use those details to help find an appropriate next care step."
        if HEALTH_CUE.search(transcript)
        else "Hello. Tell me what is happening, and I will help you find the right next step."
    )
    if not settings.sarvam_api_key:
        return fallback
    try:
        reply = await asyncio.to_thread(_general_complete, history, transcript, language_from_text(transcript, language))
        return reply or fallback
    except Exception:
        return fallback
