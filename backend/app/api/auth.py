"""Demo-only HMAC JWT login for the three judge-facing roles."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SECRET = b"carecompass-demo-only-not-for-production"
ROLES = {"patient", "hospital", "ambulance"}


class DemoLogin(BaseModel):
    role: str
    identifier: str


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
    return {"access_token": issue_token(payload.role, payload.identifier.strip()), "token_type": "bearer", "role": payload.role}
