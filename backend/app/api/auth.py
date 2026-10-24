from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db, verify_password
from app.db.models import User
from app.security import create_access_token, decode_access_token
from app.core.loaders import load_caregivers

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


def public_user(user: User) -> dict:
    return {"id": user.id, "username": user.username, "name": user.name, "role": user.role, "caregiver_id": user.caregiver_id}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login", headers={"WWW-Authenticate": "Bearer"})
    user = session.get(User, int(claims["sub"]))
    if user is None or user.role != claims.get("role") or user.caregiver_id != claims.get("caregiver_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login is no longer valid", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_role(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account cannot access this resource")
        return user
    return dependency


@router.post("/login")
def login(request: LoginRequest, session: Session = Depends(get_db)):
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise HTTPException(status_code=503, detail="Authentication is not configured. Set a JWT_SECRET of at least 32 characters in backend/.env.")
    user = session.scalar(select(User).where(User.username == request.username))
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_exp_minutes)
    token = create_access_token(user, expires_at)
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at.isoformat(), "user": public_user(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return public_user(user)


@router.get("/providers")
def demo_providers():
    return [{"caregiver_id": item["caregiver_id"], "name": item["name"], "role": item["role"], "area": item["base_area"]} for item in load_caregivers() if item.get("active", "").strip().lower() == "true"]
