import re
from difflib import get_close_matches
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.pipeline import run as run_triage
from app.core.red_flags import check as check_red_flags
from app.core.normalize import transliterate_to_devanagari
from app.core.followup import QUESTION as TRIAGE_QUESTIONS, SCREENING as TRIAGE_SCREENING
from app.integrations import sarvam_client
from app.modules.agents import answer as answer_agent
from app.schemas.care import IntakeRequest, Location

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


class CareContext(BaseModel):
    care_type: str
    urgency: str
    reasoning: str
    symptoms: list[str] = Field(default_factory=list)


class IntakeState(BaseModel):
    symptoms: list[str] = Field(default_factory=list)
    symptom_text: str = ""
    who: str | None = None
    age_group: Literal["child", "adult", "elderly"] | None = None
    duration: str | None = None
    preference: Literal["home_visit", "online_doctor"] | None = None
    requested_service: Literal["home_nursing", "lab_test_home", "paramedic_home_visit", "teleconsultation"] | None = None
    red_flags_screened: bool = False
    red_flag_answer: Literal["yes", "no"] | None = None
    question_count: int = 0
    pending_question: Literal["red_flag", "who_age", "duration", "preference", "who_problem"] | None = None


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1)
    location: Location
    history: list[dict] = Field(default_factory=list)
    language: str = "auto"
    care_context: CareContext | None = None
    booking_context: dict | None = None
    intake_state: IntakeState | None = None


class AssistantResponse(BaseModel):
    mode: Literal["emergency", "care", "followup", "answer", "smalltalk", "app_help", "off_topic"]
    message: str
    care: dict | None
    language: Literal["Hindi", "Hinglish", "English"]
    suggestions: list[str]
    care_context: CareContext | None = None
    spoken_message: str | None = None
    safety_net: str | None = None
    why_not: str | None = None
    intake_state: IntakeState | None = None
    understood: str | None = None


class IntentClassification(BaseModel):
    intent: Literal["care", "answer", "followup", "smalltalk", "app_help", "off_topic"]


CLASSIFY_SYSTEM = """Classify only within CareCompass's scope: health, wellbeing, finding care, or how to use this app. Choose exactly one intent: care, answer, followup, smalltalk, app_help, off_topic. Return JSON only as {\"intent\": ...}. care means personal symptoms or a requested care service. answer means general health information without a personal care request. followup means a health/care request is unclear. smalltalk means only a greeting, name, or thanks. app_help means CareCompass booking, services, or voice help. off_topic means anything unrelated to health or this app, including arithmetic, trivia, coding, sports, politics, and entertainment. Do not answer the user's question; classify only. Emergency language is handled by deterministic rules first."""

QUESTION_WORDS = r"\b(?:kya|kaise|kyun|kyon|what|how|why|when|which|क्या|कैसे|क्यों|कब|कौन)\b"
SERVICE_WORDS = r"home visit|home care|ghar pe|ghar par|nurse|nursing|injection|lab test|blood test|test|sample|consult|doctor|डॉक्टर|नर्स|इंजेक्शन|जांच|टेस्ट|घर पर|घर पे"
SYMPTOMS = r"bukhar|fever|khansi|cough|cold|sardi|zukham|headache|sir.{0,12}dard|stomach.{0,15}(?:ache|pain|problem|issue)|stomach issues?|pet.{0,15}dard|pain|dard|issue|problem|feeling|injury|bleeding|दर्द|बुखार|खांसी|जुकाम|सर्दी|सिर में दर्द|पेट में दर्द|कमज़ोरी|कमजोरी|weakness|vomit|उल्टी|diarrhea|दस्त|तकलीफ|परेशानी|दिक्कत"
PERSONAL = r"\b(?:i have|i am having|i feel|having|my|mujhe|mere|meri|mujhko|papa|mummy|mother|father|for my|someone|patient|i am not feeling well|not feeling well)\b|(?:मुझे|मेरे|मेरी|पापा|मम्मी|माता|पिता|तबीयत|तबियत)"
APP_HELP = r"booking|book (?:a|an|my)? ?(?:doctor|visit|appointment|service)|how (?:do i|can i) book|services (?:do you|are available)|what services|voice input|speak your request|privacy|बुकिंग|बुक कैसे|सेवाएं|सेवाएँ|आवाज़ से"
GREETING = r"^(?:hi|hello|hey|namaste|namaskar|नमस्ते|हेलो|mera naam .{1,40}|my name is .{1,40}|thanks|thank you|धन्यवाद|शुक्रिया)[!. ,?]*$"
OFF_TOPIC = r"\b(?:ipl|cricket|score|homework|maths homework|joke|jokes|football|movie review)\b|आईपीएल|क्रिकेट|होमवर्क|चुटकुला"
GENERAL_HEALTH = r"\b(?:health|fever|bukhar|blood pressure|bp|dehydration|hydration|cough|cold|nutrition|sleep|exercise|headache|symptom|signs?)\b|बुखार|खांसी|पानी की कमी|ब्लड प्रेशर|स्वास्थ्य|लक्षण"
HEALTH_DOMAIN = r"\b(?:health|wellness|medical|symptom|fever|bukhar|khansi|cough|cold|sardi|zukham|headache|pain|dard|acidity|vomit|vomiting|diarrhea|rash|weakness|weak|kamzori|breathless|breathing|blood pressure|bp|sugar|diabetes|dehydration|hydration|pregnan\w*|medicine|medication|tablet|dose|dosage|doctor|nurse|nursing|injection|lab test|blood test|sample|consult|care|patient|clinic|hospital|wellbeing|stress|anxious|anxiety|sad|mental health|injury|bleeding|wound|seizure|stroke|chest|healthcare|having|issue|problem|feeling|stomach|body|leg|arm|head|tooth|back|skin|tabiyat|takleef|pareshani|dikkat)\b|बुखार|खांसी|सर्दी|जुकाम|सिरदर्द|सिर में दर्द|दर्द|कमज़ोरी|कमजोरी|सांस|सीने|छाती|रक्तचाप|स्वास्थ्य|लक्षण|दवा|गोली|खुराक|डॉक्टर|नर्स|जांच|जाँच|चिकित्सा|देखभाल|चिंता|घबराहट|उदास|चोट|खून|गर्भावस्था|तबीयत|तबियत|तकलीफ|परेशानी|दिक्कत"
UNCLEAR_CARE = r"^(?:help|i need help|i need some help|can you help me|need help|i need help deciding what to do|i am not feeling well|i'm not feeling well|not feeling well|i feel unwell|tabiyat theek nahi|tabiyat thik nahi|तबीयत ठीक नहीं|मदद|मदद चाहिए|मुझे मदद चाहिए|madad|madad chahiye)[!. ]*$"
MEDICATION_REQUEST = r"\b(?:which|what|recommend|suggest|should i|can i take|medicine|medication|tablet|dose|dosage|mg|paracetamol|antibiotic)\b.{0,45}\b(?:medicine|medication|tablet|dose|dosage|take|mg|paracetamol|antibiotic)\b|(?:कौन सी दवा|कौनसी दवा|कितनी दवा|दवा बताएं|दवा बताइए|कितनी खुराक)"
HOME_VISIT_CHIP = r"^(?:घर पर जाँच|घर पे जाँच|ghar pe check[- ]?up|ghar par check[- ]?up|home check[- ]?up)$"
DOCTOR_CHIP = r"^(?:डॉक्टर से बात करें|doctor se baat karein|talk to a doctor)$"
SHOW_CAREGIVERS_CHIP = r"^(?:उपलब्ध देखभालकर्ता दिखाएँ|show available caregivers)$"
BOOKING_STATUS = r"when (?:will|are) (?:they|the caregiver|the provider) (?:arrive|get here)|kab aayenge|कब आएंगे|कब आएँगे|booking status|confirm hua\??|booking confirm hui\??"

