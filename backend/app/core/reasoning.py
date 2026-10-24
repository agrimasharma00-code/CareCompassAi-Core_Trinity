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


def why_not(care_type, language="English"):
    alternatives = [name[language] for key, name in CARE_NAMES.items() if key not in (care_type, "emergency_112")]
    chosen = CARE_NAMES.get(care_type, CARE_NAMES["teleconsultation"])[language]
    if language == "Hindi":
        return f"अन्य विकल्प ({', '.join(alternatives)}) नहीं चुने गए क्योंकि आपकी बताई ज़रूरत {chosen} से बेहतर मेल खाती है।"
    if language == "Hinglish":
        return f"Dusre options ({', '.join(alternatives)}) nahi chune, kyunki aapki batayi zaroorat {chosen} se zyada match karti hai."
    return f"Other options ({', '.join(alternatives)}) were not selected because your request best matches {chosen}."


def safety_net(language="English"):
    if language == "Hindi":
        return "सीने में दर्द, सांस लेने में तकलीफ़, बेहोशी या भ्रम हो तो तुरंत 112 पर कॉल करें।"
    if language == "Hinglish":
        return "Seene mein dard, saans ki dikkat, behoshi ya confusion ho to turant 112 par call karein."
    return "If there is chest pain, difficulty breathing, fainting, or confusion, call 112 immediately."


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
