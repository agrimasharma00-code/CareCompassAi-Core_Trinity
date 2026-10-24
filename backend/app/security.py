import base64
import hashlib
import hmac
import json
import time
from datetime import datetime

from app.config import get_settings
from app.db.models import User


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_access_token(user: User, expires_at: datetime) -> str:
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ValueError("JWT_SECRET must contain at least 32 characters")
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {"sub": str(user.id), "username": user.username, "role": user.role, "exp": int(expires_at.timestamp())}
    if user.role == "provider":
        claims["caregiver_id"] = user.caregiver_id
    body = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(claims, separators=(',', ':')).encode())}"
    signature = hmac.new(settings.jwt_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64url(signature)}"


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        if len(settings.jwt_secret) < 32:
            return None
        header_part, payload_part, signature_part = token.split(".")
        body = f"{header_part}.{payload_part}"
        expected = _b64url(hmac.new(settings.jwt_secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature_part):
            return None
        padded = payload_part + "=" * (-len(payload_part) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        if claims.get("exp", 0) <= int(time.time()) or not claims.get("sub") or claims.get("role") not in {"patient", "dispatch", "provider"}:
            return None
        return claims
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
