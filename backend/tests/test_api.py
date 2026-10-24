from app.api.care import intake_triage_match
from app.main import health
from app.schemas.care import CareRequest, CareResponse, Location


def test_health_endpoint() -> None:
    assert health() == {"status": "ok"}


def test_endpoint_response_validates_against_contract() -> None:
    response = intake_triage_match(
        CareRequest(
            user_input="Need a nurse for wound dressing for two days",
            language="en",
            location=Location(lat=28.545, lng=77.192),
        )
    )
    parsed = CareResponse.model_validate(response)
    assert parsed.care_type in (None, "nurse")
