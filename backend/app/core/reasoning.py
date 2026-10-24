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


def safety_netting(red_flags: list[str], urgency: str | None) -> str:
    if red_flags or urgency == "immediate":
        return "Call 5555 now. Do not wait for a home visit or a reply from this demo service."
    if urgency == "same_day":
        return "If breathing trouble, chest pain, fainting, heavy bleeding, a seizure, or sudden worsening appears, call 5555 immediately."
    return "If symptoms worsen or any breathing trouble, chest pain, fainting, heavy bleeding, or seizure appears, call 5555 immediately."


def why_not_explanation(red_flags: list[str], care_type: str | None) -> str:
    if red_flags:
        return "Other care options are not shown because a red-flag symptom needs emergency help first."
    return f"Emergency referral was not selected because no red-flag symptom was reported. {care_type or 'A follow-up'} remains the safest next step from the available details."


def handoff_summary(facts: IntakeFacts, urgency: str | None, red_flags: list[str]) -> str:
    subject = facts.relation or "Patient"
    duration = f" for {facts.duration}" if facts.duration else ""
    flags = ", ".join(red_flags) if red_flags else "no red flags reported"
    return f"{subject}: {urgency or 'pending'} priority{duration}; {flags}."
