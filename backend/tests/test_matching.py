from app.core.loaders import load_caregivers, load_multi_turn_examples, load_vignettes
from app.core.matching import match_caregivers
from app.schemas.care import Location


def test_matching_applies_role_skill_distance_and_availability_filters() -> None:
    matched = match_caregivers("nurse", Location(lat=28.545, lng=77.192), "hi", "Need wound dressing")
    assert [candidate.caregiver_id for candidate in matched] == ["CG_028", "CG_016", "CG_032"]
    assert all("Hindi-speaking" in candidate.reason for candidate in matched)


def test_matching_relaxes_language_only_after_other_hard_filters() -> None:
    matched = match_caregivers("specialist", Location(lat=28.545, lng=77.192), "hi", "skin concern")
    assert [candidate.caregiver_id for candidate in matched] == ["CG_021", "CG_056", "CG_051"]


def test_supplied_dataset_loaders_are_active() -> None:
    assert len(load_caregivers()) == 52
    assert len(load_vignettes()) == 301
    assert len(load_multi_turn_examples()) == 2
