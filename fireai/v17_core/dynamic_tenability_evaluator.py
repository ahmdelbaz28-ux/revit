"""v17_core/dynamic_tenability_evaluator.py — NFPA 101 §9.3 ASET vs RSET
======================================================================
CRITICAL LIFE-SAFETY MODULE — Part of the V17 Critical Trilogy

Wrapper around the physics-correct ASET/RSET calculator from
fireai.core.aset_rset_calculator, adding DecisionProvenance audit trails
and the TenabilityEvaluator class interface requested by the consultant.

The consultant's proposed code had these errors (all fixed in fireai.core):
  1. Fixed walking speed 1.0 m/s — varies by occupancy type (0.5-1.1 m/s)
     per NFPA 101 / SFPE / PD 7974-6.
  2. Fixed pre-movement delay 60s — ranges from 15s (high-hazard trained)
     to 300s (sleeping residential) per PD 7974-6 Table 6.
  3. Safety factor 2.0 without justification — should be risk-category-based
     (1.0 prescriptive, 1.5 standard, 2.0 high-risk, 2.5 very-high) per SFPE.
  4. No ASET tenability criteria — just accepted smoke_fill_time as-is.
     Should check smoke layer height (1.8m), temperature (60°C), CO (1500 ppm),
     visibility (10m), and O2 (12%) per SFPE / BS 7974.
  5. No path-based egress — only straight-line distance.
  6. Wrong import: fireai.v8_core.decision_provenance

Real-world failure scenario: A long corridor with two closed office doors.
Smoke fills the corridor in 120s. Walking speed is 0.7 m/s for elderly
residential occupants, with 180s pre-movement delay. RSET = 180 + 61/0.7
= 267s. With 2.5x safety factor (residential/sleeping) = 668s. ASET = 120s.
FAIL — occupants will be exposed to untenable conditions 548s before
reaching exit. Consultant's code with 1.0 m/s and 60s delay would show
RSET = 121s, passing with 2.0x factor (242s) and incorrectly deeming
the design safe.

NFPA 101 / SFPE References:
  - NFPA 101 §9.3: Means of Egress
  - SFPE Engineering Guide to Performance-Based Fire Protection
  - BS 7974:2019: Application of fire safety engineering principles
  - PD 7974-6:2019: Evacuation timing

Usage:
    from fireai.v17_core import TenabilityEvaluator

    evaluator = TenabilityEvaluator(
        walking_speed_mps=1.0,
        pre_movement_delay_s=60.0,
    )
    provenance = evaluator.validate_aset_vs_rset(
        longest_travel_dist_m=45.0,
        estimated_fill_time_s=300.0,
        safety_margin=2.0,
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Import the correct provenance shim (not the consultant's fireai.v8_core path)
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

# Import the physics-correct implementation from fireai.core
from fireai.core.aset_rset_calculator import (
    TENABILITY_THRESHOLDS,
    calculate_aset,
    calculate_rset,
    perform_aset_rset_analysis,
    validate_aset_vs_rset,
)


class TenabilityEvaluator:
    """V17 Dynamic Tenability Evaluator with DecisionProvenance audit trail.

    Evaluates whether building occupants can escape before conditions become
    untenable. This is the FUNDAMENTAL life-safety analysis:

        ASET (Available Safe Egress Time): Time until conditions become
              untenable (smoke layer descends to 1.8m, temperature > 60°C,
              visibility < 10m, CO > 1500 ppm at exit level).

        RSET (Required Safe Egress Time):  Time occupants need to reach
              a safe exit, including pre-movement delay and travel time.

        Design is SAFE only if:  ASET > RSET × Safety Factor

    The consultant's interface accepted simple parameters (walking speed,
    pre-movement delay). This implementation keeps that interface but
    overrides with occupancy-based values when occupancy_type is provided.

    Key corrections from consultant's code:
      - Fixed 1.0 m/s → occupancy-based walking speeds (0.5-1.1 m/s)
      - Fixed 60s delay → occupancy-based premovement delays (15-300s)
      - Fixed 2.0 safety factor → risk-category-based (1.0-2.5)
      - No tenability criteria → SFPE/BS 7974 multi-criteria check
      - 2D straight-line → path-based travel distance

    Usage::

        from fireai.v17_core import TenabilityEvaluator

        evaluator = TenabilityEvaluator(walking_speed_mps=1.0, pre_movement_delay_s=60.0)
        result = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=45.0,
            estimated_fill_time_s=300.0,
            safety_margin=2.0,
        )
    """

    def __init__(
        self,
        walking_speed_mps: float = 1.0,
        pre_movement_delay_s: float = 60.0,
    ) -> None:
        """Initialize the tenability evaluator.

        Args:
            walking_speed_mps: Default walking speed in m/s. Overridden
                by occupancy-based values when occupancy_type is provided.
                Default: 1.0 m/s (consultant's value — used as fallback).
            pre_movement_delay_s: Default pre-movement delay in seconds.
                Overridden by occupancy-based values when occupancy_type
                is provided. Default: 60s (consultant's value — fallback).

        """
        self.speed = walking_speed_mps
        self.delay = pre_movement_delay_s

    def validate_aset_vs_rset(
        self,
        longest_travel_dist_m: float,
        estimated_fill_time_s: float,
        safety_margin: float = 2.0,
        occupancy_type: Optional[str] = None,
        room_height_m: float = 3.0,
        is_sprinklered: bool = True,
        smoke_layer_height_series: Optional[List[Tuple[float, float]]] = None,
        temperature_series: Optional[List[Tuple[float, float]]] = None,
        co_ppm_series: Optional[List[Tuple[float, float]]] = None,
    ) -> Any:
        """Validate ASET vs RSET with DecisionProvenance audit trail.

        Calculates whether building occupants can escape before conditions
        become untenable. Uses the physics-correct core implementations
        with occupancy-based parameters when available.

        The consultant's interface used fixed parameters. This implementation
        accepts those parameters as defaults but uses occupancy-based values
        when occupancy_type is provided, producing a more accurate result.

        Args:
            longest_travel_dist_m: Maximum travel distance to nearest exit.
                Should be PATH distance (not straight-line).
            estimated_fill_time_s: Time for smoke layer to descend to
                detector level (simplified ASET estimate).
            safety_margin: Safety factor. Default 2.0 (consultant's value).
                Overridden by risk-category-based factor when occupancy_type
                is provided.
            occupancy_type: NFPA 101 occupancy classification. If provided,
                overrides walking speed, pre-movement delay, and safety
                factor with occupancy-based values. One of: assembly,
                business, educational, healthcare, industrial, mercantile,
                residential, storage, high_hazard.
            room_height_m: Room ceiling height in metres.
            is_sprinklered: Whether building has sprinklers (reduces
                safety factor by 0.25 per SFPE).
            smoke_layer_height_series: Time-series smoke layer data from
                semi_cfast_engine. If provided, uses accurate tenability
                check instead of fill time estimate.
            temperature_series: Temperature at occupant level over time.
            co_ppm_series: CO concentration at occupant level over time.

        Returns:
            DecisionProvenance with ASET/RSET comparison and audit trail,
            or dict if provenance is unavailable.

        """
        # Calculate ASET — use time-series if available, else estimate
        if smoke_layer_height_series:
            aset_result = calculate_aset(
                smoke_layer_height_series=smoke_layer_height_series,
                temperature_series=temperature_series,
                co_ppm_series=co_ppm_series,
                room_height_m=room_height_m,
            )
        else:
            aset_result = calculate_aset(
                smoke_fill_time_s=estimated_fill_time_s,
                room_height_m=room_height_m,
            )

        # Calculate RSET — use occupancy-based params if available
        if occupancy_type:
            rset_result = calculate_rset(
                travel_distance_m=longest_travel_dist_m,
                occupancy_type=occupancy_type,
                is_sprinklered=is_sprinklered,
            )
        else:
            # Consultant's fixed parameters
            rset_result = calculate_rset(
                travel_distance_m=longest_travel_dist_m,
                premovement_delay_s=self.delay,
                walking_speed_mps=self.speed,
                safety_factor=safety_margin,
                is_sprinklered=is_sprinklered,
            )

        # Validate ASET vs RSET
        validation = validate_aset_vs_rset(aset_result, rset_result)

        # Build DecisionProvenance if available
        if DecisionProvenance is not None:
            violations = []
            if not validation.is_safe:
                violations.append(
                    Violation(
                        severity="CRITICAL",
                        citation="SFPE/NFPA 101 Performance Based",
                        description=(
                            f"Smoke will asphyxiate escaping occupants. "
                            f"RSET = {rset_result.rset_seconds:.0f}s, "
                            f"RSET × SF = {rset_result.rset_with_safety_s:.0f}s, "
                            f"but ASET = {aset_result.aset_seconds:.0f}s. "
                            f"Deficit: {abs(validation.safety_margin_s):.0f}s. "
                            f"LIMITING FACTOR: {aset_result.limiting_factor}"
                        ),
                    )
                )

            rules = [
                RuleApplied(
                    citation="NFPA 101 §9.3",
                    constant_id="EVAC_VELOCITY",
                    value_used=rset_result.walking_speed_mps,
                    unit="m/s",
                ),
                RuleApplied(
                    citation="SFPE Design",
                    constant_id="ASET_SAFETY_MARGIN",
                    value_used=rset_result.safety_factor,
                    unit="Multiplier",
                ),
            ]

            conf_level = ConfidenceLevel.LOW if not validation.is_safe else ConfidenceLevel.HIGH
            conf = ConfidenceScore(
                input_quality_score=0.8 if not smoke_layer_height_series else 0.95,
                rule_coverage=1.0,
                geometry_certainty=0.85,
                overall=conf_level,
            )

            status = "SAFE" if validation.is_safe else "UNSURVIVABLE_CHOKEPOINT"

            return DecisionProvenance.new(
                decision_type="life_safety_tenability_check",
                value={
                    "rset_s": rset_result.rset_seconds,
                    "aset_s": aset_result.aset_seconds,
                    "rset_with_safety_s": rset_result.rset_with_safety_s,
                    "safety_margin_s": validation.safety_margin_s,
                    "status": status,
                    "is_safe": validation.is_safe,
                    "limiting_factor": aset_result.limiting_factor,
                },
                inputs={
                    "travel_dist_m": longest_travel_dist_m,
                    "smoke_fill_s": estimated_fill_time_s,
                    "room_height_m": room_height_m,
                    "walking_speed_mps": rset_result.walking_speed_mps,
                    "premovement_delay_s": rset_result.premovement_delay_s,
                    "safety_factor": rset_result.safety_factor,
                    "occupancy_type": occupancy_type or "unspecified",
                    "is_sprinklered": is_sprinklered,
                },
                rules_applied=rules,
                algorithm={
                    "name": "DeterministicASET_RSET_Gate",
                    "version": "v17",
                    "corrections": [
                        "Occupancy-based walking speed (not fixed 1.0 m/s)",
                        "Occupancy-based premovement delay (not fixed 60s)",
                        "Risk-category-based safety factor (not fixed 2.0)",
                        "Multi-criteria tenability check (smoke, temp, CO, O2, visibility)",
                    ],
                },
                confidence=conf,
                selected_because=(
                    f"Kinematic check proving life evacuation resolves BEFORE "
                    f"toxification zone boundary lowers below {TENABILITY_THRESHOLDS['min_smoke_layer_height_m']}m. "
                    f"RSET = {rset_result.rset_seconds:.0f}s, "
                    f"ASET = {aset_result.aset_seconds:.0f}s, "
                    f"Safety factor = {rset_result.safety_factor:.1f}x."
                ),
                violations=violations,
            )

        # Fallback: return result dict if provenance unavailable
        return {
            "rset_s": rset_result.rset_seconds,
            "aset_s": aset_result.aset_seconds,
            "rset_with_safety_s": rset_result.rset_with_safety_s,
            "safety_margin_s": validation.safety_margin_s,
            "status": "SAFE" if validation.is_safe else "UNSURVIVABLE_CHOKEPOINT",
            "is_safe": validation.is_safe,
            "limiting_factor": aset_result.limiting_factor,
            "verdict": validation.verdict,
        }

    def full_analysis(
        self,
        room_area_m2: float,
        room_height_m: float,
        travel_distance_m: float,
        occupancy_type: str = "business",
        fire_growth_rate: str = "medium",
        fire_load_MJ: float = 500.0,
        is_sprinklered: bool = True,
        safety_factor_override: Optional[float] = None,
        ventilation_opening_m2: float = 2.0,
        ceiling_type: str = "FLAT",
    ) -> Dict[str, Any]:
        """Perform a complete ASET/RSET analysis using physics-based engine.

        This is the integration function that connects to semi_cfast_engine
        for physics-based smoke modeling. Falls back to simplified calculation
        if semi_cfast_engine is unavailable.

        Args:
            room_area_m2: Floor area of the room/compartment in m².
            room_height_m: Ceiling height in metres.
            travel_distance_m: Maximum travel distance to nearest exit.
            occupancy_type: NFPA 101 occupancy classification.
            fire_growth_rate: t² fire growth rate (slow/medium/fast/ultrafast).
            fire_load_MJ: Total fire load in megajoules.
            is_sprinklered: Whether compartment has sprinklers.
            safety_factor_override: Override the occupancy-based safety factor.
            ventilation_opening_m2: Total ventilation opening area in m².
            ceiling_type: Ceiling type (FLAT, SLOPED, BEAM).

        Returns:
            Dict with ASET/RSET analysis results for release_gates.py Gate 7.

        """
        return perform_aset_rset_analysis(
            room_area_m2=room_area_m2,
            room_height_m=room_height_m,
            travel_distance_m=travel_distance_m,
            occupancy_type=occupancy_type,
            fire_growth_rate=fire_growth_rate,
            fire_load_MJ=fire_load_MJ,
            is_sprinklered=is_sprinklered,
            safety_factor_override=safety_factor_override,
            ventilation_opening_m2=ventilation_opening_m2,
            ceiling_type=ceiling_type,
        )
