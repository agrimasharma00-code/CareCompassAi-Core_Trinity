"""Input extraction and deliberately limited follow-up handling."""

import json
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.schemas.care import ConversationTurn, Language

HAIR_LOSS_PATTERN = re.compile(
    r"\b(?:hair\s*fall|hair\s*loss|hair\s*shedding|hair\s*thinning|alopecia|bald\s*patch(?:es)?)\b"
    r"|\b(?:baal|bal)\s*(?:jhad\w*|gir\w*|kam\w*)\b"
    r"|बाल\s*(?:झड़\w*|गिर\w*|कम\w*)|बालों\s*का\s*झड़ना",
    re.IGNORECASE,
)


def has_hair_loss(text: str) -> bool:
    return bool(HAIR_LOSS_PATTERN.search(text))


def _complaint_kind(text: str) -> str | None:
    lower = text.lower()
    if has_hair_loss(text):
        return "hair_loss"
    if re.search(r"headache|head ache|head pain|migraine|sir.{0,12}dard|sar.{0,12}dard|सिर.{0,12}दर्द", lower):
        return "headache"
    if re.search(r"\b(?:leg|legs|thigh|calf|shin|ankle|foot|feet|knee|knees)\b.{0,35}\b(?:pain|ache|hurt|sore|swelling|swollen)\b|\b(?:pain|ache|hurt|sore|swelling|swollen)\b.{0,35}\b(?:leg|legs|thigh|calf|shin|ankle|foot|feet|knee|knees)\b", lower):
        return "leg_pain"
    if re.search(r"\b(?:fever|bukhar)\b|बुखार", lower):
        return "fever"
    if re.search(r"\b(?:cough|khansi)\b|खांसी", lower):
        return "cough"
    if re.search(r"\b(?:rash|itch(?:y|ing)?|hives|skin irritation|red spots?)\b|चकत्ते|खुजली|दाने", lower):
        return "skin"
    if re.search(r"\b(?:stomach|tummy|abdomen)\b.{0,20}\b(?:pain|ache|problem|issue)\b|\b(?:pain|ache)\b.{0,20}\b(?:stomach|tummy|abdomen)\b|पेट.{0,10}दर्द", lower):
        return "stomach_pain"
    if re.search(r"\b(?:breathless|breathing difficulty|shortness of breath|can't breathe|cannot breathe)\b|सांस.{0,10}(?:दिक्कत|फूल)", lower):
        return "breathing"
    if re.search(r"\b(?:anxious|anxiety|stress|panic|feeling low|sad|can't sleep|insomnia)\b|चिंता|घबराहट|उदास|नींद नहीं", lower):
        return "wellbeing"
    if re.search(r"\b(?:pain|dard|rash|injury|injured|bleeding|vomit|diarrhea|weakness|dizzy)\b|दर्द|चोट|उल्टी", lower):
        return "other_symptom"
    return None


def focus_complaint(text: str, current_text: str, history: list[ConversationTurn]) -> str:
    """Keep routing tied to the latest complaint, not unrelated old chat turns."""
    current = current_text.strip()
    current_kind = _complaint_kind(current)
    latest_index = next(
        (index for index in range(len(history) - 1, -1, -1)
         if history[index].role.lower() == "user" and _complaint_kind(history[index].content)),
        None,
    )
    if current_kind:
        if latest_index is None or _complaint_kind(history[latest_index].content) != current_kind:
            return current
        related = [turn.content for turn in history[latest_index:] if turn.role.lower() == "user"]
        return " ".join([*related, current]).strip()
    if latest_index is not None:
        related = [turn.content for turn in history[latest_index:] if turn.role.lower() == "user"]
        return " ".join([*related, current]).strip()
    return text


