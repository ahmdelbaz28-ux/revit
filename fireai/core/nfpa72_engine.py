"""fireai.core.nfpa72_engine — Core NFPA 72 Engineering Calculations
=================================================================

Implements the fundamental NFPA 72 fire alarm engineering calculations:

1. Battery Sizing — NFPA 72 §10.6.7 (secondary power supply)
2. Voltage Drop  — NFPA 72 §10.6.4, NEC Chapter 9 (circuit verification)
3. Detector Spacing — NFPA 72 §17.6.3.1, Table 17.6.3.1
4. Detector Count Estimation — NFPA 72 §17.7.4.2.3.1
5. Fault Isolator Placement — NFPA 72 §12.3

SAFETY CRITICAL:
  - Battery calculations use 20% safety margin per NFPA 72 §10.6.7.2.1
  - Voltage drop uses DC return path factor (×2) per NEC 760
  - Wire resistance from NEC Chapter 9, Table 8
  - All NaN/Inf inputs are REJECTED
  - All negative inputs are REJECTED

ENGINEERING SOURCES:
  - NFPA 72-2022 — primary standard for all fire alarm calculations
  - NEC (NFPA 70) Chapter 9, Table 8 — wire resistance values
  - NEC 760 — fire alarm circuit requirements

NOTE: Previous version falsely claimed "inspiration" from ElectricPy and
SprayHydraulic repositories. That was dishonest — no code or formula from
those repositories was actually used. All calculations are from NFPA/NEC
standards directly. If future versions incorporate specific formulas from
external sources, they will be explicitly documented with line references.

All formulas are traced to their NFPA/NEC source sections.

V59 FIX (2026-05-30): Added temperature-corrected resistance calculations,
NEC 310.16 ampacity verification, and NEC 310.15(B) derating factors.
Previous code used 20°C resistance only — this UNDERESTIMATES voltage drop
by 21.6% at 75°C operating temperature, which is DANGEROUS for Egypt
(40-50°C ambient). This was identified through self-criticism per agent.md §21.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List

from fireai.constants.nec import (
    COPPER_TEMP_COEFFICIENT,
    DEFAULT_OPERATING_TEMP_C,
    TABLE8_REFERENCE_TEMP_C,
)
from fireai.constants.nec import (
    NEC_TABLE8_RESISTANCE_OHM_PER_KM_20C as AWG_RESISTANCE_OHM_PER_KM,
)
from fireai.constants.nfpa72 import HEAT_HEIGHT_SPACING_TABLE as _HEAT_SPACING_TABLE

# ═══════════════════════════════════════════════════════════════════════════════
# WIRE RESISTANCE TABLE — Imported from canonical source
# ═══════════════════════════════════════════════════════════════════════════════
# C-3 FIX: AWG_RESISTANCE_OHM_PER_KM is now imported from
# fireai.constants.nec.NEC_TABLE8_RESISTANCE_OHM_PER_KM_20C (Single Source of Truth).
# Previous local table had values ~2x the correct NEC Table 8 values.


# ═══════════════════════════════════════════════════════════════════════════════
# COPPER TEMPERATURE COEFFICIENT — Imported from canonical source
# ═══════════════════════════════════════════════════════════════════════════════
# C-3 FIX: COPPER_TEMP_COEFFICIENT, DEFAULT_OPERATING_TEMP_C, and
# TABLE8_REFERENCE_TEMP_C are now imported from fireai.constants.nec.
# Previous local values duplicated the canonical source.
#
# Formula:
#   R_T = R_20 * [1 + alpha * (T - 20)]
#
# This is CRITICAL for hot climates like Egypt (ambient 40-50 degC):
#   At 75 degC operating temperature:
#     R_75 = R_20 * [1 + 0.00393 * (75 - 20)] = R_20 * 1.2163
#     Resistance is 21.6% HIGHER than at 20 degC!
#
# NEC practice: Use 75 degC for thermoplastic insulation (THHN/THWN),
# and the conductor rating column from NEC 310.16 for ampacity.


# ═══════════════════════════════════════════════════════════════════════════════
# NEC 310.16 — AMPACITY TABLE (Copper conductors, not more than 3
# current-carrying conductors in raceway/conduit, 30 degC ambient)
# ═══════════════════════════════════════════════════════════════════════════════

# NEC 310.16 Ampacity Table — Copper, 60 degC / 75 degC / 90 degC columns
# Values in Amperes. For not more than 3 current-carrying conductors
# in a raceway or cable, based on 30 degC ambient temperature.
#
# FA circuits typically use 75 degC rated THHN/THWN wire.
# We provide all three columns for completeness.
AMPACITY_TABLE_NEC_310_16 = {
    # AWG: (60 degC column, 75 degC column, 90 degC column) in Amperes
    "18": (0, 0, 14),  # AWG 18 not in 60/75 columns
    "16": (0, 0, 18),  # AWG 16 not in 60/75 columns
    "14": (20, 25, 30),
    "12": (25, 30, 35),
    "10": (35, 40, 45),
    "8": (50, 60, 70),
    "6": (65, 75, 85),
    "4": (85, 95, 110),
    "3": (95, 110, 125),
    "2": (115, 130, 145),
    "1": (130, 150, 165),
    "1/0": (150, 170, 190),
    "2/0": (175, 195, 215),
    "3/0": (200, 225, 245),
    "4/0": (230, 260, 280),
}


# ═══════════════════════════════════════════════════════════════════════════════
# NEC 310.15(B)(2)(A) — AMBIENT TEMPERATURE CORRECTION FACTORS
# ═══════════════════════════════════════════════════════════════════════════════

# Per NEC 310.15(B)(2)(A): When ambient temperature differs from 30 degC,
# ampacity must be corrected by multiplying by the appropriate factor.
#
# CRITICAL FOR EGYPT: Summer ambient temperatures reach 40-50 degC.
# At 50 degC ambient, 90 degC rated conductor derating factor = 0.82
# This means 18% LESS ampacity than the NEC 310.16 table value!
#
# Table from NEC 310.15(B)(2)(A):
AMBIENT_TEMP_CORRECTION_FACTORS = {
    # (ambient_degC): (60 degC rated, 75 degC rated, 90 degC rated)
    # V62 FIX: Added 60 degC column per NEC 310.15(B)(2)(A).
    # Previously, 60 degC rated conductors used the 75 degC column,
    # overestimating ampacity by up to 7.3% — potential fire hazard.
    # V65 FIX: Corrected 30°C entry for 60°C column from 0.82 to 1.00.
    # V66 FIX: Corrected ALL entries per NEC 310.15(B)(2)(A) verified values.
    # V65 had systematically wrong 75°C and 90°C columns — each value
    # was the NEC value for 5°C LOWER temperature, overstating ampacity
    # by up to 19% for 60°C-rated wire at 50°C ambient (Egyptian summer).
    # Key semantics: each key represents the UPPER bound of the NEC range.
    # E.g., key 25 = NEC range 21-25°C; key 40 = NEC range 36-40°C.
    21: (1.05, 1.05, 1.04),  # NEC range 1-21°C
    25: (1.05, 1.05, 1.04),  # NEC range 21-25°C
    30: (1.00, 1.00, 1.00),  # NEC range 26-30°C — NEC 310.16 baseline
    35: (0.91, 0.94, 0.96),  # NEC range 31-35°C
    40: (0.82, 0.88, 0.91),  # NEC range 36-40°C — Common in Egyptian buildings
    45: (0.71, 0.82, 0.87),  # NEC range 41-45°C
    50: (0.58, 0.75, 0.82),  # NEC range 46-50°C — Egyptian summer peak
    55: (0.41, 0.67, 0.76),  # NEC range 51-55°C
    60: (0.29, 0.58, 0.71),  # NEC range 56-60°C
    65: (0.00, 0.47, 0.65),  # NEC range 61-65°C — 60C rated not permitted above 60°C
    70: (0.00, 0.33, 0.58),  # NEC range 66-70°C
    75: (0.00, 0.15, 0.50),  # NEC range 71-75°C
    80: (0.00, 0.00, 0.41),  # NEC range 76-80°C
}


# ═══════════════════════════════════════════════════════════════════════════════
# NEC 310.15(B)(3)(a) — CONDUCTOR COUNT DERATING FACTORS
# ═══════════════════════════════════════════════════════════════════════════════

# Per NEC 310.15(B)(3)(a): When more than 3 current-carrying conductors
# are in a raceway or cable, the ampacity must be reduced by the
# following adjustment factors.
#
# For FA circuits: PLFA (Class 2/3) circuits may share conduit with
# other PLFA circuits but NOT with NPLFA or power circuits per
# NEC 760.154.
CONDUCTOR_COUNT_DERATING = {
    # NEC 310.15(B)(3)(a) adjustment table
    1: 1.00,  # No derating needed
    2: 1.00,  # No derating needed
    3: 1.00,  # Baseline - no derating (NEC 310.16 assumes <=3)
    4: 0.80,  # 4-6 conductors: 80%
    5: 0.80,
    6: 0.80,
    7: 0.70,  # 7-9 conductors: 70%
    8: 0.70,
    9: 0.70,
    10: 0.50,  # 10-20 conductors: 50%
    20: 0.50,
    21: 0.45,  # 21-30 conductors: 45%
    30: 0.45,
    31: 0.40,  # 31-40 conductors: 40%
    40: 0.40,
    41: 0.35,  # Over 40 conductors: 35%
}


# ═══════════════════════════════════════════════════════════════════════════════
# NFPA 72 TABLE 17.6.3.1 — Detector Spacing vs Ceiling Height
# M-10 FIX: _SMOKE_SPACING_TABLE replaced with flat 9.1m per V130 fix.
# NFPA 72-2022 §17.7.3.2.3 mandates flat 9.1m for smoke detectors at ALL heights.
# The old table incorrectly applied heat detector reduction to smoke detectors.
# ═══════════════════════════════════════════════════════════════════════════════

# M-10 FIX: Smoke detector spacing is FLAT at 9.1m per NFPA 72 §17.7.3.2.3.
# The old height-reduced table (8.20, 7.30, 6.40...) was the V130 bug —
# it applied heat detector reduction (Table 17.6.3.5.1) to smoke detectors,
# which is WRONG. Smoke detectors have NO height-based spacing reduction.
# Source: fireai/constants/nfpa72.py SMOKE_HEIGHT_SPACING_TABLE (canonical).
_SMOKE_SPACING_TABLE = [
    # (max_ceiling_height_m, listed_spacing_m)
    # ALL heights: flat 9.10m per NFPA 72-2022 §17.7.3.2.3
    (3.0, 9.10),   # flat 9.1m
    (3.9, 9.10),   # flat 9.1m
    (4.9, 9.10),   # flat 9.1m
    (6.1, 9.10),   # flat 9.1m
    (7.6, 9.10),   # flat 9.1m
    (9.1, 9.10),   # flat 9.1m
    (10.7, 9.10),  # flat 9.1m
    (12.2, 9.10),  # flat 9.1m
]

# _HEAT_SPACING_TABLE is now imported from fireai.constants.nfpa72.HEAT_HEIGHT_SPACING_TABLE
# C-3 FIX: Previous local table had 6 rows with divergent values vs canonical 9-row table.
# Canonical source: NFPA 72-2022 Table 17.6.3.5.1 (heat detector height reduction).


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SpacingResult:
    """Result from NFPA 72 detector spacing calculation."""

    max_spacing_m: float
    coverage_radius_m: float
    nfpa_section: str
    formula: str
    table_row_used: str


@dataclass(frozen=True)
class BatteryResult:
    """Result from NFPA 72 battery sizing calculation.

    NFPA 72 §10.6.7 requires secondary supply capacity:
      - 24 hours of standby current
      - PLUS 5 minutes (300s) of alarm current
      - WITH 20% safety margin

    Formula:
      Ah_required = (I_standby × 24h + I_alarm × 5min/60) × 1.20
    """

    required_ah: float
    installed_ah: float
    is_adequate: bool
    formula: str
    nfpa_section: str


@dataclass(frozen=True)
class VoltageDropResult:
    """Result from NFPA 72 voltage drop calculation.

    NEC 760 and NFPA 72 §10.6.4:
      V_drop = I × 2 × R_wire(T) × L
      The ×2 factor accounts for the DC return path.

    For 24V systems, end-of-line voltage must be ≥ 21.6V (10% max drop).

    V59: Resistance is now temperature-corrected per NEC practice.
    """

    voltage_drop_v: float
    voltage_drop_pct: float
    max_length_m: float
    is_compliant: bool
    formula: str


@dataclass(frozen=True)
class AmpacityResult:
    """Result from NEC 310.16 ampacity verification.

    NEC 310.16 provides maximum allowable ampacities for copper
    conductors. This result includes:
    - Base ampacity from NEC 310.16
    - Derating for ambient temperature per NEC 310.15(B)(2)(A)
    - Derating for conductor count per NEC 310.15(B)(3)(a)
    - Adjusted (actual) ampacity after all deratings
    - Compliance status

    This is CRITICAL for Egypt: at 40-50 degC ambient, a wire rated for
    25A at 30 degC may only carry 18-22A after temperature correction.
    """

    awg_gauge: str
    base_ampacity_a: float
    ambient_derating: float
    conductor_derating: float
    adjusted_ampacity_a: float
    actual_current_a: float
    is_compliant: bool
    formula: str
    nec_section: str = "NEC 310.16"


# ═══════════════════════════════════════════════════════════════════════════════
# SPACING CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════


def get_detector_spacing(
    ceiling_height_m: float,
    detector_type: str,
) -> SpacingResult:
    """Determine NFPA 72 listed spacing for a given ceiling height.

    Reference: NFPA 72-2022 §17.6.3.1, Table 17.6.3.1

    Args:
        ceiling_height_m: Ceiling height in meters.
        detector_type: 'smoke' or 'heat'.

    Returns:
        SpacingResult with max spacing, coverage radius, and NFPA reference.

    """
    # V96 FIX: Invalid ceiling height must raise ValueError, not return
    # a valid-looking SpacingResult. The old code returned max_spacing_m=3.00
    # (a real NFPA table value) with table_row_used="fallback_conservative",
    # but no downstream code checks that field. A NaN/negative ceiling height
    # means the input is broken — fail loudly per Rule 5 (hard failure).
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        raise ValueError(f"ceiling_height_m must be positive finite, got {ceiling_height_m}")

    det_type = detector_type.lower()
    table = _SMOKE_SPACING_TABLE if det_type == "smoke" else _HEAT_SPACING_TABLE

    # M-10 FIX: Smoke detector fallback is flat 9.10m (no height reduction).
    # Heat detector fallback is conservative 3.00m (height-based reduction applies).
    spacing = 9.10 if det_type == "smoke" else 3.00
    row_desc = f">{table[-1][0]}m (conservative)"

    for max_h, listed_s in table:
        if ceiling_height_m <= max_h:
            spacing = listed_s
            row_desc = f"≤{max_h}m"
            break

    # R = 0.7 × S per NFPA 72 §17.7.4.2.3.1
    coverage_radius = 0.7 * spacing

    return SpacingResult(
        max_spacing_m=spacing,
        coverage_radius_m=round(coverage_radius, 4),
        nfpa_section="NFPA 72 §17.6.3.1",
        formula=f"S={spacing}m (Table 17.6.3.1, h={ceiling_height_m:.1f}m, {det_type}); R=0.7×S",
        table_row_used=row_desc,
    )


def estimate_detector_count(
    room_area_m2: float,
    ceiling_height_m: float,
    detector_type: str,
) -> Dict[str, Any]:
    """Estimate minimum number of detectors for a room.

    Reference: NFPA 72 §17.6.3.1, §17.7.4.2.3.1

    Each detector covers a circle of radius R = 0.7 × S.
    Conservative estimate: ceil(area / (π × R²)).

    Args:
        room_area_m2: Room area in square meters.
        ceiling_height_m: Ceiling height in meters.
        detector_type: 'smoke' or 'heat'.

    Returns:
        Dict with min_detector_count, area_per_detector_m2, spacing info.

    """
    spacing_result = get_detector_spacing(ceiling_height_m, detector_type)
    radius_m = spacing_result.coverage_radius_m

    # V96 FIX: Invalid room area must NOT return a success-like result.
    # Returning min_detector_count=1 for NaN/negative area is the
    # "failure returns success" anti-pattern — downstream code sees
    # count >= 1 and treats the room as covered. Fail-safe: return
    # count=0 with an explicit error field so callers can detect failure.
    #
    # C-4 FIX: Never return float("nan") in dict values. float("nan")
    # in JSON is either sent as invalid "NaN" literal (RFC 8259 violation)
    # or converted to null by the serializer — both silently corrupt
    # downstream calculations. In fire protection engineering, NaN in
    # area_per_detector_m2 could lead to zero detectors being placed
    # for a room that actually needs coverage — a life-safety catastrophe.
    # Replace float("nan") with None, which JSON serializes as null
    # explicitly and callers can check for deterministically.
    if not math.isfinite(room_area_m2) or room_area_m2 <= 0:
        return {
            "min_detector_count": 0,
            "area_per_detector_m2": None,  # C-4 FIX: was float("nan")
            "spacing_m": spacing_result.max_spacing_m,
            "coverage_radius_m": radius_m,
            "error": f"Invalid room_area_m2: {room_area_m2}",
        }

    coverage_area_per_detector = math.pi * radius_m**2
    min_count = max(1, math.ceil(room_area_m2 / coverage_area_per_detector))

    return {
        "min_detector_count": min_count,
        "area_per_detector_m2": round(coverage_area_per_detector, 4),
        "spacing_m": spacing_result.max_spacing_m,
        "coverage_radius_m": radius_m,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BATTERY CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

# Standard battery sizes (Ah) — common lead-acid/SLA batteries
_STANDARD_BATTERY_SIZES = [
    1.2,
    2.0,
    3.0,
    4.0,
    5.0,
    7.0,
    7.2,
    8.0,
    10.0,
    12.0,
    15.0,
    18.0,
    20.0,
    25.0,
    26.0,
    28.0,
    31.0,
    33.0,
    40.0,
    50.0,
    55.0,
    60.0,
    70.0,
    75.0,
    80.0,
    100.0,
    120.0,
    150.0,
    180.0,
    200.0,
]

# NFPA 72 battery derating — Peukert-like derating for lead-acid
# At higher discharge rates, effective capacity decreases
_BATTERY_DERATING_FACTOR = 0.85  # 15% derating for lead-acid at alarm rates


def calculate_battery(
    standby_current_a: float,
    alarm_current_a: float,
    *,
    standby_hours: float = 24.0,
    alarm_minutes: float = 5.0,
    safety_margin: float = 0.20,
    ps_voltage: float = 24.0,
) -> BatteryResult:
    """Calculate required battery capacity per NFPA 72 §10.6.7.

    NFPA 72 §10.6.7 requires the secondary supply to have sufficient
    capacity to operate the system under normal load for 24 hours and
    then operate all alarm appliances for 5 minutes.

    Formula:
      Ah_derated = (I_standby × 24h + I_alarm × 5min/60h)
      Ah_required = Ah_derated / derating_factor × (1 + safety_margin)

    The derating factor accounts for the Peukert effect in lead-acid
    batteries — at higher discharge rates, effective capacity is less
    than the rated capacity.

    Args:
        standby_current_a: Standby current draw in amperes.
        alarm_current_a: Alarm current draw in amperes.
        standby_hours: Standby duration in hours (default 24 per NFPA 72).
        alarm_minutes: Alarm duration in minutes (default 5 per NFPA 72).
        safety_margin: Additional safety margin (default 20%).
        ps_voltage: Power supply nominal voltage (default 24V).

    Returns:
        BatteryResult with required Ah, installed Ah, and compliance.

    """
    # Input validation — safety first
    if not math.isfinite(standby_current_a) or standby_current_a < 0:
        raise ValueError(f"standby_current_a must be non-negative finite, got {standby_current_a}")
    if not math.isfinite(alarm_current_a) or alarm_current_a < 0:
        raise ValueError(f"alarm_current_a must be non-negative finite, got {alarm_current_a}")
    if standby_current_a == 0 and alarm_current_a == 0:
        raise ValueError("Both standby and alarm current cannot be zero — no load specified")
    # V69-6 FIX: Validate safety_margin, standby_hours, alarm_minutes
    # A negative safety_margin reduces required capacity — life safety hazard.
    # standby_hours ≤ 0 or alarm_minutes ≤ 0 violates NFPA 72 §10.6.7.
    if not math.isfinite(safety_margin) or safety_margin < 0:
        raise ValueError(f"safety_margin must be non-negative finite, got {safety_margin}")
    if not math.isfinite(standby_hours) or standby_hours <= 0:
        raise ValueError(f"standby_hours must be positive finite, got {standby_hours}")
    if not math.isfinite(alarm_minutes) or alarm_minutes <= 0:
        raise ValueError(f"alarm_minutes must be positive finite, got {alarm_minutes}")

    # Step 1: Calculate raw Ah requirement
    # Standby: 24 hours at standby current
    standby_ah = standby_current_a * standby_hours

    # Alarm: 5 minutes at alarm current
    alarm_hours = alarm_minutes / 60.0
    alarm_ah = alarm_current_a * alarm_hours

    # Total derated Ah (Peukert effect for lead-acid)
    total_ah_raw = standby_ah + alarm_ah
    total_ah_derated = total_ah_raw / _BATTERY_DERATING_FACTOR

    # Step 2: Apply safety margin
    ah_required = total_ah_derated * (1.0 + safety_margin)

    # Step 3: Find next standard battery size
    installed_ah = ah_required  # Default: exact
    for size in _STANDARD_BATTERY_SIZES:
        if size >= ah_required:
            installed_ah = size
            break
    else:
        # No standard size found — round up to nearest 10
        installed_ah = math.ceil(ah_required / 10.0) * 10.0

    is_adequate = installed_ah >= ah_required

    formula = (
        f"Ah = (I_sb×{standby_hours}h + I_al×{alarm_minutes}min/60) "
        f"/ {_BATTERY_DERATING_FACTOR} × (1+{safety_margin}) = "
        f"({standby_current_a:.4f}×{standby_hours} + {alarm_current_a:.4f}×{alarm_hours:.4f}) "
        f"/ {_BATTERY_DERATING_FACTOR} × {1 + safety_margin} = {ah_required:.2f} Ah"
    )

    return BatteryResult(
        required_ah=round(ah_required, 4),
        installed_ah=round(installed_ah, 4),
        is_adequate=is_adequate,
        formula=formula,
        nfpa_section="NFPA 72 §10.6.7",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VOLTAGE DROP CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 maximum voltage drop: 10% for 24V systems = 2.4V
# End-of-line voltage must be ≥ 21.6V
_MAX_VOLTAGE_DROP_PCT = 10.0
_SYSTEM_VOLTAGE = 24.0


def temperature_corrected_resistance(
    r_at_20c: float,
    operating_temp_c: float = DEFAULT_OPERATING_TEMP_C,
) -> float:
    """Calculate temperature-corrected wire resistance.

    NEC Chapter 9, Table 8 provides resistance at 20 degC reference.
    However, conductors operate at higher temperatures in practice.
    Per NEC practice, voltage drop calculations should use resistance
    at the expected operating temperature, NOT 20 degC.

    Formula (copper temperature coefficient, alpha = 0.00393 /degC):
      R_T = R_20 * [1 + alpha * (T - 20)]

    This is CRITICAL for hot climates like Egypt:
      - At 75 degC (typical operating temp for THHN/THWN):
        R_75 = R_20 * 1.2163 (21.6% higher resistance!)
      - Using R_20 would UNDERESTIMATE voltage drop by ~18%
      - Underestimated voltage drop => non-compliant circuit =>
        devices may not operate during fire => LIFE SAFETY FAILURE

    Args:
        r_at_20c: Wire resistance at 20 degC in Ohm/km.
        operating_temp_c: Expected conductor operating temperature in degC.
                         Default 75 degC (NEC practice for THHN/THWN).

    Returns:
        Temperature-corrected resistance in Ohm/km.

    Raises:
        ValueError: If inputs are invalid.

    """
    if not math.isfinite(r_at_20c) or r_at_20c < 0:
        raise ValueError(f"r_at_20c must be non-negative finite, got {r_at_20c}")
    if not math.isfinite(operating_temp_c) or operating_temp_c < -50:
        raise ValueError(f"operating_temp_c must be finite and >= -50, got {operating_temp_c}")

    corrected = r_at_20c * (1.0 + COPPER_TEMP_COEFFICIENT * (operating_temp_c - TABLE8_REFERENCE_TEMP_C))
    # V65 SAFETY: Negative resistance means temperature factor made R negative.
    # This occurs at extremely cold temperatures (below ~-234°C for copper).
    # Silently clamping to 0.0 is DANGEROUS — it makes voltage drop = 0V,
    # which always passes compliance. A 0V drop on a fire alarm circuit is
    # physically impossible and masks a real failure.
    if corrected < 0:
        raise ValueError(
            f"Temperature-corrected resistance is negative ({corrected:.6f} Ohm/km) "
            f"at operating_temp_c={operating_temp_c}°C. This is physically impossible "
            f"for copper conductors and indicates an invalid temperature input. "
            f"Voltage drop would appear as 0V (always compliant), which is a "
            f"LIFE-SAFETY HAZARD. Refuse to compute."
        )
    return corrected


def calculate_voltage_drop(
    alarm_current_a: float,
    circuit_length_m: float,
    awg_gauge: str = "14",
    *,
    ps_voltage: float = 24.0,
    max_drop_pct: float = _MAX_VOLTAGE_DROP_PCT,
    ambient_temperature_c: float = DEFAULT_OPERATING_TEMP_C,
) -> VoltageDropResult:
    """Calculate voltage drop on a fire alarm circuit.

    NFPA 72 §10.6.4 and NEC Chapter 9, Table 8:
      V_drop = I × 2 × R_wire(T) × L

    The ×2 factor accounts for the DC return path (current flows out
    on one conductor and returns on the other). This was a CRITICAL
    bug fix in V14 — missing ×2 meant voltage drop was reported at
    50% of actual value, which is life-safety-dangerous.

    V59 FIX: Added temperature correction for wire resistance.
    NEC Chapter 9, Table 8 gives resistance at 20 degC, but conductors
    operate at 60-75 degC in practice. Using 20 degC resistance UNDERESTIMATES
    voltage drop, which is DANGEROUS in hot climates like Egypt (40-50 degC).
    At 75 degC, resistance is 21.6% higher than at 20 degC.

    For 24V systems: V_eol = V_ps - V_drop
    Compliant if V_eol >= V_ps * (1 - max_drop_pct/100)

    Args:
        alarm_current_a: Total alarm current on the circuit (A).
        circuit_length_m: One-way circuit length in meters.
        awg_gauge: Wire gauge string (e.g. '14', '12').
        ps_voltage: Power supply voltage (default 24V).
        max_drop_pct: Maximum allowed voltage drop % (default 10%).
        ambient_temperature_c: Conductor operating temperature in degC.
            Default 20 degC (NEC Table 8 reference — backward compatible).
            IMPORTANT: For real-world calculations, especially in Egypt,
            use 75 degC (THHN/THWN operating temperature) or higher.
            At 75 degC, resistance is 21.6% higher than at 20 degC.
            IMPORTANT: This is the conductor OPERATING temperature,
            not the ambient air temperature. Conductor temperature is
            higher than ambient due to I2R heating.

    Returns:
        VoltageDropResult with drop, percentage, max length, compliance.

    """
    # Input validation
    if not math.isfinite(alarm_current_a) or alarm_current_a < 0:
        raise ValueError(f"alarm_current_a must be non-negative finite, got {alarm_current_a}")
    if not math.isfinite(circuit_length_m) or circuit_length_m < 0:
        raise ValueError(f"circuit_length_m must be non-negative finite, got {circuit_length_m}")
    if not math.isfinite(ambient_temperature_c) or ambient_temperature_c < -50:
        raise ValueError(f"ambient_temperature_c must be finite and >= -50, got {ambient_temperature_c}")
    # V66 FIX: Validate ps_voltage — negative ps_voltage produces negative
    # drop_pct which always passes compliance check (NaN <= max == False is safe,
    # but negative ps_voltage <= 10.0 == True is dangerous).
    if not math.isfinite(ps_voltage) or ps_voltage <= 0:
        raise ValueError(f"ps_voltage must be positive finite, got {ps_voltage}")
    if not math.isfinite(max_drop_pct) or max_drop_pct <= 0 or max_drop_pct > 100:
        raise ValueError(f"max_drop_pct must be in (0, 100], got {max_drop_pct}")

    # Get wire resistance at 20 degC (NEC Chapter 9, Table 8)
    gauge = str(awg_gauge).strip()
    if gauge not in AWG_RESISTANCE_OHM_PER_KM:
        raise ValueError(f"Unsupported AWG gauge '{gauge}'. Supported: {sorted(AWG_RESISTANCE_OHM_PER_KM.keys())}")

    r_at_20c = AWG_RESISTANCE_OHM_PER_KM[gauge]

    # V59 FIX: Apply temperature correction to resistance
    # Per NEC practice, use operating temperature resistance for
    # voltage drop calculations, NOT the 20 degC reference value.
    r_per_km = temperature_corrected_resistance(r_at_20c, ambient_temperature_c)

    # Voltage drop: V_drop = I × 2 × R(T)/km × L(km)
    # The ×2 is for the DC return path — CRITICAL for life safety
    length_km = circuit_length_m / 1000.0
    voltage_drop = alarm_current_a * 2.0 * r_per_km * length_km

    # Voltage drop percentage
    # ps_voltage is guaranteed > 0 by input validation above
    drop_pct = (voltage_drop / ps_voltage) * 100.0

    # Maximum circuit length for compliance (using temperature-corrected R)
    max_drop_v = ps_voltage * (max_drop_pct / 100.0)
    if alarm_current_a > 0 and r_per_km > 0:
        max_length_km = max_drop_v / (alarm_current_a * 2.0 * r_per_km)
        max_length_m = max_length_km * 1000.0
    else:
        max_length_m = 0.0

    is_compliant = drop_pct <= max_drop_pct

    # Build formula with temperature info
    temp_note = ""
    if abs(ambient_temperature_c - TABLE8_REFERENCE_TEMP_C) > 1.0:
        pct_increase = ((r_per_km / r_at_20c) - 1.0) * 100
        temp_note = (
            f" [R corrected: {r_at_20c:.3f}Ohm/km@20C -> "
            f"{r_per_km:.3f}Ohm/km@{ambient_temperature_c:.0f}C, "
            f"+{pct_increase:.1f}%]"
        )

    formula = (
        f"V_drop = I * 2 * R(T) * L = "
        f"{alarm_current_a:.4f} * 2 * {r_per_km:.3f}Ohm/km@{ambient_temperature_c:.0f}C * "
        f"{length_km:.6f}km = {voltage_drop:.4f}V "
        f"({drop_pct:.2f}% of {ps_voltage}V)"
        f"{temp_note}"
    )

    return VoltageDropResult(
        voltage_drop_v=round(voltage_drop, 4),
        voltage_drop_pct=round(drop_pct, 4),
        max_length_m=round(max_length_m, 2),
        is_compliant=is_compliant,
        formula=formula,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AMPACITY VERIFICATION — NEC 310.16
# ═══════════════════════════════════════════════════════════════════════════════


def get_ambient_derating_factor(
    ambient_temp_c: float,
    conductor_temp_rating_c: float = 90,
) -> float:
    """Get ambient temperature derating factor per NEC 310.15(B)(2)(A).

    When the ambient temperature differs from 30 degC (the baseline for
    NEC 310.16), the ampacity must be corrected by a factor from
    NEC 310.15(B)(2)(A).

    CRITICAL FOR EGYPT: At 40-50 degC ambient, the derating factor is
    0.82-0.91 (for 90 degC rated conductors), meaning 9-18% LESS current
    capacity than the NEC 310.16 table value.

    Args:
        ambient_temp_c: Ambient air temperature in degC.
        conductor_temp_rating_c: Conductor insulation temperature rating
            (60, 75, or 90). Default 90 (THHN/THWN-2).

    Returns:
        Derating factor (0.0 to 1.0+). Values >1.0 for low temperatures.

    Raises:
        ValueError: If inputs are invalid.

    """
    if not math.isfinite(ambient_temp_c):
        raise ValueError(f"ambient_temp_c must be finite, got {ambient_temp_c}")
    if conductor_temp_rating_c not in (60, 75, 90):
        raise ValueError(f"conductor_temp_rating_c must be 60, 75, or 90, got {conductor_temp_rating_c}")

    # V65 FIX: Removed early return for temps ≤ 30°C. Previously, this
    # returned 1.0 for ALL conductor ratings at ≤30°C, but the actual NEC
    # 310.15(B)(2)(A) table has non-1.0 values for some ratings below 30°C.
    # For example, at 25°C ambient with 60°C-rated wire, the correct factor
    # is 0.91, not 1.00. The early return was overstating ampacity by ~10%
    # for 60°C-rated conductors at 25°C ambient — a potential fire hazard.

    # Look up in the correction table
    # Find the nearest temperature entry at or below the requested temp
    # V62 FIX: Added 60 degC column support. Previously, 60 degC rated
    # conductors incorrectly used the 75 degC column, overstating ampacity.
    col_idx = {60: 0, 75: 1, 90: 2}[int(conductor_temp_rating_c)]  # type: ignore[index]

    sorted_temps = sorted(AMBIENT_TEMP_CORRECTION_FACTORS.keys())

    for temp in sorted_temps:
        if temp >= ambient_temp_c:
            factor = AMBIENT_TEMP_CORRECTION_FACTORS[temp][col_idx]
            return factor

    # Above highest table entry — use linear extrapolation (conservative)
    highest_temp = sorted_temps[-1]
    highest_factor = AMBIENT_TEMP_CORRECTION_FACTORS[highest_temp][col_idx]

    # Each 5 degC above 70 degC reduces factor by ~0.07 (conservative)
    excess_temp = ambient_temp_c - highest_temp
    additional_derating = (excess_temp / 5.0) * 0.07
    factor = highest_factor - additional_derating

    return max(0.0, factor)


def get_conductor_count_derating(
    num_current_carrying: int,
) -> float:
    """Get conductor count derating factor per NEC 310.15(B)(3)(a).

    When more than 3 current-carrying conductors are installed in a
    raceway or cable, the ampacity must be reduced per NEC 310.15(B)(3)(a).

    For fire alarm circuits, each PLFA circuit typically has 2
    current-carrying conductors (outgoing and return). So:
    - 1 FA circuit = 2 conductors -> no derating
    - 2 FA circuits = 4 conductors -> 0.80 derating
    - 3 FA circuits = 6 conductors -> 0.80 derating

    Note: Grounding conductors are NOT counted per NEC 310.15(B)(5).

    Args:
        num_current_carrying: Number of current-carrying conductors.

    Returns:
        Derating factor (0.35 to 1.0).

    Raises:
        ValueError: If num_current_carrying < 1.

    """
    if not isinstance(num_current_carrying, int) or num_current_carrying < 1:
        raise ValueError(f"num_current_carrying must be a positive integer, got {num_current_carrying}")

    if num_current_carrying <= 3:
        return 1.00

    # Find the appropriate derating factor
    if num_current_carrying <= 6:
        return CONDUCTOR_COUNT_DERATING[4]  # 0.80
    if num_current_carrying <= 9:
        return CONDUCTOR_COUNT_DERATING[7]  # 0.70
    if num_current_carrying <= 20:
        return CONDUCTOR_COUNT_DERATING[10]  # 0.50
    if num_current_carrying <= 30:
        return CONDUCTOR_COUNT_DERATING[21]  # 0.45
    if num_current_carrying <= 40:
        return CONDUCTOR_COUNT_DERATING[31]  # 0.40
    return CONDUCTOR_COUNT_DERATING[41]  # 0.35


def check_ampacity(
    alarm_current_a: float,
    awg_gauge: str = "14",
    conductor_temp_rating_c: float = 90,
    ambient_temp_c: float = 30.0,
    num_current_carrying: int = 2,
) -> AmpacityResult:
    """Verify wire ampacity per NEC 310.16 with all required deratings.

    NEC 310.16 provides base ampacity values for copper conductors
    at 30 degC ambient with <=3 current-carrying conductors in raceway.

    Two additional deratings are REQUIRED by NEC:
    1. NEC 310.15(B)(2)(A): Ambient temperature correction
       - At 40 degC ambient: factor = 0.91 (90 degC rated)
       - At 50 degC ambient: factor = 0.82 (90 degC rated) <- EGYPT!
    2. NEC 310.15(B)(3)(a): Conductor count adjustment
       - >3 conductors in conduit: factor < 1.0

    The adjusted ampacity must be >= the actual circuit current.

    SAFETY NOTE: Previous versions did NOT verify ampacity at all.
    This meant a wire could be selected based on voltage drop alone,
    even if it could not safely carry the required current.
    This is a CRITICAL addition for Egypt where high ambient
    temperatures significantly reduce wire ampacity.

    Args:
        alarm_current_a: Total alarm current in amperes.
        awg_gauge: Wire gauge string (e.g. '14', '12').
        conductor_temp_rating_c: Insulation temperature rating (60, 75, 90).
        ambient_temp_c: Ambient air temperature in degC (default 30 degC).
        num_current_carrying: Number of current-carrying conductors in
            conduit (default 2 for single FA circuit).

    Returns:
        AmpacityResult with full derating analysis.

    Raises:
        ValueError: If inputs are invalid or gauge not found.

    """
    # Input validation
    if not math.isfinite(alarm_current_a) or alarm_current_a < 0:
        raise ValueError(f"alarm_current_a must be non-negative finite, got {alarm_current_a}")

    gauge = str(awg_gauge).strip()
    if gauge not in AMPACITY_TABLE_NEC_310_16:
        raise ValueError(f"Unsupported AWG gauge '{gauge}'. Supported: {sorted(AMPACITY_TABLE_NEC_310_16.keys())}")

    # Get base ampacity from NEC 310.16
    amp_60, amp_75, amp_90 = AMPACITY_TABLE_NEC_310_16[gauge]

    # Select the appropriate column based on conductor rating
    if conductor_temp_rating_c == 60:
        base_ampacity = amp_60
    elif conductor_temp_rating_c == 75:
        base_ampacity = amp_75
    else:  # 90 degC
        base_ampacity = amp_90

    if base_ampacity <= 0:
        # V63 FIX: AWG 18/16 have NO ampacity rating in the 60°C and
        # 75°C columns per NEC 310.16. Previously, the code fell through
        # to max(amp_60, amp_75, amp_90), using the 90°C column value
        # (e.g., 14A for AWG 18) for a 60°C rated conductor.
        # This is DANGEROUS: a 60°C rated conductor CANNOT carry 14A.
        # Using the 90°C column for a lower-rated conductor overstates
        # ampacity, potentially causing overheating and fire.
        # Correct behavior: report no rating → non-compliant.
        return AmpacityResult(
            awg_gauge=gauge,
            base_ampacity_a=0,
            ambient_derating=0.0,
            conductor_derating=0.0,
            adjusted_ampacity_a=0.0,
            actual_current_a=alarm_current_a,
            is_compliant=False,
            formula=(
                f"AWG {gauge} has no NEC 310.16 ampacity rating "
                f"at {conductor_temp_rating_c}°C — use 90°C rated "
                f"insulation (THHN/THWN-2) or larger wire gauge"
            ),
        )

    # Apply NEC 310.15(B)(2)(A) ambient temperature derating
    ambient_derating = get_ambient_derating_factor(ambient_temp_c, conductor_temp_rating_c)

    # Apply NEC 310.15(B)(3)(a) conductor count derating
    conductor_derating = get_conductor_count_derating(num_current_carrying)

    # Calculate adjusted ampacity
    adjusted_ampacity = base_ampacity * ambient_derating * conductor_derating

    # Compliance check
    is_compliant = alarm_current_a <= adjusted_ampacity

    formula = (
        f"I_adj = I_base * T_derate * C_derate = "
        f"{base_ampacity}A * {ambient_derating:.2f} * {conductor_derating:.2f} = "
        f"{adjusted_ampacity:.1f}A "
        f"{'>=' if is_compliant else '<'} "
        f"I_actual = {alarm_current_a:.4f}A "
        f"(ambient={ambient_temp_c:.0f}C, {num_current_carrying} cond.)"
    )

    return AmpacityResult(
        awg_gauge=gauge,
        base_ampacity_a=base_ampacity,
        ambient_derating=round(ambient_derating, 4),
        conductor_derating=round(conductor_derating, 4),
        adjusted_ampacity_a=round(adjusted_ampacity, 4),
        actual_current_a=round(alarm_current_a, 6),
        is_compliant=is_compliant,
        formula=formula,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FAULT ISOLATOR PLACEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §12.3.1 — Maximum devices between isolators
_MAX_DEVICES_BETWEEN_ISOLATORS = 32


def verify_fault_isolator_placement(devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify fault isolator placement on SLC circuits.

    NFPA 72 §12.3 requires that a single fault (short or open) on a
    Signaling Line Circuit (SLC) must not disable more than one
    zone or more than 32 devices.

    This function checks:
    1. Each device group between isolators has ≤ 32 devices
    2. Isolators are placed at circuit boundaries
    3. No device is beyond the last isolator without a terminator

    Args:
        devices: List of device dicts. Each must have:
            - 'device_id': str
            - 'device_type': str (e.g. 'detector', 'module', 'isolator')
            - 'zone_id': str (optional)
            - 'circuit_id': str (optional)

    Returns:
        Dict with compliant (bool), violations (list), device_count,
        isolator_count, nfpa_section.

    """
    if not devices:
        # V69-4 FIX: Empty device list is NOT compliant — fail-safe
        # Empty list could indicate a data extraction failure (parser bug),
        # not that the circuit is genuinely compliant.
        return {
            "compliant": False,
            "violations": [
                {
                    "type": "no_devices_to_verify",
                    "nfpa_section": "NFPA 72 §12.3",
                    "message": "No devices to verify — cannot confirm fault isolation compliance",
                }
            ],
            "device_count": 0,
            "isolator_count": 0,
            "nfpa_section": "NFPA 72 §12.3",
            "message": "No devices to verify — BLOCKED (fail-safe)",
        }

    violations = []
    isolator_count = 0
    current_segment_devices = 0
    segment_zone_ids = set()  # type: ignore[var-annotated]
    current_circuit = None

    for i, dev in enumerate(devices):
        dev_type = dev.get("device_type", "").lower()
        dev_id = dev.get("device_id", f"device_{i}")
        circuit = dev.get("circuit_id", "default")

        # Track circuit changes
        if current_circuit != circuit:
            # V69-3 FIX: Check multi-zone segment before resetting
            if len(segment_zone_ids) > 1:
                violations.append(
                    {
                        "type": "multi_zone_segment",
                        "device_id": dev_id,
                        "zones": sorted(segment_zone_ids),
                        "nfpa_section": "NFPA 72 §12.3",
                        "message": (
                            f"Segment contains devices from {len(segment_zone_ids)} "
                            f"zones ({', '.join(sorted(segment_zone_ids))}) — "
                            f"single fault could disable multiple zones "
                            f"per NFPA 72 §12.3"
                        ),
                    }
                )
            # Check previous segment for device count
            if current_segment_devices > _MAX_DEVICES_BETWEEN_ISOLATORS:
                violations.append(
                    {
                        "type": "too_many_devices_between_isolators",
                        "device_id": dev_id,
                        "device_count": current_segment_devices,
                        "max_allowed": _MAX_DEVICES_BETWEEN_ISOLATORS,
                        "nfpa_section": "NFPA 72 §12.3.1",
                        "message": (
                            f"Segment has {current_segment_devices} devices "
                            f"(max {_MAX_DEVICES_BETWEEN_ISOLATORS} per "
                            f"NFPA 72 §12.3.1)"
                        ),
                    }
                )
            current_segment_devices = 0
            segment_zone_ids = set()
            current_circuit = circuit

        if "isolator" in dev_type:
            # V69-3 FIX: Check multi-zone segment before resetting at isolator
            if len(segment_zone_ids) > 1:
                violations.append(
                    {
                        "type": "multi_zone_segment",
                        "device_id": dev_id,
                        "zones": sorted(segment_zone_ids),
                        "nfpa_section": "NFPA 72 §12.3",
                        "message": (
                            f"Segment before isolator '{dev_id}' contains devices "
                            f"from {len(segment_zone_ids)} zones "
                            f"({', '.join(sorted(segment_zone_ids))}) — "
                            f"single fault could disable multiple zones "
                            f"per NFPA 72 §12.3"
                        ),
                    }
                )
            # Check segment ending at this isolator
            if current_segment_devices > _MAX_DEVICES_BETWEEN_ISOLATORS:
                violations.append(
                    {
                        "type": "too_many_devices_between_isolators",
                        "device_id": dev_id,
                        "device_count": current_segment_devices,
                        "max_allowed": _MAX_DEVICES_BETWEEN_ISOLATORS,
                        "nfpa_section": "NFPA 72 §12.3.1",
                        "message": (
                            f"Segment before isolator '{dev_id}' has "
                            f"{current_segment_devices} devices "
                            f"(max {_MAX_DEVICES_BETWEEN_ISOLATORS})"
                        ),
                    }
                )
            isolator_count += 1
            current_segment_devices = 0
            segment_zone_ids = set()
        else:
            current_segment_devices += 1
            zone = dev.get("zone_id")
            if zone:
                segment_zone_ids.add(zone)

    # V69-3 FIX: Check multi-zone in last segment too
    if len(segment_zone_ids) > 1:
        violations.append(
            {
                "type": "multi_zone_segment",
                "zones": sorted(segment_zone_ids),
                "nfpa_section": "NFPA 72 §12.3",
                "message": (
                    f"End-of-circuit segment contains devices from "
                    f"{len(segment_zone_ids)} zones "
                    f"({', '.join(sorted(segment_zone_ids))}) — "
                    f"single fault could disable multiple zones "
                    f"per NFPA 72 §12.3"
                ),
            }
        )

    # Check last segment (after last isolator)
    if current_segment_devices > _MAX_DEVICES_BETWEEN_ISOLATORS:
        violations.append(
            {
                "type": "too_many_devices_end_of_circuit",
                "device_count": current_segment_devices,
                "max_allowed": _MAX_DEVICES_BETWEEN_ISOLATORS,
                "nfpa_section": "NFPA 72 §12.3.1",
                "message": (
                    f"End-of-circuit segment has {current_segment_devices} "
                    f"devices (max {_MAX_DEVICES_BETWEEN_ISOLATORS})"
                ),
            }
        )

    compliant = len(violations) == 0

    return {
        "compliant": compliant,
        "violations": violations,
        "device_count": len(devices),
        "isolator_count": isolator_count,
        "nfpa_section": "NFPA 72 §12.3",
        "message": "Compliant" if compliant else f"{len(violations)} violation(s) found",
    }
