from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.db.database as db_module
import app.services.job_processor as job_proc_module
from app.core.config import settings
from app.db.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Ensure each test runs with an isolated temporary directory for certificates
    and an isolated SQLite database file.
    """
    # 1. Isolated temporary directory for generated PDFs
    temp_cert_dir = tmp_path / "generated_certificates"
    temp_cert_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "GENERATED_CERTIFICATES_DIR", str(temp_cert_dir))

    # 2. Isolated test SQLite database
    test_db_path = tmp_path / "test_certificates.db"
    test_db_url = f"sqlite:///{test_db_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", test_db_url)

    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    # Create tables in test database
    Base.metadata.create_all(bind=test_engine)

    # Point application and background worker session factories to test database
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(job_proc_module, "SessionLocal", TestingSessionLocal)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield

    # Teardown
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with automatic lifespan handling."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Direct database session fixture for inspecting test database state."""
    db = db_module.SessionLocal()
    try:
        yield db
    finally:
        db.close()
