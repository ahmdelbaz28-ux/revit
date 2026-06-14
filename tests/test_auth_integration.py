"""Integration tests for authentication, RBAC, and API versioning."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """Create a test client with a known API key."""
    monkeypatch.setenv("FIREAI_API_KEY", "test-admin-key")
    monkeypatch.setenv("FIREAI_ENV", "development")
    from backend.app import app
    return TestClient(app)


def test_health_no_auth_required(client):
    """Health endpoint should work without auth."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    # Check that api_version is present
    assert data.get("data", {}).get("api_version") == "v1" or data.get("api_version") == "v1"


def test_projects_requires_auth(client):
    """Projects endpoint should require API key."""
    r = client.get("/api/v1/projects")
    assert r.status_code == 401


def test_projects_with_admin_key(client):
    """Admin key should have full access."""
    r = client.get("/api/v1/projects", headers={"X-API-Key": "test-admin-key"})
    assert r.status_code == 200


def test_legacy_api_deprecated(client):
    """Legacy /api/ path should add deprecation warning."""
    r = client.get("/api/projects", headers={"X-API-Key": "test-admin-key"})
    # The request should succeed (backward compat)
    assert r.status_code == 200
    # And should include deprecation headers
    deprecation_header = r.headers.get("deprecation", "")
    warning_header = r.headers.get("warning", "")
    assert deprecation_header == "true" or "deprecation" in str(r.headers).lower()
    assert "deprecated" in warning_header.lower() or "deprecated" in str(r.headers).lower()


def test_legacy_health_deprecated(client):
    """Legacy /api/health should still work but with deprecation headers."""
    r = client.get("/api/health")
    assert r.status_code == 200
    # Should have deprecation headers
    deprecation_header = r.headers.get("deprecation", "")
    assert deprecation_header == "true"


def test_v1_health_no_deprecation(client):
    """V1 health endpoint should NOT have deprecation headers."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    deprecation_header = r.headers.get("deprecation", "")
    assert deprecation_header != "true"


def test_oversized_request_rejected(client):
    """Request body size limit should be enforced."""
    big = {"name": "x" * 11_000_000, "description": "test", "author": "test"}
    r = client.post(
        "/api/v1/projects",
        json=big,
        headers={"X-API-Key": "test-admin-key"},
    )
    assert r.status_code == 413


def test_invalid_api_key_rejected(client):
    """Wrong API key should be rejected."""
    r = client.get("/api/v1/projects", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_api_version_in_health(client):
    """Health endpoint should report api_version."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    # Response may be wrapped in {success: true, data: {...}}
    health_data = data.get("data", data)
    assert health_data.get("api_version") == "v1"
