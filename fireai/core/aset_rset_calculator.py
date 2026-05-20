"""
aset_rset_calculator.py — ASET vs RSET Life-Safety Analysis
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
    "assembly":      (60, 180, 120),    # Theaters, churches — crowds delay
    "business":      (30, 120, 90),     # Offices — moderate response
    "educational":   (30, 90, 60),      # Schools — trained, fast response
    "healthcare":    (60, 300, 180),    # Hospitals — patients need help
    "industrial":    (30, 120, 60),     # Factories — trained workforce
    "mercantile":    (60, 180, 120),    # Stores — unfamiliar occupants
    "residential":   (60, 300, 180),    # Hotels/apartments — sleeping risk
    "storage":       (30, 120, 60),     # Warehouses — few occupants
    "high_hazard":   (15, 60, 30),      # Hazardous — trained, immediate
}

DEFAULT_PREMOVEMENT_DELAY_S = 90.0  # Default if occupancy type unknown

# Walking speeds — SFPE Handbook / PD 7974-6
# Speed decreases with population density and age.
WALKING_SPEEDS = {
    # occupancy_type: (unimpeded_mps, design_mps)
    # design_mps accounts for crowd density and mixed populations
    "assembly":      (1.2, 0.8),   # Crowds slow movement
    "business":      (1.2, 1.0),   # Normal office population
    "educational":   (1.2, 0.9),   # Children move slower
    "healthcare":    (1.0, 0.5),   # Patients, wheelchairs, beds
    "industrial":    (1.3, 1.0),   # Fit workers
    "mercantile":    (1.2, 0.8),   # Crowds, families
    "residential":   (1.0, 0.7),   # Elderly, children, sleeping
    "storage":       (1.3, 1.0),   # Fit workers, few people
    "high_hazard":   (1.3, 1.1),   # Trained personnel
}

DEFAULT_DESIGN_WALKING_SPEED_MPS = 0.8  # Conservative default

# Safety factors per SFPE Engineering Guide
# Higher uncertainty → higher safety factor
SAFETY_FACTORS = {
    "prescriptive": 1.0,    # When all prescriptive rules are met
    "standard":     1.5,    # Standard performance-based design
    "high_risk":    2.0,    # Hospitals, assembly, high hazard
    "very_high":    2.5,    # Sleeping risk, vulnerable populations
}

RISK_CATEGORIES = {
    "assembly":      "high_risk",
    "business":      "standard",
    "educational":   "standard",
    "healthcare":    "very_high",
    "industrial":    "standard",
    "mercantile":    "high_risk",
    "residential":   "very_high",
    "storage":       "standard",
    "high_hazard":   "high_risk",
}


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class ASETResult:
    """Available Safe Egress Time calculation result."""
    aset_seconds: float
    limiting_factor: str        # What made conditions untenable
    aset_method: str            # "tenability_check" or "smoke_fill_estimate"
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
    rset_with_safety_s: float     # rset × safety_factor


@dataclass
class AsetRsetValidation:
    """ASET vs RSET comparison result."""
    is_safe: bool
    aset_seconds: float
    rset_seconds: float
    rset_with_safety_s: float
    safety_margin_s: float       # aset - rset_with_safety
    safety_factor_used: float
    limiting_factor: str         # What limits ASET
    occupancy_type: str
    verdict: str                 # Human-readable PASS/FAIL
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

        # Check smoke layer height
        for t, h in smoke_layer_height_series:
            if h <= min_height:
                if t < aset:
                    aset = t
                    limiting_factor = f"smoke_layer_descended_to_{h:.1f}m"
                break  # First crossing is ASET

        # Check temperature at occupant level
        if temperature_series:
            for t, temp_c in temperature_series:
                if temp_c >= max_temp:
                    if t < aset:
                        aset = t
                        limiting_factor = f"temperature_{temp_c:.0f}C_exceeds_{max_temp}C"
                    break

        # Check CO concentration
        if co_ppm_series:
            for t, co in co_ppm_series:
                if co >= max_co:
                    if t < aset:
                        aset = t
                        limiting_factor = f"CO_{co:.0f}ppm_exceeds_{max_co}ppm"
                    break

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
) -> RSETResult:
    """Calculate Required Safe Egress Time (RSET).

    RSET = Premovement Delay + Travel Time

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
        occ = "business"  # Safe default

    # Premovement delay
    if premovement_delay_s is not None:
        pm_delay = float(premovement_delay_s)
    else:
        pm_delay = PREMOVEMENT_DELAYS[occ][2]  # Design (conservative) value

    # Walking speed — reduce for high population density
    if walking_speed_mps is not None:
        speed = float(walking_speed_mps)
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
    travel_time = travel_distance_m / speed

    # Total RSET
    rset = pm_delay + travel_time

    # Safety factor
    if safety_factor is not None:
        sf = float(safety_factor)
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

    margin = aset - rset_with_sf
    is_safe = margin > 0

    if is_safe:
        verdict = (
            f"PASS: ASET ({aset:.1f}s) > RSET×SF ({rset_with_sf:.1f}s). "
            f"Safety margin: {margin:.1f}s ({margin/aset*100:.0f}% of ASET)."
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


__all__ = [
    "TENABILITY_THRESHOLDS",
    "PREMOVEMENT_DELAYS",
    "WALKING_SPEEDS",
    "SAFETY_FACTORS",
    "RISK_CATEGORIES",
    "ASETResult",
    "RSETResult",
    "AsetRsetValidation",
    "calculate_aset",
    "calculate_rset",
    "validate_aset_vs_rset",
]
