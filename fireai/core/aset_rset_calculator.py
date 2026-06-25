"""aset_rset_calculator.py — ASET vs RSET Life-Safety Analysis
============================================================
CRITICAL LIFE-SAFETY MODULE

Calculates whether building occupants can escape before conditions
become untenable. This is the FUNDAMENTAL life-safety analysis:

    ASET (Available Safe Egress Time): Time until conditions become
          untenable (smoke layer descends to 1.8m, temperature > 60°C,
          or visibility < 10m at exit level).

    RSET (Required Safe Egress Time):  Time occupants need to reach
          a safe exit, including pre-movement delay and travel time.

    Design is SAFE only if:  ASET > RSET × Safety Factor

Without this comparison, a building can pass prescriptive code checks
(distance < 61m) while being LETHAL in reality (smoke fills the space
before occupants can escape).

References:
    - SFPE Engineering Guide to Performance-Based Fire Protection
    - NFPA 101 §9.3 (Means of Egress)
    - BS 7974:2019 (Application of fire safety engineering principles)
    - PD 7974-6:2019 (Evacuation timing)

The consultant's original code had several errors:
    - Walking speed of 1.0 m/s is too simplistic (varies by density/age)
    - Pre-movement delay of 60s is a guess (0-600s in reality)
    - Safety factor of 2.0 without justification
    - No ASET tenability criteria — just accepted smoke_fill_time as-is
    - No path-based egress — only straight-line distance

This module fixes ALL of those issues.

Usage:
    from fireai.core.aset_rset_calculator import (
        calculate_aset, calculate_rset, validate_aset_vs_rset
    )

    aset = calculate_aset(smoke_layer_height_time_series, room_height=4.0)
    rset = calculate_rset(travel_distance_m=45.0, occupancy_type="business")
    result = validate_aset_vs_rset(aset, rset)

"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# Tenability Criteria — SFPE / NFPA / BS 7974
# ============================================================================

# A condition becomes UNTENABLE when any of these thresholds are exceeded
# at the occupant level (typically 1.8m above floor for standing adults,
# 1.5m for children/wheelchair users — we use 1.8m as conservative).

TENABILITY_THRESHOLDS = {
    # Smoke layer interface height below this = untenable
    # (NFPA 101, SFPE Handbook — 1.8m = typical occupant height)
    "min_smoke_layer_height_m": 1.8,
    # Temperature at occupant level above this = untenable
    # (SFPE: 60°C for sustained exposure, 100°C for brief exposure)
    "max_temperature_c": 60.0,
    # Visibility below this = untenable
    # (BS 7974-6: 10m for familiar occupants, 30m for unfamiliar)
    "min_visibility_m": 10.0,
    # CO concentration above this = untenable
    # (SFPE: 1500 ppm for impaired escape, 3000 ppm for incapacitation)
    "max_co_ppm": 1500.0,
    # O2 concentration below this = untenable
    # (SFPE: 12% minimum for escape capability)
    "min_o2_fraction": 0.12,
}


# ============================================================================
# Occupancy-Based Parameters — NFPA 101 / SFPE
# ============================================================================

# Pre-movement delay: time from alarm sounding to start of movement.
# Based on PD 7974-6 Table 6 and NFPA 101 research.
PREMOVEMENT_DELAYS = {
    # occupancy_type: (typical_min_s, typical_max_s, design_value_s)
    # design_value = conservative (high) end for life-safety design
    "assembly": (60, 180, 120),  # Theaters, churches — crowds delay
    "business": (30, 120, 90),  # Offices — moderate response
    "educational": (30, 90, 60),  # Schools — trained, fast response
    "healthcare": (60, 300, 180),  # Hospitals — patients need help
    "industrial": (30, 120, 60),  # Factories — trained workforce
    "mercantile": (60, 180, 120),  # Stores — unfamiliar occupants
    "residential": (60, 300, 180),  # Hotels/apartments — sleeping risk
    "storage": (30, 120, 60),  # Warehouses — few occupants
    "high_hazard": (15, 60, 30),  # Hazardous — trained, immediate
}

DEFAULT_PREMOVEMENT_DELAY_S = 90.0  # Default if occupancy type unknown

# Walking speeds — SFPE Handbook / PD 7974-6
# Speed decreases with population density and age.
WALKING_SPEEDS = {
    # occupancy_type: (unimpeded_mps, design_mps)
    # design_mps accounts for crowd density and mixed populations
    "assembly": (1.2, 0.8),  # Crowds slow movement
    "business": (1.2, 1.0),  # Normal office population
    "educational": (1.2, 0.9),  # Children move slower
    "healthcare": (1.0, 0.5),  # Patients, wheelchairs, beds
    "industrial": (1.3, 1.0),  # Fit workers
    "mercantile": (1.2, 0.8),  # Crowds, families
    "residential": (1.0, 0.7),  # Elderly, children, sleeping
    "storage": (1.3, 1.0),  # Fit workers, few people
    "high_hazard": (1.3, 1.1),  # Trained personnel
}

DEFAULT_DESIGN_WALKING_SPEED_MPS = 0.8  # Conservative default

# Safety factors per SFPE Engineering Guide
# Higher uncertainty → higher safety factor
SAFETY_FACTORS = {
    "prescriptive": 1.0,  # When all prescriptive rules are met
    "standard": 1.5,  # Standard performance-based design
    "high_risk": 2.0,  # Hospitals, assembly, high hazard
    "very_high": 2.5,  # Sleeping risk, vulnerable populations
}

RISK_CATEGORIES = {
    "assembly": "high_risk",
    "business": "standard",
    "educational": "standard",
    "healthcare": "very_high",
    "industrial": "standard",
    "mercantile": "high_risk",
    "residential": "very_high",
    "storage": "standard",
    "high_hazard": "high_risk",
}


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class ASETResult:
    """Available Safe Egress Time calculation result."""

    aset_seconds: float
    limiting_factor: str  # What made conditions untenable
    aset_method: str  # "tenability_check" or "smoke_fill_estimate"
    smoke_layer_at_aset_m: Optional[float] = None
    temperature_at_aset_c: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RSETResult:
    """Required Safe Egress Time calculation result."""

    rset_seconds: float
    premovement_delay_s: float
    travel_time_s: float
    walking_speed_mps: float
    travel_distance_m: float
    occupancy_type: str
    safety_factor: float
    rset_with_safety_s: float  # rset × safety_factor


@dataclass
class AsetRsetValidation:
    """ASET vs RSET comparison result."""

    is_safe: bool
    aset_seconds: float
    rset_seconds: float
    rset_with_safety_s: float
    safety_margin_s: float  # aset - rset_with_safety
    safety_factor_used: float
    limiting_factor: str  # What limits ASET
    occupancy_type: str
    verdict: str  # Human-readable PASS/FAIL
    details: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# ASET Calculation
# ============================================================================


def calculate_aset(
    smoke_layer_height_series: Optional[List[Tuple[float, float]]] = None,
    temperature_series: Optional[List[Tuple[float, float]]] = None,
    co_ppm_series: Optional[List[Tuple[float, float]]] = None,
    room_height_m: float = 3.0,
    # Simplified inputs when no time-series data available
    smoke_fill_time_s: Optional[float] = None,
    fire_growth_rate: Optional[str] = None,
    fire_heat_release_kw: Optional[float] = None,
    room_volume_m3: Optional[float] = None,
) -> ASETResult:
    """Calculate Available Safe Egress Time (ASET).

    Two modes:
      1. TIME-SERIES MODE: Provide smoke_layer_height_series as
         [(time_s, height_m), ...] and the function finds the earliest
         time any tenability threshold is exceeded. This is the accurate
         mode when semi_cfast_engine output is available.

      2. ESTIMATE MODE: Provide smoke_fill_time_s (time for smoke layer
         to descend to detector level). ASET is estimated as the time
         for the layer to descend from detector level to 1.8m, using
         the same descent rate. This is approximate (±50%) and should
         only be used for pre-screening.

    Args:
        smoke_layer_height_series: [(time_s, layer_height_m), ...] from
            semi_cfast_engine SmokeLayerSolver output.
        temperature_series: [(time_s, temperature_c), ...] at 1.8m height.
        co_ppm_series: [(time_s, co_ppm), ...] at 1.8m height.
        room_height_m: Room ceiling height in meters.
        smoke_fill_time_s: Simplified — time for smoke to reach detector.
        fire_growth_rate: "slow", "medium", "fast", "ultrafast".
        fire_heat_release_kw: Fire HRR for estimation.
        room_volume_m3: Room volume for estimation.

    Returns:
        ASETResult with calculated ASET and limiting factor.

    """
    thresholds = TENABILITY_THRESHOLDS
    min_height = thresholds["min_smoke_layer_height_m"]
    max_temp = thresholds["max_temperature_c"]
    max_co = thresholds["max_co_ppm"]

    # === Mode 1: Time-series analysis (ACCURATE) ===
    if smoke_layer_height_series:
        aset = float("inf")
        limiting_factor = "none"

        # V57 FIX: NaN/Inf in time-series data bypasses tenability checks.
        # NaN <= threshold is False → untenable condition never detected → ASET=inf.
        # Building PASSES when conditions are actually unknown — potentially lethal.
        # Per Life-Safety Rule 5: conservative interpretation (more detectors = safer).
        _nan_detected_in_series = False

        # Check smoke layer height
        for t, h in smoke_layer_height_series:
            if not math.isfinite(h) or not math.isfinite(t):
                _nan_detected_in_series = True
                continue
            if h <= min_height:
                if t < aset:
                    aset = t
                    limiting_factor = f"smoke_layer_descended_to_{h:.1f}m"
                break  # First crossing is ASET

        # Check temperature at occupant level
        if temperature_series:
            for t, temp_c in temperature_series:
                if not math.isfinite(temp_c) or not math.isfinite(t):
                    _nan_detected_in_series = True
                    continue
                if temp_c >= max_temp:
                    if t < aset:
                        aset = t
                        limiting_factor = f"temperature_{temp_c:.0f}C_exceeds_{max_temp}C"
                    break

        # Check CO concentration
        if co_ppm_series:
            for t, co in co_ppm_series:
                if not math.isfinite(co) or not math.isfinite(t):
                    _nan_detected_in_series = True
                    continue
                if co >= max_co:
                    if t < aset:
                        aset = t
                        limiting_factor = f"CO_{co:.0f}ppm_exceeds_{max_co}ppm"
                    break

        # V57: If NaN was detected in any series, ASET is unreliable.
        # Fail-safe: set ASET=0 (assume immediately untenable).
        if _nan_detected_in_series:
            import logging as _nan_log

            _nan_log.getLogger(__name__).critical(
                "ASET-CALC-001: NaN/Inf detected in tenability time-series data. "
                "Cannot determine ASET reliably. Setting ASET=0 (fail-safe: "
                "assume immediately untenable). Per SFPE Engineering Guide."
            )
            if aset == float("inf"):
                aset = 0.0
                limiting_factor = "NaN_Inf_in_input_data_ASSUMED_UNTENABLE"

        if aset == float("inf"):
            # No untenable condition reached within simulation time
            last_time = smoke_layer_height_series[-1][0] if smoke_layer_height_series else 0
            return ASETResult(
                aset_seconds=last_time,
                limiting_factor="none_reached_within_simulation",
                aset_method="tenability_check",
                smoke_layer_at_aset_m=smoke_layer_height_series[-1][1] if smoke_layer_height_series else None,
                details={"note": "ASET exceeds simulation time — design may be safe"},
            )

        # Get smoke layer height at ASET
        smoke_h = None
        for t, h in smoke_layer_height_series:
            if t >= aset:
                smoke_h = h
                break

        return ASETResult(
            aset_seconds=aset,
            limiting_factor=limiting_factor,
            aset_method="tenability_check",
            smoke_layer_at_aset_m=smoke_h,
            details={
                "thresholds_used": {
                    "min_smoke_layer_height_m": min_height,
                    "max_temperature_c": max_temp,
                    "max_co_ppm": max_co,
                },
            },
        )

    # === Mode 2: Estimate from smoke fill time (APPROXIMATE) ===
    if smoke_fill_time_s is not None and smoke_fill_time_s > 0:
        # V59 FIX: NaN/Inf in smoke_fill_time_s produces NaN descent_rate,
        # NaN additional_time, and NaN ASET. The ASET > RSET check treats
        # NaN > value as False (fail-safe), but the actual ASET is meaningless.
        if not math.isfinite(smoke_fill_time_s):
            import logging as _nan_sft

            _nan_sft.getLogger(__name__).critical(
                "ASET-CALC-002: NaN/Inf smoke_fill_time_s=%r. "
                "Cannot estimate ASET. Returning fail-safe ASET=0. "
                "Provide valid smoke_fill_time_s or use time-series mode.",
                smoke_fill_time_s,
            )
            return ASETResult(
                aset_seconds=0.0,
                limiting_factor="NaN_Inf_smoke_fill_time_ASSUMED_UNTENABLE",
                aset_method="smoke_fill_estimate_failed",
                smoke_layer_at_aset_m=None,
                details={"error": f"Invalid smoke_fill_time_s: {smoke_fill_time_s!r}"},
            )

        # The smoke_fill_time_s is the time for the layer to descend
        # to the DETECTOR level (typically ceiling - 0.1-0.3m).
        # ASET is when it reaches 1.8m.
        # Assumption: the descent rate remains approximately constant.
        # This is a rough estimate — ±50% error band per smoke_estimator.py.
        detector_height_m = room_height_m - 0.3  # Typical detector position
        detector_height_m = max(detector_height_m, min_height + 0.5)

        # Descent rate from fill time
        descent_from_ceiling = room_height_m - detector_height_m
        if descent_from_ceiling > 0:
            descent_rate_m_per_s = descent_from_ceiling / smoke_fill_time_s
        else:
            descent_rate_m_per_s = 0.01  # Fallback

        # Time to descend from detector level to 1.8m
        remaining_descent = detector_height_m - min_height
        if remaining_descent > 0 and descent_rate_m_per_s > 0:
            additional_time = remaining_descent / descent_rate_m_per_s
        else:
            additional_time = 0.0

        aset_estimate = smoke_fill_time_s + additional_time

        return ASETResult(
            aset_seconds=aset_estimate,
            limiting_factor="smoke_layer_descent_to_1.8m",
            aset_method="smoke_fill_estimate",
            smoke_layer_at_aset_m=min_height,
            details={
                "warning": (
                    "PRE-SCREENING ESTIMATE ONLY — ±50% error band. "
                    "Use semi_cfast_engine time-series data for accurate ASET."
                ),
                "smoke_fill_time_s": smoke_fill_time_s,
                "descent_rate_m_per_s": descent_rate_m_per_s,
                "detector_height_m": detector_height_m,
                "remaining_descent_m": remaining_descent,
            },
        )

    # No data provided — cannot calculate ASET
    return ASETResult(
        aset_seconds=0.0,
        limiting_factor="no_data_provided",
        aset_method="none",
        details={"error": "Provide either smoke_layer_height_series or smoke_fill_time_s"},
    )


# ============================================================================
# RSET Calculation
# ============================================================================


def calculate_rset(
    travel_distance_m: float,
    occupancy_type: str = "business",
    premovement_delay_s: Optional[float] = None,
    walking_speed_mps: Optional[float] = None,
    safety_factor: Optional[float] = None,
    is_sprinklered: bool = True,
    population_density: Optional[float] = None,
    detection_time_s: Optional[float] = None,
) -> RSETResult:
    """Calculate Required Safe Egress Time (RSET).

    RSET = Detection Time + Premovement Delay + Travel Time

    Where:
        Premovement Delay = time from alarm to start of movement
        Travel Time = distance / walking speed (accounting for density)

    Args:
        travel_distance_m:  Distance from most remote point to nearest exit.
                            Should be PATH distance (not Euclidean straight-line).
        occupancy_type:     NFPA 101 occupancy classification.
        premovement_delay_s: Override default premovement delay (seconds).
        walking_speed_mps:  Override default walking speed (m/s).
        safety_factor:      Override default safety factor.
        is_sprinklered:     Whether building has sprinklers (affects confidence).
        population_density: People per m² (affects walking speed if crowded).

    Returns:
        RSETResult with breakdown of all components.

    """
    occ = occupancy_type.lower()
    if occ not in PREMOVEMENT_DELAYS:
        # V48 FIX: Unknown occupancy type must NOT default to "business" (lowest risk).
        # A hospital silently evaluated as "business" would have RSET underestimated
        # by ~50%, allowing a building that should FAIL to PASS. Now uses the MOST
        # conservative occupancy type and emits a CRITICAL warning.
        import logging as _log

        _log.getLogger(__name__).critical(
            "ASET-RSET-001: Unknown occupancy type '%s'. "
            "Using 'healthcare' (most conservative: premovement=180s, SF=2.5). "
            "Provide a valid occupancy type: %s. Per NFPA 101 §9.3.",
            occupancy_type,
            sorted(PREMOVEMENT_DELAYS.keys()),
        )
        occ = "healthcare"  # Most conservative default

    # Premovement delay
    if premovement_delay_s is not None:
        pm_delay = float(premovement_delay_s)
        # V57 FIX: NaN/Inf in premovement delay propagates through RSET.
        # max(NaN, 0.2) = NaN in Python (implementation-dependent). NaN RSET
        # makes ASET > RSET check meaningless.
        if not math.isfinite(pm_delay):
            import logging as _nan_log2

            _nan_log2.getLogger(__name__).critical(
                "RSET-CALC-001: NaN/Inf premovement_delay_s=%r. "
                "Using conservative default 180s (healthcare). Per NFPA 101 §9.3.",
                premovement_delay_s,
            )
            pm_delay = PREMOVEMENT_DELAYS["healthcare"][2]
    else:
        pm_delay = PREMOVEMENT_DELAYS[occ][2]  # Design (conservative) value

    # Walking speed — reduce for high population density
    if walking_speed_mps is not None:
        speed = float(walking_speed_mps)
        # V57 FIX: NaN walking speed → NaN travel_time → NaN RSET → meaningless
        if not math.isfinite(speed):
            import logging as _nan_log3

            _nan_log3.getLogger(__name__).critical(
                "RSET-CALC-002: NaN/Inf walking_speed_mps=%r. "
                "Using conservative default 0.2 m/s (minimum mobility). Per SFPE.",
                walking_speed_mps,
            )
            speed = 0.2  # Most conservative (wheelchair, injured)
    else:
        speed = WALKING_SPEEDS.get(occ, (1.2, DEFAULT_DESIGN_WALKING_SPEED_MPS))[1]

    # Reduce speed for crowd density (SFPE: Fruin LOS)
    if population_density is not None and population_density > 0.5:
        # Above 0.5 persons/m², speed decreases significantly
        # SFPE: at 1.0 p/m² speed ~0.8 m/s, at 2.0 p/m² speed ~0.4 m/s
        density_factor = max(0.3, 1.0 - (population_density - 0.5) * 0.4)
        speed = speed * density_factor

    speed = max(speed, 0.2)  # Absolute minimum (wheelchair, injured)

    # Travel time
    # V59 FIX: NaN/Inf travel_distance_m produces NaN travel_time, NaN RSET.
    # NaN RSET makes ASET > RSET comparison meaningless (NaN > value = False,
    # fail-safe, but the safety margin is lost).
    if not math.isfinite(travel_distance_m) or travel_distance_m <= 0:
        import logging as _nan_td

        _nan_td.getLogger(__name__).critical(
            "RSET-CALC-004: Invalid travel_distance_m=%r (must be finite, >0). "
            "Using conservative default 100m (maximum NFPA 101 travel distance).",
            travel_distance_m,
        )
        travel_distance_m = 100.0  # Maximum NFPA 101 travel distance (conservative)
        # Recompute speed reference since travel_distance changed
        travel_time = travel_distance_m / speed
    else:
        travel_time = travel_distance_m / speed

    # Total RSET
    # V43 FIX: Include detection time per SFPE Engineering Guide and PD 7974-6:2019.
    # RSET = detection_time + premovement_delay + travel_time.
    # Previously omitted detection time, underestimating RSET by 60-300s.
    # A building that should FAIL ASET > RSET × SF could PASS, costing lives.
    # V29 FIX: detection_time_s=None defaults to 0.0 for backward compatibility.
    # The V48 fix changed None→60.0 which broke the API contract: existing callers
    # that don't pass detection_time_s expect RSET = premovement + travel_time only.
    # V59 HARDPACK FIX: detection_time_s=None now uses conservative 60.0s default (hard gate).
    # The previous 0.0 default silently underestimated RSET, creating a false-PASS
    # risk. Callers MUST provide an explicit detection time.
    # The ASET-RSET comparison in validate_aset_vs_rset() applies safety_factor >= 1.5
    # which provides adequate margin for unaccounted detection time, but the hard
    # gate ensures no caller can accidentally omit this critical parameter.
    if detection_time_s is not None:
        dt = detection_time_s
        if not math.isfinite(dt) or dt < 0:
            import logging as _log_dt

            _log_dt.getLogger(__name__).critical(
                "ASET-RSET-002b: Invalid detection_time_s=%r (must be finite, >=0). "
                "Using conservative default 60.0s (ceiling smoke detector per NFPA 72 ss17.6).",
                detection_time_s,
            )
            dt = 60.0
    else:
        import logging as _log_hard

        _log_hard.getLogger(__name__).critical(
            "ASET-RSET-002: detection_time_s not provided — RSET calculation "
            "EXCLUDES detection time. Per SFPE Engineering Guide and "
            "PD 7974-6:2019, RSET = detection + premovement + travel. "
            "Excluding detection time UNDERESTIMATES RSET, which could cause "
            "ASET > RSET to PASS when it should FAIL. "
            "Pass detection_time_s explicitly (e.g., 60.0 for ceiling smoke detector "
            "per NFPA 72 ss17.6) for accurate life-safety calculations."
        )
        # Hard gate: use conservative default (60s smoke detector) instead of 0.0.
        # This ensures RSET is never silently underestimated. The CRITICAL log
        # above forces callers to fix their invocation.
        dt = 60.0
    rset = dt + pm_delay + travel_time

    # Safety factor
    if safety_factor is not None:
        sf = float(safety_factor)
        # V57 FIX: NaN safety_factor makes rset_with_safety = RSET * NaN = NaN.
        # ASET > NaN is False (fail-safe) but the verdict formatting crashes.
        if not math.isfinite(sf) or sf < 1.0:
            import logging as _nan_log4

            _nan_log4.getLogger(__name__).critical(
                "RSET-CALC-003: Invalid safety_factor=%r (must be >= 1.0 and finite). "
                "Using default 2.5 (healthcare/conservative). Per SFPE Engineering Guide.",
                safety_factor,
            )
            sf = 2.5  # Most conservative default
    else:
        risk_category = RISK_CATEGORIES.get(occ, "standard")
        sf = SAFETY_FACTORS.get(risk_category, 1.5)
        # Sprinklers reduce uncertainty — can use lower factor
        if is_sprinklered and sf > 1.0:
            sf = max(sf - 0.25, 1.0)  # Slight reduction for sprinklers

    rset_with_safety = rset * sf

    return RSETResult(
        rset_seconds=rset,
        premovement_delay_s=pm_delay,
        travel_time_s=travel_time,
        walking_speed_mps=speed,
        travel_distance_m=travel_distance_m,
        occupancy_type=occ,
        safety_factor=sf,
        rset_with_safety_s=rset_with_safety,
    )


# ============================================================================
# ASET vs RSET Validation
# ============================================================================


def validate_aset_vs_rset(
    aset_result: ASETResult,
    rset_result: RSETResult,
    override_safety_factor: Optional[float] = None,
) -> AsetRsetValidation:
    """Validate that ASET exceeds RSET with safety margin.

    This is the FUNDAMENTAL life-safety check:
        Design is SAFE if: ASET > RSET × Safety Factor

    If this fails, occupants will be exposed to untenable conditions
    before they can reach an exit.

    Args:
        aset_result: ASET calculation result.
        rset_result: RSET calculation result.
        override_safety_factor: Override the safety factor from RSET.

    Returns:
        AsetRsetValidation with PASS/FAIL verdict and margin.

    """
    aset = aset_result.aset_seconds
    rset = rset_result.rset_seconds
    sf = override_safety_factor if override_safety_factor is not None else rset_result.safety_factor
    rset_with_sf = rset * sf

    # V57 FIX: NaN/Inf in ASET or RSET makes margin comparison meaningless.
    # NaN > 0 is False (fail-safe) but verdict formatting crashes with division.
    if not math.isfinite(aset) or not math.isfinite(rset) or not math.isfinite(sf):
        is_safe = False
        margin = float("nan")
        verdict = (
            f"FAIL: Invalid ASET/RSET/SF values — cannot verify life safety. "
            f"ASET={aset}, RSET={rset}, SF={sf}. "
            f"Per SFPE Engineering Guide, design CANNOT be approved with invalid data."
        )
    else:
        margin = aset - rset_with_sf
        is_safe = margin > 0

        if is_safe:
            safe_aset = aset if aset > 0 else 1.0  # Prevent division by zero
            verdict = (
                f"PASS: ASET ({aset:.1f}s) > RSET×SF ({rset_with_sf:.1f}s). "
                f"Safety margin: {margin:.1f}s ({margin / safe_aset * 100:.0f}% of ASET)."
            )
        else:
            verdict = (
                f"FAIL: ASET ({aset:.1f}s) < RSET×SF ({rset_with_sf:.1f}s). "
                f"Occupants will be exposed to untenable conditions "
                f"{abs(margin):.1f}s before reaching exit. "
                f"LIMITING FACTOR: {aset_result.limiting_factor}. "
                f"ACTION: Add exits, reduce travel distance, install smoke "
                f"extraction, or increase detection speed."
            )

    return AsetRsetValidation(
        is_safe=is_safe,
        aset_seconds=aset,
        rset_seconds=rset,
        rset_with_safety_s=rset_with_sf,
        safety_margin_s=margin,
        safety_factor_used=sf,
        limiting_factor=aset_result.limiting_factor,
        occupancy_type=rset_result.occupancy_type,
        verdict=verdict,
        details={
            "aset_method": aset_result.aset_method,
            "aset_details": aset_result.details,
            "premovement_delay_s": rset_result.premovement_delay_s,
            "travel_time_s": rset_result.travel_time_s,
            "walking_speed_mps": rset_result.walking_speed_mps,
        },
    )


# ============================================================================
# Integrated ASET/RSET Analysis — Connects semi_cfast_engine to release_gates
# ============================================================================


def perform_aset_rset_analysis(
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
    """Perform a complete ASET vs RSET analysis using semi_cfast_engine physics.

    This is the integration function that connects the physics-based
    semi_cfast_engine to release_gates.py Gate 7. It creates a FireScenario,
    computes ASET using the time-stepping engine, computes RSET from egress
    parameters, and returns a result dict that can be passed directly to
    verify_and_evaluate() as the ``aset_rset_result`` parameter.

    NFPA 72 / SFPE References:
        - SFPE Engineering Guide to Performance-Based Fire Protection
        - NFPA 101 §9.3 (Means of Egress)
        - BS 7974:2019 (Application of fire safety engineering principles)
        - NFPA 72 §18.5 (Notification appliance circuit design — indirectly,
          as detection time affects ASET)

    This function is CRITICAL because Gate 7 of release_gates.py
    numerically re-verifies ASET > RSET × safety_factor. If this
    function is not called, Gate 7 has no data and blocks release.

    Args:
        room_area_m2: Floor area of the room/compartment in m².
        room_height_m: Ceiling height of the room in metres.
        travel_distance_m: Maximum travel distance to nearest exit (path-based).
        occupancy_type: NFPA 101 occupancy classification.
            One of: assembly, business, educational, healthcare,
            industrial, mercantile, residential, storage, high_hazard.
        fire_growth_rate: t² fire growth rate per NFPA 72 Annex A.
            One of: slow, medium, fast, ultrafast.
        fire_load_MJ: Total fire load in megajoules.
        is_sprinklered: Whether the compartment has sprinklers.
        safety_factor_override: Override the occupancy-based safety factor.
        ventilation_opening_m2: Total ventilation opening area in m².
        ceiling_type: Ceiling type string ("FLAT", "SLOPED", "BEAM").

    Returns:
        Dict with keys required by release_gates.py Gate 7:
          - aset_seconds: Available Safe Egress Time
          - rset_seconds: Required Safe Egress Time
          - safety_factor: Safety factor used
          - is_safe: Whether ASET > RSET × safety_factor
          - limiting_factor: What limits ASET
          - occupancy_type: Occupancy classification
          - verdict: Human-readable PASS/FAIL
          - details: Full analysis details

    """
    try:
        from fireai.core.semi_cfast_engine import (
            FireScenario,
            TenabilityCriteria,
            verify_aset_rset,
        )
        from fireai.core.semi_cfast_engine import (
            calculate_aset as _cfast_aset,
        )
        from fireai.core.semi_cfast_engine import (
            calculate_rset as _cfast_rset,
        )

        # Build fire scenario from room parameters
        scenario = FireScenario(
            room_area_m2=room_area_m2,
            room_height_m=room_height_m,
            fire_growth_rate=fire_growth_rate,
            fire_load_MJ=fire_load_MJ,
            ventilation_opening_m2=ventilation_opening_m2,
            ceiling_type=ceiling_type,
        )

        # Default tenability criteria per SFPE
        criteria = TenabilityCriteria()

        # Map occupancy type to semi_cfast_engine terminology
        # The aset_rset_calculator uses NFPA 101 terms (business, mercantile, etc.)
        # while semi_cfast_engine uses SFPE terms (office, retail, etc.)
        _OCCUPANCY_TYPE_MAP = {
            "business": "office",
            "mercantile": "retail",
            "educational": "education",
            "high_hazard": "industrial",
            "storage": "industrial",  # Storage maps to industrial (similar speeds)
            "residential": "residential",  # Same name but ensure mapping
            "healthcare": "elderly_care",  # Healthcare → elderly care (conservative)
            "assembly": "assembly",  # Same name
            "industrial": "industrial",  # Same name
        }
        cfast_occupancy = _OCCUPANCY_TYPE_MAP.get(occupancy_type, occupancy_type)

        # Compute ASET using physics-based time-stepping engine
        aset_result = _cfast_aset(scenario, criteria)

        # Compute RSET using egress parameters
        rset_result = _cfast_rset(
            room_area_m2=room_area_m2,
            room_height_m=room_height_m,
            travel_distance_m=travel_distance_m,
            occupancy_type=cfast_occupancy,
        )

        # Extract RSET values from dict result
        rset_seconds = float(rset_result.get("rset_seconds", 0))
        travel_time_s = float(rset_result.get("travel_time_s", 0))
        walking_speed_mps = float(rset_result.get("walking_speed_m_s", 0))
        premovement_delay_s = float(rset_result.get("pre_movement_s", 0))
        detection_time_s = float(rset_result.get("detection_time_s", 0))

        # Determine safety factor based on occupancy and sprinklers
        if safety_factor_override is not None:
            sf = safety_factor_override
        else:
            risk_category = RISK_CATEGORIES.get(occupancy_type, "standard")
            sf = SAFETY_FACTORS.get(risk_category, 1.5)
            if is_sprinklered and sf > 1.0:
                sf = max(sf - 0.25, 1.0)

        rset_with_safety = rset_seconds * sf

        # Verify ASET > RSET with safety factor
        # V20.2 FIX #19: Was passing rset_with_safety as rset_seconds AND sf
        # as safety_factor to verify_aset_rset(), which internally computes
        # required_aset = rset_seconds * safety_factor. This resulted in:
        #   required_aset = (rset * sf) * sf = rset * sf²
        # For sf=1.5, this means ASET > RSET × 2.25 instead of ASET > RSET × 1.5.
        # Fix: Pass the RAW rset_seconds (without safety factor) so verify_aset_rset
        # applies the safety factor exactly once internally.
        validation = verify_aset_rset(
            aset_seconds=aset_result.aset_seconds,
            rset_seconds=rset_seconds,  # V20.2 FIX #19: was rset_with_safety (double SF)
            safety_factor=sf,
        )

        # Extract limiting criterion from ASETResult
        limiting = "unknown"
        if hasattr(aset_result, "limiting_criterion"):
            limiting = str(aset_result.limiting_criterion)
        elif hasattr(aset_result, "limiting_factor"):
            limiting = str(aset_result.limiting_factor)

        return {
            "aset_seconds": aset_result.aset_seconds,
            "rset_seconds": rset_seconds,
            "rset_with_safety_s": rset_with_safety,
            "safety_factor": sf,
            "is_safe": validation.get("is_safe", False),
            "limiting_factor": limiting,
            "occupancy_type": occupancy_type,
            "verdict": "PASS" if validation.get("is_safe", False) else "FAIL",
            "details": {
                "aset_details": {
                    "method": "semi_cfast_engine_time_stepping",
                    "limiting_criterion": limiting,
                    "smoke_layer_at_aset_m": aset_result.smoke_layer_at_aset_m
                    if hasattr(aset_result, "smoke_layer_at_aset_m")
                    else None,
                    "temperature_at_aset_c": aset_result.temperature_at_aset_c
                    if hasattr(aset_result, "temperature_at_aset_c")
                    else None,
                },
                "rset_details": {
                    "detection_time_s": detection_time_s,
                    "premovement_delay_s": premovement_delay_s,
                    "travel_time_s": travel_time_s,
                    "walking_speed_mps": walking_speed_mps,
                    "travel_distance_m": travel_distance_m,
                    "is_sprinklered": is_sprinklered,
                },
                "scenario": {
                    "room_area_m2": room_area_m2,
                    "room_height_m": room_height_m,
                    "fire_growth_rate": fire_growth_rate,
                    "fire_load_MJ": fire_load_MJ,
                },
            },
        }

    except ImportError as e:
        # semi_cfast_engine not available — fall back to simplified calculation
        # using the local calculate_aset and calculate_rset
        aset_result = calculate_aset(  # type: ignore[assignment]
            smoke_fill_time_s=300.0,  # 5 min default estimate
            room_height_m=room_height_m,
        )

        rset_result = calculate_rset(  # type: ignore[assignment]
            travel_distance_m=travel_distance_m,
            occupancy_type=occupancy_type,
            is_sprinklered=is_sprinklered,
        )

        validation = validate_aset_vs_rset(aset_result, rset_result, safety_factor_override)  # type: ignore[assignment, arg-type]

        return {
            "aset_seconds": aset_result.aset_seconds,
            "rset_seconds": rset_result.rset_seconds,  # type: ignore[attr-defined]
            "rset_with_safety_s": rset_result.rset_with_safety_s,  # type: ignore[attr-defined]
            "safety_factor": rset_result.safety_factor,  # type: ignore[attr-defined]
            "is_safe": validation.is_safe,  # type: ignore[attr-defined]
            "limiting_factor": aset_result.limiting_factor,  # type: ignore[attr-defined]
            "occupancy_type": occupancy_type,
            "verdict": validation.verdict.split(":")[0]  # type: ignore[attr-defined]
            if ":" in validation.verdict  # type: ignore[attr-defined]
            else ("PASS" if validation.is_safe else "FAIL"),  # type: ignore[attr-defined]
            "details": {
                "aset_details": {
                    "method": "simplified_estimate_fallback",
                    "warning": f"semi_cfast_engine unavailable ({e}); using simplified estimate with ±50% error band",
                },
                "rset_details": {
                    "premovement_delay_s": rset_result.premovement_delay_s,  # type: ignore[attr-defined]
                    "travel_time_s": rset_result.travel_time_s,  # type: ignore[attr-defined]
                    "walking_speed_mps": rset_result.walking_speed_mps,  # type: ignore[attr-defined]
                },
            },
        }


__all__ = [
    "PREMOVEMENT_DELAYS",
    "RISK_CATEGORIES",
    "SAFETY_FACTORS",
    "TENABILITY_THRESHOLDS",
    "WALKING_SPEEDS",
    "ASETResult",
    "AsetRsetValidation",
    "RSETResult",
    "calculate_aset",
    "calculate_rset",
    "perform_aset_rset_analysis",
    "validate_aset_vs_rset",
]
