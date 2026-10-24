"""Demo-only HMAC JWT login for the three judge-facing roles."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.loaders import load_caregivers


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SECRET = b"niramaya-demo-only-not-for-production"
ROLES = {"patient", "hospital", "ambulance"}


class DemoLogin(BaseModel):
    role: str
    identifier: str


def provider_accounts() -> list[dict[str, object]]:
    """Expose dataset-backed demo provider identities to the role switcher."""
    return [
        {
            "caregiver_id": profile["id"],
            "role": profile["role"],
            "languages": profile["languages"],
            "skills": profile["skills"],
        }
        for profile in load_caregivers()
    ]


def _part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def issue_token(role: str, identifier: str) -> str:
    header = _part(b'{"alg":"HS256","typ":"JWT"}')
    payload = _part(json.dumps({"sub": identifier, "role": role, "exp": int((datetime.now(UTC) + timedelta(hours=8)).timestamp())}).encode())
    signature = _part(hmac.new(SECRET, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


@router.post("/demo-login")
def demo_login(payload: DemoLogin) -> dict[str, str]:
    if payload.role not in ROLES or not payload.identifier.strip():
        raise HTTPException(status_code=400, detail="Choose a valid demo role and identifier.")
    identifier = payload.identifier.strip()
    caregiver_ids = {str(account["caregiver_id"]) for account in provider_accounts()}
    if payload.role == "hospital" and identifier not in caregiver_ids:
        raise HTTPException(status_code=400, detail="Choose a provider profile from the supplied caregiver dataset.")
    return {"access_token": issue_token(payload.role, identifier), "token_type": "bearer", "role": payload.role, "caregiver_id": identifier if payload.role == "hospital" else ""}


@router.get("/provider-accounts")
def get_provider_accounts() -> list[dict[str, object]]:
    return provider_accounts()
