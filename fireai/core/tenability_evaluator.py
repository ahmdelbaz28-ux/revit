"""
fireai.core.tenability_evaluator — Tenability Assessment for Egress
===================================================================

Implements tenability criteria for occupant egress during fire:

1. Temperature Tenability — max 60°C (140°F) per SFPE / NFPA 101
2. Visibility Tenability  — min 10m visibility per SFPE Engineering Guide
3. CO Tenability         — max 1200 ppm per SFPE / NFPA 101
4. Combined Assessment   — ALL criteria must pass for tenable conditions

SAFETY CRITICAL:
  - These limits are for ENGINEERING ESTIMATION only
  - Actual tenability depends on occupant vulnerability, exposure duration,
    and many other factors
  - A margin of safety is ALWAYS applied
  - Tenability failure means occupants CANNOT safely evacuate
  - All NaN/Inf inputs are REJECTED

ENGINEERING SOURCES:
  - SFPE Engineering Guide to Performance-Based Fire Protection
  - NFPA 101-2024 — Life Safety Code
  - NFPA 72-2022 §17.7 — Detection Principles
  - ISO 13571 — Life-threatening components of fire
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# TENABILITY LIMITS
# ═══════════════════════════════════════════════════════════════════════════════

# Maximum temperature for tenable conditions (°C)
# SFPE / NFPA 101: 60°C (140°F) for short exposure
_MAX_TEMPERATURE_C = 60.0

# Minimum visibility for tenable conditions (meters)
# SFPE Engineering Guide: 10m for familiar occupants, 30m for unfamiliar
_MIN_VISIBILITY_M = 10.0

# Maximum CO concentration (ppm)
# SFPE / ISO 13571: 1200 ppm for short exposure
_MAX_CO_PPM = 1200.0

# Maximum CO2 concentration (ppm)
# SFPE / ISO 13571: 40000 ppm (4%) for short exposure
_MAX_CO2_PPM = 40000.0

# Maximum radiant heat flux (kW/m²)
# SFPE: 2.5 kW/m² for short exposure
_MAX_RADIANT_FLUX_KW_M2 = 2.5

# Safety margin applied to all tenability assessments
_TENABILITY_SAFETY_MARGIN = 0.20  # 20% margin


@dataclass(frozen=True)
class TenabilityResult:
    """Result from tenability assessment.

    Tenability is the ability of occupants to remain in or safely
    traverse a space during a fire. ALL criteria must be met for
    the space to be considered tenable.

    A failure in ANY single criterion means the space is NOT tenable.
    """
    is_tenable:           bool
    temperature_c:        float
    visibility_m:         float
    co_ppm:               float
    co2_ppm:              float
    radiant_flux_kw_m2:   float
    violations:           tuple   # Tuple of violation strings
    nfpa_references:      tuple   # Tuple of NFPA references


def evaluate_tenability(
    temperature_c: float,
    visibility_m: float,
    co_ppm: float = 0.0,
    co2_ppm: float = 0.0,
    radiant_flux_kw_m2: float = 0.0,
) -> TenabilityResult:
    """Evaluate tenability conditions for occupant egress.

    NFPA 101 / SFPE — A space is tenable only if ALL of the following
    are simultaneously satisfied:
      1. Temperature ≤ 60°C
      2. Visibility ≥ 10m
      3. CO ≤ 1200 ppm
      4. CO2 ≤ 40000 ppm
      5. Radiant heat flux ≤ 2.5 kW/m²

    With a 20% safety margin applied (i.e., thresholds are tightened
    by 20% — temperature limit becomes 48°C, visibility becomes 12.5m,
    etc.).

    Args:
        temperature_c: Gas temperature in °C.
        visibility_m: Visibility distance in meters.
        co_ppm: Carbon monoxide concentration in ppm.
        co2_ppm: Carbon dioxide concentration in ppm.
        radiant_flux_kw_m2: Radiant heat flux in kW/m².

    Returns:
        TenabilityResult with all criteria and overall assessment.
    """
    # Input validation
    for name, value in [
        ("temperature_c", temperature_c),
        ("visibility_m", visibility_m),
        ("co_ppm", co_ppm),
        ("co2_ppm", co2_ppm),
        ("radiant_flux_kw_m2", radiant_flux_kw_m2),
    ]:
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value}")
        if name != "temperature_c" and value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")

    violations = []
    references = []

    # Apply safety margin: tighten thresholds by 20%
    max_temp = _MAX_TEMPERATURE_C * (1.0 - _TENABILITY_SAFETY_MARGIN)  # 48°C
    min_vis = _MIN_VISIBILITY_M * (1.0 + _TENABILITY_SAFETY_MARGIN)    # 12.5m
    max_co = _MAX_CO_PPM * (1.0 - _TENABILITY_SAFETY_MARGIN)          # 960 ppm
    max_co2 = _MAX_CO2_PPM * (1.0 - _TENABILITY_SAFETY_MARGIN)        # 32000 ppm
    max_flux = _MAX_RADIANT_FLUX_KW_M2 * (1.0 - _TENABILITY_SAFETY_MARGIN)  # 2.0 kW/m²

    # Check temperature
    if temperature_c > max_temp:
        violations.append(
            f"Temperature {temperature_c:.1f}°C exceeds tenable limit "
            f"{max_temp:.1f}°C (SFPE/NFPA 101)"
        )
    references.append("SFPE/NFPA 101 §7")

    # Check visibility
    if visibility_m < min_vis:
        violations.append(
            f"Visibility {visibility_m:.1f}m below tenable minimum "
            f"{min_vis:.1f}m (SFPE Engineering Guide)"
        )
    references.append("SFPE Engineering Guide")

    # Check CO
    if co_ppm > max_co:
        violations.append(
            f"CO {co_ppm:.0f} ppm exceeds tenable limit "
            f"{max_co:.0f} ppm (ISO 13571)"
        )
    references.append("ISO 13571")

    # Check CO2
    if co2_ppm > max_co2:
        violations.append(
            f"CO2 {co2_ppm:.0f} ppm exceeds tenable limit "
            f"{max_co2:.0f} ppm (ISO 13571)"
        )
    references.append("ISO 13571")

    # Check radiant heat flux
    if radiant_flux_kw_m2 > max_flux:
        violations.append(
            f"Radiant flux {radiant_flux_kw_m2:.2f} kW/m² exceeds tenable "
            f"limit {max_flux:.2f} kW/m² (SFPE)"
        )
    references.append("SFPE")

    is_tenable = len(violations) == 0

    return TenabilityResult(
        is_tenable=is_tenable,
        temperature_c=temperature_c,
        visibility_m=visibility_m,
        co_ppm=co_ppm,
        co2_ppm=co2_ppm,
        radiant_flux_kw_m2=radiant_flux_kw_m2,
        violations=tuple(violations),
        nfpa_references=tuple(references),
    )
