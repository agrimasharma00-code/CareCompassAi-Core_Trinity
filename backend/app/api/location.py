"""Local, dataset-backed location choices for private care matching."""

from fastapi import APIRouter

from app.core.loaders import load_caregivers


router = APIRouter(prefix="/api/v1/location", tags=["location"])


@router.get("/areas")
def service_areas() -> list[dict[str, float | str]]:
    """Expose supplied roster areas; no patient location is stored."""
    areas = {
        (str(caregiver.get("base_area", "")), float(caregiver["lat"]), float(caregiver["lng"]))
        for caregiver in load_caregivers()
        if caregiver.get("base_area")
    }
    return [
        {"label": label, "lat": lat, "lng": lng}
        for label, lat, lng in sorted(areas, key=lambda area: area[0].casefold())
    ]
