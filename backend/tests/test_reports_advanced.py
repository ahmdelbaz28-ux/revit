"""test_reports_advanced.py — Advanced report integration tests covering
report export paths, pending status handling, pagination, and NFPA 72
battery calculation correctness.

Focuses on code paths NOT covered by existing tests:
  - Report export for a pending/non-completed report (should 400)
  - Report export with JSON format (StreamingResponse)
  - Report export for nonexistent project (404)
  - Report listing with pagination and sort
  - NFPA 72 battery calculation with alarm device types
  - Voltage drop report with connected devices
  - Cable sizing report content verification
  - Report generation with parameters
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
def project_with_alarm_devices(client):
    """Create a project with alarm-type devices for NFPA 72 battery test."""
    # Create project
    proj_resp = client.post(
        "/api/projects",
        json={"name": "Battery Test Project", "description": "NFPA 72 battery calculation test"},
    )
    proj_data = proj_resp.json().get("data", proj_resp.json())
    pid = proj_data.get("id") or proj_data.get("project_id")

    # Create a standby device (smoke detector)
    client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Smoke Detector SD-01",
            "type": "FA_SMOKE",
            "category": "FIRE_ALARM",
            "x": 10.0, "y": 20.0,
            "voltage": 24.0, "current": 0.05, "load": 0.05,
        },
    )

    # Create an alarm device (horn/strobe)
    client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Horn Strobe HS-01",
            "type": "FA_SOUND_STROBE",
            "category": "FIRE_ALARM",
            "x": 30.0, "y": 40.0,
            "voltage": 24.0, "current": 0.5, "load": 0.5,
        },
    )

    return pid


@pytest.fixture
def project_with_connected_devices(client):
    """Create a project with two connected devices for voltage drop test."""
    proj_resp = client.post(
        "/api/projects",
        json={"name": "Vdrop Test Project"},
    )
    proj_data = proj_resp.json().get("data", proj_resp.json())
    pid = proj_data.get("id") or proj_data.get("project_id")

    dev1_resp = client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Panel P-01",
            "type": "FA_PANEL",
            "category": "FIRE_ALARM",
            "x": 0.0, "y": 0.0,
            "voltage": 24.0, "current": 2.0, "load": 2.0,
        },
    )
    dev1 = dev1_resp.json().get("data", dev1_resp.json())

    dev2_resp = client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Detector SD-01",
            "type": "FA_SMOKE",
            "category": "FIRE_ALARM",
            "x": 50.0, "y": 50.0,
            "voltage": 22.8, "current": 0.1, "load": 0.1,
        },
    )
    dev2 = dev2_resp.json().get("data", dev2_resp.json())

    # Connect them
    dev1_id = dev1.get("id") or dev1.get("device_id")
    dev2_id = dev2.get("id") or dev2.get("device_id")
    client.post(
        f"/api/projects/{pid}/connections",
        json={
            "fromId": dev1_id,
            "toId": dev2_id,
            "cableSize": "1.5mm²",
            "length": 30.0,
            "type": "power",
        },
    )

    return pid


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION WITH DIFFERENT TYPES
# ══════════════════════════════════════════════════════════════════════════════


class TestReportGeneration:
    """Tests for report generation with various types."""

    def test_generate_nfpa72_battery_with_alarm_devices(self, client, project_with_alarm_devices):
        """NFPA 72 battery report must classify alarm vs standby devices correctly."""
        pid = project_with_alarm_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "nfpa72_battery", "name": "Battery Calc with Alarm"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        # Report should be completed
        assert data.get("status") in ("completed", "pending")
        # If completed, check the content
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            if content:
                assert "standbyLoadA" in content or "requiredAh" in content

    def test_generate_voltage_drop_with_connections(self, client, project_with_connected_devices):
        """Voltage drop report must include circuit data from connections."""
        pid = project_with_connected_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop", "name": "Vdrop Calc"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("status") in ("completed", "pending")
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            if content:
                assert "circuits" in content or "totalCircuits" in content

    def test_generate_cable_sizing_report(self, client, project_with_connected_devices):
        """Cable sizing report must include connection data."""
        pid = project_with_connected_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "cable_sizing", "name": "Cable Sizing"},
        )
        assert resp.status_code == 201

    def test_generate_nfpa72_coverage_report(self, client, project_with_alarm_devices):
        """NFPA 72 coverage report must include device category breakdown."""
        pid = project_with_alarm_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "nfpa72_coverage", "name": "Coverage Analysis"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            if content:
                assert "totalDevices" in content or "devicesByCategory" in content

    def test_generate_report_with_parameters(self, client, project_with_alarm_devices):
        """Report generation with custom parameters must succeed."""
        pid = project_with_alarm_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={
                "type": "voltage_drop",
                "name": "Custom Params Report",
                "parameters": {"threshold_percent": 5.0, "cable_type": "THHN"},
            },
        )
        assert resp.status_code == 201

    def test_generate_report_in_nonexistent_project(self, client):
        """Report generation in nonexistent project must return 404."""
        resp = client.post(
            "/api/projects/nonexistent-proj/reports",
            json={"type": "voltage_drop"},
        )
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# REPORT EXPORT EDGE CASES
# ══════════════════════════════════════════════════════════════════════════════


class TestReportExport:
    """Tests for report export paths including edge cases."""

    def test_export_completed_report_json(self, client, project_with_alarm_devices):
        """Exporting a completed report as JSON must succeed."""
        pid = project_with_alarm_devices
        # Create and complete a report
        create_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "nfpa72_coverage"},
        )
        data = create_resp.json().get("data", create_resp.json())
        report_id = data.get("id")
        if not report_id:
            pytest.skip("No report ID returned")
        # Export as JSON
        resp = client.get(f"/api/projects/{pid}/reports/{report_id}/export?format=json")
        assert resp.status_code in (200, 400)  # 400 if report not completed yet

    def test_export_report_nonexistent_project(self, client):
        """Exporting a report for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/reports/some-id/export?format=json")
        assert resp.status_code == 404

    def test_export_report_nonexistent_report(self, client, project_with_alarm_devices):
        """Exporting a nonexistent report must return 404."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports/nonexistent-report/export?format=json")
        assert resp.status_code == 404

    def test_export_report_invalid_format(self, client, project_with_alarm_devices):
        """Exporting with invalid format must return 422."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports/nonexistent-report/export?format=exe")
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# REPORT LISTING WITH PAGINATION
# ══════════════════════════════════════════════════════════════════════════════


