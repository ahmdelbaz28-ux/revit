"""ugld_raytrace.py — UGLD Acoustic Ray Tracing Engine (Phase 2)
==============================================================
V23 Phase 2 — 3D Obstacle Shadow & Maekawa Barrier Diffraction

Extends the Phase 1 point-to-point acoustic propagation with obstacle
interaction. In an industrial facility, the direct line-of-sight (LOS)
from a gas leak to a UGLD sensor may be blocked by equipment (steel tanks,
vessels, walls, pipe racks). We must calculate the Acoustic Insertion Loss
(IL) caused by these barriers.

Physical Foundation — Maekawa's Barrier Diffraction Model:

  At ultrasonic frequencies (25-100 kHz), wavelengths are very short
  (λ ≈ 3.4-13.6 mm). Sound behaves almost like light (Ray Acoustics),
  but it can STILL diffract around obstacle edges. The amount of
  diffraction depends on the Fresnel number N:

    N = 2δ / λ

  where δ = path length difference (diffraction path - direct path)
  and λ = wavelength at the operating frequency.

  Maekawa's empirical formula (ISO 9613-2:1996 Annex A, Beranek & Ver):
    IL = 10 * log10(3 + 20*N)   for N > 0
    IL = 0                       for N ≤ 0

  At ultrasonic frequencies:
    - 40 kHz, δ=0.1m: N≈23.5 → IL≈26.8 dB (NOT the flat 20 dB the
      consultant proposed — Maekawa gives 34% MORE attenuation)
    - 40 kHz, δ=0.5m: N≈118 → IL≈33.7 dB
    - 100 kHz, δ=0.1m: N≈59 → IL≈30.7 dB

  Using a flat 20 dB would UNDERESTIMATE barrier attenuation by 7-14 dB,
  making the system believe sensors can "hear" more than they actually
  can. In a life-safety system, this is negligent.

  REFUSED: Consultant's flat -20 dB per obstacle. ACCEPTED: Maekawa's
  frequency- and geometry-dependent model.

Obstacle Model:
  - AcousticObstacle: AABB with surface type → absorption coefficient
  - Uses same vertex-based AABB pattern as Layer 5 (flame_detector)
  - Reuses slab method for ray-AABB intersection

Architectural Integration:
  - Phase 1 (AcousticPropagation + check_ugld_trigger) remains untouched
  - This module ADDS obstacle-aware propagation on top
  - AcousticRayResult composes with UGLDTriggerResult for audit trail
  - No modifications to existing Layer 5 ray tracer

Standards:
  ISO 9613-2:1996 Annex A — Barrier attenuation (Maekawa)
  Z. Maekawa (1968) — "Noise reduction by distance from sources"
  Beranek & Ver (1992) — "Noise and Vibration Control Engineering"
  ISA-TR 84.00.07 — Augmented safety with acoustic gas leak detection

Usage:
    from fireai.core.ugld_raytrace import (
        AcousticObstacle, AcousticRayResult, trace_acoustic_ray,
        maekawa_insertion_loss,
    )

    obstacles = [
        AcousticObstacle(
            obstacle_id="TANK-01",
            vertices=[[5,5,0],[15,15,8]],
            surface_type="steel_plate",
        ),
    ]
    result = trace_acoustic_ray(
        leak_point=(2.0, 2.0, 3.0),
        sensor_point=(20.0, 20.0, 2.0),
        obstacles=obstacles,
        sensor=UltrasonicSensor(trigger_threshold_db=74.0, background_noise_db=60.0),
        leak_spl_at_1m=100.0,
        center_frequency_hz=40_000.0,
        temp_c=40.0,
    )
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from pydantic import BaseModel, ConfigDict, Field

from fireai.core.ugld_acoustics import (
    AcousticPropagation,
    UGLDTriggerResult,
    UltrasonicSensor,
    check_ugld_trigger,
    speed_of_sound,
)

# ===========================================================================
# Surface Absorption Coefficients for Acoustic Barriers
# ===========================================================================
# These represent the fraction of acoustic energy ABSORBED by the surface
# (not reflected). At ultrasonic frequencies, most industrial surfaces
# are highly reflective (low absorption), which means the barrier blocks
# most sound and the small fraction that reflects is the dominant path.
#
# The transmission loss (TL) through a barrier depends on its mass law:
# TL = 20*log10(f * m_surface) - 47 dB (simplified mass law)
# where f = frequency (Hz), m_surface = surface density (kg/m²)
#
# For a 10mm steel plate (m ≈ 78 kg/m²) at 40 kHz:
#   TL = 20*log10(40000 * 78) - 47 ≈ 130 - 47 = 83 dB
# → Sound does NOT pass THROUGH steel at ultrasonic frequencies.
# → The ONLY path is diffraction AROUND the edge (Maekawa).
#
# Reference: Beranek & Ver (1992), ISO 9613-2:1996 §7

_SURFACE_ABSORPTION: Dict[str, float] = {
    # surface_type: absorption_coefficient (0=perfect reflector, 1=perfect absorber)
    # At ultrasonic frequencies, most surfaces are highly reflective
    "steel_plate": 0.01,  # Polished steel — almost perfect reflector
    "concrete_wall": 0.03,  # Concrete — slightly absorbing
    "brick_wall": 0.04,  # Brick — slightly more absorbing
    "glass_panel": 0.02,  # Glass — very reflective
    "drywall": 0.05,  # Drywall — slightly more absorbing
    "insulated_panel": 0.15,  # Acoustic insulation — more absorbing
    "open_lattice": 0.50,  # Grating/lattice — partial barrier (50% open)
    "mesh_screen": 0.70,  # Wire mesh — mostly transparent acoustically
    "custom": 0.05,  # Default custom — moderate
}


# ===========================================================================
# Maekawa Barrier Diffraction Model
# ===========================================================================


def maekawa_insertion_loss(
    path_difference_m: float,
    center_frequency_hz: float,
    temp_c: float = 40.0,
) -> float:
    """Calculate barrier insertion loss using Maekawa's diffraction model.

    Maekawa's empirical formula (ISO 9613-2:1996 Annex A):
        IL = 10 * log10(3 + 20*N)  for N > 0
        IL = 0                      for N ≤ 0

    where N = 2δ/λ is the Fresnel number, δ is the path length
    difference (diffraction path - direct path), and λ is the wavelength.

    At ultrasonic frequencies (25-100 kHz), wavelengths are extremely short
    (3.4-13.6 mm), so even small barriers produce large Fresnel numbers
    and correspondingly large insertion losses.

    IMPORTANT: This replaces the consultant's proposed flat -20 dB per
    obstacle. At 40 kHz with a typical barrier (δ=0.3m), Maekawa gives
    IL≈31 dB — 55% MORE attenuation than the flat 20 dB. Using 20 dB
    would underestimate the barrier effect, potentially leaving gas leaks
    undetected behind obstacles.

    Args:
        path_difference_m: Path length difference δ in meters.
            δ = (A + B) - d, where A = source-to-barrier-edge distance,
            B = barrier-edge-to-receiver distance, d = direct distance.
            Must be >= 0 (negative means the barrier is not in the shadow).
        center_frequency_hz: Center frequency of the ultrasonic signal (Hz).
        temp_c: Ambient temperature (C) for speed of sound calculation.

    Returns:
        Insertion loss in dB. Always >= 0.
        At 40 kHz: typical range 20-40 dB depending on δ.

    Reference: Z. Maekawa (1968), ISO 9613-2:1996 Annex A,
               Beranek & Ver (1992) Chapter 7

    """
    if path_difference_m <= 0.0:
        return 0.0

    # Calculate wavelength from frequency and speed of sound
    c = speed_of_sound(temp_c)
    wavelength_m = c / center_frequency_hz

    # Fresnel number
    n = 2.0 * path_difference_m / wavelength_m

    # Maekawa's formula
    il = 10.0 * math.log10(3.0 + 20.0 * n)

    # Cap at a reasonable maximum — beyond 50 dB the sound is effectively
    # destroyed regardless of the source level (background noise always wins)
    return round(min(il, 50.0), 1)


def compute_path_difference(
    leak_point: Tuple[float, float, float],
    sensor_point: Tuple[float, float, float],
    obstacle_min: Tuple[float, float, float],
    obstacle_max: Tuple[float, float, float],
) -> float:
    """Compute the path length difference for barrier diffraction.

    The path difference δ is the difference between the shortest
    diffraction path (source → barrier edge → receiver) and the
    direct path (source → receiver).

    For an AABB obstacle, the "barrier edge" is approximated as the
    nearest point on the obstacle's top edge (or the nearest vertical
    edge) to the direct ray. This is a simplified model that works
    well for the typical case where the obstacle is between source
    and receiver at a similar height.

    Algorithm:
      1. Find the nearest point on the AABB surface to the line segment
         connecting leak_point and sensor_point.
      2. If the ray intersects the AABB, compute the diffraction path
         around the top edge (the highest point of the AABB between
         source and receiver).
      3. δ = (distance_source_to_top + distance_top_to_receiver) - direct_distance

    For a ray that passes through the AABB, the diffraction path goes
    around the top edge, so:
      - A = distance from source to top of barrier (nearest edge)
      - B = distance from top of barrier to receiver
      - d = direct distance

    Args:
        leak_point: (x, y, z) of the leak source.
        sensor_point: (x, y, z) of the UGLD sensor.
        obstacle_min: (x_min, y_min, z_min) of the AABB.
        obstacle_max: (x_max, y_max, z_max) of the AABB.

    Returns:
        Path length difference δ in meters. >= 0.

    """
    sx, sy, sz = leak_point
    rx, ry, rz = sensor_point
    ox_min, oy_min, oz_min = obstacle_min
    ox_max, oy_max, oz_max = obstacle_max

    # Direct distance
    d = math.sqrt((rx - sx) ** 2 + (ry - sy) ** 2 + (rz - sz) ** 2)
    if d < 1e-9:
        return 0.0

    # For a ray passing through the AABB, the shortest diffraction path
    # goes around the nearest edge. The most common case in industrial
    # settings is that the obstacle is between source and receiver, and
    # the sound diffracts over the top.
    #
    # The "diffraction point" is the point on the AABB boundary closest
    # to the direct line segment that is NOT inside the AABB.
    #
    # Simplified approach: Use the top of the obstacle as the diffraction
    # point. The top edge is at z = obstacle_max[2].
    #
    # Find the closest point on the top face (z = oz_max) to the direct
    # line segment. The x,y coordinates of the diffraction point are
    # where the horizontal projection of the direct line intersects the
    # AABB boundary.

    # Horizontal distances
    dx = rx - sx
    dy = ry - sy
    horiz_dist_sq = dx * dx + dy * dy

    if horiz_dist_sq < 1e-9:
        # Source and receiver are vertically aligned — use z
        # Diffraction over the top
        top_z = oz_max
        # Find if source or receiver is higher
        higher_z = max(sz, rz)
        if top_z <= higher_z:
            # Obstacle top is below the higher point — minimal diffraction
            # But the ray still passes through the AABB, so use a small δ
            delta = max(0.0, (top_z - min(sz, rz)) * 0.1)
            return delta

        # Path over the top
        a = math.sqrt((sx - sx) ** 2 + (sy - sy) ** 2 + (top_z - sz) ** 2)
        b = math.sqrt((rx - sx) ** 2 + (ry - sy) ** 2 + (top_z - rz) ** 2)
        delta = (a + b) - d
        return max(0.0, delta)

    # Parameter t for the horizontal projection hitting the AABB
    # We find where the line from (sx,sy) to (rx,ry) enters the AABB
    # in the x,y plane, then use the obstacle top z for diffraction height.
    #
    # The diffraction point is on the AABB boundary at z = oz_max.
    # Its x,y is the intersection of the line with the AABB boundary.
    #
    # Find the parameter t where the line enters the AABB rectangle:
    #   P(t) = S + t*(R-S), 0 <= t <= 1
    #
    # The nearest point on the AABB boundary to the line is at the
    # entry/exit point of the line through the AABB.

    # Find entry point (smallest t where line hits AABB in x,y)
    t_entry = 0.0
    t_exit = 1.0

    for _axis, s_val, r_val, o_min, o_max in [
        (0, sx, rx, ox_min, ox_max),
        (1, sy, ry, oy_min, oy_max),
    ]:
        if abs(r_val - s_val) < 1e-12:
            # Parallel to this axis
            if s_val < o_min or s_val > o_max:
                return 0.0  # Miss
        else:
            t1 = (o_min - s_val) / (r_val - s_val)
            t2 = (o_max - s_val) / (r_val - s_val)
            if t1 > t2:
                t1, t2 = t2, t1
            t_entry = max(t_entry, t1)
            t_exit = min(t_exit, t2)

    if t_entry > t_exit:
        return 0.0  # No intersection in x,y

    # The diffraction point is at the entry point of the AABB boundary,
    # at the top of the obstacle (z = oz_max).
    # This is the most conservative choice — the shortest diffraction
    # path goes over the nearest edge.
    t_diff = max(0.0, t_entry)

    # Diffraction point coordinates
    diff_x = sx + t_diff * (rx - sx)
    diff_y = sy + t_diff * (ry - sy)
    diff_z = oz_max  # Top of obstacle

    # Path lengths
    a = math.sqrt((diff_x - sx) ** 2 + (diff_y - sy) ** 2 + (diff_z - sz) ** 2)
    b = math.sqrt((rx - diff_x) ** 2 + (ry - diff_y) ** 2 + (rz - diff_z) ** 2)

    delta = (a + b) - d
    return max(0.0, delta)


# ===========================================================================
# Ray-AABB Intersection (Slab Method — reused from Layer 5)
# ===========================================================================


def _ray_intersects_aabb(
    origin: Tuple[float, float, float],
    end: Tuple[float, float, float],
    box_min: Tuple[float, float, float],
    box_max: Tuple[float, float, float],
) -> bool:
    """Test if a line segment from origin to end intersects an AABB.

    Uses the slab method (same algorithm as Layer 5's _ray_intersects_box).
    Ray parameter t is in [0, 1] (parametric from origin to end).

    Args:
        origin: (x, y, z) start point of the ray segment.
        end: (x, y, z) end point of the ray segment.
        box_min: (x_min, y_min, z_min) AABB minimum corner.
        box_max: (x_max, y_max, z_max) AABB maximum corner.

    Returns:
        True if the ray segment intersects the AABB.

    """
    t_min = 0.0
    t_max = 1.0

    for i in range(3):
        if abs(end[i] - origin[i]) < 1e-12:
            # Ray is parallel to this slab
            if origin[i] < box_min[i] or origin[i] > box_max[i]:
                return False
        else:
            t1 = (box_min[i] - origin[i]) / (end[i] - origin[i])
            t2 = (box_max[i] - origin[i]) / (end[i] - origin[i])
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
            if t_min > t_max:
                return False

    return True


# ===========================================================================
# Pydantic Models
# ===========================================================================


class AcousticObstacle(BaseModel):
    """An obstacle in the UGLD acoustic propagation path.

    Uses the same AABB vertex pattern as Layer 5's Obstruction model.
    At ultrasonic frequencies, sound does NOT pass through solid obstacles
    (TL through 10mm steel at 40 kHz ≈ 83 dB). The ONLY surviving path
    is diffraction around edges, modeled by Maekawa.

    The surface_type determines absorption for reflected paths (future
    reverberation phase). For Phase 2 (direct path only), the key
    property is the AABB geometry for intersection testing.

    Reference: ISO 9613-2:1996 §7, Beranek & Ver (1992)
    """

    model_config = ConfigDict(frozen=True, strict=True)

    obstacle_id: str = Field(
        ...,
        description="Unique obstacle identifier for audit trail.",
    )
    vertices: List[List[float]] = Field(
        ...,
        min_length=2,
        description=(
            "AABB vertices. Minimum 2 (opposite corners [x_min,y_min,z_min] "
            "and [x_max,y_max,z_max]). Can be 8 corners for compatibility "
            "with Layer 5 Obstruction format."
        ),
    )
    surface_type: str = Field(
        default="steel_plate",
        description=(
            "Surface material type for absorption coefficient lookup. "
            "At ultrasonic frequencies, most surfaces are highly reflective. "
            "This field is used for future reverberation calculations."
        ),
    )

    @property
    def box_min(self) -> Tuple[float, float, float]:
        """AABB minimum corner computed from vertices."""
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return (min(xs), min(ys), min(zs))

    @property
    def box_max(self) -> Tuple[float, float, float]:
        """AABB maximum corner computed from vertices."""
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return (max(xs), max(ys), max(zs))

    @property
    def absorption_coefficient(self) -> float:
        """Acoustic absorption coefficient for this surface type."""
        return _SURFACE_ABSORPTION.get(self.surface_type, 0.05)


class ObstacleHit(BaseModel):
    """Record of a single obstacle intersection with computed Maekawa IL.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    obstacle_id: str
    insertion_loss_db: float = Field(
        description="Maekawa insertion loss for this specific obstacle (dB).",
    )
    path_difference_m: float = Field(
        description="Path length difference δ used for Maekawa calculation.",
    )


class AcousticRayResult(BaseModel):
    """Result of UGLD acoustic ray tracing with obstacle interaction.

    Composes with UGLDTriggerResult from Phase 1 for full audit trail.
    Provides:
      - Whether the direct LOS is clear or obstructed
      - How many obstacles intersect the ray path
      - Per-obstacle Maekawa IL with path difference details
      - Combined effect on SPL and trigger status

    Reference: ISO 9613-2:1996 Annex A, ISA-TR 84.00.07
    """

    model_config = ConfigDict(frozen=True, strict=True)

    has_los: bool = Field(
        description="True if direct line-of-sight is completely clear.",
    )
    obstacle_intersections: int = Field(
        default=0,
        description="Number of distinct obstacles intersected by the ray.",
    )
    total_insertion_loss_db: float = Field(
        default=0.0,
        description="Sum of Maekawa IL from all intersected obstacles (dB).",
    )
    obstacle_hits: List[ObstacleHit] = Field(
        default_factory=list,
        description="Per-obstacle hit details with Maekawa IL values.",
    )

    # Phase 1 physics (free-field)
    base_spl_db: float = Field(
        description="SPL at sensor WITHOUT any obstacle attenuation (Phase 1).",
    )
    final_spl_db: float = Field(
        description="SPL at sensor AFTER all obstacle attenuation.",
    )
    distance_meters: float = Field(
        description="Direct distance from leak to sensor (m).",
    )
    center_frequency_hz: float = Field(
        description="Center frequency used for all calculations (Hz).",
    )

    # Trigger result (from Phase 1 logic, applied to final_spl_db)
    trigger_result: UGLDTriggerResult = Field(
        description="Full trigger analysis based on final SPL after obstacles.",
    )


# ===========================================================================
# Core Ray Tracing Logic
# ===========================================================================


def trace_acoustic_ray(
    leak_point: Tuple[float, float, float],
    sensor_point: Tuple[float, float, float],
    obstacles: List[AcousticObstacle],
    sensor: UltrasonicSensor,
    leak_spl_at_1m: float,
    center_frequency_hz: float = 40_000.0,
    temp_c: float = 40.0,
    relative_humidity_pct: float = 50.0,
) -> AcousticRayResult:
    """Trace an acoustic ray from leak source to UGLD sensor through obstacles.

    Algorithm:
      1. Calculate direct distance and Phase 1 free-field SPL
      2. For each obstacle, test ray-AABB intersection (slab method)
      3. For each intersected obstacle, compute Maekawa IL using:
         - Path difference δ from AABB geometry
         - Fresnel number N = 2δ/λ
         - IL = 10*log10(3 + 20*N)
      4. Sum all IL values: total_IL = Σ IL_i
      5. Final SPL = Base SPL - total_IL
      6. Check trigger against sensor config (SNR and Threshold)

    Key difference from consultant's proposal:
      - Consultant: flat -20 dB per obstacle (WRONG — underestimates IL)
      - This implementation: Maekawa model (CORRECT — frequency and
        geometry dependent, typically 25-40 dB at ultrasonic frequencies)

    Args:
        leak_point: (x, y, z) of the gas leak source.
        sensor_point: (x, y, z) of the UGLD sensor.
        obstacles: List of AcousticObstacle objects to test.
        sensor: UltrasonicSensor configuration.
        leak_spl_at_1m: Source SPL at 1m reference distance (dB SPL).
        center_frequency_hz: Center frequency for all calculations (Hz).
        temp_c: Ambient temperature (C).
        relative_humidity_pct: Relative humidity (%).

    Returns:
        AcousticRayResult with full analysis including Maekawa IL details.

    Reference: ISO 9613-2:1996 Annex A, Maekawa (1968),
               ISA-TR 84.00.07 §4.3

    """
    # 1. Compute direct distance
    dx = sensor_point[0] - leak_point[0]
    dy = sensor_point[1] - leak_point[1]
    dz = sensor_point[2] - leak_point[2]
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)

    if distance < 1e-9:
        # Zero distance — sensor at leak point
        base_spl = leak_spl_at_1m
        obstacle_hits: List[ObstacleHit] = []
        total_il = 0.0
        has_los = True
    else:
        # 2. Phase 1 free-field SPL (no obstacles)
        prop = AcousticPropagation(
            leak_spl_at_1m=leak_spl_at_1m,
            distance_meters=distance,
            center_frequency_hz=center_frequency_hz,
            temp_c=temp_c,
            relative_humidity_pct=relative_humidity_pct,
        )
        base_spl = prop.final_spl_db

        # 3. Test intersection with each obstacle
        obstacle_hits = []
        has_los = True

        for obs in obstacles:
            bmin = obs.box_min
            bmax = obs.box_max

            if _ray_intersects_aabb(leak_point, sensor_point, bmin, bmax):
                has_los = False

                # Compute Maekawa IL using AABB geometry
                delta = compute_path_difference(
                    leak_point,
                    sensor_point,
                    bmin,
                    bmax,
                )

                il = maekawa_insertion_loss(
                    path_difference_m=delta,
                    center_frequency_hz=center_frequency_hz,
                    temp_c=temp_c,
                )

                obstacle_hits.append(
                    ObstacleHit(
                        obstacle_id=obs.obstacle_id,
                        insertion_loss_db=il,
                        path_difference_m=round(delta, 4),
                    )
                )

        # 4. Sum Maekawa IL from all intersected obstacles
        # For multiple obstacles, the IL values are additive in dB
        # because each obstacle independently attenuates the already-weak
        # diffracted signal. This is a conservative approximation.
        total_il = sum(hit.insertion_loss_db for hit in obstacle_hits)

    # 5. Final SPL after all obstacle attenuation
    final_spl = base_spl - total_il

    # 6. Build a modified AcousticPropagation with the final SPL
    #    and check trigger status
    # We create a synthetic propagation that represents the "effective"
    # SPL at the sensor after obstacles, then use the Phase 1 trigger logic.
    # This ensures consistency with Phase 1's SNR/threshold checks.
    if distance > 1e-9 and total_il > 0:
        # The obstacle attenuation is equivalent to increasing the effective
        # distance. We model this by computing what SPL the sensor would
        # see and building a trigger result from that.
        bg_noise = sensor.background_noise_db
        threshold = sensor.trigger_threshold_db
        snr = final_spl - bg_noise
        margin_threshold = final_spl - threshold
        margin_snr = snr - 6.0

        threshold_met = final_spl >= threshold
        snr_met = snr >= 6.0
        triggered = threshold_met and snr_met

        fail_reason = None
        if not triggered:
            reasons = []
            if not threshold_met:
                reasons.append(
                    f"Final SPL ({final_spl:.1f} dB) below trigger threshold "
                    f"({threshold:.1f} dB). Deficit: {abs(margin_threshold):.1f} dB."
                )
            if not snr_met:
                reasons.append(f"SNR ({snr:.1f} dB) below minimum 6 dB. Deficit: {abs(margin_snr):.1f} dB.")
            fail_reason = " | ".join(reasons)

        trigger_result = UGLDTriggerResult(
            triggered=triggered,
            final_spl_db=round(final_spl, 1),
            background_noise_db=bg_noise,
            trigger_threshold_db=threshold,
            snr_db=round(snr, 1),
            margin_to_threshold_db=round(margin_threshold, 1),
            margin_to_snr_db=round(margin_snr, 1),
            fail_reason=fail_reason,
        )
    elif distance > 1e-9:
        # No obstacles — use Phase 1 result directly
        prop_clean = AcousticPropagation(
            leak_spl_at_1m=leak_spl_at_1m,
            distance_meters=distance,
            center_frequency_hz=center_frequency_hz,
            temp_c=temp_c,
            relative_humidity_pct=relative_humidity_pct,
        )
        trigger_result = check_ugld_trigger(prop_clean, sensor)
    else:
        # Zero distance — sensor at leak point
        trigger_result = UGLDTriggerResult(
            triggered=True,
            final_spl_db=round(leak_spl_at_1m, 1),
            background_noise_db=sensor.background_noise_db,
            trigger_threshold_db=sensor.trigger_threshold_db,
            snr_db=round(leak_spl_at_1m - sensor.background_noise_db, 1),
            margin_to_threshold_db=round(leak_spl_at_1m - sensor.trigger_threshold_db, 1),
            margin_to_snr_db=round(leak_spl_at_1m - sensor.background_noise_db - 6.0, 1),
            fail_reason=None,
        )

    return AcousticRayResult(
        has_los=has_los,
        obstacle_intersections=len(obstacle_hits),
        total_insertion_loss_db=round(total_il, 1),
        obstacle_hits=obstacle_hits,
        base_spl_db=round(base_spl, 1),
        final_spl_db=round(final_spl, 1),
        distance_meters=round(distance, 2),
        center_frequency_hz=center_frequency_hz,
        trigger_result=trigger_result,
    )


__all__ = [
    # Models
    "AcousticObstacle",
    "ObstacleHit",
    "AcousticRayResult",
    # Functions
    "trace_acoustic_ray",
    "maekawa_insertion_loss",
    "compute_path_difference",
    # Constants
    "_SURFACE_ABSORPTION",
]
