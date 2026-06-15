"""
tests/test_revit_exporter_v2.py
================================
Comprehensive test suite for:
  - fireai/core/revit_exporter.py

SAFETY CRITICAL: This module generates IFC and Revit output for fire alarm
cable routing. Incorrect exports could result in wrong conduit sizes,
missing bends, or non-compliant installations going undetected.

NFPA/NEC References:
  NFPA 72 §10.6.4 — Voltage drop verification
  NEC 760.24       — Fire alarm cable requirements
  ISO 16739        — IFC (IfcPipeSegment, IfcPipeFitting)
"""

from __future__ import annotations

import dataclasses
import json
import math

import pytest

from fireai.core.cable_router import (
    CableRoute,
    RouteWaypoint,
    RoutingSchedule,
)
from fireai.core.revit_exporter import (
    BEND_FITTING,
    CONDUIT_DIAMETER_M,
    CONDUIT_TYPE,
    FA_WORKSET,
    IFCElement,
    ReportSummary,
    RevitExporter,
    ScheduleRow,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers: Construct test fixtures without full BuildingModel/A*
# ──────────────────────────────────────────────────────────────────────────────


def _make_waypoint(x=0.0, y=0.0, z=0.0, is_bend=False) -> RouteWaypoint:
    return RouteWaypoint(
        x=x, y=y, z=z,
        grid_ix=0, grid_iy=0, grid_iz=0,
        is_bend=is_bend,
    )


def _make_route(
    route_id="R-001",
    start=(0.0, 0.0, 3.0),
    end=(10.0, 0.0, 3.0),
    wire_gauge="14",
    voltage_drop_v=1.5,
    voltage_drop_pct=6.25,
    is_compliant=True,
    num_bends=1,
    with_waypoints=True,
    with_bend=False,
    with_constraint_results=None,
) -> CableRoute:
    waypoints = ()
    if with_waypoints:
        wps = [
            _make_waypoint(start[0], start[1], start[2]),
        ]
        if with_bend:
            mid_x = (start[0] + end[0]) / 2
            wps.append(_make_waypoint(mid_x, start[1], start[2], is_bend=True))
        wps.append(_make_waypoint(end[0], end[1], end[2]))
        waypoints = tuple(wps)

    total_length = 0.0
    for i in range(1, len(waypoints)):
        dx = waypoints[i].x - waypoints[i-1].x
        dy = waypoints[i].y - waypoints[i-1].y
        dz = waypoints[i].z - waypoints[i-1].z
        total_length += math.sqrt(dx*dx + dy*dy + dz*dz)

    num_elev = 0
    decision_log = (
        (("Route R-001 computed", "NEC 760.24"),)
        if with_waypoints else ()
    )

    return CableRoute(
        route_id=route_id,
        start=start,
        end=end,
        waypoints=waypoints,
        total_length_m=total_length,
        straight_length_m=total_length,
        num_bends=num_bends,
        num_elevation_changes=num_elev,
        wire_gauge=wire_gauge,
        voltage_drop_v=voltage_drop_v,
        voltage_drop_pct=voltage_drop_pct,
        is_compliant=is_compliant,
        constraint_results=with_constraint_results,
        decision_log=decision_log,
    )


def _make_schedule(
    routes=None,
    project_name="Test Project",
    compliance_summary="ALL COMPLIANT",
) -> RoutingSchedule:
    if routes is None:
        routes = [
            _make_route("R-001", (0, 0, 3), (10, 0, 3)),
            _make_route("R-002", (10, 0, 3), (20, 0, 3), is_compliant=True),
        ]
    total_length = sum(r.total_length_m for r in routes)
    total_bends = sum(r.num_bends for r in routes)
    max_length = max((r.total_length_m for r in routes), default=0.0)
    return RoutingSchedule(
        project_name=project_name,
        routes=tuple(routes),
        total_cable_length_m=total_length,
        total_bends=total_bends,
        max_circuit_length_m=max_length,
        compliance_summary=compliance_summary,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structure Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestScheduleRow:
    def test_creation(self):
        row = ScheduleRow(
            device_id="R-001",
            from_location="(0.00, 0.00, 3.00)",
            to_location="(10.00, 0.00, 3.00)",
            length_m=10.0,
            cable_type="AWG 14 in EMT-3_4-RED",
            voltage_drop_v=1.5,
            voltage_drop_pct=6.25,
            num_bends=1,
            is_compliant=True,
        )
        assert row.device_id == "R-001"
        assert row.is_compliant is True

    def test_frozen(self):
        row = ScheduleRow(
            device_id="R-001", from_location="", to_location="",
            length_m=10.0, cable_type="AWG 14", voltage_drop_v=1.5,
            voltage_drop_pct=6.25, num_bends=0, is_compliant=True,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.device_id = "changed"

    def test_default_code_reference(self):
        row = ScheduleRow(
            device_id="R-001", from_location="", to_location="",
            length_m=10.0, cable_type="AWG 14", voltage_drop_v=1.5,
            voltage_drop_pct=6.25, num_bends=0, is_compliant=True,
        )
        assert "NFPA 72" in row.code_reference
        assert "NEC 760.24" in row.code_reference


class TestIFCElement:
    def test_creation(self):
        elem = IFCElement(
            global_id="abc123",
            ifc_class="IfcPipeSegment",
            name="FA-Cable-R-001-Seg000",
            description="FA Cable Segment",
            start_point=(0, 0, 3),
            end_point=(10, 0, 3),
            length_m=10.0,
        )
        assert elem.ifc_class == "IfcPipeSegment"
        assert elem.workset == "FA-CABLES"

    def test_frozen(self):
        elem = IFCElement(
            global_id="abc", ifc_class="IfcPipeSegment", name="test",
            description="", start_point=(0, 0, 0), end_point=(1, 0, 0),
            length_m=1.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            elem.global_id = "changed"

    def test_default_workset(self):
        elem = IFCElement(
            global_id="abc", ifc_class="IfcPipeSegment", name="test",
            description="", start_point=(0, 0, 0), end_point=(1, 0, 0),
            length_m=1.0,
        )
        assert elem.workset == FA_WORKSET

    def test_default_route_id(self):
        elem = IFCElement(
            global_id="abc", ifc_class="IfcPipeSegment", name="test",
            description="", start_point=(0, 0, 0), end_point=(1, 0, 0),
            length_m=1.0,
        )
        assert elem.route_id == ""


class TestReportSummary:
    def test_creation(self):
        summary = ReportSummary(
            project_name="Test",
            total_routes=5,
            total_cable_length_m=150.0,
            total_bends=12,
            max_circuit_length_m=50.0,
            max_voltage_drop_v=2.4,
            max_voltage_drop_pct=10.0,
            compliance_status="ALL COMPLIANT",
            constraint_violations=0,
        )
        assert summary.total_routes == 5
        assert summary.compliance_status == "ALL COMPLIANT"

    def test_frozen(self):
        summary = ReportSummary(
            project_name="Test", total_routes=5, total_cable_length_m=150.0,
            total_bends=12, max_circuit_length_m=50.0, max_voltage_drop_v=2.4,
            max_voltage_drop_pct=10.0, compliance_status="ALL COMPLIANT",
            constraint_violations=0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            summary.total_routes = 99

    def test_default_code_references(self):
        summary = ReportSummary(
            project_name="Test", total_routes=5, total_cable_length_m=150.0,
            total_bends=12, max_circuit_length_m=50.0, max_voltage_drop_v=2.4,
            max_voltage_drop_pct=10.0, compliance_status="ALL COMPLIANT",
            constraint_violations=0,
        )
        assert "NFPA 72 §10.6.4" in summary.code_references
        assert "NEC 760.24" in summary.code_references

    def test_default_computation_hash(self):
        summary = ReportSummary(
            project_name="Test", total_routes=5, total_cable_length_m=150.0,
            total_bends=12, max_circuit_length_m=50.0, max_voltage_drop_v=2.4,
            max_voltage_drop_pct=10.0, compliance_status="ALL COMPLIANT",
            constraint_violations=0,
        )
        assert summary.computation_hash == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_fa_workset(self):
        assert FA_WORKSET == "FA-CABLES"

    def test_conduit_type(self):
        assert CONDUIT_TYPE == "EMT-3_4-RED"

    def test_conduit_diameter(self):
        """¾" EMT = 19.05mm."""
        assert CONDUIT_DIAMETER_M == pytest.approx(0.01905)

    def test_bend_fitting(self):
        assert BEND_FITTING == "ConduitElbow-90"


# ═══════════════════════════════════════════════════════════════════════════════
# RevitExporter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRevitExporterInit:
    def test_default_init(self):
        exporter = RevitExporter()
        assert exporter.workset == FA_WORKSET

    def test_custom_workset(self):
        exporter = RevitExporter(workset="CUSTOM-WS")
        assert exporter.workset == "CUSTOM-WS"


class TestScheduleGeneration:
    def test_generate_schedule(self):
        exporter = RevitExporter()
        schedule = _make_schedule()
        rows = exporter.generate_schedule(schedule)
        assert len(rows) == 2
        assert rows[0].device_id == "R-001"
        assert "NFPA 72" in rows[0].code_reference

    def test_schedule_with_bend_reference(self):
        """Routes with bends should include NEC Chapter 9 reference."""
        exporter = RevitExporter()
        route = _make_route(num_bends=2)
        schedule = _make_schedule(routes=[route])
        rows = exporter.generate_schedule(schedule)
        assert "bend limit" in rows[0].code_reference.lower() or "NEC Chapter 9" in rows[0].code_reference

    def test_schedule_to_csv(self):
        exporter = RevitExporter()
        schedule = _make_schedule()
        csv_str = exporter.schedule_to_csv(schedule)
        assert "Device_ID" in csv_str
        assert "R-001" in csv_str
        assert "Code_Reference" in csv_str

    def test_empty_schedule(self):
        exporter = RevitExporter()
        schedule = _make_schedule(routes=[])
        rows = exporter.generate_schedule(schedule)
        assert len(rows) == 0


class TestIFCGeneration:
    def test_generate_ifc_elements(self):
        exporter = RevitExporter()
        route = _make_route(with_waypoints=True, with_bend=False)
        schedule = _make_schedule(routes=[route])
        elements = exporter.generate_ifc_elements(schedule)
        # Should have at least 1 IfcPipeSegment for the route
        assert len(elements) >= 1
        assert elements[0].ifc_class == "IfcPipeSegment"
        assert elements[0].workset == FA_WORKSET

    def test_ifc_with_bend_fitting(self):
        """Bend waypoints should generate IfcPipeFitting elements."""
        exporter = RevitExporter()
        route = _make_route(with_waypoints=True, with_bend=True)
        schedule = _make_schedule(routes=[route])
        elements = exporter.generate_ifc_elements(schedule)
        ifc_classes = [e.ifc_class for e in elements]
        assert "IfcPipeFitting" in ifc_classes

    def test_ifc_json(self):
        exporter = RevitExporter()
        route = _make_route(with_waypoints=True)
        schedule = _make_schedule(routes=[route])
        json_str = exporter.generate_ifc_json(schedule)
        data = json.loads(json_str)
        assert data["schema"] == "IFC4"
        assert data["workset"] == FA_WORKSET
        assert len(data["elements"]) >= 1

    def test_no_waypoints_skips_route(self):
        """Route without waypoints should be skipped."""
        exporter = RevitExporter()
        route = _make_route(with_waypoints=False)
        schedule = _make_schedule(routes=[route])
        elements = exporter.generate_ifc_elements(schedule)
        assert len(elements) == 0


class TestRevitModelLines:
    def test_generate_model_lines(self):
        exporter = RevitExporter()
        route = _make_route(with_waypoints=True)
        schedule = _make_schedule(routes=[route])
        lines = exporter.generate_revit_model_lines(schedule)
        assert len(lines) >= 1
        assert lines[0]["workset"] == FA_WORKSET
        assert lines[0]["category"] == "Conduit"

    def test_model_line_code_reference(self):
        exporter = RevitExporter()
        route = _make_route(with_waypoints=True)
        schedule = _make_schedule(routes=[route])
        lines = exporter.generate_revit_model_lines(schedule)
        assert "NEC 760.24" in lines[0]["code_reference"]


class TestReportGeneration:
    def test_generate_report(self):
        exporter = RevitExporter()
        schedule = _make_schedule()
        report = exporter.generate_report(schedule, "My Project")
        assert report.project_name == "My Project"
        assert report.total_routes == 2
        assert "NFPA 72" in " ".join(report.code_references)

    def test_generate_report_no_project_name(self):
        """Should use schedule's project_name when none provided."""
        exporter = RevitExporter()
        schedule = _make_schedule(project_name="From Schedule")
        report = exporter.generate_report(schedule)
        assert report.project_name == "From Schedule"

    def test_generate_text_report(self):
        exporter = RevitExporter()
        schedule = _make_schedule()
        text = exporter.generate_text_report(schedule, "Test Project")
        assert "FIRE ALARM CABLE ROUTING REPORT" in text
        assert "Test Project" in text
        assert "CODE REFERENCES" in text
        assert "ROUTE DETAILS" in text
        assert "Computation Hash" in text

    def test_text_report_includes_violations(self):
        """Non-compliant route should show violations in text report."""
        exporter = RevitExporter()
        route = _make_route(is_compliant=False)
        schedule = _make_schedule(routes=[route], compliance_summary="VIOLATIONS FOUND")
        text = exporter.generate_text_report(schedule)
        assert "VIOLATIONS" in text

    def test_report_code_references_includes_primary(self):
        """Report should always include primary NFPA/NEC references."""
        exporter = RevitExporter()
        schedule = _make_schedule()
        report = exporter.generate_report(schedule)
        refs = " ".join(report.code_references)
        assert "NFPA 72" in refs
        assert "NEC 760.24" in refs


class TestEdgeCases:
    def test_empty_schedule_csv(self):
        exporter = RevitExporter()
        schedule = _make_schedule(routes=[])
        csv_str = exporter.schedule_to_csv(schedule)
        assert "Device_ID" in csv_str

    def test_non_compliant_route(self):
        exporter = RevitExporter()
        route = _make_route(is_compliant=False, voltage_drop_pct=15.0)
        schedule = _make_schedule(routes=[route], compliance_summary="VIOLATIONS FOUND")
        rows = exporter.generate_schedule(schedule)
        assert rows[0].is_compliant is False

    def test_no_waypoints_ifc(self):
        exporter = RevitExporter()
        route = _make_route(with_waypoints=False)
        schedule = _make_schedule(routes=[route])
        elements = exporter.generate_ifc_elements(schedule)
        assert len(elements) == 0

    def test_custom_workset_in_ifc(self):
        exporter = RevitExporter(workset="CUSTOM-FA")
        route = _make_route(with_waypoints=True)
        schedule = _make_schedule(routes=[route])
        elements = exporter.generate_ifc_elements(schedule)
        if elements:
            assert elements[0].workset == "CUSTOM-FA"
