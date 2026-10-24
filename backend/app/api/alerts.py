"""Emergency demo-dispatch feed. It supplements, never replaces Call 5555."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.ws import hub
from app.core.live import create_alert, list_alerts, update_alert


router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertStatus(BaseModel):
    status: str


class EmergencyCall(BaseModel):
    patient_name: str = "Demo patient"
    summary: str = "Emergency help requested from CareCompass"
    red_flags: list[str] = []
    latitude: float = 28.545
    longitude: float = 77.192


@router.get("")
def get_alerts() -> list[dict[str, object]]:
    return list_alerts()


@router.post("/emergency")
async def emergency_call(payload: EmergencyCall) -> dict[str, object]:
    """Record the demo family + ambulance notification beside the tel:5555 action."""
    family_notification = "Demo notification: family contact and ambulance partner were alerted."
    alert = create_alert({
        "patient_name": payload.patient_name,
        "summary": f"{payload.summary}. {family_notification}",
        "red_flags": payload.red_flags,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    })
    await hub.publish("dispatch", {"type": "alert.created", "alert": alert, "family_notification": family_notification})
    return {"alert": alert, "family_notification": family_notification}


@router.post("/{alert_id}/status")
async def change_alert_status(alert_id: str, payload: AlertStatus) -> dict[str, object]:
    if payload.status not in {"accepted", "en_route", "arrived", "closed"}:
        raise HTTPException(status_code=400, detail="Unsupported alert status.")
    alert = update_alert(alert_id, payload.status)
    if not alert: raise HTTPException(status_code=404, detail="Alert not found.")
    await hub.publish("dispatch", {"type": "alert.updated", "alert": alert})
    return alert
