import json
from pathlib import Path

CARE_NAMES = {
    "teleconsultation": {"English": "virtual doctor consultation", "Hindi": "ऑनलाइन डॉक्टर से परामर्श", "Hinglish": "online doctor se salah"},
    "paramedic_home_visit": {"English": "medic home visit", "Hindi": "घर पर मेडिक विज़िट", "Hinglish": "ghar par medic visit"},
    "home_nursing": {"English": "nursing at home", "Hindi": "घर पर नर्सिंग सेवा", "Hinglish": "ghar par nursing service"},
    "lab_test_home": {"English": "lab test at home", "Hindi": "घर पर लैब टेस्ट", "Hinglish": "ghar par lab test"},
    "emergency_112": {"English": "emergency services", "Hindi": "आपातकालीन सेवा", "Hinglish": "emergency seva"},
}
URGENCY_NAMES = {
    "same_day": {"English": "same day", "Hindi": "आज ही", "Hinglish": "aaj hi"},
    "scheduled": {"English": "scheduled", "Hindi": "निर्धारित समय पर", "Hinglish": "tay samay par"},
    "emergency": {"English": "emergency", "Hindi": "आपातकालीन", "Hinglish": "emergency"},
}


def why_not(care_type, language="English", facts=None):
    alternatives = [(key, name[language]) for key, name in CARE_NAMES.items() if key not in (care_type, "emergency_112")]
    chosen = CARE_NAMES.get(care_type, CARE_NAMES["teleconsultation"])[language]
    symptom_names = {
        "English": {"headache": "headache", "fever": "fever", "cough": "cough", "cold": "cold", "stomach pain": "stomach pain", "body ache": "body ache", "acidity": "acidity", "weakness": "weakness", "nausea": "nausea", "vomiting": "vomiting", "diarrhea": "diarrhea"},
        "Hindi": {"headache": "सिरदर्द", "fever": "बुखार", "cough": "खांसी", "cold": "सर्दी", "stomach pain": "पेट दर्द", "body ache": "बदन दर्द", "acidity": "एसिडिटी", "weakness": "कमज़ोरी", "nausea": "मतली", "vomiting": "उल्टी", "diarrhea": "दस्त"},
        "Hinglish": {"headache": "sir dard", "fever": "bukhar", "cough": "khansi", "cold": "sardi", "stomach pain": "pet dard", "body ache": "badan dard", "acidity": "acidity", "weakness": "kamzori", "nausea": "matli", "vomiting": "ulti", "diarrhea": "dast"},
    }
    known = [symptom_names[language].get(str(item), str(item)) for item in (facts or []) if str(item) in symptom_names[language]]
    observed = ", ".join(known) if known else None
    lines = [f"{name} was not selected because the reported {observed or 'care need'} is better matched by {chosen}." for _key, name in alternatives]
    if language == "Hindi":
        return "\n".join(f"{name} नहीं चुना गया क्योंकि बताई गई {observed or 'देखभाल की ज़रूरत'} के लिए {chosen} बेहतर मेल खाता है।" for _key, name in alternatives)
    if language == "Hinglish":
        return "\n".join(f"{name} nahi chuna, kyunki bataye gaye {observed or 'care need'} ke liye {chosen} zyada sahi hai." for _key, name in alternatives)
    if lines:
        lines[0] = "Other options: " + lines[0]
    return "\n".join(lines)


def safety_net(language="English", care_type=None):
    with (Path(__file__).with_name("safety_net_signs.json")).open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    signs = catalog.get(care_type or "", catalog["teleconsultation"])[language]
    if language == "Hindi":
        return f"ध्यान रखें: {signs} दिखें तो 112 पर कॉल करें।"
    if language == "Hinglish":
        return f"Dhyan rakhein: {signs} dikhein to 112 par call karein."
    return f"Watch for: {signs}. If any appear, call 112."


def explain(care_type, urgency, flags, text):
    # Keep the scored endpoint's established reasoning text unchanged.
    if flags:
        return f"Red-flag symptoms detected ({', '.join(flags)}); routed to emergency services, not home care."
    t = text.lower()
    if care_type == "home_nursing":
        lead = "Specific nursing procedure requested; Medic home visit"
    elif care_type == "lab_test_home":
        lead = "Home sample collection requested; lab service"
    elif care_type == "teleconsultation":
        lead = "Request suitable for a virtual doctor consult"
    else:
        lead = "Home assessment requested; Medic home visit"
    return f"{lead}; urgency assessed as {urgency}."


def explain_for_assistant(care_type, urgency, flags, text, language="English"):
    if flags:
        if language == "Hindi":
            return f"खतरे के संकेत ({', '.join(flags)}) मिले हैं; इसलिए आपातकालीन सेवा सुझाई गई है।"
        if language == "Hinglish":
            return f"Red-flag signs ({', '.join(flags)}) mile hain, isliye emergency seva suggest ki gayi hai."
        return f"Red-flag symptoms detected ({', '.join(flags)}); routed to emergency services, not home care."
    if language == "Hindi":
        name = CARE_NAMES.get(care_type, CARE_NAMES["paramedic_home_visit"])[language]
        priority = URGENCY_NAMES.get(urgency, {}).get(language, urgency)
        return f"आपकी बताई परेशानी और ज़रूरत के आधार पर {name} चुना गया है; प्राथमिकता {priority} है।"
    if language == "Hinglish":
        name = CARE_NAMES.get(care_type, CARE_NAMES["paramedic_home_visit"])[language]
        priority = URGENCY_NAMES.get(urgency, {}).get(language, urgency)
        return f"Aapki batayi problem aur zaroorat ke hisaab se {name} chuna hai; priority {priority} hai."
    t = text.lower()
    if care_type == "home_nursing":
        lead = "A specific nursing procedure was requested"
    elif care_type == "lab_test_home":
        lead = "Home sample collection was requested"
    elif care_type == "teleconsultation":
        lead = "The request is suitable for a virtual doctor consult"
    else:
        lead = "An in-person home assessment fits the request"
    priority = URGENCY_NAMES.get(urgency, {}).get(language, urgency)
    return f"{lead}; urgency assessed as {priority}."
