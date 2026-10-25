"""Confirmed demo bookings and re-triage workflow kept outside the scored endpoint."""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.care import pipeline
from app.api.ws import hub
from app.core.live import create_alert, create_booking, list_bookings, update_booking
from app.services.sms import current_booking_sms_recipient, send_booking_sms
from app.schemas.care import CareRequest, CareResponse, Location


router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])


class BookingCreate(BaseModel):
    caregiver_id: str
    patient_name: str = "Demo patient"
    care_type: str
    urgency: str
    summary: str = Field(max_length=1000)


class StatusChange(BaseModel):
    status: str


class ReTriage(BaseModel):
    booking_id: str
    update: str = Field(min_length=1, max_length=2000)
    lat: float = 28.545
    lng: float = 77.192


@router.get("")
def get_bookings() -> list[dict[str, object]]:
    return list_bookings()


@router.post("")
async def book(payload: BookingCreate) -> dict[str, object]:
    booking = create_booking(payload.model_dump())
    if recipient := current_booking_sms_recipient():
        asyncio.create_task(asyncio.to_thread(send_booking_sms, recipient, booking))
    await hub.publish("provider", {"type": "booking.created", "booking": booking})
    await hub.publish(f"patient:{booking['id']}", {"type": "booking.created", "booking": booking})
    return booking


@router.post("/{booking_id}/status")
async def change_status(booking_id: str, payload: StatusChange) -> dict[str, object]:
    if payload.status not in {"accepted", "rejected", "rescheduled", "completed", "pending"}:
        raise HTTPException(status_code=400, detail="Unsupported booking status.")
    booking = update_booking(booking_id, payload.status)
    if not booking: raise HTTPException(status_code=404, detail="Booking not found.")
    await hub.publish("provider", {"type": "booking.updated", "booking": booking})
    await hub.publish(f"patient:{booking_id}", {"type": "booking.updated", "booking": booking})
    return booking


@router.post("/retriage")
async def retriage(payload: ReTriage) -> dict[str, object]:
    response: CareResponse = pipeline.run(CareRequest(user_input=payload.update, location=Location(lat=payload.lat, lng=payload.lng)), force_final=True)
    alert = None
    if response.care_type and response.care_type.value == "emergency_referral":
        alert = create_alert({"patient_name": "Demo patient", "summary": response.handoff_summary, "red_flags": response.red_flags, "latitude": payload.lat, "longitude": payload.lng})
        await hub.publish("dispatch", {"type": "alert.created", "alert": alert})
    await hub.publish(f"patient:{payload.booking_id}", {"type": "retriage.completed", "response": response.model_dump(mode="json"), "alert": alert})
    return {"response": response, "alert": alert}
