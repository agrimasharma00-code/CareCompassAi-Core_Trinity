from fastapi import APIRouter, HTTPException
from app.core.loaders import load_caregivers

router = APIRouter(prefix="/api/v1/caregivers", tags=["caregivers"])


@router.get("/{caregiver_id}")
def caregiver_profile(caregiver_id: str):
    caregiver = next((item for item in load_caregivers() if item["caregiver_id"] == caregiver_id and item["active"].lower() == "true"), None)
    if caregiver is None:
        raise HTTPException(status_code=404, detail="Active caregiver not found")
    return {"caregiver_id": caregiver_id, "name": caregiver["name"], "role": caregiver["role"], "qualification": caregiver["qualification"], "gender": caregiver["gender"], "languages": caregiver["languages"].split(";"), "skills": caregiver["skills"].split(";"), "base_area": caregiver["base_area"], "rating": float(caregiver["rating"]), "experience_years": int(caregiver["experience_years"]), "tier": caregiver["tier"] or None, "available_today": f"{caregiver['free_from']}–{caregiver['free_until']}"}
