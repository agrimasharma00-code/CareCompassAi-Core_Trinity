from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import initialize_database, seed_demo_accounts
from app.db.models import Base, User


def test_seed_creates_demo_users_and_active_provider_accounts():
    with TemporaryDirectory(dir=Path(__file__).parent) as folder:
        tmp_path = Path(folder)
        caregivers = tmp_path / "caregivers.csv"
        caregivers.write_text(
            "caregiver_id,name,active\nCG_001,Active Provider,True\nCG_002,Inactive Provider,False\n",
            encoding="utf-8",
        )
        engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            created = seed_demo_accounts(session, "test-password", caregivers)
            users = session.scalars(select(User).order_by(User.username)).all()
            assert created == 4
            assert [(user.username, user.role, user.caregiver_id) for user in users] == [
                ("CG_001", "provider", "CG_001"),
                ("dispatch", "dispatch", None),
                ("patient1", "patient", None),
                ("patient2", "patient", None),
            ]
            assert all(user.password_hash != "test-password" for user in users)
            assert all(user.password_hash.startswith("pbkdf2_sha256$310000$") for user in users)

            seed_demo_accounts(session, "test-password", caregivers)
            assert session.scalar(select(func.count()).select_from(User)) == 4
        engine.dispose()


def test_initialize_database_creates_all_required_tables():
    with TemporaryDirectory(dir=Path(__file__).parent) as folder:
        engine = create_engine(f"sqlite:///{Path(folder) / 'schema.db'}")
        assert initialize_database(target_engine=engine, demo_password="") == 0
        assert set(Base.metadata.tables) == {"users", "bookings", "alerts", "checkins", "events"}
        engine.dispose()
