"""backend/tests/test_monitor_unit.py — Unit tests for MonitorState, DashboardRateLimiter,
and workflow path validation classes.

These are direct unit tests (no TestClient) to cover the monitor.py and workflow.py
classes that are either not registered as routes or require unavailable modules.
"""

from __future__ import annotations

import os
import time

import pytest

# ══════════════════════════════════════════════════════════════════════════════
# MONITOR STATE UNIT TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitorState:
    """Unit tests for MonitorState singleton class — no TestClient needed."""

    @pytest.fixture(autouse=True)
    def _get_monitor(self):
        """Get the monitor singleton."""
        from backend.routers.monitor import MonitorState
        self.monitor = MonitorState()
        # Reset engines to running state before each test
        for eid in ["nfpa72-engine", "nec-engine", "sprinkler-engine", "facp-engine"]:
            self.monitor.set_engine_status(eid, "running")
            self.monitor.update_engine(eid, {"cpu_percent": 10.0, "memory_mb": 50.0})

    def test_singleton_creation(self):
        """Test that MonitorState is a singleton."""
        from backend.routers.monitor import MonitorState
        m1 = MonitorState()
        m2 = MonitorState()
        assert m1 is m2

    def test_get_engines(self):
        """Test getting all engine statuses."""
        engines = self.monitor.get_engines()
        assert isinstance(engines, list)
        assert len(engines) >= 4

    def test_get_specific_engine(self):
        """Test getting a specific engine by ID."""
        engine = self.monitor.get_engine("nfpa72-engine")
        assert engine is not None
        assert engine["engine_id"] == "nfpa72-engine"
        assert engine["status"] in ("running", "degraded", "error", "stopped")

    def test_get_nonexistent_engine(self):
        """Test getting non-existent engine returns None."""
        engine = self.monitor.get_engine("nonexistent-engine")
        assert engine is None

    def test_update_engine(self):
        """Test updating engine metrics."""
        result = self.monitor.update_engine("nfpa72-engine", {"cpu_percent": 25.0})
        assert result is True
        engine = self.monitor.get_engine("nfpa72-engine")
        assert engine["cpu_percent"] == 25.0

    def test_update_nonexistent_engine(self):
        """Test updating non-existent engine returns False."""
        result = self.monitor.update_engine("nonexistent-engine", {"cpu_percent": 99.0})
        assert result is False

    def test_set_engine_status(self):
        """Test setting engine status."""
        result = self.monitor.set_engine_status("nfpa72-engine", "running")
        assert result is True
        engine = self.monitor.get_engine("nfpa72-engine")
        assert engine["status"] == "running"

    def test_set_nonexistent_engine_status(self):
        """Test setting status for non-existent engine returns False."""
        result = self.monitor.set_engine_status("nonexistent-engine", "running")
        assert result is False

    def test_add_agent_activity(self):
        """Test adding agent activity entries."""
        self.monitor.add_agent_activity({
            "agent_id": "test-agent",
            "type": "validation",
            "message": "Test activity",
        })
        activities = self.monitor.get_agent_activity(limit=10)
        assert len(activities) >= 1
        assert activities[0]["agent_id"] == "test-agent"

    def test_agent_activity_auto_timestamp(self):
        """Test that agent activity gets auto-timestamp."""
        self.monitor.add_agent_activity({"agent_id": "ts-test", "type": "test"})
        activities = self.monitor.get_agent_activity(limit=1, agent_id="ts-test")
        assert len(activities) >= 1
        assert "timestamp" in activities[0]

    def test_agent_activity_filter_by_agent(self):
        """Test filtering agent activity by agent_id."""
        self.monitor.add_agent_activity({"agent_id": "filter-agent", "type": "test"})
        activities = self.monitor.get_agent_activity(limit=10, agent_id="filter-agent")
        assert all(a["agent_id"] == "filter-agent" for a in activities)

    def test_agent_activity_filter_by_type(self):
        """Test filtering agent activity by type."""
        self.monitor.add_agent_activity({"agent_id": "type-test", "type": "validation"})
        activities = self.monitor.get_agent_activity(limit=10, activity_type="validation")
        assert all(a.get("type") == "validation" for a in activities)

    def test_add_security_alert(self):
        """Test adding security alerts."""
        self.monitor.add_security_alert({
            "severity": "high",
            "category": "unauthorized_access",
            "message": "Test alert",
        })
        alerts = self.monitor.get_security_alerts(limit=10)
        assert len(alerts) >= 1

    def test_security_alert_auto_fields(self):
        """Test that security alerts get auto-generated fields."""
        self.monitor.add_security_alert({"severity": "medium", "message": "Auto fields test"})
        alerts = self.monitor.get_security_alerts(limit=1)
        assert "alert_id" in alerts[0]
        assert "timestamp" in alerts[0]

    def test_security_alert_filter_severity(self):
        """Test filtering security alerts by severity."""
        self.monitor.add_security_alert({"severity": "critical", "message": "Critical test"})
        critical = self.monitor.get_security_alerts(limit=10, severity="critical")
        assert all(a["severity"] == "critical" for a in critical)

    def test_security_alert_filter_resolved(self):
        """Test filtering security alerts by resolved state."""
        unresolved = self.monitor.get_security_alerts(limit=10, resolved=False)
        assert all(a.get("resolved", False) is False for a in unresolved)

    def test_get_alert_rules(self):
        """Test getting alert rules."""
        rules = self.monitor.get_alert_rules()
        assert len(rules) == 5
        rule_ids = {r["rule_id"] for r in rules}
        assert "engine-down" in rule_ids
        assert "high-cpu" in rule_ids
        assert "high-memory" in rule_ids
        assert "compliance-drop" in rule_ids
        assert "high-failure-rate" in rule_ids

    def test_evaluate_alert_rules_no_alerts(self):
        """Test alert evaluation when no rules trigger."""
        alerts = self.monitor.evaluate_alert_rules()
        rule_ids = {a["rule_id"] for a in alerts}
        assert "high-cpu" not in rule_ids
        assert "high-memory" not in rule_ids

    def test_evaluate_alert_rules_high_cpu(self):
        """Test high CPU alert rule triggers correctly."""
        self.monitor.update_engine("nfpa72-engine", {"cpu_percent": 95.0})
        alerts = self.monitor.evaluate_alert_rules()
        triggered_rules = {a["rule_id"] for a in alerts}
        assert "high-cpu" in triggered_rules
        self.monitor.update_engine("nfpa72-engine", {"cpu_percent": 10.0})

    def test_evaluate_alert_rules_high_memory(self):
        """Test high memory alert rule triggers correctly."""
        self.monitor.update_engine("nfpa72-engine", {"memory_mb": 600.0})
        alerts = self.monitor.evaluate_alert_rules()
        triggered_rules = {a["rule_id"] for a in alerts}
        assert "high-memory" in triggered_rules
        self.monitor.update_engine("nfpa72-engine", {"memory_mb": 50.0})

    def test_evaluate_alert_rules_engine_down(self):
        """Test engine-down alert when heartbeat is stale."""
        with self.monitor._lock:
            self.monitor._engines["nec-engine"]["last_heartbeat"] = time.time() - 120
        alerts = self.monitor.evaluate_alert_rules()
        triggered_rules = {a["rule_id"] for a in alerts}
        assert "engine-down" in triggered_rules
        self.monitor.update_engine("nec-engine", {"cpu_percent": 10.0})

    def test_evaluate_alert_rules_high_failure_rate(self):
        """Test high failure rate alert rule."""
        self.monitor.update_engine("nfpa72-engine", {"checks_passed": 10, "checks_failed": 5})
        alerts = self.monitor.evaluate_alert_rules()
        triggered_rules = {a["rule_id"] for a in alerts}
        # 5/15 = 33% > 20% threshold
        assert "high-failure-rate" in triggered_rules
        self.monitor.update_engine("nfpa72-engine", {"checks_passed": 0, "checks_failed": 0})

    def test_aggregated_health(self):
        """Test aggregated health endpoint data."""
        health = self.monitor.aggregated_health()
        assert health["status"] == "ok"
        assert "uptime_seconds" in health
        assert "uptime_human" in health
        assert health["engines"]["running"] == 4

    def test_aggregated_health_degraded(self):
        """Test degraded health status when one engine is stopped."""
        self.monitor.set_engine_status("sprinkler-engine", "stopped")
        health = self.monitor.aggregated_health()
        assert health["status"] in ("degraded", "ok")
        self.monitor.set_engine_status("sprinkler-engine", "running")

    def test_aggregated_health_error(self):
        """Test error health status when an engine has error."""
        self.monitor.set_engine_status("facp-engine", "error")
        health = self.monitor.aggregated_health()
        assert health["status"] == "error"
        self.monitor.set_engine_status("facp-engine", "running")

    def test_collect_metrics_prometheus(self):
        """Test Prometheus metrics collection."""
        metrics = self.monitor.collect_metrics()
        assert "# HELP" in metrics
        assert "fireai_engine_info" in metrics
        assert "fireai_uptime_seconds" in metrics
        assert "fireai_engine_cpu_percent" in metrics
        assert "fireai_engine_memory_mb" in metrics
        assert "fireai_engine_checks_passed" in metrics
        assert "fireai_engine_checks_failed" in metrics
        assert "fireai_security_alerts_total" in metrics
        assert "fireai_active_alerts" in metrics
        assert "fireai_agent_activity_count" in metrics

    def test_format_uptime(self):
        """Test uptime formatting helper."""
        from backend.routers.monitor import MonitorState
        assert MonitorState._format_uptime(90) == "1m 30s"
        assert MonitorState._format_uptime(3661) == "1h 1m 1s"
        assert MonitorState._format_uptime(86400) == "1d 0s"
        assert MonitorState._format_uptime(0) == "0s"
        assert MonitorState._format_uptime(45) == "45s"

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        self.monitor.evaluate_alert_rules()
        active = self.monitor.get_active_alerts()
        assert isinstance(active, list)


