from pathlib import Path

from app.integrations import sarvam_client
from app.core import reasoning

FAQ = Path(__file__).with_name("faq.txt").read_text(encoding="utf-8")

SYSTEM_PROMPT = """You are Priya, a female CareCompass care-navigation assistant in India. Refer to yourself with feminine Hindi forms such as 'मैं मदद कर सकती हूँ' and feminine Hinglish forms such as 'madad kar sakti hoon' and 'dhoondh sakti hoon'. Keep replies short and conversational, usually 3–4 sentences. The target language and script will be specified in this prompt; follow it exactly: Hindi must use Devanagari, Hinglish must use Roman script, and English must use English. Give only general, widely accepted health information. Never diagnose, provide medicine names or doses, or say a condition is 'nothing to worry about'. For general-health answers, end with a brief safety line naming appropriate red flags and calling 112, followed by an offer to help find a doctor. For off_topic, politely say you help with health care and ask how you can help. For app_help, use only the supplied FAQ; do not invent features or promise booking. For smalltalk, greet naturally and invite a health-care request."""

TEMPLATES = {
    "answer": {
        "English": "For general health questions, stay hydrated and seek medical advice if symptoms worsen. If there is chest pain, difficulty breathing, fainting, or confusion, call 112 now. Would you like help finding a doctor?",
        "Hindi": "सामान्य स्वास्थ्य जानकारी के लिए पर्याप्त पानी पिएँ और लक्षण बढ़ें तो डॉक्टर से सलाह लें। सीने में दर्द, सांस लेने में तकलीफ़, बेहोशी या भ्रम हो तो तुरंत 112 पर कॉल करें। क्या मैं डॉक्टर ढूँढने में मदद कर सकती हूँ?",
        "Hinglish": "General health ke liye paani peete rahein aur symptoms badhein to doctor se baat karein. Seene mein dard, saans ki dikkat, behoshi ya confusion ho to turant 112 par call karein. Kya main doctor dhoondhne mein madad kar sakti hoon?",
    },
    "app_help": {
        "English": "CareCompass can suggest a medic home visit, home nursing, a home lab test, or a virtual doctor consultation. Enter your request and location to see a suggested option. Booking is not enabled yet.",
        "Hindi": "यह ऐप घर पर मेडिक विज़िट, नर्सिंग, लैब टेस्ट या ऑनलाइन डॉक्टर परामर्श सुझा सकती है। विकल्प देखने के लिए अपनी ज़रूरत और लोकेशन दर्ज करें। बुकिंग अभी उपलब्ध नहीं है।",
        "Hinglish": "CareCompass medic home visit, home nursing, lab test ya virtual doctor consult suggest kar sakti hai. Apni request aur location daalein. Booking abhi available nahi hai.",
    },
    "smalltalk": {
        "English": "Hello! I’m CareCompass. I can help with health information or finding care. What would you like help with?",
        "Hindi": "नमस्ते! मैं स्वास्थ्य जानकारी देने या देखभाल ढूँढने में मदद कर सकती हूँ। आपको किस चीज़ में मदद चाहिए?",
        "Hinglish": "Namaste! Main CareCompass hoon. Main health jaankari dene ya care dhoondhne mein madad kar sakti hoon. Aapko kis cheez mein madad chahiye?",
    },
    "off_topic": {
        "English": "I help with health care and general health information. What health-related help do you need?",
        "Hindi": "मैं स्वास्थ्य सेवा और सामान्य स्वास्थ्य जानकारी में मदद करती हूँ। आपको स्वास्थ्य से जुड़ी किस मदद की ज़रूरत है?",
        "Hinglish": "Main health care aur general health jaankari mein madad karti hoon. Aapko health se judi kya madad chahiye?",
    },
}


def care_tip(message: str, language: str) -> str:
    text = message.lower()
    fever = any(word in text for word in ("fever", "bukhar", "बुखार"))
    if fever:
        return {
            "English": "While arranging care, offer fluids and rest.",
            "Hindi": "देखभाल की व्यवस्था करते समय तरल पदार्थ दें और आराम करने दें।",
            "Hinglish": "Care arrange karte waqt fluids dein aur aaram karne dein.",
        }[language]
    return {
        "English": "I can also share general information while you arrange care.",
            "Hindi": "देखभाल की व्यवस्था करते समय मैं सामान्य जानकारी भी दे सकती हूँ।",
            "Hinglish": "Care arrange karte waqt main general jaankari bhi de sakti hoon.",
    }[language]


