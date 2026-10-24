from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine

from app.db.database import initialize_database


def test_sqlite_database_parent_directory_is_created():
    with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
        database_file = Path(directory) / "nested" / "store" / "carecompass.db"
        engine = create_engine(f"sqlite:///{database_file}")
        try:
            assert not database_file.parent.exists()
            initialize_database(target_engine=engine, demo_password="")
            assert database_file.exists()
        finally:
            engine.dispose()
