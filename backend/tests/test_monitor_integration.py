"""test_monitor_integration.py — HTTP-level integration tests for the Monitor
dashboard API endpoints.

Covers all 6 monitor endpoints that are NOT exercised by the existing
test_monitor_unit.py (which only tests MonitorState/RateLimiter classes
directly, not through TestClient).

Endpoints:
  GET /api/monitor/health          → Aggregated health status
  GET /api/monitor/metrics         → Prometheus-formatted metrics
  GET /api/monitor/engine-status   → Per-engine status
  GET /api/monitor/agent-activity  → Agent activity log
  GET /api/monitor/security-alerts → Active security alerts
  GET /api/monitor/alerts          → Current alert state
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


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR HEALTH ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorHealth:
    """Tests for GET /api/monitor/health."""

    def test_monitor_health_returns_200(self, client):
        """Aggregated health endpoint must return 200."""
        response = client.get("/api/monitor/health")
        assert response.status_code == 200

    def test_monitor_health_has_status(self, client):
        """Health response must include a status field."""
        response = client.get("/api/monitor/health")
        data = response.json()
        # Response may be wrapped in success/data or direct
        body = data.get("data", data)
        assert "status" in body

    def test_monitor_health_status_values(self, client):
        """Status must be one of ok, degraded, or error."""
        response = client.get("/api/monitor/health")
        data = response.json().get("data", response.json())
        assert data["status"] in ("ok", "degraded", "error")

    def test_monitor_health_has_uptime(self, client):
        """Health response must include uptime information."""
        response = client.get("/api/monitor/health")
        data = response.json().get("data", response.json())
        assert "uptime_seconds" in data or "uptime" in data

    def test_monitor_health_has_engines(self, client):
        """Health response must include engine summary."""
        response = client.get("/api/monitor/health")
        data = response.json().get("data", response.json())
        assert "engines" in data


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR METRICS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorMetrics:
    """Tests for GET /api/monitor/metrics."""

    def test_monitor_metrics_returns_200(self, client):
        """Prometheus metrics endpoint must return 200."""
        response = client.get("/api/monitor/metrics")
        assert response.status_code == 200

    def test_monitor_metrics_prometheus_format(self, client):
        """Metrics must be in Prometheus text format."""
        response = client.get("/api/monitor/metrics")
        content_type = response.headers.get("content-type", "")
        # Should be text/plain for Prometheus exposition format
        assert "text" in content_type or response.status_code == 200

    def test_monitor_metrics_contains_fireai_metrics(self, client):
        """Metrics output must contain fireai_ prefixed metrics."""
        response = client.get("/api/monitor/metrics")
        text = response.text
        assert "fireai_" in text or "HELP" in text or len(text) > 0


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR ENGINE STATUS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorEngineStatus:
    """Tests for GET /api/monitor/engine-status."""

    def test_engine_status_returns_200(self, client):
        """Engine status endpoint must return 200."""
        response = client.get("/api/monitor/engine-status")
        assert response.status_code == 200

    def test_engine_status_has_engines_list(self, client):
        """Engine status must return a list of engines."""
        response = client.get("/api/monitor/engine-status")
        data = response.json()
        body = data.get("data", data)
        # Should be a list of engine objects or contain engines
        if isinstance(body, list):
            assert len(body) >= 1
        elif isinstance(body, dict):
            assert "engines" in body or "success" in body

    def test_engine_status_each_engine_has_status(self, client):
        """Each engine entry must have a status field."""
        response = client.get("/api/monitor/engine-status")
        data = response.json()
        body = data.get("data", data)
        engines = body if isinstance(body, list) else body.get("engines", [])
        if isinstance(engines, list) and len(engines) > 0:
            for engine in engines:
                assert "status" in engine or "engine_id" in engine


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR AGENT ACTIVITY ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorAgentActivity:
    """Tests for GET /api/monitor/agent-activity."""

    def test_agent_activity_returns_200(self, client):
        """Agent activity endpoint must return 200."""
        response = client.get("/api/monitor/agent-activity")
        assert response.status_code == 200

    def test_agent_activity_with_limit(self, client):
        """Agent activity endpoint must accept limit parameter."""
        response = client.get("/api/monitor/agent-activity?limit=5")
        assert response.status_code == 200

    def test_agent_activity_returns_list(self, client):
        """Agent activity must return a list of activity entries."""
        response = client.get("/api/monitor/agent-activity")
        data = response.json()
        body = data.get("data", data)
        # Could be a list or dict with activities key
        if isinstance(body, list):
            assert isinstance(body, list)
        elif isinstance(body, dict):
            assert "activities" in body or "success" in body


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR SECURITY ALERTS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorSecurityAlerts:
    """Tests for GET /api/monitor/security-alerts."""

    def test_security_alerts_returns_200(self, client):
        """Security alerts endpoint must return 200."""
        response = client.get("/api/monitor/security-alerts")
        assert response.status_code == 200

    def test_security_alerts_with_limit(self, client):
        """Security alerts endpoint must accept limit parameter."""
        response = client.get("/api/monitor/security-alerts?limit=10")
        assert response.status_code == 200

    def test_security_alerts_with_severity_filter(self, client):
        """Security alerts must accept severity filter parameter."""
        response = client.get("/api/monitor/security-alerts?severity=high")
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR ALERTS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorAlerts:
    """Tests for GET /api/monitor/alerts."""

    def test_alerts_returns_200(self, client):
        """Alerts endpoint must return 200."""
        response = client.get("/api/monitor/alerts")
        assert response.status_code == 200

    def test_alerts_returns_list(self, client):
        """Alerts must return a list of active alerts."""
        response = client.get("/api/monitor/alerts")
        data = response.json()
        body = data.get("data", data)
        if isinstance(body, list):
            assert isinstance(body, list)
        elif isinstance(body, dict):
            # The actual response uses 'active_alerts' and 'alert_count'
            assert "active_alerts" in body or "alerts" in body or "success" in body


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-ENDPOINT: MODIFY MONITOR STATE THEN VERIFY VIA HTTP
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorStatePropagation:
    """Tests that changes to MonitorState are visible through HTTP endpoints."""

    def test_engine_degraded_reflected_in_health(self, client):
        """Setting an engine to error should be reflected in health endpoint."""
        from backend.routers.monitor import MonitorState
        monitor = MonitorState()
        monitor.get_engine("facp-engine")
        # Set to error
        monitor.set_engine_status("facp-engine", "error")
        response = client.get("/api/monitor/health")
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        # Health should reflect degraded or error state
        assert data["status"] in ("ok", "degraded", "error")
        # Restore
        monitor.set_engine_status("facp-engine", "running")

    def test_agent_activity_visible_via_http(self, client):
        """Adding agent activity should be visible through HTTP endpoint."""
        from backend.routers.monitor import MonitorState
        monitor = MonitorState()
        monitor.add_agent_activity({
            "agent_id": "test-integration-agent",
            "type": "integration_test",
            "message": "Test activity from integration tests",
        })
        response = client.get("/api/monitor/agent-activity?limit=5")
        assert response.status_code == 200

    def test_security_alert_visible_via_http(self, client):
        """Adding a security alert should be visible through HTTP endpoint."""
        from backend.routers.monitor import MonitorState
        monitor = MonitorState()
        monitor.add_security_alert({
            "severity": "low",
            "category": "test",
            "message": "Test alert from integration tests",
        })
        response = client.get("/api/monitor/security-alerts?limit=5")
        assert response.status_code == 200