SUGGESTIONS = {
    "emergency": {"English": [], "Hindi": [], "Hinglish": []},
    "care": {"English": ["Talk to a doctor", "Home check-up", "Tell me more"], "Hindi": ["डॉक्टर से बात करें", "घर पर जाँच", "और जानकारी दें"], "Hinglish": ["Doctor se baat karein", "Ghar pe check-up", "Aur detail batayein"]},
    "followup": {"English": ["Yes, I need care", "Just information"], "Hindi": ["हाँ, देखभाल चाहिए", "बस जानकारी चाहिए"], "Hinglish": ["Haan, care chahiye", "Bas jaankari chahiye"]},
    "answer": {"English": ["Talk to a doctor", "Home check-up", "That’s all"], "Hindi": ["डॉक्टर से बात करें", "घर पर जाँच", "बस इतना"], "Hinglish": ["Doctor se baat karein", "Ghar pe check-up", "Nahi, bas itna"]},
    "smalltalk": {"English": ["Fever or cough", "Home injection", "Lab test"], "Hindi": ["बुखार/खांसी", "घर पर इंजेक्शन", "लैब टेस्ट"], "Hinglish": ["Bukhar/khansi", "Injection ghar pe", "Lab test"]},
    "app_help": {"English": ["Available services", "Booking help", "How voice works"], "Hindi": ["उपलब्ध सेवाएँ", "बुकिंग में मदद", "आवाज़ कैसे इस्तेमाल करें"], "Hinglish": ["Services kya hain?", "Booking mein madad", "Voice kaise use karein"]},
    "off_topic": {"English": ["Fever or cough", "Talk to a doctor", "Lab test"], "Hindi": ["बुखार/खांसी", "डॉक्टर से बात", "लैब टेस्ट"], "Hinglish": ["Bukhar/khansi", "Doctor se baat", "Lab test"]},
}

GUIDED_ANSWERS = {
    "Hindi": {
        "red_flag": ("क्या सीने में दर्द, सांस लेने में तकलीफ़, बेहोशी या भ्रम है?", ["नहीं", "हाँ"]),
        "who_age": ("यह किसके लिए है और उम्र का समूह क्या है—बच्चा, वयस्क या बुज़ुर्ग?", ["बच्चा", "वयस्क", "बुज़ुर्ग"]),
        "duration": ("यह परेशानी कब से है?", ["आज से", "1–3 दिन", "3 दिन से ज़्यादा"]),
        "preference": ("आप घर पर विज़िट चाहेंगी या ऑनलाइन डॉक्टर से बात?", ["घर पर", "ऑनलाइन"]),
        "who_problem": ("मुख्य परेशानी क्या है?", ["बुखार/खांसी", "पेट की परेशानी", "सिरदर्द", "चोट", "घर पर इंजेक्शन/ड्रेसिंग", "लैब टेस्ट"]),
    },
    "Hinglish": {
        "red_flag": ("Kya seene mein dard, saans lene mein takleef, behoshi ya confusion hai?", ["Nahi", "Haan"]),
        "who_age": ("Yeh kiske liye hai, aur age group kya hai—child, adult ya elderly?", ["Child", "Adult", "Elderly"]),
        "duration": ("Yeh problem kab se hai?", ["Aaj se", "1–3 din", "3 din se zyada"]),
        "preference": ("Aap home visit chahti hain ya online doctor se baat?", ["Ghar par", "Online"]),
        "who_problem": ("Main problem kya hai?", ["Bukhar/khansi", "Stomach problem", "Headache", "Injury", "Injection/dressing at home", "Lab test"]),
    },
    "English": {
        "red_flag": ("Is there chest pain, difficulty breathing, fainting, or confusion?", ["No", "Yes"]),
        "who_age": ("Who is this for, and what age group: child, adult, or elderly?", ["Child", "Adult", "Elderly"]),
        "duration": ("How long has this been happening?", ["Today", "1–3 days", "More than 3 days"]),
        "preference": ("Would you prefer a home visit or an online doctor?", ["Home visit", "Online"]),
        "who_problem": ("What is the main problem?", ["Fever/cough", "Stomach problem", "Headache", "Injury", "Injection/dressing at home", "Lab test"]),
    },
}

YES_ANSWERS = {"yes", "haan", "han", "हाँ", "हां", "जी हाँ", "जी हां"}
NO_ANSWERS = {"no", "nahi", "nahin", "नहीं", "नही", "जी नहीं"}

