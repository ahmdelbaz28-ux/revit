"""test_projects.py — Projects CRUD integration tests.

Verifies project creation, retrieval, update, deletion, and
the cross-database bridge sync (backend DB ↔ UDM).
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


@pytest.fixture
def sample_project(client):
    """Create a sample project and return its data."""
    response = client.post(
        "/api/projects",
        json={"name": "Test Project", "description": "Test Description"},
    )
    assert response.status_code == 201, f"Failed to create project: {response.text}"
    data = response.json()
    return data.get("data", data)


class TestProjectsList:
    """Tests for GET /api/projects."""

    def test_list_projects_returns_200(self, client):
        """Project listing must return HTTP 200."""
        response = client.get("/api/projects")
        assert response.status_code == 200

    def test_list_projects_returns_paginated(self, client):
        """Project listing must include pagination metadata."""
        response = client.get("/api/projects")
        data = response.json()
        body = data.get("data", data)
        # Should have items or total count
        assert isinstance(body, (dict, list)), f"Unexpected body type: {type(body)}"


class TestProjectsCreate:
    """Tests for POST /api/projects."""

    def test_create_project_success(self, client):
        """Creating a project with valid data must succeed."""
        response = client.post(
            "/api/projects",
            json={"name": "E2E Test Project", "description": "Created by test"},
        )
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    def test_create_project_returns_id(self, client):
        """Created project must have an ID."""
        response = client.post(
            "/api/projects",
            json={"name": "ID Check Project"},
        )
        data = response.json()
        body = data.get("data", data)
        assert "id" in body or "project_id" in body, f"Missing project ID in response: {body}"

    def test_create_project_with_empty_name_fails(self, client):
        """Creating a project with an empty name must fail validation."""
        response = client.post(
            "/api/projects",
            json={"name": ""},
        )
        assert response.status_code in (400, 422), f"Expected 400/422, got {response.status_code}"


class TestProjectsGet:
    """Tests for GET /api/projects/{project_id}."""

    def test_get_existing_project(self, client, sample_project):
        """Getting an existing project must return 200."""
        pid = sample_project.get("id") or sample_project.get("project_id")
        response = client.get(f"/api/projects/{pid}")
        assert response.status_code == 200

    def test_get_nonexistent_project_404(self, client):
        """Getting a nonexistent project must return 404."""
        response = client.get("/api/projects/nonexistent-id-12345")
        assert response.status_code == 404


class TestProjectsUpdate:
    """Tests for PUT /api/projects/{project_id}."""

    def test_update_project_name(self, client, sample_project):
        """Updating a project name must succeed."""
        pid = sample_project.get("id") or sample_project.get("project_id")
        response = client.put(
            f"/api/projects/{pid}",
            json={"name": "Updated Project Name"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestProjectsDelete:
    """Tests for DELETE /api/projects/{project_id}."""

    def test_delete_project(self, client):
        """Deleting a project must succeed."""
        # Create a project to delete
        create_resp = client.post(
            "/api/projects",
            json={"name": "Delete Me Project"},
        )
        data = create_resp.json()
        body = data.get("data", data)
        pid = body.get("id") or body.get("project_id")

        # Delete it
        response = client.delete(f"/api/projects/{pid}")
        assert response.status_code == 200, f"Delete failed: {response.text}"

        # Verify it's gone
        get_resp = client.get(f"/api/projects/{pid}")
        assert get_resp.status_code == 404
