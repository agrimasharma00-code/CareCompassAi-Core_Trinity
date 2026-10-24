from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_role
from app.core.pipeline import run as run_triage
from app.core.red_flags import check as check_red_flags
from app.db.database import get_db
from app.db.models import Alert, Booking, CheckIn, Event, User, utc_now
from app.realtime import manager
from app.schemas.care import IntakeRequest, Location

router = APIRouter(prefix="/api/v1/checkins", tags=["check-ins"])


class CheckInAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


@router.get("/mine")
def my_checkins(patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    items = session.scalars(select(CheckIn).where(CheckIn.patient_id == patient.id).order_by(CheckIn.due_at.desc())).all()
    return [{"id": item.id, "booking_id": item.booking_id, "due_at": item.due_at.isoformat(), "state": item.state, "answer": item.answer} for item in items]


@router.post("/{checkin_id}/simulate")
def simulate_checkin(checkin_id: int, request: CheckInAnswer, patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    item = session.get(CheckIn, checkin_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if item.patient_id != patient.id:
        raise HTTPException(status_code=403, detail="This check-in belongs to another account")
    booking = session.get(Booking, item.booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if item.state != "pending":
        raise HTTPException(status_code=409, detail="This check-in has already been answered")
    choice = request.answer.strip().lower()
    prompts = {"worse": "It is getting worse", "same": "It is the same", "better": "It is getting better"}
    answer_text = prompts.get(choice, request.answer.strip())
    flags = check_red_flags(f"{booking.handoff_summary} {answer_text}")
    # Run the same triage pipeline over the recorded care context and check-in answer.
    care = run_triage(IntakeRequest(user_input=answer_text, language="auto", location=Location(lat=0, lng=0), conversation_history=[{"role": "user", "content": booking.handoff_summary}]))
    emergency = bool(flags) or choice == "worse" or care.get("care_type") == "emergency_112"
    if emergency:
        care = {"follow_up_question": None, "care_type": "emergency_112", "urgency": "emergency", "red_flags": flags, "reasoning": "The check-in reported worsening symptoms or a possible red flag. Call 112 now.", "matched_caregivers": []}
        item.state = "escalated"
    else:
        item.state = choice if choice in {"same", "better"} else "same"
    item.answer = choice if choice in {"worse", "same", "better"} else "red_flag" if flags else "same"
    session.add(Event(user_id=patient.id, event_type="checkin.answered", entity_type="checkin", entity_id=item.id, payload={"answer": item.answer, "emergency": emergency, "care_type": care.get("care_type")}))
    alert_payload = None
    if emergency and booking.patient_latitude is not None and booking.patient_longitude is not None:
        alert = Alert(patient_id=patient.id, latitude=booking.patient_latitude, longitude=booking.patient_longitude, red_flags=flags or ["worsening_symptoms"], summary=booking.handoff_summary[:500] or "Emergency concern reported during demo check-in", language="English", status="new")
        session.add(alert)
        session.flush()
        dispatch_ids = list(session.scalars(select(User.id).where(User.role == "dispatch")))
        alert_payload = {"id": alert.id, "patient_id": patient.id, "patient_name": patient.name, "latitude": alert.latitude, "longitude": alert.longitude, "red_flags": alert.red_flags, "summary": alert.summary, "language": alert.language, "status": alert.status, "created_at": alert.created_at.isoformat(), "updated_at": alert.updated_at.isoformat()}
        session.add_all([Event(user_id=uid, event_type="alert.created", entity_type="alert", entity_id=alert.id, payload=alert_payload) for uid in [patient.id, *dispatch_ids]])
    session.commit()
    manager.publish_from_sync([patient.id], {"type": "checkin.updated", "checkin": {"id": item.id, "booking_id": item.booking_id, "state": item.state, "answer": item.answer, "emergency": emergency, "care": care}})
    if alert_payload:
        manager.publish_from_sync([patient.id, *dispatch_ids], {"type": "alert.created", "alert": alert_payload})
    return {"id": item.id, "booking_id": item.booking_id, "state": item.state, "answer": item.answer, "emergency": emergency, "care": care, "message": "Please call 112 now. You can also alert the demo dispatch desk." if emergency else ("Your existing booking remains active." if item.answer == "same" else "Your improvement has been noted."), "red_flags": flags}

