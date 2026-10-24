import csv
import hashlib
import secrets
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base, User


ROOT = Path(__file__).resolve().parents[2]
CAREGIVERS_CSV = ROOT / "data" / "raw" / "caregivers.csv"
_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Hash a demo password with salted PBKDF2 using only the Python standard library."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def seed_demo_accounts(session: Session, password: str, caregivers_csv: Path = CAREGIVERS_CSV) -> int:
    """Idempotently create or refresh the labelled synthetic demo accounts."""
    if not password:
        raise ValueError("DEMO_PASSWORD must be set before seeding demo accounts")

    password_hash = hash_password(password)
    accounts: list[tuple[str, str, str, str | None]] = [
        ("patient1", "Demo Patient One", "patient", None),
        ("patient2", "Demo Patient Two", "patient", None),
        ("dispatch", "Demo Dispatch Desk", "dispatch", None),
    ]
    with caregivers_csv.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("active", "").strip().lower() == "true":
                caregiver_id = row["caregiver_id"].strip()
                accounts.append((caregiver_id, row["name"].strip(), "provider", caregiver_id))

    for username, name, role, caregiver_id in accounts:
        user = session.query(User).filter_by(username=username).one_or_none()
        if user is None:
            user = User(username=username, name=name, role=role, caregiver_id=caregiver_id, password_hash=password_hash)
            session.add(user)
        else:
            user.name = name
            user.role = role
            user.caregiver_id = caregiver_id
            user.password_hash = password_hash
    session.commit()
    return len(accounts)


def initialize_database(*, target_engine: Engine = engine, demo_password: str | None = None) -> int:
    """Create all tables and seed demo accounts when a password is configured."""
    Base.metadata.create_all(target_engine)
    password = get_settings().demo_password if demo_password is None else demo_password
    if not password:
        return 0
    factory = sessionmaker(bind=target_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        return seed_demo_accounts(session, password)
