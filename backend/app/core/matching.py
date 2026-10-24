"""In-memory caregiver filtering and transparent weighted ranking."""

import math
from dataclasses import dataclass

from app.config import settings
from app.core.loaders import load_caregivers
from app.schemas.care import Location, MatchedCaregiver


@dataclass(frozen=True)
class Candidate:
    profile: dict
    distance_km: float
    score: float


def haversine_km(origin: Location, lat: float, lng: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(origin.lat), math.radians(lat)
    delta_phi, delta_lambda = math.radians(lat - origin.lat), math.radians(lng - origin.lng)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def inferred_skill(text: str) -> str | None:
    lower = text.lower()
    mapping = {"fever": "fever", "bukhar": "fever", "cough": "cough", "khansi": "cough", "wound": "wound_dressing", "dressing": "wound_dressing", "blood sample": "sample_collection", "lab test": "sample_collection"}
    return next((skill for marker, skill in mapping.items() if marker in lower), None)


def _availability_score(slots: list[str]) -> float:
    first = slots[0].lower()
    return 1.0 if "today" in first else 0.5


def _score(profile: dict, distance_km: float, language: str, skill: str | None) -> float:
    skill_score = 1.0 if skill is None or skill in profile["skills"] else 0.0
    distance_score = math.exp(-distance_km / 5)
    availability_score = _availability_score(profile["available_slots"])
    language_score = 1.0 if language in profile["languages"] else 0.0
    rating_score = min(float(profile["rating"]) / 5.0, 1.0)
    return (
        settings.skill_weight * skill_score
        + settings.distance_weight * distance_score
        + settings.availability_weight * availability_score
        + settings.language_weight * language_score
        + settings.rating_weight * rating_score
    )


def _reason(profile: dict, distance_km: float, language: str) -> str:
    pieces: list[str] = []
    if language in profile["languages"]:
        display_language = {"hi": "Hindi", "en": "English", "hinglish": "Hinglish"}.get(language, language.title())
        pieces.append(f"{display_language}-speaking")
    pieces.append(f"{distance_km:.1f} km away")
    pieces.append(f"free {profile['available_slots'][0]}")
    return ", ".join(pieces)


def match_caregivers(care_type: str, location: Location, language: str, text: str) -> list[MatchedCaregiver]:
    """Filter hard constraints first, then rank up to three transparent candidates."""
    skill = inferred_skill(text)
    eligible: list[tuple[dict, float]] = []
    for profile in load_caregivers():
        distance_km = haversine_km(location, profile["lat"], profile["lng"])
        care_types = profile.get("care_types", (profile["role"],))
        is_virtual = care_type in {"gp_teleconsult", "specialist"}
        if care_type not in care_types or not profile["available_slots"] or (not is_virtual and distance_km > min(settings.max_distance_km, profile.get("max_radius_km", settings.max_distance_km))):
            continue
        if skill is not None and skill not in profile["skills"]:
            continue
        eligible.append((profile, distance_km))
    language_matched = [(profile, distance) for profile, distance in eligible if language in profile["languages"]]
    candidates = language_matched or eligible
    ranked = [Candidate(profile, distance, _score(profile, distance, language, skill)) for profile, distance in candidates]
    ranked.sort(key=lambda candidate: candidate.score, reverse=True)
    return [
        MatchedCaregiver(caregiver_id=candidate.profile["id"], score=round(candidate.score, 3), reason=_reason(candidate.profile, candidate.distance_km, language))
        for candidate in ranked[:3]
    ]
