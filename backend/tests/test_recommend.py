from app.core.matching import match
from app.core.recommend import recommend
from app.schemas.care import Location


def test_recommendations_show_csv_names_and_preserve_scored_top_three():
    location = Location(lat=28.6139, lng=77.209)
    state = {"symptoms": ["fever"], "symptom_text": "fever"}
    expected = match("paramedic_home_visit", location, "English", "fever")
    actual = recommend("paramedic_home_visit", state, location, "English", top_k=5)
    assert [item["caregiver_id"] for item in actual[:3]] == [item["caregiver_id"] for item in expected]
    assert all(item["name"] and item["role_label"] for item in actual)
