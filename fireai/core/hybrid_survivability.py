"""hybrid_survivability.py — Layer 7: Hybrid Survivability Index Engine
====================================================================
V24 — Intersection of Optical (Layer 5) and Acoustic (V23) coverage.

Architecture:
  Layer 5 (FlameDetectorAOCRayTrace) → CoverageResult (per-grid-point optical)
  V23 Phase 2 (trace_acoustic_ray)   → AcousticRayResult (point-to-point acoustic)
  Layer 7 (this file)                → HybridSurvivabilityMap (per-grid-point hybrid)

Design Rationale:
  Both engines share the same 3D world coordinate system. Layer 5 operates on
  a List[RayTracePoint] grid indexed by integer position. V23 operates on
  (leak_point, sensor_point) tuples. The intersection is achieved by running
  V23 for every grid point as a potential leak source against every UGLD
  sensor, then joining with Layer 5's redundancy_map.

  The result classifies each grid point into one of 4 survivability states:
    REDUNDANT_HYBRID — both optical LOS clear AND acoustic SNR triggered
    OPTICAL_ONLY     — optical coverage exists, but no acoustic detection
    ACOUSTIC_ONLY    — acoustic detection exists, but no optical LOS
    BLIND_SPOT       — neither optical nor acoustic detection

Physical Foundation:
  - Optical: Beer-Lambert spectral transmittance + LOS obstruction
    (NFPA 72-2022 §17.8.3)
  - Acoustic: ISO 9613-1 atmospheric absorption + Maekawa barrier diffraction
    (ISA-TR 84.00.07, IEC 60079-29-4)
  - Hybrid: Independent physics → intersection is mathematically sound
    (no double-counting of phenomena across modalities)

Key Design Decision — Sensor Positions:
  UltrasonicSensor (V23) does not carry spatial coordinates — it models
  detection physics, not physical placement. This is correct: a sensor's
  trigger threshold and frequency response are independent of where it's
  mounted. Position is a SITE-SPECIFIC concern, not a physical constant.
  Therefore, Layer 7 accepts a separate `sensor_positions` mapping
  (sensor_id → (x, y, z)) rather than polluting UltrasonicSensor with
  location data. This preserves the Separation of Concerns principle:
  V23 models physics; Layer 7 models spatial deployment.

Reference Standards:
  - NFPA 72-2022 §17.8.3.4 (redundancy)
  - ISA-TR 84.00.07 (UGLD coverage)
  - IEC 60079-29-4 (gas detection fundamentals)
  - FM Global DS 5-48 (property loss prevention)
"""

from __future__ import annotations

import datetime
import json
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

# ── Layer 5 imports ──────────────────────────────────────────────────────
from fireai.core.flame_detector_aoc_raytrace import CoverageResult
from fireai.core.models_v21 import RayTracePoint

