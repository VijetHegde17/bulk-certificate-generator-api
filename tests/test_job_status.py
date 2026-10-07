from fastapi.testclient import TestClient


def test_get_job_status_success(client: TestClient):
    """Test retrieving status and progress for an existing generation job."""
    payload = {
        "title": "Certificate of Excellence",
        "course": "Backend Engineering",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Siddharth Sen", "email": "siddharth@example.com"},
            {"name": "Sneha Patil", "email": "sneha@example.com"},
        ],
    }

    create_res = client.post("/api/v1/certificates/generate", json=payload)
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    # Query status
    status_res = client.get(f"/api/v1/certificates/jobs/{job_id}")
    assert status_res.status_code == 200

    data = status_res.json()
    assert data["job_id"] == job_id
    assert data["total"] == 2
    assert data["successful"] == 2
    assert data["failed"] == 0
    assert data["pending"] == 0
    assert data["progress_percentage"] == 100.0
    assert data["status"] == "COMPLETED"

    # Verify certificate items
    assert len(data["certificates"]) == 2
    for cert in data["certificates"]:
        assert cert["status"] == "GENERATED"
        assert cert["download_url"] == f"/api/v1/certificates/{cert['certificate_id']}"
        assert cert["error_message"] is None


def test_get_job_status_not_found(client: TestClient):
    """Test that requesting status for an unknown job returns 404."""
    response = client.get("/api/v1/certificates/jobs/99999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_job_status_pagination(client: TestClient):
    """Test pagination with limit and offset query parameters."""
    payload = {
        "title": "Certificate",
        "course": "DevOps",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": f"User {i}", "email": f"user{i}@example.com"}
            for i in range(1, 6)
        ],
    }
    create_res = client.post("/api/v1/certificates/generate", json=payload)
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    # Query with limit=2, offset=0
    res_page1 = client.get(f"/api/v1/certificates/jobs/{job_id}?limit=2&offset=0")
    assert res_page1.status_code == 200
    data1 = res_page1.json()
    assert len(data1["certificates"]) == 2
    assert data1["certificates"][0]["recipient_name"] == "User 1"
    assert data1["certificates"][1]["recipient_name"] == "User 2"

    # Query with limit=2, offset=2
    res_page2 = client.get(f"/api/v1/certificates/jobs/{job_id}?limit=2&offset=2")
    assert res_page2.status_code == 200
    data2 = res_page2.json()
    assert len(data2["certificates"]) == 2
    assert data2["certificates"][0]["recipient_name"] == "User 3"
    assert data2["certificates"][1]["recipient_name"] == "User 4"
