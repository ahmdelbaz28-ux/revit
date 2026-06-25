"""fireai.core.building_systems_integration — Building Systems Fire Integration
=============================================================================

Implements fire alarm integration with building systems per NFPA 72:

1. Elevator Recall        — NFPA 72 §21.3
2. HVAC Shutdown          — NFPA 72 §21.4
3. Smoke Control          — NFPA 92, NFPA 72 §21.5
4. Fire Pump Monitoring   — NFPA 20, NFPA 72 §21.8

SAFETY CRITICAL:
  - These systems protect life safety during fire events
  - Integration failures can KILL people (e.g., elevator brings
    occupants TO the fire floor instead of away)
  - Every integration point MUST have a defined fail-safe state
  - All NaN/Inf inputs are REJECTED

ENGINEERING SOURCES:
  - NFPA 72-2022 Chapter 21 — Emergency Control Functions
  - NFPA 92-2024 — Smoke Control Systems
  - NFPA 20-2024 — Installation of Stationary Pumps for Fire Protection
  - ASME A17.1 — Elevator Safety Code
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List

# ═══════════════════════════════════════════════════════════════════════════════
# ELEVATOR RECALL — NFPA 72 §21.3
# ═══════════════════════════════════════════════════════════════════════════════


class ElevatorRecallPhase(str, Enum):
    """Elevator recall phases per NFPA 72 §21.3.

    Phase I: Recall to designated floor (away from fire)
    Phase II: Independent service (firefighter control)
    Shunt Trip: Power disconnect when sprinkler activates in shaft

    V111 FIX: Replaced hacky type()-based dynamic class with proper str Enum.
    The previous implementation used `type('Enum', (), {...})` with walrus
    operator, which lacked enum safety features (iteration, membership testing,
    type checking). A str Enum provides all of these while maintaining
    backward compatibility with string comparisons.
    """

    PHASE_I = "PHASE_I"
    PHASE_II = "PHASE_II"
    SHUNT_TRIP = "SHUNT_TRIP"


@dataclass(frozen=True)
class ElevatorRecallResult:
    """Result from elevator recall assessment.

    NFPA 72 §21.3 requires:
      - Lobby detector on each floor → Phase I recall
      - Hoistway detector → Phase I recall + separate alert
      - Sprinkler in shaft → Shunt trip (power disconnect)
      - Designated floor must NOT be the fire floor
      - Firefighter's service (Phase II) must be available

    Fail-safe: On loss of power or communication, elevator
    must recall to designated floor and open doors.
    """

    elevator_id: str
    recall_required: bool
    phase_i_activated: bool
    phase_ii_available: bool
    shunt_trip_required: bool
    designated_floor: str
    fire_floor: str
    is_compliant: bool
    violations: tuple
    nfpa_section: str


def evaluate_elevator_recall(
    elevator_id: str,
    has_lobby_detector: bool,
    has_hoistway_detector: bool,
    has_shaft_sprinkler: bool,
    designated_floor: str = "1",
    fire_floor: str = "1",
    # V114 FIX: Fail-safe — Phase II must be confirmed, not assumed
    has_phase_ii: bool = False,
) -> ElevatorRecallResult:
    """Evaluate elevator recall compliance per NFPA 72 §21.3.

    Args:
        elevator_id: Elevator identifier.
        has_lobby_detector: Lobby smoke detector on each floor.
        has_hoistway_detector: Hoistway smoke detector.
        has_shaft_sprinkler: Sprinkler in elevator shaft.
        designated_floor: Designated recall floor.
        fire_floor: Floor where fire is detected.
        has_phase_ii: Phase II firefighter service available.

    Returns:
        ElevatorRecallResult with compliance assessment.

    """
    violations = []
    recall_required = True  # Always required for fire alarm activation
    shunt_trip = has_shaft_sprinkler

    # NFPA 72 §21.3.2: Lobby detector required
    if not has_lobby_detector:
        violations.append(
            f"Elevator '{elevator_id}': No lobby detector — Phase I recall cannot activate per NFPA 72 §21.3.2"
        )

    # NFPA 72 §21.3.3: Hoistway detector required
    if not has_hoistway_detector:
        violations.append(
            f"Elevator '{elevator_id}': No hoistway detector — separate recall alert not available per NFPA 72 §21.3.3"
        )

    # NFPA 72 §21.3.4: Shunt trip required when shaft sprinkler present
    if has_shaft_sprinkler and not has_hoistway_detector:
        violations.append(
            f"Elevator '{elevator_id}': Shaft sprinkler present but no "
            f"hoistway detector — shunt trip cannot activate safely "
            f"per NFPA 72 §21.3.4"
        )

    # ASME A17.1: Designated floor must not be fire floor
    if designated_floor == fire_floor:
        violations.append(
            f"Elevator '{elevator_id}': Designated floor '{designated_floor}' "
            f"is the fire floor — occupants recalled TO fire per ASME A17.1"
        )

    # NFPA 72 §21.3.5: Phase II required
    if not has_phase_ii:
        violations.append(f"Elevator '{elevator_id}': No Phase II firefighter service per NFPA 72 §21.3.5")

    is_compliant = len(violations) == 0

    return ElevatorRecallResult(
        elevator_id=elevator_id,
        recall_required=recall_required,
        phase_i_activated=has_lobby_detector or has_hoistway_detector,
        phase_ii_available=has_phase_ii,
        shunt_trip_required=shunt_trip,
        designated_floor=designated_floor,
        fire_floor=fire_floor,
        is_compliant=is_compliant,
        violations=tuple(violations),
        nfpa_section="NFPA 72 §21.3",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HVAC SHUTDOWN — NFPA 72 §21.4
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class HVACShutdownResult:
    """Result from HVAC shutdown assessment.

    NFPA 72 §21.4 requires:
      - Duct smoke detector → shutdown of affected AHU
      - Building-wide shutdown when fire floor unknown
      - Manual shutdown capability at FACP
      - Duct detectors supervisory (not alarm) signal
    """

    unit_id: str
    cfm: float
    has_duct_detector: bool
    shutdown_required: bool
    is_compliant: bool
    violations: tuple
    nfpa_section: str


def evaluate_hvac_shutdown(
    unit_id: str,
    cfm: float,
    has_duct_detector: bool,
    is_fire_floor: bool = False,
    is_building_wide: bool = False,
) -> HVACShutdownResult:
    """Evaluate HVAC shutdown compliance per NFPA 72 §21.4.

    NFPA 72 §21.4 and IMC §606:
      - AHU > 2000 CFM → duct smoke detector required
      - Duct detector → supervisory signal + AHU shutdown
      - Fire alarm → building-wide shutdown (or zone-specific)

    Args:
        unit_id: HVAC unit identifier.
        cfm: Air handling unit capacity in CFM.
        has_duct_detector: Whether duct smoke detector is installed.
        is_fire_floor: Whether this unit serves the fire floor.
        is_building_wide: Whether building-wide shutdown is required.

    Returns:
        HVACShutdownResult with compliance assessment.

    """
    violations = []

    if not math.isfinite(cfm) or cfm < 0:
        raise ValueError(f"cfm must be non-negative finite, got {cfm}")

    # NFPA 72 §17.7.5.6.1: Duct detector required for >2000 CFM
    detector_required = cfm > 2000
    shutdown_required = is_fire_floor or is_building_wide

    if detector_required and not has_duct_detector:
        violations.append(f"AHU '{unit_id}': {cfm:.0f} CFM > 2000 CFM but no duct smoke detector — NFPA 72 §17.7.5.6.1")

    if shutdown_required and not has_duct_detector:
        violations.append(
            f"AHU '{unit_id}': Shutdown required but no duct detector to trigger automatic shutdown — NFPA 72 §21.4"
        )

    is_compliant = len(violations) == 0

    return HVACShutdownResult(
        unit_id=unit_id,
        cfm=cfm,
        has_duct_detector=has_duct_detector,
        shutdown_required=shutdown_required,
        is_compliant=is_compliant,
        violations=tuple(violations),
        nfpa_section="NFPA 72 §21.4",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SMOKE CONTROL — NFPA 92 / NFPA 72 §21.5
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SmokeControlResult:
    """Result from smoke control assessment.

    NFPA 92 and NFPA 72 §21.5:
      - Smoke control must activate on fire alarm
      - Pressurization or exhaust method
      - Must maintain tenable conditions in egress paths
      - Must be tested and certified per NFPA 92
    """

    zone_id: str
    method: str  # "pressurization" or "exhaust"
    design_pressure_pa: float
    is_compliant: bool
    violations: tuple
    nfpa_section: str


# V106: Constants for NFPA 92 compliance — replaces magic numbers
MIN_STAIRWELL_PRESSURIZATION_PA = 25.0  # NFPA 92 §6.3: minimum 25 Pa (0.10 in. w.g.)
MAX_PRESSURE_DIFFERENTIAL_PA = 133.0  # NFPA 92 §6.3.3: max force to open door (~0.5 in. w.g.)
VALID_SMOKE_CONTROL_METHODS = ("pressurization", "exhaust")


def evaluate_smoke_control(
    zone_id: str,
    method: str = "pressurization",
    design_pressure_pa: float = 25.0,
    # V114 FIX: Fail-safe defaults — missing interlock = NOT present
    has_fire_alarm_interlock: bool = False,
    has_stairwell_pressurization: bool = False,
) -> SmokeControlResult:
    """Evaluate smoke control compliance per NFPA 92 / NFPA 72 §21.5.

    NFPA 92 requires:
      - Stairwell pressurization: minimum 25 Pa (0.10 in. w.g.)
      - Maximum pressure differential: ~133 Pa (0.5 in. w.g.) for door opening force
      - Zone smoke control: either pressurization or exhaust
      - Fire alarm interlock for automatic activation
      - Manual override at firefighter's control panel

    Args:
        zone_id: Smoke control zone identifier.
        method: "pressurization" or "exhaust".
        design_pressure_pa: Design pressure difference in Pascals.
        has_fire_alarm_interlock: Fire alarm activates smoke control.
        has_stairwell_pressurization: Stairwell pressurization system.

    Returns:
        SmokeControlResult with compliance assessment.

    Raises:
        ValueError: If design_pressure_pa is NaN/Inf, negative, or method is invalid.

    """
    violations = []

    # V106 CRITICAL FIX: Validate method — invalid method bypasses ALL checks
    if method not in VALID_SMOKE_CONTROL_METHODS:
        raise ValueError(
            f"method must be one of {VALID_SMOKE_CONTROL_METHODS}, "
            f"got '{method}'. An invalid method would bypass all NFPA 92 checks, "
            f"falsely claiming compliance."
        )

    # V106 CRITICAL FIX: Reject negative pressure — negative pressure draws smoke
    # INTO egress paths instead of keeping it out. This is lethal.
    if not math.isfinite(design_pressure_pa):
        raise ValueError(f"design_pressure_pa must be finite, got {design_pressure_pa}")
    if design_pressure_pa < 0:
        raise ValueError(
            f"design_pressure_pa must be non-negative, got {design_pressure_pa}. "
            f"Negative pressure draws smoke INTO egress paths — lethal condition."
        )

    # V106 FIX: Reject empty zone_id — makes violations untraceable
    if not zone_id or not zone_id.strip():
        raise ValueError("zone_id must not be empty — violations must be traceable")

    # NFPA 92 §6.3: Minimum pressurization
    if method == "pressurization" and design_pressure_pa < MIN_STAIRWELL_PRESSURIZATION_PA:
        violations.append(
            f"Zone '{zone_id}': Design pressure {design_pressure_pa:.1f} Pa "
            f"below minimum {MIN_STAIRWELL_PRESSURIZATION_PA} Pa per NFPA 92 §6.3"
        )

    # V106 FIX: NFPA 92 §6.3.3: Maximum pressure differential — excessive
    # pressure prevents doors from opening, trapping occupants
    if method == "pressurization" and design_pressure_pa > MAX_PRESSURE_DIFFERENTIAL_PA:
        violations.append(
            f"Zone '{zone_id}': Design pressure {design_pressure_pa:.1f} Pa "
            f"exceeds maximum {MAX_PRESSURE_DIFFERENTIAL_PA} Pa — "
            f"door opening force exceeds 30 lbf per NFPA 92 §6.3.3, "
            f"occupants may be TRAPPED"
        )

    # V106 FIX: Exhaust method — must verify minimum exhaust rate
    # NFPA 92 §6.4: Exhaust method requires defined air changes
    if method == "exhaust" and design_pressure_pa <= 0:
        violations.append(
            f"Zone '{zone_id}': Exhaust method with zero/negative flow rate "
            f"({design_pressure_pa:.1f}) — smoke cannot be removed per NFPA 92 §6.4"
        )

    # NFPA 72 §21.5: Fire alarm interlock
    if not has_fire_alarm_interlock:
        violations.append(
            f"Zone '{zone_id}': No fire alarm interlock — smoke control cannot activate automatically per NFPA 72 §21.5"
        )

    # NFPA 92: Stairwell pressurization required for high-rise
    if not has_stairwell_pressurization:
        violations.append(
            f"Zone '{zone_id}': No stairwell pressurization — egress path may become untenable per NFPA 92"
        )

    is_compliant = len(violations) == 0

    return SmokeControlResult(
        zone_id=zone_id,
        method=method,
        design_pressure_pa=design_pressure_pa,
        is_compliant=is_compliant,
        violations=tuple(violations),
        nfpa_section="NFPA 92 / NFPA 72 §21.5",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FIRE PUMP MONITORING — NFPA 20 / NFPA 72 §21.8
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FirePumpResult:
    """Result from fire pump monitoring assessment.

    NFPA 20 and NFPA 72 §21.8 require monitoring of:
      - Pump running status
      - Pump power failure
      - Phase reversal
      - Suction pressure (where applicable)
      - Controller switch position

    All signals must be supervisory type at the FACP.
    """

    pump_id: str
    has_running_signal: bool
    has_power_monitor: bool
    has_phase_reversal: bool
    is_compliant: bool
    violations: tuple
    nfpa_section: str


def evaluate_fire_pump(
    pump_id: str,
    # V114 FIX: Fail-safe defaults — missing signals = NOT present (NFPA 20 §10.4)
    has_running_signal: bool = False,
    has_power_monitor: bool = False,
    has_phase_reversal: bool = False,
    has_suction_pressure: bool = False,
) -> FirePumpResult:
    """Evaluate fire pump monitoring per NFPA 20 / NFPA 72 §21.8.

    NFPA 20 §10.4 and NFPA 72 §21.8 require:
      - Pump running: supervisory signal
      - Loss of power: supervisory signal
      - Phase reversal: supervisory signal
      - Controller not in automatic: supervisory signal

    Args:
        pump_id: Fire pump identifier.
        has_running_signal: Pump running status monitored.
        has_power_monitor: Power failure monitored.
        has_phase_reversal: Phase reversal monitored.
        has_suction_pressure: Suction pressure monitored.

    Returns:
        FirePumpResult with compliance assessment.

    """
    violations = []

    if not has_running_signal:
        violations.append(f"Pump '{pump_id}': No running signal — pump status unknown at FACP per NFPA 72 §21.8")

    if not has_power_monitor:
        violations.append(f"Pump '{pump_id}': No power monitoring — power failure undetected per NFPA 20 §10.4")

    if not has_phase_reversal:
        violations.append(f"Pump '{pump_id}': No phase reversal monitoring — motor may run backwards per NFPA 20 §10.4")

    is_compliant = len(violations) == 0

    return FirePumpResult(
        pump_id=pump_id,
        has_running_signal=has_running_signal,
        has_power_monitor=has_power_monitor,
        has_phase_reversal=has_phase_reversal,
        is_compliant=is_compliant,
        violations=tuple(violations),
        nfpa_section="NFPA 20 / NFPA 72 §21.8",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BUILDING SYSTEMS COMPOSITE ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class BuildingSystemsAssessment:
    """Composite assessment of all building fire safety integrations.

    This aggregates all building system assessments into a single
    result that can be used by the release gate system.
    """

    elevator_results: List[ElevatorRecallResult] = field(default_factory=list)
    hvac_results: List[HVACShutdownResult] = field(default_factory=list)
    smoke_control_results: List[SmokeControlResult] = field(default_factory=list)
    fire_pump_results: List[FirePumpResult] = field(default_factory=list)
    is_compliant: bool = False  # V96 FIX: Fail-safe default — unevaluated must NOT claim compliance
    violations: List[str] = field(default_factory=list)
    nfpa_references: List[str] = field(default_factory=list)

    def evaluate(self) -> None:
        """Aggregate all sub-assessments.

        V106 SAFETY FIX: Empty assessment lists means NO evaluation was performed.
        An unevaluated building must NOT claim compliance — fail-safe default.
        """
        self.violations = []
        self.nfpa_references = []

        # V106 CRITICAL FIX: If no assessments were performed, is_compliant
        # must remain False (fail-safe). Previously, is_compliant started as
        # True even when all lists were empty, falsely claiming compliance.
        total_assessments = (
            len(self.elevator_results)
            + len(self.hvac_results)
            + len(self.smoke_control_results)
            + len(self.fire_pump_results)
        )
        if total_assessments == 0:
            self.is_compliant = False  # No evaluation = not compliant (fail-safe)
            return

        self.is_compliant = True  # Start True only when assessments exist

        for r in self.elevator_results:
            if not r.is_compliant:
                self.is_compliant = False
                self.violations.extend(r.violations)
            self.nfpa_references.append(r.nfpa_section)

        for hvac_r in self.hvac_results:
            if not hvac_r.is_compliant:
                self.is_compliant = False
                self.violations.extend(hvac_r.violations)
            self.nfpa_references.append(hvac_r.nfpa_section)

        for smoke_r in self.smoke_control_results:
            if not smoke_r.is_compliant:
                self.is_compliant = False
                self.violations.extend(smoke_r.violations)
            self.nfpa_references.append(smoke_r.nfpa_section)

        for fp_r in self.fire_pump_results:
            if not fp_r.is_compliant:
                self.is_compliant = False
                self.violations.extend(fp_r.violations)
            self.nfpa_references.append(fp_r.nfpa_section)

        # Deduplicate references
        self.nfpa_references = list(dict.fromkeys(self.nfpa_references))