CARE_LABELS = {
    "paramedic_home_visit": {"English": "Medic home visit", "Hindi": "घर पर मेडिक विज़िट", "Hinglish": "Medic home visit"},
    "home_nursing": {"English": "Nursing at home", "Hindi": "घर पर नर्सिंग सेवा", "Hinglish": "Ghar par nursing service"},
    "lab_test_home": {"English": "Lab test at home", "Hindi": "घर पर लैब टेस्ट", "Hinglish": "Ghar par lab test"},
    "teleconsultation": {"English": "Virtual doctor", "Hindi": "ऑनलाइन डॉक्टर से परामर्श", "Hinglish": "Online doctor se salah"},
    "emergency_112": {"English": "Emergency – call 112", "Hindi": "आपातकाल – 112 पर कॉल करें", "Hinglish": "Emergency – 112 par call karein"},
}
URGENCY_LABELS = {
    "same_day": {"English": "same day", "Hindi": "आज ही", "Hinglish": "aaj hi"},
    "scheduled": {"English": "scheduled", "Hindi": "निर्धारित समय पर", "Hinglish": "tay samay par"},
    "emergency": {"English": "emergency", "Hindi": "आपातकालीन", "Hinglish": "emergency"},
}


def _last_emergency(history: list[dict]) -> bool:
    return any(turn.get("role") == "assistant" and (turn.get("display", {}).get("mode") == "emergency" or turn.get("mode") == "emergency") for turn in history)


def _latest_turn_is_emergency(history: list[dict]) -> bool:
    return next((turn.get("display", {}).get("mode", turn.get("mode")) == "emergency" for turn in reversed(history) if turn.get("role") == "assistant"), False)


def _active_user_turns(history: list[dict]) -> list[str]:
    start = 0
    for index, turn in enumerate(history):
        if turn.get("role") == "assistant":
            mode = turn.get("display", {}).get("mode", turn.get("mode"))
            if mode in {"care", "emergency"}:
                start = index + 1
    turns = history[start:]
    pending: str | None = None
    user_text: list[str] = []
    for turn in turns:
        if turn.get("role") == "assistant":
            state = turn.get("display", {}).get("intake_state") or turn.get("intake_state") or {}
            pending = state.get("pending_question")
        elif turn.get("role") == "user":
            value = str(turn.get("content", turn.get("text", "")))
            if pending and _is_chip_answer(pending, value):
                continue
            user_text.append(value)
    return user_text


def _is_chip_answer(pending: str, message: str) -> bool:
    text = message.strip().lower()
    if pending == "red_flag":
        return text in YES_ANSWERS | NO_ANSWERS
    if pending == "who_age":
        return text in {"child", "बच्चा", "बच्चे", "adult", "वयस्क", "बड़े", "bade", "elderly", "बुज़ुर्ग", "बुजुर्ग", "senior"}
    if pending == "duration":
        return text in {"today", "aaj", "आज", "1–3 days", "1-3 days", "1–3 दिन", "3 days", "3 दिन से ज़्यादा", "more than 3 days"} or bool(re.fullmatch(r"\d+\s*(?:days?|din|दिन)", text))
    if pending == "preference":
        return text in {"home visit", "home", "घर पर", "घर", "online", "ऑनलाइन"}
    if pending == "who_problem":
        return text in {chip.lower() for locale in GUIDED_ANSWERS.values() for chip in locale["who_problem"][1]}
    return False


def _detect_language(message: str) -> str:
    if re.search(r"[\u0900-\u097f]", message):
        return "Hindi"
    words = set(re.findall(r"[a-z]+", message.lower()))
    roman_hindi = {"ko", "hai", "hain", "haan", "han", "ha", "nahi", "nahin", "mein", "se", "chahiye", "jaankari", "jankari", "karna", "ghar", "ka", "ki", "ho", "raha", "rahi", "papa", "mummy", "mujhe", "mere", "meri", "bukhar", "dard", "aur", "batayein", "batana", "kyun", "kyon", "din", "dhoondh", "sakti", "bas", "namaste", "namaskar"}
    return "Hinglish" if words & roman_hindi else "English"


def _localized_followup(question: str, language: str) -> str:
    if language == "English":
        return question
    if any(cue in question.lower() for cue in ("chest pain", "seene mein", "सीने में", "difficulty breathing", "saans lene")):
        return TRIAGE_SCREENING[language]
    if language == "Hindi":
        return "कृपया मुख्य परेशानी या सेवा बताएं (घर पर जाँच, नर्सिंग, लैब टेस्ट या डॉक्टर से बात)।"
    return "Kripya main problem ya service batayein (home visit, nursing, lab test, ya doctor se baat)."


SYMPTOM_PATTERNS = {
    "headache": r"headache|head pain|sir.{0,15}dard|सिर.{0,12}दर्द",
    "fever": r"fever|bukhar|बुखार",
    "cough": r"cough|khansi|खांसी",
    "cold": r"\bcold\b|sardi|zukham|सर्दी|जुकाम",
    "stomach pain": r"stomach.{0,15}(?:ache|pain)|pet.{0,15}dard|पेट.{0,12}दर्द",
    "body ache": r"body ache|body pain|badan dard|shareer dard|बदन दर्द|शरीर.{0,10}दर्द",
    "acidity": r"acidity|acid reflux|एसिडिटी|अम्लता",
    "weakness": r"weakness|weak|kamzori|kamzोर|कमज़ोरी|कमजोरी",
    "nausea": r"nausea|जी मिचलाना|मतली",
    "vomiting": r"vomit|उल्टी",
    "diarrhea": r"diarrhea|loose motions?|दस्त|पतले दस्त",
    "injury": r"injury|injured|hurt|चोट",
}

FUZZY_TERMS = ("stomach", "headache", "fever", "khansi", "cough", "pain", "dard", "issue", "problem", "feeling", "injury", "having")
SYMPTOM_CHIP_MAP = {
    "fever/cough": ("fever", "cough"), "bukhar/khansi": ("fever", "cough"), "बुखार/खांसी": ("fever", "cough"),
    "stomach problem": ("stomach pain",), "पेट की परेशानी": ("stomach pain",),
    "headache": ("headache",), "सिरदर्द": ("headache",),
    "injury": ("injury",), "चोट": ("injury",),
}
SERVICE_CHIP_MAP = {
    "injection/dressing at home": "home_nursing", "घर पर इंजेक्शन/ड्रेसिंग": "home_nursing",
    "lab test": "lab_test_home", "लैब टेस्ट": "lab_test_home",
    "ghar pe check-up": "paramedic_home_visit", "ghar par check-up": "paramedic_home_visit", "home check-up": "paramedic_home_visit", "घर पर जाँच": "paramedic_home_visit",
    "doctor se baat karein": "teleconsultation", "talk to a doctor": "teleconsultation", "डॉक्टर से बात करें": "teleconsultation",
}


