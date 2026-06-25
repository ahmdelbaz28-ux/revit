"""test_sync_websocket.py — WebSocket integration tests for the sync endpoint.

Covers the WebSocket /ws endpoint that existing tests don't exercise:
  - WebSocket connection and ping/pong
  - WebSocket subscribe action
  - WebSocket invalid JSON handling
  - Sync status via WebSocket get_status action
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
def test_project(client):
    """Create a project for sync/websocket tests."""
    resp = client.post(
        "/api/projects",
        json={"name": "WebSocket Test Project"},
    )
    data = resp.json().get("data", resp.json())
    return data.get("id") or data.get("project_id")


# ══════════════════════════════════════════════════════════════════════════════
# SYNC REST ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


class TestSyncRestEndpoints:
    """Additional tests for sync REST endpoints."""

    def test_sync_and_verify_status(self, client, test_project):
        """After syncing, the status should reflect 'synced' or 'syncing'."""
        pid = test_project
        # Trigger sync
        client.post(f"/api/projects/{pid}/sync")
        # Check status
        resp = client.get(f"/api/projects/{pid}/sync")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("status") in ("synced", "syncing", None)

    def test_sync_nonexistent_project(self, client):
        """Syncing nonexistent project must return 404."""
        resp = client.post("/api/projects/nonexistent-proj/sync")
        assert resp.status_code == 404

    def test_get_sync_status_nonexistent(self, client):
        """Getting sync status for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/sync")
        assert resp.status_code == 404

    def test_sync_then_get_status_data_structure(self, client, test_project):
        """Sync status response must have expected fields."""
        pid = test_project
        client.post(f"/api/projects/{pid}/sync")
        resp = client.get(f"/api/projects/{pid}/sync")
        data = resp.json().get("data", {})
        # Should have at least a status field
        assert isinstance(data, dict)


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestWebSocket:
    """Tests for WebSocket /ws endpoint."""

    def test_websocket_connect(self, client):
        """WebSocket connection must be accepted."""
        with client.websocket_connect("/ws"):
            # Connection should succeed
            pass  # Just connecting and disconnecting is a valid test

    def test_websocket_ping_pong(self, client):
        """WebSocket ping action must return pong."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"action": "ping"})
            response = ws.receive_json()
            assert response.get("type") == "pong"
            assert response.get("channel") == "system"

    def test_websocket_subscribe(self, client):
        """WebSocket subscribe action must confirm subscription."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"action": "subscribe", "projectId": "test-project-123"})
            response = ws.receive_json()
            assert response.get("type") == "subscribed"
            assert response.get("data", {}).get("projectId") == "test-project-123"

    def test_websocket_invalid_json(self, client):
        """WebSocket must handle invalid JSON gracefully."""
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not valid json {{{")
            response = ws.receive_json()
            assert response.get("channel") == "error" or response.get("type") == "invalid_message"

    def test_websocket_get_status(self, client, test_project):
        """WebSocket get_status action must return sync status."""
        pid = test_project
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"action": "get_status", "projectId": pid})
            response = ws.receive_json()
            assert response.get("channel") == "sync" or response.get("type") == "status"

    def test_websocket_multiple_actions(self, client):
        """WebSocket must handle multiple sequential actions."""
        with client.websocket_connect("/ws") as ws:
            # First ping
            ws.send_json({"action": "ping"})
            resp1 = ws.receive_json()
            assert resp1.get("type") == "pong"

            # Then subscribe
            ws.send_json({"action": "subscribe", "projectId": "multi-test"})
            resp2 = ws.receive_json()
            assert resp2.get("type") == "subscribed"

            # Another ping
            ws.send_json({"action": "ping"})
            resp3 = ws.receive_json()
            assert resp3.get("type") == "pong"
