"""Public caregiver recommendations layered over the scored matcher."""
from app.core.loaders import load_caregivers
from app.core.matching import distance_km, match, required_skill

ROLE_LABELS = {"medic": "Medic (home visit)", "doctor": "Doctor (virtual)", "phlebotomist": "Phlebotomist (home sample collection)"}
SKILL_LABELS = {"vitals_monitoring": "Vitals monitoring", "injection_im": "Injection", "wound_dressing": "Wound dressing", "catheter_care": "Catheter care", "injection_iv": "IV care", "sample_collection": "Sample collection", "teleconsultation": "Teleconsultation", "prescription": "Prescription review", "report_review": "Report review"}


def recommend(care_type, intake_state, location, language, preferred_time=None, top_k=5):
    state = intake_state or {}
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    text = " ".join([state.get("symptom_text") or "", *(state.get("symptoms") or [])])
    scored = match(care_type, location, language, text)
    by_id = {item["caregiver_id"]: item for item in scored}
    role = {"paramedic_home_visit": "medic", "home_nursing": "medic", "lab_test_home": "phlebotomist", "teleconsultation": "doctor"}.get(care_type)
    skill = required_skill(text)
    desired = "English" if language == "English" else "Hindi"
    candidates = []
    for caregiver in load_caregivers():
        cid = caregiver["caregiver_id"]
        if cid not in by_id or caregiver["role"] != role:
            continue
        virtual = role == "doctor"
        km = None if virtual else distance_km(location.lat, location.lng, float(caregiver["base_lat"]), float(caregiver["base_lng"]))
        radius = max(float(caregiver["max_radius_km"]), 0.001)
        languages, skills = caregiver["languages"].split(";"), caregiver["skills"].split(";")
        prox = 1.0 if virtual else max(0.0, min(1.0, 1 - (km or 0) / radius))
        free_from, free_until = caregiver["free_from"], caregiver["free_until"]
        candidates.append({
            "caregiver_id": cid, "rank": 0, "name": caregiver["name"], "role": role,
            "role_label": ROLE_LABELS.get(role, role), "qualification": caregiver["qualification"],
            "gender": caregiver["gender"], "languages": languages,
            "skills_matched": [SKILL_LABELS.get(s, s.replace("_", " ").title()) for s in skills if not skill or s == skill],
            "all_skills": [SKILL_LABELS.get(s, s.replace("_", " ").title()) for s in skills],
            "base_area": caregiver["base_area"], "distance_km": round(km, 1) if km is not None else None,
            "travel_estimate_min": round((km or 0) / 20 * 60) if km is not None else None,
            "rating": float(caregiver["rating"]), "experience_years": int(caregiver["experience_years"]),
            "tier": caregiver["tier"] or None, "available_today": f"{free_from}–{free_until}",
            "next_free_slot": free_from, "score": by_id[cid]["score"],
            "score_breakdown": {"language": .35 if desired in languages else 0, "proximity": round(.30 * prox, 2), "skill": .20 if skill and skill in skills else .10, "rating": round(.15 * float(caregiver["rating"]) / 5, 2)},
            "reason": by_id[cid]["reason"],
            "why_ranked": f"Speaks {desired}; " + (f"{km:.1f} km away" if km is not None else "virtual doctor") + f"; available {free_from}–{free_until}",
        })
    # Preserve the scored matcher's established ordering for the first three.
    candidates.sort(key=lambda c: (-c["score"], c["caregiver_id"]))
    for rank, candidate in enumerate(candidates[:top_k], 1):
        candidate["rank"] = rank
    return candidates[:top_k]
