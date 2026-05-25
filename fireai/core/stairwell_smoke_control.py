"""
fireai/core/stairwell_smoke_control.py
========================================
Stairwell Active Smoke Control & Pressurization Integrator.

V20 CRITICAL LIFE-SAFETY MODULE.

In buildings exceeding 75 ft (23 m) in height, NFPA 92 and NFPA 101
mandate that stairwells be pressurized to prevent smoke infiltration
during a fire event.  Without active pressurization, the stack effect
and buoyancy-driven flows turn stairwells into chimneys that draw
smoke upward, rendering the primary means of egress lethal.

The fire alarm panel MUST:
  1. Activate stairwell pressurization fans BEFORE general evacuation.
  2. Monitor differential pressure switches at each stairwell landing
     to verify positive pressure is maintained (typically 0.10–0.35
     inches water gauge / 25–87 Pa per NFPA 92 §6.4).
  3. Integrate with HVAC smoke control sequences per NFPA 92 §6.1.

This module analyses the building's stairwell zones and generates
the required control and monitoring device injections for the fire
alarm system's Sequence of Operations matrix.

Code references:
  - NFPA 92-2024 §6.1    — Stairwell pressurization
  - NFPA 92-2024 §6.4    — Pressure differential requirements
  - NFPA 101-2024 §7.2.3.9 — Stairwell pressurization in high-rises
  - IBC 2021 §909        — Smoke control systems
  - NFPA 72-2022 §21.6   — Emergency control function interfaces

Provenance:
  Returns ``DecisionProvenance`` via the ``.new()`` factory when
  ``src.v8_core`` is available; degrades gracefully to plain dict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        DecisionProvenance,
        RuleApplied,
        Violation,
        ConfidenceScore,
        ConfidenceLevel,
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

# Required minimum positive pressure in stairwell (Pa) per NFPA 92 §6.4
MIN_POSITIVE_PRESSURE_PA: float = 25.0

# Maximum positive pressure (Pa) — excessive pressure prevents door opening
# V20.2 FIX #18: Was 87.0 Pa, but NFPA 92 §6.4.2 limits to 85 Pa (door force
# limit per NFPA 101 §7.2.1.4.5). 87 Pa could allow designs where doors
# cannot be opened by occupants during a fire — TRAPPING PEOPLE inside.
# Changed to 85.0 Pa per NFPA 92 §6.4.2.
MAX_POSITIVE_PRESSURE_PA: float = 85.0

# Typical pressurization fan activation delay (seconds) — must occur
# BEFORE general evacuation alarm per NFPA 92 §6.1
FAN_ACTIVATION_DELAY_S: float = 0.0  # Immediate (0s delay)

# Citations
_CITE_NFPA92_6_1 = "NFPA 92-2024 §6.1"
_CITE_NFPA92_6_4 = "NFPA 92-2024 §6.4"
_CITE_NFPA101_7_2_3_9 = "NFPA 101-2024 §7.2.3.9"
_CITE_IBC_909 = "IBC 2021 §909"
_CITE_NFPA72_21_6 = "NFPA 72-2022 §21.6"


@dataclass(frozen=True)
class StairwellZone:
    """Represents a stairwell zone in the building.

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
    """
    zone_id: str
    name: str
    floors_served: List[str]
    top_floor_z: float
    roof_vent_location: Optional[Tuple[float, float]] = None
    landing_locations: Optional[Dict[str, Tuple[float, float]]] = None
    is_exterior: bool = False


@dataclass(frozen=True)
class PressurizationInjection:
    """A device injection for stairwell pressurization control."""
    device_type: str  # "CTRL_PRESSURIZATION_FAN" or "MON_PRESSURE_SWITCH"
    zone_id: str
    floor_id: str
    location: Tuple[float, float]
    action: str
    nfpa_reference: str


class StairwellSmokeControlIntegrator:
    """Analyses building stairwell zones and generates active smoke
    control device injections for the Sequence of Operations matrix.

    The integrator:
      1. Identifies stairwells in buildings exceeding the height
         threshold for pressurization.
      2. Generates CTRL_PRESSURIZATION_FAN devices at roof level.
      3. Generates MON_PRESSURE_SWITCH devices at each landing.
      4. Flags violations when pressurization is required but missing.

    Usage::

        integrator = StairwellSmokeControlIntegrator(
            building_height_m=60.0,
        )
        result = integrator.generate_active_smoke_defense(
            stairwells=[StairwellZone(...)],
        )
    """

    def __init__(
        self,
        building_height_m: float = 0.0,
        min_height_for_pressurization_m: float = MIN_HEIGHT_FOR_PRESSURIZATION_M,
    ) -> None:
        self.building_height_m = building_height_m
        self.min_height_m = min_height_for_pressurization_m

    def generate_active_smoke_defense(
        self,
        stairwells: List[Dict[str, Any]],
        building_height_m: Optional[float] = None,
    ) -> Any:
        """Generate active smoke control device injections for stairwells.

        Each element of *stairwells* must be a dict with:
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

        Args:
            stairwells: List of stairwell zone specifications.
            building_height_m: Override building height.  If None,
                uses the constructor value.

        Returns:
            ``DecisionProvenance`` or plain dict.
        """
        bldg_height = (
            building_height_m if building_height_m is not None
            else self.building_height_m
        )

        violations: list = []
        injections: List[Dict[str, Any]] = []

        # V25 FIX: NFPA 101 §7.2.3.9 says buildings "exceeding 75 ft" require
        # pressurization. "Exceeding" means strictly greater than (>), not
        # greater than or equal to (≥). A building at exactly 75 ft (22.86 m)
        # does NOT require pressurization per NFPA 101.
        pressurization_required = bldg_height > self.min_height_m

        for stair in stairwells:
            zone_id = stair.get("zone_id", "UNKNOWN-STAIR")
            name = stair.get("name", zone_id)
            floors_served = stair.get("floors_served", [])
            top_floor_z = float(stair.get("top_floor_z", 0.0))
            roof_vent = stair.get("roof_vent_location", (0.0, 0.0))
            landings = stair.get("landing_locations", {})
            has_fan = stair.get("has_pressurization_fan", False)
            has_switches = stair.get("has_pressure_switches", False)

            if not pressurization_required:
                # Building is low-rise — pressurization not required
                continue

            # Inject pressurization fan control
            if not has_fan:
                if roof_vent is None:
                    roof_vent = (0.0, 0.0)
                if isinstance(roof_vent, (list, tuple)) and len(roof_vent) >= 2:
                    vent_loc = (float(roof_vent[0]), float(roof_vent[1]))
                else:
                    vent_loc = (0.0, 0.0)

                injections.append({
                    "device_type": "CTRL_PRESSURIZATION_FAN",
                    "zone_id": zone_id,
                    "floor_id": "ROOF",
                    "location": vent_loc,
                    "action": f"ACTIVATE_STAIRWELL_FAN_{FAN_ACTIVATION_DELAY_S:.0f}s_DELAY",
                    "nfpa_reference": _CITE_NFPA92_6_1,
                })

                desc = (
                    f"Stairwell '{name}' ({zone_id}) in building "
                    f"({bldg_height:.1f} m ≥ {self.min_height_m:.1f} m) "
                    f"lacks pressurization fan control module. "
                    f"Stack effect will draw smoke into the stairwell, "
                    f"rendering the primary egress path lethal. "
                    f"Per {_CITE_NFPA92_6_1} / {_CITE_NFPA101_7_2_3_9}, "
                    f"pressurization is MANDATORY."
                )
                if Violation is not None:
                    violations.append(Violation(
                        severity="CRITICAL",
                        citation=f"{_CITE_NFPA92_6_1} / {_CITE_NFPA101_7_2_3_9}",
                        description=desc,
                    ))
                else:
                    violations.append({
                        "severity": "CRITICAL",
                        "citation": f"{_CITE_NFPA92_6_1} / {_CITE_NFPA101_7_2_3_9}",
                        "description": desc,
                    })
                logger.critical(desc)

            # Inject differential pressure monitoring at each landing
            if not has_switches:
                for floor_id in floors_served:
                    landing_loc = landings.get(floor_id, (0.0, 0.0))
                    if isinstance(landing_loc, (list, tuple)) and len(landing_loc) >= 2:
                        loc = (float(landing_loc[0]), float(landing_loc[1]))
                    else:
                        loc = (0.0, 0.0)

                    injections.append({
                        "device_type": "MON_PRESSURE_SWITCH",
                        "zone_id": zone_id,
                        "floor_id": floor_id,
                        "location": loc,
                        "action": "MONITOR_DIFF_PRESSURE",
                        "nfpa_reference": _CITE_NFPA92_6_4,
                    })

        safe = len(violations) == 0

        # V25 FIX: Validate MAX_POSITIVE_PRESSURE_PA constraint.
        # NFPA 92 §6.4.2 limits maximum stairwell pressure to prevent doors
        # from becoming impossible to open during evacuation. Without this
        # check, the system could approve a pressurization design that traps
        # occupants by exceeding 85 Pa — a life-safety failure.
        if pressurization_required:
            # If pressure data is provided, validate against max limit
            for stair in stairwells:
                zone_id = stair.get("zone_id", "UNKNOWN-STAIR")
                name = stair.get("name", zone_id)
                design_pressure = stair.get("design_pressure_pa", None)
                if design_pressure is not None and design_pressure > MAX_POSITIVE_PRESSURE_PA:
                    desc = (
                        f"Stairwell '{name}' ({zone_id}) design pressure "
                        f"({design_pressure:.1f} Pa) exceeds maximum "
                        f"({MAX_POSITIVE_PRESSURE_PA:.1f} Pa per NFPA 92 §6.4.2). "
                        f"Excessive pressure prevents door opening — occupants "
                        f"TRAPPED during fire evacuation. "
                        f"Per NFPA 101 §7.2.1.4.5, door force must not exceed "
                        f"the capability of the building occupants."
                    )
                    if Violation is not None:
                        violations.append(Violation(
                            severity="CRITICAL",
                            citation=f"{_CITE_NFPA92_6_4} / NFPA 101-2024 §7.2.1.4.5",
                            description=desc,
                        ))
                    else:
                        violations.append({
                            "severity": "CRITICAL",
                            "citation": f"{_CITE_NFPA92_6_4} / NFPA 101-2024 §7.2.1.4.5",
                            "description": desc,
                        })
                    logger.critical(desc)
                    safe = False

                # V43 FIX: Add minimum pressurization check per NFPA 92 §6.4.
                # Previously only checked maximum pressure. Insufficient pressurization
                # (below 25 Pa / 0.10 in. w.g.) allows smoke infiltration via stack
                # effect, rendering the primary egress path lethal.
                if design_pressure is not None and design_pressure < MIN_POSITIVE_PRESSURE_PA:
                    desc = (
                        f"Stairwell '{name}' ({zone_id}) design pressure "
                        f"({design_pressure:.1f} Pa) is BELOW minimum "
                        f"({MIN_POSITIVE_PRESSURE_PA:.1f} Pa per NFPA 92 §6.4). "
                        f"Insufficient pressurization allows smoke infiltration — "
                        f"primary egress path may become impassable. "
                        f"Increase design pressure to at least "
                        f"{MIN_POSITIVE_PRESSURE_PA:.1f} Pa."
                    )
                    if Violation is not None:
                        violations.append(Violation(
                            severity="CRITICAL",
                            citation=f"{_CITE_NFPA92_6_4}",
                            description=desc,
                        ))
                    else:
                        violations.append({
                            "severity": "CRITICAL",
                            "citation": _CITE_NFPA92_6_4,
                            "description": desc,
                        })
                    logger.critical(desc)
                    safe = False

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
                        citation=_CITE_NFPA92_6_4,
                        constant_id="MIN_POSITIVE_PRESSURE",
                        value_used=MIN_POSITIVE_PRESSURE_PA,
                        unit="Pa",
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
                        "defense_injections": injections,
                        "pressurization_required": pressurization_required,
                        "building_height_m": bldg_height,
                        "fan_controls": sum(
                            1 for i in injections
                            if i.get("device_type") == "CTRL_PRESSURIZATION_FAN"
                        ),
                        "pressure_monitors": sum(
                            1 for i in injections
                            if i.get("device_type") == "MON_PRESSURE_SWITCH"
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
                        f"egress path remains tenable per {_CITE_NFPA92_6_1}."
                    ),
                    violations=violations if violations else None,
                )
            except Exception:
                pass

        return {
            "decision_type": "stairwell_smoke_control",
            "value": {
                "defense_injections": injections,
                "pressurization_required": pressurization_required,
                "safe": safe,
            },
            "safe": safe,
            "violations": violations,
        }


__all__ = [
    "StairwellSmokeControlIntegrator",
    "StairwellZone",
    "PressurizationInjection",
    "MIN_HEIGHT_FOR_PRESSURIZATION_M",
    "MIN_POSITIVE_PRESSURE_PA",
    "MAX_POSITIVE_PRESSURE_PA",
]