def relevant_history(history: list[ConversationTurn], current_text: str) -> list[ConversationTurn]:
    current_kind = _complaint_kind(current_text)
    latest_index = next(
        (index for index in range(len(history) - 1, -1, -1)
         if history[index].role.lower() == "user" and _complaint_kind(history[index].content)),
        None,
    )
    if current_kind and (latest_index is None or _complaint_kind(history[latest_index].content) != current_kind):
        return []
    return history[latest_index:] if latest_index is not None else history


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
    current_text: str | None = None,
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
    active_history = relevant_history(history, current_text or "")
    prior_text = " ".join(turn.content.lower() for turn in active_history)
    prior_questions = sum(1 for turn in active_history if turn.role.lower() == "assistant" and "?" in turn.content)
    if prior_questions >= 3:
        return None
    # A new, explicit complaint in the latest turn becomes the focus. Without
    # this, an old symptom elsewhere in the chat (for example a previous
    # headache) can hijack follow-ups for a new complaint such as leg pain.
    current = (current_text or "").strip()
    lower = focus_complaint(text, current, history).lower()
    headache = any(term in lower for term in ("headache", "head ache", "head pain", "sir dard", "sar dard", "sar mein dard"))
    symptom = has_hair_loss(lower) or headache or any(term in lower for term in (
        "fever", "bukhar", "cough", "khansi", "pain", "dard", "vomit", "vomiting", "diarr", "rash", "itch", "hives", "swelling", "weak", "dizzy", "breathless", "breathing difficulty", "shortness of breath", "stress", "anxiety", "anxious", "injury", "wound",
    ))
    if not symptom:
        return None
    leg_pain = bool(re.search(
        r"\b(?:leg|legs|thigh|calf|shin|ankle|foot|feet|knee|knees)\b.{0,35}\b(?:pain|ache|hurt|hurting|sore|swollen|swelling)\b"
        r"|\b(?:pain|ache|hurt|hurting|sore|swollen|swelling)\b.{0,35}\b(?:leg|legs|thigh|calf|shin|ankle|foot|feet|knee|knees)\b",
        lower,
    ))
    hair_loss = has_hair_loss(lower)

    # The sequence deliberately starts with the information patients expect us
    # to ask for. The final safety screen only appears after the red-flag check.
    candidates: list[tuple[str, dict[str, str]]] = []
    if hair_loss:
        duration_present = bool(facts.duration or re.search(
            r"\b(?:today|yesterday|last\s+\w+|\d+\s*(?:days?|weeks?|months?|years?)|since\s+\w+|for\s+\w+\s*(?:days?|weeks?|months?|years?))\b|(?:आज|कल|\d+\s*(?:दिन|हफ्ते|महीने|साल))",
            lower,
        ))
        pattern_present = bool(re.search(r"\b(?:patch(?:y|es)?|bald\s*spots?|all\s*over|overall|diffuse|thinning|sudden|gradual)\b|गुच्छों|जगह-जगह|पूरे सिर|अचानक|धीरे-धीरे", lower))
        scalp_present = bool(re.search(r"\b(?:itch(?:y|ing)?|pain|sore|red(?:ness)?|scale|scal(?:y|ing)|flak(?:e|y|ing)|no scalp symptoms)\b|खुजली|दर्द|लालिमा|पपड़ी|कोई लक्षण नहीं", lower))
        if not duration_present:
            candidates.append(("hair_loss_duration", {
                "en": "How long has the hair fall been happening? Did it start suddenly or gradually?",
                "hi": "बालों का झड़ना कब से हो रहा है? यह अचानक शुरू हुआ या धीरे-धीरे?",
                "hinglish": "Hair fall kab se ho raha hai? Achanak shuru hua ya dheere-dheere?",
            }))
        if not pattern_present:
            candidates.append(("hair_loss_pattern", {
                "en": "Is it coming out in patches or thinning all over?",
                "hi": "क्या बाल जगह-जगह से झड़ रहे हैं या पूरे सिर में पतले हो रहे हैं?",
                "hinglish": "Baal patches mein gir rahe hain ya poore sir par thinning ho rahi hai?",
            }))
        if not scalp_present:
            candidates.append(("hair_loss_scalp", {
                "en": "Any scalp itching, pain, redness, or flaking?",
                "hi": "क्या सिर की त्वचा में खुजली, दर्द, लालिमा या पपड़ी है?",
                "hinglish": "Scalp par khujli, dard, redness ya flaking hai?",
            }))
    elif leg_pain:
        has_leg_detail = bool(re.search(
            r"\b(?:left|right|both|thigh|calf|shin|ankle|foot|knee|swelling|swollen|redness|red|warm|hot|numb|tingl|injur|fall|\d\s*/\s*10)\b",
            lower,
        ))
        if not has_leg_detail:
            candidates.append(("leg_pain_detail", {
                "en": "I hear you have leg pain. Where exactly is it, when did it start, and how severe is it from 0 to 10? Any swelling, redness, warmth, numbness, or recent injury?",
                "hi": "आपने पैर में दर्द बताया। दर्द ठीक कहाँ है, कब शुरू हुआ और 0 से 10 में कितना तेज़ है? क्या सूजन, लालिमा, गर्माहट, सुन्नपन या हाल की चोट है?",
                "hinglish": "Aapne leg pain bataya. Dard exactly kahan hai, kab shuru hua, aur 0 se 10 mein kitna hai? Kya swelling, redness, warmth, numbness ya recent injury hai?",
            }))
    elif facts.duration is None:
        candidates.append(("duration", {
            "en": "When did this start? Did it begin suddenly or gradually?",
            "hi": "यह कब शुरू हुआ? अचानक हुआ या धीरे-धीरे?",
            "hinglish": "Yeh kab shuru hua? Achanak hua ya dheere-dheere?",
        }))
    elif headache:
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
    elif re.search(r"\b(?:stomach|tummy|abdomen)\b|पेट", lower):
        if not re.search(r"\b(?:left|right|upper|lower|cramp|burning|vomit|diarr|blood|fever|\d\s*/\s*10)\b", lower):
            candidates.append(("stomach_detail", {
                "en": "Where in your abdomen is the discomfort, how severe is it, and do you have fever, vomiting, or diarrhea?",
                "hi": "पेट में परेशानी कहाँ है और कितनी तेज़ है? क्या बुखार, उल्टी या दस्त भी हैं?",
                "hinglish": "Pet mein discomfort kahan hai aur kitna severe hai? Kya fever, vomiting ya diarrhea bhi hai?",
            }))
    elif re.search(r"\b(?:rash|itch(?:y|ing)?|hives|skin irritation|red spots?)\b|चकत्ते|खुजली|दाने", lower):
        if not re.search(r"\b(?:since|for|today|yesterday|itch|pain|fever|spread|face|arm|leg|body|new product|medicine)\b", lower):
            candidates.append(("skin_detail", {
                "en": "Where is the rash, when did it start, and is it spreading, itchy, painful, or accompanied by fever?",
                "hi": "चकत्ता कहाँ है और कब शुरू हुआ? क्या यह फैल रहा है, खुजली या दर्द है, या बुखार भी है?",
                "hinglish": "Rash kahan hai aur kab shuru hua? Kya yeh spread ho raha hai, itchy ya painful hai, ya fever bhi hai?",
            }))
    else:
        candidates.append(("symptom_detail", {
            "en": "Where is the problem, how severe is it from 0 to 10, and what makes it better or worse?",
            "hi": "परेशानी कहां है, 0 से 10 में कितनी तेज है, और किससे बेहतर या बदतर होती है?",
            "hinglish": "Problem kahan hai, 0 se 10 mein kitni severe hai, aur kis se better ya worse hoti hai?",
        }))

    if not hair_loss:
        candidates.append(("red_flag", {
        "en": (
            "Is the leg suddenly very painful or markedly swollen, or do you have chest pain, trouble breathing, fainting, or a recent serious injury?"
            if leg_pain else
            "Any sudden severe symptoms, trouble breathing, chest pain, fainting, severe bleeding, or sudden weakness or trouble speaking?"
            if not headache else
            "Any sudden worst-ever headache, trouble speaking or seeing, weakness, fainting, stiff neck, repeated vomiting, breathing trouble, chest pain, or recent head injury?"
        ),
        "hi": (
            "क्या पैर में अचानक बहुत तेज दर्द या बहुत अधिक सूजन है, या सीने में दर्द, सांस लेने में दिक्कत, बेहोशी या हाल की गंभीर चोट है?"
            if leg_pain else
            "क्या अचानक गंभीर लक्षण, सांस लेने में दिक्कत, सीने में दर्द, बेहोशी, बहुत अधिक खून बहना या अचानक कमजोरी/बोलने में दिक्कत है?"
            if not headache else
            "क्या अचानक जीवन का सबसे तेज सिरदर्द, बोलने/देखने में दिक्कत, कमजोरी, बेहोशी, गर्दन अकड़ना, बार-बार उल्टी, सांस की तकलीफ, सीने में दर्द या हाल की सिर की चोट है?"
        ),
        "hinglish": (
            "Kya leg mein achanak bahut tez dard ya zyada swelling hai, ya chest pain, saans ki dikkat, behoshi, ya recent serious injury hui hai?"
            if leg_pain else
            "Kya achanak severe symptoms, saans lene mein dikkat, chest pain, behoshi, zyada bleeding, ya achanak weakness/bolne mein dikkat hai?"
            if not headache else
            "Kya achanak life ka sabse tez headache, bolne/dekhne mein dikkat, weakness, behoshi, stiff neck, repeated vomiting, saans ki dikkat, chest pain ya recent head injury hui hai?"
        ),
        }))
    for _, templates in candidates:
        question = templates[facts.language]
        normalized = question.lower().rstrip("?")
        if normalized not in prior_text:
            return question
    return None


def _has_specific_complaint(text: str) -> bool:
    """Whether a turn names a symptom specifically enough to reset the focus."""
    return bool(_complaint_kind(text)) or bool(re.search(
        r"\b(?:headache|head ache|migraine|fever|bukhar|cough|khansi|cold|stomach pain|tummy pain|"
        r"rash|pain|ache|hurt|hurting|sore|injury|injured|bleeding|vomit|vomiting|diarrhea)\b"
        r"|सिरदर्द|सिर में दर्द|बुखार|खांसी|पेट दर्द|पैर दर्द|टांग दर्द|दर्द|चोट",
        text,
        re.IGNORECASE,
    ))
