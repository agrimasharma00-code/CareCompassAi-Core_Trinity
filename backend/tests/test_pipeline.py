from app.core.pipeline import CarePipeline
from app.schemas.care import CareRequest, Location


def test_emergency_case_never_returns_caregivers() -> None:
    response = CarePipeline().run(CareRequest(user_input="I have chest pain", location=Location(lat=28.545, lng=77.192)))
    assert response.care_type == "emergency_referral"
    assert response.urgency == "immediate"
    assert response.matched_caregivers == []


def test_explicit_home_lab_request_uses_supplied_roster() -> None:
    response = CarePipeline().run(CareRequest(user_input="Need a blood sample collected at home", location=Location(lat=28.545, lng=77.192)))
    assert response.care_type == "lab_test_home"
    assert response.matched_caregivers
