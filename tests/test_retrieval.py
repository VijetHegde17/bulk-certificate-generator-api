import io
import zipfile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Certificate, CertificateStatus, GenerationJob, JobStatus


def test_retrieve_generated_certificate_success(client: TestClient):
    """Test downloading a successfully generated certificate PDF."""
    payload = {
        "title": "Certificate of Completion",
        "course": "Python Backend",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Manoj Kumar", "email": "manoj@example.com"},
        ],
    }

    create_res = client.post("/api/v1/certificates/generate", json=payload)
    job_id = create_res.json()["job_id"]

    # Check status and get certificate_id
    status_res = client.get(f"/api/v1/certificates/jobs/{job_id}")
    cert_id = status_res.json()["certificates"][0]["certificate_id"]

    # Retrieve certificate file
    download_res = client.get(f"/api/v1/certificates/{cert_id}")
    assert download_res.status_code == 200
    assert download_res.headers["content-type"] == "application/pdf"
    assert "Manoj_Kumar.pdf" in download_res.headers["content-disposition"]
    assert download_res.content.startswith(b"%PDF-")


def test_retrieve_nonexistent_certificate_returns_404(client: TestClient):
    """Test retrieving a non-existent certificate returns 404."""
    response = client.get("/api/v1/certificates/999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_retrieve_pending_certificate_returns_400(client: TestClient, db_session: Session):
    """Test retrieving a pending certificate returns 400."""
    job = GenerationJob(
        title="Pending Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=JobStatus.PENDING,
        total_count=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Pending User",
        recipient_email="pending@example.com",
        certificate_title="Pending Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=CertificateStatus.PENDING,
    )
    db_session.add(cert)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{cert.id}")
    assert response.status_code == 400
    assert "pending" in response.json()["detail"].lower()


def test_retrieve_failed_certificate_returns_400(client: TestClient, db_session: Session):
    """Test retrieving a failed certificate returns 400 with error details."""
    job = GenerationJob(
        title="Failed Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=JobStatus.COMPLETED_WITH_ERRORS,
        total_count=1,
        failed_count=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Failed User",
        recipient_email="failed@example.com",
        certificate_title="Failed Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=CertificateStatus.FAILED,
        error_message="Font rendering failed",
    )
    db_session.add(cert)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{cert.id}")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()
    assert "Font rendering failed" in response.json()["detail"]


def test_retrieve_missing_file_on_disk_returns_404(client: TestClient, db_session: Session):
    """Test retrieving a certificate when file is deleted from disk returns 404."""
    job = GenerationJob(
        title="Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=JobStatus.COMPLETED,
        total_count=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Ghost User",
        recipient_email="ghost@example.com",
        certificate_title="Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=CertificateStatus.GENERATED,
        file_path=str(settings.certificates_dir_path / "non_existent_file.pdf"),
    )
    db_session.add(cert)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{cert.id}")
    assert response.status_code == 404
    assert "not exist on disk" in response.json()["detail"].lower()


def test_retrieve_path_traversal_attempt_returns_400(client: TestClient, db_session: Session):
    """Test that a forged file path attempting directory traversal is safely rejected with 400."""
    job = GenerationJob(
        title="Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=JobStatus.COMPLETED,
        total_count=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Hacker User",
        recipient_email="hacker@example.com",
        certificate_title="Job",
        course="Course",
        organization="Org",
        event_date="2026-10-07",
        status=CertificateStatus.GENERATED,
        file_path="/etc/passwd",
    )
    db_session.add(cert)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{cert.id}")
    assert response.status_code == 400
    assert "location" in response.json()["detail"].lower()


def test_download_job_certificates_zip_archive(client: TestClient):
    """Test downloading the batch ZIP archive of all generated certificates for a job."""
    payload = {
        "title": "Certificate of Completion",
        "course": "Python Backend",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Dev One", "email": "dev1@example.com"},
            {"name": "Dev Two", "email": "dev2@example.com"},
        ],
    }

    create_res = client.post("/api/v1/certificates/generate", json=payload)
    job_id = create_res.json()["job_id"]

    zip_res = client.get(f"/api/v1/certificates/jobs/{job_id}/zip")
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"

    # Verify that the zip content can be opened and has two valid PDF files
    with zipfile.ZipFile(io.BytesIO(zip_res.content), "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert all(name.endswith(".pdf") for name in namelist)
