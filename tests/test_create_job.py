from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Certificate, GenerationJob, JobStatus


def test_create_generation_job_success(client: TestClient, db_session: Session):
    """Test successful creation and execution of a bulk certificate generation job."""
    payload = {
        "title": "Certificate of Excellence",
        "course": "Advanced Python & FastAPI",
        "organization": "Aereo Tech",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Rahul Kumar", "email": "rahul@example.com"},
            {"name": "Priya Sharma", "email": "priya@example.com"},
        ],
    }

    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 202

    data = response.json()
    assert "job_id" in data
    assert data["total_count"] == 2
    assert "Certificate generation job accepted" in data["message"]

    job_id = data["job_id"]
    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    assert job is not None
    assert job.title == "Certificate of Excellence"
    assert job.course == "Advanced Python & FastAPI"
    assert job.total_count == 2
    assert job.status in [JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED]

    # Verify recipient records in database
    certs = db_session.query(Certificate).filter(Certificate.job_id == job_id).all()
    assert len(certs) == 2
    names = [c.recipient_name for c in certs]
    assert "Rahul Kumar" in names
    assert "Priya Sharma" in names


def test_create_generation_job_single_recipient(client: TestClient, db_session: Session):
    """Verify job creation works properly with a single recipient."""
    payload = {
        "title": "Certificate of Participation",
        "course": "Cloud Foundations",
        "organization": "Aereo Academy",
        "event_date": "2026-10-01",
        "recipients": [
            {"name": "Ananya Roy", "email": "ananya@example.com"},
        ],
    }

    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["total_count"] == 1
    assert data["job_id"] is not None
