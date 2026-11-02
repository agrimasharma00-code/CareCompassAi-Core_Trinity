"""Private proxies for optional CNN features and explicitly confirmed intake data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import verify_demo_token
from app.config import settings
from app.core.patient_records import get_patient_record, save_medications, save_skin_check


router = APIRouter(prefix="/api/v1/intake", tags=["patient-intake"])
MAX_UPLOAD = 10 * 1024 * 1024


class MedicationItem(BaseModel):
    brand: str = Field(min_length=1, max_length=160)
    generic: str = Field(default="", max_length=240)
    source: Literal["ai_confirmed", "ai_corrected", "manual"]
    ai_confidence: float | None = Field(default=None, ge=0, le=1)


class MedicationConfirmation(BaseModel):
    medications: list[MedicationItem] = Field(max_length=40)


def patient_subject(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Sign in to the patient portal first.")
    claims = verify_demo_token(token)
    if claims.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Patient sign-in is required for this intake action.")
    return str(claims["sub"])


def optional_patient_subject(authorization: str | None) -> str | None:
    return patient_subject(authorization) if authorization else None


async def _read_image(image: UploadFile) -> bytes:
    data = await image.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Choose an image smaller than 10 MB.")
    if not data:
        raise HTTPException(status_code=400, detail="The selected image is empty.")
    return data


async def _proxy(method: str, path: str, **kwargs) -> tuple[int, dict[str, object]]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, f"{settings.ml_service_url.rstrip('/')}{path}", **kwargs)
            try:
                payload = response.json()
            except ValueError:
                payload = {"status": "ml_unavailable", "message": "The image service returned an unreadable response."}
            return response.status_code, payload if isinstance(payload, dict) else {"status": "error"}
    except (httpx.TimeoutException, httpx.HTTPError):
        return 200, {"status": "ml_unavailable", "message": "Automatic image reading is unavailable right now. You can continue manually."}


@router.get("/record")
def intake_record(authorization: str | None = Header(default=None)) -> dict[str, object]:
    return get_patient_record(patient_subject(authorization))


@router.post("/medications/confirm")
def confirm_medications(payload: "MedicationConfirmation", authorization: str | None = Header(default=None)) -> dict[str, object]:
    subject = patient_subject(authorization)
    confirmed = [item.model_dump() for item in payload.medications]
    return save_medications(subject, confirmed)


@router.post("/skin-check")
async def skin_check(image: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, object]:
    subject = patient_subject(authorization)
    data = await _read_image(image)
    status, result = await _proxy(
        "POST", "/skin/predict",
        files={"image": (image.filename or "skin-image", data, image.content_type or "application/octet-stream")},
    )
    if status >= 400 and result.get("status") not in {"model_missing"}:
        raise HTTPException(status_code=status, detail=str(result.get("message", "The skin image could not be analyzed.")))
    if result.get("status") == "ok":
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        save_skin_check(subject, result)
    return result


@router.post("/prescription/segment")
async def prescription_segment(image: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, object]:
    patient_subject(authorization)
    data = await _read_image(image)
    status, result = await _proxy(
        "POST", "/rx/segment",
        files={"image": (image.filename or "prescription-image", data, image.content_type or "application/octet-stream")},
    )
    if status >= 400 and result.get("status") not in {"model_missing"}:
        raise HTTPException(status_code=status, detail=str(result.get("message", "The image could not be segmented.")))
    return result


@router.post("/prescription/predict")
async def prescription_predict(
    image: UploadFile | None = File(default=None),
    crops: list[UploadFile] | None = File(default=None),
    boxes: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    patient_subject(authorization)
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    if image is not None:
        raw = await _read_image(image)
        files.append(("image", (image.filename or "prescription-image", raw, image.content_type or "application/octet-stream")))
    for crop in (crops or []):
        raw = await _read_image(crop)
        files.append(("crops", (crop.filename or "medicine-word.png", raw, crop.content_type or "application/octet-stream")))
    if not files:
        raise HTTPException(status_code=400, detail="Upload a prescription image or at least one cropped medicine name.")
    data = {"boxes": boxes} if boxes else None
    status, result = await _proxy("POST", "/rx/predict", files=files, data=data)
    if status >= 400 and result.get("status") not in {"model_missing"}:
        raise HTTPException(status_code=status, detail=str(result.get("message", "The prescription could not be read.")))
    return result
