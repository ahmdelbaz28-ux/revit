"""FireAI Rules Engine — Integration Bridge
==========================================

Bridges the new Rules Engine with the existing FireAI compliance
system. This module provides:

1. Conversion from existing data models to Rule Engine facts
2. Conversion from Rule Engine results to existing violation format
3. Integration with existing AuditStore for rule evaluation audit
4. Backward-compatible API — existing code continues to work

SAFETY: This bridge ensures that the Rules Engine enhances (not replaces)
the existing compliance checks. Both systems run in parallel during
the transition period. Discrepancies are flagged for review.

Reference: NFPA 72-2022, agent.md Rules 6 and 7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fireai.core.rules_engine.engine import (
    Fact,
    RuleAuditEntry,
    RulePriority,
    RulesEngine,
)
from fireai.core.rules_engine.nfpa72_rules import NFPA72RuleSet
from fireai.core.rules_engine.truth_maintenance import TruthMaintenanceSystem

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CONVERSION
# ═══════════════════════════════════════════════════════════════════════════════


def room_to_facts(
    room_id: str,
    ceiling_height_m: float,
    detector_type: str = "smoke",
    room_area_m2: Optional[float] = None,
    is_corridor: bool = False,
    occupancy_type: str = "office",
) -> List[Fact]:
    """Convert a room specification to Rule Engine facts.

    This is the main entry point for analyzing a room through the
    declarative rules engine.
    """
    facts = [
        Fact(
            fact_type="room",
            properties={
                "room_id": room_id,
                "ceiling_height_m": ceiling_height_m,
                "detector_type": detector_type,
                "room_area_m2": room_area_m2,
                "is_corridor": is_corridor,
                "occupancy_type": occupancy_type,
            },
            source="room_input",
            nfpa_reference="NFPA 72 §17.6.3.1",
        )
    ]
    return facts


def detector_to_fact(
    detector_id: str,
    room_id: str,
    detector_type: str,
    x: float,
    y: float,
    distance_to_wall_m: Optional[float] = None,
    listed_spacing_m: Optional[float] = None,
    wall_distance_max_m: Optional[float] = None,
) -> Fact:
    """Convert a detector to a Rule Engine fact."""
    properties = {
        "detector_id": detector_id,
        "room_id": room_id,
        "detector_type": detector_type,
        "x": x,
        "y": y,
    }
    if distance_to_wall_m is not None:
        properties["distance_to_wall_m"] = distance_to_wall_m
    if listed_spacing_m is not None:
        properties["listed_spacing_m"] = listed_spacing_m
    if wall_distance_max_m is not None:
        properties["wall_distance_max_m"] = wall_distance_max_m

    return Fact(
        fact_type="detector",
        properties=properties,
        source="detector_input",
        nfpa_reference="NFPA 72 §17.6.3.1",
    )


def hvac_to_fact(
    unit_id: str,
    cfm: float,
    has_duct_detector: bool = False,
    duct_type: str = "supply",
) -> Fact:
    """Convert an HVAC unit to a Rule Engine fact."""
    return Fact(
        fact_type="hvac_unit",
        properties={
            "unit_id": unit_id,
            "cfm": cfm,
            "has_duct_detector": has_duct_detector,
            "duct_type": duct_type,
        },
        source="hvac_input",
        nfpa_reference="NFPA 72 §17.7.5.1",
    )


def elevator_to_fact(
    elevator_id: str,
    has_lobby_detector: bool = False,
    has_hoistway_detector: bool = False,
) -> Fact:
    """Convert an elevator to a Rule Engine fact."""
    return Fact(
        fact_type="elevator",
        properties={
            "elevator_id": elevator_id,
            "has_lobby_detector": has_lobby_detector,
            "has_hoistway_detector": has_hoistway_detector,
        },
        source="elevator_input",
        nfpa_reference="NFPA 72 §21.3.3",
    )


def battery_result_to_fact(
    required_ah: float,
    installed_ah: float,
    is_adequate: bool,
    nfpa_section: str = "NFPA 72 §10.6.7",
) -> Fact:
    """Convert a battery calculation result to a Rule Engine fact.

    This bridges nfpa72_engine.calculate_battery() output into
    the Rules Engine so that RULE_BATTERY_INADEQUATE (NFPA72-011)
    can evaluate it.

    Reference: NFPA 72 §10.6.7.2.1
    """
    return Fact(
        fact_type="battery_result",
        properties={
            "required_ah": required_ah,
            "installed_ah": installed_ah,
            "is_adequate": is_adequate,
            "nfpa_section": nfpa_section,
        },
        source="nfpa72_engine",
        nfpa_reference=nfpa_section,
    )


def voltage_drop_result_to_fact(
    voltage_drop_v: float,
    voltage_drop_pct: float,
    max_length_m: float,
    is_compliant: bool,
    nfpa_section: str = "NFPA 72 §10.6.4",
) -> Fact:
    """Convert a voltage drop result to a Rule Engine fact.

    This bridges nfpa72_engine.calculate_voltage_drop() output into
    the Rules Engine so that RULE_VOLTAGE_DROP_EXCEEDED (NFPA72-012)
    can evaluate it.

    Reference: NFPA 72 §10.6.4, NEC 760
    """
    return Fact(
        fact_type="voltage_drop_result",
        properties={
            "voltage_drop_v": voltage_drop_v,
            "voltage_drop_pct": voltage_drop_pct,
            "max_length_m": max_length_m,
            "is_compliant": is_compliant,
            "nfpa_section": nfpa_section,
        },
        source="nfpa72_engine",
        nfpa_reference=nfpa_section,
    )


def fault_isolation_result_to_fact(
    compliant: bool,
    violations: List[Dict[str, Any]],
    device_count: int,
    isolator_count: int,
    nfpa_section: str = "NFPA 72 §12.3",
) -> Fact:
    """Convert a fault isolation result to a Rule Engine fact.

    This bridges nfpa72_engine.verify_fault_isolator_placement() output
    into the Rules Engine so that RULE_FAULT_ISOLATION_VIOLATION (NFPA72-013)
    can evaluate it.

    Reference: NFPA 72 §12.3.1
    """
    return Fact(
        fact_type="fault_isolation_result",
        properties={
            "compliant": compliant,
            "violations": violations,
            "device_count": device_count,
            "isolator_count": isolator_count,
            "nfpa_section": nfpa_section,
        },
        source="nfpa72_engine",
        nfpa_reference=nfpa_section,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RESULT CONVERSION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ComplianceReport:
    """Structured compliance report from the rules engine.

    Compatible with the existing ExpertResult format but enriched
    with rule evaluation details and truth maintenance data.
    """

    session_id: str
    is_safe: bool
    critical_issues: List[Dict[str, Any]] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    compliance_checks: List[Dict[str, Any]] = field(default_factory=list)
    derived_facts: List[Dict[str, Any]] = field(default_factory=list)
    audit_summary: Dict[str, Any] = field(default_factory=dict)
    nfpa_references: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def results_to_report(
    engine: RulesEngine,
) -> ComplianceReport:
    """Convert Rule Engine results to a ComplianceReport.

    This is the main output conversion function. It takes a fully
    evaluated RulesEngine and produces a structured report.
    """
    summary = engine.get_compliance_summary()

    critical_issues = []
    violations = []
    compliance_checks = []

    for result in engine.get_results():
        entry = {
            "rule_id": result.rule_id,
            "rule_name": result.rule_name,
            "nfpa_reference": result.nfpa_reference,
            "message": result.message,
            "severity": result.severity.name,
            "matched_facts": result.matched_facts,
            "confidence": result.confidence,
        }

        if result.severity == RulePriority.CRITICAL_SAFETY:
            critical_issues.append(entry)
        elif result.severity == RulePriority.SAFETY_VIOLATION:
            violations.append(entry)
        else:
            compliance_checks.append(entry)

    # Collect derived facts
    derived = []
    for fact in engine.get_facts():
        if fact.source == "derived":
            derived.append(
                {
                    "fact_type": fact.fact_type,
                    "fact_id": fact.fact_id,
                    "properties": fact.properties,
                    "nfpa_reference": fact.nfpa_reference,
                }
            )

    # Collect NFPA references
    nfpa_refs = list({r.nfpa_reference for r in engine.get_results() if r.nfpa_reference})

    # FIX: If no facts were asserted, we cannot determine safety.
    # Conservative default: is_safe=False when no analysis was performed.
    no_facts_asserted = len(engine.get_facts()) == 0
    if no_facts_asserted:
        critical_issues.append(
            {
                "rule_id": "BRIDGE-001",
                "message": "No facts analyzed — compliance cannot be determined",
                "severity": "CRITICAL_SAFETY",
            }
        )

    return ComplianceReport(
        session_id=engine.session_id,
        is_safe=(len(critical_issues) == 0 and len(violations) == 0 and not no_facts_asserted),
        critical_issues=critical_issues,
        violations=violations,
        compliance_checks=compliance_checks,
        derived_facts=derived,
        audit_summary=summary,
        nfpa_references=nfpa_refs,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HIGH-LEVEL API
# ═══════════════════════════════════════════════════════════════════════════════


class NFPA72ComplianceChecker:
    """High-level API for NFPA 72 compliance checking using the rules engine.

    This provides a simple interface for the rest of the FireAI system
    to use the rules engine without dealing with low-level details.

    Usage:
        checker = NFPA72ComplianceChecker()
        checker.add_room("R1", ceiling_height_m=3.0, detector_type="smoke")
        checker.add_detector("D1", "R1", "smoke", x=5.0, y=5.0,
                             distance_to_wall_m=0.5)
        report = checker.evaluate()
        if not report.is_safe:
            for issue in report.critical_issues:
                print(f"CRITICAL: {issue['message']}")
    """

    def __init__(self, session_id: str = "") -> None:
        self.engine = RulesEngine(
            session_id=session_id,
            max_iterations=50,
        )
        self.engine.add_rules(NFPA72RuleSet.all_rules())
        # TMS is integrated inside RulesEngine via _derived_from/_supports
        # dictionaries. The standalone TruthMaintenanceSystem is available
        # for external audit and consistency checks.
        # SAFETY FIX (CRITICAL-5): The standalone TMS is now synchronized
        # with the engine's internal TMS after every evaluate() call, so
        # validate_tms_consistency() actually checks real dependency records.
        self.tms = TruthMaintenanceSystem()
        self._sync_tms_after_evaluate = True

    def validate_tms_consistency(self) -> List[str]:
        """Check TMS consistency between engine and standalone TMS.

        Returns list of stale fact IDs. Empty list = consistent.
        SAFETY: This should always return an empty list.
        """
        existing_ids = {f.fact_id for f in self.engine.get_facts()}
        return self.tms.validate_consistency(existing_ids)

    def add_room(
        self,
        room_id: str,
        ceiling_height_m: float,
        detector_type: str = "smoke",
        room_area_m2: Optional[float] = None,
        is_corridor: bool = False,
        occupancy_type: str = "office",
    ) -> str:
        """Add a room for compliance analysis."""
        facts = room_to_facts(
            room_id=room_id,
            ceiling_height_m=ceiling_height_m,
            detector_type=detector_type,
            room_area_m2=room_area_m2,
            is_corridor=is_corridor,
            occupancy_type=occupancy_type,
        )
        fid = self.engine.assert_fact(facts[0])
        logger.info("Room added: %s h=%sm type=%s", room_id, ceiling_height_m, detector_type)
        return fid

    def add_detector(
        self,
        detector_id: str,
        room_id: str,
        detector_type: str,
        x: float,
        y: float,
        distance_to_wall_m: Optional[float] = None,
        listed_spacing_m: Optional[float] = None,
        wall_distance_max_m: Optional[float] = None,
    ) -> str:
        """Add a detector for compliance analysis."""
        fact = detector_to_fact(
            detector_id=detector_id,
            room_id=room_id,
            detector_type=detector_type,
            x=x,
            y=y,
            distance_to_wall_m=distance_to_wall_m,
            listed_spacing_m=listed_spacing_m,
            wall_distance_max_m=wall_distance_max_m,
        )
        fid = self.engine.assert_fact(fact)
        logger.info("Detector added: %s in %s at (%s, %s)", detector_id, room_id, x, y)
        return fid

    def add_hvac(
        self,
        unit_id: str,
        cfm: float,
        has_duct_detector: bool = False,
    ) -> str:
        """Add an HVAC unit for duct detector compliance."""
        fact = hvac_to_fact(
            unit_id=unit_id,
            cfm=cfm,
            has_duct_detector=has_duct_detector,
        )
        return self.engine.assert_fact(fact)

    def add_elevator(
        self,
        elevator_id: str,
        has_lobby_detector: bool = False,
        has_hoistway_detector: bool = False,
    ) -> str:
        """Add an elevator for recall compliance."""
        fact = elevator_to_fact(
            elevator_id=elevator_id,
            has_lobby_detector=has_lobby_detector,
            has_hoistway_detector=has_hoistway_detector,
        )
        return self.engine.assert_fact(fact)

    def add_battery_result(
        self,
        required_ah: float,
        installed_ah: float,
        is_adequate: bool,
    ) -> str:
        """Add a battery calculation result for compliance checking.

        Bridges nfpa72_engine.calculate_battery() results into the
        Rules Engine. Rule NFPA72-011 will fire if is_adequate=False.

        Reference: NFPA 72 §10.6.7.2.1
        """
        fact = battery_result_to_fact(
            required_ah=required_ah,
            installed_ah=installed_ah,
            is_adequate=is_adequate,
        )
        fid = self.engine.assert_fact(fact)
        logger.info(
            f"Battery result added: required={required_ah:.2f}Ah, "
            f"installed={installed_ah:.2f}Ah, "
            f"adequate={is_adequate}"
        )
        return fid

    def add_voltage_drop_result(
        self,
        voltage_drop_v: float,
        voltage_drop_pct: float,
        max_length_m: float,
        is_compliant: bool,
    ) -> str:
        """Add a voltage drop result for compliance checking.

        Bridges nfpa72_engine.calculate_voltage_drop() results into the
        Rules Engine. Rule NFPA72-012 will fire if is_compliant=False.

        Reference: NFPA 72 §10.6.4, NEC 760
        """
        fact = voltage_drop_result_to_fact(
            voltage_drop_v=voltage_drop_v,
            voltage_drop_pct=voltage_drop_pct,
            max_length_m=max_length_m,
            is_compliant=is_compliant,
        )
        fid = self.engine.assert_fact(fact)
        logger.info("Voltage drop result added: drop=%s%, compliant=%s", voltage_drop_pct, is_compliant)
        return fid

    def add_fault_isolation_result(
        self,
        compliant: bool,
        violations: List[Dict[str, Any]],
        device_count: int,
        isolator_count: int,
    ) -> str:
        """Add a fault isolation result for compliance checking.

        Bridges nfpa72_engine.verify_fault_isolator_placement() results
        into the Rules Engine. Rule NFPA72-013 will fire if compliant=False.

        Reference: NFPA 72 §12.3.1
        """
        fact = fault_isolation_result_to_fact(
            compliant=compliant,
            violations=violations,
            device_count=device_count,
            isolator_count=isolator_count,
        )
        fid = self.engine.assert_fact(fact)
        logger.info(
            f"Fault isolation result added: devices={device_count}, isolators={isolator_count}, compliant={compliant}"
        )
        return fid

    def evaluate(self) -> ComplianceReport:
        """Run compliance evaluation and return a structured report."""
        logger.info("Starting NFPA 72 compliance evaluation for session %s", self.engine.session_id)
        try:
            self.engine.evaluate()

            # SAFETY FIX (CRITICAL-5): Sync standalone TMS with engine's
            # internal TMS after evaluation. The engine maintains _derived_from
            # and _supports dicts that track fact dependencies. We copy these
            # into the standalone TMS so that validate_tms_consistency() can
            # actually detect inconsistencies instead of always returning [].
            if self._sync_tms_after_evaluate:
                self._synchronize_tms()

            report = results_to_report(self.engine)
        except Exception as e:
            # FIX: Never silently fail to produce a report in a safety-critical system
            logger.critical("Compliance evaluation failed: %s", e, exc_info=True)
            return ComplianceReport(
                session_id=self.engine.session_id,
                is_safe=False,  # Conservative: assume unsafe
                critical_issues=[
                    {
                        "rule_id": "BRIDGE-EVAL-ERROR",
                        "message": f"Compliance evaluation failed: {e}",
                        "severity": "CRITICAL_SAFETY",
                    }
                ],
            )

        # Log summary
        logger.info(
            f"Compliance evaluation complete: "
            f"safe={report.is_safe}, "
            f"critical={len(report.critical_issues)}, "
            f"violations={len(report.violations)}, "
            f"checks={len(report.compliance_checks)}"
        )

        return report

    def get_audit_log(self) -> List[RuleAuditEntry]:
        """Get the complete audit log for this session."""
        return self.engine.get_audit_log()

    def explain(self, fact_id: str) -> Dict[str, Any]:
        """Explain how a fact was derived (truth maintenance)."""
        return self.engine.explain(fact_id)

    def reset(self) -> None:
        """Reset for a new analysis session."""
        self.engine.reset()
        self.tms.reset()  # FIX: was missing — stale TMS records survived reset

    def _synchronize_tms(self) -> None:
        """Synchronize the standalone TMS with the engine's internal TMS.

        SAFETY FIX (CRITICAL-5): The engine maintains _derived_from and
        _supports dictionaries internally that track fact dependencies.
        The standalone TMS was never fed these records, so
        validate_tms_consistency() always returned an empty list, giving
        a false sense of consistency. Now we copy the engine's dependency
        records into the standalone TMS so consistency checks are real.
        """
        # Rebuild standalone TMS from engine's internal state
        self.tms.reset()
        for derived_id, source_ids in self.engine._derived_from.items():
            # Find which rule produced this derived fact
            producing_rule = "unknown"
            for audit in self.engine.get_audit_log():
                if audit.fired and audit.result:
                    if derived_id in [f.fact_id for f in audit.result.asserted_facts]:
                        producing_rule = audit.rule_id
                        break
            self.tms.record_dependency(
                derived_fact_id=derived_id,
                supporting_fact_ids=source_ids,
                producing_rule_id=producing_rule,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# DUAL-ENGINE COMPLIANCE VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DualComplianceResult:
    """Result from running BOTH compliance engines in parallel.

    SAFETY PRINCIPLE: If the two engines disagree, the design MUST be REJECTED.
    A divergence means one engine found a violation the other missed — which
    could be a real life-safety issue. In a safety-critical system, we never
    accept a design where ANY engine reports a problem, even if the other passes.

    Reference: AGENTS.md Rule 6 (No Unauthorized Changes) and Rule 7 (Stop on Errors)
    """

    is_safe: bool
    rules_engine_safe: bool
    clause_engine_safe: bool
    engines_agree: bool
    divergence_details: List[str] = field(default_factory=list)
    rules_engine_report: Optional[ComplianceReport] = None
    clause_engine_violations: List[str] = field(default_factory=list)
    combined_violations: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Ensure is_safe is the AND of both engines AND agreement."""
        if not self.engines_agree:
            # Divergence = REJECT regardless of individual results
            self.is_safe = False


