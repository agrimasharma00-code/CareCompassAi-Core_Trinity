from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import conversations
from app.db.models import Base, Conversation, User
from app.modules.agents import router as assistant
from app.schemas.care import Location


def request(message, *, history=None, context=None, booking=None):
    return assistant.AssistantRequest(message=message, location=Location(lat=28.54, lng=77.27), history=history or [], care_context=context, booking_context=booking)


def test_home_visit_chip_reuses_previous_symptoms_and_selects_medic_home_visit(monkeypatch):
    seen = {}
    monkeypatch.setattr(assistant, "check_red_flags", lambda _text: [])
    monkeypatch.setattr(assistant, "run_triage", lambda req: seen.update(input=req.user_input) or {"care_type": "teleconsultation", "urgency": "same_day", "follow_up_question": None, "red_flags": [], "reasoning": "old", "matched_caregivers": []})
    context = assistant.CareContext(care_type="teleconsultation", urgency="same_day", reasoning="doctor consult", symptoms=["headache"])
    result = assistant.chat(request("घर पर जाँच", history=[{"role": "user", "content": "मेरे सिर में दर्द है"}], context=context))
    assert result.mode == "care"
    assert result.care["care_type"] == "paramedic_home_visit"
    assert "headache" in seen["input"] and "medic home visit" in seen["input"]


def test_requested_booking_status_waits_for_confirmation_without_arrival_claim(monkeypatch):
    monkeypatch.setattr(assistant, "check_red_flags", lambda _text: [])
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *_args: None)
    result = assistant.chat(request("when will they arrive?", booking={"caregiver_id": "CG_002", "slot": "2026-10-25T11:00:00+05:30", "state": "requested"}))
    assert result.mode == "answer"
    assert "waiting for confirmation" in result.message
    assert "don’t have a confirmed arrival time" in result.message


def test_conversation_endpoint_saves_and_restores_patient_history():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        patient = User(username="patient", name="Patient", role="patient", password_hash="x")
        session.add(patient)
        session.commit()
        payload = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "नमस्ते"}]
        conversations.save_conversation(conversations.ConversationUpdate(messages=payload), patient, session)
        assert conversations.current_conversation(patient, session)["messages"] == payload
        assert session.query(Conversation).count() == 1
    engine.dispose()


def test_demo_provider_picker_lists_active_roster_entries():
    from app.api.auth import demo_providers
    roster = demo_providers()
    assert roster
    assert all(set(("caregiver_id", "name", "role", "area")).issubset(item) for item in roster)
    assert any(item["caregiver_id"] == "CG_001" and item["role"] == "doctor" for item in roster)
