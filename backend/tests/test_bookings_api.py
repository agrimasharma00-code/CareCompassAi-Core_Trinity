from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import bookings
from app.db.models import Base, Booking, CheckIn, User

IST = ZoneInfo("Asia/Kolkata")


def setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    patient = User(username="patient1", name="Demo Patient", role="patient", password_hash="hash")
    another_patient = User(username="patient2", name="Patient Two", role="patient", password_hash="hash")
    provider = User(username="CG_001", name="Provider", role="provider", caregiver_id="CG_001", password_hash="hash")
    session.add_all([patient, another_patient, provider])
    session.commit()
    return engine, session, patient, another_patient, provider


def booking_request(slot: datetime):
    return bookings.BookingCreate.model_validate({
        "caregiver_id": "CG_001",
        "slot": slot.isoformat(),
        "triage": {
            "care_type": "paramedic_home_visit",
            "urgency": "same_day",
            "reasoning": "Home assessment requested; urgency assessed as same_day.",
            "red_flags": [],
            "matched_caregivers": [{"caregiver_id": "CG_001", "score": 0.9, "reason": "available"}],
        },
        "care_context": {"care_type": "paramedic_home_visit", "urgency": "same_day", "reasoning": "reason", "symptoms": ["fever"]},
        "history": [{"role": "user", "content": "mummy ko 2 din se bukhar hai"}],
    })


def test_booking_builds_fact_based_handoff_and_checkin(monkeypatch):
    engine, session, patient, _other, _provider = setup_db()
    monkeypatch.setattr(bookings, "load_caregivers", lambda: [{"caregiver_id": "CG_001", "active": "True", "free_from": "09:00", "free_until": "17:00"}])
    slot = (datetime.now(IST) + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    result = bookings.create_booking(booking_request(slot), patient, session)
    assert result["state"] == "requested"
    assert "Who: mummy" in result["handoff_summary"]
    assert "Duration: 2 din" in result["handoff_summary"]
    assert "Symptoms: fever; care service: paramedic_home_visit" in result["handoff_summary"]
    assert "Red flags: none identified by triage" in result["handoff_summary"]
    assert session.scalar(select(CheckIn).where(CheckIn.booking_id == result["id"])) is not None
    engine.dispose()


def test_double_booking_conflict_and_provider_state_transitions(monkeypatch):
    engine, session, patient, another_patient, provider = setup_db()
    monkeypatch.setattr(bookings, "load_caregivers", lambda: [{"caregiver_id": "CG_001", "active": "True", "free_from": "09:00", "free_until": "17:00"}])
    slot = (datetime.now(IST) + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
    created = bookings.create_booking(booking_request(slot), patient, session)
    with pytest.raises(HTTPException) as conflict:
        bookings.create_booking(booking_request(slot), another_patient, session)
    assert conflict.value.status_code == 409

    booking = session.get(Booking, created["id"])
    confirmed = bookings.update_booking(booking.id, bookings.BookingAction(action="confirm"), provider, session)
    assert confirmed["state"] == "confirmed"
    with pytest.raises(HTTPException) as invalid:
        bookings.update_booking(booking.id, bookings.BookingAction(action="complete"), provider, session)
    assert invalid.value.status_code == 409
    in_progress = bookings.update_booking(booking.id, bookings.BookingAction(action="in_progress"), provider, session)
    completed = bookings.update_booking(booking.id, bookings.BookingAction(action="complete"), provider, session)
    assert in_progress["state"] == "in_progress"
    assert completed["state"] == "completed"
    engine.dispose()
