import re
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


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1)
    location: Location
    history: list[dict] = Field(default_factory=list)
    language: str = "auto"
    care_context: CareContext | None = None


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


class IntentClassification(BaseModel):
    intent: Literal["care", "answer", "followup", "smalltalk", "app_help", "off_topic"]


CLASSIFY_SYSTEM = """Classify the user's latest message into exactly one intent: care, answer, followup, smalltalk, app_help, off_topic. Return JSON only as {\"intent\": ...}. care means personal symptoms or a requested care service. answer means general health information without a personal care request. followup means it is unclear whether they want care or information. smalltalk means greeting, name, or thanks. app_help means questions about CareCompass usage or services. off_topic means unrelated topics. Never classify an emergency symptom as anything except care; application code handles red flags first."""

QUESTION_WORDS = r"\b(?:kya|kaise|kyun|kyon|what|how|why|when|which|क्या|कैसे|क्यों|कब|कौन)\b"
SERVICE_WORDS = r"home visit|home care|ghar pe|ghar par|nurse|nursing|injection|lab test|blood test|test|sample|consult|doctor|डॉक्टर|नर्स|इंजेक्शन|जांच|टेस्ट|घर पर|घर पे"
SYMPTOMS = r"bukhar|fever|khansi|cough|cold|sardi|zukham|headache|sir.{0,12}dard|stomach.{0,12}(?:ache|pain)|pet.{0,12}dard|pain|dard|दर्द|बुखार|खांसी|जुकाम|सर्दी|सिर में दर्द|पेट में दर्द|कमज़ोरी|कमजोरी|weakness|vomit|उल्टी|diarrhea|दस्त"
PERSONAL = r"\b(?:i have|i am having|i feel|my|mujhe|mere|meri|mujhko|papa|mummy|mother|father|for my|someone|patient)\b|(?:मुझे|मेरे|मेरी|पापा|मम्मी|माता|पिता)"
APP_HELP = r"booking|book (?:a|an|my)? ?(?:doctor|visit|appointment|service)|how (?:do i|can i) book|services (?:do you|are available)|what services|voice input|speak your request|privacy|बुकिंग|बुक कैसे|सेवाएं|सेवाएँ|आवाज़ से"
GREETING = r"^(?:hi|hello|hey|namaste|namaskar|नमस्ते|हेलो|mera naam .{1,40}|my name is .{1,40}|thanks|thank you|धन्यवाद|शुक्रिया)[!. ,?]*$"
OFF_TOPIC = r"\b(?:ipl|cricket|score|homework|maths homework|joke|jokes|football|movie review)\b|आईपीएल|क्रिकेट|होमवर्क|चुटकुला"
GENERAL_HEALTH = r"\b(?:health|fever|bukhar|blood pressure|bp|dehydration|hydration|cough|cold|nutrition|sleep|exercise|headache|symptom|signs?)\b|बुखार|खांसी|पानी की कमी|ब्लड प्रेशर|स्वास्थ्य|लक्षण"

SUGGESTIONS = {
    "emergency": {"English": [], "Hindi": [], "Hinglish": []},
    "care": {"English": ["Talk to a doctor", "Home check-up", "Tell me more"], "Hindi": ["डॉक्टर से बात करें", "घर पर जाँच", "और जानकारी दें"], "Hinglish": ["Doctor se baat karein", "Ghar pe check-up", "Aur detail batayein"]},
    "followup": {"English": ["Yes, I need care", "Just information"], "Hindi": ["हाँ, देखभाल चाहिए", "बस जानकारी चाहिए"], "Hinglish": ["Haan, care chahiye", "Bas jaankari chahiye"]},
    "answer": {"English": ["Talk to a doctor", "Home check-up", "That’s all"], "Hindi": ["डॉक्टर से बात करें", "घर पर जाँच", "बस इतना"], "Hinglish": ["Doctor se baat karein", "Ghar pe check-up", "Nahi, bas itna"]},
    "smalltalk": {"English": ["Fever or cough", "Home injection", "Lab test"], "Hindi": ["बुखार/खांसी", "घर पर इंजेक्शन", "लैब टेस्ट"], "Hinglish": ["Bukhar/khansi", "Injection ghar pe", "Lab test"]},
    "app_help": {"English": ["Available services", "Booking help", "How voice works"], "Hindi": ["उपलब्ध सेवाएँ", "बुकिंग में मदद", "आवाज़ कैसे इस्तेमाल करें"], "Hinglish": ["Services kya hain?", "Booking mein madad", "Voice kaise use karein"]},
    "off_topic": {"English": ["Fever or cough", "Talk to a doctor", "Lab test"], "Hindi": ["बुखार/खांसी", "डॉक्टर से बात", "लैब टेस्ट"], "Hinglish": ["Bukhar/khansi", "Doctor se baat", "Lab test"]},
}

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


