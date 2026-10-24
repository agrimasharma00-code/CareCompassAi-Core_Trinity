import re
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import require_role
from app.core.loaders import load_caregivers
from app.db.database import get_db
from app.db.models import Booking, CheckIn, Event, User, utc_now
from app.realtime import manager

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])
IST = ZoneInfo("Asia/Kolkata")
CARE_TYPES = {"paramedic_home_visit", "home_nursing", "lab_test_home", "teleconsultation"}
URGENCIES = {"same_day", "scheduled"}


class BookingTriage(BaseModel):
    care_type: str
    urgency: str
    reasoning: str = ""
    red_flags: list[str] = Field(default_factory=list)
    matched_caregivers: list[dict] = Field(default_factory=list)


class BookingCareContext(BaseModel):
    care_type: str
    urgency: str
    reasoning: str = ""
    symptoms: list[str] = Field(default_factory=list)


class BookingCreate(BaseModel):
    caregiver_id: str = Field(min_length=1, max_length=40)
    slot: datetime
    triage: BookingTriage
    care_context: BookingCareContext
    history: list[dict] = Field(default_factory=list)
    patient_latitude: float | None = None
    patient_longitude: float | None = None


class BookingAction(BaseModel):
    action: str
    proposed_slot: datetime | None = None


def _local_slot(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(IST).replace(tzinfo=None, second=0, microsecond=0)
    return value.replace(second=0, microsecond=0)


def _caregiver(caregiver_id: str) -> dict:
    return next((item for item in load_caregivers() if item["caregiver_id"] == caregiver_id and item["active"].lower() == "true"), {})


def _validate_slot(caregiver: dict, value: datetime) -> datetime:
    local = _local_slot(value)
    now = datetime.now(IST).replace(tzinfo=None, second=0, microsecond=0)
    if local <= now:
        raise HTTPException(status_code=422, detail="Choose a future appointment slot")
    try:
        free_from = time.fromisoformat(caregiver["free_from"])
        free_until = time.fromisoformat(caregiver["free_until"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=422, detail="This caregiver has no valid availability window")
    if not (free_from <= local.time() < free_until):
        raise HTTPException(status_code=422, detail=f"Choose a slot between {free_from.strftime('%H:%M')} and {free_until.strftime('%H:%M')} IST")
    return local


def _handoff(triage: BookingTriage, context: BookingCareContext, history: list[dict]) -> str:
    user_text = " ".join(str(turn.get("content", turn.get("text", ""))) for turn in history if turn.get("role") == "user")
    relation_match = re.search(r"\b(?:papa|mummy|mother|father|wife|husband|dadi|nani|nana|dada|son|daughter|child|baby)\b|(?:पापा|मम्मी|माता|पिता|दादी|नानी|बच्चा)", user_text, re.I)
    age_match = re.search(r"\b(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|years?|yrs?|saal|वर्ष|साल)\b", user_text, re.I)
    duration_match = re.search(r"\b(?:\d+\s*(?:days?|din|weeks?|hafte?|months?|mahine?|years?|saal)|since\s+\w+(?:\s+\w+){0,2}|for\s+\w+(?:\s+\w+){0,2})\b|(?:\d+\s*(?:दिन|हफ़्ते|हफ्ते|महीने|साल))", user_text, re.I)
    who = relation_match.group(0) if relation_match else "patient (relation not stated)"
    if age_match:
        who += f", age {age_match.group(1)}"
    symptoms = ", ".join(context.symptoms) if context.symptoms else "not stated"
    red_flags = ", ".join(triage.red_flags) if triage.red_flags else "none identified by triage"
    duration = duration_match.group(0) if duration_match else "not stated"
    reasoning = (triage.reasoning or context.reasoning or "not provided").rstrip(".")
    return "\n".join((
        f"Who: {who}.",
        f"Symptoms: {symptoms}; care service: {triage.care_type}.",
        f"Duration: {duration}.",
        f"Urgency: {triage.urgency}.",
        f"Red flags: {red_flags}.",
        f"Triage reasoning: {reasoning}.",
    ))


def _booking_dict(booking: Booking, session: Session) -> dict:
    patient = session.get(User, booking.patient_id)
    provider = session.get(User, booking.provider_id)
    caregiver = _caregiver(booking.caregiver_id)
    distance_km = None
    if booking.patient_latitude is not None and booking.patient_longitude is not None and caregiver:
        from math import asin, cos, radians, sin, sqrt
        lat1, lon1 = radians(booking.patient_latitude), radians(booking.patient_longitude)
        lat2, lon2 = radians(float(caregiver["base_lat"])), radians(float(caregiver["base_lng"]))
        distance_km = round(6371 * 2 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2)), 1)
    return {
        "id": booking.id,
        "patient_id": booking.patient_id,
        "patient_name": patient.name if patient else "",
        "provider_id": booking.provider_id,
        "provider_name": provider.name if provider else "",
        "caregiver_id": booking.caregiver_id,
        "slot": booking.slot.replace(tzinfo=IST).isoformat(),
        "care_type": booking.care_type,
        "urgency": booking.urgency,
        "handoff_summary": booking.handoff_summary,
        "state": booking.state,
        "proposed_slot": booking.proposed_slot.replace(tzinfo=IST).isoformat() if booking.proposed_slot else None,
        "created_at": booking.created_at.isoformat(),
        "updated_at": booking.updated_at.isoformat(),
        "distance_km": distance_km,
        "caregiver_profile": {"role": caregiver.get("role"), "skills": caregiver.get("skills", "").split(";"), "languages": caregiver.get("languages", "").split(";"), "max_radius_km": caregiver.get("max_radius_km"), "free_from": caregiver.get("free_from"), "free_until": caregiver.get("free_until")},
    }


