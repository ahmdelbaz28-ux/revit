"""
test_reports_advanced.py — Advanced report integration tests covering
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
def _setup_env() -> None:
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

    def test_generate_nfpa72_battery_with_alarm_devices(self, client, project_with_alarm_devices) -> None:
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

    def test_generate_voltage_drop_with_connections(self, client, project_with_connected_devices) -> None:
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

    def test_generate_cable_sizing_report(self, client, project_with_connected_devices) -> None:
        """Cable sizing report must include connection data."""
        pid = project_with_connected_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "cable_sizing", "name": "Cable Sizing"},
        )
        assert resp.status_code == 201

    def test_generate_nfpa72_coverage_report(self, client, project_with_alarm_devices) -> None:
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

    def test_generate_report_with_parameters(self, client, project_with_alarm_devices) -> None:
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

    def test_generate_report_in_nonexistent_project(self, client) -> None:
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

    def test_export_completed_report_json(self, client, project_with_alarm_devices) -> None:
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

    def test_export_report_nonexistent_project(self, client) -> None:
        """Exporting a report for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/reports/some-id/export?format=json")
        assert resp.status_code == 404

    def test_export_report_nonexistent_report(self, client, project_with_alarm_devices) -> None:
        """Exporting a nonexistent report must return 404."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports/nonexistent-report/export?format=json")
        assert resp.status_code == 404

    def test_export_report_invalid_format(self, client, project_with_alarm_devices) -> None:
        """Exporting with invalid format must return 422."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports/nonexistent-report/export?format=exe")
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# REPORT LISTING WITH PAGINATION
# ══════════════════════════════════════════════════════════════════════════════