def _fuzzy_correct(text: str) -> str:
    corrected = []
    for token in re.findall(r"[A-Za-z]+|[^A-Za-z]+", text):
        if not token.isalpha() or len(token) < 4:
            corrected.append(token)
            continue
        match = get_close_matches(token.lower(), FUZZY_TERMS, n=1, cutoff=0.72)
        corrected.append(match[0] if match else token)
    return "".join(corrected)


def _extract_symptoms(text: str) -> list[str]:
    text = _fuzzy_correct(text)
    symptoms = [name for name, pattern in SYMPTOM_PATTERNS.items() if re.search(pattern, text, re.I)]
    if "stomach" in text.lower() and re.search(r"\b(?:issue|problem|ache|pain|cramp)\w*\b", text, re.I):
        symptoms.append("stomach pain")
    return list(dict.fromkeys(symptoms))


def _mild_symptom_service(text: str, state: IntakeState) -> str | None:
    home_requested = state.preference == "home_visit" or bool(re.search(r"ghar pe|ghar par|ghar aa|home visit|visit at home|घर पर|घर पे|घर आ", text, re.I))
    explicit_other = re.search(r"nurs(?:e|ing)|injection|dressing|lab test|blood test|sample|doctor se consult|virtual doctor|online doctor|नर्स|इंजेक्शन|ड्रेसिंग|लैब टेस्ट|जांच|डॉक्टर से सलाह", text, re.I)
    if explicit_other:
        return None
    if "headache" in state.symptoms or "cold" in state.symptoms or "body ache" in state.symptoms:
        return "paramedic_home_visit" if home_requested else "teleconsultation"
    if "stomach pain" in state.symptoms and re.search(r"mild|light|हल्का|हल्की|कम दर्द", text, re.I):
        return "paramedic_home_visit" if home_requested else "teleconsultation"
    return None


def _prior_care_context(request: AssistantRequest) -> CareContext | None:
    if request.care_context:
        return request.care_context
    for turn in reversed(request.history):
        value = turn.get("care_context")
        if value:
            try:
                return CareContext.model_validate(value)
            except Exception:
                continue
    return None


def _prior_intake_state(request: AssistantRequest) -> IntakeState:
    if request.intake_state:
        return request.intake_state.model_copy(deep=True)
    for turn in reversed(request.history):
        value = turn.get("intake_state")
        if value:
            try:
                return IntakeState.model_validate(value)
            except Exception:
                continue
    return IntakeState()


def _merge_intake_state(state: IntakeState, all_text: str, current: str) -> IntakeState:
    all_text = _fuzzy_correct(all_text)
    state.symptoms = list(dict.fromkeys([*state.symptoms, *_extract_symptoms(all_text)]))
    if all_text.strip() and _extract_symptoms(all_text):
        state.symptom_text = "; ".join(dict.fromkeys(filter(None, [state.symptom_text, all_text.strip()])))[:500]
    text = all_text.lower()
    if not state.who:
        if re.search(r"\b(?:mujhe|mere|meri|my|i have|i am)\b|(?:मुझे|मेरे|मेरी)", text):
            state.who = "self"
        else:
            relation = re.search(r"\b(?:mummy|mother|mom|papa|father|dad|dadi|nani|nana|dada|wife|husband|child|son|daughter)\b|(?:मम्मी|माँ|माता|पापा|पिता|दादी|नानी|दादा|नाना|बच्चा)", text, re.I)
            if relation:
                state.who = relation.group(0)
    if not state.age_group:
        age = re.search(r"\b(child|baby|kid|elderly|senior|adult)\b|(?:बच्चा|बुज़ुर्ग|बुजुर्ग|वयस्क)", text, re.I)
        if age:
            word = age.group(0).lower()
            state.age_group = "child" if word in {"child", "baby", "kid", "बच्चा"} else "elderly" if word in {"elderly", "senior", "बुज़ुर्ग", "बुजुर्ग"} else "adult"
        elif state.who and state.who.lower() in {"papa", "father", "dad", "mummy", "mother", "mom", "wife", "husband"}:
            state.age_group = "adult"
    if not state.duration:
        duration = re.search(r"\b(?:today|aaj|yesterday|kal|(?:one|two|three|do|teen)\s*(?:days?|din)|\d+\s*(?:days?|din|weeks?|hafte?|months?|mahine?))\b|(?:आज|कल|दो दिन|तीन दिन|\d+\s*(?:दिन|हफ्ते|हफ़्ते|महीने))", text, re.I)
        if duration:
            state.duration = duration.group(0)
    if not state.preference:
        if re.search(r"home visit|ghar pe|ghar par|घर पर|घर पे|घर में", text, re.I):
            state.preference = "home_visit"
        elif re.search(r"online|virtual|consult|doctor se|डॉक्टर से|ऑनलाइन", text, re.I):
            state.preference = "online_doctor"
    return state


