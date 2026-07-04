"""
test_basebyright.py — Comprehensive tests for the BASEBYRIGHT framework itself.
===============================================================================

This file tests the BASEBYRIGHT framework's own components:
  1. BaseByRightError — custom exception
  2. StateIsolationContext — state tracking & cleanup
  3. FaultInjector — fault injection & deactivation
  4. GoldenTestRunner — golden snapshot recording & comparison
  5. IdempotencyChecker — PUT/DELETE idempotency verification
  6. BaseByRight — main class assertions & context managers
  7. Integration with real backend endpoints

Usage:
    pytest backend/basebyright/test_basebyright.py -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest

from backend.basebyright import (
    BaseByRight,
    BaseByRightError,
    FaultInjector,
    GoldenTestRunner,
    IdempotencyChecker,
    StateIsolationContext,
    REQUIRED_SECURITY_HEADERS,
    create_basebyright,
)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

TEST_API_KEY = "test-api-key-for-testing-only"

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module", autouse=True)
def _setup_env() -> None:
    """Set development environment for testing."""
    os.environ["FIREAI_ENV"] = "development"
    os.environ["FIREAI_API_KEY"] = TEST_API_KEY


@pytest.fixture(scope="module")
def client():
    """Create a test client without auth (for 401 tests)."""
    from fastapi.testclient import TestClient
    from backend.app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client():
    """Create a test client that always sends the test API key.

    The FIREAI_API_KEY env var bypass in ApiKeyMiddleware checks
    `hmac.compare_digest(api_key, env_key)`. Setting the env var
    to a known value and sending that same value as X-API-Key
    grants ADMIN role. This is the established pattern from
    backend/tests/conftest.py (V138 FIX).
    """
    from fastapi.testclient import TestClient
    from backend.app import app

    # Ensure the env var is set (conftest sets it at module level,
    # but we set it again here to be safe)
    os.environ.setdefault("FIREAI_API_KEY", TEST_API_KEY)

    with TestClient(app, headers={"X-API-Key": TEST_API_KEY}) as c:
        yield c


@pytest.fixture
def bbr(auth_client):
    """Create a BASEBYRIGHT instance with strict_mode=True for testing."""
    return BaseByRight(auth_client, strict_mode=True)


@pytest.fixture
def bbr_nonstrict(auth_client):
    """Create a BASEBYRIGHT instance with strict_mode=False (records failures without raising)."""
    return BaseByRight(auth_client, strict_mode=False, auto_cleanup=True)


@pytest.fixture
def mock_response():
    """Create a mock HTTP response for unit testing assertions."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'self'",
        "strict-transport-security": "max-age=31536000",
        "referrer-policy": "no-referrer",
        "x-xss-protection": "0",
        "permissions-policy": "accelerometer=()",
        "x-correlation-id": "test-correlation-id",
        "content-type": "application/json",
        "www-authenticate": 'X-API-Key realm="fireai"',
    }
    resp.json.return_value = {"success": True, "data": {"id": "test-id"}}
    resp.text = '{"success": true, "data": {"id": "test-id"}}'
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# 1. BaseByRightError Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBaseByRightError:
    """Tests for the custom BaseByRightError exception."""

    def test_error_has_contract_and_detail(self) -> None:
        """Error must include contract name and detail dict."""
        err = BaseByRightError("Test message", contract="TEST_CONTRACT", detail={"key": "value"})
        assert err.contract == "TEST_CONTRACT"
        assert err.detail == {"key": "value"}
        assert "TEST_CONTRACT" in str(err)
        assert "Test message" in str(err)

    def test_error_default_detail(self) -> None:
        """Error must default detail to empty dict."""
        err = BaseByRightError("Simple message", contract="SIMPLE")
        assert err.detail == {}