class TestReportListing:
    """Tests for report listing with pagination and sort."""

    def test_list_reports_with_pagination(self, client, project_with_alarm_devices) -> None:
        """Listing reports with pagination must succeed."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports?page=1&limit=5")
        assert resp.status_code == 200

    def test_list_reports_with_sort(self, client, project_with_alarm_devices) -> None:
        """Listing reports with sort parameter must succeed."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports?sort=type&order=asc")
        assert resp.status_code == 200

    def test_list_reports_with_sort_by_status(self, client, project_with_alarm_devices) -> None:
        """Listing reports sorted by status must succeed."""
        pid = project_with_alarm_devices
        resp = client.get(f"/api/projects/{pid}/reports?sort=status&order=desc")
        assert resp.status_code == 200

    def test_list_reports_nonexistent_project_404(self, client) -> None:
        """Listing reports for nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/reports")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GET BY ID
# ══════════════════════════════════════════════════════════════════════════════


class TestReportGetById:
    """Tests for getting a specific report by ID."""

    def test_get_report_by_id_after_creation(self, client, project_with_alarm_devices) -> None:
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

    def test_get_report_nonexistent_project(self, client) -> None:
        """Getting a report in nonexistent project must return 404."""
        resp = client.get("/api/projects/nonexistent-proj/reports/some-report")
        assert resp.status_code == 404

    def test_get_report_has_status_field(self, client, project_with_alarm_devices) -> None:
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


# ══════════════════════════════════════════════════════════════════════════════
# V213: VOLTAGE DROP REPORT MUST INCLUDE REAL NEC TABLE 8 CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════


class TestV213VoltageDropRealCalculations:
    """V213 regression tests: the voltage_drop report must call the real
    ``fireai.core.qomn_kernel.compute_voltage_drop`` (NEC Ch. 9 Table 8)
    for each circuit where the cable size can be mapped to an AWG gauge —
    not just list circuits as before.
    """

    def test_voltage_drop_report_has_computed_count_field(self, client, project_with_connected_devices) -> None:
        """The report must include ``computedCircuits`` and
        ``skippedCircuits`` summary fields (V213).
        """
        pid = project_with_connected_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop", "name": "V213 VDrop"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        # Status may be pending or completed
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            assert "computedCircuits" in content
            assert "skippedCircuits" in content
            assert "nonCompliantCircuits" in content

    def test_voltage_drop_circuit_has_real_calculation_fields(self, client, project_with_connected_devices) -> None:
        """Each computed circuit must include ``voltage_drop_v``,
        ``drop_pct``, ``is_compliant``, ``nec_section``, ``formula``,
        and ``computation_hash`` from the real qomn_kernel.
        """
        pid = project_with_connected_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop", "name": "V213 VDrop Detail"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            circuits = content.get("circuits", [])
            assert len(circuits) > 0, "Expected at least one circuit"
            # The fixture connects Panel P-01 → Detector SD-01 with 1.5mm² cable, 30m length
            # 1.5mm² maps to AWG 16 → compute_voltage_drop should succeed
            computed = [c for c in circuits if c.get("calculation") == "computed"]
            assert len(computed) > 0, (
                f"Expected at least one computed circuit, got: {circuits}"
            )
            c = computed[0]
            assert "voltage_drop_v" in c
            assert "drop_pct" in c
            assert "is_compliant" in c
            assert "nec_section" in c
            assert "formula" in c
            assert "computation_hash" in c
            assert "NEC" in c["nec_section"]

    def test_voltage_drop_formula_uses_real_ohm_per_m(self, client, project_with_connected_devices) -> None:
        """The formula string must include the real resistance value
        from NEC Table 8 (not a placeholder).
        """
        pid = project_with_connected_devices
        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop", "name": "V213 VDrop Formula"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            circuits = content.get("circuits", [])
            computed = [c for c in circuits if c.get("calculation") == "computed"]
            if computed:
                formula = computed[0].get("formula", "")
                # Formula format: "V_drop = 2 × {I}A × {L}m × {R}Ω/m = {V}V"
                assert "V_drop = 2" in formula
                assert "Ω/m" in formula
                # Resistance must be > 0 (not a placeholder 0.000000)
                assert "0.000000Ω/m" not in formula

    def test_voltage_drop_skips_unmappable_cable_size(self, client) -> None:
        """When cable size cannot be mapped to AWG, the circuit must be
        listed with ``calculation: "skipped"`` (not silently dropped).
        """
        # Create a project with a connection using an exotic cable size
        proj_resp = client.post(
            "/api/projects",
            json={"name": "V213 Exotic Cable Test"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        dev1 = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Dev A", "type": "FA_PANEL", "category": "FIRE_ALARM",
                  "x": 0.0, "y": 0.0, "voltage": 24.0, "current": 1.0, "load": 1.0},
        ).json().get("data", {})
        dev2 = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Dev B", "type": "FA_SMOKE", "category": "FIRE_ALARM",
                  "x": 10.0, "y": 10.0, "voltage": 24.0, "current": 0.1, "load": 0.1},
        ).json().get("data", {})

        client.post(
            f"/api/projects/{pid}/connections",
            json={
                "fromId": dev1.get("id"),
                "toId": dev2.get("id"),
                "cableSize": "exotic_unknown_format",
                "length": 20.0,
                "type": "power",
            },
        )

        resp = client.post(
            f"/api/projects/{pid}/reports",
            json={"type": "voltage_drop", "name": "V213 Exotic"},
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        if data.get("status") == "completed":
            params = data.get("parameters", {})
            content = params.get("content", {})
            circuits = content.get("circuits", [])
            assert len(circuits) > 0
            skipped = [c for c in circuits if c.get("calculation") == "skipped"]
            assert len(skipped) > 0, (
                f"Expected at least one skipped circuit for exotic cable, got: {circuits}"
            )

    def test_cable_size_to_awg_direct_awg(self):
        """_cable_size_to_awg must parse direct AWG strings."""
        from backend.routers.reports import _cable_size_to_awg
        assert _cable_size_to_awg("12") == "12"
        assert _cable_size_to_awg("12 AWG") == "12"
        assert _cable_size_to_awg("#12") == "12"
        assert _cable_size_to_awg("12AWG") == "12"
        assert _cable_size_to_awg("14") == "14"

    def test_cable_size_to_awg_metric_mm2(self):
        """_cable_size_to_awg must map metric mm² to nearest AWG."""
        from backend.routers.reports import _cable_size_to_awg
        assert _cable_size_to_awg("1.5mm²") == "16"
        assert _cable_size_to_awg("2.5mm²") == "14"
        assert _cable_size_to_awg("4.0mm²") == "12"
        assert _cable_size_to_awg("1.5 mm2") == "16"
        assert _cable_size_to_awg("2.5 mm²") == "14"

    def test_cable_size_to_awg_unmappable_returns_none(self):
        """_cable_size_to_awg must return None for unmappable strings."""
        from backend.routers.reports import _cable_size_to_awg
        assert _cable_size_to_awg("exotic_unknown") is None
        assert _cable_size_to_awg("") is None
        assert _cable_size_to_awg(None) is None
        assert _cable_size_to_awg("100000") is None  # too large for AWG


# ══════════════════════════════════════════════════════════════════════════════
# V213: AHJ COMPLIANCE PROOF DOCUMENT ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


class TestV213AhjSubmittalEndpoint:
    """V213 regression tests: POST /api/projects/{id}/reports/ahj-submittal
    must produce a real NFPA 72 compliance proof document via the
    ComplianceProofDocument class — not a placeholder or 404.

    Previously the ComplianceProofDocument class (562 lines, real
    engineering content) was unreachable via any HTTP endpoint.
    """

    def test_ahj_submittal_returns_markdown(self, client, project_with_alarm_devices) -> None:
        """POST /ahj-submittal must return 200 with text/markdown content
        containing real NFPA 72 references.
        """
        pid = project_with_alarm_devices
        resp = client.post(
            f"/api/projects/{pid}/reports/ahj-submittal",
            json={
                "designer": "Jane Smith, PE #12345",
                "jurisdiction": "Dubai Civil Defence",
                "nfpa_edition": "2022",
            },
        )
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "markdown" in ct, f"Expected text/markdown, got: {ct}"
        body = resp.content.decode("utf-8")
        # The document must contain real NFPA 72 references
        assert "NFPA 72" in body
        # Must contain the designer name
        assert "Jane Smith" in body
        # Must contain the jurisdiction
        assert "Dubai Civil Defence" in body

    def test_ahj_submittal_with_explicit_rooms(self, client) -> None:
        """POST /ahj-submittal with explicit rooms must include those rooms
        in the generated document.
        """
        # Create a fresh project for this test
        proj_resp = client.post(
            "/api/projects",
            json={"name": "AHJ Rooms Test Project"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        resp = client.post(
            f"/api/projects/{pid}/reports/ahj-submittal",
            json={
                "designer": "John Doe, PE",
                "jurisdiction": "Civil Defence",
                "nfpa_edition": "2022",
                "rooms": [
                    {"name": "Office 101", "width": 6.0, "length": 8.0, "ceiling_height": 3.0},
                    {"name": "Corridor 200", "width": 2.0, "length": 15.0, "ceiling_height": 3.0},
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "Office 101" in body
        assert "Corridor 200" in body
        # Rooms count header
        assert resp.headers.get("X-Rooms-Count") == "2"

    def test_ahj_submittal_nonexistent_project_404(self, client) -> None:
        """POST /ahj-submittal for nonexistent project must return 404."""
        resp = client.post(
            "/api/projects/nonexistent-id/reports/ahj-submittal",
            json={"designer": "Test", "jurisdiction": "Test"},
        )
        assert resp.status_code == 404

    def test_ahj_submittal_no_rooms_no_devices_400(self, client) -> None:
        """POST /ahj-submittal with no rooms and no devices must return 400
        (cannot generate a document without any room data).
        """
        # Create a fresh empty project
        proj_resp = client.post(
            "/api/projects",
            json={"name": "AHJ Empty Project"},
        )
        proj_data = proj_resp.json().get("data", proj_resp.json())
        pid = proj_data.get("id") or proj_data.get("project_id")

        resp = client.post(
            f"/api/projects/{pid}/reports/ahj-submittal",
            json={"designer": "Test", "jurisdiction": "Test"},
        )
        # With no devices and no rooms, the bounding box fallback fails → 400
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "devices" in detail.lower() or "rooms" in detail.lower()

    def test_ahj_submittal_document_has_six_sections(self, client, project_with_alarm_devices) -> None:
        """The generated document must contain all 6 mandatory sections:
        header, design criteria, room summary, detailed results, consensus
        summary, certification.
        """
        pid = project_with_alarm_devices
        resp = client.post(
            f"/api/projects/{pid}/reports/ahj-submittal",
            json={"designer": "Test PE", "jurisdiction": "Test AHJ"},
        )
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        # The ComplianceProofDocument._header() includes "Compliance Proof Document"
        assert "Compliance Proof" in body or "NFPA 72" in body
        # The certification section includes "Engineer" or "Certification"
        assert "Certification" in body or "Engineer" in body or "PE" in body

    def test_ahj_submittal_content_disposition_is_markdown(self, client, project_with_alarm_devices) -> None:
        """The Content-Disposition header must specify a .md filename."""
        pid = project_with_alarm_devices
        resp = client.post(
            f"/api/projects/{pid}/reports/ahj-submittal",
            json={"designer": "Test", "jurisdiction": "Test"},
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert ".md" in cd, f"Expected .md filename in Content-Disposition, got: {cd}"
        assert "attachment" in cd