def _consume_guided_answer(state: IntakeState, current: str) -> tuple[bool, bool]:
    answer = current.strip().lower().strip(".!? ")
    pending = state.pending_question
    if pending == "red_flag":
        if answer in YES_ANSWERS:
            state.red_flag_answer = "yes"
            state.pending_question = None
            return True, True
        if answer in NO_ANSWERS:
            state.red_flag_answer = "no"
            state.red_flags_screened = True
            state.pending_question = None
            return False, True
    elif pending == "who_age":
        if answer in {"child", "बच्चा", "बच्चे"}:
            state.age_group = "child"
        elif answer in {"adult", "वयस्क", "बड़े", "bade"}:
            state.age_group = "adult"
        elif answer in {"elderly", "बुज़ुर्ग", "बुजुर्ग", "senior"}:
            state.age_group = "elderly"
        if state.age_group and not state.who:
            state.who = "self"
        if state.age_group:
            state.pending_question = None
            return False, True
    elif pending == "duration":
        if _is_chip_answer(pending, current) or re.search(r"\b(?:today|yesterday|\d+\s*(?:days?|weeks?)|aaj|kal|din|दिन)\b", current, re.I):
            state.duration = current.strip()
            state.pending_question = None
            return False, True
    elif pending == "preference":
        if re.search(r"home|ghar|घर", answer):
            state.preference = "home_visit"
        elif re.search(r"online|doctor|ऑनलाइन|डॉक्टर", answer):
            state.preference = "online_doctor"
        if state.preference:
            state.pending_question = None
            return False, True
    elif pending == "who_problem":
        chip = next((key for key in SYMPTOM_CHIP_MAP if key.lower() == answer), None)
        if chip:
            state.symptoms = list(dict.fromkeys([*state.symptoms, *SYMPTOM_CHIP_MAP[chip]]))
            state.symptom_text = "; ".join(dict.fromkeys(filter(None, [state.symptom_text, *SYMPTOM_CHIP_MAP[chip]])))[:500]
            state.pending_question = None
            return False, True
        service = next((key for key in SERVICE_CHIP_MAP if key.lower() == answer), None)
        if service:
            state.requested_service = SERVICE_CHIP_MAP[service]
            state.pending_question = None
            return False, True
        found = _extract_symptoms(current)
        if found:
            state.symptoms = list(dict.fromkeys([*state.symptoms, *found]))
            state.symptom_text = "; ".join(filter(None, [state.symptom_text, current.strip()]))[:500]
            state.pending_question = None
            return False, False
        return False, True
    return False, False


def _next_guided_question(state: IntakeState, language: str, *, vague: bool = False) -> tuple[str, list[str]] | None:
    if state.question_count >= 3:
        return None
    if vague and not state.symptoms:
        key = "who_problem"
    elif state.symptoms and not state.red_flags_screened:
        key = "red_flag"
    elif not state.who or not state.age_group:
        key = "who_age"
    elif not state.duration:
        key = "duration"
    elif not state.preference and state.symptoms == ["headache"]:
        key = "preference"
    else:
        return None
    state.pending_question = key
    state.question_count += 1
    return GUIDED_ANSWERS[language][key]


def _intake_summary(state: IntakeState, language: str) -> str:
    symptoms = ", ".join(state.symptoms) if state.symptoms else ("बताई परेशानी" if language == "Hindi" else "batayi problem" if language == "Hinglish" else "reported concern")
    who = state.who or ("आप" if language == "Hindi" else "aap" if language == "Hinglish" else "you")
    duration = state.duration or ("अवधि नहीं बताई" if language == "Hindi" else "duration nahi batayi" if language == "Hinglish" else "duration not stated")
    age = {"child": "बच्चा" if language == "Hindi" else "child", "adult": "वयस्क" if language == "Hindi" else "adult", "elderly": "बुज़ुर्ग" if language == "Hindi" else "elderly"}.get(state.age_group or "", "")
    preference = ("घर पर" if state.preference == "home_visit" else "ऑनलाइन डॉक्टर" if state.preference == "online_doctor" else "") if language == "Hindi" else ("ghar par" if state.preference == "home_visit" else "online doctor" if state.preference == "online_doctor" else "") if language == "Hinglish" else ("home visit" if state.preference == "home_visit" else "online doctor" if state.preference == "online_doctor" else "")
    age_text = f" ({age})" if age else ""
    preference_text = f"; पसंद: {preference}" if preference and language == "Hindi" else f"; preference: {preference}" if preference else ""
    if language == "Hindi":
        return f"परेशानी: {symptoms}; किसके लिए: {who}{age_text}; अवधि: {duration}{preference_text}।"
    if language == "Hinglish":
        return f"Problem: {symptoms}; kiske liye: {who}{age_text}; duration: {duration}{preference_text}."
    return f"Concern: {symptoms}; for: {who}{age_text}; duration: {duration}{preference_text}."


def _is_explanation_request(message: str) -> bool:
    text = message.strip().lower()
    return bool(re.fullmatch(r"(?:aur detail batayein|aur detail|more details?|tell me more|why\??|kyun\??|क्यों\??|और विस्तार से बताइए|और जानकारी(?: दें)?)[!. ]*", text, re.I))


def _is_next_steps_request(message: str) -> bool:
    return bool(re.fullmatch(r"(?:what to do next\??|what should i do next\??|aage kya karein\??|aage kya karna hai\??|आगे क्या करें\??|अब क्या करें\??|आगे क्या करना है\??)[!. ]*", message.strip(), re.I))


def _next_steps(context: CareContext, booking: dict | None, language: str) -> str:
    from app.core import reasoning
    if language == "Hindi":
        action = f"आपकी बुकिंग {booking.get('caregiver_id', 'देखभालकर्ता')} के साथ {booking.get('slot', 'दर्ज समय')} के लिए है; स्थिति {booking.get('state', 'अज्ञात')} है।" if booking else "उपलब्ध देखभालकर्ताओं में से चुनकर समय की बुकिंग करें।"
        return f"{action} परेशानी कब शुरू हुई और लक्षणों में क्या बदलाव आया, यह जानकारी तैयार रखें। {reasoning.safety_net(language, context.care_type)} मैं आपकी मदद कर सकती हूँ।"
    if language == "Hinglish":
        action = f"Aapki booking {booking.get('caregiver_id', 'caregiver')} ke saath {booking.get('slot', 'selected slot')} par hai; status {booking.get('state', 'unknown')} hai." if booking else "Available caregivers mein se chunein aur ek slot book karein."
        return f"{action} Problem kab shuru hui aur symptoms mein kya badlav aaye, yeh ready rakhein. {reasoning.safety_net(language, context.care_type)} Main madad kar sakti hoon."
    action = f"Your booking is with {booking.get('caregiver_id', 'the caregiver')} for {booking.get('slot', 'the selected slot')}; its status is {booking.get('state', 'unknown')}." if booking else "Choose an available caregiver and request an appointment slot."
    return f"Keep a note of when the concern began and any changes in symptoms. {reasoning.safety_net(language, context.care_type)} I can help with the next step."


