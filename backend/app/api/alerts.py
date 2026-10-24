from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_role
from app.db.database import get_db
from app.db.models import Alert, Event, User, utc_now
from app.realtime import manager

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    latitude: float
    longitude: float
    red_flags: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=500)


class AlertUpdate(BaseModel):
    action: Literal["accept", "en_route", "arrived", "close"]


def _data(alert: Alert, session: Session) -> dict:
    patient = session.get(User, alert.patient_id)
    return {"id": alert.id, "patient_id": alert.patient_id, "patient_name": patient.name if patient else "", "latitude": alert.latitude, "longitude": alert.longitude, "red_flags": alert.red_flags or [], "summary": alert.summary, "status": alert.status, "created_at": alert.created_at.isoformat(), "updated_at": alert.updated_at.isoformat()}


@router.post("")
def create_alert(request: AlertCreate, patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    if not (-90 <= request.latitude <= 90 and -180 <= request.longitude <= 180):
        raise HTTPException(status_code=422, detail="Location coordinates are invalid")
    alert = Alert(patient_id=patient.id, latitude=request.latitude, longitude=request.longitude, red_flags=request.red_flags[:12], summary=request.summary.strip(), status="new")
    session.add(alert)
    session.flush()
    dispatch_ids = list(session.scalars(select(User.id).where(User.role == "dispatch")))
    recipients = [patient.id, *dispatch_ids]
    payload = _data(alert, session)
    session.add_all([Event(user_id=uid, event_type="alert.created", entity_type="alert", entity_id=alert.id, payload=payload) for uid in set(recipients)])
    session.commit()
    session.refresh(alert)
    payload = _data(alert, session)
    manager.publish_from_sync(recipients, {"type": "alert.created", "alert": payload})
    return payload


@router.get("/mine")
def my_alerts(patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    alerts = session.scalars(select(Alert).where(Alert.patient_id == patient.id).order_by(Alert.created_at.desc())).all()
    return [_data(alert, session) for alert in alerts]


@router.get("/incoming")
def incoming_alerts(dispatch: User = Depends(require_role("dispatch")), session: Session = Depends(get_db)):
    alerts = session.scalars(select(Alert).order_by(Alert.created_at.desc())).all()
    return [_data(alert, session) for alert in alerts]


@router.patch("/{alert_id}")
def update_alert(alert_id: int, request: AlertUpdate, dispatch: User = Depends(require_role("dispatch")), session: Session = Depends(get_db)):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    transitions = {"accept": ("new", "accepted"), "en_route": ("accepted", "en_route"), "arrived": ("en_route", "arrived"), "close": (("accepted", "en_route", "arrived"), "closed")}
    expected, new_status = transitions[request.action]
    expected_states = expected if isinstance(expected, tuple) else (expected,)
    if alert.status not in expected_states:
        raise HTTPException(status_code=409, detail="This alert action is not allowed in its current state")
    alert.status = new_status
    alert.updated_at = utc_now()
    payload = _data(alert, session)
    session.add_all([Event(user_id=alert.patient_id, event_type="alert.updated", entity_type="alert", entity_id=alert.id, payload=payload), Event(user_id=dispatch.id, event_type="alert.updated", entity_type="alert", entity_id=alert.id, payload=payload)])
    session.commit()
    session.refresh(alert)
    payload = _data(alert, session)
    manager.publish_from_sync([alert.patient_id, dispatch.id], {"type": "alert.updated", "alert": payload})
    return payload