def _all_user_text(history: list[dict], current: str) -> str:
    turns = [str(x.get("content", x.get("text", ""))) for x in history if x.get("role") == "user"]
    return " ".join([*turns, current])


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
}


def _extract_symptoms(text: str) -> list[str]:
    return [name for name, pattern in SYMPTOM_PATTERNS.items() if re.search(pattern, text, re.I)]


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


def _is_explanation_request(message: str) -> bool:
    text = message.strip().lower()
    return bool(re.fullmatch(r"(?:aur detail batayein|aur detail|more details?|tell me more|why\??|kyun\??|क्यों\??|और विस्तार से बताइए|और जानकारी दें)[!. ]*", text, re.I))


def _is_information_request(message: str) -> bool:
    text = message.strip().lower()
    return bool(re.search(r"bas jaankari chahiye|bas jankari chahiye|just information|just info|only information|बस जानकारी चाहिए|सिर्फ जानकारी चाहिए", text, re.I))


def _rule_intent(message: str) -> str | None:
    text = message.strip().lower()
    if re.search(APP_HELP, text, re.I):
        return "app_help"
    if re.fullmatch(GREETING, text, re.I):
        return "smalltalk"
    if re.search(OFF_TOPIC, text, re.I):
        return "off_topic"
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
    return None


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


def _care_context(care: dict, symptoms: list[str]) -> CareContext | None:
    if not care.get("care_type") or not care.get("urgency"):
        return None
    return CareContext(care_type=care["care_type"], urgency=care["urgency"], reasoning=care.get("reasoning", ""), symptoms=symptoms)


@router.post("/chat", response_model=AssistantResponse)
def chat(request: AssistantRequest):
    # Use only the latest message to select language and script for this reply.
    language = "Hindi" if request.language == "hi-IN" else "English" if request.language == "en-IN" else _detect_language(request.message)
    context = _prior_care_context(request)
    routing_message = transliterate_to_devanagari(request.message)
    all_text = transliterate_to_devanagari(_all_user_text(request.history, request.message))
    symptoms = list(dict.fromkeys((context.symptoms if context else []) + _extract_symptoms(all_text)))
    has_prior_context = bool(context or any(x.get("role") == "user" and (x.get("content") or x.get("text")) for x in request.history))
    care_request = IntakeRequest(user_input=request.message, language="auto", location=request.location, conversation_history=request.history)

    # Safety routing always precedes conversational intent handling.
    flags = check_red_flags(all_text)
    if flags:
        care = run_triage(care_request)
        updated_context = _care_context(care, symptoms) or context
        message = _emergency_message(language)
        spoken = answer_agent.spoken_text(message, language, "emergency", updated_context.model_dump() if updated_context else None)
        return AssistantResponse(mode="emergency", message=message, spoken_message=spoken, care=care, language=language, suggestions=_suggestions("emergency", language), care_context=updated_context)

    # A short follow-up about the previous result explains that result directly;
    # it must not send a new request through triage.
    if context and _is_explanation_request(request.message):
        message = answer_agent.explain_decision(context.model_dump(), language)
        spoken = answer_agent.spoken_text(message, language, "answer", context.model_dump())
        return AssistantResponse(mode="answer", message=message, spoken_message=spoken, care=None, language=language, suggestions=_suggestions("answer", language), care_context=context)

    information_request = _is_information_request(request.message)
    if information_request and symptoms:
        message = answer_agent.generate("answer", request.message, language, context=", ".join(symptoms))
        spoken = answer_agent.spoken_text(message, language, "answer", context.model_dump() if context else None)
        return AssistantResponse(mode="answer", message=message, spoken_message=spoken, care=None, language=language, suggestions=_suggestions("answer", language), care_context=context)

    intent = _rule_intent(routing_message)
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
        care = run_triage(care_request)
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
    spoken_message = answer_agent.spoken_text(message, language, mode, speech_context)
    safety = None
    alternatives = None
    if mode == "care" and care:
        from app.core.reasoning import safety_net, why_not
        safety = safety_net(language, care.get("care_type"))
        alternatives = why_not(care.get("care_type"), language, symptoms)
    return AssistantResponse(mode=mode, message=message, spoken_message=spoken_message, care=care, language=language, suggestions=_suggestions(mode, language), care_context=updated_context, safety_net=safety, why_not=alternatives)
