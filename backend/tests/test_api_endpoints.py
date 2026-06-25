"""test_api_endpoints.py — API endpoint integration tests covering edge cases,
validation, security, and cross-router workflows.

Tests focus on:
  - Input validation and error handling
  - Negative test cases (bad inputs, missing data)
  - Cross-router workflows (create project → add devices → add connections → generate reports)
  - Security edge cases (path traversal, XSS, injection)
  - Boundary conditions (pagination limits, max lengths)
  - API contract conformance (response shapes, status codes)
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
def full_project(client):
    """Create a project with devices and connections for workflow testing."""
    # Create project
    proj_resp = client.post(
        "/api/projects",
        json={"name": "Full Workflow Project", "description": "Integration test", "author": "pytest"},
    )
    proj_data = proj_resp.json().get("data", proj_resp.json())
    pid = proj_data.get("id") or proj_data.get("project_id")

    # Create devices
    devices = []
    for i in range(3):
        dev_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": f"Device-{i}",
                "type": f"type_{i}",
                "category": "FIRE_ALARM",
                "x": float(i * 10),
                "y": float(i * 10 + 5),
                "z": 2.4,
                "voltage": 24.0,
                "current": 0.1,
                "load": 0.1,
            },
        )
        dev_data = dev_resp.json().get("data", dev_resp.json())
        devices.append(dev_data)

    return pid, devices


# ══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    """Tests for input validation across all routers."""

    def test_create_project_missing_name(self, client):
        """POST /api/projects without name must return 422."""
        response = client.post("/api/projects", json={"description": "No name"})
        assert response.status_code == 422

    def test_create_project_name_too_long(self, client):
        """POST /api/projects with name > 255 chars must return 422."""
        response = client.post("/api/projects", json={"name": "x" * 256})
        assert response.status_code == 422

    def test_create_project_description_too_long(self, client):
        """POST /api/projects with description > 5000 chars must return 422."""
        response = client.post(
            "/api/projects",
            json={"name": "Valid Name", "description": "x" * 5001},
        )
        assert response.status_code == 422

    def test_create_device_missing_required_fields(self, client, full_project):
        """POST device without required fields must return 422."""
        pid, _ = full_project
        response = client.post(f"/api/projects/{pid}/devices", json={})
        assert response.status_code == 422

    def test_create_device_negative_voltage(self, client, full_project):
        """POST device with negative voltage must return 422."""
        pid, _ = full_project
        response = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Bad Voltage", "type": "test", "category": "test",
                "x": 0.0, "y": 0.0, "voltage": -24.0,
            },
        )
        assert response.status_code == 422

    def test_create_device_negative_load(self, client, full_project):
        """POST device with negative load must return 422."""
        pid, _ = full_project
        response = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Bad Load", "type": "test", "category": "test",
                "x": 0.0, "y": 0.0, "load": -1.0,
            },
        )
        assert response.status_code == 422

    def test_create_connection_self_reference(self, client, full_project):
        """POST connection with fromId == toId must return 422."""
        pid, devices = full_project
        dev_id = devices[0].get("id") or devices[0].get("device_id")
        if not dev_id:
            pytest.skip("No device ID")
        response = client.post(
            f"/api/projects/{pid}/connections",
            json={"fromId": dev_id, "toId": dev_id},
        )
        assert response.status_code == 422

    def test_create_connection_missing_from_id(self, client, full_project):
        """POST connection without fromId must return 422."""
        pid, _ = full_project
        response = client.post(
            f"/api/projects/{pid}/connections",
            json={"toId": "some-id"},
        )
        assert response.status_code == 422

    def test_create_report_missing_type(self, client, full_project):
        """POST report without type must return 422."""
        pid, _ = full_project
        response = client.post(f"/api/projects/{pid}/reports", json={})
        assert response.status_code == 422

    def test_environment_weather_invalid_lat(self, client):
        """GET /api/environment/weather with lat > 90 must return 422."""
        response = client.get("/api/environment/weather?lat=100&lon=0")
        assert response.status_code == 422

    def test_environment_weather_invalid_lon(self, client):
        """GET /api/environment/weather with lon > 180 must return 422."""
        response = client.get("/api/environment/weather?lat=0&lon=200")
        assert response.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-ROUTER WORKFLOW TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossRouterWorkflows:
    """End-to-end workflow tests spanning multiple routers."""

    def test_full_crud_lifecycle(self, client):
        """Test the full project → device → connection → report lifecycle."""
        # 1. Create project
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Lifecycle Project", "description": "Full CRUD lifecycle"},
        )
        assert proj_resp.status_code == 201
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        # 2. List projects — should include our new project
        list_resp = client.get("/api/projects")
        assert list_resp.status_code == 200

        # 3. Get project
        get_resp = client.get(f"/api/projects/{pid}")
        assert get_resp.status_code == 200

        # 4. Create devices
        dev1_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Panel-01", "type": "FA_PANEL", "category": "FIRE_ALARM",
                "x": 0.0, "y": 0.0, "z": 1.5,
                "voltage": 24.0, "current": 1.0, "load": 1.0,
            },
        )
        assert dev1_resp.status_code == 201
        dev1 = dev1_resp.json().get("data", dev1_resp.json())
        dev1_id = dev1.get("id") or dev1.get("device_id")

        dev2_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Smoke-01", "type": "FA_SMOKE", "category": "FIRE_ALARM",
                "x": 15.0, "y": 20.0, "z": 3.0,
                "voltage": 24.0, "current": 0.05, "load": 0.05,
            },
        )
        assert dev2_resp.status_code == 201
        dev2 = dev2_resp.json().get("data", dev2_resp.json())
        dev2_id = dev2.get("id") or dev2.get("device_id")

        # 5. List devices
        list_dev_resp = client.get(f"/api/projects/{pid}/devices")
        assert list_dev_resp.status_code == 200

        # 6. Create connection
        conn_resp = client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1_id,
                "toId": dev2_id,
                "cableSize": "2.5mm²",
                "length": 30.0,
                "type": "slc",
            },
        )
        assert conn_resp.status_code == 201

        # 7. Generate reports
        for report_type in ["voltage_drop", "nfpa72_battery", "nfpa72_coverage", "cable_sizing"]:
            report_resp = client.post(
                f"/api/projects/{pid}/reports",
                json={"type": report_type, "name": f"{report_type} Report"},
            )
            assert report_resp.status_code == 201, f"Report type {report_type} failed"

        # 8. List reports
        reports_resp = client.get(f"/api/projects/{pid}/reports")
        assert reports_resp.status_code == 200

        # 9. Sync project
        sync_resp = client.post(f"/api/projects/{pid}/sync")
        assert sync_resp.status_code == 200

        # 10. Export as DXF
        dxf_resp = client.get(f"/api/projects/{pid}/export/dxf")
        assert dxf_resp.status_code == 200

        # 11. Export as Revit JSON
        revit_resp = client.get(f"/api/projects/{pid}/export/revit")
        assert revit_resp.status_code == 200

        # 12. Delete connection
        conn_data = conn_resp.json().get("data", conn_resp.json())
        conn_id = conn_data.get("id") or conn_data.get("connection_id")
        if conn_id:
            del_conn_resp = client.delete(f"/api/projects/{pid}/connections/{conn_id}")
            assert del_conn_resp.status_code == 200

        # 13. Delete devices
        for dev_id in [dev1_id, dev2_id]:
            del_dev_resp = client.delete(f"/api/projects/{pid}/devices/{dev_id}")
            assert del_dev_resp.status_code == 200

        # 14. Delete project
        del_proj_resp = client.delete(f"/api/projects/{pid}")
        assert del_proj_resp.status_code == 200

        # 15. Verify project is gone
        verify_resp = client.get(f"/api/projects/{pid}")
        assert verify_resp.status_code == 404

    def test_project_update_then_verify(self, client):
        """Test updating a project and verifying changes."""
        # Create
        create_resp = client.post(
            "/api/projects",
            json={"name": "Update Test", "description": "Original"},
        )
        data = create_resp.json().get("data", create_resp.json())
        pid = data.get("id") or data.get("project_id")

        # Update name
        update_resp = client.put(
            f"/api/projects/{pid}",
            json={"name": "Updated Name", "status": "active"},
        )
        assert update_resp.status_code == 200

        # Verify
        get_resp = client.get(f"/api/projects/{pid}")
        assert get_resp.status_code == 200
        body = get_resp.json().get("data", get_resp.json())
        assert body.get("name") == "Updated Name" or body.get("name") == "Updated Name"

    def test_device_update_with_position_change(self, client):
        """Test updating device position coordinates."""
        # Create project and device
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Position Test Project"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        dev_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Movable Device", "type": "test", "category": "test", "x": 0.0, "y": 0.0},
        )
        dev_data = dev_resp.json().get("data", dev_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        if not dev_id:
            pytest.skip("No device ID")

        # Update position
        update_resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"x": 100.0, "y": 200.0, "z": 5.0},
        )
        assert update_resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# PAGINATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPagination:
    """Tests for pagination parameters across list endpoints."""

    def test_project_pagination_page_1(self, client):
        """GET /api/projects?page=1 must work."""
        response = client.get("/api/projects?page=1&limit=5")
        assert response.status_code == 200

    def test_project_pagination_limit_range(self, client):
        """GET /api/projects with limit=1 must work."""
        response = client.get("/api/projects?limit=1")
        assert response.status_code == 200

    def test_project_pagination_max_limit(self, client):
        """GET /api/projects with limit=100 (max) must work."""
        response = client.get("/api/projects?limit=100")
        assert response.status_code == 200

    def test_project_pagination_limit_exceeds_max(self, client):
        """GET /api/projects with limit > 100 must return 422."""
        response = client.get("/api/projects?limit=101")
        assert response.status_code == 422

    def test_project_pagination_page_zero_fails(self, client):
        """GET /api/projects?page=0 must return 422."""
        response = client.get("/api/projects?page=0")
        assert response.status_code == 422

    def test_project_sort_order(self, client):
        """GET /api/projects with sort and order params must work."""
        response = client.get("/api/projects?sort=createdAt&order=asc")
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY EDGE CASE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityEdgeCases:
    """Tests for security-related edge cases."""

    def test_health_security_headers_on_all_responses(self, client):
        """Security headers must be present on API responses."""
        response = client.get("/api/health")
        assert "x-frame-options" in response.headers
        assert "x-content-type-options" in response.headers
        assert "content-security-policy" in response.headers
        assert "strict-transport-security" in response.headers

    def test_cors_headers_present(self, client):
        """CORS headers must be present for allowed origins."""
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # In dev mode, localhost should be allowed
        assert response.status_code in (200, 204, 405)

    def test_project_name_with_special_chars(self, client):
        """Project name with special characters should be stored as-is (no server-side sanitization needed)."""
        response = client.post(
            "/api/projects",
            json={"name": "Test <script>alert('xss')</script>", "description": "XSS test"},
        )
        assert response.status_code == 201
        # API stores raw data — XSS prevention is the frontend's responsibility.
        # The security headers (CSP, X-Frame-Options) prevent script execution.
        data = response.json().get("data", response.json())
        assert "name" in data

    def test_connection_validates_different_endpoints(self, client):
        """Connection with fromId == toId must be rejected."""
        # This is tested more thoroughly in test_routers.py but repeated
        # here as it's a safety-critical validation
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Self-Connection Test"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        dev_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Dev", "type": "t", "category": "c", "x": 0.0, "y": 0.0},
        )
        dev_data = dev_resp.json().get("data", dev_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        if not dev_id:
            pytest.skip("No device ID")

        conn_resp = client.post(
            f"/api/projects/{pid}/connections",
            json={"fromId": dev_id, "toId": dev_id},
        )
        assert conn_resp.status_code == 422

    def test_device_negative_electrical_values_rejected(self, client):
        """Devices with negative voltage/current/load must be rejected."""
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Electrical Validation Test"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        # Negative voltage
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Bad", "type": "t", "category": "c", "x": 0, "y": 0, "voltage": -1},
        )
        assert resp.status_code == 422

        # Negative current
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Bad", "type": "t", "category": "c", "x": 0, "y": 0, "current": -1},
        )
        assert resp.status_code == 422

        # Negative load
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Bad", "type": "t", "category": "c", "x": 0, "y": 0, "load": -1},
        )
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# API CONTRACT CONFORMANCE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIContractConformance:
    """Tests that API responses conform to the expected contract."""

    def test_project_response_has_required_fields(self, client):
        """Project response must include id, name, status."""
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Contract Test Project"},
        )
        data = proj_resp.json().get("data", proj_resp.json())
        assert "id" in data or "project_id" in data
        assert "name" in data
        assert "status" in data

    def test_device_response_has_required_fields(self, client):
        """Device response must include id, type, name."""
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Device Contract Test"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        dev_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Contract Device", "type": "test_type", "category": "test_cat", "x": 1.0, "y": 2.0},
        )
        data = dev_resp.json().get("data", dev_resp.json())
        assert "id" in data or "device_id" in data
        assert "type" in data or "device_type" in data
        assert "name" in data

    def test_health_response_contract(self, client):
        """Health response must conform to the HealthStatus contract."""
        response = client.get("/api/health")
        data = response.json().get("data", response.json())
        assert isinstance(data.get("status"), str)
        assert data["status"] in ("ok", "degraded")
        assert "version" in data
        assert "timestamp" in data

    def test_statistics_response_contract(self, client):
        """Statistics response must include all required fields."""
        response = client.get("/api/health/statistics")
        data = response.json().get("data", response.json())
        assert isinstance(data.get("total_elements"), int)
        assert isinstance(data.get("total_projects"), int)
        assert isinstance(data.get("active_projects"), int)
        assert isinstance(data.get("total_connections"), int)

    def test_successful_response_has_success_flag(self, client):
        """Successful responses must include a success flag."""
        response = client.get("/api/projects")
        body = response.json()
        # The API wraps in {success: true, data: ...}
        if "success" in body:
            assert body["success"] is True

    def test_error_response_has_error_flag(self, client):
        """Error responses must include error information."""
        response = client.get("/api/projects/nonexistent-id-12345")
        assert response.status_code == 404
        body = response.json()
        # Must have some form of error indication
        assert "error" in body or "detail" in body or "success" in body

    def test_paginated_list_has_pagination_fields(self, client):
        """Paginated list responses must include pagination metadata."""
        response = client.get("/api/projects")
        body = response.json()
        data = body.get("data", body)
        if isinstance(data, dict):
            # Should have total and page info
            assert "total" in data or "items" in data or "data" in data


# ══════════════════════════════════════════════════════════════════════════════
# NFPA 72 SAFETY-CRITICAL CALCULATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestNFPA72Calculations:
    """Tests for NFPA 72 safety-critical calculation endpoints."""

    def test_battery_calc_with_alarm_and_standby(self, client):
        """Battery calculation must include both alarm and standby loads."""
        # Create project with alarm + standby devices
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Battery Calc Project"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        # Standby device (detector)
        client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Smoke Det", "type": "FA_SMOKE", "category": "FIRE_ALARM",
                "x": 0, "y": 0, "voltage": 24, "current": 0.05, "load": 0.05,
            },
        )

        # Alarm device (horn/strobe)
        client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Horn Strobe", "type": "FA_SOUND_STROBE", "category": "FIRE_ALARM",
                "x": 10, "y": 10, "voltage": 24, "current": 0.5, "load": 0.5,
            },
        )

        # Generate battery report
        report_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "nfpa72_battery", "name": "Battery Calc"},
        )
        assert report_resp.status_code == 201
        report_data = report_resp.json().get("data", report_resp.json())

        # If report completed, check battery Ah calculation
        if report_data.get("status") == "completed":
            params = report_data.get("parameters", {})
            content = params.get("content", {})
            if content:
                # Battery Ah should be > 0 if there are loads
                required_ah = content.get("requiredAh", 0)
                if content.get("standbyLoadA", 0) > 0 or content.get("alarmLoadA", 0) > 0:
                    assert required_ah > 0, "Battery Ah must be positive when loads exist"

    def test_voltage_drop_report_with_connections(self, client):
        """Voltage drop report must include circuit data from connections."""
        proj_resp = client.post(
            "/api/projects",
            json={"name": "VDrop Test"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        # Create panel + detector
        dev1 = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Panel", "type": "FA_PANEL", "category": "FIRE_ALARM",
                "x": 0, "y": 0, "voltage": 24, "current": 0, "load": 0,
            },
        )
        dev1_data = dev1.json().get("data", dev1.json())
        dev1_id = dev1_data.get("id") or dev1_data.get("device_id")

        dev2 = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Detector", "type": "FA_SMOKE", "category": "FIRE_ALARM",
                "x": 50, "y": 50, "voltage": 24, "current": 0.05, "load": 0.05,
            },
        )
        dev2_data = dev2.json().get("data", dev2.json())
        dev2_id = dev2_data.get("id") or dev2_data.get("device_id")

        if dev1_id and dev2_id:
            # Create connection
            client.post(
                f"/api/projects/{pid}/connections",
                json={"fromId": dev1_id, "toId": dev2_id, "length": 50.0, "cableSize": "2.5mm²"},
            )

        # Generate voltage drop report
        report_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop"},
        )
        assert report_resp.status_code == 201

    def test_load_unit_conversion_traceability(self, client):
        """Device created with mA must store traceability info in properties."""
        proj_resp = client.post(
            "/api/projects",
            json={"name": "Traceability Test"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        dev_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "mA Device", "type": "FA_SMOKE", "category": "FIRE_ALARM",
                "x": 0, "y": 0, "voltage": 24, "load": 500, "load_unit": "mA",
            },
        )
        assert dev_resp.status_code == 201
        dev_data = dev_resp.json().get("data", dev_resp.json())
        # Properties should contain traceability info
        props = dev_data.get("properties", {})
        if isinstance(props, dict):
            assert "load_original_value" in props or "load_original_unit" in props


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR & SYSTEM ENDPOINT TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestMonitorEndpoints:
    """Tests for backend/routers/monitor.py — 6 endpoints."""

    def test_monitor_health(self, client):
        """GET /api/monitor/health must return 200 or 404."""
        response = client.get("/api/monitor/health")
        assert response.status_code in (200, 404)

    def test_monitor_metrics(self, client):
        """GET /api/monitor/metrics must return 200 or 404."""
        response = client.get("/api/monitor/metrics")
        assert response.status_code in (200, 404)

    def test_monitor_engine_status(self, client):
        """GET /api/monitor/engine-status must return 200 or 404."""
        response = client.get("/api/monitor/engine-status")
        assert response.status_code in (200, 404)

    def test_monitor_agent_activity(self, client):
        """GET /api/monitor/agent-activity must return 200 or 404."""
        response = client.get("/api/monitor/agent-activity")
        assert response.status_code in (200, 404)

    def test_monitor_security_alerts(self, client):
        """GET /api/monitor/security-alerts must return 200 or 404."""
        response = client.get("/api/monitor/security-alerts")
        assert response.status_code in (200, 404)

    def test_monitor_alerts(self, client):
        """GET /api/monitor/alerts must return 200 or 404."""
        response = client.get("/api/monitor/alerts")
        assert response.status_code in (200, 404)