# ── V23 imports ──────────────────────────────────────────────────────────
from fireai.core.ugld_acoustics import UltrasonicSensor
from fireai.core.ugld_raytrace import (
    AcousticObstacle,
    trace_acoustic_ray,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums and Models
# ===========================================================================


class SurvivabilityClass(str, Enum):
    """Per-point hybrid survivability classification.

    The classification is the Cartesian product of {optical, no_optical}
    x {acoustic, no_acoustic}, yielding 4 exhaustive and mutually exclusive
    states.

    Engineering interpretation per NFPA 72 / ISA-TR 84.00.07:

      REDUNDANT_HYBRID — Both modalities detect. Highest confidence.
        Optical sees the flame; acoustic hears the leak. Independent failure
        modes (smoke blinds optical, low-pressure leak silences acoustic).
        NFPA 72 §17.8.3.4 effectively requires this for critical areas.

      OPTICAL_ONLY — Flame detector covers this point, but no UGLD hears.
        Risk: dense smoke/steam blocks optical LOS before flame is visible,
        or the fire is smoldering (no UV/IR emission). The acoustic channel
        is absent, so there is no diversity against optical failure modes.

      ACOUSTIC_ONLY — UGLD can hear a leak here, but no flame detector sees.
        Risk: low-pressure leaks may not generate sufficient ultrasonic energy.
        Also, once ignited, the flame may not be in the UGLD detection cone.
        The optical channel is absent, so there is no diversity against
        acoustic failure modes (e.g., high background noise masking).

      BLIND_SPOT — Neither modality covers this point.
        This is a gap that MUST be addressed by adding detectors.
        In a SIL-rated system, any BLIND_SPOT in the hazardous zone
        is a violation that prevents submission.
    """

    REDUNDANT_HYBRID = "REDUNDANT_HYBRID"
    OPTICAL_ONLY = "OPTICAL_ONLY"
    ACOUSTIC_ONLY = "ACOUSTIC_ONLY"
    BLIND_SPOT = "BLIND_SPOT"

    @property
    def is_covered(self) -> bool:
        """True if at least one modality covers this point."""
        return self in (
            SurvivabilityClass.REDUNDANT_HYBRID,
            SurvivabilityClass.OPTICAL_ONLY,
            SurvivabilityClass.ACOUSTIC_ONLY,
        )

    @property
    def is_redundant(self) -> bool:
        """True if both modalities cover this point."""
        return self == SurvivabilityClass.REDUNDANT_HYBRID

    @property
    def severity_rank(self) -> int:
        """Lower = safer. Used for heatmap color mapping in Revit export."""
        return {
            SurvivabilityClass.REDUNDANT_HYBRID: 0,
            SurvivabilityClass.OPTICAL_ONLY: 1,
            SurvivabilityClass.ACOUSTIC_ONLY: 2,
            SurvivabilityClass.BLIND_SPOT: 3,
        }[self]


class AcousticCoverageDetail(BaseModel):
    """Per-point acoustic coverage detail from UGLD analysis.

    This is an OUTPUT model — it stores the result of running V23's
    trace_acoustic_ray for a specific (grid_point, sensor) pair. It does
    NOT belong on input models (UltrasonicSensor, AcousticObstacle).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    sensor_id: str = Field(description="UGLD sensor that produced this result.")
    triggered: bool = Field(description="Whether the UGLD triggers for this point.")
    snr_db: float = Field(description="Signal-to-noise ratio at this point (dB).")
    margin_to_threshold_db: float = Field(
        description="Margin above trigger threshold (dB). Negative = below.",
    )
    has_los: bool = Field(
        description="Whether direct acoustic LOS is clear (no obstacles).",
    )
    total_insertion_loss_db: float = Field(
        default=0.0,
        description="Total Maekawa IL from all intersected obstacles (dB).",
    )
    distance_meters: float = Field(
        description="Distance from this point (as leak source) to sensor (m).",
    )


class HybridPointResult(BaseModel):
    """Per-point hybrid survivability result.

    The atomic unit of the hybrid map. Each grid point gets one of these,
    combining optical and acoustic data into a single classification.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    point_index: int = Field(description="Index into the shared grid.")
    x: float = Field(description="World X coordinate (m).")
    y: float = Field(description="World Y coordinate (m).")
    z: float = Field(description="World Z coordinate (m).")
    survivability_class: SurvivabilityClass = Field(
        description="Hybrid classification (4-state).",
    )
    optical_detector_count: int = Field(
        default=0,
        description="Number of flame detectors covering this point.",
    )
    best_acoustic_detail: Optional[AcousticCoverageDetail] = Field(
        default=None,
        description="Best UGLD sensor result for this point (highest SNR).",
    )


class HybridSurvivabilityMap(BaseModel):
    """Layer 7 output: complete hybrid survivability analysis.

    Intersects Layer 5 optical coverage with V23 acoustic coverage on a
    shared spatial grid. Each point is classified into one of 4 states.

    This is an OUTPUT model — warnings are appropriate here (not on input).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    total_points: int = Field(ge=0, description="Total grid points analyzed.")
    point_results: Dict[int, HybridPointResult] = Field(
        default_factory=dict,
        description="Per-point hybrid results, keyed by grid index.",
    )

    # Aggregate counts
    redundant_hybrid_count: int = Field(
        default=0,
        ge=0,
        description="Points with both optical and acoustic coverage.",
    )
    optical_only_count: int = Field(
        default=0,
        ge=0,
        description="Points with optical coverage only.",
    )
    acoustic_only_count: int = Field(
        default=0,
        ge=0,
        description="Points with acoustic coverage only.",
    )
    blind_spot_count: int = Field(
        default=0,
        ge=0,
        description="Points with neither optical nor acoustic coverage.",
    )

    # Coverage fractions
    hybrid_coverage_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of points with REDUNDANT_HYBRID classification.",
    )
    any_coverage_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of points with at least one modality.",
    )
    blind_spot_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of points that are BLIND_SPOT.",
    )

    # Diagnostics (OUTPUT model — warnings belong here)
    warnings: List[str] = Field(default_factory=list)

    @property
    def redundant_hybrid_pct(self) -> float:
        """V60 FIX (P3-1): Coverage percentage without masking 100%.

        Previously, `round(fraction * 100, 2)` could produce 100.00 when actual
        coverage was < 100%, masking NFPA 72 §17.8.3.4 compliance gaps.
        This is the same fix as V59-8 applied to flame_detector_aoc_raytrace.py.
        """
        raw_pct = self.hybrid_coverage_fraction * 100.0
        if self.redundant_hybrid_count == self.total_points:
            return 100.00
        rounded = round(raw_pct, 2)
        if rounded >= 100.0 and raw_pct < 100.0:
            return round(raw_pct, 4)
        return rounded

    @property
    def any_coverage_pct(self) -> float:
        """V60 FIX (P3-2): Same rounding fix as redundant_hybrid_pct."""
        raw_pct = self.any_coverage_fraction * 100.0
        if self.blind_spot_count == 0 and self.total_points > 0:
            return 100.00
        rounded = round(raw_pct, 2)
        if rounded >= 100.0 and raw_pct < 100.0:
            return round(raw_pct, 4)
        return rounded

    @property
    def blind_spot_pct(self) -> float:
        """V60 FIX (P3-3): Blind spot percentage — no rounding to zero.

        Previously, `round(0.00005 * 100, 2) = 0.00` could hide actual blind spots.
        Now returns 4 decimal places when rounding would mask non-zero blind spots.
        """
        raw_pct = self.blind_spot_fraction * 100.0
        if self.blind_spot_count == 0:
            return 0.00  # True zero
        rounded = round(raw_pct, 2)
        if rounded <= 0.0 and raw_pct > 0.0:
            return round(raw_pct, 4)  # Reveal actual blind spot percentage
        return rounded

    @property
    def is_fully_covered(self) -> bool:
        """True if every point has at least one modality (no BLIND_SPOT)."""
        return self.blind_spot_count == 0 and self.total_points > 0

    @property
    def is_nfpa72_compliant(self) -> bool:
        """True if every point is REDUNDANT_HYBRID.

        NFPA 72-2022 §17.8.3.4: For critical applications, detector
        redundancy is required. While the standard does not explicitly
        mandate hybrid (optical + acoustic) redundancy, this represents
        the highest assurance level achievable with dual-modality detection.
        """
        return self.redundant_hybrid_count == self.total_points and self.total_points > 0

    @property
    def has_blind_spots(self) -> bool:
        """True if any BLIND_SPOT exists."""
        return self.blind_spot_count > 0


# ===========================================================================
# Layer 7 Engine
# ===========================================================================


class HybridSurvivabilityEngine:
    """Layer 7: Intersects optical and acoustic coverage on a shared grid.

    Algorithm:
      1. Take Layer 5 CoverageResult (optical) — redundancy_map gives
         which grid points are optically covered and by how many detectors.
      2. For each UGLD sensor, for each grid point, run trace_acoustic_ray
         treating the grid point as a potential leak source.
      3. For each grid point, select the BEST acoustic result (highest SNR).
      4. Classify each point into the 4-state SurvivabilityClass.
      5. Compute aggregate statistics and generate warnings.

    Physical Model:
      We treat each grid point as a potential LEAK SOURCE, not a detector
      position. This is physically correct because UGLD sensors detect the
      ultrasonic noise FROM the leak. The grid represents locations where
      a leak could occur, and we check if any UGLD can hear it.

    Sensor Positions:
      UltrasonicSensor models detection physics (threshold, frequency,
      background noise), NOT spatial placement. Position is site-specific.
      Therefore, sensor_positions is a separate Dict[str, Tuple[x,y,z]]
      mapping sensor IDs to their world coordinates. This preserves
      Separation of Concerns: V23 = physics, Layer 7 = spatial deployment.
    """

    def __init__(
        self,
        leak_spl_at_1m: float = 100.0,
        center_frequency_hz: float = 40_000.0,
        temp_c: float = 40.0,
        relative_humidity_pct: float = 50.0,
    ) -> None:
        """Initialize with UGLD acoustic parameters.

        Args:
            leak_spl_at_1m: Reference SPL of a gas leak at 1m distance (dB).
              Default 100 dB is representative of a 1mm orifice at 10 bar
              per ISA-TR 84.00.07 Table 1. The engineer should override
              this with site-specific values.
            center_frequency_hz: Center frequency for acoustic calculations.
            temp_c: Ambient temperature (Celsius).
            relative_humidity_pct: Relative humidity (%).

        """
        self._leak_spl = leak_spl_at_1m
        self._freq_hz = center_frequency_hz
        self._temp_c = temp_c
        self._rh_pct = relative_humidity_pct

    def analyse(
        self,
        optical_result: CoverageResult,
        grid: List[RayTracePoint],
        ugld_sensors: List[UltrasonicSensor],
        sensor_positions: Dict[str, Tuple[float, float, float]],
        acoustic_obstacles: Optional[List[AcousticObstacle]] = None,
    ) -> HybridSurvivabilityMap:
        """Run hybrid survivability analysis.

        Intersects Layer 5 optical coverage with V23 acoustic coverage
        on the same spatial grid, classifying each point into one of
        4 survivability states.

        Args:
            optical_result: Layer 5 CoverageResult with redundancy_map.
            grid: The shared spatial grid (same list passed to Layer 5).
            ugld_sensors: List of UGLD sensors to test against.
            sensor_positions: Mapping of sensor_id to (x, y, z) world coords.
            acoustic_obstacles: Obstacles for acoustic ray tracing.

        Returns:
            HybridSurvivabilityMap with per-point classification and
            aggregate statistics.

        Raises:
            ValueError: If grid is empty, length mismatch, or missing
              sensor positions.

        """
        # ── Input validation ──────────────────────────────────────────
        if not grid:
            raise ValueError("Grid must not be empty for hybrid analysis.")

        if optical_result.total_points != len(grid):
            raise ValueError(
                f"Grid length ({len(grid)}) does not match optical result "
                f"total_points ({optical_result.total_points}). "
                "The grid must be the same list used for Layer 5 analysis."
            )

        for sensor in ugld_sensors:
            if sensor.sensor_id not in sensor_positions:
                raise ValueError(f"UGLD sensor '{sensor.sensor_id}' has no position in sensor_positions mapping.")

        obstacles = acoustic_obstacles or []
        warnings: List[str] = []

        if not ugld_sensors:
            warnings.append(
                "No UGLD sensors provided — all points classified as OPTICAL_ONLY or BLIND_SPOT (no acoustic analysis)."
            )
            logger.warning("HybridSurvivabilityEngine: no UGLD sensors — falling back to optical-only classification.")

        # ── Step 1: Optical coverage lookup ───────────────────────────
        # redundancy_map: Dict[int, int] → point_index → detector_count
        optical_map: Dict[int, int] = optical_result.redundancy_map

        # ── Step 2: Acoustic analysis per grid point ──────────────────
        # For each grid point (treated as leak source), find the best
        # UGLD sensor result (highest SNR across all sensors).
        acoustic_map: Dict[int, AcousticCoverageDetail] = {}

        for pt_idx, pt in enumerate(grid):
            leak_point = (pt.x, pt.y, pt.z)
            best_detail: Optional[AcousticCoverageDetail] = None
            best_snr = float("-inf")

            for sensor in ugld_sensors:
                sensor_point = sensor_positions[sensor.sensor_id]

                ray_result = trace_acoustic_ray(
                    leak_point=leak_point,
                    sensor_point=sensor_point,
                    obstacles=obstacles,
                    sensor=sensor,
                    leak_spl_at_1m=self._leak_spl,
                    center_frequency_hz=self._freq_hz,
                    temp_c=self._temp_c,
                    relative_humidity_pct=self._rh_pct,
                )

                # Select best sensor for this point (highest SNR)
                if ray_result.trigger_result.snr_db > best_snr:
                    best_snr = ray_result.trigger_result.snr_db
                    best_detail = AcousticCoverageDetail(
                        sensor_id=sensor.sensor_id,
                        triggered=ray_result.trigger_result.triggered,
                        snr_db=ray_result.trigger_result.snr_db,
                        margin_to_threshold_db=(ray_result.trigger_result.margin_to_threshold_db),
                        has_los=ray_result.has_los,
                        total_insertion_loss_db=(ray_result.total_insertion_loss_db),
                        distance_meters=ray_result.distance_meters,
                    )

            if best_detail is not None:
                acoustic_map[pt_idx] = best_detail

        # ── Step 3: Classify each point ───────────────────────────────
        point_results: Dict[int, HybridPointResult] = {}
        counts = {
            SurvivabilityClass.REDUNDANT_HYBRID: 0,
            SurvivabilityClass.OPTICAL_ONLY: 0,
            SurvivabilityClass.ACOUSTIC_ONLY: 0,
            SurvivabilityClass.BLIND_SPOT: 0,
        }

        for pt_idx, pt in enumerate(grid):
            opt_count = optical_map.get(pt_idx, 0)
            opt_covered = opt_count > 0

            ac_detail = acoustic_map.get(pt_idx)
            ac_covered = ac_detail is not None and ac_detail.triggered

            if opt_covered and ac_covered:
                cls = SurvivabilityClass.REDUNDANT_HYBRID
            elif opt_covered and not ac_covered:
                cls = SurvivabilityClass.OPTICAL_ONLY
            elif not opt_covered and ac_covered:
                cls = SurvivabilityClass.ACOUSTIC_ONLY
            else:
                cls = SurvivabilityClass.BLIND_SPOT

            counts[cls] += 1

            # Store acoustic detail only if triggered (avoids storing
            # non-detecting results that would bloat the output).
            point_results[pt_idx] = HybridPointResult(
                point_index=pt_idx,
                x=pt.x,
                y=pt.y,
                z=pt.z,
                survivability_class=cls,
                optical_detector_count=opt_count,
                best_acoustic_detail=(ac_detail if ac_detail and ac_detail.triggered else None),
            )

        # ── Step 4: Compute aggregate statistics ──────────────────────
        total = len(grid)
        rh_count = counts[SurvivabilityClass.REDUNDANT_HYBRID]
        oo_count = counts[SurvivabilityClass.OPTICAL_ONLY]
        ao_count = counts[SurvivabilityClass.ACOUSTIC_ONLY]
        bs_count = counts[SurvivabilityClass.BLIND_SPOT]

        # Diagnostics
        if bs_count > 0:
            blind_pct = round(100.0 * bs_count / total, 1)
            warnings.append(
                f"BLIND_SPOT detected: {bs_count}/{total} points "
                f"({blind_pct}%) have neither optical nor acoustic coverage. "
                "Additional detectors are REQUIRED per NFPA 72 §17.8.3.4."
            )

        if total > 0 and rh_count / total < 0.5:
            warnings.append(
                f"Low hybrid redundancy: only "
                f"{round(100.0 * rh_count / total, 1)}% "
                "of points have dual-modality (optical + acoustic) coverage. "
                "Consider adding UGLD sensors for detection diversity."
            )

        return HybridSurvivabilityMap(
            total_points=total,
            point_results=point_results,
            redundant_hybrid_count=rh_count,
            optical_only_count=oo_count,
            acoustic_only_count=ao_count,
            blind_spot_count=bs_count,
            hybrid_coverage_fraction=(round(rh_count / total, 4) if total else 0.0),
            any_coverage_fraction=(round((rh_count + oo_count + ao_count) / total, 4) if total else 0.0),
            blind_spot_fraction=(round(bs_count / total, 4) if total else 0.0),
            warnings=warnings,
        )

    # ── GAP-2: 3D Heatmap Export ──────────────────────────────────

    def export_heatmap_json(
        self,
        hybrid_map: HybridSurvivabilityMap,
        output_path: str,
    ) -> str:
        """Export HybridSurvivabilityMap to a JSON file consumable by the
        WebGL heatmap viewer (heatmap_viewer.html).

        The JSON schema matches the HybridSurvivabilityMap model exactly:
        - point_results is a Dict[int, HybridPointResult]
        - Each HybridPointResult has: x, y, z, survivability_class,
          optical_detector_count, best_acoustic_detail
        - best_acoustic_detail (if present) has: sensor_id, triggered,
          snr_db, margin_to_threshold_db, has_los, total_insertion_loss_db,
          distance_meters

        Color coding (NFPA 72 convention):
          REDUNDANT_HYBRID -> #00AA44  (green)
          OPTICAL_ONLY     -> #FFD700  (yellow)
          ACOUSTIC_ONLY    -> #FF8C00  (orange)
          BLIND_SPOT       -> #CC0000  (red)

        Args:
            hybrid_map: The HybridSurvivabilityMap to export.
            output_path: Path to write the JSON file.

        Returns:
            Path of the written JSON file.

        """
        COLOR_MAP = {
            SurvivabilityClass.REDUNDANT_HYBRID: "#00AA44",
            SurvivabilityClass.OPTICAL_ONLY: "#FFD700",
            SurvivabilityClass.ACOUSTIC_ONLY: "#FF8C00",
            SurvivabilityClass.BLIND_SPOT: "#CC0000",
        }

        total_pts = hybrid_map.total_points
        cls_counts: Dict[str, int] = {
            "REDUNDANT_HYBRID": 0,
            "OPTICAL_ONLY": 0,
            "ACOUSTIC_ONLY": 0,
            "BLIND_SPOT": 0,
        }

        points_out: List[Dict] = []
        for _pt_idx, pr in hybrid_map.point_results.items():
            cls_str = pr.survivability_class.value
            cls_counts[cls_str] += 1

            # Acoustic detail extraction
            acoustic_snr = None
            if pr.best_acoustic_detail is not None:
                acoustic_snr = pr.best_acoustic_detail.snr_db

            points_out.append(
                {
                    "x": pr.x,
                    "y": pr.y,
                    "z": pr.z,
                    "class": cls_str,
                    "optical_count": pr.optical_detector_count,
                    "acoustic_snr_db": acoustic_snr,
                    "color": COLOR_MAP.get(pr.survivability_class, "#888888"),
                }
            )

        def _pct(n: int) -> float:
            return round(100 * n / total_pts, 2) if total_pts else 0.0

        payload = {
            "meta": {
                "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "version": "FireAI_V24",
                "total_points": total_pts,
                "standards": [
                    "NFPA 72-2022 §17.8.3.4",
                    "ISA-TR 84.00.07",
                ],
            },
            "statistics": {
                "total_points": total_pts,
                "redundant_hybrid_pct": _pct(cls_counts["REDUNDANT_HYBRID"]),
                "optical_only_pct": _pct(cls_counts["OPTICAL_ONLY"]),
                "acoustic_only_pct": _pct(cls_counts["ACOUSTIC_ONLY"]),
                "blind_spot_pct": _pct(cls_counts["BLIND_SPOT"]),
            },
            "class_legend": {
                "REDUNDANT_HYBRID": {
                    "color": "#00AA44",
                    "label": "Redundant (Optical ∩ Acoustic)",
                },
                "OPTICAL_ONLY": {
                    "color": "#FFD700",
                    "label": "Optical coverage only",
                },
                "ACOUSTIC_ONLY": {
                    "color": "#FF8C00",
                    "label": "Acoustic coverage only",
                },
                "BLIND_SPOT": {
                    "color": "#CC0000",
                    "label": "Blind spot — no coverage",
                },
            },
            "points": points_out,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(
            f"Heatmap JSON exported: {output_path} ({total_pts} points, {cls_counts['BLIND_SPOT']} blind spots)"
        )
        return output_path
