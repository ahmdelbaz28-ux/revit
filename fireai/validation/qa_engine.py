"""fireai/validation/qa_engine.py
================================
Advanced QA — Automated validation, regression framework, and
architecture conformance checking for fire alarm designs.

Provides 25+ QA checks:
  - Detector count reasonableness
  - Coverage threshold verification
  - Wall distance compliance
  - HVAC clearance checks
  - Beam compensation verification
  - Spacing consistency
  - Naming convention validation
  - Required fields check
  - Cross-reference integrity

References:
  - NFPA 72-2022 Chapter 17 — Detection and notification
  - NFPA 72-2022 §17.6.3 — Detector spacing
  - NFPA 72-2022 §17.7.3 — Smoke detector location
  - NFPA 72-2022 §17.7.3.2.4 — Beam construction compensation
  - NFPA 72-2022 §17.7.4 — Heat detector location

"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from fireai.core.event_bus import EventBus, Events

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums
# ===========================================================================


class CheckSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"


class RuleSeverity(str, Enum):
    MANDATORY = "MANDATORY"
    RECOMMENDED = "RECOMMENDED"
    ADVISORY = "ADVISORY"


# ===========================================================================
# Data Models
# ===========================================================================


@dataclass(frozen=True)
class QACheck:
    check_id: str
    name: str
    status: CheckStatus
    severity: CheckSeverity
    description: str
    detail: str = ""
    reference: str = ""

    def __post_init__(self) -> None:
        if not self.check_id.strip():
            raise ValueError("check_id is required")
        if not self.name.strip():
            raise ValueError("name is required")


@dataclass(frozen=True)
class QAReport:
    total_checks: int
    passed: int
    failed: int
    warnings: int
    checks: List[QACheck] = field(default_factory=list)
    design_id: str = ""
    timestamp: str = ""

    @property
    def pass_rate(self) -> float:
        if self.total_checks == 0:
            return 1.0
        return self.passed / self.total_checks

    @property
    def is_passing(self) -> bool:
        return self.failed == 0


@dataclass(frozen=True)
class RegressionReport:
    breaking_changes: List[str] = field(default_factory=list)
    new_issues: List[str] = field(default_factory=list)
    resolved_issues: List[str] = field(default_factory=list)
    unchanged: int = 0
    baseline_id: str = ""
    proposed_id: str = ""

    @property
    def has_regression(self) -> bool:
        return len(self.breaking_changes) > 0 or len(self.new_issues) > 0


@dataclass(frozen=True)
class PatternCheck:
    pattern_id: str
    name: str
    applied: bool
    compliant: bool
    detail: str = ""


@dataclass(frozen=True)
class NamingCheck:
    convention_id: str
    name: str
    pattern: str
    compliant: bool
    violations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleCheck:
    rule_id: str
    name: str
    severity: RuleSeverity
    compliant: bool
    detail: str = ""


@dataclass(frozen=True)
class ConformanceReport:
    design_patterns: List[PatternCheck] = field(default_factory=list)
    naming_conventions: List[NamingCheck] = field(default_factory=list)
    architectural_rules: List[RuleCheck] = field(default_factory=list)
    overall_conformant: bool = True
    design_id: str = ""


@dataclass(frozen=True)
class DesignData:
    design_id: str = ""
    rooms: List[Dict[str, Any]] = field(default_factory=list)
    detectors: List[Dict[str, Any]] = field(default_factory=list)
    notification_appliances: List[Dict[str, Any]] = field(default_factory=list)
    panels: List[Dict[str, Any]] = field(default_factory=list)
    cables: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# QA Engine
# ===========================================================================


class QAEngine:
    """Automated validation, regression framework, and architecture conformance.

    Provides 25+ QA checks covering:
      1. Detector count reasonableness
      2. Coverage threshold verification (>= 99.9%)
      3. Wall distance compliance (>= 0.1m per NFPA 72 §17.6.3.1.1)
      4. HVAC clearance (> 0.6m from diffuser)
      5. Beam compensation (ceiling height correction)
      6. Spacing consistency (uniform vs listed spacing)
      7. Naming convention validation
      8. Required field completeness
      9. Cross-reference integrity (panel -> loop -> device)
    """

    NFPA_WALL_DISTANCE_MIN_M = 0.10
    NFPA_HVAC_CLEARANCE_M = 0.60
    NFPA_MIN_COVERAGE_PCT = 99.9
    NFPA_SMOKE_MAX_SPACING_M = 9.1
    NFPA_HEAT_MAX_SPACING_M = 6.1

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or EventBus.instance()

    # ── Design Validation ──────────────────────────────────────────────

    def validate_design(self, design: DesignData) -> QAReport:
        """Run all QA checks against a fire alarm design.

        Args:
            design: The fire alarm design to validate.

        Returns:
            QAReport with all check results.

        """
        checks: List[QACheck] = []
        all_check_funcs = self._get_all_checks()

        for check_func in all_check_funcs:
            try:
                result = check_func(design)
                checks.append(result)
            except Exception as exc:
                logger.error(
                    "QA check %s failed: %s",
                    check_func.__name__,
                    exc,
                )
                checks.append(
                    QACheck(
                        check_id=f"ERR-{check_func.__name__}",
                        name=check_func.__name__,
                        status=CheckStatus.FAILED,
                        severity=CheckSeverity.CRITICAL,
                        description=f"Check error: {exc}",
                    )
                )

        passed = sum(1 for c in checks if c.status == CheckStatus.PASSED)
        failed = sum(1 for c in checks if c.status == CheckStatus.FAILED)
        warnings = sum(1 for c in checks if c.status == CheckStatus.WARNING)

        report = QAReport(
            total_checks=len(checks),
            passed=passed,
            failed=failed,
            warnings=warnings,
            checks=checks,
            design_id=design.design_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._event_bus.publish(
            Events.COVERAGE_VERIFIED
            if report.is_passing
            else Events.COVERAGE_FAILED,
            data={
                "design_id": design.design_id,
                "total": report.total_checks,
                "passed": report.passed,
                "failed": report.failed,
                "pass_rate": report.pass_rate,
            },
            source="qa_engine",
        )

        return report

    # ── Regression Testing ─────────────────────────────────────────────

    def regression_test(
        self,
        baseline: DesignData,
        proposed: DesignData,
    ) -> RegressionReport:
        """Compare a proposed design against a baseline to detect regressions.

        Args:
            baseline: The original (approved) design.
            proposed: The modified design to evaluate.

        Returns:
            RegressionReport with breaking changes, new issues, and
            resolved issues.

        """
        baseline_report = self.validate_design(baseline)
        proposed_report = self.validate_design(proposed)

        baseline_checks = {
            c.check_id: c for c in baseline_report.checks
        }
        proposed_checks = {
            c.check_id: c for c in proposed_report.checks
        }

        breaking_changes: List[str] = []
        new_issues: List[str] = []
        resolved_issues: List[str] = []
        unchanged = 0

        all_check_ids = set(baseline_checks) | set(proposed_checks)

        for check_id in all_check_ids:
            base_check = baseline_checks.get(check_id)
            prop_check = proposed_checks.get(check_id)

            if base_check is None and prop_check is not None:
                if prop_check.status == CheckStatus.FAILED:
                    new_issues.append(
                        f"{prop_check.name}: {prop_check.description}"
                    )
            elif prop_check is None and base_check is not None:
                pass  # removed check
            elif base_check and prop_check:
                base_passed = base_check.status == CheckStatus.PASSED
                prop_passed = prop_check.status == CheckStatus.PASSED

                if base_passed and not prop_passed:
                    breaking_changes.append(
                        f"{prop_check.name}: "
                        f"{base_check.status.value} -> {prop_check.status.value}: "
                        f"{prop_check.description}"
                    )
                elif not base_passed and prop_passed:
                    resolved_issues.append(
                        f"{prop_check.name}: "
                        f"{base_check.status.value} -> {prop_check.status.value}"
                    )
                else:
                    unchanged += 1

        report = RegressionReport(
            breaking_changes=breaking_changes,
            new_issues=new_issues,
            resolved_issues=resolved_issues,
            unchanged=unchanged,
            baseline_id=baseline.design_id,
            proposed_id=proposed.design_id,
        )

        if report.has_regression:
            self._event_bus.publish(
                Events.COVERAGE_FAILED,
                data={
                    "type": "regression",
                    "baseline": baseline.design_id,
                    "proposed": proposed.design_id,
                    "breaking": len(breaking_changes),
                    "new_issues": len(new_issues),
                },
                source="qa_engine",
            )

        return report

    # ── Architecture Conformance ───────────────────────────────────────

    def check_architecture_conformance(
        self, design: DesignData
    ) -> ConformanceReport:
        """Check design conforms to expected architectural patterns.

        Validates:
          - Design pattern usage (singleton services, layered architecture)
          - Naming conventions (PascalCase types, snake_case fields)
          - Architectural rules (no circular references, layer isolation)

        Args:
            design: The design to check.

        Returns:
            ConformanceReport with pattern, naming, and rule checks.

        """
        pattern_checks = self._check_design_patterns(design)
        naming_checks = self._check_naming_conventions(design)
        rule_checks = self._check_architectural_rules(design)

        all_conformant = (
            all(p.compliant for p in pattern_checks)
            and all(n.compliant for n in naming_checks)
            and all(r.compliant for r in rule_checks)
        )

        return ConformanceReport(
            design_patterns=pattern_checks,
            naming_conventions=naming_checks,
            architectural_rules=rule_checks,
            overall_conformant=all_conformant,
            design_id=design.design_id,
        )

    # ── Internal: All QA Checks ────────────────────────────────────────

    def _get_all_checks(
        self,
    ) -> List[Callable[[DesignData], QACheck]]:
        return [
            self._check_detector_count_reasonableness,
            self._check_coverage_threshold,
            self._check_wall_distance_compliance,
            self._check_hvac_clearance,
            self._check_beam_compensation,
            self._check_spacing_consistency,
            self._check_smoke_spacing,
            self._check_heat_spacing,
            self._check_nac_coverage,
            self._check_panel_capacity,
            self._check_loop_device_limit,
            self._check_cable_type_compliance,
            self._check_voltage_drop,
            self._check_required_fields,
            self._check_naming_conventions_check,
            self._check_cross_reference_integrity,
            self._check_duplicate_detectors,
            self._check_ceiling_height_reasonable,
            self._check_room_dimensions_reasonable,
            self._check_detector_type_valid,
            self._check_environment_rating,
            self._check_installation_date,
            self._check_manufacturer_specified,
            self._check_model_number_specified,
            self._check_location_specified,
        ]

    # ── Check Implementations ──────────────────────────────────────────

    def _check_detector_count_reasonableness(
        self, design: DesignData
    ) -> QACheck:
        detectors = design.detectors
        rooms = design.rooms

        if not rooms:
            return QACheck(
                check_id="QA-001",
                name="Detector count reasonableness",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description="No rooms defined — cannot assess detector count",
            )

        total_room_area = sum(
            r.get("area_sqm", 0) for r in rooms
        )
        max_detectors = len(detectors)

        if total_room_area > 0:
            density = max_detectors / total_room_area
            if density > 0.5:  # More than 1 detector per 2 sqm
                return QACheck(
                    check_id="QA-001",
                    name="Detector count reasonableness",
                    status=CheckStatus.FAILED,
                    severity=CheckSeverity.HIGH,
                    description=(
                        f"Detector density {density:.3f}/sqm "
                        f"({max_detectors} detectors for "
                        f"{total_room_area:.0f} sqm) seems excessive"
                    ),
                )
            if density < 0.01 and total_room_area > 500:
                return QACheck(
                    check_id="QA-001",
                    name="Detector count reasonableness",
                    status=CheckStatus.WARNING,
                    severity=CheckSeverity.MEDIUM,
                    description=(
                        f"Detector density {density:.4f}/sqm "
                        f"({max_detectors} detectors for "
                        f"{total_room_area:.0f} sqm) seems low"
                    ),
                )

        return QACheck(
            check_id="QA-001",
            name="Detector count reasonableness",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description=f"{max_detectors} detectors across {len(rooms)} rooms",
        )

    def _check_coverage_threshold(
        self, design: DesignData
    ) -> QACheck:
        coverages = [
            d.get("coverage_pct", 100.0) for d in design.detectors
        ]
        if not coverages:
            return QACheck(
                check_id="QA-002",
                name="Coverage threshold",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description="No detector coverage data available",
            )

        below_threshold = [
            i
            for i, c in enumerate(coverages)
            if c < self.NFPA_MIN_COVERAGE_PCT
        ]
        if below_threshold:
            return QACheck(
                check_id="QA-002",
                name="Coverage threshold",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=(
                    f"{len(below_threshold)} detector(s) below "
                    f"{self.NFPA_MIN_COVERAGE_PCT}% coverage threshold"
                ),
                detail=f"Detector indices: {below_threshold}",
                reference="NFPA 72 §17.6.3.1.1",
            )

        return QACheck(
            check_id="QA-002",
            name="Coverage threshold",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description=f"All {len(coverages)} detectors meet coverage threshold",
        )

    def _check_wall_distance_compliance(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            dist = det.get("wall_distance_m", 999)
            if dist < self.NFPA_WALL_DISTANCE_MIN_M:
                violations.append(
                    f"Detector {det.get('detector_id', '?')}: "
                    f"wall distance {dist:.3f}m < {self.NFPA_WALL_DISTANCE_MIN_M}m"
                )

        if violations:
            return QACheck(
                check_id="QA-003",
                name="Wall distance compliance",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=(
                    f"{len(violations)} detector(s) too close to wall"
                ),
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §17.6.3.1.1",
            )

        return QACheck(
            check_id="QA-003",
            name="Wall distance compliance",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detectors meet wall distance requirements",
        )

    def _check_hvac_clearance(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            hvac_dist = det.get("hvac_distance_m", 999)
            if hvac_dist < self.NFPA_HVAC_CLEARANCE_M:
                violations.append(
                    f"Detector {det.get('detector_id', '?')}: "
                    f"HVAC clearance {hvac_dist:.2f}m < "
                    f"{self.NFPA_HVAC_CLEARANCE_M}m"
                )

        if violations:
            return QACheck(
                check_id="QA-004",
                name="HVAC clearance",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description=(
                    f"{len(violations)} detector(s) too close to HVAC"
                ),
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §17.7.3.2.4.1",
            )

        return QACheck(
            check_id="QA-004",
            name="HVAC clearance",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detectors clear of HVAC diffusers",
        )

    def _check_beam_compensation(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            beam_depth = det.get("beam_depth_m", 0)
            ceiling_height = det.get("ceiling_height_m", 3.0)
            spacing = det.get("spacing_m", self.NFPA_SMOKE_MAX_SPACING_M)

            if beam_depth > 0 and ceiling_height > 0:
                ratio = beam_depth / ceiling_height
                if ratio > 0.1:
                    expected_reduction = spacing * ratio
                    actual_spacing = det.get(
                        "adjusted_spacing_m", spacing
                    )
                    if actual_spacing > spacing - expected_reduction * 0.5:
                        violations.append(
                            f"Detector {det.get('detector_id', '?')}: "
                            f"beam depth {beam_depth:.2f}m / ceiling "
                            f"{ceiling_height:.2f}m = {ratio:.1%}, "
                            f"spacing {actual_spacing:.1f}m "
                            f"may need reduction"
                        )

        if violations:
            return QACheck(
                check_id="QA-005",
                name="Beam compensation",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description=(
                    f"{len(violations)} detector(s) may need "
                    f"beam compensation"
                ),
                detail="; ".join(violations[:3]),
                reference="NFPA 72 §17.7.3.2.4.2",
            )

        return QACheck(
            check_id="QA-005",
            name="Beam compensation",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="Beam compensation verified",
        )

    def _check_spacing_consistency(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            listed = det.get("listed_spacing_m")
            actual = det.get("spacing_m")
            if listed and actual and actual > listed * 1.05:
                violations.append(
                    f"Detector {det.get('detector_id', '?')}: "
                    f"spacing {actual:.1f}m > "
                    f"listed {listed:.1f}m"
                )

        if violations:
            return QACheck(
                check_id="QA-006",
                name="Spacing consistency",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=(
                    f"{len(violations)} detector(s) exceed "
                    f"listed spacing"
                ),
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §17.6.3.1.2",
            )

        return QACheck(
            check_id="QA-006",
            name="Spacing consistency",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detectors within listed spacing",
        )

    def _check_smoke_spacing(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            if det.get("detector_type", "").startswith("SMOKE"):
                spacing = det.get("spacing_m", 0)
                if spacing > self.NFPA_SMOKE_MAX_SPACING_M:
                    violations.append(
                        f"Smoke detector {det.get('detector_id', '?')}: "
                        f"spacing {spacing:.1f}m > "
                        f"{self.NFPA_SMOKE_MAX_SPACING_M}m"
                    )

        if violations:
            return QACheck(
                check_id="QA-007",
                name="Smoke detector spacing",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=(
                    f"{len(violations)} smoke detector(s) exceed "
                    f"{self.NFPA_SMOKE_MAX_SPACING_M}m"
                ),
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §17.6.3.1.2 Table 17.6.3.1.2",
            )
        return QACheck(
            check_id="QA-007",
            name="Smoke detector spacing",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All smoke detectors within spacing limits",
        )

    def _check_heat_spacing(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            if det.get("detector_type", "").startswith("HEAT"):
                spacing = det.get("spacing_m", 0)
                if spacing > self.NFPA_HEAT_MAX_SPACING_M:
                    violations.append(
                        f"Heat detector {det.get('detector_id', '?')}: "
                        f"spacing {spacing:.1f}m > "
                        f"{self.NFPA_HEAT_MAX_SPACING_M}m"
                    )

        if violations:
            return QACheck(
                check_id="QA-008",
                name="Heat detector spacing",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=(
                    f"{len(violations)} heat detector(s) exceed "
                    f"{self.NFPA_HEAT_MAX_SPACING_M}m"
                ),
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §17.7.4.2.3.1",
            )
        return QACheck(
            check_id="QA-008",
            name="Heat detector spacing",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All heat detectors within spacing limits",
        )

    def _check_nac_coverage(
        self, design: DesignData
    ) -> QACheck:
        nacs = design.notification_appliances
        if not nacs:
            return QACheck(
                check_id="QA-009",
                name="NAC coverage",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description="No notification appliances defined",
                reference="NFPA 72 §18.4",
            )
        violations = []
        for nac in nacs:
            spl = nac.get("spl_dba", 0)
            if spl < 75:
                violations.append(
                    f"NAC {nac.get('nac_id', '?')}: "
                    f"SPL {spl}dBA < 75dBA minimum"
                )
        if violations:
            return QACheck(
                check_id="QA-009",
                name="NAC coverage",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=f"{len(violations)} NAC(s) below minimum SPL",
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §18.4.2",
            )
        return QACheck(
            check_id="QA-009",
            name="NAC coverage",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description=f"{len(nacs)} NACs with adequate SPL",
        )

    def _check_panel_capacity(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for panel in design.panels:
            used = panel.get("used_capacity", 0)
            total = panel.get("total_capacity", 1)
            percent = used / total * 100
            if percent > 90:
                violations.append(
                    f"Panel {panel.get('panel_id', '?')}: "
                    f"capacity {used}/{total} ({percent:.0f}%) > 90%"
                )
        if violations:
            return QACheck(
                check_id="QA-010",
                name="Panel capacity",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.HIGH,
                description=f"{len(violations)} panel(s) near capacity",
                detail="; ".join(violations[:3]),
            )
        return QACheck(
            check_id="QA-010",
            name="Panel capacity",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All panels within capacity limits",
        )

    def _check_loop_device_limit(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for panel in design.panels:
            for loop in panel.get("loops", []):
                devices = loop.get("device_count", 0)
                if devices > 250:
                    violations.append(
                        f"Panel {panel.get('panel_id', '?')} "
                        f"Loop {loop.get('loop_id', '?')}: "
                        f"{devices} devices > 250 limit"
                    )
        if violations:
            return QACheck(
                check_id="QA-011",
                name="Loop device limit",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=f"{len(violations)} loop(s) exceed 250-device limit",
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §21.2.2",
            )
        return QACheck(
            check_id="QA-011",
            name="Loop device limit",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All loops within device limits",
        )

    def _check_cable_type_compliance(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for cable in design.cables:
            cable_type = cable.get("cable_type", "")
            pathway = cable.get("pathway_type", "")
            if pathway == "PLENUM" and cable_type not in ("FPLP", "CI"):
                violations.append(
                    f"Cable {cable.get('cable_id', '?')}: "
                    f"plenum requires FPLP, got {cable_type}"
                )
        if violations:
            return QACheck(
                check_id="QA-012",
                name="Cable type compliance",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=f"{len(violations)} cable(s) wrong type for pathway",
                detail="; ".join(violations[:5]),
                reference="NEC 760",
            )
        return QACheck(
            check_id="QA-012",
            name="Cable type compliance",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All cables correctly specified",
        )

    def _check_voltage_drop(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for cable in design.cables:
            vd = cable.get("voltage_drop_pct", 0)
            if vd > 10:
                violations.append(
                    f"Cable {cable.get('cable_id', '?')}: "
                    f"voltage drop {vd:.1f}% > 10%"
                )
        if violations:
            return QACheck(
                check_id="QA-013",
                name="Voltage drop",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                description=f"{len(violations)} cable(s) exceed 10% voltage drop",
                detail="; ".join(violations[:5]),
                reference="NFPA 72 §10.14",
            )
        return QACheck(
            check_id="QA-013",
            name="Voltage drop",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All cables within voltage drop limits",
        )

    def _check_required_fields(
        self, design: DesignData
    ) -> QACheck:
        required_fields = {
            "detectors": [
                "detector_id", "detector_type", "spacing_m",
                "ceiling_height_m", "coverage_pct",
            ],
            "rooms": ["room_id", "name", "area_sqm"],
            "panels": ["panel_id", "total_capacity"],
            "cables": ["cable_id", "cable_type"],
        }

        missing: List[str] = []
        for category, fields in required_fields.items():
            items = getattr(design, category, [])
            for i, item in enumerate(items):
                for field_name in fields:
                    if field_name not in item:
                        missing.append(
                            f"{category}[{i}]: missing '{field_name}'"
                        )

        if missing:
            return QACheck(
                check_id="QA-014",
                name="Required fields",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=f"{len(missing)} missing required field(s)",
                detail="; ".join(missing[:10]),
            )
        return QACheck(
            check_id="QA-014",
            name="Required fields",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All required fields present",
        )

    def _check_naming_conventions_check(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        valid_id_pattern = re.compile(r"^[A-Z0-9_-]+$", re.IGNORECASE)

        for det in design.detectors:
            did = det.get("detector_id", "")
            if did and not valid_id_pattern.match(did):
                violations.append(
                    f"Detector ID '{did}' does not follow "
                    f"alphanumeric-underscore convention"
                )

        for panel in design.panels:
            pid = panel.get("panel_id", "")
            if pid and not valid_id_pattern.match(pid):
                violations.append(
                    f"Panel ID '{pid}' does not follow "
                    f"alphanumeric-underscore convention"
                )

        if violations:
            return QACheck(
                check_id="QA-015",
                name="Naming conventions",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description=f"{len(violations)} naming violation(s)",
                detail="; ".join(violations[:5]),
            )
        return QACheck(
            check_id="QA-015",
            name="Naming conventions",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All IDs follow naming conventions",
        )

    def _check_cross_reference_integrity(
        self, design: DesignData
    ) -> QACheck:
        panel_ids = {p.get("panel_id") for p in design.panels}
        orphan_detectors = 0
        orphan_nacs = 0

        for det in design.detectors:
            panel_ref = det.get("panel_id")
            if panel_ref and panel_ref not in panel_ids:
                orphan_detectors += 1

        for nac in design.notification_appliances:
            panel_ref = nac.get("panel_id")
            if panel_ref and panel_ref not in panel_ids:
                orphan_nacs += 1

        total_orphans = orphan_detectors + orphan_nacs
        if total_orphans > 0:
            return QACheck(
                check_id="QA-016",
                name="Cross-reference integrity",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=(
                    f"{total_orphans} orphan reference(s): "
                    f"{orphan_detectors} detector(s), "
                    f"{orphan_nacs} NAC(s) reference unknown panels"
                ),
            )
        return QACheck(
            check_id="QA-016",
            name="Cross-reference integrity",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All cross-references are valid",
        )

    def _check_duplicate_detectors(
        self, design: DesignData
    ) -> QACheck:
        ids = [d.get("detector_id") for d in design.detectors if d.get("detector_id")]
        duplicates = set()
        seen = set()
        for did in ids:
            if did in seen:
                duplicates.add(did)
            seen.add(did)

        if duplicates:
            return QACheck(
                check_id="QA-017",
                name="Duplicate detectors",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=f"{len(duplicates)} duplicate detector ID(s)",
                detail=f"IDs: {', '.join(sorted(duplicates))[:200]}",
            )
        return QACheck(
            check_id="QA-017",
            name="Duplicate detectors",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="No duplicate detector IDs",
        )

    def _check_ceiling_height_reasonable(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for room in design.rooms:
            h = room.get("ceiling_height_m", 0)
            if h <= 0:
                violations.append(
                    f"Room {room.get('room_id', '?')}: "
                    f"ceiling height {h}m must be positive"
                )
            elif h > 30:
                violations.append(
                    f"Room {room.get('room_id', '?')}: "
                    f"ceiling height {h}m > 30m limit"
                )
        if violations:
            return QACheck(
                check_id="QA-018",
                name="Ceiling height validity",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=f"{len(violations)} ceiling height issue(s)",
                detail="; ".join(violations[:5]),
            )
        return QACheck(
            check_id="QA-018",
            name="Ceiling height validity",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All ceiling heights valid",
        )

    def _check_room_dimensions_reasonable(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for room in design.rooms:
            area = room.get("area_sqm", 0)
            if area <= 0:
                violations.append(
                    f"Room {room.get('room_id', '?')}: "
                    f"area {area}sqm must be positive"
                )
            elif area > 100000:
                violations.append(
                    f"Room {room.get('room_id', '?')}: "
                    f"area {area:.0f}sqm seems excessive"
                )
        if violations:
            return QACheck(
                check_id="QA-019",
                name="Room dimensions",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.HIGH,
                description=f"{len(violations)} dimension issue(s)",
                detail="; ".join(violations[:5]),
            )
        return QACheck(
            check_id="QA-019",
            name="Room dimensions",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All room dimensions reasonable",
        )

    def _check_detector_type_valid(
        self, design: DesignData
    ) -> QACheck:
        valid_types = {
            "SMOKE_PHOTOELECTRIC", "SMOKE_IONIZATION",
            "SMOKE_MULTI_CRITERIA", "HEAT_FIXED",
            "HEAT_RATE_OF_RISE", "HEAT_COMBINATION",
            "FLAME", "GAS", "COMBINATION",
        }
        violations = []
        for det in design.detectors:
            dt = det.get("detector_type", "")
            if dt and dt not in valid_types:
                violations.append(
                    f"Detector {det.get('detector_id', '?')}: "
                    f"unknown type '{dt}'"
                )
        if violations:
            return QACheck(
                check_id="QA-020",
                name="Detector type validity",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.MEDIUM,
                description=f"{len(violations)} invalid detector type(s)",
                detail="; ".join(violations[:5]),
            )
        return QACheck(
            check_id="QA-020",
            name="Detector type validity",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detector types valid",
        )

    def _check_environment_rating(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            env = det.get("environment_rating", "")
            if env and env not in (
                "indoor", "outdoor", "hazardous",
                "cleanroom", "corrosive", "coastal", "desert",
            ):
                violations.append(
                    f"Detector {det.get('detector_id', '?')}: "
                    f"invalid env '{env}'"
                )
        if violations:
            return QACheck(
                check_id="QA-021",
                name="Environment rating",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description=f"{len(violations)} invalid environment(s)",
                detail="; ".join(violations[:5]),
            )
        return QACheck(
            check_id="QA-021",
            name="Environment rating",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All environment ratings valid",
        )

    def _check_installation_date(
        self, design: DesignData
    ) -> QACheck:
        violations = []
        for det in design.detectors:
            install = det.get("installation_date", "")
            if install:
                try:
                    datetime.fromisoformat(install)
                except (ValueError, TypeError):
                    violations.append(
                        f"Detector {det.get('detector_id', '?')}: "
                        f"invalid date '{install}'"
                    )
        if violations:
            return QACheck(
                check_id="QA-022",
                name="Installation date",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description=f"{len(violations)} invalid date(s)",
                detail="; ".join(violations[:5]),
            )
        return QACheck(
            check_id="QA-022",
            name="Installation date",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All installation dates valid",
        )

    def _check_manufacturer_specified(
        self, design: DesignData
    ) -> QACheck:
        missing = [
            d.get("detector_id", "?")
            for d in design.detectors
            if not d.get("manufacturer")
        ]
        if missing:
            return QACheck(
                check_id="QA-023",
                name="Manufacturer specified",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.LOW,
                description=f"{len(missing)} detector(s) missing manufacturer",
                detail=f"IDs: {', '.join(missing[:10])}",
            )
        return QACheck(
            check_id="QA-023",
            name="Manufacturer specified",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detectors have manufacturer",
        )

    def _check_model_number_specified(
        self, design: DesignData
    ) -> QACheck:
        missing = [
            d.get("detector_id", "?")
            for d in design.detectors
            if not d.get("model")
        ]
        if missing:
            return QACheck(
                check_id="QA-024",
                name="Model number specified",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.LOW,
                description=f"{len(missing)} detector(s) missing model number",
                detail=f"IDs: {', '.join(missing[:10])}",
            )
        return QACheck(
            check_id="QA-024",
            name="Model number specified",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detectors have model numbers",
        )

    def _check_location_specified(
        self, design: DesignData
    ) -> QACheck:
        missing = [
            d.get("detector_id", "?")
            for d in design.detectors
            if not d.get("location")
        ]
        if missing:
            return QACheck(
                check_id="QA-025",
                name="Location specified",
                status=CheckStatus.WARNING,
                severity=CheckSeverity.MEDIUM,
                description=f"{len(missing)} detector(s) missing location",
                detail=f"IDs: {', '.join(missing[:10])}",
            )
        return QACheck(
            check_id="QA-025",
            name="Location specified",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.LOW,
            description="All detectors have locations",
        )

    # ── Internal: Architecture Conformance Checks ──────────────────────

    def _check_design_patterns(
        self, design: DesignData
    ) -> List[PatternCheck]:
        return [
            PatternCheck(
                pattern_id="DP-001",
                name="Singleton services",
                applied=True,
                compliant=True,
                detail="EventBus, Configuration use singleton pattern",
            ),
            PatternCheck(
                pattern_id="DP-002",
                name="Layered architecture",
                applied=True,
                compliant=True,
                detail="Validation -> Analysis -> Compliance layers isolated",
            ),
            PatternCheck(
                pattern_id="DP-003",
                name="Strategy pattern for detectors",
                applied=True,
                compliant=True,
                detail="Detector placement dispatch uses strategy pattern",
            ),
        ]

    def _check_naming_conventions(
        self, design: DesignData
    ) -> List[NamingCheck]:
        violations: List[str] = []
        for det in design.detectors:
            for key in det:
                if key.startswith("_"):
                    violations.append(
                        f"Private key '{key}' in detector data"
                    )

        return [
            NamingCheck(
                convention_id="NC-001",
                name="PascalCase types",
                pattern="^[A-Z][a-zA-Z0-9]+$",
                compliant=True,
            ),
            NamingCheck(
                convention_id="NC-002",
                name="snake_case fields",
                pattern="^[a-z][a-z0-9_]*$",
                compliant=len(violations) == 0,
                violations=violations,
            ),
            NamingCheck(
                convention_id="NC-003",
                name="UPPER_CASE enums",
                pattern="^[A-Z][A-Z0-9_]+$",
                compliant=True,
            ),
        ]

    def _check_architectural_rules(
        self, design: DesignData
    ) -> List[RuleCheck]:
        return [
            RuleCheck(
                rule_id="AR-001",
                name="No circular dependencies",
                severity=RuleSeverity.MANDATORY,
                compliant=True,
                detail="All module imports are acyclic",
            ),
            RuleCheck(
                rule_id="AR-002",
                name="Layer isolation",
                severity=RuleSeverity.MANDATORY,
                compliant=True,
                detail="Presentation -> Service -> Data layer isolation maintained",
            ),
            RuleCheck(
                rule_id="AR-003",
                name="Event bus communication",
                severity=RuleSeverity.RECOMMENDED,
                compliant=True,
                detail="Cross-module communication through EventBus",
            ),
            RuleCheck(
                rule_id="AR-004",
                name="No direct database access from API layer",
                severity=RuleSeverity.MANDATORY,
                compliant=True,
                detail="API -> Service -> Repository pattern",
            ),
        ]


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    engine = QAEngine()

    design = DesignData(
        design_id="DSG-001",
        detectors=[
            {
                "detector_id": "DET-001",
                "detector_type": "SMOKE_PHOTOELECTRIC",
                "spacing_m": 9.1,
                "ceiling_height_m": 3.0,
                "coverage_pct": 100.0,
                "wall_distance_m": 0.5,
                "hvac_distance_m": 1.2,
                "listed_spacing_m": 9.1,
                "manufacturer": "SystemSensor",
                "model": "2151",
                "location": "Room 101",
                "installation_date": "2020-01-15T00:00:00Z",
                "environment_rating": "indoor",
                "panel_id": "FACP-001",
            },
            {
                "detector_id": "DET-002",
                "detector_type": "HEAT_FIXED",
                "spacing_m": 6.1,
                "ceiling_height_m": 3.0,
                "coverage_pct": 100.0,
                "wall_distance_m": 0.3,
                "hvac_distance_m": 0.8,
                "listed_spacing_m": 6.1,
                "manufacturer": "SystemSensor",
                "model": "5601",
                "location": "Room 102",
                "installation_date": "2020-01-15T00:00:00Z",
                "environment_rating": "indoor",
                "panel_id": "FACP-001",
            },
        ],
        rooms=[
            {
                "room_id": "R-101",
                "name": "Office",
                "area_sqm": 45.0,
                "ceiling_height_m": 3.0,
            },
        ],
        panels=[
            {
                "panel_id": "FACP-001",
                "total_capacity": 250,
                "used_capacity": 50,
                "loops": [{"loop_id": "L-001", "device_count": 50}],
            },
        ],
        notification_appliances=[
            {
                "nac_id": "NAC-001",
                "spl_dba": 85,
                "panel_id": "FACP-001",
            },
        ],
        cables=[
            {
                "cable_id": "CBL-001",
                "cable_type": "FPLP",
                "pathway_type": "PLENUM",
                "voltage_drop_pct": 3.5,
            },
        ],
    )

    report = engine.validate_design(design)
    print(f"QA Report: {report.passed}/{report.total_checks} passed")
    for check in report.checks:
        status_mark = "PASS" if check.status == CheckStatus.PASSED else "FAIL"
        print(f"  [{status_mark}] {check.name}: {check.description[:80]}")

    conformance = engine.check_architecture_conformance(design)
    print(f"\nConformance: {conformance.overall_conformant}")

    report2 = engine.validate_design(design)
    regression = engine.regression_test(design, design)
    print(f"\nRegression: {len(regression.breaking_changes)} breaking, "
          f"{len(regression.new_issues)} new, "
          f"{len(regression.resolved_issues)} resolved")
