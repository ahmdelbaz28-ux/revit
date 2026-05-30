"""
fireai/core/schedule_generator.py
===================================
Cable schedule and compliance report generator.

Generates per-system-requirement §4:
  Schedule: Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop
  Report:   Total cable length, bends, max circuit length, compliance status

Integrates with:
  - fireai/core/cable_router.py       (CableRoute, RoutingSchedule)
  - fireai/core/cable_routing_engine.py (RouteResult, VoltageDropSegment)
  - fireai/core/revit_exporter.py     (ScheduleRow, ReportSummary)

REFERENCES:
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Wire gauge → max circuit length (NFPA 72 §23.6.2)
_NFPA72_23_6_2_MAX_LEN_M: Dict[str, float] = {
    "12 AWG": 2286.0,
    "14 AWG": 1524.0,
    "16 AWG":  914.0,
    "18 AWG":  610.0,
}


@dataclass
class ScheduleRow:
    """One row in the cable schedule output (system req §4)."""
    device_id:      str
    from_location:  str
    to_location:    str
    length_m:       float
    wire_type:      str       # e.g. "14 AWG in 3/4\" RED EMT"
    voltage_drop_v: float
    end_voltage_v:  float
    bend_count:     int
    compliant:      bool
    code_refs:      str = "NFPA72§23.6.2+NEC760.24+ProjSpec"


@dataclass
class ScheduleReport:
    """Summary compliance report (system req §4)."""
    generated:            str
    total_cable_length_m: float
    total_bends:          int
    max_circuit_length_m: float
    min_end_voltage_v:    float
    all_compliant:        bool
    route_count:          int
    violations_count:     int
    nfpa72_limits:        Dict[str, float]
    code_refs:            List[str]
    routes:               List[Dict[str, Any]] = field(default_factory=list)


class ScheduleGenerator:
    """
    Generates cable schedules and compliance reports from routing results.

    Accepts results from either:
      - CableRouter.route_all() → RoutingSchedule
      - CableRoutingEngine.route_circuit() → RouteResult list

    Output formats: CSV, JSON, plain text.
    """

    def from_routing_schedule(self, schedule) -> List[ScheduleRow]:
        """
        Convert a RoutingSchedule (from CableRouter) to ScheduleRow list.
        RoutingSchedule.waypoints contains RouteWaypoint objects.
        """
        rows = []
        waypoints = getattr(schedule, 'waypoints', [])
        for i in range(len(waypoints) - 1):
            wp_a = waypoints[i]
            wp_b = waypoints[i + 1]
            rows.append(ScheduleRow(
                device_id=f"{getattr(wp_a,'device_id',f'DEV-{i}')}→{getattr(wp_b,'device_id',f'DEV-{i+1}')}",
                from_location=str(getattr(wp_a, 'world_position', (0, 0, 0))),
                to_location=str(getattr(wp_b, 'world_position', (0, 0, 0))),
                length_m=float(getattr(schedule, 'total_length_m', 0)),
                wire_type=f"{getattr(schedule,'wire_gauge','14 AWG')} in 3/4\" RED EMT",
                voltage_drop_v=float(getattr(schedule, 'voltage_drop_v', 0)),
                end_voltage_v=float(getattr(schedule, 'end_voltage_v', 24.0)),
                bend_count=int(getattr(schedule, 'bend_count', 0)),
                compliant=bool(getattr(schedule, 'is_compliant', False)),  # V69-10 FIX: fail-safe default
            ))
        return rows

    def from_route_results(self, results: List[Any]) -> List[ScheduleRow]:
        """Convert RouteResult list (from CableRoutingEngine) to ScheduleRow list."""
        rows = []
        for r in results:
            rows.append(ScheduleRow(
                device_id=f"{getattr(r,'device_from','?')}→{getattr(r,'device_to','?')}",
                from_location=str(getattr(r, 'path_world_m', [[0,0,0]])[0] if getattr(r,'path_world_m',None) else (0,0,0)),
                to_location=str(getattr(r, 'path_world_m', [[0,0,0]])[-1] if getattr(r,'path_world_m',None) else (0,0,0)),
                length_m=float(getattr(r, 'total_length_m', 0)),
                wire_type=f"{getattr(r,'wire_gauge','14 AWG')} in 3/4\" RED EMT",
                voltage_drop_v=float(getattr(r, 'voltage_drop_v', 0)),
                end_voltage_v=float(getattr(r, 'end_voltage_v', 24.0)),
                bend_count=int(getattr(r, 'bend_count', 0)),
                compliant=bool(getattr(r, 'compliant', False)),  # V69-10 FIX: fail-safe default
            ))
        return rows

    def to_csv(self, rows: List[ScheduleRow]) -> str:
        """
        Generate CSV cable schedule (system requirement §4).
        Columns: Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop
        """
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Device_ID", "From_Location", "To_Location",
            "Length_m", "Wire_Type", "Voltage_Drop_V",
            "End_Voltage_V", "Bend_Count", "Compliant", "Code_Refs",
        ])
        for r in rows:
            writer.writerow([
                r.device_id, r.from_location, r.to_location,
                f"{r.length_m:.3f}", r.wire_type,
                f"{r.voltage_drop_v:.4f}", f"{r.end_voltage_v:.4f}",
                r.bend_count, "YES" if r.compliant else "NO",
                r.code_refs,
            ])
        return buf.getvalue()

    def to_report(self, rows: List[ScheduleRow]) -> ScheduleReport:
        """
        Generate compliance summary report (system requirement §4).
        Includes: total cable length, bends, max circuit length.
        """
        if not rows:
            return ScheduleReport(
                generated=datetime.now(timezone.utc).isoformat(),
                total_cable_length_m=0.0, total_bends=0,
                max_circuit_length_m=0.0, min_end_voltage_v=0.0,
                all_compliant=True, route_count=0, violations_count=0,
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
                "NEC 760.24(A) — cable support every 18\" (457mm)",
                "Project Spec — 3/4\" RED EMT, bend radius 6×OD",
                "NEC Chapter 9, Table 8 — conductor resistance",
            ],
            routes=[
                {
                    "route":       r.device_id,
                    "length_m":    round(r.length_m, 3),
                    "bends":       r.bend_count,
                    "vdrop_v":     round(r.voltage_drop_v, 4),
                    "end_v":       round(r.end_voltage_v, 4),
                    "compliant":   r.compliant,
                }
                for r in rows
            ],
        )

    def to_json(self, rows: List[ScheduleRow]) -> str:
        """Export schedule + report as JSON."""
        report = self.to_report(rows)
        return json.dumps({
            "schedule": [asdict(r) for r in rows],
            "report":   asdict(report),
        }, indent=2)

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
                f"  {r.device_id}: {r.length_m:.1f}m, "
                f"{r.bend_count} bends, Vdrop={r.voltage_drop_v:.3f}V  [{status}]"
            )
        lines.append("=" * 60)
        return "\n".join(lines)
