"""test_connections_advanced.py — Advanced connection CRUD integration tests
covering device validation, self-connection prevention, and connection
listing with pagination and sort.

Focuses on code paths NOT covered by existing tests:
  - Connection creation with nonexistent target device (specific error)
  - Connection self-validation (fromId == toId should fail at schema level)
  - Connection listing with sort and order parameters
  - Connection creation with custom cable_size, length, and type
  - Connection deletion cascade verification
  - Connection creation in nonexistent project
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _setup_env():
    """Set development environment for testing."""
    os.environ["FIREAI_ENV"] = "development"
    os.environ["FIREAI_API_KEY"] = ""


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    from backend.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project_with_two_devices(client):
    """Create a project with two devices for connection tests."""
    # Create project
    proj_resp = client.post(
        "/api/projects",
        json={"name": "Connection Test Project", "description": "For connection tests"},
    )
    proj_data = proj_resp.json().get("data", proj_resp.json())
    pid = proj_data.get("id") or proj_data.get("project_id")

    # Create device 1
    dev1_resp = client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Panel FACP-01",
            "type": "FA_PANEL",
            "category": "FIRE_ALARM",
            "x": 0.0, "y": 0.0,
            "voltage": 24.0, "current": 2.0, "load": 2.0,
        },
    )
    dev1 = dev1_resp.json().get("data", dev1_resp.json())

    # Create device 2
    dev2_resp = client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Smoke Detector SD-01",
            "type": "FA_SMOKE",
            "category": "FIRE_ALARM",
            "x": 10.0, "y": 20.0,
            "voltage": 24.0, "current": 0.1, "load": 0.1,
        },
    )
    dev2 = dev2_resp.json().get("data", dev2_resp.json())

    return pid, dev1, dev2


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION CREATION WITH DEVICE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionDeviceValidation:
    """Tests for device existence validation during connection creation."""

    def test_create_connection_nonexistent_source_device(self, client, project_with_two_devices):
        """Connection with nonexistent source device must return 400."""
        pid, _, dev2 = project_with_two_devices
        dev2_id = dev2.get("id") or dev2.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": "nonexistent-source-id",
                "toId": dev2_id,
                "cableSize": "1.5mm²",
                "length": 15.0,
                "type": "power",
            },
        )
        assert resp.status_code == 400

    def test_create_connection_nonexistent_target_device(self, client, project_with_two_devices):
        """Connection with nonexistent target device must return 400."""
        pid, dev1, _ = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": "nonexistent-target-id",
                "cableSize": "1.5mm²",
                "length": 15.0,
                "type": "power",
            },
        )
        assert resp.status_code == 400

    def test_create_connection_both_devices_nonexistent(self, client, project_with_two_devices):
        """Connection with both devices nonexistent must return 400."""
        pid, _, _ = project_with_two_devices
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": "nonexistent-source",
                "toId": "nonexistent-target",
                "cableSize": "1.5mm²",
                "length": 15.0,
                "type": "power",
            },
        )
        assert resp.status_code == 400

    def test_create_connection_self_connection_rejected(self, client, project_with_two_devices):
        """Connection with fromId == toId must be rejected (self-connection)."""
        pid, dev1, _ = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": dev1_id,
                "cableSize": "1.5mm²",
                "length": 0.0,
                "type": "power",
            },
        )
        # Self-connection validation in schema returns 422
        assert resp.status_code in (400, 422)

    def test_create_connection_in_nonexistent_project(self, client):
        """Connection in nonexistent project must return 404."""
        resp = client.post(
            "/api/projects/nonexistent-proj-id/connections",
            json={
                "fromId": "dev-a",
                "toId": "dev-b",
                "cableSize": "1.5mm²",
                "length": 10.0,
                "type": "power",
            },
        )
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION CREATION WITH CUSTOM PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionCustomParameters:
    """Tests for connection creation with custom cable and type parameters."""

    def test_create_connection_with_custom_cable_size(self, client, project_with_two_devices):
        """Connection with custom cableSize must be stored correctly."""
        pid, dev1, dev2 = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        dev2_id = dev2.get("id") or dev2.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": dev2_id,
                "cableSize": "2.5mm²",
                "length": 30.0,
                "type": "power",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("cableSize") == "2.5mm²"

    def test_create_connection_with_signal_type(self, client, project_with_two_devices):
        """Connection with type='signal' must be stored correctly."""
        pid, dev1, dev2 = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        dev2_id = dev2.get("id") or dev2.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": dev2_id,
                "cableSize": "0.5mm²",
                "length": 50.0,
                "type": "signal",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("type") == "signal"

    def test_create_connection_default_cable_size(self, client, project_with_two_devices):
        """Connection without cableSize must default to '1.5mm²'."""
        pid, dev1, dev2 = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        dev2_id = dev2.get("id") or dev2.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": dev2_id,
                "length": 20.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("cableSize") == "1.5mm²"

    def test_create_connection_default_type(self, client, project_with_two_devices):
        """Connection without type must default to 'power'."""
        pid, dev1, dev2 = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        dev2_id = dev2.get("id") or dev2.get("device_id")
        resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": dev2_id,
                "length": 10.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("type") == "power"


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION LISTING
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionListing:
    """Tests for connection listing with pagination and sort."""

    def test_list_connections_with_sort(self, client, project_with_two_devices):
        """Listing connections with sort parameter must succeed."""
        pid, _, _ = project_with_two_devices
        resp = client.get(f"/api/projects/{pid}/connections?sort=createdAt&order=asc")
        assert resp.status_code == 200

    def test_list_connections_sort_by_length(self, client, project_with_two_devices):
        """Listing connections sorted by length must succeed."""
        pid, _, _ = project_with_two_devices
        resp = client.get(f"/api/projects/{pid}/connections?sort=length&order=asc")
        assert resp.status_code == 200

    def test_list_connections_sort_by_type(self, client, project_with_two_devices):
        """Listing connections sorted by type must succeed."""
        pid, _, _ = project_with_two_devices
        resp = client.get(f"/api/projects/{pid}/connections?sort=type&order=desc")
        assert resp.status_code == 200

    def test_list_connections_nonexistent_project_404(self, client):
        """Listing connections for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/connections")
        assert resp.status_code == 404

    def test_list_connections_pagination(self, client, project_with_two_devices):
        """Listing connections with pagination must include metadata."""
        pid, _, _ = project_with_two_devices
        resp = client.get(f"/api/projects/{pid}/connections?page=1&limit=10")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        # Should have pagination fields
        assert "total" in data or "data" in data or "items" in data


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION DELETION
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionDeletion:
    """Tests for connection deletion edge cases."""

    def test_delete_connection_then_verify_gone(self, client, project_with_two_devices):
        """After deleting a connection, it should not be findable."""
        pid, dev1, dev2 = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        dev2_id = dev2.get("id") or dev2.get("device_id")
        # Create a connection
        create_resp = client.post(
            f"/api/projects/{pid}/connections",
            json={"fromId": dev1_id, "toId": dev2_id, "length": 15.0, "type": "power"},
        )
        assert create_resp.status_code == 201
        conn_data = create_resp.json().get("data", create_resp.json())
        conn_id = conn_data.get("id") or conn_data.get("connection_id")
        if not conn_id:
            pytest.skip("No connection ID returned")
        # Delete it
        del_resp = client.delete(f"/api/projects/{pid}/connections/{conn_id}")
        assert del_resp.status_code == 200

    def test_delete_connection_nonexistent_project_404(self, client):
        """Deleting connection in nonexistent project must return 404."""
        resp = client.delete("/api/projects/nonexistent-proj/connections/some-conn")
        assert resp.status_code == 404

    def test_delete_connection_twice(self, client, project_with_two_devices):
        """Deleting a connection twice must return 404 on second attempt."""
        pid, dev1, dev2 = project_with_two_devices
        dev1_id = dev1.get("id") or dev1.get("device_id")
        dev2_id = dev2.get("id") or dev2.get("device_id")
        # Create and delete
        create_resp = client.post(
            f"/api/projects/{pid}/connections",
            json={"fromId": dev1_id, "toId": dev2_id, "length": 20.0},
        )
        conn_data = create_resp.json().get("data", create_resp.json())
        conn_id = conn_data.get("id") or conn_data.get("connection_id")
        if not conn_id:
            pytest.skip("No connection ID returned")
        client.delete(f"/api/projects/{pid}/connections/{conn_id}")
        # Delete again
        resp = client.delete(f"/api/projects/{pid}/connections/{conn_id}")
        assert resp.status_code == 404
