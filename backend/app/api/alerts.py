"""Emergency demo-dispatch feed. It supplements, never replaces, 112."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.ws import hub
from app.core.live import list_alerts, update_alert


router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertStatus(BaseModel):
    status: str


@router.get("")
def get_alerts() -> list[dict[str, object]]:
    return list_alerts()


@router.post("/{alert_id}/status")
async def change_alert_status(alert_id: str, payload: AlertStatus) -> dict[str, object]:
    if payload.status not in {"accepted", "en_route", "arrived", "closed"}:
        raise HTTPException(status_code=400, detail="Unsupported alert status.")
    alert = update_alert(alert_id, payload.status)
    if not alert: raise HTTPException(status_code=404, detail="Alert not found.")
    await hub.publish("dispatch", {"type": "alert.updated", "alert": alert})
    return alert
