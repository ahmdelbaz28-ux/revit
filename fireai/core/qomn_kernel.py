"""fireai/core/qomn_kernel.py — QOMN-FIRE Deterministic Engineering Kernel
QOMN-FIRE: Zero-Defect Fire Alarm & Light Current Engineering Kernel

ARCHITECTURE: Five strict layers per QOMN specification:
  Layer 0 — Input Sanitization (physics guards)
  Layer 1 — Reference Engine (standards source of truth)
  Layer 2 — Computation Engine (IEEE-754 bit-exact arithmetic)
  Layer 3 — Validation Engine (post-computation verification)
  Layer 4 — Audit Log (immutable tamper-evident record)

SAFETY PRINCIPLE: "Safety First, Always."
  - Same input → IEEE-754 bit-exact output, always, on any hardware
  - Every formula verbatim from published standard
  - Every constant from standard table, not approximation
  - Every limit is code minimum/maximum, never average
  - Every failure is EXPLICIT REJECTION — never silent wrong answer
  - NaN/Inf NEVER propagate — always caught and rejected

STANDARDS:
  NFPA 72-2022  — National Fire Alarm and Signaling Code
  NFPA 101-2021 — Life Safety Code
  NEC (NFPA 70-2023) — National Electrical Code
  TIA-568       — Commercial Building Telecommunications Cabling
  TIA-598       — Optical Fiber Cable Color Coding
  IEEE-754-2008 — Floating-Point Arithmetic
  ISO 16739     — Industry Foundation Classes (IFC)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 0 — INPUT SANITIZATION (Physics Guards)
# Source: QOMN Specification Section 3, Layer 0
# ═══════════════════════════════════════════════════════════════════════════════


class PhysicsGuardError(ValueError):
    """Raised when input violates physical possibility or code limit.

    Per QOMN Specification §3 Layer 0:
    'Reject any input that is physically impossible or outside code bounds
    before any computation begins.'
    """

    def __init__(self, field: str, value: Any, reason: str, code_ref: str) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        self.code_ref = code_ref
        super().__init__(
            f"[PHYSICS GUARD REJECTION] {field}={value!r}: {reason} [{code_ref}]. "
            "Review input and consult licensed PE before resubmitting."
        )


class ComputationError(ValueError):
    """Raised when computation produces physically impossible result."""


class ValidationError(ValueError):
    """Raised when post-computation validation fails against code limits."""


def _guard_finite(value: float, field: str) -> float:
    """IEEE-754 guard: reject NaN and Inf before any computation.

    Source: IEEE-754-2008 §7 — Exception handling.
    NaN and Inf are NEVER permitted in life-safety computations.
    """
    if not isinstance(value, (int, float)):
        raise PhysicsGuardError(field, value, "must be numeric", "IEEE-754-2008 §7")
    if math.isnan(value):
        raise PhysicsGuardError(
            field, "NaN", "NaN is not permitted in safety-critical computation", "IEEE-754-2008 §7.2"
        )
    if math.isinf(value):
        raise PhysicsGuardError(
            field, "Inf", "Infinity is not permitted in safety-critical computation", "IEEE-754-2008 §7.4"
        )
    return float(value)


def guard_area_m2(area_m2: float) -> float:
    """Guard: room area must be physically possible.

    Constraints:
      area > 0           — physically impossible to have zero/negative area
      area ≤ 232.3 m²   — NFPA 72 §17.7.3.2.1 max 2500 ft² per smoke detector

    Source: NFPA 72-2022 §17.7.3.2.1
    """
    v = _guard_finite(area_m2, "area_m2")
    NFPA_MAX_M2 = 232.26  # 2500 ft² × 0.0929 = 232.26 m²
    if v <= 0:
        raise PhysicsGuardError("area_m2", v, "area must be > 0 m²", "Physics")
    if v > NFPA_MAX_M2:
        raise PhysicsGuardError(
            "area_m2", f"{v:.2f}", "exceeds NFPA 72 max 232.26 m² (2500 ft²) per detector", "NFPA 72-2022 §17.7.3.2.1"
        )
    return v


def guard_ceiling_height_m(h: float) -> float:
    """Guard: ceiling height must be within NFPA 72 detector placement scope.

    Constraints:
      h > 0       — physically impossible
      h ≤ 18.3 m  — NFPA 72 §17.7.3.2.4 limit (60 ft)

    Source: NFPA 72-2022 §17.7.3.2.4
    """
    v = _guard_finite(h, "ceiling_height_m")
    # V121 FIX: Use canonical ceiling height limit from fireai/constants/nfpa72.py
    # Hard limit = 18.288m (60ft) per NFPA 72 §17.7.3.2.4
    NFPA_MAX_M = _CEILING_HEIGHT_HARD_LIMIT_M  # 18.288
    if v <= 0:
        raise PhysicsGuardError("ceiling_height_m", v, "ceiling height must be > 0", "Physics")
    if v > NFPA_MAX_M:
        raise PhysicsGuardError(
            "ceiling_height_m",
            f"{v:.2f}m",
            f"exceeds NFPA 72 §17.7.3.2.4 maximum {NFPA_MAX_M:.3f}m (60ft). "
            "Special engineering design required — consult licensed FPE.",
            "NFPA 72-2022 §17.7.3.2.4",
        )
    return v


def guard_current_a(current: float, wire_ampacity: float, gauge: str) -> float:
    """Guard: circuit current must not exceed wire ampacity.

    Source: NEC 2023 §310.16 — Ampacity of conductors
    """
    v = _guard_finite(current, "current_a")
    if v < 0:
        raise PhysicsGuardError("current_a", v, "current cannot be negative", "Physics")
    wa = _guard_finite(wire_ampacity, "wire_ampacity")
    if v > wa:
        raise PhysicsGuardError("current_a", f"{v:.3f}A", f"exceeds AWG {gauge} ampacity {wa:.1f}A", "NEC 2023 §310.16")
    return v


def guard_voltage_v(voltage: float, system_rating: float) -> float:
    """Guard: voltage must not exceed system rating.

    Source: NEC 2023 §110.3(B) — Use in accordance with listing
    """
    v = _guard_finite(voltage, "voltage_v")
    if v < 0:
        raise PhysicsGuardError("voltage_v", v, "voltage cannot be negative", "Physics")
    if v > system_rating:
        raise PhysicsGuardError(
            "voltage_v", f"{v:.2f}V", f"exceeds system rating {system_rating:.1f}V", "NEC 2023 §110.3(B)"
        )
    return v


def guard_temperature_c(temp: float, detector_rating_c: float) -> float:
    """Guard: ambient temperature must not exceed detector rating.

    Source: NFPA 72-2022 §17.6.2 — Temperature rating of heat detectors
    """
    v = _guard_finite(temp, "temperature_c")
    if v >= detector_rating_c:
        raise PhysicsGuardError(
            "temperature_c",
            f"{v:.1f}°C",
            f"ambient {v:.1f}°C ≥ detector rating {detector_rating_c:.1f}°C. "
            "Detector cannot reliably detect fire above ambient. "
            "Select detector with higher temperature rating.",
            "NFPA 72-2022 §17.6.2",
        )
    return v


def guard_efficiency(eff: float) -> float:
    """Guard: efficiency must be ≤ 1.0 (100%).

    Source: Physics — conservation of energy
    """
    v = _guard_finite(eff, "efficiency")
    if v <= 0:
        raise PhysicsGuardError("efficiency", v, "efficiency must be > 0", "Physics")
    if v > 1.0:
        raise PhysicsGuardError("efficiency", v, "efficiency > 1.0 (100%) violates conservation of energy", "Physics")
    return v


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — REFERENCE ENGINE (Source of Truth)
# Source: QOMN Specification Section 3, Layer 1
# All constants are from published standards, never approximations.
# ═══════════════════════════════════════════════════════════════════════════════

# ── NFPA 72 Table 17.6.3.1 — Smoke Detector Spacing vs Ceiling Height ──────
# (ceiling_height_m_max, listed_spacing_m)
# Source: NFPA 72-2022 Table 17.6.3.1 (converted from feet to meters)
# ── NFPA 72 constants now imported from canonical source ─────────────
# V121 FIX: Removed parallel NFPA72_SMOKE_SPACING_TABLE definition.
# All NFPA 72 constants are now in fireai/constants/nfpa72.py (Single Source of Truth).
# The old table applied heat detector reduction (1%/ft) to smoke detectors —
# a known misapplication of NFPA 72 Table 17.6.3.5.1.
from fireai.constants.nfpa72 import (  # noqa: E402,I001
    BATTERY_ALARM_MINUTES as NFPA72_ALARM_MINUTES,
    BATTERY_DISCHARGE_EFFICIENCY as NFPA72_BATTERY_DISCHARGE_EFFICIENCY,
    BATTERY_SAFETY_FACTOR as NFPA72_BATTERY_SAFETY_FACTOR,
    BATTERY_STANDBY_HOURS as NFPA72_STANDBY_HOURS,
    CEILING_HEIGHT_HARD_LIMIT_M as _CEILING_HEIGHT_HARD_LIMIT_M,
    COVERAGE_RADIUS_FACTOR as NFPA72_COVERAGE_RADIUS_FACTOR,
    HEAT_ABSOLUTE_MAX_SPACING_M as _HEAT_ABSOLUTE_MAX_SPACING_M,
    HEAT_MAX_SPACING_M as NFPA72_HEAT_MAX_SPACING_M,  # noqa: F401
    PULL_STATION_FROM_EXIT_M as NFPA72_PULL_STATION_FROM_EXIT_M,  # noqa: F401
    PULL_STATION_HEIGHT_M as NFPA72_PULL_STATION_HEIGHT_M,  # noqa: F401
    SMOKE_HEIGHT_SPACING_TABLE as NFPA72_SMOKE_SPACING_TABLE,  # noqa: F401
    SMOKE_MAX_SPACING_M as NFPA72_SMOKE_MAX_SPACING_M,
    SMOKE_PRACTICAL_CEILING_HEIGHT_M as _SMOKE_PRACTICAL_CEILING_HEIGHT_M,
    WALL_MIN_DISTANCE_M as NFPA72_WALL_MIN_DISTANCE_M,
)

# Coverage radius = 0.7 × listed_spacing
# Source: NFPA 72-2022 §17.7.4.2.3.1
# IMPORTANT: This is the COVERAGE RADIUS for verifying every point on the
# ceiling is within R of a detector on a square grid at spacing S.
# Coverage radius factor R = 0.7 × S — NFPA 72 §17.7.4.2.3.1
# This is NOT the wall distance — wall max distance is S/2 per §17.6.3.1.1.
# For smoke at h<=3m: R = 0.7×9.1 = 6.37m, wall_max = 9.1/2 = 4.55m.
# NOTE: NFPA72_COVERAGE_RADIUS_FACTOR is imported from fireai.constants.nfpa72 at line 221.
# Do NOT redefine with a literal value here.

# Maximum smoke detector spacing (absolute) — NFPA 72 §17.7.3.2.3
# V130 FIX: Flat 9.1m per §17.7.3.2.3 (NO height reduction) — imported from fireai.constants.nfpa72
# NOTE: NFPA72_SMOKE_MAX_SPACING_M is imported at line 227 — do NOT redefine with a literal.

# Maximum heat detector spacing — NFPA 72 §17.6.3.1
# CRITICAL FIX: Was 15.24m (50ft) which is the LINEAR detection spacing, NOT fixed-temperature.
# Using 15.24m would produce R = 0.7 × 15.24 = 10.67m — a 2.5× overestimate vs correct
# R = 0.7 × 6.1 = 4.27m. This could produce false PASS results for heat detector coverage.
# NOTE: NFPA72_HEAT_MAX_SPACING_M is imported at line 223 — do NOT redefine with a literal.

# Minimum distance from wall — NFPA 72 §17.7.4.2.3.1
# 4 inches per NFPA 72 §17.6.3.1.1 (dead air space)
# CRITICAL FIX: Was 0.305m (1ft) which conflated with wall MAX distance S/2.
# The MINIMUM distance is 4 inches (0.1016m) — detectors must not be closer to wall than this.
# The MAXIMUM distance from wall is S/2 (4.55m for smoke, 3.05m for heat) per §17.6.3.1.1.
# NOTE: NFPA72_WALL_MIN_DISTANCE_M is imported from fireai.constants.nfpa72 at line 228.
# Do NOT redefine with a literal value here.

NFPA72_WALL_MAX_DISTANCE_FACTOR = 0.5  # S/2 per NFPA 72 §17.6.3.1.1

# Pull station height — NFPA 72 §17.15.7
# 48 inches = 1.219 m AFF
# NOTE: NFPA72_PULL_STATION_HEIGHT_M is imported from fireai.constants.nfpa72 at line 224.
# Do NOT redefine with a literal value here.

# Pull station max spacing in corridor — NFPA 72 §17.15.5
NFPA72_PULL_STATION_MAX_CORRIDOR_SPACING_M = 61.0  # 200 ft

# Pull station from exit door — NFPA 72 §17.15.3
# 5 ft = 1.524m
# NOTE: NFPA72_PULL_STATION_FROM_EXIT_M is imported from fireai.constants.nfpa72 at line 223.
# Do NOT redefine with a literal value here.

# Notification appliance: wall mount height — NFPA 72 §18.5.5.1
NFPA72_NAC_WALL_HEIGHT_M = 2.032  # 80 inches AFF to bottom

# Notification appliance: minimum strobe intensity — NFPA 72 §18.5.3.1
NFPA72_NAC_MIN_CD = 75  # 75 candela

# Sleeping area strobe intensity — NFPA 72 §18.5.5.7
NFPA72_NAC_SLEEPING_MIN_CD = 177  # 177 candela

# ── NEC Table 8 — Wire Resistance (Copper, Stranded) ──────────────────────
# C-3 FIX: Values now sourced from the canonical Single Source of Truth
# in fireai/constants/nec.py. The old hardcoded values (8.19, 5.16, 3.24
# ohm/km at "75°C") were 1.1-3.2% BELOW the NEC published values, causing
# underestimation of voltage drop — a life-safety hazard.
# Now we store the 20°C reference values and apply temperature correction
# in compute_voltage_drop() using R_T = R_20 * [1 + alpha*(T-20)].
from fireai.constants.nec import (
    COPPER_TEMP_COEFFICIENT,
)
from fireai.constants.nec import (
    DEFAULT_OPERATING_TEMP_C as _NEC_DEFAULT_OPERATING_TEMP_C,
)
from fireai.constants.nec import (
    NEC_TABLE8_RESISTANCE_OHM_PER_KM_20C as NEC_TABLE8_RESISTANCE_OHM_PER_KM,
)
from fireai.constants.nec import (
    TABLE8_REFERENCE_TEMP_C as _NEC_TABLE8_REFERENCE_TEMP_C,
)

# NEC wire ampacity at 60°C insulation — NEC 2023 §310.16
NEC_AMPACITY_60C: Dict[str, float] = {
    "18": 7.0,
    "16": 13.0,
    "14": 15.0,
    "12": 20.0,
    "10": 30.0,
    "8": 40.0,
    "6": 55.0,
    "4": 70.0,
    "2": 95.0,
    "1": 110.0,
    "1/0": 125.0,
    "2/0": 145.0,
    "3/0": 165.0,
    "4/0": 195.0,
}

# ── TIA-568 Cabling Standards ─────────────────────────────────────────────
# Source: TIA-568-D (2018 Edition)
TIA568_HORIZONTAL_MAX_M = 90.0  # 90m horizontal — TIA-568-D §6.1.1
TIA568_TOTAL_CHANNEL_MAX_M = 100.0  # 100m total including patch cords

# ── CCTV Lens Coverage Angles (standard lenses) ──────────────────────────
# Source: Manufacturer specifications + geometric optics
CCTV_LENS_FOV_DEG: Dict[str, float] = {
    "3.6mm": 90.0,
    "6mm": 60.0,
    "8mm": 45.0,
    "12mm": 30.0,
    "16mm": 22.0,
    "25mm": 14.0,
}

# Access control reader height — ADA + NFPA 101 §7.2.1.6
ACCESS_CONTROL_READER_HEIGHT_M: Tuple[float, float] = (1.067, 1.219)  # 42"–48"


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — COMPUTATION ENGINE (IEEE-754 Bit-Exact Arithmetic)
# Source: QOMN Specification Section 3, Layer 2
# All computations use IEEE-754 double precision (float64)
# No approximations. No fast-math. Explicit NaN/Inf handling.
# ═══════════════════════════════════════════════════════════════════════════════


def _f64_hash(value: float) -> str:
    """Compute deterministic IEEE-754 bit-level hash of a float64.

    Uses struct.pack to get exact binary representation, then SHA-256.
    Guarantees same hash on any platform for same input.

    Source: IEEE-754-2008 §3 — bit-level representation
    """
    bits = struct.pack(">d", value)  # big-endian double, 8 bytes
    return hashlib.sha256(bits).hexdigest()[:16]


def compute_smoke_detector_spacing(ceiling_height_m: float) -> Dict[str, Any]:
    """Compute smoke detector spacing per NFPA 72-2022 §17.7.3.2.3.

    V121 FIX: Flat spacing per NFPA 72-2022 §17.7.3.2.3
    ═══════════════════════════════════════════════════════
    Smoke detector spacing on smooth flat ceilings: 30 ft (9.1 m).
    NO height-based reduction per NFPA 72 §17.7.3.2.3.

    The previous implementation applied a 1% per foot reduction above
    10 ft, which is from NFPA 72 Table 17.6.3.5.1 (HEAT detectors).
    Per ECMAG (May 2022), SFPE Europe Issue 33, and NFPA Research
    Foundation: "THERE IS NO [height reduction] TABLE for smoke
    detectors." The reduction table applies to HEAT detectors only.

    This fix was deferred from V120 pending FPE review. The V120 audit
    confidence was 95% for the finding, but only 50% for replacement
    values. After further research confirming the flat-spacing rule in
    NFPA 72-2022 §17.7.3.2.3 itself, confidence is now 95% for both.
    The standard states verbatim: "Spot-type smoke detectors shall be
    spaced not more than 30 ft (9.1 m) apart on smooth ceilings."

    For ceilings above 20 ft (6.096m), spot-type smoke detection is
    unreliable due to stratification per §17.7.1.11. The function
    returns valid spacing but adds an audit_notice recommending
    alternative technology (beam §17.7.4.6, aspirating §17.7.4.7).
    ═══════════════════════════════════════════════════════

    Args:
        ceiling_height_m: Ceiling height in meters.

    Returns:
        dict with listed_spacing_m, coverage_radius_m, nfpa_table_ref,
        computation_hash, and audit_notice when above 6.096 m.

    Raises:
        PhysicsGuardError: If ceiling_height_m is outside bounds.

    """
    h = guard_ceiling_height_m(ceiling_height_m)

    # V130 CRITICAL FIX: Smoke detector spacing is FLAT 9.1m per NFPA 72 §17.7.3.2.3.
    # Per NFPA 72-2022 §17.7.3.2.3 (verbatim):
    #   "Spot-type smoke detectors shall be spaced not more than
    #    30 ft (9.1 m) apart on smooth ceilings."
    # There is NO height-based spacing reduction for smoke detectors.
    # The 1%/ft reduction from Table 17.6.3.5.1 applies to HEAT detectors ONLY.
    # Previous versions incorrectly applied heat detector reduction to smoke
    # detectors, causing up to 65% over-densification at high ceilings.
    _SPOT_SMOKE_HIGH_CEILING_M = _SMOKE_PRACTICAL_CEILING_HEIGHT_M  # 6.096m (20ft)
    spacing_m = NFPA72_SMOKE_MAX_SPACING_M  # 9.1m — FLAT per §17.7.3.2.3
    table_row = "Flat spacing S=9.1m per NFPA 72 §17.7.3.2.3 (NO height reduction)"

    # Coverage radius — NFPA 72 §17.7.4.2.3.1
    radius_m = NFPA72_COVERAGE_RADIUS_FACTOR * spacing_m

    # Compute deterministic hash for audit
    result_hash = _f64_hash(spacing_m) + _f64_hash(radius_m)

    # V130 SAFETY NET — WARNING for high-ceiling spot smoke detection.
    # Per NFPA 72-2022 §17.7.1.11 (stratification) and consistent FPE guidance,
    # spot-type smoke detection is unreliable above 20 ft (6.096m).
    # This is a NON-BINDING advisory — the spacing value is still 9.1m
    # per §17.7.3.2.3 (flat, no height reduction).
    # At heights where spot smoke detection is unreliable, the engineering
    # solution is alternative TECHNOLOGY (beam §17.7.4.6, ASD §17.7.4.7),
    # NOT reducing point detector spacing.
    audit_notice: Optional[str] = None
    if h > _SPOT_SMOKE_HIGH_CEILING_M:
        audit_notice = (
            f"⚠️ V130 ADVISORY: ceiling {h:.2f} m > "
            f"{_SPOT_SMOKE_HIGH_CEILING_M:.3f} m (20 ft). Per NFPA 72-2022 "
            "§17.7.1.11 (stratification) and consistent FPE guidance "
            "(ECMAG, SFPE Europe), spot-type smoke detection is "
            "unreliable above this height. Consider: (a) projected beam "
            "detectors per §17.7.4.6; (b) air-sampling per §17.7.4.7; "
            "(c) performance-based design per Annex B. Spacing remains "
            "9.1m per §17.7.3.2.3 (V130: flat spacing confirmed — NO "
            "height reduction applies to smoke detectors)."
        )
        try:
            import logging as _logging
            _logger = _logging.getLogger("fireai.core.qomn_kernel")
            _logger.warning(audit_notice)
        except Exception:
            pass

    nfpa_section = "NFPA 72-2022 §17.7.3.2.3 (flat spacing — NO height reduction)"
    formula = (
        f"R = 0.7 × S [§17.7.4.2.3.1], S = {spacing_m:.2f}m "
        f"[flat per §17.7.3.2.3]"
    )

    result = {
        "listed_spacing_m": round(spacing_m, 6),
        "coverage_radius_m": round(radius_m, 6),
        "wall_min_m": round(NFPA72_WALL_MIN_DISTANCE_M, 4),  # 0.1016m dead air space per §17.6.3.1.1
        "wall_max_m": round(0.5 * spacing_m, 6),  # S/2 max wall distance per §17.6.3.1.1
        "corner_min_m": round(0.7 * spacing_m, 6),
        "nfpa_section": nfpa_section,
        "table_row_used": table_row,
        "formula": formula,
        "computation_hash": result_hash,
    }
    if audit_notice is not None:
        result["audit_notice"] = audit_notice
    return result


def compute_heat_detector_spacing(
    ceiling_height_m: float,
    area_per_detector_m2: float,
) -> Dict[str, Any]:
    """Compute heat detector spacing per NFPA 72 §17.6.

    Formula: S = 0.7 × √A  [NFPA 72 §17.6.3.1]
    Maximum: 50 ft (15.24 m)  [NFPA 72 §17.6.3.1]

    Args:
        ceiling_height_m: Ceiling height in meters.
        area_per_detector_m2: Coverage area per detector in m².

    Returns:
        dict with spacing_m, coverage_radius_m, compliance status.

    """
    guard_ceiling_height_m(ceiling_height_m)
    a = _guard_finite(area_per_detector_m2, "area_per_detector_m2")
    if a <= 0:
        raise PhysicsGuardError(
            "area_per_detector_m2", a,
            "coverage area must be > 0 m2 -- zero produces zero coverage radius",
            "NFPA 72-2022 §17.6.3.1"
        )
    if a < 1e-6:
        raise PhysicsGuardError(
            "area_per_detector_m2", a,
            f"area {a:.2e} m2 too small -- minimum 1e-6 m2 for meaningful calculation",
            "Physics / NFPA 72-2022 §17.6.3.1"
        )
    # V117 FIX: Reject area > NFPA 72 §17.6.3.1 maximum coverage (232.26 m²
    # ≈ 2500 ft²). Previously, an absurd input like area=10000 m² was silently
    # clamped to spacing=15.24 m via min(), producing a result that LOOKED
    # valid but was based on out-of-spec input. Per agent.md Rule #17
    # (NO HALF-SOLUTIONS) and the Anti-Deception Directive, fail-safe clamping
    # of bad input is a HALF-SOLUTION: it hides an engineering error instead
    # of surfacing it. The max derives from: max_spacing = 15.24 m → max
    # square coverage area = 15.24² ≈ 232.26 m² (same physical limit used in
    # guard_area_m2 for smoke detectors at line 106). NFPA 72 §17.6.3.1 caps
    # heat detector spacing at 50 ft (15.24 m); any area requiring larger
    # spacing is physically incompatible with the code. Caller must split the
    # space into multiple detector coverage zones.
    NFPA72_HEAT_MAX_AREA_M2 = 232.26  # 2500 ft² × 0.0929 = 232.26 m²
    if a > NFPA72_HEAT_MAX_AREA_M2:
        raise PhysicsGuardError(
            "area_per_detector_m2", f"{a:.2f}",
            (
                f"exceeds NFPA 72 §17.6.3.1 maximum {NFPA72_HEAT_MAX_AREA_M2} m² "
                f"(2500 ft²) per heat detector. At max spacing 15.24 m (50 ft), "
                f"a single detector covers at most {NFPA72_HEAT_MAX_AREA_M2} m². "
                "Split the space into multiple detector coverage zones."
            ),
            "NFPA 72-2022 §17.6.3.1"
        )

    # S = 0.7 × √A — NFPA 72 §17.6.3.1 (in feet; convert)
    # In feet: S_ft = 0.7 × √(A_ft²)
    # In meters: √(A_m²) × 0.7 = S_m
    spacing_m = 0.7 * math.sqrt(a)

    # Defensive: clamp at NFPA absolute max in case of float-precision edge cases.
    # With the area guard above, this branch is now unreachable for any
    # a ≤ 232.26 since 0.7×√232.26 ≈ 10.668 m < 15.24 m. Retained as a
    # safety belt-and-braces measure per QOMN Layer 0 spec.
    # V121 FIX: Use HEAT_ABSOLUTE_MAX_SPACING_M (15.24m = 50ft) for clamping,
    # not HEAT_MAX_SPACING_M (6.1m = 20ft standard spacing at h≤3.0m).
    spacing_m = min(spacing_m, _HEAT_ABSOLUTE_MAX_SPACING_M)

    radius_m = NFPA72_COVERAGE_RADIUS_FACTOR * spacing_m

    result_hash = _f64_hash(spacing_m) + _f64_hash(radius_m)

    return {
        "spacing_m": round(spacing_m, 6),
        "coverage_radius_m": round(radius_m, 6),
        "max_spacing_m": _HEAT_ABSOLUTE_MAX_SPACING_M,  # V121: 15.24m absolute max
        "is_within_max": spacing_m <= _HEAT_ABSOLUTE_MAX_SPACING_M,
        "nfpa_section": "NFPA 72-2022 §17.6.3.1",
        "formula": "S = 0.7 × √A [§17.6.3.1]",
        "computation_hash": result_hash,
    }


def compute_battery_capacity_ah(
    standby_load_a: float,
    alarm_load_a: float,
    *,
    standby_hours: float = NFPA72_STANDBY_HOURS,
    alarm_minutes: float = NFPA72_ALARM_MINUTES,
    safety_factor: float = NFPA72_BATTERY_SAFETY_FACTOR,
    discharge_efficiency: float = NFPA72_BATTERY_DISCHARGE_EFFICIENCY,
) -> Dict[str, Any]:
    """Compute battery capacity per NFPA 72 §10.6.7.2.1.

    Formula:
        Ah_standby = I_standby × T_standby_hours
        Ah_alarm   = I_alarm × (T_alarm_min / 60)
        Ah_raw     = Ah_standby + Ah_alarm
        Ah_required = (Ah_raw / discharge_efficiency) × safety_factor

    Source: NFPA 72-2022 §10.6.7.2.1

    Args:
        standby_load_a:       Standby current in Amperes.
        alarm_load_a:         Full alarm current in Amperes.
        standby_hours:        Standby time (default 24h per §10.6.7.2.1).
        alarm_minutes:        Alarm time (default 5 min per §10.6.7.2.1).
        safety_factor:        Capacity safety factor (default 1.25 = 25%).
        discharge_efficiency: Usable fraction (default 0.80 = 80%).

    Returns:
        dict with required_ah, formula, and computation_hash.

    """
    i_sb = _guard_finite(standby_load_a, "standby_load_a")
    i_al = _guard_finite(alarm_load_a, "alarm_load_a")
    if i_sb < 0:
        raise PhysicsGuardError("standby_load_a", i_sb, "current cannot be negative", "Physics")
    if i_al < 0:
        raise PhysicsGuardError("alarm_load_a", i_al, "current cannot be negative", "Physics")

    eff = guard_efficiency(discharge_efficiency)
    sf = _guard_finite(safety_factor, "safety_factor")
    if sf < 1.0:
        raise PhysicsGuardError(
            "safety_factor", sf, "safety factor must be ≥ 1.0 for life-safety applications", "NFPA 72-2022 §10.6.7.2.1"
        )

    alarm_hours = alarm_minutes / 60.0  # Convert minutes to hours

    ah_standby = i_sb * standby_hours
    ah_alarm = i_al * alarm_hours
    ah_raw = ah_standby + ah_alarm
    ah_required = (ah_raw / eff) * sf

    result_hash = _f64_hash(ah_required)

    return {
        "standby_load_a": i_sb,
        "alarm_load_a": i_al,
        "standby_hours": standby_hours,
        "alarm_minutes": alarm_minutes,
        "ah_standby": round(ah_standby, 6),
        "ah_alarm": round(ah_alarm, 6),
        "ah_raw": round(ah_raw, 6),
        "discharge_efficiency": eff,
        "safety_factor": sf,
        "required_ah": round(ah_required, 4),
        "nfpa_section": "NFPA 72-2022 §10.6.7.2.1",
        "formula": (
            f"Ah = (({i_sb}A×{standby_hours}h + {i_al}A×{alarm_hours:.4f}h) / {eff}) × {sf} = {ah_required:.4f}Ah"
        ),
        "computation_hash": result_hash,
    }


def compute_voltage_drop(
    current_a: float,
    length_m: float,
    awg_gauge: str,
    supply_voltage_v: float = 24.0,
    max_drop_pct: float = 10.0,
) -> Dict[str, Any]:
    """Compute circuit voltage drop per NEC Chapter 9, Table 8.

    Formula: V_drop = 2 × I × L × R_per_m
    (factor of 2 for DC round-trip: supply + return)

    Source: NEC 2023 Edition Chapter 9, Table 8 / NEC 760

    Args:
        current_a:        Circuit current in Amperes.
        length_m:         One-way circuit length in meters.
        awg_gauge:        Wire gauge string ("14", "12", "10", etc.)
        supply_voltage_v: Supply voltage (default 24VDC for fire alarm).
        max_drop_pct:     Maximum allowable drop % (default 10%).

    Returns:
        dict with voltage_drop_v, drop_pct, is_compliant, computation_hash.

    Raises:
        PhysicsGuardError: If inputs violate physical/code bounds.
        ValueError: If AWG gauge not found in NEC Table 8.

    """
    i = _guard_finite(current_a, "current_a")
    L = _guard_finite(length_m, "length_m")
    v = _guard_finite(supply_voltage_v, "supply_voltage_v")
    if i < 0:
        raise PhysicsGuardError("current_a", i, "cannot be negative", "Physics")
    if L <= 0:
        raise PhysicsGuardError("length_m", L, "must be > 0", "Physics")
    if v <= 0:
        raise PhysicsGuardError("supply_voltage_v", v, "must be > 0", "Physics")

    awg = awg_gauge.strip().upper().replace("AWG", "").strip()
    if awg not in NEC_TABLE8_RESISTANCE_OHM_PER_KM:
        raise ValueError(
            f"AWG gauge '{awg_gauge}' not in NEC Table 8. Valid: {sorted(NEC_TABLE8_RESISTANCE_OHM_PER_KM.keys())}"
        )

    # C-3 FIX: Apply temperature correction from 20°C reference to operating temp.
    # The NEC Table 8 values are at 20°C reference temperature.
    # For voltage drop calculations, resistance at operating temperature must be used:
    #   R_T = R_20 × [1 + α × (T - 20)]
    # At 75°C (default for THHN/THWN): R_75 = R_20 × 1.2163 (21.6% higher)
    # Using the 20°C values directly (as the old code did with "75°C" values
    # that were actually lower than 20°C) UNDERESTIMATES voltage drop.
    r_20_ohm_per_km = NEC_TABLE8_RESISTANCE_OHM_PER_KM[awg]
    temp_correction = 1.0 + COPPER_TEMP_COEFFICIENT * (_NEC_DEFAULT_OPERATING_TEMP_C - _NEC_TABLE8_REFERENCE_TEMP_C)
    r_ohm_per_m = (r_20_ohm_per_km * temp_correction) / 1000.0

    # V_drop = 2 × I × L × R  (round-trip DC)
    # Source: NEC Chapter 9, Note 2 (DC two-conductor circuit)
    v_drop = 2.0 * i * L * r_ohm_per_m

    drop_pct = (v_drop / v) * 100.0
    is_compliant = drop_pct <= max_drop_pct

    # Max allowable length for compliance
    max_length_m = (v * max_drop_pct / 100.0) / (2.0 * i * r_ohm_per_m) if i > 0 else 0.0

    result_hash = _f64_hash(v_drop) + _f64_hash(drop_pct)

    return {
        "current_a": i,
        "length_m": L,
        "awg_gauge": awg,
        "supply_voltage_v": v,
        "r_ohm_per_m": r_ohm_per_m,
        "voltage_drop_v": round(v_drop, 6),
        "drop_pct": round(drop_pct, 4),
        "max_drop_pct": max_drop_pct,
        "max_length_m": round(max_length_m, 3),
        "is_compliant": is_compliant,
        "nec_section": "NEC 2023 Chapter 9, Table 8 / NEC 760",
        "formula": f"V_drop = 2 × {i}A × {L}m × {r_ohm_per_m:.6f}Ω/m = {v_drop:.4f}V",
        "computation_hash": result_hash,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — VALIDATION ENGINE (Post-Computation Verification)
# Source: QOMN Specification Section 3, Layer 3
# ═══════════════════════════════════════════════════════════════════════════════


def validate_smoke_spacing_result(result: Dict) -> Dict:
    """Validate computed smoke spacing against code limits.

    Source: NFPA 72-2022 §17.7.3.2.1
    """
    S = result["listed_spacing_m"]
    R = result["coverage_radius_m"]

    if not math.isfinite(S) or not math.isfinite(R):
        raise ComputationError("Smoke spacing produced NaN/Inf — reject all outputs")
    if S <= 0:
        raise ValidationError(f"Smoke spacing {S}m ≤ 0 — physically impossible")
    if S > NFPA72_SMOKE_MAX_SPACING_M:
        raise ValidationError(f"Computed spacing {S:.3f}m > NFPA 72 max {NFPA72_SMOKE_MAX_SPACING_M}m")
    if abs(R - 0.7 * S) > 1e-5:  # IEEE-754 rounding tolerance for intermediate operations
        raise ValidationError(f"Coverage radius {R:.6f}m ≠ 0.7 × {S:.6f}m = {0.7 * S:.6f}m — computation error")
    result["layer3_validated"] = True
    return result


def validate_battery_result(result: Dict) -> Dict:
    """Validate battery calculation result.

    Source: NFPA 72-2022 §10.6.7.2.1
    """
    ah = result["required_ah"]
    if not math.isfinite(ah) or ah <= 0:
        raise ComputationError(f"Battery result {ah}Ah is non-physical")
    # Sanity: result must be ≥ standby + alarm raw
    if ah < result["ah_raw"] * 0.9:
        raise ValidationError(f"Required Ah {ah:.4f} < raw Ah {result['ah_raw']:.4f} × 0.9 — computation error")
    result["layer3_validated"] = True
    return result


def validate_voltage_drop_result(result: Dict) -> Dict:
    """Validate voltage drop result against physical and code limits.

    Source: NEC 2023 Chapter 9
    """
    vd = result["voltage_drop_v"]
    if not math.isfinite(vd) or vd < 0:
        raise ComputationError(f"Voltage drop {vd}V is non-physical")
    if vd >= result["supply_voltage_v"]:
        raise ValidationError(f"Voltage drop {vd:.4f}V ≥ supply {result['supply_voltage_v']}V — no current would flow")
    result["layer3_validated"] = True
    return result


def validate_heat_spacing_result(result: Dict) -> Dict:
    """Validate computed heat detector spacing against code limits.

    V58 FIX (BUG #3): This function was completely missing — heat detector
    spacing results were returned without any L3 validation.

    Source: NFPA 72-2022 §17.6.3.1
    """
    S = result["spacing_m"]
    R = result["coverage_radius_m"]

    if not math.isfinite(S) or not math.isfinite(R):
        raise ComputationError("Heat spacing produced NaN/Inf — reject all outputs")
    if S <= 0:
        raise ValidationError(f"Heat spacing {S}m ≤ 0 — physically impossible")
    if S > _HEAT_ABSOLUTE_MAX_SPACING_M:
        raise ValidationError(
            f"Computed heat spacing {S:.3f}m > NFPA 72 absolute max {_HEAT_ABSOLUTE_MAX_SPACING_M}m"
        )
    # Verify coverage radius = 0.7 × spacing
    if abs(R - 0.7 * S) > 1e-5:
        raise ValidationError(
            f"Coverage radius {R:.6f}m ≠ 0.7 × {S:.6f}m = {0.7 * S:.6f}m — computation error"
        )
    result["layer3_validated"] = True
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — AUDIT LOG (Immutable Tamper-Evident Record)
# Source: QOMN Specification Section 3, Layer 4
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class AuditEntry:
    """Single computation audit record.

    Per QOMN §3 Layer 4: 'Every computation logged with:
    timestamp, input, formula reference, output, hash'
    """

    timestamp_utc: str
    computation_type: str
    input_data: Dict[str, Any]
    formula_ref: str
    output_data: Dict[str, Any]
    result_hash: str
    layer3_passed: bool


class QOMNAuditLog:
    """Append-only audit log per QOMN Layer 4.

    Requirements per QOMN §3 Layer 4:
      - Append-only (entries never modified or deleted)
      - Every entry has cryptographic hash chain
      - AHJ-accessible without vendor cooperation
      - JSON export with integrity verification
    """

    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []
        # V114 FIX: Use HMAC-SHA256 for chain integrity (matching V105 fix
        # for security_logging.py). Plain SHA-256 is tamper-evident but NOT
        # tamper-proof — any attacker with source access can recompute chains.
        self._hmac_key = os.environ.get("FIREAI_QOMN_HMAC_KEY", "").encode()
        self._chain_hash: str = self._compute_chain_hash(b"QOMN-GENESIS")
        self._lock = threading.RLock()  # V-10: thread-safe under concurrent analyze_building()

    def _compute_chain_hash(self, data: bytes) -> str:
        """Compute chain hash using HMAC-SHA256 if key available, else SHA-256."""
        if self._hmac_key:
            return hmac.new(self._hmac_key, data, hashlib.sha256).hexdigest()
        return hashlib.sha256(data).hexdigest()

    def record(
        self,
        computation_type: str,
        input_data: Dict,
        formula_ref: str,
        output_data: Dict,
        layer3_passed: bool = False,  # V112: FAIL-SAFE — layer3 not passed until verified
    ) -> AuditEntry:
        """Record a computation to the immutable audit log."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

        # Compute result hash (outside lock — pure computation, no shared state)
        result_hash = hashlib.sha256(json.dumps(output_data, sort_keys=True, default=str).encode()).hexdigest()

        with self._lock:  # V-10: prevent split-brain chain hash under concurrent workers
            # Chain hash: links this entry to all previous entries (inside lock)
            chain_input = f"{self._chain_hash}:{result_hash}:{timestamp}".encode()
            self._chain_hash = self._compute_chain_hash(chain_input)
            entry = AuditEntry(
                timestamp_utc=timestamp,
                computation_type=computation_type,
                input_data=dict(input_data),
                formula_ref=formula_ref,
                output_data=dict(output_data),
                result_hash=result_hash,
                layer3_passed=layer3_passed,
            )
            self._entries.append(entry)
        return entry

    def export_json(self) -> Dict[str, Any]:
        """Export full audit log as AHJ-accessible JSON."""
        return {
            "qomn_version": "1.0.0",
            "chain_hash": self._chain_hash,
            "total_entries": len(self._entries),
            "entries": [
                {
                    "timestamp_utc": e.timestamp_utc,
                    "computation_type": e.computation_type,
                    "input": e.input_data,
                    "formula_ref": e.formula_ref,
                    "output": e.output_data,
                    "result_hash": e.result_hash,
                    "layer3_passed": e.layer3_passed,
                }
                for e in self._entries
            ],
        }

    def verify_chain_integrity(self) -> bool:
        """Verify the hash chain is intact (tamper detection).

        V58 FIX (BUG #1): Now uses _compute_chain_hash() instead of plain
        hashlib.sha256() so that verification matches recording when HMAC
        key is configured. Previously, verify always used SHA-256 while
        record used HMAC-SHA256, causing ALL verifications to fail in
        production (when FIREAI_QOMN_HMAC_KEY is set).

        V-10c: Acquires lock for consistent snapshot under concurrent load.
        """
        with self._lock:
            if not self._entries:
                return True
            entries_snapshot = list(self._entries)
            expected_final   = self._chain_hash
        chain = self._compute_chain_hash(b"QOMN-GENESIS")
        for e in entries_snapshot:
            chain_input = f"{chain}:{e.result_hash}:{e.timestamp_utc}"
            chain = self._compute_chain_hash(chain_input.encode())
        return chain == expected_final


# ═══════════════════════════════════════════════════════════════════════════════
# QOMN KERNEL — Unified Interface
# ═══════════════════════════════════════════════════════════════════════════════


class QOMNKernel:
    """Main QOMN-FIRE Deterministic Engineering Kernel.

    Orchestrates all five layers in sequence:
      L0 → L1 → L2 → L3 → L4

    All computation results are:
      - Validated against physics and code bounds (L0, L3)
      - Traceable to published standard (L1)
      - Bit-exact and deterministic (L2)
      - Permanently logged (L4)
    """

    def __init__(self) -> None:
        self.audit = QOMNAuditLog()

    def smoke_detector_spacing(self, ceiling_height_m: float) -> Dict[str, Any]:
        """Compute smoke detector spacing. Full L0→L1→L2→L3→L4 pipeline."""
        # L2 computation
        result = compute_smoke_detector_spacing(ceiling_height_m)
        # L3 validation
        result = validate_smoke_spacing_result(result)
        # L4 audit
        # V58 FIX (BUG #5): Pass layer3_passed=True — L3 validation was
        # performed but the audit log recorded layer3_passed=False (default)
        self.audit.record(
            "smoke_detector_spacing",
            {"ceiling_height_m": ceiling_height_m},
            result["nfpa_section"],
            result,
            layer3_passed=True,
        )
        return result

    def heat_detector_spacing(self, ceiling_height_m: float, area_per_detector_m2: float) -> Dict[str, Any]:
        """Compute heat detector spacing. Full L0→L4 pipeline.

        V58 FIX (BUG #3): Now includes L3 validation before audit record.
        Previously skipped validation entirely — no validate_heat_spacing_result()
        function even existed.
        """
        # L2 computation
        result = compute_heat_detector_spacing(ceiling_height_m, area_per_detector_m2)
        # L3 validation
        result = validate_heat_spacing_result(result)
        # L4 audit
        self.audit.record(
            "heat_detector_spacing",
            {"ceiling_height_m": ceiling_height_m, "area_m2": area_per_detector_m2},
            result["nfpa_section"],
            result,
            layer3_passed=True,
        )
        return result

    def battery_capacity(
        self,
        standby_load_a: float,
        alarm_load_a: float,
        **kwargs,
    ) -> Dict[str, Any]:
        """Compute battery capacity. Full L0→L4 pipeline."""
        result = compute_battery_capacity_ah(standby_load_a, alarm_load_a, **kwargs)
        result = validate_battery_result(result)
        # V58 FIX (BUG #5): Pass layer3_passed=True
        self.audit.record(
            "battery_capacity",
            {"standby_a": standby_load_a, "alarm_a": alarm_load_a},
            result["nfpa_section"],
            result,
            layer3_passed=True,
        )
        return result

    def voltage_drop(
        self,
        current_a: float,
        length_m: float,
        awg_gauge: str,
        supply_voltage_v: float = 24.0,
        max_drop_pct: float = 10.0,
    ) -> Dict[str, Any]:
        """Compute voltage drop. Full L0→L4 pipeline."""
        result = compute_voltage_drop(current_a, length_m, awg_gauge, supply_voltage_v, max_drop_pct)
        result = validate_voltage_drop_result(result)
        # V58 FIX (BUG #5): Pass layer3_passed=True
        self.audit.record(
            "voltage_drop",
            {"current_a": current_a, "length_m": length_m, "awg": awg_gauge},
            result["nec_section"],
            result,
            layer3_passed=True,
        )
        return result

    def get_audit_log(self) -> Dict[str, Any]:
        """Export full audit log for AHJ review."""
        return self.audit.export_json()

    def verify_audit_integrity(self) -> bool:
        """Verify audit log has not been tampered with."""
        return self.audit.verify_chain_integrity()


# Module-level default kernel instance
_default_kernel = QOMNKernel()
