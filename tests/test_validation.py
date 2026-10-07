from fastapi.testclient import TestClient


def test_validation_empty_recipients_list(client: TestClient):
    """Test that submitting an empty recipients list is rejected with 422."""
    payload = {
        "title": "Certificate of Completion",
        "course": "Python Backend",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [],
    }
    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("recipients" in str(err["loc"]) for err in errors)


def test_validation_missing_required_fields(client: TestClient):
    """Test that missing required fields trigger 422 validation error."""
    payload = {
        # Missing course, organization, event_date
        "recipients": [{"name": "Rahul Kumar", "email": "rahul@example.com"}],
    }
    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 422


def test_validation_invalid_recipient_email(client: TestClient):
    """Test that an invalid recipient email address is rejected with 422."""
    payload = {
        "title": "Certificate of Completion",
        "course": "Python Backend",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Invalid User", "email": "not-a-valid-email-format"},
        ],
    }
    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 422
    assert any("email" in str(err) for err in response.json()["detail"])


def test_validation_blank_recipient_name(client: TestClient):
    """Test that whitespace-only recipient names are rejected with 422."""
    payload = {
        "title": "Certificate of Completion",
        "course": "Python Backend",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "   ", "email": "blankname@example.com"},
        ],
    }
    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 422
    assert any("name" in str(err) for err in response.json()["detail"])


def test_validation_invalid_date_format(client: TestClient):
    """Test that improperly formatted dates (e.g. DD-MM-YYYY) are rejected."""
    payload = {
        "title": "Certificate of Completion",
        "course": "Python Backend",
        "organization": "Aereo",
        "event_date": "07-10-2026",  # Expected YYYY-MM-DD
        "recipients": [
            {"name": "Test User", "email": "test@example.com"},
        ],
    }
    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 422
    assert any("event_date" in str(err) for err in response.json()["detail"])


def test_validation_whitespace_only_course(client: TestClient):
    """Test that whitespace-only course strings are rejected with 422."""
    payload = {
        "title": "Certificate",
        "course": "   ",
        "organization": "Aereo",
        "event_date": "2026-10-07",
        "recipients": [
            {"name": "Test User", "email": "test@example.com"},
        ],
    }
    response = client.post("/api/v1/certificates/generate", json=payload)
    assert response.status_code == 422
