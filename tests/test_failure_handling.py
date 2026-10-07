import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Certificate, CertificateStatus, GenerationJob, JobStatus
from app.services.certificate_generator import CertificateGenerator


def test_individual_recipient_failure_isolation(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """
    CRITICAL EVALUATION TEST:
    Verify that when one recipient (Bob) fails during certificate generation,
    preceding (Alice) and succeeding (Charlie) recipients continue processing successfully.

    Expected:
    - Alice: GENERATED
    - Bob: FAILED
    - Charlie: GENERATED
    - Job status: COMPLETED_WITH_ERRORS
    - Job counts: total=3, successful=2, failed=1
    """
    original_generate = CertificateGenerator.generate

    def mock_generate(recipient_name, *args, **kwargs):
        if recipient_name == "Bob":
            raise RuntimeError("Simulated PDF rendering failure for Bob")
        return original_generate(recipient_name, *args, **kwargs)

    monkeypatch.setattr(CertificateGenerator, "generate", mock_generate)

    payload = {
        "title": "Certificate of Excellence",
        "course": "Distributed Systems",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
            {"name": "Charlie", "email": "charlie@example.com"},
        ],
    }

    create_res = client.post("/api/v1/certificates/generate", json=payload)
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    # Verify via Status API
    status_res = client.get(f"/api/v1/certificates/jobs/{job_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()

    assert status_data["job_id"] == job_id
    assert status_data["status"] == "COMPLETED_WITH_ERRORS"
    assert status_data["total"] == 3
    assert status_data["successful"] == 2
    assert status_data["failed"] == 1
    assert status_data["pending"] == 0
    assert status_data["progress_percentage"] == 100.0

    # Verify individual certificate statuses
    certs_by_name = {c["recipient_name"]: c for c in status_data["certificates"]}

    assert "Alice" in certs_by_name
    assert certs_by_name["Alice"]["status"] == "GENERATED"
    assert certs_by_name["Alice"]["download_url"] is not None
    assert certs_by_name["Alice"]["error_message"] is None

    assert "Bob" in certs_by_name
    assert certs_by_name["Bob"]["status"] == "FAILED"
    assert certs_by_name["Bob"]["download_url"] is None
    assert "Simulated PDF rendering failure for Bob" in certs_by_name["Bob"]["error_message"]

    assert "Charlie" in certs_by_name
    assert certs_by_name["Charlie"]["status"] == "GENERATED"
    assert certs_by_name["Charlie"]["download_url"] is not None
    assert certs_by_name["Charlie"]["error_message"] is None

    # Verify directly against database state
    db_job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    assert db_job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert db_job.successful_count == 2
    assert db_job.failed_count == 1
    assert db_job.total_count == 3


def test_all_recipients_failed_job_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Verify that when all recipients fail, the job status is marked FAILED."""
    def fail_all(*args, **kwargs):
        raise RuntimeError("Total storage failure")

    monkeypatch.setattr(CertificateGenerator, "generate", fail_all)

    payload = {
        "title": "Certificate of Completion",
        "course": "Data Engineering",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "User One", "email": "user1@example.com"},
            {"name": "User Two", "email": "user2@example.com"},
        ],
    }

    create_res = client.post("/api/v1/certificates/generate", json=payload)
    job_id = create_res.json()["job_id"]

    status_res = client.get(f"/api/v1/certificates/jobs/{job_id}")
    status_data = status_res.json()

    assert status_data["status"] == "FAILED"
    assert status_data["successful"] == 0
    assert status_data["failed"] == 2
