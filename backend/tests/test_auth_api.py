from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth
from app.db.database import hash_password
from app.db.models import Base, User
from app.security import create_access_token, decode_access_token
import app.security as security


def test_login_token_identity_and_server_side_role_checks(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory() as session:
        patient = User(username="patient1", name="Demo Patient", role="patient", password_hash=hash_password("demo-pass"))
        provider = User(username="CG_001", name="Demo Provider", role="provider", caregiver_id="CG_001", password_hash=hash_password("demo-pass"))
        session.add_all([patient, provider])
        session.commit()
        provider_id = provider.id

    settings = SimpleNamespace(jwt_secret="x" * 48, jwt_exp_minutes=10)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    with factory() as session:
        result = auth.login(auth.LoginRequest(username="patient1", password="demo-pass"), session)
        claims = decode_access_token(result["access_token"])
        assert claims["role"] == "patient"
        current = auth.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=result["access_token"]), session)
        assert auth.me(current)["username"] == "patient1"
        assert auth.require_role("patient")(current) is current
        with pytest.raises(HTTPException) as forbidden:
            auth.require_role("patient")(session.get(User, provider_id))
        assert forbidden.value.status_code == 403
        with pytest.raises(HTTPException) as bad_password:
            auth.login(auth.LoginRequest(username="patient1", password="wrong"), session)
        assert bad_password.value.status_code == 401
    test_engine.dispose()


def test_provider_token_includes_caregiver_id_and_expires(monkeypatch):
    settings = SimpleNamespace(jwt_secret="x" * 48, jwt_exp_minutes=10)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    provider = User(id=8, username="CG_001", name="Provider", role="provider", caregiver_id="CG_001", password_hash="unused")
    token = create_access_token(provider, datetime.now(timezone.utc) + timedelta(minutes=5))
    assert decode_access_token(token)["caregiver_id"] == "CG_001"
    expired = create_access_token(provider, datetime.now(timezone.utc) - timedelta(minutes=1))
    assert decode_access_token(expired) is None


def test_login_requires_strong_jwt_secret(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(jwt_secret="short", jwt_exp_minutes=10))
    with pytest.raises(HTTPException) as error:
        auth.login(auth.LoginRequest(username="x", password="x"), object())
    assert error.value.status_code == 503
