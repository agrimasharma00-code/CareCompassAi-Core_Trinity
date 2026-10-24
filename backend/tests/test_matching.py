from app.core.matching import match_caregivers
from app.schemas.care import Location


def test_matching_applies_role_skill_distance_and_availability_filters() -> None:
    matched = match_caregivers("nurse", Location(lat=28.545, lng=77.192), "hi", "Need wound dressing")
    assert [candidate.caregiver_id for candidate in matched] == ["cg-asha-01"]


def test_matching_relaxes_language_only_after_other_hard_filters() -> None:
    matched = match_caregivers("specialist", Location(lat=28.545, lng=77.192), "hi", "skin concern")
    assert [candidate.caregiver_id for candidate in matched] == ["cg-arjun-04"]
