from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import alerts, checkins
from app.api.auth import require_role
from app.db.models import Alert, Base, Booking, CheckIn, Event, User


def setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    patient = User(username="patient", name="Patient", role="patient", password_hash="x")
    dispatch = User(username="dispatch", name="Dispatch", role="dispatch", password_hash="x")
    provider = User(username="provider", name="Provider", role="provider", caregiver_id="CG_001", password_hash="x")
    session.add_all([patient, dispatch, provider])
    session.commit()
    return engine, session, patient, dispatch, provider


def test_alert_flow_role_check_and_recipient_events(monkeypatch):
    engine, session, patient, dispatch, _provider = setup_db()
    second_dispatch = User(username="dispatch2", name="Dispatch 2", role="dispatch", password_hash="x")
    session.add(second_dispatch); session.commit()
    broadcasts = []
    monkeypatch.setattr(alerts.manager, "publish_from_sync", lambda recipients, payload: broadcasts.append((recipients, payload)))
    with pytest.raises(HTTPException) as denied:
        require_role("dispatch")(patient)
    assert denied.value.status_code == 403
    created = alerts.create_alert(alerts.AlertCreate(latitude=28.5, longitude=77.2, red_flags=["chest_pain"], summary="Chest pain", language="Hindi"), patient, session)
    assert created["status"] == "new"
    assert created["language"] == "Hindi"
    assert created["created_at"].endswith("Z")
    assert created["red_flags"] == ["chest_pain"]
    assert session.scalar(select(Event).where(Event.user_id == dispatch.id, Event.entity_type == "alert")) is not None
    accepted = alerts.update_alert(created["id"], alerts.AlertUpdate(action="accept"), dispatch, session)
    assert accepted["status"] == "accepted"
    assert patient.id in broadcasts[-1][0] and dispatch.id in broadcasts[-1][0] and second_dispatch.id in broadcasts[-1][0]
    assert broadcasts[-1][1]["type"] == "alert.updated" and broadcasts[-1][1]["alert"]["status"] == "accepted"
    with pytest.raises(HTTPException) as invalid:
        alerts.update_alert(created["id"], alerts.AlertUpdate(action="arrived"), dispatch, session)
    assert invalid.value.status_code == 409
    engine.dispose()


def test_alert_create_deduplicates_open_alerts_and_alert_list_is_available():
    engine, session, patient, dispatch, _provider = setup_db()
    request = alerts.AlertCreate(latitude=28.5, longitude=77.2, red_flags=["severe_bleeding"], summary="Symptoms: bleeding; Red flags: severe bleeding")
    first = alerts.create_alert(request, patient, session)
    second = alerts.create_alert(request, patient, session)
    assert first["id"] == second["id"]
    assert len(alerts.list_alerts(dispatch, session)) == 1
    assert second["red_flags"] == ["severe_bleeding"]
    assert len(session.scalars(select(Alert)).all()) == 1
    engine.dispose()


@pytest.mark.parametrize(("answer", "expected"), [("same", False), ("better", False), ("worse", True), ("Yes, chest pain", True)])
def test_checkin_runs_triage_and_escalates_for_worse_or_red_flag(monkeypatch, answer, expected):
    engine, session, patient, _dispatch, provider = setup_db()
    booking = Booking(patient_id=patient.id, provider_id=provider.id, caregiver_id="CG_001", slot=datetime.now(timezone.utc) + timedelta(days=1), care_type="teleconsultation", urgency="same_day", handoff_summary="Symptoms: headache", patient_latitude=28.5, patient_longitude=77.2)
    session.add(booking)
    session.flush()
    item = CheckIn(booking_id=booking.id, patient_id=patient.id, due_at=datetime.now(timezone.utc))
    session.add(item)
    session.commit()
    monkeypatch.setattr(checkins.manager, "publish_from_sync", lambda *_args: None)
    monkeypatch.setattr(checkins, "run_triage", lambda _request: {"care_type": "teleconsultation", "urgency": "same_day", "red_flags": [], "reasoning": "ok", "matched_caregivers": []})
    result = checkins.simulate_checkin(item.id, checkins.CheckInAnswer(answer=answer), patient, session)
    assert result["emergency"] is expected
    assert result["care"]["care_type"] == ("emergency_112" if expected else "teleconsultation")
    assert session.get(CheckIn, item.id).state == ("escalated" if expected else answer)
    assert bool(session.scalar(select(Alert).where(Alert.patient_id == patient.id))) is expected
    engine.dispose()
