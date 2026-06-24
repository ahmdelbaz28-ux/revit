"""fireai.core.revit_exporter — IFC & Revit Output Generation
===========================================================

Generates output files from cable routing results:

1. IFC Output:
   - IfcPipeSegment for straight cable runs
   - IfcPipeFitting for 90° elbows
   - Placed on dedicated workset "FA-CABLES"

2. Revit Output:
   - Model Lines on dedicated workset "FA-CABLES"
   - Cable tray / conduit family instances

3. Schedule:
   - Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop

4. Report:
   - Total cable length, number of bends, max circuit length
   - Compliance summary
   - Every decision traceable to code reference

Standards:
   - ISO 16739 — IFC (IfcPipeSegment, IfcPipeFitting)
   - NEC 760.24 — Fire alarm cable requirements
   - NFPA 72 §10.6.4 — Voltage drop verification

QOMN-FIRE Principles:
   - Every output element tagged with code reference
   - Deterministic: same routes → same output, always
   - No approximations in geometry or calculations
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from fireai.core.cable_router import RoutingSchedule

# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ScheduleRow:
    """Single row in the cable schedule.

    Attributes:
        device_id: Route/circuit identifier.
        from_location: Start point description.
        to_location: End point description.
        length_m: Cable length in meters.
        cable_type: Wire gauge / cable type string.
        voltage_drop_v: Voltage drop in volts.
        voltage_drop_pct: Voltage drop as percentage.
        num_bends: Number of 90° bends.
        is_compliant: Whether this route meets all constraints.
        code_reference: Applicable code sections.

    """

    device_id: str
    from_location: str
    to_location: str
    length_m: float
    cable_type: str
    voltage_drop_v: float
    voltage_drop_pct: float
    num_bends: int
    is_compliant: bool
    code_reference: str = "NFPA 72 §10.6.4, NEC 760.24"


@dataclass(frozen=True)
class IFCElement:
    """IFC element for cable output.

    Attributes:
        global_id: IFC GlobalId (UUID format).
        ifc_class: IFC class name (IfcPipeSegment or IfcPipeFitting).
        name: Element name.
        description: Element description with code reference.
        start_point: (x, y, z) start point in meters.
        end_point: (x, y, z) end point in meters.
        length_m: Element length in meters.
        workset: Dedicated workset name ("FA-CABLES").
        route_id: Parent route identifier.

    """

    global_id: str
    ifc_class: str
    name: str
    description: str
    start_point: Tuple[float, float, float]
    end_point: Tuple[float, float, float]
    length_m: float
    workset: str = "FA-CABLES"
    route_id: str = ""


@dataclass(frozen=True)
class ReportSummary:
    """Summary report for cable routing.

    Attributes:
        project_name: Project name.
        total_routes: Number of cable routes.
        total_cable_length_m: Total cable length in meters.
        total_bends: Total number of 90° bends.
        max_circuit_length_m: Longest single circuit.
        max_voltage_drop_v: Maximum voltage drop.
        max_voltage_drop_pct: Maximum voltage drop percentage.
        compliance_status: Overall compliance status.
        constraint_violations: Number of constraint violations.
        code_references: All code sections referenced.
        computation_hash: SHA-256 hash for verification.

    """

    project_name: str
    total_routes: int
    total_cable_length_m: float
    total_bends: int
    max_circuit_length_m: float
    max_voltage_drop_v: float
    max_voltage_drop_pct: float
    compliance_status: str
    constraint_violations: int
    code_references: Tuple[str, ...] = (
        "NFPA 72 §10.6.4",
        "NFPA 72 §23.6.2",
        "NEC 760.24",
        "NEC 760.24(A)",
        "NEC Chapter 9, Table 8",
    )
    computation_hash: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# REVIT EXPORTER
# ═══════════════════════════════════════════════════════════════════════════════

# IFC Workset name per project specification
FA_WORKSET = "FA-CABLES"

# Conduit properties per project spec
CONDUIT_TYPE = "EMT-3_4-RED"
CONDUIT_DIAMETER_M = 0.01905  # ¾" EMT = 19.05mm

# Bend fitting name
BEND_FITTING = "ConduitElbow-90"


class RevitExporter:
    """Export cable routing results to IFC, Revit, Schedule, and Report.

    Every output element is tagged with:
    - IFC class (IfcPipeSegment / IfcPipeFitting)
    - Code reference (NEC/NFPA section)
    - Workset assignment (FA-CABLES)
    - Route identifier for traceability

    Example usage::

        exporter = RevitExporter()
        schedule = exporter.generate_schedule(routing_result)
        ifc_elements = exporter.generate_ifc_elements(routing_result)
        report = exporter.generate_report(routing_result, "My Project")
    """

    @property
    def workset(self) -> str:
        """Public workset name. System req 4: always FA-CABLES."""
        return self._workset

    def __init__(self, workset: str = FA_WORKSET):
        """Initialize the exporter.

        Args:
            workset: Dedicated workset name for fire alarm cables.

        """
        self._workset = workset

    # ─── Schedule Generation ─────────────────────────────────────────────

    def generate_schedule(
        self,
        schedule: RoutingSchedule,
    ) -> List[ScheduleRow]:
        """Generate cable schedule from routing results.

        Schedule format per specification:
          Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop

        Args:
            schedule: RoutingSchedule with all routes.

        Returns:
            List of ScheduleRow objects.

        """
        rows = []

        for route in schedule.routes:
            # Format location strings
            from_loc = f"({route.start[0]:.2f}, {route.start[1]:.2f}, {route.start[2]:.2f})"
            to_loc = f"({route.end[0]:.2f}, {route.end[1]:.2f}, {route.end[2]:.2f})"

            # Compile code references
            code_refs = ["NFPA 72 §10.6.4", "NEC 760.24"]
            if route.num_bends > 0:
                code_refs.append("NEC Chapter 9 (bend limit)")
            if route.num_elevation_changes > 0:
                code_refs.append("NEC 760.24 (vertical routing)")

            rows.append(
                ScheduleRow(
                    device_id=route.route_id,
                    from_location=from_loc,
                    to_location=to_loc,
                    length_m=route.total_length_m,
                    cable_type=f"AWG {route.wire_gauge if isinstance(route.wire_gauge, str) else route.wire_gauge.awg_value} in {CONDUIT_TYPE}",
                    voltage_drop_v=route.voltage_drop_v,
                    voltage_drop_pct=route.voltage_drop_pct,
                    num_bends=route.num_bends,
                    is_compliant=route.is_compliant,
                    code_reference=", ".join(code_refs),
                )
            )

        return rows

    def schedule_to_csv(
        self,
        schedule: RoutingSchedule,
    ) -> str:
        """Export cable schedule as CSV string.

        Args:
            schedule: RoutingSchedule with all routes.

        Returns:
            CSV-formatted string.

        """
        rows = self.generate_schedule(schedule)
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "Device_ID",
                "From_Location",
                "To_Location",
                "Length_m",
                "Cable_Type",
                "Voltage_Drop_V",
                "Voltage_Drop_Pct",
                "Num_Bends",
                "Compliant",
                "Code_Reference",
            ]
        )

        # Data rows
        for row in rows:
            writer.writerow(
                [
                    row.device_id,
                    row.from_location,
                    row.to_location,
                    f"{row.length_m:.2f}",
                    row.cable_type,
                    f"{row.voltage_drop_v:.4f}",
                    f"{row.voltage_drop_pct:.2f}",
                    row.num_bends,
                    "YES" if row.is_compliant else "NO",
                    row.code_reference,
                ]
            )

        return output.getvalue()

    # ─── IFC Element Generation ──────────────────────────────────────────

    def generate_ifc_elements(
        self,
        schedule: RoutingSchedule,
    ) -> List[IFCElement]:
        """Generate IFC elements from cable routes.

        Output format per specification:
          - IfcPipeSegment for straight runs
          - IfcPipeFitting for elbows (90° bends)
          - All on workset "FA-CABLES"

        Args:
            schedule: RoutingSchedule with all routes.

        Returns:
            List of IFCElement objects.

        """
        elements = []

        for route in schedule.routes:
            if not route.waypoints or len(route.waypoints) < 2:
                continue

            for i in range(len(route.waypoints) - 1):
                wp_start = route.waypoints[i]
                wp_end = route.waypoints[i + 1]

                # Calculate segment length
                dx = wp_end.x - wp_start.x
                dy = wp_end.y - wp_start.y
                dz = wp_end.z - wp_start.z
                seg_length = math.sqrt(dx * dx + dy * dy + dz * dz)

                if seg_length < 0.001:
                    continue  # Skip zero-length segments

                # Generate unique ID
                seg_id = f"{route.route_id}-S{i:03d}"
                seg_hash = hashlib.sha256(seg_id.encode()).hexdigest()[:32]

                # Straight segment → IfcPipeSegment
                description = (
                    f"FA Cable Segment: AWG {route.wire_gauge if isinstance(route.wire_gauge, str) else route.wire_gauge.awg_value} in "
                    f"{CONDUIT_TYPE}, L={seg_length:.3f}m. "
                    f"Per NEC 760.24, NFPA 72 §10.6.4"
                )

                elements.append(
                    IFCElement(
                        global_id=seg_hash,
                        ifc_class="IfcPipeSegment",
                        name=f"FA-Cable-{route.route_id}-Seg{i:03d}",
                        description=description,
                        start_point=(wp_start.x, wp_start.y, wp_start.z),
                        end_point=(wp_end.x, wp_end.y, wp_end.z),
                        length_m=round(seg_length, 4),
                        workset=self._workset,
                        route_id=route.route_id,
                    )
                )

                # If next waypoint is a bend, add IfcPipeFitting
                if wp_end.is_bend:
                    bend_id = f"{route.route_id}-F{i:03d}"
                    bend_hash = hashlib.sha256(bend_id.encode()).hexdigest()[:32]

                    bend_desc = (
                        f"FA Conduit Elbow 90°: {CONDUIT_TYPE}, "
                        f"R={6 * CONDUIT_DIAMETER_M * 1000:.1f}mm. "
                        f"Bend added per NEC Chapter 9"
                    )

                    elements.append(
                        IFCElement(
                            global_id=bend_hash,
                            ifc_class="IfcPipeFitting",
                            name=f"FA-Elbow-{route.route_id}-F{i:03d}",
                            description=bend_desc,
                            start_point=(wp_end.x, wp_end.y, wp_end.z),
                            end_point=(wp_end.x, wp_end.y, wp_end.z),
                            length_m=0.0,  # Fitting has no length
                            workset=self._workset,
                            route_id=route.route_id,
                        )
                    )

        return elements

    def generate_ifc_json(
        self,
        schedule: RoutingSchedule,
    ) -> str:
        """Generate IFC-like JSON representation of cable elements.

        This is a simplified JSON output for interoperability.
        For full IFC file generation, use IfcOpenShell's writer.

        Args:
            schedule: RoutingSchedule with all routes.

        Returns:
            JSON string with IFC element data.

        """
        elements = self.generate_ifc_elements(schedule)

        output: dict[str, Any] = {
            "schema": "IFC4",
            "workset": self._workset,
            "elements": [],
        }

        for elem in elements:
            output["elements"].append(
                {
                    "GlobalId": elem.global_id,
                    "IFC_Class": elem.ifc_class,
                    "Name": elem.name,
                    "Description": elem.description,
                    "StartPoint": list(elem.start_point),
                    "EndPoint": list(elem.end_point),
                    "Length_m": elem.length_m,
                    "Workset": elem.workset,
                    "RouteID": elem.route_id,
                }
            )

        return json.dumps(output, indent=2, sort_keys=False)

    # ─── Revit Model Line Generation ─────────────────────────────────────

    def generate_revit_model_lines(
        self,
        schedule: RoutingSchedule,
    ) -> List[Dict[str, Any]]:
        """Generate Revit Model Line definitions.

        Model Lines are placed on the dedicated workset "FA-CABLES".
        Each line segment represents a cable run between waypoints.

        Args:
            schedule: RoutingSchedule with all routes.

        Returns:
            List of model line definition dicts.

        """
        lines = []

        for route in schedule.routes:
            for i in range(len(route.waypoints) - 1):
                wp_start = route.waypoints[i]
                wp_end = route.waypoints[i + 1]

                line = {
                    "line_id": f"ML-{route.route_id}-{i:03d}",
                    "workset": self._workset,
                    "start": {
                        "x": wp_start.x,
                        "y": wp_start.y,
                        "z": wp_start.z,
                    },
                    "end": {
                        "x": wp_end.x,
                        "y": wp_end.y,
                        "z": wp_end.z,
                    },
                    "line_style": "FA-Cable",
                    "category": "Conduit",
                    "family": "Conduit",
                    "type": CONDUIT_TYPE,
                    "route_id": route.route_id,
                    "code_reference": "NEC 760.24, NFPA 72 §10.6.4",
                }
                lines.append(line)

        return lines

    # ─── Report Generation ───────────────────────────────────────────────

    def generate_report(
        self,
        schedule: RoutingSchedule,
        project_name: str = "",
    ) -> ReportSummary:
        """Generate summary report from cable routing results.

        Report includes:
        - Total cable length
        - Number of bends
        - Maximum circuit length
        - Compliance summary

        Args:
            schedule: RoutingSchedule with all routes.
            project_name: Project name.

        Returns:
            ReportSummary with all metrics.

        """
        total_violations = 0
        max_vdrop = 0.0
        max_vdrop_pct = 0.0

        for route in schedule.routes:
            if route.constraint_results:
                total_violations += route.constraint_results.total_violations
            max_vdrop = max(max_vdrop, route.voltage_drop_v)
            max_vdrop_pct = max(max_vdrop_pct, route.voltage_drop_pct)

        # Collect all unique code references from decision logs
        code_refs = set()
        for route in schedule.routes:
            for _desc, ref in route.decision_log:
                if ref:
                    code_refs.add(ref)

        # Always include primary references
        code_refs.update(
            [
                "NFPA 72 §10.6.4",
                "NFPA 72 §23.6.2",
                "NEC 760.24",
                "NEC 760.24(A)",
                "NEC Chapter 9, Table 8",
            ]
        )

        return ReportSummary(
            project_name=project_name or schedule.project_name,
            total_routes=len(schedule.routes),
            total_cable_length_m=schedule.total_cable_length_m,
            total_bends=schedule.total_bends,
            max_circuit_length_m=schedule.max_circuit_length_m,
            max_voltage_drop_v=round(max_vdrop, 4),
            max_voltage_drop_pct=round(max_vdrop_pct, 2),
            compliance_status=schedule.compliance_summary,
            constraint_violations=total_violations,
            code_references=tuple(sorted(code_refs)),
        )

    def generate_text_report(
        self,
        schedule: RoutingSchedule,
        project_name: str = "",
    ) -> str:
        """Generate human-readable text report.

        Args:
            schedule: RoutingSchedule with all routes.
            project_name: Project name.

        Returns:
            Formatted text report string.

        """
        report = self.generate_report(schedule, project_name)

        lines = [
            "=" * 60,
            "FIRE ALARM CABLE ROUTING REPORT",
            f"Project: {report.project_name}",
            "=" * 60,
            "",
            "SUMMARY",
            "-" * 40,
            f"Total Routes:              {report.total_routes}",
            f"Total Cable Length:         {report.total_cable_length_m:.2f} m",
            f"Total Bends (90 deg):      {report.total_bends}",
            f"Max Circuit Length:         {report.max_circuit_length_m:.2f} m",
            f"Max Voltage Drop:           {report.max_voltage_drop_v:.4f} V ({report.max_voltage_drop_pct:.2f}%)",
            f"Compliance Status:         {report.compliance_status}",
            f"Constraint Violations:      {report.constraint_violations}",
            "",
            "CODE REFERENCES",
            "-" * 40,
        ]

        for ref in report.code_references:
            lines.append(f"  - {ref}")

        lines.extend(
            [
                "",
                "ROUTE DETAILS",
                "-" * 40,
            ]
        )

        for route in schedule.routes:
            status = "COMPLIANT" if route.is_compliant else "VIOLATIONS"
            lines.append(f"  Route: {route.route_id} [{status}]")
            lines.append(f"    From: ({route.start[0]:.2f}, {route.start[1]:.2f}, {route.start[2]:.2f})")
            lines.append(f"    To:   ({route.end[0]:.2f}, {route.end[1]:.2f}, {route.end[2]:.2f})")
            lines.append(f"    Length: {route.total_length_m:.2f}m")
            lines.append(f"    Bends: {route.num_bends}")
            lines.append(f"    V-drop: {route.voltage_drop_v:.4f}V ({route.voltage_drop_pct:.2f}%)")
            lines.append(
                f"    Wire: AWG {route.wire_gauge if isinstance(route.wire_gauge, str) else route.wire_gauge.awg_value}"
            )

            if route.constraint_results and not route.constraint_results.all_satisfied:
                lines.append("    VIOLATIONS:")
                for cr in route.constraint_results.results:
                    if not cr.is_satisfied:
                        lines.append(f"      - {cr.constraint_name} ({cr.source})")
                        lines.append(f"        {cr.remediation}")
            lines.append("")

        # Verification hash
        lines.extend(
            [
                "=" * 60,
                f"Computation Hash: {report.computation_hash or schedule.computation_hash}",
                "Same input → same output, always (QOMN-FIRE deterministic)",
                "=" * 60,
            ]
        )

        return "\n".join(lines)