SYMPTOM_LABELS = {
    "headache": {"English": "headache", "Hindi": "सिरदर्द", "Hinglish": "sir dard"},
    "fever": {"English": "fever", "Hindi": "बुखार", "Hinglish": "bukhar"},
    "cough": {"English": "cough", "Hindi": "खांसी", "Hinglish": "khansi"},
    "cold": {"English": "a cold", "Hindi": "सर्दी-जुकाम", "Hinglish": "sardi-zukham"},
    "stomach pain": {"English": "stomach pain", "Hindi": "पेट दर्द", "Hinglish": "pet dard"},
    "body ache": {"English": "body ache", "Hindi": "बदन दर्द", "Hinglish": "badan dard"},
    "acidity": {"English": "acidity", "Hindi": "एसिडिटी", "Hinglish": "acidity"},
    "weakness": {"English": "weakness", "Hindi": "कमज़ोरी", "Hinglish": "kamzori"},
    "nausea": {"English": "nausea", "Hindi": "मतली", "Hinglish": "ji michlana"},
    "vomiting": {"English": "vomiting", "Hindi": "उल्टी", "Hinglish": "ulti"},
    "diarrhea": {"English": "diarrhea", "Hindi": "दस्त", "Hinglish": "dast"},
}


def explain_decision(context: dict, language: str) -> str:
    from app.core.reasoning import explain_for_assistant, safety_net, why_not

    care_type = context.get("care_type", "teleconsultation")
    urgency = context.get("urgency", "same_day")
    symptoms = context.get("symptoms") or []
    symptom_text = ", ".join(symptoms)
    parts = [explain_for_assistant(care_type, urgency, [], symptom_text, language), why_not(care_type, language), safety_net(language)]
    return " ".join(parts)


def spoken_text(message: str, language: str, mode: str, context: dict | None = None) -> str:
    if language == "English" or language == "Hindi":
        return message
    try:
        translated = sarvam_client.chat_text([
            {"role": "system", "content": "Translate the assistant message into natural Hindi written entirely in Devanagari. Preserve its meaning and safety instructions. Use feminine first-person Hindi forms. Output only the Hindi translation."},
            {"role": "user", "content": message},
        ])
        if translated and translated.strip():
            return translated.strip()
    except Exception:
        pass
    if mode == "emergency":
        return "यह आपातकाल हो सकता है। कृपया अभी 112 पर कॉल करें।"
    if mode == "followup":
        from app.core.followup import QUESTION
        return QUESTION["Hindi"]
    if mode == "answer" and context and context.get("care_type"):
        return explain_decision(context, "Hindi")
    if mode == "care" and context:
        return reasoning.explain_for_assistant(context.get("care_type"), context.get("urgency"), [], ", ".join(context.get("symptoms", [])), "Hindi")
    return TEMPLATES.get(mode, TEMPLATES["off_topic"])["Hindi"]


def generate(intent: str, message: str, language: str, context: str = "") -> str:
    faq = FAQ if intent == "app_help" else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + f"\n\nMandatory target language: {language}. Use Devanagari for Hindi, Roman script for Hinglish, and English script for English." + ("\n\nFixed FAQ (use only these facts for app_help):\n" + faq if faq else "")},
        {"role": "user", "content": f"Intent: {intent}\nLanguage: {language}\nUser message: {message}\nRelevant prior symptom/context: {context or 'none'}"},
    ]
    try:
        response = sarvam_client.chat_text(messages)
        if response and response.strip():
            return response.strip()
    except Exception:
        pass
    if intent == "answer" and context:
        labels = [SYMPTOM_LABELS.get(item, {}).get(language, item) for item in context.split(", ") if item]
        symptom = ", ".join(labels)
        if language == "Hindi":
            return f"आपने {symptom} बताया था। इसके कई कारण हो सकते हैं; आराम करें और लक्षण बने रहें या बढ़ें तो डॉक्टर से सलाह लें। {reasoning.safety_net(language)} क्या मैं डॉक्टर ढूँढने में मदद कर सकती हूँ?"
        if language == "Hinglish":
            return f"Aapne {symptom} bataya tha. Iske kai kaaran ho sakte hain; aaram karein aur symptoms rahein ya badhein to doctor se baat karein. {reasoning.safety_net(language)} Kya main doctor dhoondhne mein madad kar sakti hoon?"
        return f"You mentioned {symptom}. It can have different causes; rest and seek medical advice if it continues or worsens. {reasoning.safety_net(language)} Would you like me to help find a doctor?"
    return TEMPLATES.get(intent, TEMPLATES["off_topic"])[language]
