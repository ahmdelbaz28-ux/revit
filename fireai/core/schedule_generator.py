"""fireai/core/schedule_generator.py
===================================
Cable schedule and compliance report generator.

Generates per-system-requirement §4:
  Schedule: Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop
  Report:   Total cable length, bends, max circuit length, compliance status

Integrates with:
  - fireai/core/cable_router.py       (CableRoute, RoutingSchedule)
  - fireai/core/cable_routing_engine.py (RouteResult, VoltageDropSegment)
  - fireai/core/revit_exporter.py     (ScheduleRow, ReportSummary)

References:
  - System Requirement §4: Output format (schedule + report)
  - NFPA 72 §23.6.2: NAC circuit max length per gauge
  - NEC 760.24(A): 18" (457mm) support spacing

"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Wire gauge → max circuit length (NFPA 72 §23.6.2)
_NFPA72_23_6_2_MAX_LEN_M: Dict[str, float] = {
    "12 AWG": 2286.0,
    "14 AWG": 1524.0,
    "16 AWG": 914.0,
    "18 AWG": 610.0,
}


@dataclass
class ScheduleRow:
    """One row in the cable schedule output (system req §4)."""

    device_id: str
    from_location: str
    to_location: str
    length_m: float
    wire_type: str  # e.g. "14 AWG in 3/4\" RED EMT"
    voltage_drop_v: float
    end_voltage_v: float
    bend_count: int
    compliant: bool
    code_refs: str = "NFPA72§23.6.2+NEC760.24+ProjSpec"


@dataclass
class ScheduleReport:
    """Summary compliance report (system req §4)."""

    generated: str
    total_cable_length_m: float
    total_bends: int
    max_circuit_length_m: float
    min_end_voltage_v: float
    all_compliant: bool
    route_count: int
    violations_count: int
    nfpa72_limits: Dict[str, float]
    code_refs: List[str]
    routes: List[Dict[str, Any]] = field(default_factory=list)


class ScheduleGenerator:
    """Generates cable schedules and compliance reports from routing results.

    Accepts results from either:
      - CableRouter.route_all() → RoutingSchedule
      - CableRoutingEngine.route_circuit() → RouteResult list

    Output formats: CSV, JSON, plain text.
    """

    def from_routing_schedule(self, schedule, ps_voltage: float = 0.0) -> List[ScheduleRow]:
        """Convert a RoutingSchedule (from CableRouter.route_all) to ScheduleRow list.

        V113 FIX: Added ps_voltage parameter with fail-safe default of 0.0.
        Previously, this method hardcoded ps_voltage=24.0, which is WRONG for:
          - 12VDC systems (common in small fire alarm panels per NFPA 72 §10.6.5)
          - 48VDC systems (used in some notification appliance circuits)
        A 12VDC system with hardcoded 24.0V would report end_voltage = 24.0 - vdrop,
        appearing compliant when the actual voltage is 12.0 - vdrop (likely failing).
        This is a life-safety calculation error per agent.md Priority 1.

        The caller MUST pass ps_voltage explicitly. If 0.0 (default), a warning
        is logged and we attempt to read from the schedule object. If still
        unavailable, we use 24.0 as a LAST RESORT with a CRITICAL warning.

        REAL RoutingSchedule fields (verified from cable_router.py):
          schedule.routes: Tuple[CableRoute]         — all routes
          schedule.total_cable_length_m: float
          schedule.total_bends: int
          schedule.max_circuit_length_m: float
          schedule.computation_hash: str

        REAL CableRoute fields (verified from cable_router.py):
          route.route_id: str
          route.start: Tuple[float, float, float]
          route.end:   Tuple[float, float, float]
          route.total_length_m: float
          route.num_bends: int
          route.wire_gauge: WireGauge (has .awg_value property)
          route.voltage_drop_v: float
          route.is_compliant: bool

        BUG HISTORY: Previous version read schedule.waypoints (never existed)
        and schedule.wire_gauge (on CableRoute, not RoutingSchedule).
        Fixed to iterate schedule.routes and read per-CableRoute fields.
        """
        # V113: Determine ps_voltage with fail-safe hierarchy:
        # 1. Explicit parameter (preferred — caller knows the system voltage)
        # 2. From schedule object (if it stores ps_voltage)
        # 3. Default 24.0V with CRITICAL warning (last resort)
        actual_ps_voltage = ps_voltage
        if actual_ps_voltage <= 0.0:
            actual_ps_voltage = float(getattr(schedule, "ps_voltage", 0.0))
        if actual_ps_voltage <= 0.0:
            # LAST RESORT: Default to 24.0VDC but log CRITICAL warning
            # This is dangerous — 12VDC systems will show wrong end_voltage
            actual_ps_voltage = 24.0
            logger.critical(
                "V113 SAFETY WARNING: ps_voltage not specified — defaulting to 24.0V. "
                "If your system uses 12VDC or 48VDC, all voltage drop calculations "
                "are WRONG. Pass ps_voltage explicitly to from_routing_schedule(). "
                "NFPA 72 §10.6.5 requires accurate voltage calculations. "
                "Wrong voltage = devices may not operate during a fire."
            )

        rows = []
        for route in getattr(schedule, "routes", ()):
            start = getattr(route, "start", (0.0, 0.0, 0.0))
            end = getattr(route, "end", (0.0, 0.0, 0.0))
            gauge = getattr(route, "wire_gauge", None)
            awg = gauge.awg_value if (gauge and hasattr(gauge, "awg_value")) else "14"
            vdrop = float(getattr(route, "voltage_drop_v", 0.0))
            rows.append(
                ScheduleRow(
                    device_id=str(getattr(route, "route_id", "ROUTE")),
                    from_location=f"({start[0]:.2f},{start[1]:.2f},{start[2]:.2f})",
                    to_location=f"({end[0]:.2f},{end[1]:.2f},{end[2]:.2f})",
                    length_m=float(getattr(route, "total_length_m", 0.0)),
                    wire_type=f'{awg} AWG in 3/4" RED EMT',
                    voltage_drop_v=vdrop,
                    end_voltage_v=actual_ps_voltage - vdrop,  # V113: Use actual system voltage
                    bend_count=int(getattr(route, "num_bends", 0)),
                    compliant=bool(getattr(route, "is_compliant", False)),
                )
            )
        return rows

    def from_route_results(self, results: List[Any], ps_voltage: float = 0.0) -> List[ScheduleRow]:
        """Convert RouteResult list (from CableRoutingEngine) to ScheduleRow list.

        V113 FIX: Added ps_voltage parameter (same as from_routing_schedule).
        """
        # V113: Same ps_voltage resolution logic as from_routing_schedule
        actual_ps_voltage = ps_voltage
        if actual_ps_voltage <= 0.0:
            actual_ps_voltage = 24.0
            logger.warning(
                "V113: ps_voltage not specified for from_route_results() — "
                "defaulting to 24.0V. Pass explicit ps_voltage for 12VDC/48VDC systems."
            )

        rows = []
        for r in results:
            rows.append(
                ScheduleRow(
                    device_id=f"{getattr(r, 'device_from', '?')}→{getattr(r, 'device_to', '?')}",
                    from_location=str(
                        getattr(r, "path_world_m", [[0, 0, 0]])[0] if getattr(r, "path_world_m", None) else (0, 0, 0)
                    ),
                    to_location=str(
                        getattr(r, "path_world_m", [[0, 0, 0]])[-1] if getattr(r, "path_world_m", None) else (0, 0, 0)
                    ),
                    length_m=float(getattr(r, "total_length_m", 0)),
                    wire_type=f'{getattr(r, "wire_gauge", "14 AWG")} in 3/4" RED EMT',
                    voltage_drop_v=float(getattr(r, "voltage_drop_v", 0)),
                    end_voltage_v=float(getattr(r, "end_voltage_v", actual_ps_voltage)),  # V113: Use actual voltage
                    bend_count=int(getattr(r, "bend_count", 0)),
                    compliant=bool(getattr(r, "compliant", False)),  # V69-10 FIX: fail-safe default
                )
            )
        return rows

    def to_csv(self, rows: List[ScheduleRow]) -> str:
        """Generate CSV cable schedule (system requirement §4).
        Columns: Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop
        """
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Device_ID",
                "From_Location",
                "To_Location",
                "Length_m",
                "Wire_Type",
                "Voltage_Drop_V",
                "End_Voltage_V",
                "Bend_Count",
                "Compliant",
                "Code_Refs",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.device_id,
                    r.from_location,
                    r.to_location,
                    f"{r.length_m:.3f}",
                    r.wire_type,
                    f"{r.voltage_drop_v:.4f}",
                    f"{r.end_voltage_v:.4f}",
                    r.bend_count,
                    "YES" if r.compliant else "NO",
                    r.code_refs,
                ]
            )
        return buf.getvalue()

    def to_report(self, rows: List[ScheduleRow]) -> ScheduleReport:
        """Generate compliance summary report (system requirement §4).
        Includes: total cable length, bends, max circuit length.
        """
        if not rows:
            # V97 FIX: Empty schedule must report all_compliant=False (fail-safe).
            # An empty schedule means no circuits were analyzed — claiming
            # compliance is the false-GREEN anti-pattern. Per Rule 17:
            # a half-solution (empty=True) is worse than no solution because
            # it creates a false sense of security.
            return ScheduleReport(
                generated=datetime.now(timezone.utc).isoformat(),
                total_cable_length_m=0.0,
                total_bends=0,
                max_circuit_length_m=0.0,
                min_end_voltage_v=0.0,
                all_compliant=False,
                route_count=0,
                violations_count=0,
                nfpa72_limits=_NFPA72_23_6_2_MAX_LEN_M,
                code_refs=["NFPA 72 §23.6.2", "NEC 760.24(A)", "Project Spec"],
            )

        return ScheduleReport(
            generated=datetime.now(timezone.utc).isoformat(),
            total_cable_length_m=round(sum(r.length_m for r in rows), 3),
            total_bends=sum(r.bend_count for r in rows),
            max_circuit_length_m=round(max(r.length_m for r in rows), 3),
            min_end_voltage_v=round(min(r.end_voltage_v for r in rows), 4),
            all_compliant=all(r.compliant for r in rows),
            route_count=len(rows),
            violations_count=sum(1 for r in rows if not r.compliant),
            nfpa72_limits=_NFPA72_23_6_2_MAX_LEN_M,
            code_refs=[
                "NFPA 72 §23.6.2 — NAC circuit max length",
                'NEC 760.24(A) — cable support every 18" (457mm)',
                'Project Spec — 3/4" RED EMT, bend radius 6×OD',
                "NEC Chapter 9, Table 8 — conductor resistance",
            ],
            routes=[
                {
                    "route": r.device_id,
                    "length_m": round(r.length_m, 3),
                    "bends": r.bend_count,
                    "vdrop_v": round(r.voltage_drop_v, 4),
                    "end_v": round(r.end_voltage_v, 4),
                    "compliant": r.compliant,
                }
                for r in rows
            ],
        )

    def to_json(self, rows: List[ScheduleRow]) -> str:
        """Export schedule + report as JSON."""
        report = self.to_report(rows)
        return json.dumps(
            {
                "schedule": [asdict(r) for r in rows],
                "report": asdict(report),
            },
            indent=2,
        )

    def to_text_report(self, rows: List[ScheduleRow]) -> str:
        """Plain-text compliance report for field use."""
        rep = self.to_report(rows)
        lines = [
            "=" * 60,
            f"FIRE ALARM CABLE SCHEDULE — {rep.generated[:10]}",
            f"Generated: {rep.generated}",
            "=" * 60,
            f"Total Routes:       {rep.route_count}",
            f"Total Cable Length: {rep.total_cable_length_m:.1f} m",
            f"Total Bends:        {rep.total_bends}",
            f"Max Circuit Length: {rep.max_circuit_length_m:.1f} m",
            f"Min End Voltage:    {rep.min_end_voltage_v:.2f} V",
            f"All Compliant:      {'YES' if rep.all_compliant else 'NO — SEE VIOLATIONS'}",
            "",
            "CODE REFERENCES:",
        ]
        for ref in rep.code_refs:
            lines.append(f"  - {ref}")
        lines += ["", "ROUTE DETAILS:", "-" * 60]
        for r in rows:
            status = "✓ OK" if r.compliant else "✗ VIOLATION"
            lines.append(
                f"  {r.device_id}: {r.length_m:.1f}m, {r.bend_count} bends, Vdrop={r.voltage_drop_v:.3f}V  [{status}]"
            )
        lines.append("=" * 60)
        return "\n".join(lines)