def _is_information_request(message: str) -> bool:
    text = message.strip().lower()
    return bool(re.search(r"bas jaankari chahiye|bas jankari chahiye|just information|just info|only information|बस जानकारी चाहिए|सिर्फ जानकारी चाहिए", text, re.I))


def _rule_intent(message: str) -> str | None:
    text = message.strip().lower()
    if re.search(APP_HELP, text, re.I):
        return "app_help"
    if re.fullmatch(GREETING, text, re.I):
        return "smalltalk"
    if re.search(r"^(?:thanks|thank you|dhanyavaad|shukriya)(?:\s+for\s+.{1,40})?[!. ]*$|^(?:धन्यवाद|शुक्रिया)(?:\s+.{1,40})?$", text, re.I):
        return "smalltalk"
    if re.search(OFF_TOPIC, text, re.I) or re.search(r"\d+\s*[+*/-]\s*\d+|\b(?:capital of|write (?:me )?(?:a )?(?:python|javascript|code)|solve (?:this )?equation|homework|tell me a joke|joke about|ipl score|cricket score|football score|movie review)\b", text, re.I):
        if not (re.search(SYMPTOMS + "|" + PERSONAL + "|" + HEALTH_DOMAIN, text, re.I) and not re.search(r"\d+\s*[+*/-]\s*\d+", text)):
            return "off_topic"
    if re.fullmatch(UNCLEAR_CARE, text, re.I):
        return "followup"
    if re.search(MEDICATION_REQUEST, text, re.I):
        return "answer"
    symptom = bool(re.search(SYMPTOMS, text, re.I))
    personal = bool(re.search(PERSONAL, text, re.I)) or bool(symptom and re.search(r"\b(?:hai|hain|is|has|have|ho raha|ho rahi)\b|(?:है|हैं|हो रहा|हो रही)", text, re.I))
    service = bool(re.search(SERVICE_WORDS, text, re.I))
    question = bool(re.search(QUESTION_WORDS, text, re.I))
    if service or (symptom and personal):
        return "care"
    if question and (symptom or re.search(GENERAL_HEALTH, text, re.I)):
        return "answer"
    if re.search(r"\b(?:thanks|thank you|dhanyavaad|shukriya)\b|(?:धन्यवाद|शुक्रिया)", text, re.I):
        return "smalltalk"
    # Unknown questions never go to an open-ended model by default. Only allow
    # model classification when a health/care subject is actually present.
    if re.search(HEALTH_DOMAIN + "|" + SYMPTOMS + "|" + PERSONAL, text, re.I):
        return "care" if symptom or re.search(PERSONAL, text, re.I) else "answer"
    return "followup"


def _template(intent: str, language: str) -> str:
    hindi = language == "Hindi"
    hinglish = language == "Hinglish"
    if intent == "care":
        return "मैं मदद कर सकती हूँ।" if hindi else ("Main madad kar sakti hoon." if hinglish else "I can help you find care.")
    if intent == "followup":
        return "क्या आपको किसी के लिए देखभाल चाहिए या सिर्फ जानकारी?" if hindi else ("Kya aapko kisi ke liye care chahiye ya sirf jaankari?" if hinglish else "Are you looking for care for someone, or just information?")
    if intent == "smalltalk":
        return "नमस्ते! मैं CareCompass हूँ। मैं आपकी मदद कैसे कर सकती हूँ?" if hindi else ("Namaste! Main CareCompass hoon. Aapki madad kaise kar sakti hoon?" if hinglish else "Hello! I’m CareCompass. How can I help?")
    if intent == "app_help":
        return "मैं CareCompass की सुविधाओं और इस्तेमाल के बारे में जानकारी दे सकती हूँ।" if hindi else ("Main CareCompass ke features aur istemaal ke baare mein bata sakti hoon." if hinglish else "I can help explain CareCompass services and how to use the app.")
    if intent == "off_topic":
        return "मैं स्वास्थ्य सेवा से जुड़ी मदद करती हूँ। आपकी सेहत से जुड़ा सवाल क्या है?" if hindi else ("Main health care mein madad karti hoon. Aapki health se judi kya madad chahiye?" if hinglish else "I help with health care. What health question can I help with?")
    return "मैं सामान्य स्वास्थ्य जानकारी दे सकती हूँ। क्या आप डॉक्टर से बात करना चाहेंगी?" if hindi else ("Main general health jaankari de sakti hoon. Kya aap doctor se baat karna chahengi?" if hinglish else "I can share general health information. Would you like help finding a doctor?")


def _suggestions(mode: str, language: str) -> list[str]:
    return SUGGESTIONS.get(mode, {}).get(language, [])


def _emergency_message(language: str) -> str:
    return {
        "Hindi": "यह आपातकाल हो सकता है। कृपया अभी 112 पर कॉल करें।",
        "Hinglish": "Yeh emergency ho sakti hai. Kripya abhi 112 par call karein.",
        "English": "This may be an emergency. Please call 112 now.",
    }[language]


def _emergency_reminder(message: str, language: str, was_emergency: bool) -> str:
    if not was_emergency:
        return message
    reminder = {
        "English": "If the earlier emergency symptoms are still present, call 112 now.",
        "Hindi": "अगर पहले वाले आपातकालीन लक्षण अभी भी हैं, तो तुरंत 112 पर कॉल करें।",
        "Hinglish": "Agar pehle wale emergency symptoms abhi bhi hain, to abhi 112 par call karein.",
    }[language]
    return f"{message} {reminder}"


def _booking_status_message(booking: dict | None, language: str) -> tuple[str, list[str]]:
    if not booking:
        messages = {
            "Hindi": "अभी कोई बुकिंग नहीं है। मैं उपलब्ध देखभालकर्ता दिखा सकती हूँ।",
            "Hinglish": "Abhi koi booking nahi hai. Main available caregivers dikha sakti hoon.",
            "English": "There is no booking yet. I can show available caregivers.",
        }
        chips = {"Hindi": ["उपलब्ध देखभालकर्ता दिखाएँ"], "Hinglish": ["Show available caregivers"], "English": ["Show available caregivers"]}
        return messages[language], chips[language]
    status = str(booking.get("state", "requested"))
    caregiver = str(booking.get("caregiver_id") or booking.get("provider_name") or "caregiver")
    slot = str(booking.get("slot") or "")
    if language == "Hindi":
        state_text = "देखभालकर्ता की पुष्टि का इंतज़ार है" if status == "requested" else f"स्थिति: {status}"
        return f"आपकी बुकिंग {caregiver} के साथ {slot} के लिए है। {state_text}। पहुँचने का समय अभी उपलब्ध नहीं है।", []
    if language == "Hinglish":
        state_text = "caregiver ki confirmation ka intezaar hai" if status == "requested" else f"status {status} hai"
        return f"Aapki booking {caregiver} ke saath {slot} ke liye hai. {state_text}. Arrival ka time confirm nahi hai.", []
    state_text = "It is waiting for confirmation from the caregiver." if status == "requested" else f"Its current status is {status}."
    return f"Your booking is with {caregiver} for {slot}. {state_text} I don’t have a confirmed arrival time.", []


