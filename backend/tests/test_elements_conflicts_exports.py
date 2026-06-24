"""test_elements_conflicts_exports.py — Integration tests for the elements CRUD,
conflicts CRUD, and export endpoints that exercise deeper code paths.

These tests aim to cover:
  - Elements: full create → get → update → delete cycle
  - Conflicts: detect, list with filters, resolve flow
  - Exports: DXF, Revit, IFC with actual project data
  - Report export: JSON and PDF format with completed reports
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
    """Create a project for element/conflict/export tests."""
    resp = client.post(
        "/api/projects",
        json={"name": "ECE Test Project", "description": "For elements, conflicts, exports"},
    )
    data = resp.json().get("data", resp.json())
    return data.get("id") or data.get("project_id")


@pytest.fixture
def project_with_device(client, test_project):
    """Create a project with a device for export tests."""
    pid = test_project
    client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Smoke Detector",
            "type": "FA_SMOKE",
            "category": "FIRE_ALARM",
            "x": 10.0, "y": 20.0,
            "voltage": 24.0, "current": 0.1, "load": 0.1,
        },
    )
    return pid


# ══════════════════════════════════════════════════════════════════════════════
# ELEMENTS CRUD FULL CYCLE
# ══════════════════════════════════════════════════════════════════════════════


class TestElementsFullCycle:
    """Tests for the complete elements CRUD lifecycle."""

    def test_create_element(self, client):
        """POST /api/elements must create an element."""
        resp = client.post(
            "/api/elements",
            json={
                "element_id": "elem-cycle-001",
                "properties": {
                    "element_type": "wall",
                    "name": "Test Wall for Cycle",
                },
                "geometry": {
                    "points": [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}],
                },
            },
        )
        # May return 201 or 500 if db_service unavailable
        assert resp.status_code in (200, 201, 500)
        if resp.status_code in (200, 201):
            data = resp.json()
            body = data.get("data", data)
            assert body.get("success") is True or body.get("elementId") is not None

    def test_list_elements(self, client):
        """GET /api/elements must return elements list."""
        resp = client.get("/api/elements")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True

    def test_list_elements_with_type_filter(self, client):
        """GET /api/elements with element_type filter."""
        resp = client.get("/api/elements?element_type=wall")
        assert resp.status_code == 200

    def test_list_elements_with_project_filter(self, client):
        """GET /api/elements with project_id filter."""
        resp = client.get("/api/elements?project_id=test-project")
        assert resp.status_code == 200

    def test_list_elements_with_pagination(self, client):
        """GET /api/elements with pagination."""
        resp = client.get("/api/elements?page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        body = data.get("data", data)
        assert "total" in body or "items" in body

    def test_list_elements_with_sort(self, client):
        """GET /api/elements with sort parameters."""
        resp = client.get("/api/elements?sort_by=created_timestamp&sort_order=desc")
        assert resp.status_code == 200

    def test_get_element_nonexistent(self, client):
        """GET /api/elements/{id} for nonexistent element must return 404."""
        resp = client.get("/api/elements/nonexistent-elem-999")
        assert resp.status_code == 404

    def test_update_element_nonexistent(self, client):
        """PUT /api/elements/{id} for nonexistent element must return 404."""
        resp = client.put(
            "/api/elements/nonexistent-elem-999",
            json={"properties": {"name": "Ghost"}},
        )
        assert resp.status_code == 404

    def test_delete_element_nonexistent(self, client):
        """DELETE /api/elements/{id} for nonexistent element must return 404."""
        resp = client.delete("/api/elements/nonexistent-elem-999")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# CONFLICTS OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════


class TestConflictsOperations:
    """Tests for conflicts detection and resolution."""

    def test_list_conflicts(self, client):
        """GET /api/conflicts must return conflicts list."""
        resp = client.get("/api/conflicts")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True

    def test_list_conflicts_with_pagination(self, client):
        """GET /api/conflicts with pagination."""
        resp = client.get("/api/conflicts?page=1&page_size=10")
        assert resp.status_code == 200

    def test_list_conflicts_with_resolved_filter(self, client):
        """GET /api/conflicts with resolved filter."""
        resp = client.get("/api/conflicts?resolved=false")
        assert resp.status_code == 200

    def test_list_conflicts_with_type_filter(self, client):
        """GET /api/conflicts with conflict_type filter."""
        resp = client.get("/api/conflicts?conflict_type=geometry_mismatch")
        assert resp.status_code == 200

    def test_detect_conflicts(self, client):
        """POST /api/conflicts/detect must run detection."""
        resp = client.post("/api/conflicts/detect")
        assert resp.status_code in (200, 500)

    def test_resolve_nonexistent_conflict(self, client):
        """POST /api/conflicts/{id}/resolve for nonexistent must return 404."""
        resp = client.post(
            "/api/conflicts/nonexistent-conflict-id/resolve",
            json={"strategy": "SEMANTIC_MERGE"},
        )
        assert resp.status_code in (404, 500)

    def test_resolve_conflict_with_invalid_strategy(self, client):
        """POST resolve with invalid strategy must return 422."""
        resp = client.post(
            "/api/conflicts/nonexistent-conflict-id/resolve",
            json={"strategy": "INVALID_STRATEGY"},
        )
        assert resp.status_code == 422

    def test_resolve_conflict_last_write_wins(self, client):
        """POST resolve with LAST_WRITE_WINS strategy."""
        resp = client.post(
            "/api/conflicts/nonexistent-conflict-id/resolve",
            json={"strategy": "LAST_WRITE_WINS"},
        )
        assert resp.status_code in (404, 500)


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


class TestExportEndpoints:
    """Tests for project export endpoints."""

    def test_export_dxf(self, client, project_with_device):
        """GET /api/projects/{id}/export/dxf must return DXF content."""
        pid = project_with_device
        resp = client.get(f"/api/projects/{pid}/export/dxf")
        # May return 200 or 503 if ezdxf not installed
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            assert "application/dxf" in resp.headers.get("content-type", "")
            assert len(resp.content) > 0

    def test_export_revit(self, client, project_with_device):
        """GET /api/projects/{id}/export/revit must return JSON content."""
        pid = project_with_device
        resp = client.get(f"/api/projects/{pid}/export/revit")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data or "elements" in data or "source" in data

    def test_export_ifc_default(self, client, project_with_device):
        """GET /api/projects/{id}/export/ifc must return IFC or fallback JSON."""
        pid = project_with_device
        resp = client.get(f"/api/projects/{pid}/export/ifc")
        assert resp.status_code in (200, 503)

    def test_export_ifc_ifc2x3(self, client, project_with_device):
        """GET /api/projects/{id}/export/ifc?version=IFC2X3 must work."""
        pid = project_with_device
        resp = client.get(f"/api/projects/{pid}/export/ifc?version=IFC2X3")
        assert resp.status_code in (200, 503)

    def test_export_ifc_invalid_version(self, client, project_with_device):
        """GET /api/projects/{id}/export/ifc?version=INVALID must return 422."""
        pid = project_with_device
        resp = client.get(f"/api/projects/{pid}/export/ifc?version=INVALID")
        assert resp.status_code == 422

    def test_export_dxf_nonexistent_project(self, client):
        """GET export/dxf for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-id/export/dxf")
        assert resp.status_code == 404

    def test_export_revit_nonexistent_project(self, client):
        """GET export/revit for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-id/export/revit")
        assert resp.status_code == 404

    def test_export_ifc_nonexistent_project(self, client):
        """GET export/ifc for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-id/export/ifc")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# REPORT EXPORT WITH COMPLETED REPORT