def _event(session: Session, booking: Booking, event_type: str) -> None:
    payload = {"booking_id": booking.id, "state": booking.state, "caregiver_id": booking.caregiver_id, "slot": booking.slot.replace(tzinfo=IST).isoformat(), "proposed_slot": booking.proposed_slot.replace(tzinfo=IST).isoformat() if booking.proposed_slot else None}
    session.add_all([
        Event(user_id=booking.patient_id, event_type=event_type, entity_type="booking", entity_id=booking.id, payload=payload),
        Event(user_id=booking.provider_id, event_type=event_type, entity_type="booking", entity_id=booking.id, payload=payload),
    ])


@router.post("")
def create_booking(
    request: BookingCreate,
    patient: User = Depends(require_role("patient")),
    session: Session = Depends(get_db),
):
    triage, context = request.triage, request.care_context
    if triage.care_type not in CARE_TYPES or triage.urgency not in URGENCIES or triage.red_flags:
        raise HTTPException(status_code=422, detail="Only non-emergency care recommendations can be booked")
    if (context.care_type, context.urgency) != (triage.care_type, triage.urgency):
        raise HTTPException(status_code=422, detail="The care recommendation context does not match the triage result")
    if not any(item.get("caregiver_id") == request.caregiver_id for item in triage.matched_caregivers):
        raise HTTPException(status_code=422, detail="Choose a caregiver from this care recommendation")
    caregiver = _caregiver(request.caregiver_id)
    provider = session.scalar(select(User).where(User.caregiver_id == request.caregiver_id, User.role == "provider"))
    if not caregiver or provider is None:
        raise HTTPException(status_code=404, detail="This active demo caregiver account is unavailable")
    slot = _validate_slot(caregiver, request.slot)
    booking = Booking(
        patient_id=patient.id,
        provider_id=provider.id,
        caregiver_id=request.caregiver_id,
        slot=slot,
        care_type=triage.care_type,
        urgency=triage.urgency,
        handoff_summary=_handoff(triage, context, request.history),
        patient_latitude=request.patient_latitude,
        patient_longitude=request.patient_longitude,
        state="requested",
    )
    try:
        session.add(booking)
        session.flush()
        session.add(CheckIn(booking_id=booking.id, patient_id=patient.id, due_at=slot + timedelta(hours=6)))
        _event(session, booking, "booking.created")
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="That caregiver is already booked for this slot. Choose another time.")
    session.refresh(booking)
    result = _booking_dict(booking, session)
    manager.publish_from_sync([booking.patient_id, booking.provider_id], {"type": "booking.created", "booking": result})
    return result