def _care_context(care: dict, symptoms: list[str]) -> CareContext | None:
    if not care.get("care_type") or not care.get("urgency"):
        return None
    return CareContext(care_type=care["care_type"], urgency=care["urgency"], reasoning=care.get("reasoning", ""), symptoms=symptoms)


@router.post("/chat", response_model=AssistantResponse)
def chat(request: AssistantRequest):
    # Use only the latest message to select language and script for this reply.
    language = "Hindi" if request.language == "hi-IN" else "English" if request.language == "en-IN" else _detect_language(request.message)
    context = _prior_care_context(request)
    routing_message = _fuzzy_correct(transliterate_to_devanagari(request.message))
    prior_emergency = _latest_turn_is_emergency(request.history)
    reset_after_emergency = _latest_turn_is_emergency(request.history)
    intake_state = IntakeState() if reset_after_emergency else _prior_intake_state(request)
    pending_question = intake_state.pending_question
    has_prior_context = bool(context or any(x.get("role") == "user" and (x.get("content") or x.get("text")) for x in request.history))
    prior_turns = [] if reset_after_emergency else _active_user_turns(request.history)
    screen_yes, consumed = _consume_guided_answer(intake_state, request.message) if pending_question else (False, False)
    home_chip = bool(re.fullmatch(HOME_VISIT_CHIP, routing_message.strip(), re.I))
    doctor_chip = bool(re.fullmatch(DOCTOR_CHIP, routing_message.strip(), re.I))
    show_caregivers_chip = bool(re.fullmatch(SHOW_CAREGIVERS_CHIP, routing_message.strip(), re.I))
    action_chip = home_chip or doctor_chip or show_caregivers_chip
    if home_chip: intake_state.preference = "home_visit"
    if doctor_chip: intake_state.preference = "online_doctor"
    latest_clinical = not consumed and not action_chip
    current_safety = transliterate_to_devanagari(request.message) if latest_clinical else ""
    active_text = " ".join([*prior_turns, *([current_safety] if current_safety else [])])
    flags = check_red_flags(active_text)
    if re.search(r"\b(?:bleeding heavily|heavy bleeding|bleeding a lot|bleeding won.t stop|bleeding profusely)\b|(?:बहुत तेज़? रक्तस्राव|बहुत खून बह रहा|खून बहुत बह रहा)", active_text, re.I):
        flags = list(dict.fromkeys([*flags, "severe_bleeding"]))
    symptoms = list(dict.fromkeys((context.symptoms if context and not reset_after_emergency else []) + intake_state.symptoms + _extract_symptoms(active_text)))
    if latest_clinical:
        intake_state = _merge_intake_state(intake_state, active_text, request.message)
    intake_state.symptoms = list(dict.fromkeys([*intake_state.symptoms, *symptoms]))
    if not intake_state.symptom_text and intake_state.symptoms:
        intake_state.symptom_text = "; ".join(intake_state.symptoms)
    service_words = {"home_nursing": "home nursing requested", "lab_test_home": "home lab test requested", "paramedic_home_visit": "home visit requested", "teleconsultation": "doctor consultation requested"}
    triage_text = "; ".join(filter(None, [intake_state.symptom_text, " ".join(intake_state.symptoms), service_words.get(intake_state.requested_service or "", ""), intake_state.duration or "", intake_state.who or ""]))
    care_request = IntakeRequest(user_input=triage_text or request.message, language="auto", location=request.location, conversation_history=[{"role": "user", "content": text} for text in prior_turns])

    # Safety routing always precedes conversational intent handling.
    if flags:
        care = run_triage(care_request)
        care["red_flags"] = list(dict.fromkeys([*(care.get("red_flags") or []), *flags]))
        care["care_type"] = "emergency_112"
        care["urgency"] = "emergency"
        care["follow_up_question"] = None
        care["matched_caregivers"] = []
        updated_context = _care_context(care, symptoms) or context
        message = _emergency_message(language)
        spoken = answer_agent.spoken_text(message, language, "emergency", updated_context.model_dump() if updated_context else None)
        return AssistantResponse(mode="emergency", message=message, spoken_message=spoken, care=care, language=language, suggestions=_suggestions("emergency", language), care_context=updated_context, intake_state=intake_state)

    if screen_yes:
        care = {"follow_up_question": None, "care_type": "emergency_112", "urgency": "emergency", "red_flags": ["red_flag_screen_confirmed"], "reasoning": "The user confirmed a red-flag symptom during safety screening.", "matched_caregivers": []}
        message = _emergency_message(language)
        return AssistantResponse(mode="emergency", message=message, spoken_message=message, care=care, language=language, suggestions=[], care_context=context, intake_state=intake_state)

    if re.search(BOOKING_STATUS, routing_message, re.I):
        message, suggestions = _booking_status_message(request.booking_context, language)
        message = _emergency_reminder(message, language, prior_emergency)
        spoken = answer_agent.spoken_text(message, language, "answer", context.model_dump() if context else None)
        return AssistantResponse(mode="answer", message=message, spoken_message=spoken, care=None, language=language, suggestions=suggestions, care_context=context, intake_state=intake_state)

    # A short follow-up about the previous result explains that result directly;
    # it must not send a new request through triage.
    if context and _is_explanation_request(request.message):
        message = answer_agent.explain_decision(context.model_dump(), language)
        message = _emergency_reminder(message, language, prior_emergency)
        spoken = answer_agent.spoken_text(message, language, "answer", context.model_dump())
        return AssistantResponse(mode="answer", message=message, spoken_message=spoken, care=None, language=language, suggestions=_suggestions("answer", language), care_context=context, intake_state=intake_state)

    if context and _is_next_steps_request(request.message):
        message = _next_steps(context, request.booking_context, language)
        message = _emergency_reminder(message, language, prior_emergency)
        spoken = answer_agent.spoken_text(message, language, "answer", context.model_dump())
        return AssistantResponse(mode="answer", message=message, spoken_message=spoken, care=None, language=language, suggestions=_suggestions("answer", language), care_context=context, intake_state=intake_state)

    information_request = _is_information_request(request.message)
    if information_request and symptoms:
        message = answer_agent.generate("answer", request.message, language, context=", ".join(symptoms))
        message = _emergency_reminder(message, language, prior_emergency)
        spoken = answer_agent.spoken_text(message, language, "answer", context.model_dump() if context else None)
        return AssistantResponse(mode="answer", message=message, spoken_message=spoken, care=None, language=language, suggestions=_suggestions("answer", language), care_context=context, intake_state=intake_state)

    vague_intake = bool(re.fullmatch(UNCLEAR_CARE, routing_message.strip(), re.I)) or (re.fullmatch(r"(?:yes|haan|हाँ|हां)[!. ]*", routing_message.strip(), re.I) and not symptoms and not intake_state.requested_service)
    explicit_service = "paramedic_home_visit" if home_chip else "teleconsultation" if doctor_chip else intake_state.requested_service or (context.care_type if show_caregivers_chip and context else None)
    if home_chip:
        intake_state.preference = "home_visit"
        intake_state.requested_service = "paramedic_home_visit"
    elif doctor_chip:
        intake_state.preference = "online_doctor"
        intake_state.requested_service = "teleconsultation"
    if explicit_service and context:
        symptom_text = ", ".join(symptoms or context.symptoms)
        service_text = {"paramedic_home_visit": "medic home visit", "teleconsultation": "virtual doctor consultation", "home_nursing": "home nursing", "lab_test_home": "home lab test"}.get(explicit_service, "care option")
        care_request.user_input = f"{service_text} requested for the same problem: {symptom_text or 'previous care concern'}"
    intent = "care" if explicit_service and (context or intake_state.symptoms) or pending_question or vague_intake else _rule_intent(routing_message)
    if intent is None:
        try:
            classified = sarvam_client.chat_json(CLASSIFY_SYSTEM, routing_message, IntentClassification)
            intent = (classified or {}).get("intent")
        except Exception:
            intent = None
    if intent is None:
        intent = "followup" if not has_prior_context else "answer"
    elif intent == "followup" and has_prior_context:
        intent = "answer"

    care = None
    updated_context = context
    mode = intent
    if intent == "care":
        if not symptoms and not intake_state.requested_service and not explicit_service:
            question, chips = GUIDED_ANSWERS[language]["who_problem"]
            intake_state.pending_question = "who_problem"
            return AssistantResponse(mode="followup", message=question, spoken_message=question, care=None, language=language, suggestions=chips, care_context=context, intake_state=intake_state)
        guided_question = None if explicit_service else _next_guided_question(intake_state, language, vague=vague_intake)
        if guided_question:
            question, chips = guided_question
            question = _emergency_reminder(question, language, prior_emergency)
            return AssistantResponse(mode="followup", message=question, spoken_message=question, care=None, language=language, suggestions=chips, care_context=context, intake_state=intake_state)
        care = run_triage(care_request)
        mild_service = _mild_symptom_service(triage_text, intake_state) if not explicit_service else None
        if mild_service and care.get("care_type") != "emergency_112" and not care.get("follow_up_question"):
            care["care_type"] = mild_service
            care["urgency"] = "same_day"
            from app.core.matching import match
            from app.core.reasoning import explain_for_assistant
            care["matched_caregivers"] = match(mild_service, request.location, language, triage_text)
            care["reasoning"] = explain_for_assistant(mild_service, "same_day", [], triage_text, language)
        if explicit_service and care.get("care_type") != "emergency_112" and not care.get("follow_up_question"):
            care["care_type"] = explicit_service
            care["urgency"] = "same_day"
            from app.core.matching import match
            care["matched_caregivers"] = match(explicit_service, request.location, language, care_request.user_input)
            from app.core.reasoning import explain_for_assistant
            care["reasoning"] = explain_for_assistant(explicit_service, "same_day", [], care_request.user_input, language)
        new_context = _care_context(care, symptoms)
        if new_context:
            updated_context = new_context
        if care.get("care_type") == "emergency_112":
            mode = "emergency"
            message = _emergency_message(language)
        elif care.get("follow_up_question"):
            mode = "followup"
            message = _localized_followup(care["follow_up_question"], language)
            care["follow_up_question"] = message
        else:
            mode = "care"
            care_label = CARE_LABELS.get(care.get("care_type"), {}).get(language, "care")
            urgency_label = URGENCY_LABELS.get(care.get("urgency"), {}).get(language, "")
            message = f"{care_label}, {urgency_label}." if urgency_label else f"{care_label}."
        if mode == "care" and re.search(QUESTION_WORDS, routing_message, re.I) and re.search(PERSONAL, routing_message, re.I):
            message = f"{message} {answer_agent.care_tip(routing_message, language)}"
    elif intent == "followup":
        message = _template(intent, language)
    else:
        message = answer_agent.generate(intent, request.message, language, context=", ".join(symptoms))

    speech_context = updated_context.model_dump() if updated_context else None
    message = _emergency_reminder(message, language, prior_emergency)
    spoken_message = answer_agent.spoken_text(message, language, mode, speech_context)
    safety = None
    alternatives = None
    if mode == "care" and care:
        from app.core.reasoning import safety_net, why_not
        safety = safety_net(language, care.get("care_type"))
        alternatives = why_not(care.get("care_type"), language, symptoms)
    understood = _intake_summary(intake_state, language) if mode == "care" else None
    return AssistantResponse(mode=mode, message=message, spoken_message=spoken_message, care=care, language=language, suggestions=_suggestions(mode, language), care_context=updated_context, safety_net=safety, why_not=alternatives, intake_state=intake_state, understood=understood)