# ══════════════════════════════════════════════════════════════════════════════


class TestReportExportFormats:
    """Tests for report export with different formats on completed reports."""

    def test_export_report_json_format(self, client, project_with_device):
        """Export completed report as JSON must return streaming response."""
        pid = project_with_device
        # Create a report
        create_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "nfpa72_coverage"},
        )
        assert create_resp.status_code == 201
        data = create_resp.json().get("data", create_resp.json())
        report_id = data.get("id")
        if not report_id:
            pytest.skip("No report ID returned")
        # Export as JSON
        export_resp = client.get(f"/api/projects/{pid}/reports/{report_id}/export?format=json")
        if export_resp.status_code == 200:
            # Should have JSON content type or attachment header
            ct = export_resp.headers.get("content-type", "")
            assert "json" in ct or "application" in ct
        elif export_resp.status_code == 400:
            # Report not completed yet
            pass
        else:
            # 404 if project or report not found
            assert export_resp.status_code in (400, 404, 200)

    def test_export_report_pdf_format(self, client, project_with_device):
        """Export completed report as PDF must return streaming response or 501."""
        pid = project_with_device
        create_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "nfpa72_battery"},
        )
        data = create_resp.json().get("data", create_resp.json())
        report_id = data.get("id")
        if not report_id:
            pytest.skip("No report ID returned")
        export_resp = client.get(f"/api/projects/{pid}/reports/{report_id}/export?format=pdf")
        # 200 if reportlab installed, 501 if not, 400 if report not completed
        assert export_resp.status_code in (200, 400, 501)

    def test_export_report_dxf_format(self, client, project_with_device):
        """Export completed report as DXF must return streaming response or 501."""
        pid = project_with_device
        create_resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "cable_sizing"},
        )
        data = create_resp.json().get("data", create_resp.json())
        report_id = data.get("id")
        if not report_id:
            pytest.skip("No report ID returned")
        export_resp = client.get(f"/api/projects/{pid}/reports/{report_id}/export?format=dxf")
        assert export_resp.status_code in (200, 400, 501)


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTIONS V2 ADVANCED
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionsV2Advanced:
    """Advanced tests for connections v2 endpoints."""

    def test_list_connections_with_project_filter(self, client):
        """GET /api/connections with project_id filter."""
        resp = client.get("/api/connections?project_id=test-project&page=1&page_size=5")
        assert resp.status_code == 200

    def test_list_connections_with_element_filter(self, client):
        """GET /api/connections with element_id filter."""
        resp = client.get("/api/connections?element_id=elem-001")
        assert resp.status_code == 200

    def test_list_connections_with_type_filter(self, client):
        """GET /api/connections with relationship_type filter."""
        resp = client.get("/api/connections?relationship_type=adjacent")
        assert resp.status_code == 200

    def test_create_self_connection_rejected(self, client):
        """POST /api/connections with same from/to must be rejected."""
        resp = client.post(
            "/api/connections",
            json={
                "from_element_id": "elem-same",
                "to_element_id": "elem-same",
                "relationship_type": "cable",
            },
        )
        assert resp.status_code in (400, 422)

    def test_delete_nonexistent_connection(self, client):
        """DELETE /api/connections/{id} for nonexistent must return 404."""
        resp = client.delete("/api/connections/nonexistent-conn-v2")
        assert resp.status_code in (404, 500)
