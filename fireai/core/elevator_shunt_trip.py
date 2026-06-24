"""fireai/core/elevator_shunt_trip.py
===================================
Elevator Shunt-Trip Power Severance Auditor — CRITICAL LIFE-SAFETY MODULE.

V19.1 FIX: Added RTI (Response Time Index) thermodynamic validation.
The original V19 implementation only checked the temperature gap between
the heat detector and sprinkler ratings.  This is INSUFFICIENT because
thermal response depends on BOTH temperature rating AND RTI.  A heat
detector with a lower temperature rating but a MUCH higher RTI (slower
thermal response) will actuate AFTER a fast-response sprinkler bursts,
defeating the entire shunt-trip safety mechanism.

Physics:
  RTI (Response Time Index) quantifies how quickly a thermal device
  responds to a given heat flux.  A device with RTI=50 (m·s)^0.5 is
  "quick response"; RTI=150 is "standard response".  Under a fast-
  growing t² fire, the activation time of a device is proportional
  to its RTI and inversely proportional to the heat release rate.

  The critical test: the heat detector's COMBINED thermal lag
  (rating + RTI) must guarantee actuation BEFORE the sprinkler.
  If the sprinkler has a LOWER RTI than the heat detector, the
  sprinkler will respond to the thermal plume faster even if the
  heat detector's temperature setpoint is lower.

  Per NFPA 72 §21.4.2 and UL 521 / UL 199, the heat detector must
  have a response time index that guarantees actuation before the
  sprinkler under the design fire scenario.  The simplified rule:
  - HD temperature rating must be at least 11.1°C below sprinkler rating
  - HD RTI must be LESS THAN OR EQUAL TO sprinkler RTI
    (a slower HD cannot "outrun" a faster sprinkler)

Code references:
  - NFPA 72-2022 §21.4.1  — Shunt trip requirement
  - NFPA 72-2022 §21.4.2  — Heat detector placement & rating
  - ASME A17.1 Rule 2.8.3.3 — Elevator safety
  - NFPA 13-2022           — Sprinkler requirements in elevator spaces
  - UL 521                 — Standard for Heat Detectors for Fire
                            Protective Signaling Systems
  - SFPE Handbook           — Alpert ceiling jet correlations, RTI theory

Provenance:
  Returns ``DecisionProvenance`` via the ``.new()`` factory when
  ``src.v8_core`` is available; degrades gracefully to plain dict otherwise.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

# The heat detector must actuate at least 20 °F (11.1 °C) BELOW the
# sprinkler's temperature rating per NFPA 72 §21.4.2.
SAFETY_GAP_C: float = 11.1

# Maximum permissible horizontal distance between a sprinkler head and its
# dedicated shunt-trip heat detector — 2 ft = 0.61 m per NFPA 72 §21.4.2.
MAX_HD_SPRINKLER_DISTANCE_M: float = 0.6

# Default RTI values (m·s)^0.5
# Quick-response sprinkler per NFPA 13 §8.3.3.1
DEFAULT_SPRINKLER_RTI: float = 50.0
# V20.2 FIX: Standard-response heat detector per UL 521 typically has
# RTI of 100–150 (m·s)^0.5. Previous value of 50.0 was WRONG — it
# matched the quick-response sprinkler default, making the RTI check
# `hd_rti > (spk_rti * 1.0)` ALWAYS False. The V19.1 RTI fix was
# therefore a no-op with default values.
# A standard-response HD at RTI=100 will respond ~2× slower than a
# quick-response sprinkler (RTI=50), meaning the sprinkler bursts
# FIRST → electrified water → firefighter electrocution.
# Setting 100.0 (conservative standard-response) ensures the RTI
# check triggers by default when paired with quick-response sprinklers.
DEFAULT_HD_RTI: float = 100.0

# RTI threshold: if the HD's RTI exceeds the sprinkler's RTI by more
# than this factor, the HD is guaranteed to respond too slowly.
# Conservative limit: HD RTI must be ≤ sprinkler RTI (factor = 1.0).
RTI_RATIO_LIMIT: float = 1.0

# Standard sprinkler temperature ratings (°C) per NFPA 13 Table 6.2.5.1
STANDARD_SPRINKLER_TEMPS_C: Dict[str, float] = {
    "ordinary": 68.3,  # 155 °F
    "intermediate": 93.3,  # 200 °F
    "high": 140.6,  # 286 °F
    "extra_high": 182.2,  # 360 °F
}

# Standard heat detector temperature ratings (°C) per UL 521
STANDARD_HD_TEMPS_C: Dict[str, float] = {
    "135F": 57.2,  # 135 °F — most common for shunt-trip
    "145F": 62.8,  # 145 °F
    "160F": 71.1,  # 160 °F
    "190F": 87.8,  # 190 °F
    "200F": 93.3,  # 200 °F
}

# Citations
_CITE_NFPA72_21_4_1 = "NFPA 72-2022 §21.4.1"
_CITE_NFPA72_21_4_2 = "NFPA 72-2022 §21.4.2"
_CITE_ASME_A17_1 = "ASME A17.1 Rule 2.8.3.3"
_CITE_SFPE_RTI = "SFPE Handbook / UL 521 RTI"


@dataclass(frozen=True)
class ShuntTripResult:
    """Structured result for a single sprinkler head's shunt-trip audit."""

    sprinkler_id: str
    room_id: str
    has_dedicated_hd: bool
    hd_device_id: Optional[str] = None
    hd_distance_m: Optional[float] = None
    hd_temp_rating_C: Optional[float] = None
    hd_rti: Optional[float] = None
    required_hd_temp_C: float = 0.0
    sprinkler_temp_C: float = 0.0
    sprinkler_rti: float = 0.0
    rti_violation: bool = False
    temp_violation: bool = False
    compliant: bool = False
    violation_description: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class ElevatorShuntTripAuditor:
    """Audits elevator spaces for mandatory shunt-trip heat detector
    compliance per NFPA 72 §21.4.1 / ASME A17.1 Rule 2.8.3.3.

    V19.1 ENHANCEMENT: Now validates BOTH temperature gap AND RTI
    (Response Time Index) to ensure thermodynamic response priority.
    A heat detector with a lower temperature rating but a much higher
    RTI will respond too slowly to a fast-growing fire, allowing the
    sprinkler to burst before the shunt-trip signal is generated.

    The auditor examines every sprinkler located inside an elevator
    hoistway or machine room and verifies:

      1. A dedicated heat detector exists within 0.6 m of the sprinkler.
      2. The heat detector's temperature rating is at least 11.1 °C
         (20 °F) lower than the sprinkler's temperature rating.
      3. The heat detector's RTI is ≤ the sprinkler's RTI, guaranteeing
         that the HD responds to the thermal plume no slower than the
         sprinkler (SFPE Handbook / UL 521).

    When all conditions are met, the auditor generates a logic injection
    (``SHUNT_TRIP_POWER_DELAY_0s``) for the Sequence of Operations matrix
    to sever the elevator's main power breaker instantaneously.

    Usage::

        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=sprinklers,
            heat_detector_locations=heat_detectors,
            elevator_spaces=elevator_room_ids,
        )
    """

    def __init__(
        self,
        safety_gap_C: float = SAFETY_GAP_C,
        rti_ratio_limit: float = RTI_RATIO_LIMIT,
    ) -> None:
        """Initialise the auditor.

        Args:
            safety_gap_C: Minimum temperature gap (°C) between the heat
                detector and sprinkler ratings.  Defaults to 11.1 °C
                (20 °F) per NFPA 72 §21.4.2.
            rti_ratio_limit: Maximum allowed ratio of HD RTI to sprinkler
                RTI.  Defaults to 1.0 (HD must not be slower than
                sprinkler).  A more permissive value (e.g. 1.5) may be
                used when the temperature gap is sufficiently large.

        """
        self.safety_gap_C = safety_gap_C
        self.rti_ratio_limit = rti_ratio_limit

    def audit_hoistway_machine_room(
        self,
        sprinkler_locations: List[Dict[str, Any]],
        heat_detector_locations: List[Dict[str, Any]],
        elevator_spaces: List[str],
    ) -> Any:
        """Audit all sprinklers in elevator spaces for shunt-trip compliance.

        Each sprinkler dict now supports an optional ``rti`` field:
        - ``rti`` (float, optional): Response Time Index in (m·s)^0.5.
          Defaults to 50.0 (quick-response sprinkler per NFPA 13).

        Each heat detector dict now supports an optional ``rti`` field:
        - ``rti`` (float, optional): Response Time Index in (m·s)^0.5.
          Defaults to 50.0 (standard per UL 521).
        """
        violations: list = []
        injections: list = []
        detailed_results: List[ShuntTripResult] = []

        for sprinkler in sprinkler_locations:
            room_id = sprinkler.get("room_id", "")
            if room_id not in elevator_spaces:
                continue

            spk_id = sprinkler.get("device_id", "UNKNOWN-SPK")
            # V FIX: Wrap float() in try/except to prevent crash on non-numeric
            # strings (e.g., "N/A", "TBD"). Log error and continue to next device.
            try:
                spk_x = float(sprinkler.get("x", 0.0))
                spk_y = float(sprinkler.get("y", 0.0))
                spk_temp = float(sprinkler.get("temp_rating_C", 68.3))
                spk_rti = float(sprinkler.get("rti", DEFAULT_SPRINKLER_RTI))
            except (ValueError, TypeError) as e:
                logger.error(
                    f"Non-numeric data in sprinkler '{spk_id}': {e}. "
                    f"Skipping this device — cannot verify thermal response."
                )
                continue

            # V FIX: Validate sprinkler temperature is physically plausible.
            # NFPA 13 Table 6.2.5.1: ordinary=57-77°C, intermediate=79-163°C,
            # high=163-191°C, extra-high=191-343°C. Values outside 40-300°C
            # are not physically plausible for sprinkler temperature ratings.
            if spk_temp < 40.0 or spk_temp > 300.0:
                logger.warning(
                    f"Sprinkler '{spk_id}' temp_rating_C={spk_temp}°C is outside "
                    f"plausible range [40, 300] per NFPA 13 Table 6.2.5.1. "
                    f"Using default 68.3°C for heat detector matching."
                )
                spk_temp = 68.3

            # V57 FIX: NaN/Inf in sprinkler data bypasses all safety checks.
            # NaN > X is always False → no temp_violation, no rti_violation → compliant=True.
            # This means a sprinkler with corrupt data passes audit → electrocution risk.
            # Per Life-Safety Rule 2: every code change must be committed + pushed.
            _spk_nan = []
            if not math.isfinite(spk_x):
                _spk_nan.append("x")
            if not math.isfinite(spk_y):
                _spk_nan.append("y")
            if not math.isfinite(spk_temp):
                _spk_nan.append("temp_rating_C")
            if not math.isfinite(spk_rti):
                _spk_nan.append("rti")
            if _spk_nan:
                desc = (
                    f"NaN/Inf in sprinkler '{spk_id}' fields: {', '.join(_spk_nan)}. "
                    f"Cannot verify thermal response. Per NFPA 72 §21.4.2, "
                    f"shunt-trip CANNOT be safely designed with corrupt data."
                )
                logger.critical(desc)
                if Violation is not None:
                    violations.append(
                        Violation(
                            severity="CRITICAL",
                            citation=f"{_CITE_NFPA72_21_4_2} / {_CITE_ASME_A17_1}",
                            description=desc,
                        )
                    )
                else:
                    violations.append(
                        {
                            "severity": "CRITICAL",
                            "citation": f"{_CITE_NFPA72_21_4_2} / {_CITE_ASME_A17_1}",
                            "description": desc,
                        }
                    )
                continue  # Skip this sprinkler — cannot verify safety
            required_hd_temp = round(spk_temp - self.safety_gap_C, 1)

            # Find the closest heat detector in the same elevator space
            best_hd = None
            best_dist = float("inf")

            # V43 FIX: Track assigned HDs to enforce 1:1 sprinkler→HD mapping
            # per NFPA 72 §21.4.2. Previously, two sprinklers near the same HD
            # would both pass with that HD as their dedicated detector. But one
            # HD cannot trigger shunt-trip for two independent sprinklers — if
            # the unguarded sprinkler discharges, 480V windings are electrified.
            used_hd_ids = set()
            # Collect IDs of HDs already assigned to previous sprinklers
            for prev_result in detailed_results:
                if hasattr(prev_result, "hd_device_id") and prev_result.hd_device_id:
                    used_hd_ids.add(prev_result.hd_device_id)

            for hd in heat_detector_locations:
                if hd.get("room_id", "") != room_id:
                    continue
                hd_id_candidate = hd.get("device_id", "UNKNOWN-HD")
                # Skip HDs already assigned to another sprinkler
                if hd_id_candidate in used_hd_ids:
                    continue
                # V FIX: Wrap float() in try/except to prevent crash on non-numeric data
                try:
                    hd_x = float(hd.get("x", 0.0))
                    hd_y = float(hd.get("y", 0.0))
                except (ValueError, TypeError):
                    continue
                dist = math.hypot(spk_x - hd_x, spk_y - hd_y)
                if dist < best_dist:
                    best_dist = dist
                    best_hd = hd

            if best_hd is not None and best_dist <= MAX_HD_SPRINKLER_DISTANCE_M:
                hd_id = best_hd.get("device_id", "UNKNOWN-HD")
                # V FIX: Wrap float() in try/except
                _hd_warnings = []  # Collect warnings for this result
                try:
                    hd_temp = float(best_hd.get("temp_rating_C", 57.2))
                    hd_rti = float(best_hd.get("rti", DEFAULT_HD_RTI))
                except (ValueError, TypeError) as e:
                    _warn_msg = f"Non-numeric data in heat detector '{hd_id}': {e}. Using defaults (temp=57.2C, rti={DEFAULT_HD_RTI})."
                    logger.warning(_warn_msg)
                    _hd_warnings.append(_warn_msg)
                    hd_temp = 57.2
                    hd_rti = DEFAULT_HD_RTI

                # V57 FIX: NaN/Inf in HD data bypasses temperature and RTI checks.
                # NaN > threshold is False → no violation detected → compliant=True.
                # A heat detector with corrupt thermal data would PASS the audit,
                # potentially allowing sprinkler to burst before power is severed.
                _hd_nan = []
                if not math.isfinite(hd_temp):
                    _hd_nan.append("temp_rating_C")
                if not math.isfinite(hd_rti):
                    _hd_nan.append("rti")
                if _hd_nan:
                    # Force BOTH violations when data is corrupt (fail-safe)
                    temp_violation = True
                    rti_violation = True
                    logger.critical(
                        f"NaN/Inf in HD '{hd_id}' fields: {', '.join(_hd_nan)}. "
                        f"Forcing temp_violation=True and rti_violation=True (fail-safe). "
                        f"Cannot verify thermal response per NFPA 72 §21.4.2."
                    )
                else:
                    # CHECK 1: Temperature gap
                    temp_violation = hd_temp > required_hd_temp
                    # CHECK 2: RTI ratio — HD must not be slower than sprinkler
                    rti_violation = hd_rti > (spk_rti * self.rti_ratio_limit)

                if temp_violation or rti_violation:
                    # Build violation description
                    parts = []
                    if temp_violation:
                        parts.append(
                            f"Temperature rating ({hd_temp:.1f}°C) exceeds max allowed ({required_hd_temp:.1f}°C)"
                        )
                    if rti_violation:
                        parts.append(
                            f"RTI ({hd_rti:.0f} (m·s)^0.5) exceeds sprinkler "
                            f"RTI ({spk_rti:.0f}) — HD responds too slowly, "
                            f"sprinkler will burst before power is severed"
                        )
                    desc = (
                        f"Thermal Response MISMATCH for HD '{hd_id}' guarding "
                        f"sprinkler '{spk_id}' in {room_id}: "
                        + "; ".join(parts)
                        + ". Water shock on 480V windings is IMMINENT."
                    )
                    if Violation is not None:
                        violations.append(
                            Violation(
                                severity="CRITICAL",
                                citation=f"{_CITE_NFPA72_21_4_2} / {_CITE_ASME_A17_1} / {_CITE_SFPE_RTI}",
                                description=desc,
                            )
                        )
                    else:
                        violations.append(
                            {
                                "severity": "CRITICAL",
                                "citation": f"{_CITE_NFPA72_21_4_2} / {_CITE_ASME_A17_1} / {_CITE_SFPE_RTI}",
                                "description": desc,
                            }
                        )
                    logger.critical(desc)
                    detailed_results.append(
                        ShuntTripResult(
                            sprinkler_id=spk_id,
                            room_id=room_id,
                            has_dedicated_hd=True,
                            hd_device_id=hd_id,
                            hd_distance_m=round(best_dist, 4),
                            hd_temp_rating_C=hd_temp,
                            hd_rti=hd_rti,
                            required_hd_temp_C=round(required_hd_temp, 1),
                            sprinkler_temp_C=spk_temp,
                            sprinkler_rti=spk_rti,
                            rti_violation=rti_violation,
                            temp_violation=temp_violation,
                            compliant=False,
                            violation_description=desc,
                            warnings=_hd_warnings,
                        )
                    )
                else:
                    # ALL CHECKS PASSED → inject shunt-trip logic
                    injections.append(
                        {
                            "input": hd_id,
                            "action": "SHUNT_TRIP_POWER_DELAY_0s",
                            "target": f"ELEVATOR_BREAKER_{room_id}",
                        }
                    )
                    detailed_results.append(
                        ShuntTripResult(
                            sprinkler_id=spk_id,
                            room_id=room_id,
                            has_dedicated_hd=True,
                            hd_device_id=hd_id,
                            hd_distance_m=round(best_dist, 4),
                            hd_temp_rating_C=hd_temp,
                            hd_rti=hd_rti,
                            required_hd_temp_C=round(required_hd_temp, 1),
                            sprinkler_temp_C=spk_temp,
                            sprinkler_rti=spk_rti,
                            rti_violation=False,
                            temp_violation=False,
                            compliant=True,
                            warnings=_hd_warnings,
                        )
                    )
            else:
                # FATAL OMISSION: No heat detector within range
                desc = (
                    f"FATAL OMISSION: Sprinkler '{spk_id}' at "
                    f"({spk_x:.1f}, {spk_y:.1f}) in Elevator Space "
                    f"'{room_id}' lacks dedicated Shunt-Trip Heat Detector "
                    f"within {MAX_HD_SPRINKLER_DISTANCE_M} m. "
                    f"Water on 480 V motor windings will cause lethal "
                    f"electrocution."
                )
                if Violation is not None:
                    violations.append(
                        Violation(
                            severity="CRITICAL",
                            citation=_CITE_NFPA72_21_4_1,
                            description=desc,
                        )
                    )
                else:
                    violations.append(
                        {
                            "severity": "CRITICAL",
                            "citation": _CITE_NFPA72_21_4_1,
                            "description": desc,
                        }
                    )
                logger.critical(desc)
                detailed_results.append(
                    ShuntTripResult(
                        sprinkler_id=spk_id,
                        room_id=room_id,
                        has_dedicated_hd=False,
                        hd_distance_m=round(best_dist, 4) if best_hd else None,
                        hd_temp_rating_C=None,
                        hd_rti=None,
                        required_hd_temp_C=round(required_hd_temp, 1),
                        sprinkler_temp_C=spk_temp,
                        sprinkler_rti=spk_rti,
                        rti_violation=False,
                        temp_violation=False,
                        compliant=False,
                        violation_description=desc,
                    )
                )

        # Count sprinklers inside elevator spaces
        sprinklers_in_shaft = sum(1 for s in sprinkler_locations if s.get("room_id", "") in elevator_spaces)

        safe = len(violations) == 0

        # Build provenance result
        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NFPA72_21_4_1,
                        constant_id="SHUNT_TRIP",
                        value_used=self.safety_gap_C,
                        unit="Celsius",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA72_21_4_2,
                        constant_id="HD_SPRINKLER_MAX_DISTANCE",
                        value_used=MAX_HD_SPRINKLER_DISTANCE_M,
                        unit="metres",
                    ),
                    RuleApplied(
                        citation=_CITE_SFPE_RTI,
                        constant_id="RTI_RATIO_LIMIT",
                        value_used=self.rti_ratio_limit,
                        unit="dimensionless",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="elevator_shunt_trip",
                    value={
                        "logic_injections": injections,
                        "safe": safe,
                        "detailed_results": [
                            {
                                "sprinkler_id": r.sprinkler_id,
                                "room_id": r.room_id,
                                "has_dedicated_hd": r.has_dedicated_hd,
                                "hd_device_id": r.hd_device_id,
                                "hd_distance_m": r.hd_distance_m,
                                "hd_temp_rating_C": r.hd_temp_rating_C,
                                "hd_rti": r.hd_rti,
                                "required_hd_temp_C": r.required_hd_temp_C,
                                "sprinkler_temp_C": r.sprinkler_temp_C,
                                "sprinkler_rti": r.sprinkler_rti,
                                "rti_violation": r.rti_violation,
                                "temp_violation": r.temp_violation,
                                "compliant": r.compliant,
                                "violation_description": r.violation_description,
                            }
                            for r in detailed_results
                        ],
                    },
                    inputs={
                        "sprinklers_in_shaft": sprinklers_in_shaft,
                        "heat_detectors_total": len(heat_detector_locations),
                        "elevator_spaces": len(elevator_spaces),
                    },
                    rules_applied=rules,
                    algorithm={"name": "RTI_Differential_Comparator", "version": "v19.1"},
                    confidence=conf,
                    selected_because=(
                        "True thermodynamic validation replaces lazy delta-temp "
                        "checking.  Both temperature rating AND RTI must guarantee "
                        "HD actuation before sprinkler discharge per SFPE / UL 521."
                    ),
                    violations=violations if violations else None,
                )
            except Exception as e:
                logger.warning(
                    f"V112: audit_hoistway_machine_room: failed to construct DecisionProvenance audit result: {e!r}"
                )
                pass

        # Fallback: plain dict
        return {
            "decision_type": "elevator_shunt_trip",
            "value": {
                "logic_injections": injections,
                "safe": safe,
                "detailed_results": [
                    {
                        "sprinkler_id": r.sprinkler_id,
                        "room_id": r.room_id,
                        "has_dedicated_hd": r.has_dedicated_hd,
                        "hd_device_id": r.hd_device_id,
                        "hd_distance_m": r.hd_distance_m,
                        "hd_temp_rating_C": r.hd_temp_rating_C,
                        "hd_rti": r.hd_rti,
                        "required_hd_temp_C": r.required_hd_temp_C,
                        "sprinkler_temp_C": r.sprinkler_temp_C,
                        "sprinkler_rti": r.sprinkler_rti,
                        "rti_violation": r.rti_violation,
                        "temp_violation": r.temp_violation,
                        "compliant": r.compliant,
                        "violation_description": r.violation_description,
                    }
                    for r in detailed_results
                ],
            },
            "inputs": {
                "sprinklers_in_shaft": sprinklers_in_shaft,
                "heat_detectors_total": len(heat_detector_locations),
                "elevator_spaces": len(elevator_spaces),
            },
            "safe": safe,
            "violations": violations,
        }


__all__ = [
    "DEFAULT_HD_RTI",
    "DEFAULT_SPRINKLER_RTI",
    "MAX_HD_SPRINKLER_DISTANCE_M",
    "RTI_RATIO_LIMIT",
    "SAFETY_GAP_C",
    "STANDARD_HD_TEMPS_C",
    "STANDARD_SPRINKLER_TEMPS_C",
    "ElevatorShuntTripAuditor",
    "ShuntTripResult",
]
