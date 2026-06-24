"""test_health.py — Health endpoint integration tests.

Verifies that the /api/health endpoint returns correct status,
proper structure, and honest health reporting per agent.md.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    import os
    os.environ.setdefault("FIREAI_ENV", "development")
    os.environ.setdefault("FIREAI_API_KEY", "")

    from backend.app import app
    with TestClient(app) as c:
        yield c


def _health_data(client):
    """Helper to get the data payload from a health response."""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    if "data" in body:
        return body["data"]
    return body


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self, client):
        """Health endpoint must return HTTP 200."""
        response = client.get("/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_health_has_status_field(self, client):
        """Health response must include a 'status' field."""
        data = _health_data(client)
        assert "status" in data, "Missing 'status' field in health response"

    def test_health_status_is_ok_or_degraded(self, client):
        """Status must be 'ok' or 'degraded' — never 'error' or missing."""
        data = _health_data(client)
        assert data["status"] in ("ok", "degraded"), f"Unexpected status: {data['status']}"

    def test_health_has_version(self, client):
        """Health response must include a 'version' field."""
        data = _health_data(client)
        assert "version" in data, "Missing 'version' field"

    def test_health_has_uptime(self, client):
        """Health response must include uptime information."""
        data = _health_data(client)
        assert "uptime" in data or "uptime_seconds" in data, "Missing uptime field"

    def test_health_has_database_status(self, client):
        """Health response must report database connectivity."""
        data = _health_data(client)
        assert "database" in data, "Missing 'database' field"

    def test_health_has_timestamp(self, client):
        """Health response must include a timestamp."""
        data = _health_data(client)
        assert "timestamp" in data, "Missing 'timestamp' field"

    def test_security_headers_present(self, client):
        """Security headers must be present on health response."""
        response = client.get("/api/health")
        assert "x-frame-options" in response.headers, "Missing X-Frame-Options header"
        assert "x-content-type-options" in response.headers, "Missing X-Content-Type-Options header"
        assert "content-security-policy" in response.headers, "Missing CSP header"
        assert "strict-transport-security" in response.headers, "Missing HSTS header"


class TestStatisticsEndpoint:
    """Tests for GET /api/reports/statistics."""

    def test_statistics_returns_200(self, client):
        """Statistics endpoint must return HTTP 200."""
        response = client.get("/api/reports/statistics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_statistics_has_counts(self, client):
        """Statistics response must include element and project counts."""
        response = client.get("/api/reports/statistics")
        data = response.json()
        if "data" in data:
            data = data["data"]
        assert "total_elements" in data, "Missing total_elements"
        assert "total_projects" in data, "Missing total_projects"
