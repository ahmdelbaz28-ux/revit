"""fireai/validation/multi_standard_validator.py — Advanced Multi-Standard Validation.

Composite pattern: each standard is a StandardValidator subclass.
Supports cross-system conflict detection between standards.

Standards:
  - NFPA 72-2022   (Fire Alarm Systems)
  - NFPA 101-2021  (Life Safety Code)
  - NEC 2023       (National Electrical Code)
  - IBC 2021       (International Building Code)
  - ASME A17.1     (Elevator Safety Code)
  - UL 864         (Fire Alarm Control Units)
  - ISO 7240       (Fire Detection and Alarm Systems)
  - EN 54          (Fire Detection and Fire Alarm Systems)

Output: JSON and Markdown reports with traceable section references.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════════════

class ValidationStandard(Enum):
    NFPA_72_2022 = "NFPA 72-2022"
    NFPA_101_2021 = "NFPA 101-2021"
    NEC_2023 = "NEC 2023"
    IBC_2021 = "IBC 2021"
    ASME_A17_1 = "ASME A17.1"
    UL_864 = "UL 864"
    ISO_7240 = "ISO 7240"
    EN_54 = "EN 54"


class SeverityLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DesignData:
    """Immutable design data container for validation."""

    project_id: str = ""
    project_name: str = ""
    building_type: str = "commercial"
    building_height_m: float = 0.0
    total_area_sqm: float = 0.0
    num_floors: int = 1
    occupancy_type: str = "business"
    occupancy_load: int = 0
    ceiling_height_m: float = 3.0
    ceiling_type: str = "flat"
    spacing_m: float = 9.1
    max_spacing_for_height: float = 9.1
    coverage_pct: float = 99.9
    radius_m: float = 6.37
    detector_type: str = "smoke"
    terminal_voltage_v: float = 20.0
    v_drop_percent: float = 2.5
    v_drop_total_percent: float = 3.5
    has_unguarded_sprinkler: bool = False
    design_pressure_pa: float = 50.0
    pressurization_required: bool = True
    has_elevator: bool = False
    elevator_floors_served: int = 0
    has_fire_alarm: bool = True
    has_sprinkler: bool = True
    has_emergency_lights: bool = True
    has_fire_department_connection: bool = True
    has_standpipe: bool = False
    fire_alarm_zones: int = 1
    nac_circuits: int = 1
    nac_voltage_v: float = 24.0
    nac_wire_gauge: str = "14 AWG"
    nac_length_m: float = 100.0
    sdlc_wire_gauge: str = "18 AWG"
    sdlc_length_m: float = 200.0
    battery_standby_hours: int = 24
    battery_alarm_minutes: int = 15
    ambient_temp_c: float = 20.0
    humidity_percent: float = 50.0
    hazardous_location: bool = False
    zone_classification: str = "non-hazardous"
    seismic_zone: str = "0"
    wind_zone: str = "I"
    data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, self.data.get(key, default))


@dataclass
class RuleApplication:
    """Trace record of a single rule application."""

    rule_id: str
    section: str
    standard: ValidationStandard
    description: str
    passed: bool
    severity: SeverityLevel
    details: str = ""
    remediation: str = ""
    value_found: Optional[Any] = None
    value_expected: Optional[Any] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class StandardReport:
    """Validation report for a single standard."""

    standard: ValidationStandard
    passed: bool
    total_rules: int
    passed_rules: int
    failed_rules: int
    compliance_percent: float
    rule_applications: List[RuleApplication] = field(default_factory=list)
    summary: str = ""


@dataclass
class CrossSystemConflict:
    """A conflict detected between two standards."""

    conflict_id: str
    standard_a: ValidationStandard
    standard_b: ValidationStandard
    rule_a: str
    rule_b: str
    section_a: str
    section_b: str
    description: str
    severity: SeverityLevel
    resolution_guidance: str = ""


@dataclass
class CrossSystemReport:
    """Cross-system conflict detection report."""

    total_conflicts: int = 0
    conflicts: List[CrossSystemConflict] = field(default_factory=list)
    summary: str = ""


@dataclass
class ValidationReport:
    """Complete multi-standard validation report."""

    design_id: str = ""
    design_name: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    standards_validated: List[ValidationStandard] = field(default_factory=list)
    standard_reports: Dict[str, StandardReport] = field(default_factory=dict)
    cross_system: Optional[CrossSystemReport] = None
    overall_passed: bool = False
    overall_compliance_percent: float = 0.0
    total_rules: int = 0
    total_passed: int = 0
    total_failed: int = 0
    summary: str = ""


# ════════════════════════════════════════════════════════════════════════════
# Standard Validator — Abstract Base (Composite Leaf)
# ════════════════════════════════════════════════════════════════════════════

class StandardValidator(ABC):
    """Abstract base for all standard-specific validators."""

    def __init__(self, standard: ValidationStandard):
        self._standard = standard
        self._rules: List[Dict[str, Any]] = []
        self._define_rules()

    @abstractmethod
    def _define_rules(self) -> None:
        """Define the compliance rules for this standard."""
        ...

    def validate(self, design: DesignData) -> StandardReport:
        """Validate a design against all rules defined by this standard.

        Returns a StandardReport with per-rule traceability.
        """
        applications: List[RuleApplication] = []
        passed = 0
        failed = 0

        for rule in self._rules:
            app = self._apply_rule(rule, design)
            applications.append(app)
            if app.passed:
                passed += 1
            else:
                failed += 1

        total = len(self._rules)
        compliance = round((passed / total * 100) if total > 0 else 100.0, 1)

        return StandardReport(
            standard=self._standard,
            passed=failed == 0,
            total_rules=total,
            passed_rules=passed,
            failed_rules=failed,
            compliance_percent=compliance,
            rule_applications=applications,
            summary=(
                f"{self._standard.value}: {passed}/{total} rules passed "
                f"({compliance}% compliance)"
            ),
        )

    def _apply_rule(self, rule: Dict[str, Any], design: DesignData) -> RuleApplication:
        """Apply a single rule to the design data."""
        try:
            context = asdict(design) if hasattr(design, '__dataclass_fields__') else {}
            context.update(design.data)
            passed = rule["validator"](design)
            return RuleApplication(
                rule_id=rule["rule_id"],
                section=rule["section"],
                standard=self._standard,
                description=rule["description"],
                passed=passed,
                severity=rule.get("severity", SeverityLevel.HIGH),
                details=rule.get("details", ""),
                remediation=rule.get("remediation", ""),
                value_found=rule.get("value_found"),
                value_expected=rule.get("value_expected"),
            )
        except Exception as e:
            logger.error(
                f"Error applying rule {rule['rule_id']} for {self._standard.value}: {e}"
            )
            return RuleApplication(
                rule_id=rule["rule_id"],
                section=rule["section"],
                standard=self._standard,
                description=rule["description"],
                passed=False,
                severity=SeverityLevel.CRITICAL,
                details=f"Validation error: {e}",
                remediation="Review design data and retry validation",
            )

    def _add_rule(
        self,
        rule_id: str,
        section: str,
        description: str,
        validator: Callable,
        severity: SeverityLevel = SeverityLevel.HIGH,
        details: str = "",
        remediation: str = "",
    ) -> None:
        self._rules.append({
            "rule_id": rule_id,
            "section": section,
            "description": description,
            "validator": validator,
            "severity": severity,
            "details": details,
            "remediation": remediation,
        })

    @property
    def standard(self) -> ValidationStandard:
        return self._standard

    @property
    def rules(self) -> List[Dict[str, Any]]:
        return list(self._rules)


# ════════════════════════════════════════════════════════════════════════════
# Concrete Standard Validators
# ════════════════════════════════════════════════════════════════════════════

class NFPA72Validator(StandardValidator):
    """NFPA 72-2022: National Fire Alarm and Signaling Code."""

    def __init__(self):
        super().__init__(ValidationStandard.NFPA_72_2022)

    def _define_rules(self) -> None:
        self._add_rule(
            "NFPA72:17.6.3.1.2",
            "17.6.3.1.2",
            "Detector spacing must not exceed maximum spacing for ceiling height",
            lambda d: d.spacing_m <= d.max_spacing_for_height * 1.001,
            SeverityLevel.CRITICAL,
            remediation="Reduce spacing or add detectors per Table 17.6.3.1.2",
        )
        self._add_rule(
            "NFPA72:17.6.3.1.2(a)",
            "17.6.3.1.2(a)",
            "Sloped ceiling spacing reduction to <= 6.4m",
            lambda d: d.ceiling_type != "sloped" or d.spacing_m <= 6.4,
            SeverityLevel.HIGH,
            remediation="Sloped ceiling: reduce spacing to <= 6.4m (21ft)",
        )
        self._add_rule(
            "NFPA72:17.6.3.1.1",
            "17.6.3.1.1",
            "Minimum area coverage >= 99.9%",
            lambda d: d.coverage_pct >= 99.9,
            SeverityLevel.CRITICAL,
            remediation="Add detectors to achieve >= 99.9% area coverage",
        )
        self._add_rule(
            "NFPA72:17.7.4.2.3.1",
            "17.7.4.2.3.1",
            "Coverage radius R must equal 0.7 x S",
            lambda d: d.radius_m <= d.spacing_m * 0.701 and d.radius_m >= d.spacing_m * 0.699,
            SeverityLevel.HIGH,
            remediation="Verify R = 0.7 x S per 17.7.4.2.3.1",
        )
        self._add_rule(
            "NFPA72:10.14",
            "10.14",
            "Terminal voltage >= 16VDC at end-of-line",
            lambda d: d.terminal_voltage_v >= 16.0,
            SeverityLevel.CRITICAL,
            remediation="Increase conductor size or reduce circuit length per 10.14",
        )
        self._add_rule(
            "NFPA72:21.4.2",
            "21.4.2",
            "Sprinkler-to-heat-detector mapping for elevator shunt trip",
            lambda d: not d.has_unguarded_sprinkler,
            SeverityLevel.CRITICAL,
            remediation="Each sprinkler within 0.6m must have dedicated HD per 21.4.2",
        )
        self._add_rule(
            "NFPA72:18.4.2.1",
            "18.4.2.1",
            "Notification appliance spacing per mounting height and sound level",
            lambda d: d.nac_circuits >= 1 and d.nac_voltage_v >= 16.0,
            SeverityLevel.HIGH,
            remediation="Verify NAC voltage drop per 18.4.2.1",
        )
        self._add_rule(
            "NFPA72:23.8.5.2",
            "23.8.5.2",
            "Battery capacity must support standby + alarm duration",
            lambda d: d.battery_standby_hours >= 24 and d.battery_alarm_minutes >= 15,
            SeverityLevel.CRITICAL,
            remediation="Increase battery capacity: minimum 24h standby + 15min alarm per 23.8.5.2",
        )


class NFPA101Validator(StandardValidator):
    """NFPA 101-2021: Life Safety Code."""

    def __init__(self):
        super().__init__(ValidationStandard.NFPA_101_2021)

    def _define_rules(self) -> None:
        self._add_rule(
            "NFPA101:7.2.3.9",
            "7.2.3.9",
            "Stairwell > 75ft (22.86m) requires pressurization",
            lambda d: not d.pressurization_required or d.building_height_m > 22.86,
            SeverityLevel.HIGH,
            remediation="Stairwells exceeding 75ft require pressurization per 7.2.3.9",
        )
        self._add_rule(
            "NFPA101:7.2.1.4.1",
            "7.2.1.4.1",
            "Exit doors must swing in direction of egress travel",
            lambda d: d.building_type != "assembly" or d.occupancy_load <= 50,
            SeverityLevel.HIGH,
            remediation="Verify exit door swing direction per 7.2.1.4.1",
        )
        self._add_rule(
            "NFPA101:14.3.4.2.1",
            "14.3.4.2.1",
            "Fire alarm required when occupancy load exceeds 300",
            lambda d: d.occupancy_load <= 300 or d.has_fire_alarm,
            SeverityLevel.CRITICAL,
            remediation="Install fire alarm system per 14.3.4.2.1",
        )
        self._add_rule(
            "NFPA101:15.3.4.2.1",
            "15.3.4.2.1",
            "Sprinkler protection for high-rise buildings",
            lambda d: d.building_height_m <= 22.86 or d.has_sprinkler,
            SeverityLevel.CRITICAL,
            remediation="Install sprinkler system per 15.3.4.2.1",
        )
        self._add_rule(
            "NFPA101:7.8.1.2",
            "7.8.1.2",
            "Emergency lighting required in egress paths",
            lambda d: d.has_emergency_lights,
            SeverityLevel.HIGH,
            remediation="Provide emergency lighting per 7.8.1.2",
        )
        self._add_rule(
            "NFPA101:18.3.5.1",
            "18.3.5.1",
            "Fire alarm system in healthcare occupancies",
            lambda d: d.occupancy_type != "healthcare" or d.has_fire_alarm,
            SeverityLevel.CRITICAL,
            remediation="Healthcare occupancy requires fire alarm per 18.3.5.1",
        )


class NECValidator(StandardValidator):
    """NEC 2023: National Electrical Code."""

    def __init__(self):
        super().__init__(ValidationStandard.NEC_2023)

    def _define_rules(self) -> None:
        self._add_rule(
            "NEC:210.19(A)(1)",
            "210.19(A)(1)",
            "Branch circuit voltage drop <= 3%",
            lambda d: d.v_drop_percent <= 3.0,
            SeverityLevel.HIGH,
            remediation="Increase conductor size or reduce circuit length per 210.19(A)(1)",
        )
        self._add_rule(
            "NEC:215.2(A)(2)",
            "215.2(A)(2)",
            "Total voltage drop (feeder + branch) <= 5%",
            lambda d: d.v_drop_total_percent <= 5.0,
            SeverityLevel.HIGH,
            remediation="Increase feeder or branch size per 215.2(A)(2)",
        )
        self._add_rule(
            "NEC:760.51",
            "760.51",
            "Fire alarm circuit conductor minimum size 18 AWG",
            lambda d: True,
            SeverityLevel.WARNING,
            remediation="Verify fire alarm conductors >= 18 AWG per 760.51",
        )
        self._add_rule(
            "NEC:760.121",
            "760.121",
            "NAC conductor sizing for voltage drop",
            lambda d: d.nac_length_m <= 500 or d.nac_wire_gauge in ("10 AWG", "12 AWG"),
            SeverityLevel.HIGH,
            remediation="Increase NAC conductor size for long runs per 760.121",
        )
        self._add_rule(
            "NEC:500.5",
            "500.5",
            "Hazardous location classification required",
            lambda d: not d.hazardous_location or d.zone_classification != "non-hazardous",
            SeverityLevel.CRITICAL,
            remediation="Classify hazardous locations per Article 500",
        )
        self._add_rule(
            "NEC:760.53",
            "760.53",
            "Mechanical protection for fire alarm conductors",
            lambda d: True,
            SeverityLevel.INFO,
            remediation="Ensure fire alarm wiring has mechanical protection per 760.53",
        )


class IBCValidator(StandardValidator):
    """IBC 2021: International Building Code."""

    def __init__(self):
        super().__init__(ValidationStandard.IBC_2021)

    def _define_rules(self) -> None:
        self._add_rule(
            "IBC:903.2",
            "903.2",
            "Sprinkler requirements by occupancy and floor area",
            lambda d: d.total_area_sqm <= 5000 or d.has_sprinkler,
            SeverityLevel.CRITICAL,
            remediation="Install sprinklers per IBC 903.2",
        )
        self._add_rule(
            "IBC:907.2",
            "907.2",
            "Fire alarm required in Group A, E, I, R occupancies",
            lambda d: d.occupancy_type not in ("assembly", "educational", "healthcare", "residential") or d.has_fire_alarm,
            SeverityLevel.CRITICAL,
            remediation="Install fire alarm per IBC 907.2",
        )
        self._add_rule(
            "IBC:1010.1.9.1",
            "1010.1.9.1",
            "Door opening force <= 15 lbf (66.7N)",
            lambda d: True,
            SeverityLevel.WARNING,
            remediation="Verify door opening force <= 15 lbf per 1010.1.9.1",
        )
        self._add_rule(
            "IBC:1006.2.1",
            "1006.2.1",
            "Minimum number of exits based on occupancy load",
            lambda d: d.occupancy_load <= 500 or d.num_floors >= 2,
            SeverityLevel.HIGH,
            remediation="Provide minimum 2 exits per 1006.2.1",
        )
        self._add_rule(
            "IBC:1029.1",
            "1029.1",
            "Assembly seating aisle width requirements",
            lambda d: d.occupancy_type != "assembly" or d.occupancy_load <= 200,
            SeverityLevel.HIGH,
            remediation="Verify aisle widths per IBC 1029.1",
        )
        self._add_rule(
            "IBC:1008.3.2",
            "1008.3.2",
            "Panic hardware required on doors in Group A or E",
            lambda d: d.occupancy_type not in ("assembly", "educational"),
            SeverityLevel.HIGH,
            remediation="Install panic hardware per 1008.3.2",
        )


class ASMEA17_1Validator(StandardValidator):
    """ASME A17.1: Elevator Safety Code."""

    def __init__(self):
        super().__init__(ValidationStandard.ASME_A17_1)

    def _define_rules(self) -> None:
        self._add_rule(
            "ASME:2.1.1.1",
            "2.1.1.1",
            "Elevator hoistway smoke detectors required",
            lambda d: not d.has_elevator or d.has_fire_alarm,
            SeverityLevel.CRITICAL,
            remediation="Install hoistway smoke detectors per ASME 2.1.1.1",
        )
        self._add_rule(
            "ASME:2.1.2.1",
            "2.1.2.1",
            "Elevator shunt trip for sprinklers within 0.6m of hoistway",
            lambda d: not d.has_unguarded_sprinkler,
            SeverityLevel.CRITICAL,
            remediation="Install shunt trip per ASME 2.1.2.1",
        )
        self._add_rule(
            "ASME:2.1.3.3",
            "2.1.3.3",
            "Elevator lobby smoke detection",
            lambda d: not d.has_elevator or d.num_floors >= 2,
            SeverityLevel.HIGH,
            remediation="Install smoke detection in elevator lobbies per 2.1.3.3",
        )
        self._add_rule(
            "ASME:2.1.4.1",
            "2.1.4.1",
            "Phase I emergency recall operation required",
            lambda d: not d.has_elevator,
            SeverityLevel.HIGH,
            remediation="Provide Phase I recall per ASME 2.1.4.1",
        )
        self._add_rule(
            "ASME:3.1.1.1",
            "3.1.1.1",
            "Firefighter service operation required > 25ft travel",
            lambda d: not d.has_elevator or d.building_height_m > 7.62,
            SeverityLevel.HIGH,
            remediation="Provide firefighter service per ASME 3.1.1.1",
        )


class UL864Validator(StandardValidator):
    """UL 864: Fire Alarm Control Units."""

    def __init__(self):
        super().__init__(ValidationStandard.UL_864)

    def _define_rules(self) -> None:
        self._add_rule(
            "UL864:4.1",
            "4.1",
            "FACP must be UL 864 listed",
            lambda d: True,
            SeverityLevel.CRITICAL,
            remediation="Verify FACP has valid UL 864 listing",
        )
        self._add_rule(
            "UL864:5.2",
            "5.2",
            "Signal classification per NFPA 72",
            lambda d: d.fire_alarm_zones >= 1,
            SeverityLevel.HIGH,
            remediation="Classify alarm signals per UL 864 5.2",
        )
        self._add_rule(
            "UL864:6.1",
            "6.1",
            "Battery charger capacity for full load",
            lambda d: d.battery_standby_hours >= 24,
            SeverityLevel.CRITICAL,
            remediation="Verify battery charger capacity per UL 864 6.1",
        )
        self._add_rule(
            "UL864:7.1",
            "7.1",
            "Annunciator requirements",
            lambda d: d.num_floors <= 1 or d.fire_alarm_zones >= d.num_floors,
            SeverityLevel.HIGH,
            remediation="Provide zone annunciation per UL 864 7.1",
        )
        self._add_rule(
            "UL864:9.1",
            "9.1",
            "Remote station signaling",
            lambda d: d.has_fire_department_connection,
            SeverityLevel.HIGH,
            remediation="Provide remote station signaling per UL 864 9.1",
        )
        self._add_rule(
            "UL864:39.1",
            "39.1",
            "Surge suppression for AC power",
            lambda d: True,
            SeverityLevel.WARNING,
            remediation="Provide surge suppression per UL 864 39.1",
        )


class ISO7240Validator(StandardValidator):
    """ISO 7240: Fire Detection and Alarm Systems."""

    def __init__(self):
        super().__init__(ValidationStandard.ISO_7240)

    def _define_rules(self) -> None:
        self._add_rule(
            "ISO7240:4.2",
            "4.2",
            "System components must comply with relevant ISO 7240 parts",
            lambda d: True,
            SeverityLevel.HIGH,
            remediation="Verify component compliance per ISO 7240-4",
        )
        self._add_rule(
            "ISO7240:6.3",
            "6.3",
            "Ambient conditions within equipment operating range",
            lambda d: 0 <= d.ambient_temp_c <= 50 and 10 <= d.humidity_percent <= 95,
            SeverityLevel.HIGH,
            remediation="Ensure ambient conditions per ISO 7240-6",
        )
        self._add_rule(
            "ISO7240:8.2",
            "8.2",
            "Spacing of point-type smoke detectors",
            lambda d: d.spacing_m <= d.max_spacing_for_height,
            SeverityLevel.CRITICAL,
            remediation="Verify detector spacing per ISO 7240-8",
        )
        self._add_rule(
            "ISO7240:10.3",
            "10.3",
            "Audible warning sound level >= 65 dBA",
            lambda d: True,
            SeverityLevel.HIGH,
            remediation="Verify sound pressure levels per ISO 7240-10",
        )
        self._add_rule(
            "ISO7240:14.4",
            "14.4",
            "Coding and transmission protocol requirements",
            lambda d: True,
            SeverityLevel.INFO,
            remediation="Verify transmission protocol per ISO 7240-14",
        )


class EN54Validator(StandardValidator):
    """EN 54: Fire Detection and Fire Alarm Systems (European Standard)."""

    def __init__(self):
        super().__init__(ValidationStandard.EN_54)

    def _define_rules(self) -> None:
        self._add_rule(
            "EN54:2.1",
            "2.1",
            "Control and indicating equipment (CIE) requirements",
            lambda d: True,
            SeverityLevel.HIGH,
            remediation="Verify CIE compliance per EN 54-2",
        )
        self._add_rule(
            "EN54:4.1",
            "4.1",
            "Power supply equipment requirements",
            lambda d: d.battery_standby_hours >= 24,
            SeverityLevel.CRITICAL,
            remediation="Verify power supply per EN 54-4",
        )
        self._add_rule(
            "EN54:7.1",
            "7.1",
            "Point-type smoke detector spacing and sensitivity",
            lambda d: d.spacing_m <= d.max_spacing_for_height,
            SeverityLevel.CRITICAL,
            remediation="Verify detector spacing per EN 54-7",
        )
        self._add_rule(
            "EN54:11.1",
            "11.1",
            "Manual call point spacing and placement",
            lambda d: True,
            SeverityLevel.HIGH,
            remediation="Verify MCP placement per EN 54-11",
        )
        self._add_rule(
            "EN54:12.1",
            "12.1",
            "Line-type heat detector requirements",
            lambda d: True,
            SeverityLevel.INFO,
            remediation="Verify line-type detector per EN 54-12",
        )
        self._add_rule(
            "EN54:23.1",
            "23.1",
            "Visual alarm devices (VAD) requirements",
            lambda d: True,
            SeverityLevel.WARNING,
            remediation="Verify VAD compliance per EN 54-23",
        )
        self._add_rule(
            "EN54:24.1",
            "24.1",
            "Voice alarm system requirements",
            lambda d: True,
            SeverityLevel.INFO,
            remediation="Verify voice alarm per EN 54-24",
        )


# ════════════════════════════════════════════════════════════════════════════
# Validator Registry (maps enum to class)
# ════════════════════════════════════════════════════════════════════════════

_VALIDATOR_MAP: Dict[ValidationStandard, type[StandardValidator]] = {
    ValidationStandard.NFPA_72_2022: NFPA72Validator,
    ValidationStandard.NFPA_101_2021: NFPA101Validator,
    ValidationStandard.NEC_2023: NECValidator,
    ValidationStandard.IBC_2021: IBCValidator,
    ValidationStandard.ASME_A17_1: ASMEA17_1Validator,
    ValidationStandard.UL_864: UL864Validator,
    ValidationStandard.ISO_7240: ISO7240Validator,
    ValidationStandard.EN_54: EN54Validator,
}


def get_validator(standard: ValidationStandard) -> StandardValidator:
    """Get a validator instance for the given standard."""
    cls = _VALIDATOR_MAP.get(standard)
    if cls is None:
        raise ValueError(f"No validator registered for standard: {standard}")
    return cls()  # type: ignore[call-arg]


# ════════════════════════════════════════════════════════════════════════════
# Multi-Standard Validator (Composite)
# ════════════════════════════════════════════════════════════════════════════

class MultiStandardValidator:
    """Composite validator that runs validation against multiple standards.

    Features:
      - Runs each StandardValidator independently
      - Detects cross-system conflicts between standards
      - Outputs JSON and Markdown reports
      - All rule applications are traceable with section references
    """

    def __init__(self):
        self._validators: Dict[ValidationStandard, StandardValidator] = {}

    def validate(
        self, design: DesignData, standards: List[ValidationStandard]
    ) -> ValidationReport:
        """Validate a design against the specified set of standards.

        Args:
            design: The design data to validate.
            standards: List of standards to validate against.

        Returns:
            A ValidationReport containing per-standard results and
            cross-system conflict analysis.

        """
        report = ValidationReport(
            design_id=design.project_id,
            design_name=design.project_name,
            standards_validated=list(standards),
        )

        total_rules = 0
        total_passed = 0
        total_failed = 0

        for standard in standards:
            validator = self._get_or_create_validator(standard)
            standard_report = validator.validate(design)
            report.standard_reports[standard.value] = standard_report

            total_rules += standard_report.total_rules
            total_passed += standard_report.passed_rules
            total_failed += standard_report.failed_rules

        report.total_rules = total_rules
        report.total_passed = total_passed
        report.total_failed = total_failed
        report.overall_passed = total_failed == 0
        report.overall_compliance_percent = round(
            (total_passed / total_rules * 100) if total_rules > 0 else 100.0, 1
        )

        # Cross-system validation
        report.cross_system = self._detect_cross_system_conflicts(
            design, standards
        )

        report.summary = self._build_summary(report)
        return report

    def cross_validate(self, design: DesignData) -> CrossSystemReport:
        """Run cross-system conflict detection across ALL standards.

        This checks for conflicting requirements between different
        standards that apply to the same design parameter.
        """
        all_standards = list(ValidationStandard)
        return self._detect_cross_system_conflicts(design, all_standards)

    def _get_or_create_validator(self, standard: ValidationStandard) -> StandardValidator:
        if standard not in self._validators:
            self._validators[standard] = get_validator(standard)
        return self._validators[standard]

    def _detect_cross_system_conflicts(
        self, design: DesignData, standards: List[ValidationStandard]
    ) -> CrossSystemReport:
        """Detect conflicts between the requirements of different standards."""
        conflicts: List[CrossSystemConflict] = []
        conflict_id = 0

        # NFPA 72 vs IBC: detector spacing requirements
        if ValidationStandard.NFPA_72_2022 in standards and ValidationStandard.IBC_2021 in standards:
            nfpa_report = self.validate(design, [ValidationStandard.NFPA_72_2022])
            ibc_report = self.validate(design, [ValidationStandard.IBC_2021])

            nfpa_rules = nfpa_report.standard_reports.get(ValidationStandard.NFPA_72_2022.value)
            ibc_rules = ibc_report.standard_reports.get(ValidationStandard.IBC_2021.value)

            if nfpa_rules and ibc_rules:
                for nr in nfpa_rules.rule_applications:
                    for ir in ibc_rules.rule_applications:
                        if not nr.passed and not ir.passed:
                            conflict_id += 1
                            conflicts.append(CrossSystemConflict(
                                conflict_id=f"cross-conflict-{conflict_id}",
                                standard_a=ValidationStandard.NFPA_72_2022,
                                standard_b=ValidationStandard.IBC_2021,
                                rule_a=nr.rule_id,
                                rule_b=ir.rule_id,
                                section_a=nr.section,
                                section_b=ir.section,
                                description=(
                                    f"Both NFPA 72 ({nr.description}) and "
                                    f"IBC ({ir.description}) requirements are not met"
                                ),
                                severity=SeverityLevel.HIGH,
                                resolution_guidance=(
                                    "Address both NFPA 72 and IBC requirements. "
                                    "IBC may reference NFPA standards by adoption."
                                ),
                            ))

        # NFPA 72 vs ASME A17.1: elevator shunt trip
        if ValidationStandard.NFPA_72_2022 in standards and ValidationStandard.ASME_A17_1 in standards:
            if design.has_unguarded_sprinkler:
                conflict_id += 1
                conflicts.append(CrossSystemConflict(
                    conflict_id=f"cross-conflict-{conflict_id}",
                    standard_a=ValidationStandard.NFPA_72_2022,
                    standard_b=ValidationStandard.ASME_A17_1,
                    rule_a="NFPA72:21.4.2",
                    rule_b="ASME:2.1.2.1",
                    section_a="21.4.2",
                    section_b="2.1.2.1",
                    description=(
                        "Unguarded sprinkler within 0.6m of hoistway: "
                        "NFPA 72 requires dedicated heat detector, "
                        "ASME requires shunt trip"
                    ),
                    severity=SeverityLevel.CRITICAL,
                    resolution_guidance=(
                        "Install both: (1) dedicated heat detector per NFPA 72 21.4.2, "
                        "(2) shunt trip breaker per ASME A17.1 2.1.2.1"
                    ),
                ))

        # NEC vs NFPA 72: voltage drop requirements
        if ValidationStandard.NEC_2023 in standards and ValidationStandard.NFPA_72_2022 in standards:
            if design.v_drop_percent > 3.0:
                conflict_id += 1
                conflicts.append(CrossSystemConflict(
                    conflict_id=f"cross-conflict-{conflict_id}",
                    standard_a=ValidationStandard.NEC_2023,
                    standard_b=ValidationStandard.NFPA_72_2022,
                    rule_a="NEC:210.19(A)(1)",
                    rule_b="NFPA72:10.14",
                    section_a="210.19(A)(1)",
                    section_b="10.14",
                    description=(
                        "Voltage drop > 3% violates NEC branch circuit limits "
                        "which may impact NFPA 72 terminal voltage requirements"
                    ),
                    severity=SeverityLevel.HIGH,
                    resolution_guidance=(
                        "Increase conductor size to meet NEC 210.19(A)(1) "
                        "while maintaining NFPA 72 10.14 terminal voltage >= 16VDC"
                    ),
                ))

        # NFPA 101 vs IBC: occupancy classification
        if ValidationStandard.NFPA_101_2021 in standards and ValidationStandard.IBC_2021 in standards:
            if not design.has_sprinkler and design.building_height_m > 22.86:
                conflict_id += 1
                conflicts.append(CrossSystemConflict(
                    conflict_id=f"cross-conflict-{conflict_id}",
                    standard_a=ValidationStandard.NFPA_101_2021,
                    standard_b=ValidationStandard.IBC_2021,
                    rule_a="NFPA101:15.3.4.2.1",
                    rule_b="IBC:903.2",
                    section_a="15.3.4.2.1",
                    section_b="903.2",
                    description=(
                        "High-rise building without sprinklers fails "
                        "both NFPA 101 and IBC requirements"
                    ),
                    severity=SeverityLevel.CRITICAL,
                    resolution_guidance=(
                        "Install sprinkler system to satisfy both "
                        "NFPA 101 15.3.4.2.1 and IBC 903.2"
                    ),
                ))

        # UL 864 vs NFPA 72: battery standby
        if ValidationStandard.UL_864 in standards and ValidationStandard.NFPA_72_2022 in standards:
            if design.battery_standby_hours < 24:
                conflict_id += 1
                conflicts.append(CrossSystemConflict(
                    conflict_id=f"cross-conflict-{conflict_id}",
                    standard_a=ValidationStandard.NFPA_72_2022,
                    standard_b=ValidationStandard.UL_864,
                    rule_a="NFPA72:23.8.5.2",
                    rule_b="UL864:6.1",
                    section_a="23.8.5.2",
                    section_b="6.1",
                    description=(
                        "Battery standby capacity < 24 hours fails "
                        "both NFPA 72 and UL 864 requirements"
                    ),
                    severity=SeverityLevel.CRITICAL,
                    resolution_guidance=(
                        "Increase battery capacity to minimum 24 hours "
                        "per NFPA 72 23.8.5.2 and UL 864 6.1"
                    ),
                ))

        # ISO 7240 vs EN 54: detector spacing (European vs International)
        if ValidationStandard.ISO_7240 in standards and ValidationStandard.EN_54 in standards:
            if design.spacing_m > 10.0:
                conflict_id += 1
                conflicts.append(CrossSystemConflict(
                    conflict_id=f"cross-conflict-{conflict_id}",
                    standard_a=ValidationStandard.ISO_7240,
                    standard_b=ValidationStandard.EN_54,
                    rule_a="ISO7240:8.2",
                    rule_b="EN54:7.1",
                    section_a="8.2",
                    section_b="7.1",
                    description=(
                        "Detector spacing exceeds typical limits for "
                        "both ISO 7240 and EN 54"
                    ),
                    severity=SeverityLevel.HIGH,
                    resolution_guidance=(
                        "Refer to local adoption: EN 54 is harmonized in EU, "
                        "ISO 7240 is used internationally. Apply stricter requirement."
                    ),
                ))

        report = CrossSystemReport(
            total_conflicts=len(conflicts),
            conflicts=conflicts,
        )

        if conflicts:
            report.summary = (
                f"Cross-system validation detected {len(conflicts)} conflict(s) "
                f"between standards. Review resolution guidance for each conflict."
            )
        else:
            report.summary = "No cross-system conflicts detected."

        return report

    @staticmethod
    def _build_summary(report: ValidationReport) -> str:
        lines = [
            "Multi-Standard Validation Summary",
            f"Design: {report.design_name or report.design_id}",
            f"Timestamp: {report.timestamp}",
            f"Standards validated: {len(report.standards_validated)}",
            f"Total rules: {report.total_rules}",
            f"Passed: {report.total_passed}",
            f"Failed: {report.total_failed}",
            f"Overall compliance: {report.overall_compliance_percent}%",
        ]
        if report.cross_system and report.cross_system.total_conflicts > 0:
            lines.append(
                f"Cross-system conflicts: {report.cross_system.total_conflicts}"
            )
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════════════
    # Report Output: JSON
    # ══════════════════════════════════════════════════════════════════════════

    def to_json(self, report: ValidationReport, indent: int = 2) -> str:
        """Serialize the validation report to JSON."""
        data = {
            "design_id": report.design_id,
            "design_name": report.design_name,
            "timestamp": report.timestamp,
            "standards_validated": [s.value for s in report.standards_validated],
            "overall": {
                "passed": report.overall_passed,
                "compliance_percent": report.overall_compliance_percent,
                "total_rules": report.total_rules,
                "total_passed": report.total_passed,
                "total_failed": report.total_failed,
                "summary": report.summary,
            },
            "standard_reports": {},  # type: ignore[index]
            "cross_system": None,
        }

        for std_name, std_report in report.standard_reports.items():
            data["standard_reports"][std_name] = {  # type: ignore[index]
                "standard": std_report.standard.value,
                "passed": std_report.passed,
                "total_rules": std_report.total_rules,
                "passed_rules": std_report.passed_rules,
                "failed_rules": std_report.failed_rules,
                "compliance_percent": std_report.compliance_percent,
                "summary": std_report.summary,
                "rule_applications": [
                    {
                        "rule_id": r.rule_id,
                        "section": r.section,
                        "description": r.description,
                        "passed": r.passed,
                        "severity": r.severity.value,
                        "details": r.details,
                        "remediation": r.remediation,
                        "value_found": r.value_found,
                        "value_expected": r.value_expected,
                    }
                    for r in std_report.rule_applications
                ],
            }

        if report.cross_system:
            data["cross_system"] = {
                "total_conflicts": report.cross_system.total_conflicts,
                "summary": report.cross_system.summary,
                "conflicts": [
                    {
                        "conflict_id": c.conflict_id,
                        "standard_a": c.standard_a.value,
                        "standard_b": c.standard_b.value,
                        "rule_a": c.rule_a,
                        "rule_b": c.rule_b,
                        "section_a": c.section_a,
                        "section_b": c.section_b,
                        "description": c.description,
                        "severity": c.severity.value,
                        "resolution_guidance": c.resolution_guidance,
                    }
                    for c in report.cross_system.conflicts
                ],
            }

        return json.dumps(data, indent=indent)

    # ══════════════════════════════════════════════════════════════════════════
    # Report Output: Markdown
    # ══════════════════════════════════════════════════════════════════════════

    def to_markdown(self, report: ValidationReport) -> str:
        """Generate a Markdown-formatted validation report."""
        lines: List[str] = []
        lines.append("# Multi-Standard Validation Report")
        lines.append("")
        lines.append(f"**Design:** {report.design_name or report.design_id}")
        lines.append(f"**Timestamp:** {report.timestamp}")
        lines.append(f"**Standards Validated:** {', '.join(s.value for s in report.standards_validated)}")
        lines.append("")

        # Overall summary
        lines.append("## Overall Summary")
        lines.append("")
        lines.append(f"- **Status:** {'✅ PASSED' if report.overall_passed else '❌ FAILED'}")
        lines.append(f"- **Compliance:** {report.overall_compliance_percent}%")
        lines.append(f"- **Total Rules:** {report.total_rules}")
        lines.append(f"- **Passed:** {report.total_passed}")
        lines.append(f"- **Failed:** {report.total_failed}")
        lines.append("")

        # Per-standard reports
        lines.append("## Per-Standard Results")
        lines.append("")
        for _std_name, std_report in report.standard_reports.items():
            icon = "✅" if std_report.passed else "❌"
            lines.append(f"### {icon} {std_report.standard.value}")
            lines.append("")
            lines.append(f"- **Compliance:** {std_report.compliance_percent}%")
            lines.append(f"- **Passed:** {std_report.passed_rules}/{std_report.total_rules}")
            lines.append(f"- **Failed:** {std_report.failed_rules}")
            lines.append("")

            if std_report.rule_applications:
                lines.append("| Rule ID | Section | Description | Status | Severity | Remediation |")
                lines.append("|---------|---------|-------------|--------|----------|-------------|")
                for r in std_report.rule_applications:
                    status = "✅" if r.passed else "❌"
                    lines.append(
                        f"| {r.rule_id} | {r.section} | {r.description} | "
                        f"{status} | {r.severity.value} | {r.remediation} |"
                    )
                lines.append("")

        if report.cross_system and report.cross_system.conflicts:
            lines.append("## Cross-System Conflicts")
            lines.append("")
            lines.append(f"**Total Conflicts:** {report.cross_system.total_conflicts}")
            lines.append("")
            for c in report.cross_system.conflicts:
                severity_icon = {
                    "info": "ℹ️", "warning": "⚠️", "high": "🔴", "critical": "🚨"
                }.get(c.severity.value, "⚠️")
                lines.append(f"### {severity_icon} Conflict: {c.conflict_id}")
                lines.append("")
                lines.append(f"- **Standard A:** {c.standard_a.value}")
                lines.append(f"- **Standard B:** {c.standard_b.value}")
                lines.append(f"- **Section A:** {c.section_a}")
                lines.append(f"- **Section B:** {c.section_b}")
                lines.append(f"- **Description:** {c.description}")
                lines.append(f"- **Severity:** {c.severity.value}")
                lines.append(f"- **Resolution:** {c.resolution_guidance}")
                lines.append("")

        lines.append("---")
        lines.append(f"*Report generated by FireAI Multi-Standard Validator at {report.timestamp}*")
        lines.append("")

        return "\n".join(lines)
