"""Persistence helpers for patient-confirmed demo intake data."""

from sqlalchemy import select

from app.db.database import SessionLocal, engine
from app.db.models import Base, PatientIntakeRecord
from app.schemas.care import Urgency


def get_patient_record(subject: str) -> dict[str, object]:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        item = session.scalar(select(PatientIntakeRecord).where(PatientIntakeRecord.patient_subject == subject))
        if item is None:
            return {"medications": [], "skin_check": None}
        return {"medications": item.medications or [], "skin_check": item.skin_check}


def save_medications(subject: str, medications: list[dict[str, object]]) -> dict[str, object]:
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        item = session.scalar(select(PatientIntakeRecord).where(PatientIntakeRecord.patient_subject == subject))
        if item is None:
            item = PatientIntakeRecord(patient_subject=subject, medications=medications)
            session.add(item)
        else:
            item.medications = medications
    return get_patient_record(subject)


def save_skin_check(subject: str, skin_check: dict[str, object]) -> None:
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        item = session.scalar(select(PatientIntakeRecord).where(PatientIntakeRecord.patient_subject == subject))
        if item is None:
            item = PatientIntakeRecord(patient_subject=subject, medications=[], skin_check=skin_check)
            session.add(item)
        else:
            item.skin_check = skin_check


def apply_skin_priority(response, subject: str | None):
    """Raise routed urgency one level only for this patient's saved high-risk screen."""
    if not subject or not response.urgency:
        return response
    record = get_patient_record(subject)
    check = record.get("skin_check")
    if not isinstance(check, dict) or check.get("triage_effect") != "raise_priority":
        return response
    next_level = {"routine": "same_day", "same_day": "immediate", "immediate": "immediate"}.get(response.urgency.value)
    if not next_level or next_level == response.urgency.value:
        return response
    prediction = check.get("top_prediction") or {}
    name = prediction.get("name", "a possible high-risk lesion") if isinstance(prediction, dict) else "a possible high-risk lesion"
    confidence = prediction.get("confidence") if isinstance(prediction, dict) else None
    detail = f"Skin image screening flagged {name} for clinician review"
    if isinstance(confidence, (int, float)):
        detail += f" ({confidence:.0%} model confidence)"
    reason = f"{response.reasoning} {detail}. This image model is not a diagnosis."
    return response.model_copy(update={"urgency": Urgency(next_level), "reasoning": reason[:1000]})
