"""acoustics_engine.py — Unified Acoustics Integration Engine for FireAI
======================================================================
CRITICAL LIFE-SAFETY MODULE — V25

Integration layer that UNIFIES the existing acoustic capabilities across
three domain modules:

  1. fireai.core.acoustic_calculator  — NFPA 72 §18.4 audible notification
  2. fireai.core.ugld_acoustics       — ISA-TR84.00.07 UGLD free-field physics
  3. fireai.core.ugld_raytrace        — UGLD ray tracing with Maekawa diffraction

This module does NOT duplicate physics calculations. It DELEGATES to the
existing domain modules and adds only the orchestration logic required
to produce unified compliance results across both audible and ultrasonic
domains.

Architectural Role:
  - AcousticsEngine is the SINGLE ENTRY POINT for all acoustic analysis
    in the FireAI platform.
  - Downstream callers (orchestrator, CLI, API) interact ONLY with this
    class — never directly with the domain modules.
  - The domain modules remain independently testable and usable.

Domain Separation (maintained from existing modules):
  - Audible (500-4000 Hz, dBA-weighted, NFPA 72 §18.4)
  - Ultrasonic (25,000-100,000 Hz, dB SPL unweighted, ISA-TR84.00.07)
  These are completely separate physics domains with no overlap.

Standards Referenced:
  NFPA 72-2022       — National Fire Alarm and Signaling Code
    §18.4.1.2        — Maximum sound level 110 dBA
    §18.4.2          — Sleeping areas: 75 dBA at pillow
    §18.4.3          — Public mode: 15 dB above ambient
    §18.4.4          — Private mode: 10 dB above ambient
  ISO 9613-1:1993    — Attenuation of sound during propagation outdoors
  ISO 9613-2:1996    — General method of calculation (Annex A: Maekawa)
  ISA-TR84.00.07     — Augmented safety with acoustic gas leak detection
  IEC 60079-29-4     — Gas detectors performance requirements
  IEC 61508          — Functional safety of electrical/electronic systems

Usage:
    from fireai.core.acoustics_engine import (
        AcousticsEngine,
        AcousticCoverageResult,
        UGLDCoverageResult,
        UGLDDetectionZone,
        UGLDCoverageGap,
    )

    # NFPA 72 audible coverage
    engine = AcousticsEngine()
    result = engine.check_coverage(
        room_id="R-101",
        occ_type="business",
        speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
        check_points=[CheckPoint(x=1, y=1, z=1.5)],
        mode="public",
    )
    assert result.compliant

    # UGLD single-sensor ray trace
    ugld_result = engine.ugld_raytrace(
        leak_point=(2.0, 2.0, 3.0),
        sensor_point=(20.0, 20.0, 2.0),
        sensor=UltrasonicSensor(trigger_threshold_db=74.0),
        leak_spl_at_1m=100.0,
        obstacles=[AcousticObstacle(obstacle_id="TANK-01",
                     vertices=[[5,5,0],[15,15,8]])],
    )

    # UGLD multi-sensor coverage
    multi_result = engine.ugld_multi_sensor_coverage(
        leak_points=[(2.0, 2.0, 3.0), (10.0, 5.0, 1.5)],
        sensor_points=[(5.0, 5.0, 3.0), (25.0, 15.0, 3.0)],
        sensors=[sensor_a, sensor_b],
        obstacles=obstacles,
        area_bounds=((0,0,0), (30,30,10)),
    )
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Delegation imports — ALL physics lives in domain modules, NOT here.
# ---------------------------------------------------------------------------
# Audible notification (NFPA 72 §18.4) — acoustic_calculator
from fireai.core.acoustic_calculator import (
    AUDIBLE_REQUIREMENTS,
    AcousticSPLCalculator,
    Barrier,
    CheckPoint,
    RoomAcousticResult,
    Speaker,
)

# UGLD free-field physics (ISA-TR84.00.07) — ugld_acoustics
from fireai.core.ugld_acoustics import (
    AcousticPropagation,
    UltrasonicSensor,
    atmospheric_attenuation_db_per_m,
    max_detection_range_m,
)

# UGLD ray tracing with Maekawa diffraction (ISA-TR84.00.07) — ugld_raytrace
from fireai.core.ugld_raytrace import (
    AcousticObstacle,
    AcousticRayResult,
    trace_acoustic_ray,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Module-level Constants
# ============================================================================

# UGLD defaults per ISA-TR84.00.07 / ISO 9613-1
#: Default UGLD center frequency (Hz) — most common for commercial sensors.
UGLD_CENTER_FREQUENCY_HZ: float = 40_000.0

#: Conservative air absorption at 40 kHz per ISO 9613-1.
#: The atmospheric_attenuation_db_per_m() function computes ~0.5 dB/m at
#: 20 °C / 50 % RH, but 1.5 dB/m accounts for higher-temperature industrial
#: conditions and additional scattering losses not captured by pure molecular
#: absorption.  Used as a default override when callers need a conservative
#: design margin per ISA-TR84.00.07 §4.3.2.
UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M: float = 1.5

#: Minimum SNR for reliable UGLD detection (dB).
#: 6 dB = signal 4x noise power.  ISA-TR84.00.07, IEC 61508.
UGLD_MIN_SNR_DB: float = 6.0

# NFPA 72-2022 audible notification thresholds
NFPA72_PUBLIC_MODE_ABOVE_AMBIENT_DB: float = 15.0  # §18.4.3
NFPA72_PRIVATE_MODE_ABOVE_AMBIENT_DB: float = 10.0  # §18.4.4
NFPA72_SLEEPING_ABSOLUTE_MIN_DBA: float = 75.0  # §18.4.2
NFPA72_MAX_DBA: float = 110.0  # §18.4.1.2

#: Typical ceiling absorption coefficient for industrial spaces at
#: ultrasonic frequencies.  Concrete/steel deck ≈ 0.03-0.05.
#: Source: Beranek & Ver (1992), ISO 9613-2:1996 §7.
DEFAULT_CEILING_ABSORPTION_COEFF: float = 0.04


# ============================================================================
# Result Dataclasses
# ============================================================================


@dataclass
class AcousticCoverageResult:
    """NFPA 72 §18.4 audible notification coverage verification result.

    Aggregates compliance status across all evaluated check points in a
    room (or set of rooms), providing per-point detail and an overall
    PASS / FAIL verdict.

    Attributes:
        compliant: True only if EVERY check point meets the applicable
            NFPA 72 §18.4 requirement AND no point exceeds the 110 dBA
            maximum per §18.4.1.2.
        mode: Audible mode — ``"public"`` (§18.4.3), ``"private"``
            (§18.4.4), or ``"sleeping"`` (§18.4.2).
        required_dba: Minimum required SPL at the worst check point.
        worst_spl_dba: SPL at the worst (lowest-SPL) check point.
        worst_room_id: Identifier of the room containing the worst point.
        worst_point_label: Label of the worst check point.
        margin_dba: ``worst_spl_dba - required_dba``.  Negative = deficit.
        violations: Human-readable violation descriptions for audit trail.
        room_results: Per-room detailed results delegated from
            :class:`AcousticSPLCalculator`.
        nfpa_sections_referenced: NFPA 72 sections checked during analysis.

    """

    compliant: bool
    mode: str
    required_dba: float
    worst_spl_dba: float
    worst_room_id: str
    worst_point_label: str
    margin_dba: float
    violations: List[str]
    room_results: List[RoomAcousticResult]
    nfpa_sections_referenced: List[str] = field(default_factory=list)


@dataclass
class UGLDDetectionZone:
    """Coverage zone for a single UGLD sensor-leak pair.

    Produced during multi-sensor coverage analysis to describe whether a
    specific sensor can detect a specific leak, and under what acoustic
    conditions.

    Attributes:
        sensor_id: Unique identifier of the UGLD sensor.
        leak_point: (x, y, z) coordinates of the evaluated leak source.
        detected: True if the sensor will reliably detect this leak
            (both trigger-threshold AND SNR conditions met per
            ISA-TR84.00.07).
        detection_range_m: Maximum free-field detection range for this
            sensor/leak combination (from :func:`max_detection_range_m`).
        final_spl_db: SPL arriving at the sensor after all propagation
            losses and obstacle attenuation.
        has_los: True if direct line-of-sight is clear (no obstacles).
        total_insertion_loss_db: Sum of Maekawa IL from all intersected
            obstacles (0.0 if LOS is clear).
        obstacle_count: Number of obstacles intersecting the ray path.

    """

    sensor_id: str
    leak_point: Tuple[float, float, float]
    detected: bool
    detection_range_m: float
    final_spl_db: float
    has_los: bool
    total_insertion_loss_db: float
    obstacle_count: int


@dataclass
class UGLDCoverageGap:
    """A leak-source location not adequately covered by any UGLD sensor.

    Represents a gap in the multi-sensor coverage map where no single
    sensor can reliably detect a postulated leak.  These gaps must be
    resolved by adding sensors or repositioning existing ones.

    Attributes:
        leak_point: (x, y, z) of the uncovered leak location.
        nearest_sensor_id: ID of the closest sensor (even though it
            cannot detect the leak).
        nearest_sensor_distance_m: Distance to the nearest sensor.
        spl_at_nearest_sensor_db: SPL arriving at the nearest sensor
            after all propagation losses.
        deficit_db: How far below the detection threshold the signal is
            at the nearest sensor.  Positive = deficit.

    """

    leak_point: Tuple[float, float, float]
    nearest_sensor_id: str
    nearest_sensor_distance_m: float
    spl_at_nearest_sensor_db: float
    deficit_db: float


@dataclass
class UGLDCoverageResult:
    """Multi-sensor UGLD coverage analysis result per ISA-TR84.00.07.

    Provides a unified view of detection capability across all sensors
    for all evaluated leak-source locations.

    Attributes:
        fully_covered: True only if every leak point is detectable by at
            least one sensor.
        sensors_evaluated: Number of UGLD sensors in the analysis.
        leak_points_evaluated: Number of postulated leak locations.
        detection_zones: Per-sensor/leak detection results.
        coverage_gaps: Leak locations not covered by any sensor.
        ray_results: Raw :class:`AcousticRayResult` for every
            sensor-leak ray trace (including ceiling-reflection rays).
        combined_detection_area_m2: Estimated area covered by at least
            one sensor, based on maximum detection ranges.
        total_area_m2: Total floor area of the evaluated region.
        ceiling_reflections_used: Whether image-source ceiling
            reflections were included in the analysis.

    """

    fully_covered: bool
    sensors_evaluated: int
    leak_points_evaluated: int
    detection_zones: List[UGLDDetectionZone]
    coverage_gaps: List[UGLDCoverageGap]
    ray_results: List[AcousticRayResult]
    combined_detection_area_m2: float
    total_area_m2: float
    ceiling_reflections_used: bool


# ============================================================================
# Image-Source Ceiling Reflection (UGLD)
# ============================================================================


def _image_source_reflection_spl(
    leak_point: Tuple[float, float, float],
    sensor_point: Tuple[float, float, float],
    ceiling_z: float,
    leak_spl_at_1m: float,
    center_frequency_hz: float,
    temp_c: float = 40.0,
    relative_humidity_pct: float = 50.0,
    ceiling_absorption_coeff: float = DEFAULT_CEILING_ABSORPTION_COEFF,
) -> float:
    """Calculate the SPL contribution from a first-order ceiling reflection.

    Uses the **image source method**: the ceiling reflection is modelled by
    placing a virtual (image) source at the mirror position of the real
    source across the ceiling plane, then computing free-field propagation
    from the image source to the receiver.

    The image source position is::

        image_z = 2 * ceiling_z - leak_z

    The reflected path length equals the distance from the image source to
    the sensor.  Ceiling absorption reduces the reflected energy by
    ``10 * log10(1 - alpha)`` where alpha is the absorption coefficient.

    At ultrasonic frequencies (25-100 kHz), industrial ceilings (concrete,
    steel deck) are highly reflective (alpha ~ 0.03-0.05), so the reflected
    SPL can be significant and must not be ignored for conservative design.

    Args:
        leak_point: (x, y, z) of the gas leak source.
        sensor_point: (x, y, z) of the UGLD sensor.
        ceiling_z: Z-coordinate of the ceiling plane (metres).
        leak_spl_at_1m: Source SPL at 1 m reference distance (dB SPL).
        center_frequency_hz: Center frequency (Hz).
        temp_c: Ambient temperature (degrees C).
        relative_humidity_pct: Relative humidity (%).
        ceiling_absorption_coeff: Ceiling absorption coefficient alpha at
            ultrasonic frequencies (default 0.04 for concrete/steel deck).

    Returns:
        Reflected-path SPL at the sensor in dB SPL.  Always >= 0.

    Reference:
        ISO 9613-2:1996 §7 (image source method),
        Beranek & Ver (1992) Chapter 7.

    """
    # Mirror the leak source across the ceiling plane
    image_x = leak_point[0]
    image_y = leak_point[1]
    image_z = 2.0 * ceiling_z - leak_point[2]

    # Distance from image source to sensor
    dx = sensor_point[0] - image_x
    dy = sensor_point[1] - image_y
    dz = sensor_point[2] - image_z
    reflected_distance = math.sqrt(dx * dx + dy * dy + dz * dz)

    if reflected_distance < 1e-9:
        return leak_spl_at_1m

    # Delegate to ugld_acoustics for free-field propagation
    prop = AcousticPropagation(
        leak_spl_at_1m=leak_spl_at_1m,
        distance_meters=reflected_distance,
        center_frequency_hz=center_frequency_hz,
        temp_c=temp_c,
        relative_humidity_pct=relative_humidity_pct,
    )

    # Apply ceiling absorption: reflection reduces energy by (1 - alpha)
    # In dB: reflection_loss = -10 * log10(1 - alpha)
    # V65 SAFETY: Negative absorption coefficient is physically meaningless.
    # It would produce log10(>1) = negative loss, ADDING energy — violates
    # energy conservation and is physically impossible.
    if ceiling_absorption_coeff < 0:
        raise ValueError(
            f"ceiling_absorption_coeff must be >= 0, got {ceiling_absorption_coeff}. "
            f"Negative absorption would add energy (violates conservation)."
        )
    if ceiling_absorption_coeff >= 1.0:
        # Perfect absorber — no reflection
        return 0.0
    reflection_loss_db = -10.0 * math.log10(1.0 - ceiling_absorption_coeff)
    reflected_spl = prop.final_spl_db - reflection_loss_db

    return max(0.0, reflected_spl)


def _combine_spl_db(spl_a: float, spl_b: float) -> float:
    """Energetically add two SPL values (logarithmic addition).

    SPL_total = 10 * log10(10^(A/10) + 10^(B/10))

    Args:
        spl_a: First SPL value (dB).
        spl_b: Second SPL value (dB).

    Returns:
        Combined SPL in dB.

    """
    # V65 SAFETY: Guard against NaN/Inf inputs.
    # NaN SPL silently bypasses compliance checks (NaN < threshold is False).
    if not math.isfinite(spl_a) and not math.isfinite(spl_b):
        return 0.0
    if not math.isfinite(spl_a):
        return spl_b if math.isfinite(spl_b) else 0.0
    if not math.isfinite(spl_b):
        return spl_a
    if spl_a <= 0.0 and spl_b <= 0.0:
        return 0.0
    result = 10.0 * math.log10(math.pow(10, spl_a / 10.0) + math.pow(10, spl_b / 10.0))
    # V65 SAFETY: Guard result against overflow
    if not math.isfinite(result):
        return max(spl_a, spl_b)
    return result


def _evaluate_ugld_trigger(
    final_spl: float,
    sensor: UltrasonicSensor,
) -> Tuple[bool, float]:
    """Evaluate whether a UGLD sensor triggers for a given final SPL.

    A sensor triggers only if BOTH conditions are met:
      1. final_spl >= sensor trigger threshold (hardware limit)
      2. SNR >= 6 dB (ISA-TR84.00.07 minimum)

    Args:
        final_spl: SPL at the sensor position (dB SPL).
        sensor: UGLD sensor specification.

    Returns:
        Tuple of (detected: bool, deficit_db: float).
        deficit_db is 0.0 when detected, positive when not detected.

    """
    snr = final_spl - sensor.background_noise_db
    threshold_met = final_spl >= sensor.trigger_threshold_db
    snr_met = snr >= UGLD_MIN_SNR_DB
    detected = threshold_met and snr_met

    if detected:
        return True, 0.0

    # Compute deficit (whichever condition is further from passing)
    threshold_deficit = max(0.0, sensor.trigger_threshold_db - final_spl)
    snr_deficit = max(0.0, UGLD_MIN_SNR_DB - snr)
    deficit = max(threshold_deficit, snr_deficit)
    return False, deficit


# ============================================================================
# AcousticsEngine — Unified Integration Layer
# ============================================================================


class AcousticsEngine:
    """Unified acoustics integration engine combining NFPA 72 audible
    notification coverage verification and ISA-TR84.00.07 UGLD detection.

    This class is the **single entry point** for all acoustic analysis in
    the FireAI platform.  It orchestrates calls to three domain modules:

    - :mod:`fireai.core.acoustic_calculator` for NFPA 72 §18.4 SPL
      calculations and audibility compliance.
    - :mod:`fireai.core.ugld_acoustics` for UGLD free-field propagation
      (inverse square law + atmospheric absorption).
    - :mod:`fireai.core.ugld_raytrace` for obstacle shadowing and Maekawa
      barrier diffraction.

    No physics is duplicated here — every calculation delegates to the
    appropriate domain module.  This class adds only:

    1. **Orchestration**: combining results from multiple domain modules.
    2. **Unified results**: :class:`AcousticCoverageResult` and
       :class:`UGLDCoverageResult` that span both domains.
    3. **Ceiling reflections**: image-source method for UGLD (not in any
       domain module because it requires spatial context this layer owns).
    4. **Multi-sensor coverage**: cross-sensor detection zone merging.

    Usage::

        engine = AcousticsEngine()

        # --- NFPA 72 Audible Coverage ---
        cov = engine.check_coverage(
            room_id="R-101",
            occ_type="business",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=1, y=1, z=1.5)],
            mode="public",
        )

        # --- UGLD Single-Sensor Ray Trace ---
        ugld = engine.ugld_raytrace(
            leak_point=(2.0, 2.0, 3.0),
            sensor_point=(20.0, 20.0, 2.0),
            sensor=UltrasonicSensor(trigger_threshold_db=74.0),
            leak_spl_at_1m=100.0,
            obstacles=[AcousticObstacle(
                obstacle_id="TANK-01",
                vertices=[[5,5,0],[15,15,8]],
            )],
        )

        # --- UGLD Multi-Sensor Coverage ---
        multi = engine.ugld_multi_sensor_coverage(
            leak_points=[(2,2,3), (10,5,1.5)],
            sensor_points=[(5,5,3), (25,15,3)],
            sensors=[sensor_a, sensor_b],
            obstacles=obstacles,
            area_bounds=((0,0,0), (30,30,10)),
        )
    """

    def __init__(
        self,
        room_ambient_noise: Optional[Dict[str, float]] = None,
    ) -> None:
        """Initialize the unified acoustics engine.

        Args:
            room_ambient_noise: Optional mapping of occupancy type to
                ambient noise level (dBA).  If ``None``, defaults from
                :data:`acoustic_calculator.AMBIENT_NOISE_LEVELS` are used.
                Passed through to the internal
                :class:`AcousticSPLCalculator`.

        """
        self._spl_calculator = AcousticSPLCalculator(
            room_ambient_noise=room_ambient_noise,
        )
        logger.info("AcousticsEngine initialized (unified audible + UGLD).")

    # ------------------------------------------------------------------
    # NFPA 72 §18.4 — Audible Notification Coverage
    # ------------------------------------------------------------------

    def check_coverage(
        self,
        room_id: str,
        occ_type: str,
        speakers: List[Speaker],
        check_points: List[CheckPoint],
        barriers: Optional[List[Barrier]] = None,
        mode: str = "public",
        room_absorption_m2: Optional[float] = None,
        room_volume_m3: Optional[float] = None,
    ) -> AcousticCoverageResult:
        """Verify NFPA 72 §18.4 audible notification coverage.

        Delegates SPL calculation to :class:`AcousticSPLCalculator` and
        aggregates the result into a unified :class:`AcousticCoverageResult`
        with compliance status and detailed violation information.

        The following NFPA 72-2022 requirements are checked:

        - **§18.4.3** Public mode: minimum 15 dB above average ambient.
        - **§18.4.4** Private mode: minimum 10 dB above ambient, 45 dBA
          absolute minimum.
        - **§18.4.2** Sleeping areas: minimum 75 dBA at pillow level.
        - **§18.4.1.2** Maximum 110 dBA at minimum distance.

        SPL calculation uses the inverse square law::

            Lp(d) = Lp(ref) - 20 * log10(d / d_ref)

        with optional Sabine room constant correction for the reverberant
        field (Hopkins-Stryker equation)::

            Lp_total = 10 * log10(10^(Ld/10) + 10^(Lr/10))

        where the reverberant contribution depends on room absorption *A*
        (m² Sabine)::

            Lr = Lp(ref) + 10 * log10(4 / A)

        Args:
            room_id: Unique room identifier for audit trail.
            occ_type: Occupancy type (e.g. ``"business"``,
                ``"mechanical_room"``, ``"sleeping_area"``).
            speakers: List of :class:`Speaker` objects with 3D positions
                and ratings.
            check_points: List of :class:`CheckPoint` objects where SPL
                is evaluated.
            barriers: Optional list of :class:`Barrier` objects between
                speakers and check points.
            mode: Audible mode — ``"public"`` (§18.4.3), ``"private"``
                (§18.4.4), or ``"sleeping"`` (§18.4.2).
            room_absorption_m2: Room absorption in m² Sabine
                (*A* = alpha * *S*).  If ``None``, only direct sound is
                considered.
            room_volume_m3: Room volume in m³ (unused by calculator but
                reserved for future reverberation-time corrections).

        Returns:
            :class:`AcousticCoverageResult` with compliance status.

        Raises:
            ValueError: If ``speakers`` or ``check_points`` is empty, or
                ``mode`` is invalid.

        Reference:
            NFPA 72-2022 §18.4, ISO 9613-1:1993 §5.2

        """
        # ── Input validation ──────────────────────────────────────────
        if not speakers:
            raise ValueError(
                "check_coverage requires at least one Speaker. An empty speaker list produces undefined SPL."
            )
        if not check_points:
            raise ValueError(
                "check_coverage requires at least one CheckPoint. "
                "Without evaluation points, coverage cannot be verified."
            )
        valid_modes = set(AUDIBLE_REQUIREMENTS.keys())
        if mode not in valid_modes:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of {sorted(valid_modes)}. "
                f"Defaulting to 'public' is not permitted for life-safety "
                f"checks — the caller must explicitly choose the correct "
                f"mode per NFPA 72 §18.4."
            )

        logger.info(
            "check_coverage: room=%s mode=%s speakers=%d points=%d",
            room_id,
            mode,
            len(speakers),
            len(check_points),
        )

        # ── Delegate to AcousticSPLCalculator ────────────────────────
        room_result: RoomAcousticResult = self._spl_calculator.calculate_room_spl(
            room_id=room_id,
            occ_type=occ_type,
            speakers=speakers,
            check_points=check_points,
            barriers=barriers,
            mode=mode,
            room_absorption_m2=room_absorption_m2,
        )

        # ── Aggregate NFPA 72 compliance ─────────────────────────────
        _min_above_ambient, _absolute_min, nfpa_section = AUDIBLE_REQUIREMENTS[mode]

        violations: List[str] = []
        for v in room_result.violations:
            # RoomAcousticResult.violations are dicts with 'message' key
            if isinstance(v, dict):
                violations.append(str(v.get("message", v)))
            else:
                violations.append(str(v))

        # Additional validation: sleeping-area absolute minimum
        if mode == "sleeping" and room_result.worst_point_spl < NFPA72_SLEEPING_ABSOLUTE_MIN_DBA:
            violations.append(
                f"Sleeping area SPL {room_result.worst_point_spl:.1f} dBA "
                f"is below the absolute minimum "
                f"{NFPA72_SLEEPING_ABSOLUTE_MIN_DBA:.0f} dBA required by "
                f"NFPA 72 §18.4.2."
            )

        # Maximum level check (may already be in room_result.violations
        # but we verify explicitly for the unified result)
        if room_result.worst_point_spl > NFPA72_MAX_DBA:
            violations.append(
                f"Sound level {room_result.worst_point_spl:.1f} dBA "
                f"exceeds maximum {NFPA72_MAX_DBA:.0f} dBA per "
                f"NFPA 72 §18.4.1.2."
            )

        # Collect all referenced NFPA 72 sections
        nfpa_sections = [nfpa_section, "§18.4.1.2"]
        if mode == "sleeping":
            nfpa_sections.append("§18.4.2")

        compliant = room_result.compliant and len(violations) == 0

        result = AcousticCoverageResult(
            compliant=compliant,
            mode=mode,
            required_dba=room_result.required_dba,
            worst_spl_dba=room_result.worst_point_spl,
            worst_room_id=room_id,
            worst_point_label=room_result.worst_point_label,
            margin_dba=room_result.margin_dba,
            violations=violations,
            room_results=[room_result],
            nfpa_sections_referenced=nfpa_sections,
        )

        if compliant:
            logger.info(
                "check_coverage PASS: room=%s margin=%.1f dB",
                room_id,
                result.margin_dba,
            )
        else:
            logger.warning(
                "check_coverage FAIL: room=%s violations=%d",
                room_id,
                len(violations),
            )

        return result

    # ------------------------------------------------------------------
    # ISA-TR84.00.07 — UGLD Ray Trace (Single Sensor)
    # ------------------------------------------------------------------

    def ugld_raytrace(
        self,
        leak_point: Tuple[float, float, float],
        sensor_point: Tuple[float, float, float],
        sensor: UltrasonicSensor,
        leak_spl_at_1m: float,
        obstacles: Optional[List[AcousticObstacle]] = None,
        center_frequency_hz: float = UGLD_CENTER_FREQUENCY_HZ,
        temp_c: float = 40.0,
        relative_humidity_pct: float = 50.0,
        include_ceiling_reflection: bool = False,
        ceiling_z: Optional[float] = None,
        ceiling_absorption_coeff: float = DEFAULT_CEILING_ABSORPTION_COEFF,
        use_conservative_absorption: bool = False,
    ) -> UGLDCoverageResult:
        """ISA-TR84.00.07 ultrasonic gas leak detection ray tracing.

        Traces an acoustic ray from a postulated gas leak to a UGLD sensor,
        computing:

        1. **Free-field propagation**: inverse square law + atmospheric
           absorption via :class:`AcousticPropagation`.
        2. **Obstacle shadowing**: AABB intersection via slab method,
           with **Maekawa barrier diffraction model** (NOT flat -20 dB)
           per ISO 9613-2:1996 Annex A.
        3. **Ceiling reflection** (optional): first-order image source
           method — the reflected path adds SPL at the sensor via
           logarithmic addition.

        The 40 kHz center frequency and 1.5 dB/m air absorption (at 40 kHz,
        ISO 9613-1) are the defaults per ISA-TR84.00.07.  The existing
        :func:`atmospheric_attenuation_db_per_m` computes frequency-,
        temperature-, and humidity-dependent values; the conservative
        1.5 dB/m override is available via
        ``use_conservative_absorption=True``.

        Args:
            leak_point: (x, y, z) of the gas leak source (metres).
            sensor_point: (x, y, z) of the UGLD sensor (metres).
            sensor: :class:`UltrasonicSensor` configuration.
            leak_spl_at_1m: Source SPL at 1 m reference distance (dB SPL).
            obstacles: List of :class:`AcousticObstacle` objects.
                Empty list (or ``None``) = free-field.
            center_frequency_hz: Center frequency (Hz). Default 40 kHz.
            temp_c: Ambient temperature (degrees C). Must be consistent
                with EnvironmentalContext.ambient_temp_c to avoid
                Dual-Path Inconsistency.
            relative_humidity_pct: Relative humidity (%).
            include_ceiling_reflection: Include first-order image-source
                ceiling reflection in the SPL calculation.
            ceiling_z: Z-coordinate of the ceiling plane (metres).
                Required if ``include_ceiling_reflection`` is True.
            ceiling_absorption_coeff: Ceiling absorption coefficient alpha
                at ultrasonic frequencies. Default 0.04 (concrete/steel
                deck).
            use_conservative_absorption: If True, override the ISO 9613-1
                computed air absorption with the conservative value of
                1.5 dB/m at 40 kHz.

        Returns:
            :class:`UGLDCoverageResult` with single-sensor detection zone.

        Raises:
            ValueError: If ``leak_spl_at_1m`` is non-positive, or
                ceiling reflection requested without ``ceiling_z``.

        Reference:
            ISA-TR84.00.07 §4.3, ISO 9613-1:1993 §6,
            ISO 9613-2:1996 Annex A (Maekawa),
            IEC 60079-29-4

        """
        # ── Input validation ──────────────────────────────────────────
        if leak_spl_at_1m <= 0:
            raise ValueError(
                f"leak_spl_at_1m must be positive, got {leak_spl_at_1m}. "
                "A non-positive source level is physically meaningless."
            )
        if include_ceiling_reflection and ceiling_z is None:
            raise ValueError(
                "ceiling_z is required when include_ceiling_reflection=True. "
                "The image source method requires the ceiling plane height."
            )

        obstacles = obstacles or []

        logger.info(
            "ugld_raytrace: leak=%s sensor=%s obstacles=%d ceiling_refl=%s",
            leak_point,
            sensor_point,
            len(obstacles),
            include_ceiling_reflection,
        )

        # ── 1. Direct-path ray trace (delegates to ugld_raytrace) ────
        direct_result: AcousticRayResult = trace_acoustic_ray(
            leak_point=leak_point,
            sensor_point=sensor_point,
            obstacles=obstacles,
            sensor=sensor,
            leak_spl_at_1m=leak_spl_at_1m,
            center_frequency_hz=center_frequency_hz,
            temp_c=temp_c,
            relative_humidity_pct=relative_humidity_pct,
        )

        # ── 2. Optional: apply conservative air absorption override ───
        adjusted_spl = direct_result.final_spl_db
        if use_conservative_absorption:
            computed_alpha = atmospheric_attenuation_db_per_m(
                center_frequency_hz=center_frequency_hz,
                temp_c=temp_c,
                relative_humidity_pct=relative_humidity_pct,
            )
            extra_absorption = UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M - computed_alpha
            if extra_absorption > 0:
                additional_loss = extra_absorption * direct_result.distance_meters
                adjusted_spl = direct_result.final_spl_db - additional_loss
                logger.debug(
                    "Conservative absorption override: +%.3f dB/m -> additional loss %.1f dB over %.1f m",
                    extra_absorption,
                    additional_loss,
                    direct_result.distance_meters,
                )
            else:
                logger.debug(
                    "Computed absorption (%.3f dB/m) already exceeds "
                    "conservative value (%.1f dB/m). No override applied.",
                    computed_alpha,
                    UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M,
                )

        # ── 3. Optional: ceiling reflection (image source method) ─────
        ceiling_reflections_used = False
        combined_spl = adjusted_spl
        if include_ceiling_reflection and ceiling_z is not None:
            reflected_spl = _image_source_reflection_spl(
                leak_point=leak_point,
                sensor_point=sensor_point,
                ceiling_z=ceiling_z,
                leak_spl_at_1m=leak_spl_at_1m,
                center_frequency_hz=center_frequency_hz,
                temp_c=temp_c,
                relative_humidity_pct=relative_humidity_pct,
                ceiling_absorption_coeff=ceiling_absorption_coeff,
            )
            combined_spl = _combine_spl_db(adjusted_spl, reflected_spl)
            ceiling_reflections_used = True
            logger.debug(
                "Ceiling reflection: direct=%.1f dB, reflected=%.1f dB, combined=%.1f dB",
                adjusted_spl,
                reflected_spl,
                combined_spl,
            )

        # ── 4. Re-evaluate trigger status with combined SPL ───────────
        # The direct_result.trigger_result was computed by
        # trace_acoustic_ray using the direct-path SPL.  If we added
        # ceiling reflection or conservative absorption, we must
        # re-evaluate.
        if ceiling_reflections_used or use_conservative_absorption:
            detected, _deficit = _evaluate_ugld_trigger(
                combined_spl,
                sensor,
            )
        else:
            detected = direct_result.trigger_result.triggered

        # ── 5. Build detection zone ───────────────────────────────────
        detection_range = max_detection_range_m(
            leak_spl_at_1m=leak_spl_at_1m,
            sensor=sensor,
            temp_c=temp_c,
            relative_humidity_pct=relative_humidity_pct,
        )

        detection_zone = UGLDDetectionZone(
            sensor_id=sensor.sensor_id,
            leak_point=leak_point,
            detected=detected,
            detection_range_m=detection_range,
            final_spl_db=round(combined_spl, 1),
            has_los=direct_result.has_los,
            total_insertion_loss_db=direct_result.total_insertion_loss_db,
            obstacle_count=direct_result.obstacle_intersections,
        )

        # ── 6. Build coverage result ──────────────────────────────────
        coverage_gaps: List[UGLDCoverageGap] = []
        if not detected:
            _det, deficit = _evaluate_ugld_trigger(combined_spl, sensor)
            coverage_gaps.append(
                UGLDCoverageGap(
                    leak_point=leak_point,
                    nearest_sensor_id=sensor.sensor_id,
                    nearest_sensor_distance_m=direct_result.distance_meters,
                    spl_at_nearest_sensor_db=round(combined_spl, 1),
                    deficit_db=round(deficit, 1),
                )
            )

        result = UGLDCoverageResult(
            fully_covered=detected,
            sensors_evaluated=1,
            leak_points_evaluated=1,
            detection_zones=[detection_zone],
            coverage_gaps=coverage_gaps,
            ray_results=[direct_result],
            combined_detection_area_m2=0.0,  # Single sensor: no area calc
            total_area_m2=0.0,
            ceiling_reflections_used=ceiling_reflections_used,
        )

        if detected:
            logger.info(
                "ugld_raytrace DETECTED: sensor=%s spl=%.1f dB snr=%.1f dB",
                sensor.sensor_id,
                combined_spl,
                combined_spl - sensor.background_noise_db,
            )
        else:
            logger.warning(
                "ugld_raytrace NOT DETECTED: sensor=%s spl=%.1f dB",
                sensor.sensor_id,
                combined_spl,
            )

        return result

    # ------------------------------------------------------------------
    # ISA-TR84.00.07 — Multi-Sensor UGLD Coverage
    # ------------------------------------------------------------------

    def ugld_multi_sensor_coverage(
        self,
        leak_points: List[Tuple[float, float, float]],
        sensor_points: List[Tuple[float, float, float]],
        sensors: List[UltrasonicSensor],
        obstacles: Optional[List[AcousticObstacle]] = None,
        area_bounds: Optional[
            Tuple[
                Tuple[float, float, float],
                Tuple[float, float, float],
            ]
        ] = None,
        leak_spl_at_1m: float = 100.0,
        center_frequency_hz: float = UGLD_CENTER_FREQUENCY_HZ,
        temp_c: float = 40.0,
        relative_humidity_pct: float = 50.0,
        include_ceiling_reflection: bool = False,
        ceiling_z: Optional[float] = None,
        ceiling_absorption_coeff: float = DEFAULT_CEILING_ABSORPTION_COEFF,
        use_conservative_absorption: bool = False,
    ) -> UGLDCoverageResult:
        """Multi-sensor UGLD coverage analysis per ISA-TR84.00.07.

        Evaluates every postulated leak point against every UGLD sensor,
        building a combined coverage map.  A leak point is considered
        **covered** if **at least one** sensor can reliably detect it
        (both trigger-threshold AND minimum-SNR conditions met per
        ISA-TR84.00.07).

        For each sensor-leak pair, the method:

        1. Traces a direct-path ray via :func:`trace_acoustic_ray`
           (obstacle shadowing + Maekawa diffraction).
        2. Optionally adds a ceiling-reflection contribution via the
           image source method.
        3. Optionally applies conservative air absorption (1.5 dB/m at
           40 kHz per ISO 9613-1).
        4. Evaluates trigger status (threshold + SNR).

        The combined detection area is estimated by summing the circular
        coverage areas (pi * r^2) of each sensor, where *r* is the
        maximum free-field detection range from
        :func:`max_detection_range_m`.

        Args:
            leak_points: List of (x, y, z) postulated leak source
                locations.
            sensor_points: List of (x, y, z) sensor positions.  Must be
                the same length as ``sensors``.
            sensors: List of :class:`UltrasonicSensor` specification
                objects.  Must be the same length as ``sensor_points``.
            obstacles: Optional list of :class:`AcousticObstacle` objects.
            area_bounds: ``((x_min, y_min, z_min), (x_max, y_max, z_max))``
                defining the evaluation region for area calculations.
            leak_spl_at_1m: Source SPL at 1 m for all leak points (dB SPL).
            center_frequency_hz: Center frequency (Hz). Default 40 kHz.
            temp_c: Ambient temperature (degrees C).
            relative_humidity_pct: Relative humidity (%).
            include_ceiling_reflection: Include first-order image-source
                ceiling reflection in SPL calculations.
            ceiling_z: Z-coordinate of the ceiling plane.  Required if
                ``include_ceiling_reflection`` is True.
            ceiling_absorption_coeff: Ceiling absorption coefficient at
                ultrasonic frequencies. Default 0.04 (concrete/steel deck).
            use_conservative_absorption: Override computed air absorption
                with conservative 1.5 dB/m at 40 kHz.

        Returns:
            :class:`UGLDCoverageResult` with per-sensor/leak detection
            zones, coverage gaps, and combined detection area.

        Raises:
            ValueError: If inputs are invalid or missing required
                parameters.

        Reference:
            ISA-TR84.00.07 §4.3, ISO 9613-1:1993 §6,
            ISO 9613-2:1996 Annex A, IEC 60079-29-4

        """
        # ── Input validation ──────────────────────────────────────────
        if not leak_points:
            raise ValueError(
                "ugld_multi_sensor_coverage requires at least one leak "
                "point. Without leak sources, coverage cannot be evaluated."
            )
        if not sensors:
            raise ValueError(
                "ugld_multi_sensor_coverage requires at least one sensor. Without sensors, no detection is possible."
            )
        if len(sensor_points) != len(sensors):
            raise ValueError(
                f"sensor_points length ({len(sensor_points)}) must match "
                f"sensors length ({len(sensors)}). Each sensor needs a "
                f"corresponding position."
            )
        if leak_spl_at_1m <= 0:
            raise ValueError(
                f"leak_spl_at_1m must be positive, got {leak_spl_at_1m}. "
                "A non-positive source level is physically meaningless."
            )
        if include_ceiling_reflection and ceiling_z is None:
            raise ValueError(
                "ceiling_z is required when include_ceiling_reflection=True."
                " The image source method requires the ceiling plane height."
            )

        obstacles = obstacles or []
        logger.info(
            "ugld_multi_sensor_coverage: leaks=%d sensors=%d obstacles=%d",
            len(leak_points),
            len(sensors),
            len(obstacles),
        )

        # ── Per-sensor/leak ray tracing ──────────────────────────────
        all_ray_results: List[AcousticRayResult] = []
        detection_zones: List[UGLDDetectionZone] = []
        ceiling_reflections_used = False

        # Track per-leak-point best detection (for gap analysis)
        # key: leak_index -> (best_spl, best_sensor_id, best_distance,
        #                      detected_by_any)
        leak_best: Dict[int, Tuple[float, str, float, bool]] = {}

        for leak_idx, leak_pt in enumerate(leak_points):
            best_spl = -999.0
            best_sensor_id = ""
            best_distance = float("inf")
            detected_by_any = False

            for sensor_idx, sensor in enumerate(sensors):
                spt = sensor_points[sensor_idx]

                # ── Delegate to trace_acoustic_ray ────────────────────
                ray_result = trace_acoustic_ray(
                    leak_point=leak_pt,
                    sensor_point=spt,
                    obstacles=obstacles,
                    sensor=sensor,
                    leak_spl_at_1m=leak_spl_at_1m,
                    center_frequency_hz=center_frequency_hz,
                    temp_c=temp_c,
                    relative_humidity_pct=relative_humidity_pct,
                )
                all_ray_results.append(ray_result)

                # ── Conservative absorption adjustment ────────────────
                effective_spl = ray_result.final_spl_db
                if use_conservative_absorption:
                    computed_alpha = atmospheric_attenuation_db_per_m(
                        center_frequency_hz=center_frequency_hz,
                        temp_c=temp_c,
                        relative_humidity_pct=relative_humidity_pct,
                    )
                    extra = UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M - computed_alpha
                    if extra > 0:
                        effective_spl -= extra * ray_result.distance_meters

                # ── Ceiling reflection (image source method) ──────────
                if include_ceiling_reflection and ceiling_z is not None:
                    reflected_spl = _image_source_reflection_spl(
                        leak_point=leak_pt,
                        sensor_point=spt,
                        ceiling_z=ceiling_z,
                        leak_spl_at_1m=leak_spl_at_1m,
                        center_frequency_hz=center_frequency_hz,
                        temp_c=temp_c,
                        relative_humidity_pct=relative_humidity_pct,
                        ceiling_absorption_coeff=ceiling_absorption_coeff,
                    )
                    effective_spl = _combine_spl_db(
                        effective_spl,
                        reflected_spl,
                    )
                    ceiling_reflections_used = True

                # ── Evaluate detection ────────────────────────────────
                detected, _deficit = _evaluate_ugld_trigger(
                    effective_spl,
                    sensor,
                )

                # Compute free-field max detection range (for zone info)
                det_range = max_detection_range_m(
                    leak_spl_at_1m=leak_spl_at_1m,
                    sensor=sensor,
                    temp_c=temp_c,
                    relative_humidity_pct=relative_humidity_pct,
                )

                zone = UGLDDetectionZone(
                    sensor_id=sensor.sensor_id,
                    leak_point=leak_pt,
                    detected=detected,
                    detection_range_m=det_range,
                    final_spl_db=round(effective_spl, 1),
                    has_los=ray_result.has_los,
                    total_insertion_loss_db=(ray_result.total_insertion_loss_db),
                    obstacle_count=ray_result.obstacle_intersections,
                )
                detection_zones.append(zone)

                # Track best for this leak point
                if effective_spl > best_spl:
                    best_spl = effective_spl
                    best_sensor_id = sensor.sensor_id
                    best_distance = ray_result.distance_meters

                if detected:
                    detected_by_any = True

            leak_best[leak_idx] = (
                best_spl,
                best_sensor_id,
                best_distance,
                detected_by_any,
            )

        # ── Coverage gap analysis ─────────────────────────────────────
        coverage_gaps: List[UGLDCoverageGap] = []
        for leak_idx, leak_pt in enumerate(leak_points):
            best_spl, best_sensor_id, best_distance, detected = leak_best[leak_idx]
            if not detected:
                # Find the actual sensor for threshold reference
                sensor_threshold = sensors[0].trigger_threshold_db
                for s in sensors:
                    if s.sensor_id == best_sensor_id:
                        sensor_threshold = s.trigger_threshold_db
                        break
                deficit = max(0.0, sensor_threshold - best_spl)
                coverage_gaps.append(
                    UGLDCoverageGap(
                        leak_point=leak_pt,
                        nearest_sensor_id=best_sensor_id,
                        nearest_sensor_distance_m=round(best_distance, 2),
                        spl_at_nearest_sensor_db=round(best_spl, 1),
                        deficit_db=round(deficit, 1),
                    )
                )

        # ── Area estimation ───────────────────────────────────────────
        total_area = 0.0
        if area_bounds is not None:
            dx = area_bounds[1][0] - area_bounds[0][0]
            dy = area_bounds[1][1] - area_bounds[0][1]
            total_area = max(0.0, dx * dy)

        # Combined detection area: sum of pi*r^2 for each unique sensor
        # using max_detection_range (free-field), capped by total area
        combined_area = 0.0
        seen_sensors: set = set()
        for zone in detection_zones:
            if zone.sensor_id not in seen_sensors:
                r = zone.detection_range_m
                combined_area += math.pi * r * r
                seen_sensors.add(zone.sensor_id)
        if total_area > 0:
            combined_area = min(combined_area, total_area)

        fully_covered = len(coverage_gaps) == 0

        result = UGLDCoverageResult(
            fully_covered=fully_covered,
            sensors_evaluated=len(sensors),
            leak_points_evaluated=len(leak_points),
            detection_zones=detection_zones,
            coverage_gaps=coverage_gaps,
            ray_results=all_ray_results,
            combined_detection_area_m2=round(combined_area, 1),
            total_area_m2=round(total_area, 1),
            ceiling_reflections_used=ceiling_reflections_used,
        )

        logger.info(
            "ugld_multi_sensor_coverage: covered=%s gaps=%d area=%.1f/%.1f m²",
            fully_covered,
            len(coverage_gaps),
            combined_area,
            total_area,
        )

        return result


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    # Constants
    "UGLD_CENTER_FREQUENCY_HZ",
    "UGLD_AIR_ABSORPTION_CONSERVATIVE_DB_PER_M",
    "UGLD_MIN_SNR_DB",
    "NFPA72_PUBLIC_MODE_ABOVE_AMBIENT_DB",
    "NFPA72_PRIVATE_MODE_ABOVE_AMBIENT_DB",
    "NFPA72_SLEEPING_ABSOLUTE_MIN_DBA",
    "NFPA72_MAX_DBA",
    "DEFAULT_CEILING_ABSORPTION_COEFF",
    # Result dataclasses
    "AcousticCoverageResult",
    "UGLDDetectionZone",
    "UGLDCoverageGap",
    "UGLDCoverageResult",
    # Main class
    "AcousticsEngine",
]