# ═══════════════════════════════════════════════════════════════════════════
# 2. StateIsolationContext Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestStateIsolationContext:
    """Tests for StateIsolationContext — state tracking & cleanup."""

    def test_track_and_all_tracked(self, auth_client) -> None:
        """Tracked resources must appear in all_tracked."""
        ctx = StateIsolationContext(auth_client)
        ctx.track_project("proj-1")
        ctx.track_device("dev-1")
        ctx.track_element("elem-1")
        ctx.track_connection("conn-1")

        tracked = ctx.all_tracked
        assert "proj-1" in tracked
        assert "dev-1" in tracked
        assert "elem-1" in tracked
        assert "conn-1" in tracked

    def test_cleanup_clears_tracked(self, auth_client) -> None:
        """Cleanup must clear all tracked resources."""
        ctx = StateIsolationContext(auth_client)
        ctx.track_project("proj-clean-1")
        ctx.track_element("elem-clean-1")
        ctx.cleanup()
        assert len(ctx.all_tracked) == 0

    def test_reset_rate_limiter_does_not_crash(self, auth_client) -> None:
        """reset_rate_limiter must not raise exceptions."""
        ctx = StateIsolationContext(auth_client)
        ctx.reset_rate_limiter()

    def test_reset_cache_does_not_crash(self, auth_client) -> None:
        """reset_cache must not raise exceptions."""
        ctx = StateIsolationContext(auth_client)
        ctx.reset_cache()

    def test_thread_safety(self, auth_client) -> None:
        """Concurrent track calls must not corrupt state."""
        import threading

        ctx = StateIsolationContext(auth_client)
        errors = []

        def _track(n: int) -> None:
            try:
                for i in range(100):
                    ctx.track_project(f"thread-{n}-proj-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_track, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(ctx.all_tracked) == 500  # 5 threads × 100 projects


# ═══════════════════════════════════════════════════════════════════════════
# 3. FaultInjector Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestFaultInjector:
    """Tests for FaultInjector — fault injection & deactivation."""

    def test_activate_sets_env_var(self) -> None:
        """Activate must set the corresponding env var."""
        injector = FaultInjector()
        injector.activate(db_fault="connection_lost")
        assert os.environ.get("FIREAI_FAULT_DB_FAULT") == "connection_lost"
        assert injector.is_active
        injector.deactivate_all()

    def test_deactivate_clears_env_var(self) -> None:
        """Deactivate must clear the env var."""
        injector = FaultInjector()
        injector.activate(db_fault="timeout")
        assert os.environ.get("FIREAI_FAULT_DB_FAULT") == "timeout"
        injector.deactivate_all()
        assert "FIREAI_FAULT_DB_FAULT" not in os.environ
        assert not injector.is_active

    def test_multiple_faults(self) -> None:
        """Multiple faults must be tracked independently."""
        injector = FaultInjector()
        injector.activate(db_fault="connection_lost", cache_fault="unavailable")
        assert injector.active_faults == {
            "db_fault": "connection_lost",
            "cache_fault": "unavailable",
        }
        injector.deactivate_all()
        assert injector.active_faults == {}

    def test_restores_original_value(self) -> None:
        """Deactivate must restore the original env var value."""
        os.environ["FIREAI_FAULT_DB_FAULT"] = "original_value"
        injector = FaultInjector()
        injector.activate(db_fault="new_value")
        assert os.environ["FIREAI_FAULT_DB_FAULT"] == "new_value"
        injector.deactivate_all()
        assert os.environ["FIREAI_FAULT_DB_FAULT"] == "original_value"
        os.environ.pop("FIREAI_FAULT_DB_FAULT", None)

    def test_fault_catalog_has_descriptions(self) -> None:
        """Every fault type must have a description."""
        injector = FaultInjector()
        assert len(injector.FAULT_CATALOG) >= 9
        for fault_type, description in injector.FAULT_CATALOG.items():
            assert len(description) > 10, f"Fault {fault_type} has short description"


# ═══════════════════════════════════════════════════════════════════════════
# 4. GoldenTestRunner Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestGoldenTestRunner:
    """Tests for GoldenTestRunner — golden snapshot recording & comparison."""

    def test_record_and_assert_match(self, auth_client, tmp_path) -> None:
        """Record a golden snapshot, then assert a matching response passes."""
        runner = GoldenTestRunner(auth_client)
        runner.GOLDEN_DIR = str(tmp_path)

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = {"success": True, "data": {"name": "test"}}
        resp.text = '{"success": true, "data": {"name": "test"}}'

        path = runner.record_golden("test_endpoint", resp)
        assert os.path.exists(path)

        result = runner.assert_against_golden("test_endpoint", resp)
        assert result.passed, f"Golden test failed: {result.diff}"

    def test_assert_missing_golden_raises(self, auth_client) -> None:
        """Asserting against a non-existent golden must raise BaseByRightError."""
        runner = GoldenTestRunner(auth_client)
        resp = MagicMock()
        resp.status_code = 200

        with pytest.raises(BaseByRightError, match="GOLDEN_MISSING"):
            runner.assert_against_golden("nonexistent_golden", resp)

    def test_summary_counts(self, auth_client, tmp_path) -> None:
        """Summary must report correct pass/fail counts."""
        runner = GoldenTestRunner(auth_client)
        runner.GOLDEN_DIR = str(tmp_path)

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = {"success": True}
        resp.text = '{"success": true}'
        runner.record_golden("summary_test", resp)

        runner.assert_against_golden("summary_test", resp)

        summary = runner.summary()
        assert summary["total"] == 1
        assert summary["passed"] == 1
        assert summary["failed"] == 0

    def test_shallow_compare_ignores_nondeterministic(self, auth_client) -> None:
        """Shallow compare must ignore non-deterministic fields like id, timestamp."""
        runner = GoldenTestRunner(auth_client)

        expected = {
            "id": "some-uuid",
            "name": "Test",
            "created_at": "2026-01-01T00:00:00",
        }
        actual = {
            "id": "different-uuid",
            "name": "Test",
            "created_at": "2026-07-04T13:00:00",
        }

        assert runner._shallow_compare(expected, actual), "Non-deterministic fields should be ignored"


# ═══════════════════════════════════════════════════════════════════════════
# 5. IdempotencyChecker Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotencyChecker:
    """Tests for IdempotencyChecker — PUT/DELETE idempotency verification."""

    def _create_v1_project(self, client):
        """Create a project using the /api/v1/projects endpoint.
        
        Tests in backend/basebyright/ do NOT get the URL-rewriting that
        conftest.py provides for backend/tests/. Use /api/v1/ paths directly.
        """
        return client.post(
            "/api/v1/projects",
            json={"name": "Idempotency Test Project"},
        )

    def test_check_put_idempotent_same_status(self, auth_client) -> None:
        """PUT to same resource twice must return same status."""
        create_resp = self._create_v1_project(auth_client)
        assert create_resp.status_code == 201, f"Create failed: {create_resp.status_code} {create_resp.text}"
        project = create_resp.json().get("data", create_resp.json())
        pid = project.get("id") or project.get("project_id")
        assert pid is not None, f"No project ID in response: {project}"

        passed, message = IdempotencyChecker.check_put_idempotent(
            auth_client,
            f"/api/v1/projects/{pid}",
            {"name": "Updated Name"},
        )
        assert passed, message

    def test_check_delete_idempotent(self, auth_client) -> None:
        """DELETE twice: first=200, second=404."""
        create_resp = self._create_v1_project(auth_client)
        assert create_resp.status_code == 201
        project = create_resp.json().get("data", create_resp.json())
        pid = project.get("id") or project.get("project_id")
        assert pid is not None, f"No project ID in response: {project}"

        passed, message = IdempotencyChecker.check_delete_idempotent(
            auth_client,
            f"/api/v1/projects/{pid}",
            expected_first_status=200,
        )
        assert passed, message


# ═══════════════════════════════════════════════════════════════════════════
# 6. BaseByRight Main Class Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBaseByRightAssertions:
    """Tests for BaseByRight core assertion methods (with strict_mode=True)."""

    def test_assert_200_passes(self, bbr, mock_response) -> None:
        """assert_200 must pass for status 200."""
        bbr.assert_200(mock_response)

    def test_assert_200_fails(self) -> None:
        """assert_200 must fail for non-200 status."""
        # Use a fresh instance with strict_mode=True
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        resp = MagicMock()
        resp.status_code = 404
        with pytest.raises(BaseByRightError, match="STATUS_"):
            bbr_strict.assert_200(resp)

    def test_assert_201_passes(self, bbr, mock_response) -> None:
        """assert_201 must pass for status 201."""
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = mock_response.headers
        resp.json.return_value = mock_response.json.return_value
        resp.text = mock_response.text
        bbr.assert_201(resp)

    def test_assert_400_passes(self, bbr) -> None:
        """assert_400 must pass for status 400."""
        resp = MagicMock()
        resp.status_code = 400
        bbr.assert_400(resp)

    def test_assert_401_passes(self, bbr) -> None:
        """assert_401 must pass for status 401."""
        resp = MagicMock()
        resp.status_code = 401
        bbr.assert_401(resp)

    def test_assert_403_passes(self, bbr) -> None:
        """assert_403 must pass for status 403."""
        resp = MagicMock()
        resp.status_code = 403
        bbr.assert_403(resp)

    def test_assert_404_passes(self, bbr) -> None:
        """assert_404 must pass for status 404."""
        resp = MagicMock()
        resp.status_code = 404
        bbr.assert_404(resp)

    def test_assert_422_passes(self, bbr) -> None:
        """assert_422 must pass for status 422."""
        resp = MagicMock()
        resp.status_code = 422
        bbr.assert_422(resp)

    def test_assert_429_passes(self, bbr) -> None:
        """assert_429 must pass for status 429."""
        resp = MagicMock()
        resp.status_code = 429
        bbr.assert_429(resp)

    def test_assert_not_500_passes(self, bbr, mock_response) -> None:
        """assert_not_500 must pass for non-500 status."""
        bbr.assert_not_500(mock_response)

    def test_assert_not_500_fails(self) -> None:
        """assert_not_500 must fail for status 500."""
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        resp = MagicMock()
        resp.status_code = 500
        with pytest.raises(BaseByRightError, match="STATUS_500"):
            bbr_strict.assert_not_500(resp)

    def test_assert_status_with_set(self, bbr) -> None:
        """assert_status must accept a set of acceptable codes."""
        resp = MagicMock()
        resp.status_code = 503
        bbr.assert_status(resp, {200, 503})

    def test_assert_status_with_list(self, bbr) -> None:
        """assert_status must accept a list of acceptable codes."""
        resp = MagicMock()
        resp.status_code = 201
        bbr.assert_status(resp, [200, 201, 202])

    def test_assert_status_returns_actual(self, bbr) -> None:
        """assert_status must return the actual status code."""
        resp = MagicMock()
        resp.status_code = 418
        actual = bbr.assert_status(resp, {200, 418})
        assert actual == 418


class TestBaseByRightSecurityAssertions:
    """Tests for BaseByRight security header assertions (with strict_mode=True)."""

    def test_assert_security_headers_all_present(self, bbr, mock_response) -> None:
        """All required headers present must pass."""
        missing = bbr.assert_security_headers(mock_response)
        assert len(missing) == 0

    def test_assert_security_headers_missing(self) -> None:
        """Missing headers must raise with strict_mode=True."""
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/plain"}

        with pytest.raises(BaseByRightError, match="SECURITY_HEADERS"):
            bbr_strict.assert_security_headers(resp)

    def test_assert_has_correlation_id_present(self, bbr, mock_response) -> None:
        """X-Correlation-ID present must pass."""
        bbr.assert_has_correlation_id(mock_response)

    def test_assert_has_correlation_id_missing(self) -> None:
        """Missing X-Correlation-ID must fail with strict_mode=True."""
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        with pytest.raises(BaseByRightError, match="CORRELATION_ID"):
            bbr_strict.assert_has_correlation_id(resp)

    def test_assert_www_authenticate_on_401_present(self, bbr) -> None:
        """401 with WWW-Authenticate must pass."""
        resp = MagicMock()
        resp.status_code = 401
        resp.headers = {"www-authenticate": 'X-API-Key realm="fireai"'}
        bbr.assert_www_authenticate_on_401(resp)

    def test_assert_www_authenticate_on_401_missing(self) -> None:
        """401 without WWW-Authenticate must fail with strict_mode=True."""
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        resp = MagicMock()
        resp.status_code = 401
        resp.headers = {}
        with pytest.raises(BaseByRightError, match="WWW_AUTHENTICATE"):
            bbr_strict.assert_www_authenticate_on_401(resp)


class TestBaseByRightJsonAssertions:
    """Tests for BaseByRight JSON response assertions (with strict_mode=True)."""

    def test_assert_json_response_valid(self, bbr, mock_response) -> None:
        """Valid JSON with 'success' field must pass."""
        data = bbr.assert_json_response(mock_response)
        assert data.get("success") is True

    def test_assert_json_response_invalid(self) -> None:
        """Invalid JSON must fail with strict_mode=True."""
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        resp = MagicMock()
        resp.json.side_effect = ValueError("Invalid JSON")
        with pytest.raises(BaseByRightError, match="JSON_BODY"):
            bbr_strict.assert_json_response(resp)

    def test_assert_has_field_present(self, bbr) -> None:
        """Existing field must pass."""
        data = {"name": "test", "value": 42}
        bbr.assert_has_field(data, "name")

    def test_assert_has_field_missing(self) -> None:
        """Missing field must fail with strict_mode=True."""
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        bbr_strict = BaseByRight(client, strict_mode=True)

        data = {"name": "test"}
        with pytest.raises(BaseByRightError, match="FIELD_PRESENCE"):
            bbr_strict.assert_has_field(data, "nonexistent")


class TestBaseByRightContextManagers:
    """Tests for BaseByRight context managers."""

    def test_isolated_project_creates_and_cleans(self, auth_client) -> None:
        """isolated_project must create a project and clean it up on exit.

        NOTE: Tests in backend/basebyright/ do NOT get the URL-rewriting that
        conftest.py provides for backend/tests/. The BaseByRight.isolated_project()
        POSTs to /api/projects which only works if conftest rewrites it.
        We use the V1 path directly to be compatible.
        """
        bbr = BaseByRight(auth_client, strict_mode=False, auto_cleanup=True)

        with bbr.isolated_project() as project:
            pid = project.get("id") or project.get("project_id")
            assert pid is not None, f"Project must have an ID: {project}"

            resp = auth_client.get(f"/api/v1/projects/{pid}")
            assert resp.status_code == 200

        resp = auth_client.get(f"/api/v1/projects/{pid}")
        assert resp.status_code == 404, "Project should be cleaned up"

    def test_isolated_project_auto_cleanup_disabled(self, auth_client) -> None:
        """With auto_cleanup=False, project must persist after context exit."""
        bbr = BaseByRight(auth_client, strict_mode=False, auto_cleanup=False)

        with bbr.isolated_project() as project:
            pid = project.get("id") or project.get("project_id")

        resp = auth_client.get(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200, "Project should persist with auto_cleanup=False"

        auth_client.delete(f"/api/v1/projects/{pid}")

    def test_fault_injector_context(self, bbr) -> None:
        """fault_injector must activate and deactivate faults."""
        with bbr.fault_injector(db_fault="connection_lost"):
            assert bbr.faults.is_active
            assert "FIREAI_FAULT_DB_FAULT" in os.environ

        assert not bbr.faults.is_active
        assert "FIREAI_FAULT_DB_FAULT" not in os.environ


class TestBaseByRightReport:
    """Tests for BaseByRight reporting."""

    def test_report_has_summary(self, bbr, mock_response) -> None:
        """Report must include summary with pass/fail counts."""
        bbr.assert_200(mock_response)
        report = bbr.report()
        assert "summary" in report
        assert report["summary"]["total"] >= 1
        assert report["summary"]["passed"] >= 1

    def test_report_has_results(self, bbr, mock_response) -> None:
        """Report must include detailed results."""
        bbr.assert_200(mock_response)
        bbr.assert_security_headers(mock_response)
        report = bbr.report()
        assert len(report["results"]) >= 2

    def test_save_report_creates_file(self, bbr, mock_response, tmp_path) -> None:
        """save_report must create a JSON file."""
        bbr.assert_200(mock_response)
        report_path = os.path.join(str(tmp_path), "test_report.json")
        saved_path = bbr.save_report(path=report_path)
        assert os.path.exists(saved_path)
        with open(saved_path, "r") as f:
            data = json.load(f)
        assert data["framework"] == "BASEBYRIGHT"
        assert data["summary"]["total"] >= 1

    def test_print_report_does_not_crash(self, bbr, mock_response, capsys) -> None:
        """print_report must not raise exceptions."""
        bbr.assert_200(mock_response)
        bbr.print_report()
        captured = capsys.readouterr()
        assert "BASEBYRIGHT Report" in captured.out


class TestBaseByRightRBAC:
    """Tests for BaseByRight RBAC assertions."""

    def test_admin_only_endpoint_cache_clear(self, auth_client) -> None:
        """Cache clear endpoint must reject non-admin requests."""
        bbr = BaseByRight(auth_client, strict_mode=False)
        bbr.assert_admin_only_endpoint("/api/v1/cache/clear", method="POST")

        report = bbr.report()
        rbac_results = [r for r in report["results"] if r["contract"] == "RBAC_ENFORCED"]
        assert len(rbac_results) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 7. Integration Tests with Real Backend
# ═══════════════════════════════════════════════════════════════════════════


class TestBaseByRightIntegration:
    """Integration tests: BASEBYRIGHT with real backend endpoints."""

    def test_health_endpoint_full_validation(self, auth_client) -> None:
        """Full BASEBYRIGHT validation of /api/health."""
        bbr = BaseByRight(auth_client, strict_mode=False)

        response = auth_client.get("/api/health")

        bbr.assert_not_500(response)
        bbr.assert_200(response)
        bbr.assert_security_headers(response)
        bbr.assert_has_correlation_id(response)

        data = bbr.assert_json_response(response)
        body = data.get("data", data)
        bbr.assert_has_field(body, "status")
        bbr.assert_has_field(body, "version")
        bbr.assert_has_field(body, "timestamp")

        report = bbr.report()
        assert report["summary"]["failed"] == 0, f"Assertions failed: {report['results']}"

    def test_projects_crud_with_basebyright(self, auth_client) -> None:
        """Complete CRUD cycle validated with BASEBYRIGHT."""
        bbr = BaseByRight(auth_client, strict_mode=False)

        create_resp = auth_client.post(
            "/api/v1/projects",
            json={"name": "BBR Integration Test", "description": "Testing BASEBYRIGHT"},
        )
        bbr.assert_201(create_resp)
        bbr.assert_security_headers(create_resp)
        bbr.assert_not_500(create_resp)
        project = create_resp.json().get("data", create_resp.json())
        pid = project.get("id") or project.get("project_id")
        assert pid is not None, f"No project ID: {project}"

        get_resp = auth_client.get(f"/api/v1/projects/{pid}")
        bbr.assert_200(get_resp)
        bbr.assert_security_headers(get_resp)

        update_resp = auth_client.put(
            f"/api/v1/projects/{pid}",
            json={"name": "BBR Updated Project"},
        )
        bbr.assert_200(update_resp)
        bbr.assert_security_headers(update_resp)

        delete_resp = auth_client.delete(f"/api/v1/projects/{pid}")
        bbr.assert_200(delete_resp)
        bbr.assert_security_headers(delete_resp)

        get_deleted = auth_client.get(f"/api/v1/projects/{pid}")
        bbr.assert_404(get_deleted)

        report = bbr.report()
        assert report["summary"]["failed"] == 0, f"CRUD assertions failed: {report['results']}"

    def test_unauthorized_access_returns_401(self, client) -> None:
        """Requests without API key must return 401."""
        bbr = BaseByRight(client, strict_mode=False)

        response = client.get("/api/projects")
        bbr.assert_401(response)
        bbr.assert_www_authenticate_on_401(response)
        bbr.assert_security_headers(response)
        bbr.assert_not_500(response)

    def test_nonexistent_resource_returns_404(self, auth_client) -> None:
        """Nonexistent resources must return 404."""
        bbr = BaseByRight(auth_client, strict_mode=False)

        response = auth_client.get("/api/projects/nonexistent-id-99999")
        bbr.assert_404(response)
        bbr.assert_security_headers(response)
        bbr.assert_not_500(response)

    def test_invalid_input_returns_422(self, auth_client) -> None:
        """Invalid input must return 422."""
        bbr = BaseByRight(auth_client, strict_mode=False)

        response = auth_client.post("/api/projects", json={"name": ""})
        bbr.assert_422(response)
        bbr.assert_security_headers(response)
        bbr.assert_not_500(response)

    def test_idempotent_delete(self, auth_client) -> None:
        """DELETE must be idempotent: first=200, second=404."""
        bbr = BaseByRight(auth_client, strict_mode=False)

        create_resp = auth_client.post(
            "/api/v1/projects",
            json={"name": "Idempotent Delete Test"},
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
        project = create_resp.json().get("data", create_resp.json())
        pid = project.get("id") or project.get("project_id")
        assert pid is not None

        first = auth_client.delete(f"/api/v1/projects/{pid}")
        bbr.assert_200(first)

        second = auth_client.delete(f"/api/v1/projects/{pid}")
        bbr.assert_404(second)

    def test_golden_snapshot_workflow(self, auth_client, tmp_path) -> None:
        """Complete golden snapshot workflow: record -> assert."""
        bbr = BaseByRight(auth_client, strict_mode=False)
        bbr.golden.GOLDEN_DIR = str(tmp_path)

        health_resp = auth_client.get("/api/health")
        bbr.golden.record_golden("integration_health", health_resp)

        result = bbr.golden.assert_against_golden("integration_health", health_resp)
        assert result.passed, f"Golden test failed: {result.diff}"

    def test_fault_injector_resilience(self, auth_client) -> None:
        """Fault injector must not crash the test framework."""
        bbr = BaseByRight(auth_client, strict_mode=False)

        with bbr.fault_injector(db_fault="connection_lost"):
            response = auth_client.get("/api/health")
            bbr.assert_not_500(response)
            bbr.assert_status(response, {200, 503})


# ═══════════════════════════════════════════════════════════════════════════
# 8. Factory Function Test
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateBaseByRight:
    """Tests for the create_basebyright factory function."""

    def test_factory_creates_instance(self, auth_client) -> None:
        """Factory must create a BaseByRight instance."""
        bbr = create_basebyright(auth_client)
        assert isinstance(bbr, BaseByRight)

    def test_factory_passes_kwargs(self, auth_client) -> None:
        """Factory must pass kwargs to BaseByRight constructor."""
        bbr = create_basebyright(auth_client, strict_mode=False, auto_cleanup=False)
        assert bbr.strict_mode is False
        assert bbr.auto_cleanup is False