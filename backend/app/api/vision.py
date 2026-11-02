from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_role
from app.config import get_settings
from app.db.database import get_db
from app.db.models import Conversation, User, utc_now

router = APIRouter(prefix="/api/intake/{patient_id}", tags=["vision"])


def _owned_patient(patient_id: int, patient: User):
    if patient.id != patient_id:
        raise HTTPException(status_code=403, detail="You can only update your own intake.")


def _conversation(patient: User, session: Session):
    row = session.scalar(select(Conversation).where(Conversation.user_id == patient.id))
    if row is None:
        row = Conversation(user_id=patient.id, messages=[], confirmed_medications=[])
        session.add(row)
        session.flush()
    return row


async def _proxy(path: str, image: UploadFile):
    data = await image.read(10 * 1024 * 1024 + 1)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{get_settings().ml_service_url.rstrip('/')}{path}", files={"image": (image.filename or "upload.jpg", data, image.content_type or "application/octet-stream")})
    except httpx.HTTPError:
        return {"status": "ml_unavailable", "message": "Vision service is unavailable. You can continue intake and enter information manually."}
    if response.status_code >= 500 and response.status_code != 503:
        return {"status": "ml_unavailable", "message": "Vision service is unavailable. You can continue intake and enter information manually."}
    try:
        payload = response.json()
    except ValueError:
        return {"status": "ml_unavailable", "message": "Vision service returned an unreadable response. You can continue intake manually."}
    if response.status_code == 503 and isinstance(payload, dict):
        return {**(payload.get("detail") if isinstance(payload.get("detail"), dict) else payload), "status": "model_missing"}
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=payload.get("detail", "Image could not be processed.") if isinstance(payload, dict) else "Image could not be processed.")
    return payload


@router.post("/vision/skin-check")
async def skin_check(patient_id: int, image: UploadFile = File(...), patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    _owned_patient(patient_id, patient)
    result = await _proxy("/derma/predict", image)
    if result.get("status") == "ok":
        row = _conversation(patient, session)
        row.skin_check = {"top_prediction": result.get("top_prediction"), "top3": result.get("top3", []), "risk_level": result.get("risk_level"), "triage_effect": result.get("triage_effect"), "model_version": result.get("model_version"), "condition_card": result.get("condition_card"), "timestamp": datetime.now(timezone.utc).isoformat()}
        row.updated_at = utc_now(); session.commit()
    return result


@router.post("/vision/prescription/segment")
async def prescription_segment(patient_id: int, image: UploadFile = File(...), patient: User = Depends(require_role("patient"))):
    _owned_patient(patient_id, patient)
    return await _proxy("/rx/segment", image)


@router.post("/vision/prescription/predict")
async def prescription_predict(patient_id: int, image: UploadFile = File(...), boxes: str = Form("[]"), patient: User = Depends(require_role("patient"))):
    _owned_patient(patient_id, patient)
    data = await image.read(10 * 1024 * 1024 + 1)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{get_settings().ml_service_url.rstrip('/')}/rx/predict", files={"image": (image.filename or "upload.jpg", data, image.content_type or "application/octet-stream")}, data={"boxes": boxes})
    except httpx.HTTPError:
        return {"status": "ml_unavailable", "message": "Vision service is unavailable. Continue with manual entry."}
    if response.status_code == 503:
        detail = response.json().get("detail", {})
        return {**(detail if isinstance(detail, dict) else {}), "status": "model_missing"}
    if response.status_code >= 400:
        raise HTTPException(response.status_code, response.json().get("detail", "Prescription image could not be processed."))
    return response.json()


class ConfirmedMedication(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    composition: str | None = Field(default=None, max_length=300)
    source: Literal["ai_confirmed", "ai_corrected", "manual"]
    ai_confidence: float | None = Field(default=None, ge=0, le=1)


class MedicationConfirmation(BaseModel):
    medications: list[ConfirmedMedication] = Field(max_length=100)


@router.post("/medications/confirm")
def confirm_medications(patient_id: int, request: MedicationConfirmation, patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    _owned_patient(patient_id, patient)
    row = _conversation(patient, session)
    row.confirmed_medications = [item.model_dump() for item in request.medications]
    row.updated_at = utc_now(); session.commit()
    return {"status": "saved", "confirmed_medications": row.confirmed_medications, "source_badges": [item["source"] for item in row.confirmed_medications]}


@router.get("/vision/summary")
def vision_summary(patient_id: int, patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    _owned_patient(patient_id, patient)
    row = session.scalar(select(Conversation).where(Conversation.user_id == patient.id))
    return {"skin_check": row.skin_check if row else None, "confirmed_medications": row.confirmed_medications if row else []}
