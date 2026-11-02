"""Explainable urgency score constrained to the existing triage decision."""
from __future__ import annotations

import re

BANDS = {
    "emergency": {"min": 85, "max": 100},
    "same_day": {"min": 40, "max": 84},
    "scheduled": {"min": 0, "max": 39},
}


def compute_urgency_score(intake_state, triage_result: dict) -> dict:
    """Score only explicit intake facts; the triage label controls the band."""
    state = intake_state or {}
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    state = state or {}
    level = triage_result.get("urgency") or "scheduled"
    if level not in BANDS:
        level = "scheduled"
    band = BANDS[level]
    factors = []
    flags = list(dict.fromkeys(triage_result.get("red_flags") or []))
    if flags:
        for flag in flags:
            factors.append({"label": "Red flag", "points": 100, "detail": str(flag)})
        return {"score": 100, "level": "emergency", "band": BANDS["emergency"], "factors": factors, "summary": "A reported red flag requires emergency routing."}

    def add(label: str, points: int, detail: str):
        factors.append({"label": label, "points": points, "detail": detail})

    age = (state.get("age_group") or "").lower()
    who = (state.get("who") or "").lower()
    if age in {"child", "infant"}:
        add("Age group", 10, age)
    elif age == "elderly" or re.search(r"\b(?:65\+|65|dadi|nana|grandparent|grandmother|grandfather)\b", who):
        add("Age group", 10, "Older adult stated")
    else:
        add("Age group", 0, "Not provided")

    duration = (state.get("duration") or "").lower()
    if duration:
        number = re.search(r"\b(\d+)\b", duration)
        days = int(number.group(1)) if number else None
        points = 5 if re.search(r"today|aaj|आज|started today", duration) else 12 if (days is not None and days > 3) or re.search(r"more than|week|weeks|हफ्त|दिन से", duration) else 8 if (days is not None and 1 <= days <= 3) or re.search(r"one|two|three|दिन|days?", duration) else 0
        add("Duration", points, duration)
    else:
        add("Duration", 0, "Not provided")

    text = " ".join([state.get("symptom_text") or "", *(state.get("symptoms") or [])]).lower()
    severity = bool(re.search(r"\b(?:tez|bahut|severe|unbearable|worse)\b", text))
    add("Severity words", 10 if severity else 0, "Severity wording provided" if severity else "Not provided")
    symptom_count = len(set(state.get("symptoms") or []))
    add("Number of symptoms", 6 if symptom_count >= 3 else 0, f"{symptom_count} reported" if symptom_count else "Not provided")
    probability = triage_result.get("urgency_probability")
    if isinstance(probability, (int, float)):
        points = max(0, min(10, round(float(probability) * 10)))
        add("Model probability", points, f"Predicted urgency probability {float(probability):.2f}")
    else:
        add("Model probability", 0, "Not provided")

    # The minimum is the decision's band anchor; transparent fact points only
    # move the score within that band and can never change the triage outcome.
    score = min(band["max"], band["min"] + sum(f["points"] for f in factors))
    return {"score": int(score), "level": level, "band": band, "factors": factors, "summary": f"Score is within the {level.replace('_', ' ')} range selected by care routing."}
