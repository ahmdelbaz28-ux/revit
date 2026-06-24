"""nfpa72_technology_dispatcher.py — Automatic Detector Technology Selection
=========================================================================

Automatically selects the appropriate detector TECHNOLOGY (not just radius)
based on ceiling height and slope per NFPA 72-2022.

Consultant #7 Proposal (EliteTechnologyDispatcher) — CONCEPT ACCEPTED,
IMPLEMENTATION CORRECTED:

  The consultant proposed MAX_POINT_HEIGHT_M = 9.1m, but NFPA 72
  Table 17.6.3.1.1 extends point-type detector spacing up to 12.2m
  ceiling height. Setting the limit at 9.1m would unnecessarily require
  beam detectors for rooms where NFPA 72 explicitly permits point
  detectors (with reduced spacing).

  CORRECTIONS applied:
    1. MAX_POINT_HEIGHT_M = 12.2 (NFPA 72 Table 17.6.3.1.1 max)
    2. Slope consideration: steep slopes + high ceiling = earlier switch
    3. Integration with existing SensorPhysicsAdvisor (no duplication)
    4. Progressive recommendation: Point → Point(reduced) → Beam → ASD
    5. Does NOT modify coverage calculations — only selects technology

Architecture:
  - DetectorTechnology enum: POINT_SMOKE, BEAM_SMOKE, ASD
  - TechnologyDecision: structured decision with technology, reason, NFPA refs
  - EliteTechnologyDispatcher: static method for technology selection
  - Integration: called from FloorAnalyser after SensorPhysicsAdvisor

NFPA 72 References:
  - Table 17.6.3.1.1: Height-adjusted spacing (up to 12.2m for smoke)
  - §17.7.1: Spot-type smoke detectors
  - §17.7.2: Projected beam-type smoke detectors
  - §17.7.3: Performance-based design alternative
  - §17.7.3.6: Air-sampling detection (ASD)
  - §17.6.3.4: Sloped ceilings (ridge zone requirement)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Detector Technology Types
# ──────────────────────────────────────────────────────────────────


class DetectorTechnology(Enum):
    """Detector technology types per NFPA 72 Chapter 17."""

    POINT_SMOKE = "POINT_SMOKE"  # Spot-type photoelectric/ionization
    POINT_HEAT = "POINT_HEAT"  # Spot-type heat detector
    BEAM_SMOKE = "BEAM_SMOKE"  # Projected beam-type
    ASD = "ASD"  # Aspirating Smoke Detection
    DUCT_SMOKE = "DUCT_SMOKE"  # Duct smoke detector


# ──────────────────────────────────────────────────────────────────
# Technology Decision
# ──────────────────────────────────────────────────────────────────


@dataclass
class TechnologyDecision:
    """Structured decision from the Technology Dispatcher.

    Attributes:
        technology: Selected detector technology.
        ceiling_height_m: Ceiling height used for the decision.
        slope_degrees: Ceiling slope in degrees.
        reason: Human-readable explanation of the decision.
        nfpa_references: List of NFPA 72 section references.
        spacing_m: Recommended spacing for this technology.
        ridge_zone_required: True if ridge zone detector is required.
        warnings: Advisory warnings.
        fallback_technology: Technology to use if preferred is unavailable.

    """

    technology: DetectorTechnology
    ceiling_height_m: float
    slope_degrees: float = 0.0
    reason: str = ""
    nfpa_references: List[str] = field(default_factory=list)
    spacing_m: float = 0.0
    ridge_zone_required: bool = False
    warnings: List[str] = field(default_factory=list)
    fallback_technology: Optional[DetectorTechnology] = None


# ──────────────────────────────────────────────────────────────────
# Thresholds per NFPA 72
# ──────────────────────────────────────────────────────────────────

# NFPA 72 Table 17.6.3.1.1: Maximum ceiling height for point-type
# smoke detectors with height-adjusted spacing. The table extends
# to 12.2m — point detectors ARE permitted at heights up to 12.2m,
# with progressively reduced spacing.
_POINT_DETECTOR_MAX_CEILING_M = 12.2

# Projected beam-type smoke detectors per NFPA 72 §17.7.2.
# Standard beam spacing is approximately 60ft (18.3m) per NFPA 72.
_BEAM_SPACING_M = 18.3
_BEAM_MAX_CEILING_M = 25.0  # Engineering practice — beyond this, ASD preferred

# Slope thresholds per NFPA 72 §17.6.3.4
_SLOPE_RIDGE_ZONE_THRESHOLD_DEG = 7.125  # 1 in 8 pitch — ridge zone required
_STEEP_SLOPE_THRESHOLD_DEG = 30.0  # Beyond this, spot detectors impractical

# High ceiling WARNING threshold (still within NFPA table, but cost-inefficient)
_HIGH_CEILING_ECONOMIC_THRESHOLD_M = 9.1  # Consider beam for cost efficiency

# NFPA 72 Table 17.6.3.1.1 — Height-adjusted smoke spacing
# V128: Import from CANONICAL single source of truth (fireai/constants/nfpa72.py)
# to eliminate divergent duplicate tables across the codebase.
# Previously, this was imported via fireai.constants (which had its own duplicates).
# Now imports directly from the authoritative nfpa72.py module.
from fireai.constants.nfpa72 import SMOKE_HEIGHT_SPACING_TABLE as _CANONICAL_SMOKE_TABLE

_NFPA72_SMOKE_SPACING_TABLE = list(_CANONICAL_SMOKE_TABLE)


# ──────────────────────────────────────────────────────────────────
# Technology Dispatcher
# ──────────────────────────────────────────────────────────────────


class EliteTechnologyDispatcher:
    """Automatic detector technology selection per NFPA 72-2022.

    Selects the appropriate detector TECHNOLOGY (not just spacing)
    based on ceiling height and slope conditions.

    Decision logic (progressive):
      1. h ≤ 12.2m AND slope ≤ 30° → Point-type detectors
         (with height-adjusted spacing from NFPA 72 Table 17.6.3.1.1)
      2. h > 12.2m AND h ≤ 25.0m → Beam-type detectors
         (per NFPA 72 §17.7.2)
      3. h > 25.0m → ASD (Aspirating Smoke Detection)
         (per NFPA 72 §17.7.3.6)
      4. Slope > 30° → Performance-based design required
         (per NFPA 72 §17.7.3)
      5. Slope > 7.125° → Ridge zone detector required
         (per NFPA 72 §17.6.3.4)

    Economic consideration:
      For h > 9.1m, beam detectors may be more cost-effective than
      point detectors with reduced spacing. A WARNING is issued
      recommending beam detectors for economic efficiency, but
      point detectors remain the CODE-COMPLIANT option.

    Usage:
        decision = EliteTechnologyDispatcher.select_technology(
            ceiling_height_m=10.5,
            slope_degrees=12.0,
            detector_category="smoke",
        )
        if decision.technology == DetectorTechnology.BEAM_SMOKE:
            print("Use beam detectors for this room.")
    """

    @staticmethod
    def select_technology(
        ceiling_height_m: float,
        slope_degrees: float = 0.0,
        detector_category: str = "smoke",
    ) -> TechnologyDecision:
        """Select detector technology based on ceiling conditions.

        Args:
            ceiling_height_m: Ceiling height at the LOW point (meters).
            slope_degrees: Ceiling slope in degrees (0 = flat).
            detector_category: "smoke" or "heat".

        Returns:
            TechnologyDecision with technology selection, spacing, and NFPA refs.

        """
        warnings: List[str] = []
        nfpa_refs: List[str] = []
        ridge_zone_required = slope_degrees > _SLOPE_RIDGE_ZONE_THRESHOLD_DEG

        # ─── Safety: reject invalid heights ─────────────────────────
        if ceiling_height_m <= 0:
            raise ValueError(f"Ceiling height must be positive, got {ceiling_height_m}m.")

        # V20.2 FIX: Handle heat detector category.
        # Previously, detector_category was accepted but IGNORED, causing
        # heat detector requests to return POINT_SMOKE with smoke spacing.
        # Heat detectors at h≤3.0m use S=6.1m (R=4.27m), NOT S=9.1m.
        # NFPA 72 Table 17.6.3.1.1 / Table 17.6.3.5.1.
        if detector_category == "heat":
            from fireai.core.nfpa72_calculations import (
                calculate_coverage_radius_from_height,
            )

            heat_spec = calculate_coverage_radius_from_height(ceiling_height_m, "heat")
            return TechnologyDecision(
                technology=DetectorTechnology.POINT_HEAT,
                ceiling_height_m=ceiling_height_m,
                slope_degrees=slope_degrees,
                reason=(
                    f"Heat detector selected. Ceiling height {ceiling_height_m:.1f}m, "
                    f"height-adjusted spacing S={heat_spec.spacing_max:.1f}m "
                    f"(R={heat_spec.radius:.2f}m) per NFPA 72 Table 17.6.3.5.1."
                ),
                nfpa_references=["NFPA 72-2022 Table 17.6.3.5.1", "NFPA 72-2022 Table 17.6.3.1.1"],
                spacing_m=round(heat_spec.spacing_max, 2),
                ridge_zone_required=ridge_zone_required,
                warnings=warnings,
            )

        # ─── Check 1: Steep slope (>30°) — spot detectors impractical ──
        if slope_degrees > _STEEP_SLOPE_THRESHOLD_DEG:
            return TechnologyDecision(
                technology=DetectorTechnology.ASD,
                ceiling_height_m=ceiling_height_m,
                slope_degrees=slope_degrees,
                reason=(
                    f"Ceiling slope {slope_degrees:.1f}° exceeds "
                    f"{_STEEP_SLOPE_THRESHOLD_DEG}°. Spot-type and beam-type "
                    f"detectors are impractical on steep surfaces. "
                    f"Performance-based design with ASD required per NFPA 72 §17.7.3."
                ),
                nfpa_references=["NFPA 72-2022 §17.7.3", "NFPA 72-2022 §17.7.3.6"],
                spacing_m=0.0,  # ASD spacing depends on pipe layout — PE design required
                ridge_zone_required=False,
                warnings=[
                    "PERFORMANCE_BASED_DESIGN_REQUIRED: Ceiling is too steep "
                    "for standard detector placement. PE design required."
                ],
                fallback_technology=DetectorTechnology.BEAM_SMOKE,
            )

        # ─── Check 2: Height beyond beam limit (>25m) → ASD ─────────
        if ceiling_height_m > _BEAM_MAX_CEILING_M:
            return TechnologyDecision(
                technology=DetectorTechnology.ASD,
                ceiling_height_m=ceiling_height_m,
                slope_degrees=slope_degrees,
                reason=(
                    f"Ceiling height {ceiling_height_m:.1f}m exceeds beam detector "
                    f"practical limit ({_BEAM_MAX_CEILING_M}m). Aspirating Smoke "
                    f"Detection (ASD) required per engineering best practice "
                    f"and NFPA 72 §17.7.3.6."
                ),
                nfpa_references=["NFPA 72-2022 §17.7.3.6"],
                spacing_m=0.0,  # ASD spacing depends on pipe layout
                ridge_zone_required=ridge_zone_required,
                warnings=[
                    f"ASD_REQUIRED: Height {ceiling_height_m:.1f}m exceeds beam "
                    f"detector practical limit. Aspirating detection recommended. "
                    f"PE performance-based design required."
                ],
                fallback_technology=DetectorTechnology.BEAM_SMOKE,
            )

        # ─── Check 3: Height beyond NFPA table (>12.2m) → Beam ─────
        if ceiling_height_m > _POINT_DETECTOR_MAX_CEILING_M:
            return TechnologyDecision(
                technology=DetectorTechnology.BEAM_SMOKE,
                ceiling_height_m=ceiling_height_m,
                slope_degrees=slope_degrees,
                reason=(
                    f"Ceiling height {ceiling_height_m:.1f}m exceeds point detector "
                    f"NFPA 72 Table 17.6.3.1.1 maximum ({_POINT_DETECTOR_MAX_CEILING_M}m). "
                    f"Projected beam-type detectors required per NFPA 72 §17.7.2. "
                    f"Beam spacing: {_BEAM_SPACING_M}m."
                ),
                nfpa_references=[
                    "NFPA 72-2022 §17.7.2",
                    "NFPA 72-2022 Table 17.6.3.1.1",
                ],
                spacing_m=_BEAM_SPACING_M,
                ridge_zone_required=ridge_zone_required,
                warnings=warnings,
                fallback_technology=DetectorTechnology.POINT_SMOKE,
            )

        # ─── Check 4: Within NFPA table — Point detectors ──────────
        # V130 FIX: Smoke detector spacing is FLAT 9.1m per §17.7.3.2.3.
        # NO height-based reduction — the table now returns 9.1m at all heights.
        spacing = EliteTechnologyDispatcher._get_smoke_spacing(ceiling_height_m)

        # Economic efficiency warning: beam detectors may be more
        # cost-effective for high ceilings due to stratification concerns
        # (§17.7.1.11), NOT because spacing is reduced.
        if ceiling_height_m > _HIGH_CEILING_ECONOMIC_THRESHOLD_M:
            warnings.append(
                f"STRATIFICATION_ADVISORY: Ceiling height {ceiling_height_m:.1f}m exceeds "
                f"{_HIGH_CEILING_ECONOMIC_THRESHOLD_M}m. Per NFPA 72 §17.7.1.11, "
                f"spot-type smoke detection may be unreliable due to stratification. "
                f"Projected beam-type detectors (spacing {_BEAM_SPACING_M}m) "
                f"may be more reliable per NFPA 72 §17.7.2. "
                f"Spacing remains 9.1m per §17.7.3.2.3 (flat, no height reduction)."
            )
            nfpa_refs.append("NFPA 72-2022 §17.7.2")
            nfpa_refs.append("NFPA 72-2022 §17.7.1.11")

        # Ridge zone warning for sloped ceilings
        if ridge_zone_required:
            warnings.append(
                f"RIDGE_ZONE_REQUIRED: Sloped ceiling ({slope_degrees:.1f}° > "
                f"{_SLOPE_RIDGE_ZONE_THRESHOLD_DEG}°). At least one detector must "
                f"be within 0.9m (3ft) of the ridge per NFPA 72 §17.6.3.4."
            )
            nfpa_refs.append("NFPA 72-2022 §17.6.3.4")

        return TechnologyDecision(
            technology=DetectorTechnology.POINT_SMOKE,
            ceiling_height_m=ceiling_height_m,
            slope_degrees=slope_degrees,
            reason=(
                f"Ceiling height {ceiling_height_m:.1f}m is within NFPA 72 "
                f"spot-type detector range (≤{_POINT_DETECTOR_MAX_CEILING_M}m). "
                f"Point-type smoke detectors with flat spacing "
                f"S={spacing:.1f}m (R={0.7 * spacing:.2f}m) per §17.7.3.2.3."
            ),
            nfpa_references=["NFPA 72-2022 §17.7.3.2.3"] + nfpa_refs,
            spacing_m=round(spacing, 2),
            ridge_zone_required=ridge_zone_required,
            warnings=warnings,
        )

    @staticmethod
    def _get_smoke_spacing(ceiling_height_m: float) -> float:
        """Get smoke detector spacing — FLAT 9.1m per NFPA 72 §17.7.3.2.3.

        V130 FIX: Smoke detector spacing is flat 9.1m at ALL ceiling heights.
        There is NO height-based reduction for smoke detectors.
        The canonical table (fireai.constants.nfpa72.SMOKE_HEIGHT_SPACING_TABLE)
        returns 9.1m for every height bracket, so iteration is a no-op but
        preserved for structural consistency with the heat detector path.

        Args:
            ceiling_height_m: Ceiling height in meters.

        Returns:
            Flat spacing S = 9.1m per NFPA 72 §17.7.3.2.3.

        """
        # NOTE: Table iteration is vestigial — all rows return 9.10m.
        # Kept for structural parity with heat detector spacing lookup.
        for h_max, spacing in _NFPA72_SMOKE_SPACING_TABLE:
            if ceiling_height_m <= h_max:
                return spacing
        # Beyond table — still flat 9.1m (no height reduction for smoke)
        return _NFPA72_SMOKE_SPACING_TABLE[-1][1]


# ──────────────────────────────────────────────────────────────────
# Integration helper for FloorAnalyser
# ──────────────────────────────────────────────────────────────────


def dispatch_detector_technology(room_dict: dict) -> TechnologyDecision:
    """Convenience function for FloorAnalyser integration.

    Extracts ceiling height and slope from room dict and dispatches
    the appropriate detector technology.

    Args:
        room_dict: Room dict with ceiling_height, ceiling_slope_degrees, etc.

    Returns:
        TechnologyDecision for this room.

    """
    ceiling_h = room_dict.get("ceiling_height", 3.0) or 3.0
    slope = room_dict.get("ceiling_slope_degrees", 0.0) or 0.0
    det_type = room_dict.get("detector_type", "smoke_photoelectric")
    category = "heat" if "heat" in det_type.lower() else "smoke"

    return EliteTechnologyDispatcher.select_technology(
        ceiling_height_m=ceiling_h,
        slope_degrees=slope,
        detector_category=category,
    )
