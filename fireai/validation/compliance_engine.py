"""Clause-Mapped Compliance Engine — NFPA 72 / NEC Validation

PDF Audit Phase 3: Domain Verification
Per "From Prototype to Production-Grade" §Phase 3, Appendix B:
"A new validation module should be developed that acts as a post-processor
to the main calculation engine. This engine will take the final design and
cross-reference every parameter against the NFPA 72 and NEC compliance
matrix."

Usage:
    from fireai.validation.compliance_engine import ComplianceEngine

    context = {
        'spacing_m': 9.1,
        'max_spacing_for_height': 9.1,
        'v_drop_percent': 2.5,
        'ceiling_height_m': 3.0,
        'ceiling_type': 'flat',
    }
    engine = ComplianceEngine()
    violations = engine.validate(context)
    if violations:
        for v in violations:
            print(f"  - {v}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComplianceRule:
    """A rule that defines a valid state for a calculation."""

    clause_id: str
    description: str
    validator: Callable[[Dict[str, Any]], bool]
    remediation: str
    severity: str = "HIGH"


class ComplianceEngine:
    """An engine to evaluate a calculation context against compliance rules.

    Each rule maps to a specific NFPA 72 or NEC clause.
    """

    def __init__(self):
        self.rules: List[ComplianceRule] = self._define_rules()

    def _define_rules(self) -> List[ComplianceRule]:
        """Define all compliance rules from the NFPA 72 / NEC matrix."""
        return [
            # ── NFPA 72 Chapter 17 — Detector Spacing ─────────────────
            ComplianceRule(
                clause_id="NFPA72:17.6.3.1.2",
                description="Detector spacing vs. ceiling height",
                validator=lambda ctx: ctx.get('spacing_m', float('inf')) <= ctx.get('max_spacing_for_height', 0) * 1.001,
                remediation="Reduce spacing or add detectors per Table 17.6.3.1.2",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="NFPA72:17.6.3.1.2(a)",
                description="Sloped ceiling spacing reduction",
                validator=lambda ctx: (
                    ctx.get('ceiling_type') != 'sloped'
                    or ctx.get('spacing_m', float('inf')) <= 6.4
                ),
                remediation="Sloped ceiling: reduce spacing to <= 6.4m (21ft) per Table 17.6.3.1.2(a)",
                severity="HIGH",
            ),
            ComplianceRule(
                clause_id="NFPA72:17.6.3.1.1",
                description="Minimum coverage >= 99.9%",
                validator=lambda ctx: ctx.get('coverage_pct', 0) >= 99.9,
                remediation="Add detectors to achieve >= 99.9% area coverage per 17.6.3.1.1",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="NFPA72:17.7.4.2.3.1",
                description="Coverage radius R = 0.7 x S (for square grid verification)",
                validator=lambda ctx: (
                    ctx.get('radius_m', 0) <= ctx.get('spacing_m', 0) * 0.701
                    and ctx.get('radius_m', 0) >= ctx.get('spacing_m', 999) * 0.699
                ),
                remediation="Verify R = 0.7 x S per 17.7.4.2.3.1 (coverage radius for circular detection on square grid)",
                severity="HIGH",
            ),
            ComplianceRule(
                clause_id="NFPA72:17.6.3.1.1.wall_max",
                description="Max wall distance = S/2 (half the listed spacing)",
                validator=lambda ctx: (
                    ctx.get('wall_distance_m', float('inf')) <= ctx.get('spacing_m', 0) * 0.501
                ),
                remediation="Reduce wall distance to <= S/2 per NFPA 72 §17.6.3.1.1. For smoke at h<=3m: S=9.1m, wall max=4.55m",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="NFPA72:17.6.3.1.1.wall_min",
                description="Min wall distance = 4 inches (0.1016m, dead air space)",
                validator=lambda ctx: (
                    ctx.get('wall_distance_m', 0) >= 0.1016
                ),
                remediation="Move detector at least 0.1016m (4 inches) from wall per NFPA 72 §17.6.3.1.1 (dead air space)",
                severity="HIGH",
            ),

            # ── NFPA 72 Chapter 10 — Circuits ─────────────────────────
            ComplianceRule(
                clause_id="NFPA72:10.14",
                description="Terminal voltage >= 16VDC at end-of-line",
                validator=lambda ctx: ctx.get('terminal_voltage_v', 0) >= 16.0,
                remediation="Increase conductor size or reduce circuit length per 10.14",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="NEC:210.19(A)(1)",
                description="Branch circuit voltage drop <= 3%",
                validator=lambda ctx: ctx.get('v_drop_percent', 100) <= 3.0,
                remediation="Increase conductor size or reduce circuit length per NEC 210.19(A)(1)",
                severity="HIGH",
            ),
            ComplianceRule(
                clause_id="NEC:215.2(A)(2)",
                description="Total voltage drop (feeder + branch) <= 5%",
                validator=lambda ctx: ctx.get('v_drop_total_percent', ctx.get('v_drop_percent', 100)) <= 5.0,
                remediation="Increase feeder or branch conductor size per NEC 215.2(A)(2)",
                severity="HIGH",
            ),

            # ── NFPA 72 Chapter 21 — Elevator Shunt Trip ───────────────
            ComplianceRule(
                clause_id="NFPA72:21.4.2",
                description="1:1 sprinkler-to-HD mapping for shunt trip",
                validator=lambda ctx: ctx.get('has_unguarded_sprinkler', False) is False,
                remediation="Each sprinkler within 0.6m of heat detector must have dedicated HD per 21.4.2",
                severity="CRITICAL",
            ),

            # ── NFPA 92 — Stairwell Smoke Control ─────────────────────
            ComplianceRule(
                clause_id="NFPA92:6.4.2",
                description="Stairwell pressure <= 85 Pa (door entrapment limit)",
                validator=lambda ctx: ctx.get('design_pressure_pa', 0) <= 85.0,
                remediation="Reduce pressurization to <= 85 Pa per NFPA 92 6.4.2",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="NFPA92:6.4",
                description="Stairwell pressure >= 25 Pa (smoke infiltration limit)",
                validator=lambda ctx: ctx.get('design_pressure_pa', 100) >= 25.0 if ctx.get('pressurization_required', False) else True,
                remediation="Increase pressurization to >= 25 Pa per NFPA 92 6.4",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="NFPA101:7.2.3.9",
                description="Stairwell > 75ft requires pressurization",
                validator=lambda ctx: (
                    not ctx.get('pressurization_required', False)
                    or ctx.get('building_height_m', 0) > 22.86
                ),
                remediation="Stairwells exceeding 75ft (22.86m) require pressurization per NFPA 101 7.2.3.9",
                severity="HIGH",
            ),

            # ── IEC 60079-10-1 — Hazardous Area Classification ─────────
            ComplianceRule(
                clause_id="IEC60079-10-1:4.3",
                description="CONTINUOUS releases must not be relaxed by HIGH ventilation",
                validator=lambda ctx: (
                    ctx.get('release_grade') != 'CONTINUOUS'
                    or ctx.get('zone_delta', 0) <= 0
                ),
                remediation="CONTINUOUS releases cannot be relaxed by ventilation per IEC 4.3",
                severity="CRITICAL",
            ),
            ComplianceRule(
                clause_id="IEC60079-0:5",
                description="Zone 0 requires EPL Ga equipment only",
                validator=lambda ctx: (
                    ctx.get('zone_type') != 'ZONE_0'
                    or ctx.get('epl', '') in ('ia', 'ma', 's', 'Ga')
                ),
                remediation="Zone 0 requires EPL Ga equipment (ia, ma, s) per IEC 60079-0 5",
                severity="CRITICAL",
            ),
        ]

    def validate(self, context: Dict[str, Any]) -> List[str]:
        """Run all compliance checks and return a list of violation messages."""
        violations = []
        logger.info("Starting compliance validation against %d rules.", len(self.rules))

        for rule in self.rules:
            try:
                if not rule.validator(context):
                    violation_msg = (
                        f"[{rule.severity}] COMPLIANCE VIOLATION [{rule.clause_id}]: "
                        f"{rule.description}. "
                        f"REMEDIAL ACTION: {rule.remediation}"
                    )
                    logger.warning(violation_msg)
                    violations.append(violation_msg)
            except Exception as e:
                logger.error("Error during validation of rule %s: %s", rule.clause_id, e)
                violations.append(
                    f"[{rule.severity}] VALIDATION ERROR [{rule.clause_id}]: Could not validate - {e}"
                )

        if not violations:
            logger.info("All %d compliance checks passed.", len(self.rules))
        else:
            logger.warning("%d compliance violations detected.", len(violations))

        return violations

    def validate_and_report(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run validation and return structured report."""
        violations = self.validate(context)
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "violation_count": len(violations),
            "rules_checked": len(self.rules),
            "compliance_percentage": round(
                (1 - len(violations) / len(self.rules)) * 100, 1
            ) if self.rules else 100.0,
        }
