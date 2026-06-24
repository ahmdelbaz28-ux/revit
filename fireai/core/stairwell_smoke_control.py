"""fireai.core.stairwell_smoke_control — Stairwell Smoke Control Integrator
=========================================================================

V20 CRITICAL LIFE-SAFETY MODULE — Extended per QOMN-FIRE principles.

Integrates stairwell smoke control with the fire alarm system per
NFPA 92 and NFPA 72 §21.5.  In buildings exceeding 75 ft (22.86 m) in
height, NFPA 92 and NFPA 101 mandate that stairwells be pressurized to
prevent smoke infiltration during a fire event.  Without active
pressurization, the stack effect and buoyancy-driven flows turn
stairwells into chimneys that draw smoke upward, rendering the primary
means of egress lethal.

The fire alarm panel MUST:
  1. Activate stairwell pressurization fans automatically upon fire
     alarm per NFPA 72 §21.5.
  2. Monitor differential pressure switches at each stairwell landing
     to verify positive pressure is maintained (minimum 25 Pa per
     NFPA 92 §6.3, maximum 133 Pa per NFPA 92 §6.3.3).
  3. Provide pressurization fan status as supervisory signals per
     NFPA 72 §21.5.
  4. Integrate with HVAC smoke control sequences per NFPA 92 §6.1.
  5. Maintain pressurization or fail to a safe state on loss of power.

QOMN-FIRE PRINCIPLES:
  - Deterministic: every code path produces a defined result.
  - NaN-rejecting: all numeric inputs validated with math.isfinite().
  - Evidence-based: every decision traceable to an NFPA section.

ENGINEERING SOURCES:
  - NFPA 92-2024 §6.1    — Stairwell pressurization systems
  - NFPA 92-2024 §6.3    — Minimum pressurization (25 Pa / 0.10 in. w.g.)
  - NFPA 92-2024 §6.3.3  — Maximum pressure differential (133 Pa / 0.54 in. w.g.)
  - NFPA 92-2024 §6.4    — Pressure differential requirements
  - NFPA 72-2022 §21.5   — Emergency control function interfaces (smoke control)
  - NFPA 72-2022 §21.5.2 — Supervisory signals for smoke control
  - NFPA 101-2024 §7.2.3.8  — Smoke-proof enclosures (vestibule pressurization)
  - NFPA 101-2024 §7.2.3.9  — Stairwell pressurization in high-rises
  - IBC 2021 §909.6      — Smokeproof enclosures
  - IBC 2021 §403.5.4    — Vestibule pressurization for smoke-proof enclosures
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# Import smoke control primitives from building_systems_integration — these
# provide the foundational evaluate_smoke_control() validator and the
# canonical NFPA 92 constants (MIN_STAIRWELL_PRESSURIZATION_PA = 25.0,
# MAX_PRESSURE_DIFFERENTIAL_PA = 133.0).
from fireai.core.building_systems_integration import (
    MAX_PRESSURE_DIFFERENTIAL_PA,
    MIN_STAIRWELL_PRESSURIZATION_PA,
    SmokeControlResult,
    evaluate_smoke_control,
)

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Minimum building height requiring stairwell pressurization per NFPA 101
# §7.2.3.9 / IBC §909: 75 ft ≈ 22.86 m
MIN_HEIGHT_FOR_PRESSURIZATION_M: float = 22.86

# Required minimum positive pressure in stairwell (Pa) per NFPA 92 §6.3.
# Re-exported from building_systems_integration for module-level access;
# the authoritative value lives there (25.0 Pa = 0.10 in. w.g.).
MIN_POSITIVE_PRESSURE_PA: float = MIN_STAIRWELL_PRESSURIZATION_PA

# Maximum positive pressure (Pa) per NFPA 92 §6.3.3 — excessive pressure
# prevents door opening, trapping occupants.  133 Pa ≈ 0.54 in. w.g.,
# corresponding to a 30 lbf door-opening force limit per NFPA 101 §7.2.1.4.5.
MAX_POSITIVE_PRESSURE_PA: float = MAX_PRESSURE_DIFFERENTIAL_PA

# Vestibule pressurization for smoke-proof enclosures per NFPA 101 §7.2.3.8.
# A vestibule is an enclosed intermediate space between the stairwell and the
# floor corridor.  It requires its own pressurization (typically 25 Pa minimum)
# to prevent smoke from entering the stairwell via the vestibule door.
VESTIBULE_MIN_PRESSURIZATION_PA: float = MIN_STAIRWELL_PRESSURIZATION_PA

# Typical pressurization fan activation delay (seconds) — must occur
# BEFORE general evacuation alarm per NFPA 92 §6.1
FAN_ACTIVATION_DELAY_S: float = 0.0  # Immediate (0s delay)

# Citations
_CITE_NFPA92_6_1 = "NFPA 92-2024 §6.1"
_CITE_NFPA92_6_3 = "NFPA 92-2024 §6.3"
_CITE_NFPA92_6_3_3 = "NFPA 92-2024 §6.3.3"
_CITE_NFPA92_6_4 = "NFPA 92-2024 §6.4"
_CITE_NFPA72_21_5 = "NFPA 72-2022 §21.5"
_CITE_NFPA72_21_5_2 = "NFPA 72-2022 §21.5.2"
_CITE_NFPA101_7_2_3_8 = "NFPA 101-2024 §7.2.3.8"
_CITE_NFPA101_7_2_3_9 = "NFPA 101-2024 §7.2.3.9"
_CITE_IBC_909 = "IBC 2021 §909"
_CITE_IBC_403_5_4 = "IBC 2021 §403.5.4"
_CITE_NFPA72_21_6 = "NFPA 72-2022 §21.6"


# ============================================================================
# Enums
# ============================================================================


class FanStatus(str, Enum):
    """Pressurization fan operational status per NFPA 72 supervisory signal.

    NFPA 72 §21.5.2 requires that the FACP display the operational status
    of each smoke control element, including pressurization fans.

    Attributes:
        RUNNING: Fan is operating normally.
        STOPPED: Fan is off (may or may not be a fault condition).
        FAULT: Fan has reported a fault condition.
        UNKNOWN: Fan status cannot be determined (communication loss).

    """

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


class FailSafeState(str, Enum):
    """Fail-safe state for stairwell pressurization on power loss.

    NFPA 92 §6.1 and NFPA 72 §21.5 require that stairwell pressurization
    systems maintain a safe state upon loss of power or communication.
    The fail-safe state must preserve the pressurization function.

    Attributes:
        MAINTAIN_PRESSURIZATION: Fan continues on emergency power.
            This is the preferred fail-safe — stairwell stays pressurized.
        DOORS_OPEN_TO_VENT: If power cannot be maintained, doors
            automatically open to provide natural ventilation.  This
            is a secondary fail-safe for systems without standby power.
        ALARM_ONLY: System can only signal the fault — no automatic
            corrective action.  Requires firefighter intervention.

    """

    MAINTAIN_PRESSURIZATION = "MAINTAIN_PRESSURIZATION"
    DOORS_OPEN_TO_VENT = "DOORS_OPEN_TO_VENT"
    ALARM_ONLY = "ALARM_ONLY"


class VestibuleType(str, Enum):
    """Vestibule classification for smoke-proof enclosures.

    NFPA 101 §7.2.3.8 and IBC §403.5.4 define smoke-proof enclosures
    as having either a vestibule or an exterior balcony providing
    natural ventilation.

    Attributes:
        PRESSURIZED_VESTIBULE: Enclosed vestibule with active
            pressurization (minimum 25 Pa per NFPA 92 §6.3).
        NATURALLY_VENTILATED_VESTIBULE: Vestibule with openings
            to the exterior for natural ventilation.
        NO_VESTIBULE: No vestibule — stairwell door opens directly
            to the floor corridor (not a smoke-proof enclosure).

    """

    PRESSURIZED_VESTIBULE = "PRESSURIZED_VESTIBULE"
    NATURALLY_VENTILATED_VESTIBULE = "NATURALLY_VENTILATED_VESTIBULE"
    NO_VESTIBULE = "NO_VESTIBULE"


# ============================================================================
# Frozen Dataclasses — Results
# ============================================================================


@dataclass(frozen=True)
class StairwellZone:
    """Represents a stairwell zone in the building.

    A stairwell zone is a single enclosed stairway serving one or more
    floors.  Each zone has independent pressurization control and
    monitoring.

    Attributes:
        zone_id: Unique stairwell identifier (e.g. "STAIR-A").
        name: Human-readable name (e.g. "Stairwell A").
        floors_served: List of floor IDs served by this stairwell.
        top_floor_z: Elevation of the top floor served (metres).
        roof_vent_location: (x, y) location of the roof-level
            pressurization fan supply point.
        landing_locations: Dict mapping floor_id → (x, y) for each
            stairwell landing where pressure monitoring is required.
        is_exterior: Whether the stairwell has exterior exposure
            (affects pressurization design).
        design_pressure_pa: Design pressurization setpoint in Pascals.
            Must be between 25 Pa and 133 Pa per NFPA 92 §6.3/§6.3.3.
        has_pressurization_fan: Whether a pressurization fan is installed.
        has_pressure_switches: Whether differential pressure monitoring
            is installed at each landing.
        has_fire_alarm_interlock: Whether the fire alarm panel can
            automatically activate the pressurization fan per NFPA 72 §21.5.
        fail_safe_state: The fail-safe state for this stairwell zone
            upon loss of power or communication.
        has_emergency_power: Whether the pressurization fan is connected
            to a standby/emergency power source.
        vestibule_type: Type of vestibule for smoke-proof enclosure
            classification per NFPA 101 §7.2.3.8.
        vestibule_design_pressure_pa: Design pressurization setpoint for
            the vestibule (if pressurized vestibule type).  Must be
            at least 25 Pa per NFPA 92 §6.3.

    """

    zone_id: str
    name: str
    floors_served: List[str]
    top_floor_z: float
    roof_vent_location: Optional[Tuple[float, float]] = None
    landing_locations: Optional[Dict[str, Tuple[float, float]]] = None
    is_exterior: bool = False
    design_pressure_pa: Optional[float] = None
    has_pressurization_fan: bool = False
    has_pressure_switches: bool = False
    # V114 FIX: Fail-safe — interlock must be confirmed, not assumed
    has_fire_alarm_interlock: bool = False
    fail_safe_state: FailSafeState = FailSafeState.MAINTAIN_PRESSURIZATION
    has_emergency_power: bool = False
    vestibule_type: VestibuleType = VestibuleType.NO_VESTIBULE
    vestibule_design_pressure_pa: Optional[float] = None


@dataclass(frozen=True)
class PressurizationInjection:
    """A device injection for stairwell pressurization control.

    Represents a control or monitoring device that must be added to the
    fire alarm system's Sequence of Operations matrix for stairwell
    smoke control.

    Attributes:
        device_type: Type of device to inject (e.g. "CTRL_PRESSURIZATION_FAN",
            "MON_PRESSURE_SWITCH", "CTRL_VESTIBULE_FAN").
        zone_id: Stairwell zone identifier.
        floor_id: Floor where the device is located.
        location: (x, y) position of the device.
        action: Control action or monitoring function.
        nfpa_reference: NFPA code section requiring this device.

    """

    device_type: str
    zone_id: str
    floor_id: str
    location: Tuple[float, float]
    action: str
    nfpa_reference: str


@dataclass(frozen=True)
class FanStatusResult:
    """Result of pressurization fan status evaluation.

    NFPA 72 §21.5.2 requires that the FACP supervise the operational
    status of smoke control equipment, including pressurization fans.
    A fan in FAULT or UNKNOWN status must be reported as a supervisory
    condition.

    Attributes:
        zone_id: Stairwell zone identifier.
        fan_id: Pressurization fan identifier.
        status: Current fan operational status.
        is_supervisory: Whether this status requires a supervisory
            signal at the FACP per NFPA 72 §21.5.2.
        description: Human-readable description of the fan status.

    """

    zone_id: str
    fan_id: str
    status: FanStatus
    is_supervisory: bool
    description: str


@dataclass(frozen=True)
class FireAlarmActivationResult:
    """Result of fire alarm automatic activation assessment.

    NFPA 72 §21.5 requires that stairwell pressurization systems activate
    automatically upon fire alarm.  The activation must occur before
    general evacuation alarm per NFPA 92 §6.1.

    Attributes:
        zone_id: Stairwell zone identifier.
        activation_required: Whether automatic activation is required
            for this stairwell zone.
        is_activated: Whether the pressurization system is currently
            activated (or would be upon fire alarm).
        has_interlock: Whether the fire alarm interlock is present.
        activation_delay_s: Delay between fire alarm and fan activation
            (must be 0 for stairwell pressurization).
        is_compliant: Whether the activation configuration complies
            with NFPA 72 §21.5.
        violations: Tuple of violation descriptions (empty if compliant).

    """

    zone_id: str
    activation_required: bool
    is_activated: bool
    has_interlock: bool
    activation_delay_s: float
    is_compliant: bool
    violations: tuple = ()


@dataclass(frozen=True)
class VestibulePressurizationResult:
    """Result of vestibule pressurization assessment.

    NFPA 101 §7.2.3.8 and IBC §403.5.4 require smoke-proof enclosures
    for stairwells in high-rise buildings.  A pressurized vestibule is
    one method of achieving smoke-proof enclosure classification.

    Attributes:
        zone_id: Stairwell zone identifier.
        vestibule_type: Type of vestibule for this stairwell.
        design_pressure_pa: Vestibule design pressurization (Pa).
            Required for pressurized vestibules; must be ≥ 25 Pa
            per NFPA 92 §6.3.
        is_compliant: Whether the vestibule configuration complies
            with NFPA 101 §7.2.3.8 / IBC §403.5.4.
        violations: Tuple of violation descriptions (empty if compliant).

    """

    zone_id: str
    vestibule_type: VestibuleType
    design_pressure_pa: Optional[float]
    is_compliant: bool
    violations: tuple = ()


@dataclass(frozen=True)
class FailSafeAssessment:
    """Assessment of fail-safe capability for a stairwell zone.

    NFPA 92 §6.1 and NFPA 72 §21.5 require that stairwell pressurization
    systems maintain pressurization or fail to a safe state upon loss of
    power or communication.  Without emergency power, the fan stops and
    the stairwell loses pressurization — the stack effect then draws
    smoke into the primary egress path.

    Attributes:
        zone_id: Stairwell zone identifier.
        fail_safe_state: The configured fail-safe state.
        has_emergency_power: Whether the fan is on emergency power.
        can_maintain_pressurization: Whether the stairwell can maintain
            pressurization on loss of normal power.
        is_compliant: Whether the fail-safe configuration complies
            with NFPA 92 §6.1 and NFPA 72 §21.5.
        violations: Tuple of violation descriptions (empty if compliant).

    """

    zone_id: str
    fail_safe_state: FailSafeState
    has_emergency_power: bool
    can_maintain_pressurization: bool
    is_compliant: bool
    violations: tuple = ()


@dataclass(frozen=True)
class StairwellSmokeControlResult:
    """Comprehensive result from stairwell smoke control integration.

    Aggregates all assessment results for a stairwell zone into a single
    frozen result object.  This is the primary output of the
    StairwellSmokeControlIntegrator.

    Attributes:
        zone_id: Stairwell zone identifier.
        building_height_m: Building height in metres.
        pressurization_required: Whether pressurization is required
            based on building height per NFPA 101 §7.2.3.9.
        smoke_control_result: Result from evaluate_smoke_control()
            from building_systems_integration.
        fan_status: Fan status assessment per NFPA 72 §21.5.2.
        activation_result: Fire alarm activation assessment per
            NFPA 72 §21.5.
        vestibule_result: Vestibule pressurization assessment per
            NFPA 101 §7.2.3.8.
        fail_safe_assessment: Fail-safe capability assessment per
            NFPA 92 §6.1.
        injections: Device injections for the Sequence of Operations.
        is_compliant: Whether the stairwell zone complies with all
            applicable NFPA requirements.
        violations: Tuple of all violation descriptions.

    """

    zone_id: str
    building_height_m: float
    pressurization_required: bool
    smoke_control_result: Optional[SmokeControlResult]
    fan_status: Optional[FanStatusResult]
    activation_result: Optional[FireAlarmActivationResult]
    vestibule_result: Optional[VestibulePressurizationResult]
    fail_safe_assessment: Optional[FailSafeAssessment]
    injections: tuple = ()
    is_compliant: bool = False
    violations: tuple = ()


# ============================================================================
# Numeric Validation Helpers
# ============================================================================


def _validate_finite(value: float, name: str) -> float:
    """Validate that a numeric value is finite (not NaN, not Inf).

    QOMN-FIRE principle: NaN and Inf inputs are REJECTED with ValueError.
    NaN comparisons silently return False, which can bypass all safety
    checks.  For example, ``NaN < 25`` and ``NaN > 133`` are both False,
    so a NaN pressure would pass both min and max checks — a lethal
    false compliance.

    Args:
        value: The numeric value to validate.
        name: Parameter name for error messages.

    Returns:
        The validated value (unchanged).

    Raises:
        ValueError: If value is NaN or Inf.

    """
    if not math.isfinite(value):
        raise ValueError(
            f"{name} must be finite (not NaN or Inf), got {value}. "
            f"Non-finite values bypass NFPA 92 safety checks — "
            f"NaN comparisons silently return False, producing "
            f"lethal false compliance."
        )
    return value


def _validate_non_negative_finite(value: float, name: str) -> float:
    """Validate that a numeric value is non-negative and finite.

    Extends _validate_finite to also reject negative values.  Negative
    pressure in stairwell pressurization draws smoke INTO the egress
    path — a lethal condition.

    Args:
        value: The numeric value to validate.
        name: Parameter name for error messages.

    Returns:
        The validated value (unchanged).

    Raises:
        ValueError: If value is NaN, Inf, or negative.

    """
    _validate_finite(value, name)
    if value < 0:
        raise ValueError(
            f"{name} must be non-negative, got {value}. "
            f"Negative pressure draws smoke INTO egress paths — "
            f"lethal condition per NFPA 92 §6.3."
        )
    return value


def _validate_non_empty_str(value: str, name: str) -> str:
    """Validate that a string value is not empty or whitespace-only.

    QOMN-FIRE principle: empty identifiers make violations untraceable.

    Args:
        value: The string value to validate.
        name: Parameter name for error messages.

    Returns:
        The validated value (stripped of leading/trailing whitespace).

    Raises:
        ValueError: If value is empty or whitespace-only.

    """
    if not value or not value.strip():
        raise ValueError(
            f"{name} must not be empty — violations must be traceable to a specific zone per NFPA 92 / NFPA 72 §21.5."
        )
    return value.strip()


# ============================================================================
# StairwellSmokeControlIntegrator
# ============================================================================


class StairwellSmokeControlIntegrator:
    """Analyses building stairwell zones and generates active smoke
    control device injections for the Sequence of Operations matrix.

    Integrates stairwell smoke control with the fire alarm system per
    NFPA 92 and NFPA 72 §21.5.  The integrator:

      1. Identifies stairwells in buildings exceeding the height
         threshold for pressurization (75 ft / 22.86 m per NFPA 101
         §7.2.3.9).
      2. Validates pressurization design pressures against NFPA 92
         §6.3 (minimum 25 Pa) and §6.3.3 (maximum 133 Pa) using the
         ``evaluate_smoke_control`` function from
         ``building_systems_integration``.
      3. Generates CTRL_PRESSURIZATION_FAN devices at roof level.
      4. Generates MON_PRESSURE_SWITCH devices at each landing.
      5. Assesses pressurization fan status monitoring per
         NFPA 72 §21.5.2 (supervisory signals).
      6. Evaluates fire alarm automatic activation per
         NFPA 72 §21.5.
      7. Assesses vestibule pressurization for smoke-proof enclosures
         per NFPA 101 §7.2.3.8.
      8. Evaluates fail-safe capability on loss of power per
         NFPA 92 §6.1 and NFPA 72 §21.5.
      9. Flags violations when pressurization is required but missing.

    QOMN-FIRE PRINCIPLES:
      - Deterministic: every code path produces a defined result.
      - NaN-rejecting: all numeric inputs validated with
        ``math.isfinite()``; non-finite values raise ``ValueError``.
      - Evidence-based: every decision traceable to an NFPA section.

    Usage::

        integrator = StairwellSmokeControlIntegrator(
            building_height_m=60.0,
        )
        result = integrator.generate_active_smoke_defense(
            stairwells=[StairwellZone(...)],
        )

    Attributes:
        building_height_m: Building height in metres.
        min_height_m: Height threshold for pressurization requirement.

    """

    def __init__(
        self,
        building_height_m: float = 0.0,
        min_height_for_pressurization_m: float = MIN_HEIGHT_FOR_PRESSURIZATION_M,
    ) -> None:
        """Initialize the stairwell smoke control integrator.

        Args:
            building_height_m: Building height in metres.  Must be finite.
                A value of 0.0 means "not provided" — pressurization
                analysis will be inactive (a CRITICAL log warns that
                the module is inactive).
            min_height_for_pressurization_m: Height threshold above
                which stairwell pressurization is required per
                NFPA 101 §7.2.3.9.  Default is 22.86 m (75 ft).

        Raises:
            ValueError: If building_height_m is NaN or Inf.

        """
        # Validate building_height_m — NaN/Inf must be rejected
        if not math.isfinite(building_height_m):
            raise ValueError(
                f"building_height_m must be finite, got {building_height_m}. "
                f"Non-finite height disables pressurization analysis — "
                f"NaN comparisons silently return False."
            )

        # V48 FIX: building_height_m=0.0 neuters the entire module —
        # pressurization_required = 0.0 > 22.86 = False. A 50-story building
        # would pass with zero pressurization. Now emit CRITICAL log warning.
        # V FIX: Also set a flag to mark ALL results as non-compliant when
        # height is unknown. In a high-rise, unknown height = unknown
        # pressurization requirement = FAIL (fail-safe). A building with
        # missing height data must NOT be marked compliant.
        self._height_unknown = False
        if building_height_m <= 0.0:
            logger.critical(
                "STAIRWELL-001: building_height_m=%.1f — stairwell smoke control is INACTIVE. "
                "Pass building_height_m > 0 to enable pressurization analysis per NFPA 92 §6.1. "
                "ALL stairwell zones will be marked NON-COMPLIANT (fail-safe).",
                building_height_m,
            )
            self._height_unknown = True

        _validate_finite(min_height_for_pressurization_m, "min_height_for_pressurization_m")

        self.building_height_m = building_height_m
        self.min_height_m = min_height_for_pressurization_m

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def generate_active_smoke_defense(
        self,
        stairwells: List[Dict[str, Any]],
        building_height_m: Optional[float] = None,
    ) -> Any:
        """Generate active smoke control device injections for stairwells.

        Each element of *stairwells* must be a dict with at least:
        - ``zone_id`` (str): Stairwell zone identifier.
        - ``name`` (str, optional): Human-readable name.
        - ``floors_served`` (list[str]): Floor IDs served.
        - ``top_floor_z`` (float): Elevation of top floor (m).
        - ``roof_vent_location`` (tuple, optional): (x, y) for fan.
        - ``landing_locations`` (dict, optional): {floor_id: (x, y)}.
        - ``has_pressurization_fan`` (bool, optional): Whether a fan
          already exists.
        - ``has_pressure_switches`` (bool, optional): Whether pressure
          monitoring exists.
        - ``design_pressure_pa`` (float, optional): Design pressurization
          setpoint in Pascals.
        - ``has_fire_alarm_interlock`` (bool, optional): Whether the
          fire alarm panel can activate the fan automatically.
        - ``fan_status`` (str, optional): Current fan status — one of
          "RUNNING", "STOPPED", "FAULT", "UNKNOWN".
        - ``fail_safe_state`` (str, optional): Fail-safe state — one of
          "MAINTAIN_PRESSURIZATION", "DOORS_OPEN_TO_VENT", "ALARM_ONLY".
        - ``has_emergency_power`` (bool, optional): Whether the fan is
          on emergency/standby power.
        - ``vestibule_type`` (str, optional): Vestibule type — one of
          "PRESSURIZED_VESTIBULE", "NATURALLY_VENTILATED_VESTIBULE",
          "NO_VESTIBULE".
        - ``vestibule_design_pressure_pa`` (float, optional): Vestibule
          design pressure in Pascals (required for pressurized vestibules).

        Args:
            stairwells: List of stairwell zone specifications.
            building_height_m: Override building height.  If None,
                uses the constructor value.

        Returns:
            ``DecisionProvenance`` or plain dict.

        Raises:
            ValueError: If building_height_m override is NaN or Inf,
                or if any stairwell numeric field is NaN or Inf.

        """
        # Validate override height
        if building_height_m is not None:
            if not math.isfinite(building_height_m):
                raise ValueError(
                    f"building_height_m must be finite, got {building_height_m}. "
                    f"Non-finite height disables pressurization analysis — "
                    f"NaN comparisons silently return False."
                )

        bldg_height = building_height_m if building_height_m is not None else self.building_height_m

        all_violations: list = []
        all_injections: List[Dict[str, Any]] = []
        zone_results: List[StairwellSmokeControlResult] = []

        # Determine if pressurization is required based on building height
        # V25 FIX: NFPA 101 §7.2.3.9 says buildings "exceeding 75 ft"
        # require pressurization.  "Exceeding" means strictly greater
        # than (>), not greater than or equal to (≥).
        pressurization_required = bldg_height > self.min_height_m

        for stair in stairwells:
            zone_id = _validate_non_empty_str(stair.get("zone_id", ""), "zone_id")
            name = stair.get("name", zone_id)
            floors_served = stair.get("floors_served", [])

            # Validate top_floor_z
            top_floor_z = stair.get("top_floor_z", 0.0)
            if not math.isfinite(top_floor_z):
                raise ValueError(f"Stairwell '{name}' ({zone_id}): top_floor_z must be finite, got {top_floor_z}.")

            # Validate design_pressure_pa if provided
            design_pressure_pa = stair.get("design_pressure_pa", None)
            if design_pressure_pa is not None:
                _validate_non_negative_finite(design_pressure_pa, f"Stairwell '{name}' ({zone_id}) design_pressure_pa")

            # Validate vestibule_design_pressure_pa if provided
            vestibule_design_pressure_pa = stair.get("vestibule_design_pressure_pa", None)
            if vestibule_design_pressure_pa is not None:
                _validate_non_negative_finite(
                    vestibule_design_pressure_pa, f"Stairwell '{name}' ({zone_id}) vestibule_design_pressure_pa"
                )

            # If pressurization is not required for this building, skip
            # detailed analysis but record the zone as non-required
            # V FIX: When building height is unknown (height_unknown flag),
            # mark all zones as NON-COMPLIANT (fail-safe). Unknown height
            # means we cannot determine if pressurization is required.
            if not pressurization_required:
                is_compliant = not self._height_unknown
                violations_list = () if is_compliant else (
                    "BUILDING_HEIGHT_UNKNOWN: Building height not provided — "
                    "pressurization requirement cannot be determined per NFPA 92 §6.1. "
                    "Zone marked NON-COMPLIANT (fail-safe).",
                )
                zone_results.append(
                    StairwellSmokeControlResult(
                        zone_id=zone_id,
                        building_height_m=bldg_height,
                        pressurization_required=False,
                        smoke_control_result=None,
                        fan_status=None,
                        activation_result=None,
                        vestibule_result=None,
                        fail_safe_assessment=None,
                        injections=(),
                        is_compliant=is_compliant,
                        violations=violations_list,
                    )
                )
                continue

            # ── 1. Smoke control assessment (delegates to
            #       building_systems_integration.evaluate_smoke_control)
            #       per NFPA 92 / NFPA 72 §21.5 ──────────────────────
            smoke_control_result = self._assess_smoke_control(stair, zone_id, name)

            # ── 2. Fan status monitoring per NFPA 72 §21.5.2 ────────
            fan_status_result = self._assess_fan_status(stair, zone_id, name)

            # ── 3. Fire alarm automatic activation per NFPA 72 §21.5 ─
            activation_result = self._assess_fire_alarm_activation(stair, zone_id, name)

            # ── 4. Vestibule pressurization per NFPA 101 §7.2.3.8 ───
            vestibule_result = self._assess_vestibule(stair, zone_id, name)

            # ── 5. Fail-safe assessment per NFPA 92 §6.1 / §21.5 ────
            fail_safe = self._assess_fail_safe(stair, zone_id, name)

            # ── 6. Device injections for Sequence of Operations ──────
            injections = self._generate_injections(stair, zone_id, name, floors_served)

            # Aggregate violations
            zone_violations: List[str] = []
            if smoke_control_result and not smoke_control_result.is_compliant:
                zone_violations.extend(smoke_control_result.violations)
            if activation_result and not activation_result.is_compliant:
                zone_violations.extend(activation_result.violations)
            if vestibule_result and not vestibule_result.is_compliant:
                zone_violations.extend(vestibule_result.violations)
            if fail_safe and not fail_safe.is_compliant:
                zone_violations.extend(fail_safe.violations)
            if fan_status_result and fan_status_result.is_supervisory:
                zone_violations.append(fan_status_result.description)

            # Flag missing fan as critical violation
            has_fan = stair.get("has_pressurization_fan", False)
            if not has_fan:
                desc = (
                    f"Stairwell '{name}' ({zone_id}) in building "
                    f"({bldg_height:.1f} m > {self.min_height_m:.1f} m) "
                    f"lacks pressurization fan control module. "
                    f"Stack effect will draw smoke into the stairwell, "
                    f"rendering the primary egress path lethal. "
                    f"Per {_CITE_NFPA92_6_1} / {_CITE_NFPA101_7_2_3_9}, "
                    f"pressurization is MANDATORY."
                )
                zone_violations.append(desc)
                logger.critical(desc)

            # Flag missing pressure switches
            has_switches = stair.get("has_pressure_switches", False)
            if not has_switches and has_fan:
                desc = (
                    f"Stairwell '{name}' ({zone_id}) has pressurization fan "
                    f"but NO differential pressure monitoring. Cannot verify "
                    f"that positive pressure is maintained per "
                    f"{_CITE_NFPA92_6_4}."
                )
                zone_violations.append(desc)
                logger.critical(desc)

            # Validate design_pressure range when provided
            if design_pressure_pa is not None:
                if design_pressure_pa < MIN_POSITIVE_PRESSURE_PA:
                    desc = (
                        f"Stairwell '{name}' ({zone_id}) design pressure "
                        f"({design_pressure_pa:.1f} Pa) is BELOW minimum "
                        f"({MIN_POSITIVE_PRESSURE_PA:.1f} Pa per "
                        f"{_CITE_NFPA92_6_3}). Insufficient pressurization "
                        f"allows smoke infiltration — primary egress path "
                        f"may become impassable."
                    )
                    zone_violations.append(desc)
                    logger.critical(desc)

                if design_pressure_pa > MAX_POSITIVE_PRESSURE_PA:
                    desc = (
                        f"Stairwell '{name}' ({zone_id}) design pressure "
                        f"({design_pressure_pa:.1f} Pa) EXCEEDS maximum "
                        f"({MAX_POSITIVE_PRESSURE_PA:.1f} Pa per "
                        f"{_CITE_NFPA92_6_3_3}). Excessive pressure prevents "
                        f"door opening — occupants TRAPPED during fire "
                        f"evacuation per NFPA 101 §7.2.1.4.5."
                    )
                    zone_violations.append(desc)
                    logger.critical(desc)

            # Missing design_pressure when pressurization is required
            if design_pressure_pa is None and pressurization_required:
                has_equipment = has_fan and has_switches
                if has_equipment:
                    desc = (
                        f"Stairwell '{name}' ({zone_id}) has pressurization "
                        f"equipment (fan + pressure switches) but "
                        f"design_pressure_pa is NOT specified. Cannot verify "
                        f"compliance with {_CITE_NFPA92_6_3} "
                        f"({MIN_POSITIVE_PRESSURE_PA:.0f}–"
                        f"{MAX_POSITIVE_PRESSURE_PA:.0f} Pa). "
                        f"Commissioning data should be provided."
                    )
                    logger.warning(desc)
                else:
                    desc = (
                        f"Stairwell '{name}' ({zone_id}) requires "
                        f"pressurization but design_pressure_pa is NOT "
                        f"specified. Cannot verify compliance with "
                        f"{_CITE_NFPA92_6_3} "
                        f"({MIN_POSITIVE_PRESSURE_PA:.0f}–"
                        f"{MAX_POSITIVE_PRESSURE_PA:.0f} Pa). "
                        f"Pressurization design MUST be validated by a "
                        f"licensed fire protection engineer."
                    )
                    zone_violations.append(desc)
                    logger.critical(desc)

            # Propagate all zone violations to the aggregate list
            all_violations.extend(zone_violations)

            zone_compliant = len(zone_violations) == 0

            # Collect injection dicts
            injection_dicts = [
                {
                    "device_type": inj.device_type,
                    "zone_id": inj.zone_id,
                    "floor_id": inj.floor_id,
                    "location": inj.location,
                    "action": inj.action,
                    "nfpa_reference": inj.nfpa_reference,
                }
                for inj in injections
            ]
            all_injections.extend(injection_dicts)

            zone_results.append(
                StairwellSmokeControlResult(
                    zone_id=zone_id,
                    building_height_m=bldg_height,
                    pressurization_required=pressurization_required,
                    smoke_control_result=smoke_control_result,
                    fan_status=fan_status_result,
                    activation_result=activation_result,
                    vestibule_result=vestibule_result,
                    fail_safe_assessment=fail_safe,
                    injections=tuple(injections),
                    is_compliant=zone_compliant,
                    violations=tuple(zone_violations),
                )
            )

        safe = len(all_violations) == 0

        # Build provenance result
        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NFPA92_6_1,
                        constant_id="STAIRWELL_PRESSURIZATION",
                        value_used=self.min_height_m,
                        unit="metres",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA92_6_3,
                        constant_id="MIN_POSITIVE_PRESSURE",
                        value_used=MIN_POSITIVE_PRESSURE_PA,
                        unit="Pa",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA92_6_3_3,
                        constant_id="MAX_POSITIVE_PRESSURE",
                        value_used=MAX_POSITIVE_PRESSURE_PA,
                        unit="Pa",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA72_21_5,
                        constant_id="FIRE_ALARM_INTERLOCK",
                        value_used=True,
                        unit="bool",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="stairwell_smoke_control",
                    value={
                        "defense_injections": all_injections,
                        "pressurization_required": pressurization_required,
                        "building_height_m": bldg_height,
                        "zone_results": [
                            {
                                "zone_id": r.zone_id,
                                "is_compliant": r.is_compliant,
                                "violations": r.violations,
                            }
                            for r in zone_results
                        ],
                        "fan_controls": sum(
                            1 for i in all_injections if i.get("device_type") == "CTRL_PRESSURIZATION_FAN"
                        ),
                        "pressure_monitors": sum(
                            1 for i in all_injections if i.get("device_type") == "MON_PRESSURE_SWITCH"
                        ),
                        "vestibule_controls": sum(
                            1 for i in all_injections if i.get("device_type") == "CTRL_VESTIBULE_FAN"
                        ),
                        "safe": safe,
                    },
                    inputs={
                        "stairwells_analyzed": len(stairwells),
                        "building_height_m": bldg_height,
                    },
                    rules_applied=rules,
                    algorithm={"name": "ActiveSmokeDefenseGenerator", "version": "v20"},
                    confidence=conf,
                    selected_because=(
                        "Stairwell pressurization prevents stack-effect smoke "
                        "ingress in high-rise buildings.  Active control modules "
                        "and differential pressure monitoring ensure the primary "
                        f"egress path remains tenable per {_CITE_NFPA92_6_1}.  "
                        f"Fire alarm interlock per {_CITE_NFPA72_21_5} ensures "
                        f"automatic activation on fire alarm."
                    ),
                    violations=all_violations if all_violations else None,
                )
            except Exception as exc:
                logger.error("Failed to record stairwell smoke control decision audit: %s", exc)

        return {
            "decision_type": "stairwell_smoke_control",
            "value": {
                "defense_injections": all_injections,
                "pressurization_required": pressurization_required,
                "zone_results": [
                    {
                        "zone_id": r.zone_id,
                        "is_compliant": r.is_compliant,
                        "violations": r.violations,
                    }
                    for r in zone_results
                ],
                "safe": safe,
            },
            "safe": safe,
            "violations": all_violations,
        }

    # ------------------------------------------------------------------
    # Sub-assessments
    # ------------------------------------------------------------------

    def _assess_smoke_control(
        self,
        stair: Dict[str, Any],
        zone_id: str,
        name: str,
    ) -> Optional[SmokeControlResult]:
        """Delegate smoke control assessment to evaluate_smoke_control().

        Uses the ``evaluate_smoke_control`` function from
        ``building_systems_integration`` to validate the stairwell zone
        against NFPA 92 / NFPA 72 §21.5 requirements.  This ensures
        consistency with the building-level smoke control assessment.

        Args:
            stair: Stairwell specification dict.
            zone_id: Validated zone identifier.
            name: Human-readable name.

        Returns:
            SmokeControlResult from evaluate_smoke_control(), or None
            if the required parameters are missing.

        """
        design_pressure_pa = stair.get("design_pressure_pa")
        has_fire_alarm_interlock = stair.get(
            "has_fire_alarm_interlock",
            False,  # V112: FAIL-SAFE — missing interlock data = NOT verified
        )
        has_pressurization_fan = stair.get("has_pressurization_fan", False)

        # If design_pressure is not provided, use minimum as default
        # for the evaluate_smoke_control call — the missing-pressure
        # violation is handled separately in the main method.
        if design_pressure_pa is None:
            design_pressure_pa = MIN_POSITIVE_PRESSURE_PA

        try:
            result = evaluate_smoke_control(
                zone_id=zone_id,
                method="pressurization",
                design_pressure_pa=design_pressure_pa,
                has_fire_alarm_interlock=has_fire_alarm_interlock,
                has_stairwell_pressurization=has_pressurization_fan,
            )
            logger.info(
                "Smoke control assessment for zone '%s': compliant=%s",
                zone_id,
                result.is_compliant,
            )
            return result
        except ValueError as exc:
            # evaluate_smoke_control raises ValueError on invalid inputs
            # (bad method, negative pressure, etc.) — log and re-raise
            # as these indicate data integrity issues.
            logger.critical(
                "Smoke control assessment FAILED for zone '%s': %s",
                zone_id,
                exc,
            )
            raise

    def _assess_fan_status(
        self,
        stair: Dict[str, Any],
        zone_id: str,
        name: str,
    ) -> FanStatusResult:
        """Assess pressurization fan status monitoring.

        NFPA 72 §21.5.2 requires that the FACP supervise the operational
        status of smoke control equipment, including pressurization fans.
        A fan in FAULT or UNKNOWN status must be reported as a supervisory
        condition at the FACP.

        Args:
            stair: Stairwell specification dict.
            zone_id: Validated zone identifier.
            name: Human-readable name.

        Returns:
            FanStatusResult with fan status assessment.

        """
        raw_status = stair.get("fan_status", "UNKNOWN")
        fan_id = stair.get("fan_id", f"FAN-{zone_id}")

        try:
            status = FanStatus(raw_status)
        except ValueError:
            logger.warning(
                "Stairwell '%s' (%s): Unknown fan status '%s' — defaulting to UNKNOWN per NFPA 72 §21.5.2.",
                name,
                zone_id,
                raw_status,
            )
            status = FanStatus.UNKNOWN

        # NFPA 72 §21.5.2: FAULT and UNKNOWN require supervisory signal
        # MED-07 FIX: STOPPED also requires supervisory signal. Per NFPA 72 §21.5.2,
        # the FACP must supervise the operational status of smoke control equipment.
        # A STOPPED fan in a building requiring pressurization means the egress path
        # may not be protected — this is a supervisory condition requiring operator
        # awareness and acknowledgment, not just an informational status.
        is_supervisory = status in (FanStatus.FAULT, FanStatus.UNKNOWN, FanStatus.STOPPED)

        descriptions = {
            FanStatus.RUNNING: (
                f"Stairwell '{name}' ({zone_id}) fan '{fan_id}' is RUNNING. Normal operation per NFPA 72 §21.5.2."
            ),
            FanStatus.STOPPED: (
                f"Stairwell '{name}' ({zone_id}) fan '{fan_id}' is STOPPED. "
                f"Supervisory signal required at FACP per NFPA 72 §21.5.2. "
                f"Verify if this is expected (standby) or a fault condition. "
                f"Stairwell may not maintain pressurization if fire occurs."
            ),
            FanStatus.FAULT: (
                f"Stairwell '{name}' ({zone_id}) fan '{fan_id}' FAULT. "
                f"Supervisory signal required at FACP per NFPA 72 §21.5.2. "
                f"Stairwell may not maintain pressurization — egress path "
                f"potentially compromised."
            ),
            FanStatus.UNKNOWN: (
                f"Stairwell '{name}' ({zone_id}) fan '{fan_id}' status UNKNOWN. "
                f"Supervisory signal required at FACP per NFPA 72 §21.5.2. "
                f"Cannot verify pressurization — egress path status unknown."
            ),
        }

        description = descriptions[status]

        if is_supervisory:
            logger.critical(description)

        return FanStatusResult(
            zone_id=zone_id,
            fan_id=fan_id,
            status=status,
            is_supervisory=is_supervisory,
            description=description,
        )

    def _assess_fire_alarm_activation(
        self,
        stair: Dict[str, Any],
        zone_id: str,
        name: str,
    ) -> FireAlarmActivationResult:
        """Assess fire alarm automatic activation per NFPA 72 §21.5.

        NFPA 72 §21.5 requires that stairwell pressurization systems
        activate automatically upon fire alarm.  The activation must
        occur before general evacuation alarm per NFPA 92 §6.1 (zero
        delay for stairwell pressurization).

        Args:
            stair: Stairwell specification dict.
            zone_id: Validated zone identifier.
            name: Human-readable name.

        Returns:
            FireAlarmActivationResult with activation assessment.

        """
        has_interlock = stair.get("has_fire_alarm_interlock", False)  # V112: FAIL-SAFE
        activation_delay_s = stair.get("activation_delay_s", FAN_ACTIVATION_DELAY_S)

        # Validate activation_delay_s
        if not math.isfinite(activation_delay_s):
            raise ValueError(
                f"Stairwell '{name}' ({zone_id}): activation_delay_s must be finite, got {activation_delay_s}."
            )

        violations: List[str] = []
        activation_required = True  # Always required for high-rise stairwells

        # NFPA 72 §21.5: Fire alarm interlock required
        if not has_interlock:
            violations.append(
                f"Stairwell '{name}' ({zone_id}): No fire alarm interlock — "
                f"pressurization cannot activate automatically on fire alarm "
                f"per {_CITE_NFPA72_21_5}. Manual activation only — delayed "
                f"response may allow smoke infiltration."
            )
            logger.critical(
                "Stairwell '%s' (%s): NO fire alarm interlock — pressurization cannot auto-activate per NFPA 72 §21.5.",
                name,
                zone_id,
            )

        # NFPA 92 §6.1: Zero delay for stairwell pressurization
        # Any delay in stairwell pressurization activation allows smoke
        # to infiltrate the primary egress path before fans reach full
        # pressurization.
        if activation_delay_s > 0:
            violations.append(
                f"Stairwell '{name}' ({zone_id}): Activation delay "
                f"{activation_delay_s:.1f}s is non-zero. NFPA 92 §6.1 "
                f"requires stairwell pressurization activation BEFORE "
                f"general evacuation alarm — zero delay required."
            )
            logger.warning(
                "Stairwell '%s' (%s): Activation delay %.1fs > 0 — smoke may infiltrate before pressurization.",
                name,
                zone_id,
                activation_delay_s,
            )

        is_activated = has_interlock and activation_delay_s <= 0

        return FireAlarmActivationResult(
            zone_id=zone_id,
            activation_required=activation_required,
            is_activated=is_activated,
            has_interlock=has_interlock,
            activation_delay_s=activation_delay_s,
            is_compliant=len(violations) == 0,
            violations=tuple(violations),
        )

    def _assess_vestibule(
        self,
        stair: Dict[str, Any],
        zone_id: str,
        name: str,
    ) -> VestibulePressurizationResult:
        """Assess vestibule pressurization for smoke-proof enclosures.

        NFPA 101 §7.2.3.8 and IBC §403.5.4 require smoke-proof
        enclosures for stairwells in high-rise buildings.  A pressurized
        vestibule is one method of achieving smoke-proof enclosure
        classification.  The vestibule must maintain at least 25 Pa
        positive pressure per NFPA 92 §6.3.

        Smoke-proof enclosures provide an intermediate buffer zone
        between the floor corridor and the stairwell, preventing smoke
        from directly entering the stairwell when doors are opened.

        Args:
            stair: Stairwell specification dict.
            zone_id: Validated zone identifier.
            name: Human-readable name.

        Returns:
            VestibulePressurizationResult with vestibule assessment.

        """
        raw_vestibule_type = stair.get("vestibule_type", VestibuleType.NO_VESTIBULE.value)
        vestibule_design_pressure_pa = stair.get("vestibule_design_pressure_pa")

        try:
            vestibule_type = VestibuleType(raw_vestibule_type)
        except ValueError:
            logger.warning(
                "Stairwell '%s' (%s): Unknown vestibule_type '%s' — defaulting to NO_VESTIBULE.",
                name,
                zone_id,
                raw_vestibule_type,
            )
            vestibule_type = VestibuleType.NO_VESTIBULE

        violations: List[str] = []

        # Pressurized vestibule requires valid design pressure
        if vestibule_type == VestibuleType.PRESSURIZED_VESTIBULE:
            if vestibule_design_pressure_pa is None:
                violations.append(
                    f"Stairwell '{name}' ({zone_id}): Pressurized vestibule "
                    f"but vestibule_design_pressure_pa is NOT specified. "
                    f"Cannot verify compliance with {_CITE_NFPA92_6_3} "
                    f"(minimum {VESTIBULE_MIN_PRESSURIZATION_PA:.0f} Pa). "
                    f"Per {_CITE_NFPA101_7_2_3_8} / {_CITE_IBC_403_5_4}, "
                    f"vestibule pressurization design MUST be validated."
                )
                logger.critical(
                    "Stairwell '%s' (%s): Pressurized vestibule with NO design pressure specified.",
                    name,
                    zone_id,
                )
            elif vestibule_design_pressure_pa < VESTIBULE_MIN_PRESSURIZATION_PA:
                violations.append(
                    f"Stairwell '{name}' ({zone_id}): Vestibule design "
                    f"pressure ({vestibule_design_pressure_pa:.1f} Pa) is "
                    f"below minimum ({VESTIBULE_MIN_PRESSURIZATION_PA:.0f} Pa "
                    f"per {_CITE_NFPA92_6_3}). Insufficient vestibule "
                    f"pressurization may allow smoke infiltration into "
                    f"the stairwell."
                )
                logger.critical(
                    "Stairwell '%s' (%s): Vestibule pressure %.1f Pa below minimum %.0f Pa.",
                    name,
                    zone_id,
                    vestibule_design_pressure_pa,
                    VESTIBULE_MIN_PRESSURIZATION_PA,
                )

            # Check vestibule pressure doesn't exceed door force limit
            if vestibule_design_pressure_pa is not None and vestibule_design_pressure_pa > MAX_POSITIVE_PRESSURE_PA:
                violations.append(
                    f"Stairwell '{name}' ({zone_id}): Vestibule design "
                    f"pressure ({vestibule_design_pressure_pa:.1f} Pa) "
                    f"exceeds maximum ({MAX_POSITIVE_PRESSURE_PA:.0f} Pa "
                    f"per {_CITE_NFPA92_6_3_3}). Excessive pressure "
                    f"prevents vestibule door opening."
                )

        # Naturally ventilated vestibule — verify openings exist
        # (no pressurization check needed, but must have ventilation)
        if vestibule_type == VestibuleType.NATURALLY_VENTILATED_VESTIBULE:
            # Naturally ventilated vestibules rely on openings to exterior
            # IBC §909.6.2: Minimum opening area requirements
            logger.info(
                "Stairwell '%s' (%s): Naturally ventilated vestibule — verify exterior openings per IBC §909.6.2.",
                name,
                zone_id,
            )

        # No vestibule — may not meet smoke-proof enclosure requirements
        # for high-rise buildings per IBC §403.5.4
        if vestibule_type == VestibuleType.NO_VESTIBULE:
            logger.info(
                "Stairwell '%s' (%s): No vestibule — stairwell doors "
                "open directly to corridor. Verify if smoke-proof "
                "enclosure is required per IBC §403.5.4.",
                name,
                zone_id,
            )

        return VestibulePressurizationResult(
            zone_id=zone_id,
            vestibule_type=vestibule_type,
            design_pressure_pa=vestibule_design_pressure_pa,
            is_compliant=len(violations) == 0,
            violations=tuple(violations),
        )

    def _assess_fail_safe(
        self,
        stair: Dict[str, Any],
        zone_id: str,
        name: str,
    ) -> FailSafeAssessment:
        """Assess fail-safe capability on loss of power.

        NFPA 92 §6.1 and NFPA 72 §21.5 require that stairwell
        pressurization systems maintain pressurization or fail to a safe
        state upon loss of power or communication.

        The preferred fail-safe is MAINTAIN_PRESSURIZATION via emergency
        power.  Without emergency power, the fan stops and the stairwell
        loses pressurization — the stack effect then draws smoke into
        the primary egress path, potentially killing occupants.

        Args:
            stair: Stairwell specification dict.
            zone_id: Validated zone identifier.
            name: Human-readable name.

        Returns:
            FailSafeAssessment with fail-safe capability assessment.

        """
        raw_fail_safe = stair.get(
            "fail_safe_state",
            FailSafeState.MAINTAIN_PRESSURIZATION.value,
        )
        has_emergency_power = stair.get("has_emergency_power", False)

        try:
            fail_safe_state = FailSafeState(raw_fail_safe)
        except ValueError:
            logger.warning(
                "Stairwell '%s' (%s): Unknown fail_safe_state '%s' — defaulting to MAINTAIN_PRESSURIZATION.",
                name,
                zone_id,
                raw_fail_safe,
            )
            fail_safe_state = FailSafeState.MAINTAIN_PRESSURIZATION

        violations: List[str] = []

        # Can the stairwell maintain pressurization on power loss?
        can_maintain = fail_safe_state == FailSafeState.MAINTAIN_PRESSURIZATION and has_emergency_power

        # MAINTAIN_PRESSURIZATION without emergency power is impossible
        if fail_safe_state == FailSafeState.MAINTAIN_PRESSURIZATION and not has_emergency_power:
            violations.append(
                f"Stairwell '{name}' ({zone_id}): Fail-safe state is "
                f"MAINTAIN_PRESSURIZATION but NO emergency power is "
                f"provided. Without emergency power, the pressurization "
                f"fan CANNOT maintain operation during a power outage. "
                f"Stack effect will draw smoke into the stairwell, "
                f"rendering the primary egress path lethal. "
                f"Provide emergency power per {_CITE_NFPA92_6_1} / "
                f"{_CITE_NFPA72_21_5}, or change fail-safe state to "
                f"DOORS_OPEN_TO_VENT."
            )
            logger.critical(
                "Stairwell '%s' (%s): MAINTAIN_PRESSURIZATION fail-safe "
                "but NO emergency power — stairwell will lose "
                "pressurization on power failure.",
                name,
                zone_id,
            )

        # ALARM_ONLY fail-safe — no automatic corrective action
        if fail_safe_state == FailSafeState.ALARM_ONLY:
            violations.append(
                f"Stairwell '{name}' ({zone_id}): Fail-safe state is "
                f"ALARM_ONLY — no automatic corrective action on power "
                f"loss. Stairwell will lose pressurization, requiring "
                f"firefighter intervention. Per {_CITE_NFPA92_6_1} / "
                f"{_CITE_NFPA72_21_5}, stairwell pressurization must be "
                f"maintained or a safe alternative state must be achieved."
            )
            logger.warning(
                "Stairwell '%s' (%s): ALARM_ONLY fail-safe — requires firefighter intervention on power loss.",
                name,
                zone_id,
            )

        # DOORS_OPEN_TO_VENT — secondary fail-safe
        if fail_safe_state == FailSafeState.DOORS_OPEN_TO_VENT:
            logger.info(
                "Stairwell '%s' (%s): DOORS_OPEN_TO_VENT fail-safe — "
                "natural ventilation on power loss. Verify door "
                "auto-open mechanism per NFPA 92 §6.1.",
                name,
                zone_id,
            )

        return FailSafeAssessment(
            zone_id=zone_id,
            fail_safe_state=fail_safe_state,
            has_emergency_power=has_emergency_power,
            can_maintain_pressurization=can_maintain,
            is_compliant=len(violations) == 0,
            violations=tuple(violations),
        )

    # ------------------------------------------------------------------
    # Device injection generation
    # ------------------------------------------------------------------

    def _generate_injections(
        self,
        stair: Dict[str, Any],
        zone_id: str,
        name: str,
        floors_served: List[str],
    ) -> List[PressurizationInjection]:
        """Generate device injections for the Sequence of Operations.

        Creates control and monitoring device entries for:
          - Pressurization fan control at roof level
          - Differential pressure monitoring at each landing
          - Vestibule fan control (for pressurized vestibules)
          - Fire alarm interlock monitoring

        Args:
            stair: Stairwell specification dict.
            zone_id: Validated zone identifier.
            name: Human-readable name.
            floors_served: List of floor IDs served by this stairwell.

        Returns:
            List of PressurizationInjection objects.

        """
        injections: List[PressurizationInjection] = []

        has_fan = stair.get("has_pressurization_fan", False)
        has_switches = stair.get("has_pressure_switches", False)
        roof_vent = stair.get("roof_vent_location", (0.0, 0.0))
        landings = stair.get("landing_locations", {})
        vestibule_type = stair.get("vestibule_type", VestibuleType.NO_VESTIBULE.value)

        # --- Pressurization fan control ---
        if not has_fan:
            if roof_vent is None:
                roof_vent = (0.0, 0.0)
            if isinstance(roof_vent, (list, tuple)) and len(roof_vent) >= 2:
                vent_loc = (float(roof_vent[0]), float(roof_vent[1]))
            else:
                vent_loc = (0.0, 0.0)

            injections.append(
                PressurizationInjection(
                    device_type="CTRL_PRESSURIZATION_FAN",
                    zone_id=zone_id,
                    floor_id="ROOF",
                    location=vent_loc,
                    action=(f"ACTIVATE_STAIRWELL_FAN_{FAN_ACTIVATION_DELAY_S:.0f}s_DELAY"),
                    nfpa_reference=_CITE_NFPA92_6_1,
                )
            )

        # --- Differential pressure monitoring at each landing ---
        if not has_switches:
            for floor_id in floors_served:
                landing_loc = landings.get(floor_id, (0.0, 0.0))
                if isinstance(landing_loc, (list, tuple)) and len(landing_loc) >= 2:
                    loc = (float(landing_loc[0]), float(landing_loc[1]))
                else:
                    loc = (0.0, 0.0)

                injections.append(
                    PressurizationInjection(
                        device_type="MON_PRESSURE_SWITCH",
                        zone_id=zone_id,
                        floor_id=floor_id,
                        location=loc,
                        action="MONITOR_DIFF_PRESSURE",
                        nfpa_reference=_CITE_NFPA92_6_4,
                    )
                )

        # --- Vestibule fan control (pressurized vestibules) ---
        if vestibule_type == VestibuleType.PRESSURIZED_VESTIBULE.value:
            # Vestibule requires its own pressurization fan
            vestibule_vent = stair.get("vestibule_vent_location", (0.0, 0.0))
            if isinstance(vestibule_vent, (list, tuple)) and len(vestibule_vent) >= 2:
                v_loc = (float(vestibule_vent[0]), float(vestibule_vent[1]))
            else:
                v_loc = (0.0, 0.0)

            injections.append(
                PressurizationInjection(
                    device_type="CTRL_VESTIBULE_FAN",
                    zone_id=zone_id,
                    floor_id="VESTIBULE",
                    location=v_loc,
                    action="ACTIVATE_VESTIBULE_PRESSURIZATION",
                    nfpa_reference=(f"{_CITE_NFPA101_7_2_3_8} / {_CITE_IBC_403_5_4}"),
                )
            )

        # --- Fire alarm interlock monitoring ---
        has_interlock = stair.get("has_fire_alarm_interlock", False)  # V112: FAIL-SAFE
        if not has_interlock:
            injections.append(
                PressurizationInjection(
                    device_type="MON_FIRE_ALARM_INTERLOCK",
                    zone_id=zone_id,
                    floor_id="FACP",
                    location=(0.0, 0.0),
                    action="MONITOR_FAN_INTERLOCK_STATUS",
                    nfpa_reference=_CITE_NFPA72_21_5,
                )
            )

        return injections


__all__ = [
    "MAX_POSITIVE_PRESSURE_PA",
    "MIN_HEIGHT_FOR_PRESSURIZATION_M",
    "MIN_POSITIVE_PRESSURE_PA",
    "VESTIBULE_MIN_PRESSURIZATION_PA",
    "FailSafeAssessment",
    "FailSafeState",
    "FanStatus",
    "FanStatusResult",
    "FireAlarmActivationResult",
    "PressurizationInjection",
    "StairwellSmokeControlIntegrator",
    "StairwellSmokeControlResult",
    "StairwellZone",
    "VestibulePressurizationResult",
    "VestibuleType",
]
