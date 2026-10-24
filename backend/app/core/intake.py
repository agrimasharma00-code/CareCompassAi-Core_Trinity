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
    duration_match = re.search(r"\b(\d+\s*(?:days?|din)|(?:one|two|three|four|five)\s+days?(?:\s+ago)?|do\s+din|ek\s+din|kal\s+se|since\s+yesterday)\b", lower)
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
    """Return one focused, non-repeated intake question, up to three turns.

    A confident classifier is not a reason to skip intake.  It can predict a
    suitable route from very little text, but it cannot know useful details
    such as onset, location, severity, or associated warning symptoms.
    """
    # A clearly requested service (for example, home sample collection) is
    # already actionable. Emergency symptoms are handled before this function.
    if force_final or facts.requested_service:
        return None
    prior_text = " ".join(turn.content.lower() for turn in history)
    prior_questions = sum(1 for turn in history if turn.role.lower() == "assistant" and "?" in turn.content)
    if prior_questions >= 3:
        return None
    lower = text.lower()
    headache = any(term in lower for term in ("headache", "head ache", "head pain", "sir dard", "sar dard", "sar mein dard"))
    symptom = headache or any(term in lower for term in (
        "fever", "bukhar", "cough", "khansi", "pain", "dard", "vomit", "vomiting", "diarr", "rash", "weak", "dizzy",
    ))
    if not symptom:
        return None

    # The sequence deliberately starts with the information patients expect us
    # to ask for. The final safety screen only appears after the red-flag check.
    candidates: list[tuple[str, dict[str, str]]] = []
    if facts.duration is None:
        candidates.append(("duration", {
            "en": "When did this start? Did it begin suddenly or gradually?",
            "hi": "यह कब शुरू हुआ? अचानक हुआ या धीरे-धीरे?",
            "hinglish": "Yeh kab shuru hua? Achanak hua ya dheere-dheere?",
        }))
    if headache:
        has_headache_detail = bool(re.search(r"\b(left|right|front|back|one.side|both.sides|throbbing|pressure|pounding|[0-9]{1,2}\s*/\s*10)\b", lower))
        if not has_headache_detail:
            candidates.append(("headache_detail", {
                "en": "Where is the headache, how severe is it from 0 to 10, and does it feel throbbing or pressure-like?",
                "hi": "सिर के किस हिस्से में दर्द है, 0 से 10 में कितना तेज है, और धड़कन या दबाव जैसा लगता है?",
                "hinglish": "Headache kahan hai, 0 se 10 mein kitna severe hai, aur dhadkan ya pressure jaisa lagta hai?",
            }))
    elif "fever" in lower or "bukhar" in lower:
        if not re.search(r"\b(temperature|temp|degree|°c|°f|chills|rash)\b", lower):
            candidates.append(("fever_detail", {
                "en": "What is the highest temperature, and are there chills, a rash, vomiting, or any other main symptom?",
                "hi": "सबसे अधिक तापमान कितना रहा, और क्या ठंड लगना, रैश, उल्टी या कोई और मुख्य लक्षण है?",
                "hinglish": "Highest temperature kitna raha, aur chills, rash, vomiting ya koi aur main symptom hai?",
            }))
    elif "cough" in lower or "khansi" in lower:
        if not re.search(r"\b(dry|wet|phlegm|balgam|blood|wheez|night)\b", lower):
            candidates.append(("cough_detail", {
                "en": "Is the cough dry or with phlegm, and is there fever, wheezing, or breathlessness?",
                "hi": "खांसी सूखी है या बलगम वाली, और क्या बुखार, घरघराहट या सांस फूलना है?",
                "hinglish": "Khansi dry hai ya balgam wali, aur fever, wheezing ya saans phoolna hai?",
            }))
    else:
        candidates.append(("symptom_detail", {
            "en": "Where is the problem, how severe is it from 0 to 10, and what makes it better or worse?",
            "hi": "परेशानी कहां है, 0 से 10 में कितनी तेज है, और किससे बेहतर या बदतर होती है?",
            "hinglish": "Problem kahan hai, 0 se 10 mein kitni severe hai, aur kis se better ya worse hoti hai?",
        }))

    candidates.append(("red_flag", {
        "en": "Any sudden worst-ever symptom, trouble speaking or seeing, weakness, fainting, stiff neck, repeated vomiting, breathing trouble, chest pain, recent head injury, or pregnancy?",
        "hi": "क्या अचानक बहुत तेज लक्षण, बोलने/देखने में दिक्कत, कमजोरी, बेहोशी, गर्दन अकड़ना, बार-बार उल्टी, सांस की तकलीफ, सीने में दर्द, हाल की सिर की चोट या गर्भावस्था है?",
        "hinglish": "Kya achanak sabse tez symptom, bolne/dekhne mein dikkat, weakness, behoshi, stiff neck, repeated vomiting, saans ki dikkat, chest pain, recent head injury ya pregnancy hai?",
    }))
    for _, templates in candidates:
        question = templates[facts.language]
        normalized = question.lower().rstrip("?")
        if normalized not in prior_text:
            return question
    return None
