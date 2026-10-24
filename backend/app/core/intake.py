"""Input extraction and deliberately limited follow-up handling."""

import json
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.schemas.care import ConversationTurn, Language


@dataclass(frozen=True)
class IntakeFacts:
    language: str
    duration: str | None
    age: int | None
    relation: str | None
    requested_service: str | None


class SarvamExtractor:
    """Optional adapter. Errors are intentionally invisible to the routing flow."""

    endpoint = "https://api.sarvam.ai/v1/chat/completions"

    def extract(self, text: str) -> IntakeFacts | None:
        if not settings.use_llm or not settings.sarvam_api_key:
            return None
        prompt = (
            "Extract only JSON keys language, duration, age, relation, requested_service from this "
            "health routing message. Use null when absent. Do not diagnose: " + text
        )
        try:
            response = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {settings.sarvam_api_key}"},
                json={"model": "sarvam-m", "messages": [{"role": "user", "content": prompt}]},
                timeout=4.0,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
            return IntakeFacts(
                language=str(data.get("language") or detect_language(text)),
                duration=_as_text(data.get("duration")),
                age=_as_age(data.get("age")),
                relation=_as_text(data.get("relation")),
                requested_service=_as_text(data.get("requested_service")),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


def _as_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _as_age(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text):
        return Language.HI.value
    lower = text.lower()
    markers = ("mujhe", "ko", "hai", "hain", "se", "bukhar", "khansi", "dard", "saans", "kal")
    return Language.HINGLISH.value if any(re.search(rf"\b{marker}\b", lower) for marker in markers) else Language.EN.value


def extract_facts(text: str, requested_language: Language) -> IntakeFacts:
    """Extract deterministic safety facts; Sarvam enrichment occurs in voice_agent.py."""
    language = detect_language(text) if requested_language == Language.AUTO else requested_language.value
    lower = text.lower()
    duration_match = re.search(r"\b(\d+\s*(?:days?|din)|do\s+din|ek\s+din|kal\s+se|since\s+yesterday)\b", lower)
    age_match = re.search(r"\b(\d{1,3})\s*(?:years? old|yr(?:s)?|saal)\b", lower)
    relation_match = re.search(r"\b(papa|father|dad|mummy|mother|mom|dadi|grandmother|baby|child|infant)\b", lower)
    service_patterns = {
        "paramedic_home_visit": ("home visit", "vitals"),
        "lab_test_home": ("sample collection", "blood sample", "lab test", "blood test"),
        "nurse": ("nurse", "dressing", "wound care"),
        "gp_teleconsult": ("teleconsult", "video consult", "doctor call"),
    }
    service = next((name for name, terms in service_patterns.items() if any(term in lower for term in terms)), None)
    rule_facts = IntakeFacts(
        language=language,
        duration=duration_match.group(1) if duration_match else None,
        age=int(age_match.group(1)) if age_match else None,
        relation=relation_match.group(1) if relation_match else None,
        requested_service=service,
    )
    # Do not invoke the deprecated legacy extractor here. The active voice/chat route
    # performs one validated Sarvam 105B structured-understanding call per turn.
    return rule_facts


def next_follow_up(
    facts: IntakeFacts,
    text: str,
    history: list[ConversationTurn],
    confidence: float,
    force_final: bool = False,
) -> str | None:
    """Return one non-repeated question, with a maximum of three across a chat."""
    # A clearly requested service (for example, home sample collection) is
    # already actionable; avoid asking a generic symptom-duration question.
    if force_final or facts.requested_service or confidence >= 0.7:
        return None
    prior_text = " ".join(turn.content.lower() for turn in history)
    prior_questions = sum(1 for turn in history if turn.role.lower() == "assistant" and "?" in turn.content)
    if prior_questions >= 3:
        return None
    potentially_serious = any(term in text.lower() for term in ("fever", "bukhar", "cough", "khansi", "pain", "dard"))
    candidates: list[tuple[str, dict[str, str]]] = []
    if potentially_serious:
        candidates.append(("red_flag", {"en": "Is there any breathing trouble, chest pain, fainting, heavy bleeding, or seizure?", "hi": "क्या सांस की तकलीफ, सीने में दर्द, बेहोशी, ज्यादा खून या दौरा है?", "hinglish": "Kya saans ki dikkat, seene mein dard, behoshi, zyada khoon ya daura hai?"}))
    if facts.age is None and (facts.relation is not None or potentially_serious):
        candidates.append(("age", {"en": "What is the person's age?", "hi": "मरीज की उम्र क्या है?", "hinglish": "Patient ki umar kya hai?"}))
    if facts.duration is None:
        candidates.append(("duration", {"en": "How long has this been happening?", "hi": "यह कब से हो रहा है?", "hinglish": "Yeh kab se ho raha hai?"}))
    for _, templates in candidates:
        question = templates[facts.language]
        normalized = question.lower().rstrip("?")
        if normalized not in prior_text:
            return question
    return None