@router.get("/mine")
def my_bookings(patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    bookings = session.scalars(select(Booking).where(Booking.patient_id == patient.id).order_by(Booking.created_at.desc())).all()
    return [_booking_dict(item, session) for item in bookings]


@router.get("/incoming")
def incoming_bookings(provider: User = Depends(require_role("provider")), session: Session = Depends(get_db)):
    bookings = session.scalars(select(Booking).where(Booking.provider_id == provider.id).order_by(Booking.created_at.desc())).all()
    return [_booking_dict(item, session) for item in bookings]


@router.get("/profile")
def provider_profile(provider: User = Depends(require_role("provider"))):
    caregiver = _caregiver(provider.caregiver_id or "")
    if not caregiver:
        raise HTTPException(status_code=404, detail="Provider profile not found")
    return {"caregiver_id": provider.caregiver_id, "name": provider.name, "role": caregiver.get("role"), "skills": caregiver.get("skills", "").split(";"), "languages": caregiver.get("languages", "").split(";"), "max_radius_km": caregiver.get("max_radius_km"), "free_from": caregiver.get("free_from"), "free_until": caregiver.get("free_until")}


def _get_booking_for_user(booking_id: int, user: User, session: Session) -> Booking:
    booking = session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if user.role == "patient" and booking.patient_id != user.id or user.role == "provider" and booking.provider_id != user.id:
        raise HTTPException(status_code=403, detail="This booking belongs to another account")
    return booking


@router.patch("/{booking_id}")
def update_booking(
    booking_id: int,
    request: BookingAction,
    user: User = Depends(require_role("patient", "provider")),
    session: Session = Depends(get_db),
):
    booking = _get_booking_for_user(booking_id, user, session)
    action = request.action
    if user.role == "provider":
        allowed = {"confirm": ("requested", "confirmed"), "reject": ("requested", "rejected"), "in_progress": ("confirmed", "in_progress"), "complete": ("in_progress", "completed")}
        if action == "propose_slot":
            if booking.state != "requested" or request.proposed_slot is None:
                raise HTTPException(status_code=409, detail="A new slot can be proposed only for a requested booking")
            caregiver = _caregiver(booking.caregiver_id)
            proposed = _validate_slot(caregiver, request.proposed_slot)
            conflict = session.scalar(select(Booking).where(Booking.caregiver_id == booking.caregiver_id, Booking.slot == proposed, Booking.id != booking.id))
            if conflict:
                raise HTTPException(status_code=409, detail="That caregiver is already booked for the proposed slot")
            booking.proposed_slot = proposed
            _event(session, booking, "booking.updated")
        else:
            transition = allowed.get(action)
            if not transition or booking.state != transition[0]:
                raise HTTPException(status_code=409, detail="This booking action is not allowed in its current state")
            booking.state = transition[1]
            _event(session, booking, "booking.updated")
    else:
        if action == "cancel" and booking.state in {"requested", "confirmed"}:
            booking.state = "cancelled"
            _event(session, booking, "booking.updated")
        elif action == "accept_proposed" and booking.state == "requested" and booking.proposed_slot is not None:
            caregiver = _caregiver(booking.caregiver_id)
            accepted = _validate_slot(caregiver, booking.proposed_slot)
            conflict = session.scalar(select(Booking).where(Booking.caregiver_id == booking.caregiver_id, Booking.slot == accepted, Booking.id != booking.id))
            if conflict:
                raise HTTPException(status_code=409, detail="That caregiver is already booked for the proposed slot")
            booking.slot = accepted
            booking.proposed_slot = None
            _event(session, booking, "booking.updated")
        else:
            raise HTTPException(status_code=409, detail="This booking action is not allowed in its current state")
    booking.updated_at = utc_now()
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="That caregiver is already booked for this slot. Choose another time.")
    session.refresh(booking)
    result = _booking_dict(booking, session)
    manager.publish_from_sync([booking.patient_id, booking.provider_id], {"type": "booking.updated", "booking": result})
    return result
