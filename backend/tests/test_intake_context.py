from app.core.pipeline import run
from app.schemas.care import IntakeRequest
import app.core.normalize as normalize

def req(text, history=None):
    return IntakeRequest(user_input=text, location={"lat": 28.54, "lng": 77.27}, conversation_history=history or [])

def test_doctor_chahiye_alone_asks_followup():
    response = run(req("doctor chahiye"))
    assert response["follow_up_question"]
    assert response["care_type"] is None and response["urgency"] is None

def test_hinglish_fever_with_home_visit_routes_to_paramedic():
    response = run(req("mummy ko bukhar hai, ghar pe dikhana hai"))
    assert response["care_type"] == "paramedic_home_visit"

def test_acidity_with_consult_routes_to_teleconsultation():
    response = run(req("acidity hai, doctor se consult karna hai"))
    assert response["care_type"] == "teleconsultation"


def test_gurmukhi_headache_falls_through_to_non_emergency_triage(monkeypatch):
    monkeypatch.setattr(normalize, "get_settings", lambda: type("Settings", (), {"sarvam_api_key": ""})())
    response = run(req("ਮੇਰੇ ਸਿਰ ਦਰਦ ਹੋ ਰਿਹਾ ਹੈ"))
    assert response["care_type"] in {"teleconsultation", None}
    assert response["care_type"] != "emergency_112"


def test_gurmukhi_chest_pain_routes_to_emergency_with_chest_pain_flag(monkeypatch):
    monkeypatch.setattr(normalize, "get_settings", lambda: type("Settings", (), {"sarvam_api_key": ""})())
    response = run(req("ਪਾਪਾ ਨੂੰ ਸੀਨੇ ਵਿੱਚ ਦਰਦ ਹੈ"))
    assert response["care_type"] == "emergency_112"
    assert "chest_pain" in response["red_flags"]
