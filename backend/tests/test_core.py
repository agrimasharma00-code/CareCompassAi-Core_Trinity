from app.core.red_flags import check, VOCAB
from app.core.pipeline import run
from app.schemas.care import IntakeRequest, IntakeResponse
from app.core import matching
from app.integrations import sarvam_client
from pydantic import BaseModel

def req(text, history=None):
    return IntakeRequest(user_input=text, location={"lat": 28.54, "lng": 77.27}, conversation_history=history or [])

def test_all_red_flags_english_hindi_hinglish():
    examples = {
        "chest_pain": ["chest pain", "सीने में दर्द", "seene mein dard"],
        "breathlessness": ["can't breathe", "सांस नहीं आ रही", "saans nahi aa rahi"],
        "unconsciousness": ["collapsed", "बेहोश", "behosh"],
        "severe_bleeding": ["heavy bleeding", "खून नहीं रुक रहा", "bleeding ruk nahi rahi"],
        "stroke_symptoms": ["face droop", "लकवा", "ek taraf kamzori"],
        "seizure": ["convulsion", "दौरा", "daura"],
        "high_fever_infant": ["baby high fever", "नवजात तेज बुखार", "navjaat tez bukhar"],
        "suicidal_ideation": ["suicide", "आत्महत्या", "khudkushi"],
        "severe_dehydration": ["sunken eyes", "बहुत उल्टी दस्त पेशाब नहीं", "bahut ulti dast peshab nahi"],
    }
    assert set(examples) == set(VOCAB)
    for label, variants in examples.items():
        for phrase in variants:
            assert label in check(phrase), (label, phrase)

def test_symptom_negation_is_direct_and_correct():
    assert "severe_bleeding" in check("bleeding ruk nahi rahi")
    assert "unconsciousness" in check("gir gaye response nahi de rahe")
    assert "breathlessness" not in check("saans ki dikkat nahi hai")
    assert "chest_pain" not in check("no chest pain")

def test_emergency_response_has_no_matches_and_valid_contract():
    out = IntakeResponse.model_validate(run(req("chest pain ho raha hai papa ko")))
    assert out.care_type == "emergency_112"
    assert out.urgency == "emergency"
    assert out.matched_caregivers == []

def test_followup_response_shape():
    out = IntakeResponse.model_validate(run(req("doctor chahiye")))
    assert out.follow_up_question
    assert out.care_type is None and out.urgency is None and out.matched_caregivers == []

def test_multiturn_examples_resolve():
    history = [{"role": "user", "text": "doctor chahiye"}, {"role": "assistant", "follow_up_question": "Who is this for?"}]
    out = run(req("mummy ko 2 din se bukhar hai, ghar pe dikhana hai", history))
    assert out["care_type"] == "paramedic_home_visit"
    assert run(req("chest pain ho raha hai papa ko"))["care_type"] == "emergency_112"

def test_matching_hard_filters_and_reason_formats(monkeypatch):
    rows = [
        {"caregiver_id":"ok","role":"medic","active":"True","languages":"Hindi;English","skills":"vitals_monitoring","base_lat":"28.54","base_lng":"77.27","max_radius_km":"5","rating":"5","free_from":"09:00","free_until":"17:00"},
        {"caregiver_id":"inactive","role":"medic","active":"False","languages":"Hindi","skills":"vitals_monitoring","base_lat":"28.54","base_lng":"77.27","max_radius_km":"5","rating":"5","free_from":"09:00","free_until":"17:00"},
        {"caregiver_id":"wrong-role","role":"doctor","active":"True","languages":"Hindi","skills":"vitals_monitoring","base_lat":"28.54","base_lng":"77.27","max_radius_km":"5","rating":"5","free_from":"09:00","free_until":"17:00"},
        {"caregiver_id":"far","role":"medic","active":"True","languages":"Hindi","skills":"vitals_monitoring","base_lat":"29.5","base_lng":"77.27","max_radius_km":"1","rating":"5","free_from":"09:00","free_until":"17:00"},
    ]
    monkeypatch.setattr(matching, "load_caregivers", lambda: rows)
    loc = req("check").location
    out = matching.match("paramedic_home_visit", loc, "Hindi", "home checkup")
    assert [x["caregiver_id"] for x in out] == ["ok"]
    assert "km away" in out[0]["reason"]
    rows[0]["role"] = "doctor"
    doctor = matching.match("teleconsultation", loc, "Hindi", "doctor consult")
    assert doctor and "km away" not in doctor[0]["reason"]

def test_sarvam_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(sarvam_client, "is_configured", lambda: False)
    assert sarvam_client.chat_json("system", "user", BaseModel) is None