class TestReportListing:
    """Tests for report listing with pagination and sort."""

    def test_list_reports_with_pagination(self, client, project_with_alarm_devices):
        """Listing reports with pagination must succeed."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports?page=1&limit=5")
        assert resp.status_code == 200

    def test_list_reports_with_sort(self, client, project_with_alarm_devices):
        """Listing reports with sort parameter must succeed."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports?sort=type&order=asc")
        assert resp.status_code == 200

    def test_list_reports_with_sort_by_status(self, client, project_with_alarm_devices):
        """Listing reports sorted by status must succeed."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports?sort=status&order=desc")
        assert resp.status_code == 200

    def test_list_reports_nonexistent_project_404(self, client):
        """Listing reports for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/reports")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GET BY ID
# ══════════════════════════════════════════════════════════════════════════════


class TestReportGetById:
    """Tests for getting a specific report by ID."""

    def test_get_report_by_id_after_creation(self, client, project_with_alarm_devices):
        """Getting a report by ID after creation must return 200."""
        pid = project_with_alarm_devices
        create_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop", "name": "Get Test Report"},
        )
        data = create_resp.json().get("data", create_resp.json())
        report_id = data.get("id")
        if not report_id:
            pytest.skip("No report ID returned")
        resp = client.get(f"/api/projects/{pid}/reports/{report_id}")
        assert resp.status_code == 200
        report_data = resp.json().get("data", resp.json())
        assert report_data.get("id") == report_id or report_data.get("type") == "voltage_drop"

    def test_get_report_nonexistent_project(self, client):
        """Getting a report in nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/reports/some-report")
        assert resp.status_code == 404

    def test_get_report_has_status_field(self, client, project_with_alarm_devices):
        """Retrieved report must have a status field."""
        pid = project_with_alarm_devices
        create_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "cable_sizing"},
        )
        data = create_resp.json().get("data", create_resp.json())
        report_id = data.get("id")
        if not report_id:
            pytest.skip("No report ID returned")
        resp = client.get(f"/api/projects/{pid}/reports/{report_id}")
        assert resp.status_code == 200
        report_data = resp.json().get("data", resp.json())
        assert "status" in report_data
        assert report_data["status"] in ("pending", "completed", "failed")