def dual_compliance_check(
    context: Dict[str, Any],
    session_id: str = "",
) -> DualComplianceResult:
    """Run BOTH compliance engines and REJECT on divergence.

    SAFETY: This is the highest-level compliance verification. It runs:
    1. ComplianceEngine (clause-mapped, validation/compliance_engine.py)
    2. NFPA72ComplianceChecker (declarative rules engine)

    If BOTH pass → PASS
    If EITHER fails → FAIL
    If they DISAGREE → FAIL with divergence flag

    Divergence indicates a bug in one of the engines — a serious safety issue.
    All divergences are logged at CRITICAL level for investigation.

    Args:
        context: Dictionary with compliance parameters (spacing_m, coverage_pct, etc.)
        session_id: Optional session ID for audit tracking

    Returns:
        DualComplianceResult with combined pass/fail and divergence info

    """
    from fireai.validation.compliance_engine import ComplianceEngine

    # ── Engine 1: Clause-mapped ComplianceEngine ──────────────────────────
    clause_engine = ComplianceEngine()
    clause_violations = clause_engine.validate(context)
    clause_safe = len(clause_violations) == 0

    # ── Engine 2: Declarative Rules Engine ────────────────────────────────
    rules_checker = NFPA72ComplianceChecker(session_id=session_id)

    # Add room context to rules engine if available
    if "ceiling_height_m" in context:
        rules_checker.add_room(
            room_id=context.get("room_id", "dual-check-room"),
            ceiling_height_m=context["ceiling_height_m"],
            detector_type=context.get("detector_type", "smoke"),
            room_area_m2=context.get("room_area_m2"),
        )

    # Add detector context if available
    if "spacing_m" in context:
        rules_checker.add_detector(
            detector_id="dual-check-detector",
            room_id=context.get("room_id", "dual-check-room"),
            detector_type=context.get("detector_type", "smoke"),
            x=0.0,
            y=0.0,
            listed_spacing_m=context["spacing_m"],
        )

    rules_report = rules_checker.evaluate()
    rules_safe = rules_report.is_safe

    # ── Check for divergence ──────────────────────────────────────────────
    engines_agree = clause_safe == rules_safe
    divergence_details = []

    if not engines_agree:
        if clause_safe and not rules_safe:
            divergence_details.append(
                "DIVERGENCE: Clause engine PASSED but Rules engine FAILED. "
                "The Rules engine found violations that the clause engine missed. "
                "This may indicate a gap in the clause engine's rule coverage."
            )
        elif not clause_safe and rules_safe:
            divergence_details.append(
                "DIVERGENCE: Clause engine FAILED but Rules engine PASSED. "
                "The clause engine found violations that the Rules engine missed. "
                "This may indicate a gap in the rules engine's rule coverage."
            )

        # Log at CRITICAL level — divergence is a safety concern
        for detail in divergence_details:
            logger.critical(
                "COMPLIANCE ENGINE DIVERGENCE DETECTED: %s "
                "Session: %s, Context: %s",
                detail, session_id, context,
            )

    # ── Combine violations ────────────────────────────────────────────────
    combined = list(clause_violations)
    for issue in rules_report.critical_issues:
        combined.append(f"[RULES-CRITICAL] {issue.get('message', 'Unknown')}")
    for issue in rules_report.violations:
        combined.append(f"[RULES-VIOLATION] {issue.get('message', 'Unknown')}")
    for detail in divergence_details:
        combined.append(f"[DIVERGENCE] {detail}")

    # ── Construct result ──────────────────────────────────────────────────
    # is_safe = True ONLY if BOTH engines pass AND they agree
    is_safe = clause_safe and rules_safe and engines_agree

    result = DualComplianceResult(
        is_safe=is_safe,
        rules_engine_safe=rules_safe,
        clause_engine_safe=clause_safe,
        engines_agree=engines_agree,
        divergence_details=divergence_details,
        rules_engine_report=rules_report,
        clause_engine_violations=clause_violations,
        combined_violations=combined,
    )

    logger.info(
        "Dual compliance check complete: safe=%s, clause_safe=%s, "
        "rules_safe=%s, agree=%s, violations=%d",
        result.is_safe, clause_safe, rules_safe, engines_agree, len(combined),
    )

    return result
