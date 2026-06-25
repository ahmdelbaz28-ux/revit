"""duct_detector.py — NFPA 72 §17.7.5 Duct Detector Placement
============================================================
Computes required duct smoke detector positions per NFPA 72-2022 §17.7.5.

Rules applied:
  · §17.7.5.1 — detectors required in supply/return ducts serving
    air-handling units with capacity > 2000 CFM.
  · §17.7.5.3 — detector location within the duct.
  · Maximum spacing 3.05 m (10 ft) along duct centreline — sourced from
    NFPA 90A §6.4.2.2 and IMC §606.4 (not NFPA 72 itself, which does
    not specify inter-detector spacing for duct units).

Design principles:
  - Zero external dependencies — pure Python.
  - All dataclasses are immutable (frozen=True) for safety.
  - Length validation: warns if length_m doesn't match geometric distance.
  - Graceful exemption for narrow/short ducts.

References:
  NFPA 72-2022 §17.7.5 — Smoke Detectors in Duct Systems
  NFPA 90A-2024 §6.4.2.2 — Duct Detector Spacing
  IMC §606.4 — Smoke Detectors in Duct Systems
  UL 268A — Smoke Detectors for Duct Heater and Air-Handling System Applications
      (velocity blindness limit: sampling tubes ineffective above 4000 FPM)

"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Point = Tuple[float, float]

# NFPA 90A §6.4.2.2 / IMC §606.4 — maximum spacing between duct detectors
# NOTE: NFPA 72 §17.7.5 does NOT specify inter-detector spacing.
# The 3.05m (10 ft) value comes from NFPA 90A and IMC.
NFPA_DUCT_MAX_SPACING_M: float = 3.05  # 10 ft converted to metres
NFPA_DUCT_SPACING_REF: str = "NFPA 90A-2024 §6.4.2.2"  # spacing source

# Minimum dimensions for duct detector requirement
NFPA_DUCT_MIN_WIDTH_M: float = 0.20  # ducts narrower than this are exempt
NFPA_DUCT_MIN_LENGTH_M: float = 1.00  # ducts shorter than this are exempt

# CFM threshold — NFPA 72 §17.7.5.1
NFPA_DUCT_CFM_THRESHOLD: float = 2000.0

# UL 268A — maximum air velocity for reliable smoke detection
# Above this velocity, sampling tubes cannot capture smoke particles (blow-by effect).
UL268A_MAX_VELOCITY_FPM: float = 4000.0

# V20.2 FIX: UL 268A minimum velocity — below 100 FPM, sampling tubes cannot
# draw enough air through the sensing chamber. Smoke may be present but undetected.
UL268A_MIN_VELOCITY_FPM: float = 100.0

# Tolerance for length mismatch warning
_LENGTH_MISMATCH_TOLERANCE: float = 0.10  # 10 cm


@dataclass(frozen=True)
class DuctSpec:
    """Immutable specification of one air duct.

    Args:
        duct_id:      Unique identifier for this duct.
        length_m:     Centreline length of the duct in metres.
        width_m:      Cross-section width (diameter for round) in metres.
        start_point:  Entry point of duct in room coordinates (x, y).
        end_point:    Exit point of duct in room coordinates (x, y).
        airflow_cfm:  Optional airflow capacity in CFM.
                      Used for §17.7.5.1 compliance check.
                      None = unknown (conservative — detector placed).
        duct_type:    Type of duct: "supply", "return", or "exhaust".
                      Only supply and return require detectors per §17.7.5.1.

    """

    duct_id: str
    length_m: float
    width_m: float
    start_point: Point = (0.0, 0.0)
    end_point: Point = (1.0, 0.0)
    airflow_cfm: Optional[float] = None
    duct_type: str = "supply"
    height_m: float = 0.0  # cross-section height (0 = round duct; width_m = diameter)

    def __post_init__(self):
        # V25 FIX: Validate duct_type against NFPA 72 §17.7.5.1 recognized types.
        # A misspelled duct_type (e.g., "suply") would bypass the CFM override
        # in analyse_duct(), potentially leaving a 5000+ CFM air handler without
        # smoke detection — a life-safety failure.
        valid_types = {"supply", "return", "exhaust", "mixed"}
        normalized = self.duct_type.lower().strip()
        if normalized not in valid_types:
            raise ValueError(
                f"DuctSpec.duct_type='{self.duct_type}' is not a recognized "
                f"NFPA 72 §17.7.5.1 duct type. Must be one of: "
                f"{sorted(valid_types)}. A misspelled duct_type could bypass "
                f"CFM-based detector requirements — a life-safety risk."
            )
        # V50 FIX: Store the normalized duct_type, not the original.
        # Previous code validated normalized value but stored the original
        # (e.g., " supply " with spaces). Downstream code comparing
        # duct.duct_type.lower() against ("supply", "return", "mixed") would
        # fail because spaces are preserved, bypassing the CFM override.
        # This caused a false exemption for high-CFM ducts with padded type.
        object.__setattr__(self, "duct_type", normalized)

        # V50 FIX: Validate numeric inputs — reject NaN, Inf, negative values.
        # NaN airflow_cfm silently bypasses CFM override (NaN > 2000 = False).
        # Negative dimensions produce nonsensical results. Life-critical code
        # must reject garbage inputs rather than silently producing garbage output.
        import math

        for name in ("length_m", "width_m", "height_m"):
            val = getattr(self, name)
            if not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
                raise ValueError(
                    f"DuctSpec.{name}={val} is invalid. Must be a non-negative finite number. [NFPA 72 §17.7.5.1]"
                )
        if self.airflow_cfm is not None:
            if (
                not isinstance(self.airflow_cfm, (int, float))
                or not math.isfinite(self.airflow_cfm)
                or self.airflow_cfm < 0
            ):
                raise ValueError(
                    f"DuctSpec.airflow_cfm={self.airflow_cfm} is invalid. "
                    f"Must be a non-negative finite number or None. "
                    f"[NFPA 72 §17.7.5.1]"
                )


@dataclass(frozen=True)
class DuctDetectorPosition:
    """Position of one duct smoke detector.

    nfpa_ref cites the requirement for duct detectors (NFPA 72 §17.7.5).
    spacing_ref cites the maximum inter-detector spacing (NFPA 90A §6.4.2.2).
    """

    duct_id: str
    index: int  # detector index within duct (1-based)
    x: float
    y: float
    distance_from_start_m: float
    nfpa_ref: str = "NFPA 72-2022 §17.7.5"  # detector requirement
    spacing_ref: str = "NFPA 90A-2024 §6.4.2.2"  # max spacing source


@dataclass(frozen=True)
class DuctAnalysisResult:
    """Complete analysis result for one duct.

    nfpa_ref cites the requirement for duct detectors (NFPA 72 §17.7.5).
    spacing_ref cites the maximum inter-detector spacing (NFPA 90A §6.4.2.2).
    """

    duct_id: str
    duct_length_m: float
    duct_width_m: float
    detectors: List[DuctDetectorPosition] = field(default_factory=list)
    detector_count: int = 0
    spacing_used_m: float = 0.0
    exempt: bool = False
    exemption_reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    velocity_fpm: float = 0.0  # computed air velocity in FPM
    velocity_blindness: bool = False  # True if velocity exceeds UL 268A limit
    # V51 FIX: When velocity_blindness=True, placed detectors are non-functional.
    # A compliance report showing detectors placed would be a false PASS.
    # This flag indicates detectors need alternative detection method.
    detectors_functional: bool = True  # False when velocity_blindness or other issue
    # V20.2 FIX: HVAC shutdown flag per NFPA 72 §21.7.1
    hvac_shutdown_required: bool = False
    hvac_shutdown_ref: str = ""
    nfpa_ref: str = "NFPA 72-2022 §17.7.5"  # detector requirement
    spacing_ref: str = "NFPA 90A-2024 §6.4.2.2"  # max spacing source


# ============================================================================
# Core analysis function
# ============================================================================


def analyse_duct(duct: DuctSpec) -> DuctAnalysisResult:
    """Compute required duct detector positions per NFPA 72 §17.7.5.

    Placement algorithm:
      1. Check exemptions (width, length, duct type).
      2. Verify length_m matches geometric distance (warn if mismatch).
      3. Compute detector count: ceil(length / max_spacing).
      4. Distribute detectors evenly along centreline, centred in each segment.
      5. Check CFM threshold — warn if ≤ 2000 CFM.

    Returns:
        DuctAnalysisResult with detector positions, exemptions, and warnings.

    """
    warnings: List[str] = []

    # V68 FIX: Three-tier exemption logic per NFPA 72 §17.7.5.1:
    # 1. CFM override: When KNOWN CFM >2000 for supply/return/mixed,
    #    detectors are REQUIRED regardless of dimensions.
    # 2. CFM unknown block: When CFM is UNKNOWN (None) for supply/return/mixed,
    #    dimension exemptions are BLOCKED — the AHU could be >2000 CFM.
    #    This is the conservative/fail-safe position per NFPA 72.
    # 3. Physical dimension exemptions: Only when CFM is KNOWN and ≤2000 CFM,
    #    narrow/short/zero-dimension ducts are exempt because you cannot
    #    physically install a standard UL 268A duct smoke detector housing.

    _is_supply_return_mixed = duct.duct_type.lower() in ("supply", "return", "mixed")

    # ── CFM override: NFPA 72 §17.7.5.1 ──────────────────────────────────
    # When CFM is KNOWN and >2000 for supply/return/mixed ducts, detectors
    # are REQUIRED regardless of dimensions. This overrides ALL exemptions.
    cfm_override = (
        duct.airflow_cfm is not None and duct.airflow_cfm > NFPA_DUCT_CFM_THRESHOLD and _is_supply_return_mixed
    )

    # ── CFM unknown block (V68 FIX — life-safety conservative) ────────────
    # When CFM is unknown for supply/return/mixed ducts, dimension exemptions
    # are BLOCKED because the AHU could be >2000 CFM. Per NFPA 72 §17.7.5.1,
    # the conservative position is to REQUIRE detectors unless CFM is KNOWN
    # to be ≤2000. Exhaust ducts are always exempt regardless.
    cfm_unknown_blocks_exemption = duct.airflow_cfm is None and _is_supply_return_mixed

    if not cfm_override and not cfm_unknown_blocks_exemption:
        # ── Exemption: zero-dimension ducts ──────────────────────────────
        if duct.width_m == 0.0 or duct.length_m == 0.0:
            return DuctAnalysisResult(
                duct_id=duct.duct_id,
                duct_length_m=duct.length_m,
                duct_width_m=duct.width_m,
                detectors=[],
                detector_count=0,
                spacing_used_m=0.0,
                exempt=True,
                exemption_reason=(
                    f"Duct has zero dimensions (width={duct.width_m:.2f}m, "
                    f"length={duct.length_m:.2f}m) — physically non-existent, "
                    f"exempt from detector requirements."
                ),
            )

        # ── Exemption: narrow duct ────────────────────────────────────────
        if duct.width_m < NFPA_DUCT_MIN_WIDTH_M:
            return DuctAnalysisResult(
                duct_id=duct.duct_id,
                duct_length_m=duct.length_m,
                duct_width_m=duct.width_m,
                detectors=[],
                detector_count=0,
                spacing_used_m=0.0,
                exempt=True,
                exemption_reason=(
                    f"Duct width {duct.width_m:.2f}m < minimum {NFPA_DUCT_MIN_WIDTH_M}m (NFPA 72 §17.7.5 — exempt)."
                ),
            )

        # ── Exemption: short duct ─────────────────────────────────────────
        if duct.length_m < NFPA_DUCT_MIN_LENGTH_M:
            return DuctAnalysisResult(
                duct_id=duct.duct_id,
                duct_length_m=duct.length_m,
                duct_width_m=duct.width_m,
                detectors=[],
                detector_count=0,
                spacing_used_m=0.0,
                exempt=True,
                exemption_reason=(
                    f"Duct length {duct.length_m:.2f}m < minimum {NFPA_DUCT_MIN_LENGTH_M}m (NFPA 72 §17.7.5 — exempt)."
                ),
            )

    # ── Exemption: exhaust ducts don't require detectors ──────────────────
    if duct.duct_type.lower() == "exhaust":
        return DuctAnalysisResult(
            duct_id=duct.duct_id,
            duct_length_m=duct.length_m,
            duct_width_m=duct.width_m,
            detectors=[],
            detector_count=0,
            spacing_used_m=0.0,
            exempt=True,
            exemption_reason=(
                f"Duct type '{duct.duct_type}' — exhaust ducts are exempt "
                f"from detector requirements (NFPA 72 §17.7.5.1 applies to "
                f"supply/return only)."
            ),
        )

    # ── Length consistency check ──────────────────────────────────────────
    geo_length = math.hypot(
        duct.end_point[0] - duct.start_point[0],
        duct.end_point[1] - duct.start_point[1],
    )
    if geo_length > _LENGTH_MISMATCH_TOLERANCE:
        diff = abs(duct.length_m - geo_length)
        if diff > _LENGTH_MISMATCH_TOLERANCE:
            warnings.append(
                f"Duct '{duct.duct_id}': length_m={duct.length_m:.2f}m "
                f"differs from geometric distance {geo_length:.2f}m "
                f"(delta={diff:.2f}m). Using length_m for spacing calculation."
            )

    # ── CFM threshold warning ────────────────────────────────────────────
    if duct.airflow_cfm is not None and duct.airflow_cfm <= NFPA_DUCT_CFM_THRESHOLD:
        warnings.append(
            f"Duct '{duct.duct_id}': airflow {duct.airflow_cfm:.0f} CFM ≤ "
            f"{NFPA_DUCT_CFM_THRESHOLD:.0f} CFM — verify with AHJ whether "
            f"detector is mandatory (NFPA 72 §17.7.5.1)."
        )

    # ── UL 268A velocity blindness check ─────────────────────────────────
    velocity_fpm = 0.0
    velocity_blindness = False
    if duct.airflow_cfm is not None and duct.airflow_cfm > 0 and duct.width_m > 0:
        # Compute cross-section area
        if duct.height_m > 0:
            # Rectangular duct
            area_m2 = duct.width_m * duct.height_m
        else:
            # Round duct (width_m = diameter)
            area_m2 = math.pi * (duct.width_m / 2.0) ** 2
        area_sq_ft = area_m2 * 10.764  # m² → ft²
        if area_sq_ft > 0:
            velocity_fpm = duct.airflow_cfm / area_sq_ft
            if velocity_fpm > UL268A_MAX_VELOCITY_FPM:
                velocity_blindness = True
                warnings.append(
                    f"Duct '{duct.duct_id}': air velocity {velocity_fpm:.0f} FPM "
                    f"exceeds UL 268A limit of {UL268A_MAX_VELOCITY_FPM:.0f} FPM — "
                    f"smoke detector sampling tubes cannot capture smoke particles "
                    f"at this velocity (blow-by effect). Reduce duct velocity or "
                    f"use alternative detection method."
                )
            # V20.2 FIX: Check UL 268A MINIMUM velocity — below 100 FPM,
            # sampling tubes cannot draw enough air for smoke detection.
            if velocity_fpm < UL268A_MIN_VELOCITY_FPM:
                velocity_blindness = True
                warnings.append(
                    f"Duct '{duct.duct_id}': air velocity {velocity_fpm:.0f} FPM "
                    f"is below UL 268A minimum of {UL268A_MIN_VELOCITY_FPM:.0f} FPM — "
                    f"sampling tubes cannot draw sufficient air for smoke detection "
                    f"(stagnation effect). Increase duct velocity or use alternative "
                    f"detection method per UL 268A listing."
                )

    # ── Compute detector count and spacing ───────────────────────────────
    n_detectors = max(1, math.ceil(duct.length_m / NFPA_DUCT_MAX_SPACING_M))
    spacing_m = duct.length_m / n_detectors

    # ── Interpolate positions along duct centreline ──────────────────────
    sx, sy = duct.start_point
    ex, ey = duct.end_point
    dx = ex - sx
    dy = ey - sy
    duct_vec_len = math.hypot(dx, dy)

    positions: List[DuctDetectorPosition] = []
    for i in range(n_detectors):
        dist = spacing_m * (i + 0.5)  # centred within each segment
        if duct_vec_len > 1e-9:
            t = min(dist / duct_vec_len, 1.0)
            px = sx + t * dx
            py = sy + t * dy
        else:
            px, py = sx, sy

        positions.append(
            DuctDetectorPosition(
                duct_id=duct.duct_id,
                index=i + 1,
                x=round(px, 4),
                y=round(py, 4),
                distance_from_start_m=round(dist, 4),
            )
        )

    return DuctAnalysisResult(
        duct_id=duct.duct_id,
        duct_length_m=duct.length_m,
        duct_width_m=duct.width_m,
        detectors=positions,
        detector_count=len(positions),
        spacing_used_m=round(spacing_m, 4),
        warnings=warnings,
        velocity_fpm=round(velocity_fpm, 1),
        velocity_blindness=velocity_blindness,
        # V51 FIX: When velocity_blindness=True, detectors are non-functional.
        # UL 268A listed detectors cannot operate outside their rated velocity
        # range. A compliance report showing "detectors placed" would be a
        # false PASS — the system must explicitly flag non-functional detectors.
        detectors_functional=not velocity_blindness,
        # V20.2 FIX: HVAC shutdown per NFPA 72 §21.7.1
        hvac_shutdown_required=(
            duct.duct_type.lower() in ("supply", "return", "mixed")
            and (duct.airflow_cfm is None or duct.airflow_cfm > NFPA_DUCT_CFM_THRESHOLD)
        ),
        hvac_shutdown_ref=("NFPA 72-2022 §21.7.1" if duct.duct_type.lower() in ("supply", "return", "mixed") else ""),
    )


def analyse_ducts(ducts: List[DuctSpec]) -> List[DuctAnalysisResult]:
    """Analyse a list of ducts. Returns one result per duct."""
    return [analyse_duct(d) for d in ducts]


def total_duct_detectors(results: List[DuctAnalysisResult]) -> int:
    """Sum detector counts across all duct results."""
    return sum(r.detector_count for r in results)
