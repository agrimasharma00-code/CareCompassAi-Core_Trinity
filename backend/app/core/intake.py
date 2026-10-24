import re
from app.core.normalize import normalize_text, history_text, detect_language

SHORT_ACKS = {"haan", "han", "ha", "nahi", "nahin", "yes", "no", "ok", "okay", "2 din", "2 days"}
SLOT_PATTERNS = {
    "relation": r"\b(?:papa|mummy|dadi|nani|nana|dada|wife|husband|mother|father|child|baby|son|daughter)\b|(?:पापा|मम्मी|दादी|नानी|नाना|दादा|माता|पिता|बच्चा)",
    "duration": r"\b\d+\s*(?:din|days?|weeks?|hafte?|months?|mahine?|years?|saal)\b|\b(?:since|for)\s+\w+(?:\s+\w+){0,2}",
    "age": r"\b\d+\s*(?:years? old|year|yrs?|months? old|months?)\b|\b(?:aged|age)\s*\d+",
}
SERVICE_RE = re.compile(r"home visit|home care|ghar|at home|lab|test|sample|nurs|injection|insulin|dressing|doctor|consult|teleconsult|घर|जांच|डॉक्टर|नर्स", re.I)

def _user_turns(history):
    return [str(item.get("content", item.get("text", ""))) for item in history or [] if item.get("role") == "user" and (item.get("content") or item.get("text"))]

def _is_underspecified(text):
    normalized = normalize_text(text)
    if normalized in SHORT_ACKS or len(normalized.split()) <= 2 and not re.search(r"\d+\s*(?:day|days|din|week|weeks)", normalized):
        return True
    return False

def _slot_context(previous, latest):
    latest_normalized = normalize_text(latest)
    pieces = []
    for slot, pattern in SLOT_PATTERNS.items():
        if not re.search(pattern, latest_normalized, re.I):
            for turn in reversed(previous):
                normalized = normalize_text(turn)
                match = re.search(pattern, normalized, re.I)
                if match:
                    pieces.append(match.group(0))
                    break
    if not SERVICE_RE.search(latest):
        for turn in reversed(previous):
            if SERVICE_RE.search(turn):
                service = SERVICE_RE.search(turn)
                pieces.append(service.group(0))
                break
    return " ".join(pieces)

def prepare(request):
    latest = normalize_text(request.user_input)
    previous = _user_turns(request.conversation_history)
    joined = history_text(request.conversation_history, request.user_input)
    if _is_underspecified(latest):
        triage_text = joined
        language_text = " ".join(previous + [request.user_input])
    else:
        context = _slot_context(previous, request.user_input)
        triage_text = normalize_text(" ".join([request.user_input, context]))
        language_text = request.user_input
    # Keep the original Unicode marks for red-flag matching (normalization can
    # discard Devanagari vowel marks); safety checks scan every user turn.
    safety_text = " ".join(previous + [request.user_input])
    detected_language = detect_language(language_text)
    if str(getattr(request, "language", "auto")).lower().startswith("hi"):
        detected_language = "Hindi"
    return triage_text, detected_language, safety_text
