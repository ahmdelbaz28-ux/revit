"""sensor_physics_advisor.py — Advisory Layer for 3D Ceiling/Slope Effects
========================================================================

VERIFICATION-ONLY advisory module. Does NOT modify coverage calculations.
The actual coverage radius adjustment per ceiling height is already handled
by calculate_coverage_radius_from_height() in nfpa72_calculations.py, which
uses the authoritative NFPA 72 Table 17.6.3.1.1.

This module provides ADVISORY WARNINGS for extreme ceiling conditions where
point-type detectors may be insufficient and beam/projected-type detectors
should be considered per NFPA 72 §17.7.

Consultant #6 Criticism #1 — CONCEPT ACCEPTED, IMPLEMENTATION REJECTED:
  The consultant's EliteSensorPhysics class proposed a linear 5%/m height
  penalty and cos(slope) reduction. This is REJECTED because:

  1. NFPA 72 Table 17.6.3.1.1 already provides the authoritative height-
     adjusted spacing — a linear approximation is LESS accurate than the
     discrete table.
  2. NFPA 72 handles sloped ceilings via ridge zone requirements (§17.6.3.4),
     NOT by reducing horizontal coverage with cos(slope). The system already
     implements this in check_ridge_zone_compliance().
  3. Adding a second radius adjustment would create DOUBLE PENALTY (height
     table + slope factor), making placement over-conservative.

  ACCEPTED: The advisory concept — warn when ceiling conditions exceed
  point detector capability and recommend beam detectors.

NFPA 72 References:
  - §17.7.1: Spot-type smoke detectors
  - §17.7.2: Projected beam-type smoke detectors
  - §17.7.3: Performance-based design alternative
  - Table 17.6.3.1.1: Height-adjusted spacing
  - §17.6.3.4: Sloped ceilings
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Advisory Result
# ──────────────────────────────────────────────────────────────────


@dataclass
class SensorAdvisory:
    """Advisory result for a room's ceiling/slope conditions.

    This is NOT a compliance result — it is an advisory that flags
    conditions where the current point-type detector approach may
    be suboptimal and alternative detector types should be considered.

    Attributes:
        room_id: Room identifier.
        ceiling_height_m: Ceiling height at low point (meters).
        slope_degrees: Ceiling slope in degrees.
        detector_type: Detector type used (e.g. "smoke").
        severity: "INFO", "WARNING", or "CRITICAL".
        recommendations: List of human-readable recommendations.
        nfpa_references: List of NFPA 72 section references.
        beam_detector_recommended: True if beam detectors should be considered.
        performance_based_design: True if PE performance-based design required.

    """

    room_id: str
    ceiling_height_m: float
    slope_degrees: float = 0.0
    detector_type: str = "smoke"
    severity: str = "INFO"
    recommendations: List[str] = field(default_factory=list)
    nfpa_references: List[str] = field(default_factory=list)
    beam_detector_recommended: bool = False
    performance_based_design: bool = False


# ──────────────────────────────────────────────────────────────────
# Thresholds per NFPA 72
# ──────────────────────────────────────────────────────────────────

# NFPA 72 §17.7.1: Spot-type detectors are generally suitable up to
# the maximum height in Table 17.6.3.1.1 (12.2m for smoke).
# Beyond this, beam detectors are the standard recommendation.
_POINT_DETECTOR_MAX_HEIGHT_SMOKE = 12.2  # meters (NFPA 72 Table 17.6.3.1.1)
_POINT_DETECTOR_MAX_HEIGHT_HEAT = 12.2  # meters

# NFPA 72 §17.6.3.4: Sloped ceiling with pitch > 1 in 8 (7.125°)
# requires special treatment (ridge zone detectors). Beyond ~30°,
# the ceiling is effectively a wall and spot detection is impractical.
_STEEP_SLOPE_THRESHOLD_DEG = 30.0  # beyond this, spot detectors impractical
_SLOPED_CEILING_THRESHOLD_DEG = 7.125  # 1 in 8 pitch per NFPA 72 §17.6.3.4

# High ceiling warning thresholds (still within NFPA table, but PE review advised)
_HIGH_CEILING_WARNING_SMOKE = 9.1  # meters — consider beam detectors
_HIGH_CEILING_WARNING_HEAT = 9.1


class SensorPhysicsAdvisor:
    """Advisory layer for 3D ceiling/slope effects on detector performance.

    This class does NOT modify coverage calculations. It provides advisory
    warnings and recommendations when ceiling conditions exceed the practical
    limits of point-type detectors.

    The actual coverage radius is already adjusted by:
      - calculate_coverage_radius_from_height() (NFPA 72 Table 17.6.3.1.1)
      - check_ridge_zone_compliance() (NFPA 72 §17.6.3.4)
      - adjust_coverage_for_beams() (NFPA 72 §17.6.3.6)

    This advisor adds RECOMMENDATIONS for alternative detector types when
    point detectors are at the edge of their effective range.

    Usage:
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1",
            ceiling_height_m=10.5,
            slope_degrees=15.0,
            detector_type="smoke",
        )
        if advisory.beam_detector_recommended:
            print("Consider beam detectors for this room.")
    """

    def advise(
        self,
        room_id: str,
        ceiling_height_m: float,
        slope_degrees: float = 0.0,
        detector_type: str = "smoke",
    ) -> SensorAdvisory:
        """Generate advisory for ceiling/slope conditions.

        Args:
            room_id: Room identifier.
            ceiling_height_m: Ceiling height at low point (meters).
            slope_degrees: Ceiling slope in degrees (0 = flat).
            detector_type: "smoke" or "heat".

        Returns:
            SensorAdvisory with recommendations.

        """
        recommendations: List[str] = []
        nfpa_refs: List[str] = []
        severity = "INFO"
        beam_recommended = False
        perf_based = False

        # ─── Check 1: Height beyond NFPA table ───────────────────
        max_h = _POINT_DETECTOR_MAX_HEIGHT_SMOKE if detector_type == "smoke" else _POINT_DETECTOR_MAX_HEIGHT_HEAT
        warn_h = _HIGH_CEILING_WARNING_SMOKE if detector_type == "smoke" else _HIGH_CEILING_WARNING_HEAT

        if ceiling_height_m > max_h:
            severity = "CRITICAL"
            beam_recommended = True
            recommendations.append(
                f"Ceiling height {ceiling_height_m:.1f}m exceeds NFPA 72 Table 17.6.3.1.1 "
                f"maximum ({max_h}m) for point-type {detector_type} detectors. "
                f"Projected beam-type detectors are REQUIRED per NFPA 72 §17.7.2."
            )
            nfpa_refs.append("NFPA 72-2022 §17.7.2")
            nfpa_refs.append("NFPA 72-2022 Table 17.6.3.1.1")

        elif ceiling_height_m > warn_h:
            if severity == "INFO":
                severity = "WARNING"
            beam_recommended = True
            recommendations.append(
                f"Ceiling height {ceiling_height_m:.1f}m exceeds {warn_h}m. "
                f"Point-type {detector_type} detectors operate with reduced spacing "
                f"at this height. Consider projected beam-type detectors per "
                f"NFPA 72 §17.7.2 for more cost-effective coverage."
            )
            nfpa_refs.append("NFPA 72-2022 §17.7.2")

        # ─── Check 2: Steep slope ────────────────────────────────
        if slope_degrees > _STEEP_SLOPE_THRESHOLD_DEG:
            severity = "CRITICAL"
            perf_based = True
            recommendations.append(
                f"Ceiling slope {slope_degrees:.1f}° exceeds {_STEEP_SLOPE_THRESHOLD_DEG}°. "
                f"Spot-type detectors are impractical on steep surfaces. "
                f"Performance-based design per NFPA 72 §17.7.3 is required. "
                f"Consult a licensed fire protection engineer."
            )
            nfpa_refs.append("NFPA 72-2022 §17.7.3")
            nfpa_refs.append("NFPA 72-2022 §17.6.3.4")

        elif slope_degrees > _SLOPED_CEILING_THRESHOLD_DEG:
            if severity == "INFO":
                severity = "WARNING"
            recommendations.append(
                f"Sloped ceiling ({slope_degrees:.1f}°) — ridge zone detectors "
                f"required per NFPA 72 §17.6.3.4. At least one detector must be "
                f"within 0.9m (3ft) of the highest point (ridge). Smoke rises "
                f"and collects at the ridge in sloped configurations."
            )
            nfpa_refs.append("NFPA 72-2022 §17.6.3.4")

        # ─── Check 3: Combined high ceiling + slope ──────────────
        if ceiling_height_m > warn_h and slope_degrees > _SLOPED_CEILING_THRESHOLD_DEG:
            severity = "CRITICAL"
            beam_recommended = True
            perf_based = True
            recommendations.append(
                f"CRITICAL COMBINATION: High ceiling ({ceiling_height_m:.1f}m) "
                f"+ sloped ({slope_degrees:.1f}°). Point detector coverage is "
                f"severely limited. Projected beam-type detectors along the ridge "
                f"are the recommended solution. PE performance-based design required."
            )
            nfpa_refs.append("NFPA 72-2022 §17.7.2")
            nfpa_refs.append("NFPA 72-2022 §17.7.3")

        # ─── Check 4: Very low ceiling (smoke stratification risk) ──
        if ceiling_height_m < 2.4 and detector_type == "smoke":
            if severity == "INFO":
                severity = "WARNING"
            recommendations.append(
                f"Ceiling height {ceiling_height_m:.1f}m is very low. Smoke "
                f"stratification may occur before reaching the detector. "
                f"Consider multi-level detection or air-sampling detection "
                f"(NFPA 72 §17.7.3.6) for improved response time."
            )
            nfpa_refs.append("NFPA 72-2022 §17.7.3.6")

        return SensorAdvisory(
            room_id=room_id,
            ceiling_height_m=ceiling_height_m,
            slope_degrees=slope_degrees,
            detector_type=detector_type,
            severity=severity,
            recommendations=recommendations,
            nfpa_references=nfpa_refs,
            beam_detector_recommended=beam_recommended,
            performance_based_design=perf_based,
        )

    def advise_room_dict(self, room_dict: dict) -> SensorAdvisory:
        """Convenience method: advise from room dict (as used in FloorAnalyser).

        Args:
            room_dict: Room dict with ceiling_height, room_id, etc.

        Returns:
            SensorAdvisory with recommendations.

        """
        ceiling_h = room_dict.get("ceiling_height", 3.0) or 3.0
        slope = room_dict.get("ceiling_slope_degrees", 0.0) or 0.0
        det_type = room_dict.get("detector_type", "smoke_photoelectric")
        det_simple = "heat" if "heat" in det_type.lower() else "smoke"
        room_id = room_dict.get("room_id", room_dict.get("name", "unknown"))

        return self.advise(
            room_id=room_id,
            ceiling_height_m=ceiling_h,
            slope_degrees=slope,
            detector_type=det_simple,
        )