class TestDashboardRateLimiter:
    """Unit tests for the DashboardRateLimiter class."""

    def test_rate_limiter_allows_normal(self):
        """Test that normal request rates are allowed."""
        from backend.routers.monitor import DashboardRateLimiter
        limiter = DashboardRateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.check("192.168.1.1") is True

    def test_rate_limiter_blocks_excess(self):
        """Test that excess requests are blocked."""
        from backend.routers.monitor import DashboardRateLimiter
        limiter = DashboardRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.check("10.0.0.1") is True
        assert limiter.check("10.0.0.1") is False

    def test_rate_limiter_per_ip(self):
        """Test that rate limiting is per-IP."""
        from backend.routers.monitor import DashboardRateLimiter
        limiter = DashboardRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.check("1.1.1.1") is True
        assert limiter.check("1.1.1.1") is True
        assert limiter.check("2.2.2.2") is True  # Different IP
        assert limiter.check("1.1.1.1") is False  # Original IP blocked

    def test_rate_limiter_window_expiry(self):
        """Test that rate limit window expires."""
        from backend.routers.monitor import DashboardRateLimiter
        limiter = DashboardRateLimiter(max_requests=2, window_seconds=1)
        assert limiter.check("3.3.3.3") is True
        assert limiter.check("3.3.3.3") is True
        assert limiter.check("3.3.3.3") is False
        time.sleep(1.1)
        assert limiter.check("3.3.3.3") is True


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW PATH VALIDATION UNIT TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestWorkflowPathValidation:
    """Direct unit tests for _validate_file_path — no langgraph dependency."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        """Import workflow module (may not be available without langgraph)."""
        try:
            from backend.routers import workflow
            self.workflow_mod = workflow
            self.available = True
        except ImportError:
            self.workflow_mod = None
            self.available = False

    def test_allowed_extensions_constant(self):
        """Test that ALLOWED_FILE_EXTENSIONS contains expected values."""
        if not self.available:
            pytest.skip("workflow module not available (requires langgraph)")
        assert ".dxf" in self.workflow_mod.ALLOWED_FILE_EXTENSIONS
        assert ".dwg" in self.workflow_mod.ALLOWED_FILE_EXTENSIONS
        assert ".pdf" in self.workflow_mod.ALLOWED_FILE_EXTENSIONS
        assert ".ifc" in self.workflow_mod.ALLOWED_FILE_EXTENSIONS
        assert ".rvt" in self.workflow_mod.ALLOWED_FILE_EXTENSIONS

    def test_allowed_dirs_constant(self):
        """Test that ALLOWED_DATA_DIRS is properly configured."""
        if not self.available:
            pytest.skip("workflow module not available")
        assert len(self.workflow_mod.ALLOWED_DATA_DIRS) >= 1

    def test_allowed_extensions_pass(self):
        """Test all allowed file extensions pass validation."""
        if not self.available:
            pytest.skip("workflow module not available")
        for ext in [".dxf", ".dwg", ".pdf", ".ifc", ".rvt"]:
            test_path = os.path.join(self.workflow_mod.ALLOWED_DATA_DIRS[0], f"test{ext}")
            result = self.workflow_mod._validate_file_path(test_path)
            assert result == test_path

    def test_disallowed_extensions_rejected(self):
        """Test disallowed file extensions are rejected."""
        if not self.available:
            pytest.skip("workflow module not available")
        from fastapi import HTTPException
        for ext in [".exe", ".sh", ".py", ".bat"]:
            test_path = os.path.join(self.workflow_mod.ALLOWED_DATA_DIRS[0], f"test{ext}")
            with pytest.raises(HTTPException) as exc_info:
                self.workflow_mod._validate_file_path(test_path)
            assert exc_info.value.status_code == 400

    def test_null_byte_injection_rejected(self):
        """Test null byte injection is blocked."""
        if not self.available:
            pytest.skip("workflow module not available")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self.workflow_mod._validate_file_path("/tmp/test.pdf\x00.sh")
        assert exc_info.value.status_code == 400

    def test_path_traversal_rejected(self):
        """Test path traversal outside allowed dirs is rejected."""
        if not self.available:
            pytest.skip("workflow module not available")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self.workflow_mod._validate_file_path("/etc/shadow.dxf")
        assert exc_info.value.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# SYNC CONNECTION MANAGER UNIT TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionManager:
    """Unit tests for the WebSocket ConnectionManager class."""

    def test_connection_manager_creation(self):
        """Test ConnectionManager initializes correctly."""
        from backend.routers.sync import ConnectionManager
        mgr = ConnectionManager()
        assert len(mgr.active_connections) == 0

    def test_subscribe_without_connection(self):
        """Test subscribing a non-connected websocket does nothing."""
        from backend.routers.sync import ConnectionManager
        mgr = ConnectionManager()
        class MockWS:
            pass
        ws = MockWS()
        mgr.subscribe(ws, "proj-001")
        assert ws not in mgr._subscriptions

    def test_disconnect_nonexistent(self):
        """Test disconnecting a non-connected websocket."""
        from backend.routers.sync import ConnectionManager
        mgr = ConnectionManager()
        class MockWS:
            pass
        ws = MockWS()
        mgr.disconnect(ws)  # Should not raise


class TestSyncWSValidation:
    """Unit tests for WebSocket origin/api key validation functions."""

    def test_validate_ws_origin_no_api_key(self):
        """Test WS origin validation when no API key is set (dev mode)."""
        # V131 FIX: _FIREAI_API_KEY was removed from sync.py — the module
        # now reads os.getenv("FIREAI_API_KEY") at runtime. Tests must
        # monkeypatch os.environ instead of the removed module attribute.
        import os

        from backend.routers.sync import _validate_ws_origin
        original_key = os.environ.get("FIREAI_API_KEY")
        try:
            os.environ.pop("FIREAI_API_KEY", None)  # No API key → dev mode
            class MockWS:
                client = None
                class headers:
                    @staticmethod
                    def get(key, default=""):
                        return default
            result = _validate_ws_origin(MockWS())
            assert result is True  # Dev mode allows
        finally:
            if original_key is not None:
                os.environ["FIREAI_API_KEY"] = original_key
            else:
                os.environ.pop("FIREAI_API_KEY", None)

    def test_validate_ws_api_key_no_key_configured(self):
        """Test WS API key validation when no key is configured."""
        # V131 FIX: _FIREAI_API_KEY was removed — use os.environ
        import os

        from backend.routers.sync import _validate_ws_api_key
        original_key = os.environ.get("FIREAI_API_KEY")
        try:
            os.environ.pop("FIREAI_API_KEY", None)  # No API key configured
            class MockWS:
                client = None
            result = _validate_ws_api_key(MockWS())
            assert result is True  # No key configured → auth disabled
        finally:
            if original_key is not None:
                os.environ["FIREAI_API_KEY"] = original_key
            else:
                os.environ.pop("FIREAI_API_KEY", None)

    def test_validate_ws_api_key_with_key_configured(self):
        """Test WS API key validation when key is configured (query param rejected)."""
        # V131 FIX: _FIREAI_API_KEY was removed — use os.environ
        import os

        from backend.routers.sync import _validate_ws_api_key
        original_key = os.environ.get("FIREAI_API_KEY")
        try:
            os.environ["FIREAI_API_KEY"] = "test-key-123"  # API key configured
            class MockWS:
                client = None
            result = _validate_ws_api_key(MockWS())
            # Query param auth is DEPRECATED and REJECTED — only
            # message-based auth is accepted when API key is configured
            assert result is False
        finally:
            if original_key is not None:
                os.environ["FIREAI_API_KEY"] = original_key
            else:
                os.environ.pop("FIREAI_API_KEY", None)
