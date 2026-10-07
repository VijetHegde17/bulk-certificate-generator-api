from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """Test that GET /health returns 200 with status healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_openapi_documentation_accessible(client: TestClient):
    """Test that OpenAPI JSON schema and /docs are accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "/api/v1/certificates/generate" in data["paths"]
    assert "/api/v1/certificates/jobs/{job_id}" in data["paths"]
    assert "/api/v1/certificates/{certificate_id}" in data["paths"]
