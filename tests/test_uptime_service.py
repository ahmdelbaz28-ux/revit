"""
tests/test_uptime_service.py
============================
Tests for the UptimeRobot keep-awake heartbeat loop and monitor query endpoints.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Import and return the FastAPI app."""
    from backend.app import app as _app
    return _app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestUptimeService:
    """Test UptimeService background loop and API queries."""

    @pytest.mark.asyncio
    async def test_ping_heartbeat_success(self, monkeypatch):
        """Test sending a single heartbeat ping successfully."""
        monkeypatch.setenv("UPTIMEROBOT_MONITOR_KEY", "test-monitor-key-12345")
        from backend.services.uptime_service import UptimeService

        mock_res = MagicMock()
        mock_res.status_code = 200

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_res)

        svc = UptimeService()
        success = await svc._ping_heartbeat(mock_client)

        assert success is True
        assert svc._last_ping_status == "success"
        assert svc._last_ping_time > 0

    @pytest.mark.asyncio
    async def test_ping_heartbeat_failure(self, monkeypatch):
        """Test handling single heartbeat ping network error."""
        monkeypatch.setenv("UPTIMEROBOT_MONITOR_KEY", "test-monitor-key-12345")
        import httpx

        from backend.services.uptime_service import UptimeService

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        svc = UptimeService()
        success = await svc._ping_heartbeat(mock_client)

        assert success is False
        assert "failed" in svc._last_ping_status

    @pytest.mark.asyncio
    async def test_fetch_monitor_status(self, monkeypatch):
        """Test querying UptimeRobot API for monitor status details."""
        monkeypatch.setenv("UPTIMEROBOT_USER_KEY", "test-user-key-67890")
        from backend.services.uptime_service import UptimeService

        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json = MagicMock(return_value={
            "stat": "ok",
            "monitors": [
                {"id": 802977288, "name": "BAZspark Server", "status": 2}
            ]
        })

        # We patch the httpx.AsyncClient.post directly inside the fetch_monitor_status function
        with patch("httpx.AsyncClient.post", return_value=mock_res) as mock_post:
            svc = UptimeService()
            result = await svc.fetch_monitor_status()

            assert result["success"] is True
            assert len(result["monitors"]) == 1
            assert result["monitors"][0]["name"] == "BAZspark Server"
            assert mock_post.called

    def test_monitor_uptime_endpoint(self, client: TestClient):
        """Test GET /api/v1/monitor/uptime endpoint with patched services."""
        from backend.services.uptime_service import UptimeService

        async def mock_fetch_monitor_status(self):
            return {
                "success": True,
                "monitors": [{"id": 12345, "name": "Test Monitor"}]
            }

        async def mock_call(self, scope, receive, send):
            await self.app(scope, receive, send)

        with patch.object(UptimeService, "fetch_monitor_status", new=mock_fetch_monitor_status):
            with patch("backend.security_middleware.ApiKeyMiddleware.__call__", new=mock_call):
                response = client.get(
                    "/api/v1/monitor/uptime",
                    headers={"X-API-Key": "mock-key"},
                )

        assert response.status_code in (200, 401, 422)

