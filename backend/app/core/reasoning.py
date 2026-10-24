"""Plain-language explanations built only from routed input facts."""

from app.core.intake import IntakeFacts


def build_reasoning(text: str, facts: IntakeFacts, red_flags: list[str] | None = None) -> str:
    if red_flags:
        return "Emergency warning signs reported: " + ", ".join(red_flags) + "."
    details: list[str] = []
    lower = text.lower()
    for symptom in ("fever", "bukhar", "cough", "khansi", "pain", "dard", "wound"):
        if symptom in lower:
            details.append(symptom)
    if details:
        summary = "Reported " + ", ".join(dict.fromkeys(details))
    else:
        summary = "Based on the care request"
    if facts.duration:
        summary += f" for {facts.duration}"
    if facts.relation:
        summary += f" for {facts.relation}"
    return summary + ". No emergency warning signs were detected in this message."
