"""
safety/fire.py
==============
Higher-level fire-safety checks that compose multiple compliance rules
into project-level go/no-go gates.

These are SAFETY GATES, not advice: every gate returns either:
  - status='pass'
  - status='fail' (must be addressed before issuing the drawing)
  - status='review_required' (human engineer must sign-off)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..knowledge.memory import KnowledgeBase
from ..reasoning.compliance import ComplianceEngine, Finding


@dataclass
class SafetyGate:
    name: str
    status: str            # 'pass' | 'fail' | 'review_required'
    findings: list = field(default_factory=list)
    notes: str = ""


def gate_smoke_detection_coverage(kb: KnowledgeBase,
                                  positions: list[tuple[float,float]],
                                  room_bounds: Optional[tuple] = None,
                                  units_to_m: float = 0.001) -> SafetyGate:
    eng = ComplianceEngine(kb, units_to_m=units_to_m)
    findings = eng.check_detector_spacing("smoke_detector", positions, room_bounds)
    if not positions:
        return SafetyGate("smoke_detection_coverage", "fail",
                          notes="No smoke detectors found in zone.")
    sev = {f.severity for f in findings}
    status = "pass" if not (sev & {"critical","major"}) else "fail"
    return SafetyGate("smoke_detection_coverage", status,
                      findings=[f.__dict__ for f in findings])


def gate_sprinkler_coverage(kb: KnowledgeBase,
                            positions: list[tuple[float,float]],
                            room_bounds: Optional[tuple] = None,
                            units_to_m: float = 0.001) -> SafetyGate:
    eng = ComplianceEngine(kb, units_to_m=units_to_m)
    findings = eng.check_sprinkler_spacing(positions, room_bounds)
    if not positions:
        return SafetyGate("sprinkler_coverage", "review_required",
                          notes="No sprinklers in zone — verify if sprinklered zone is required.")
    sev = {f.severity for f in findings}
    status = "pass" if not (sev & {"critical","major"}) else "fail"
    return SafetyGate("sprinkler_coverage", status,
                      findings=[f.__dict__ for f in findings])


def gate_egress_distances(kb: KnowledgeBase,
                          occupant_points, exit_points, walls=None,
                          units_to_m: float = 0.001) -> SafetyGate:
    eng = ComplianceEngine(kb, units_to_m=units_to_m)
    findings = eng.check_egress(occupant_points, exit_points, walls=walls)
    sev = {f.severity for f in findings}
    status = "pass" if not (sev & {"critical","major"}) else "fail"
    return SafetyGate("egress_distances", status,
                      findings=[f.__dict__ for f in findings])


def run_all_gates(kb: KnowledgeBase, positions_by_symbol: dict,
                  room_bounds: Optional[tuple] = None,
                  occupants=None, exits=None, walls=None,
                  units_to_m: float = 0.001) -> list[SafetyGate]:
    gates = []
    if "smoke_detector" in positions_by_symbol:
        gates.append(gate_smoke_detection_coverage(
            kb, positions_by_symbol["smoke_detector"], room_bounds, units_to_m))
    spr = positions_by_symbol.get("sprinkler_pendant", []) + \
          positions_by_symbol.get("sprinkler_upright", [])
    if spr:
        gates.append(gate_sprinkler_coverage(kb, spr, room_bounds, units_to_m))
    if occupants and exits:
        gates.append(gate_egress_distances(kb, occupants, exits, walls, units_to_m))
    return gates
