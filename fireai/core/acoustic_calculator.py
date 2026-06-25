"""acoustic_calculator.py — NFPA 72 Audible Notification Compliance
=================================================================
CRITICAL LIFE-SAFETY MODULE

Replaces the hardcoded SPEAKER_COVERAGE constants (30m / 21m) with
proper acoustic calculations based on physics and NFPA 72 requirements.

The old approach (fixed coverage radius) ignores:
  - Inverse square law (sound decreases with distance)
  - Room absorption (reverberant field adds to direct sound)
  - Ambient noise levels (must be 15 dB above ambient per NFPA 72)
  - Speaker reference distance (specs given at 3m or 10ft, not 1m)

The consultant's proposed code had a critical math error:
  drop_dB = 20 * log10(dist_m)
This assumes the source_dBa is measured at 1m. In reality, speaker
specifications are typically given at 3m (10ft) reference distance.
This would overestimate attenuation by ~9.5 dB, causing unnecessary
speaker additions.

This module uses the correct formula:
  Lp(d) = Lw - 20*log10(d/d_ref) + room_absorption_correction

NFPA 72 References:
  - §18.4.3: Public mode audible — minimum 15 dB above ambient
  - §18.4.4: Private mode — minimum 10 dB above ambient
  - §18.4.2: Sleeping areas — minimum 75 dBA at pillow
  - §18.4.1.2: Maximum 110 dBA at minimum distance

Usage:
    from fireai.core.acoustic_calculator import (
        calculate_spl_at_distance, check_audibility_compliance,
        calculate_min_speakers_for_room,
    )

    result = check_audibility_compliance(
        source_dba=95.0, ref_distance_m=3.0, target_distance_m=15.0,
        ambient_dba=60.0, mode="public",
    )
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ============================================================================
# NFPA 72 Audible Requirements
# ============================================================================

# Minimum sound levels per NFPA 72 §18.4
AUDIBLE_REQUIREMENTS = {
    # mode: (min_above_ambient_dB, absolute_min_dBA, nfpa_section)
    "public": (15, 0, "§18.4.3"),  # 15 dB above average ambient OR 5 dB above max ambient
    "private": (10, 45, "§18.4.4"),  # 10 dB above ambient, min 45 dBA
    "sleeping": (15, 75, "§18.4.2"),  # 75 dBA at pillow level, OR 15 dB above ambient
}

MAX_SOUND_LEVEL_DBA = 110.0  # NFPA 72 §18.4.1.2

# Default ambient noise levels by space type (dBA)
# Based on ASHRAE Handbook and acoustic engineering data
AMBIENT_NOISE_LEVELS = {
    "office_quiet": 40,
    "office_normal": 50,
    "office_loud": 60,
    "corridor": 50,
    "mechanical_room": 85,
    "warehouse": 70,
    "assembly_quiet": 45,
    "assembly_loud": 80,
    "educational": 50,
    "healthcare": 50,
    "industrial": 85,
    "kitchen": 75,
    "sleeping_area": 40,
    "stairwell": 55,
}

# Typical speaker specifications
# Most fire alarm speakers are rated at 3m (10ft) reference distance
DEFAULT_REF_DISTANCE_M = 3.0


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class SPLResult:
    """Sound Pressure Level calculation result."""

    effective_dba: float  # SPL at target distance
    source_dba: float  # Source SPL at reference distance
    target_distance_m: float  # Distance from source
    ref_distance_m: float  # Reference distance for source spec
    direct_attenuation_dB: float  # Attenuation from inverse square law
    room_gain_dB: float  # Reverberant field contribution
    method: str = "inverse_square_law"


@dataclass
class AudibilityResult:
    """Audibility compliance check result."""

    compliant: bool
    effective_dba: float  # SPL at listener position
    required_dba: float  # Required minimum per NFPA 72
    margin_dba: float  # effective_dba - required_dba
    mode: str  # "public", "private", "sleeping"
    nfpa_section: str  # Applicable NFPA 72 section
    ambient_dba: float  # Ambient noise level used
    violations: List[str] = field(default_factory=list)


@dataclass
class SpeakerPlacementResult:
    """Result of speaker placement calculation for a room."""

    room_area_m2: float
    room_height_m: float
    ambient_dba: float
    mode: str
    speaker_count: int
    speaker_spacing_m: float
    source_dba: float
    coverage_verified: bool
    violations: List[str] = field(default_factory=list)


# ============================================================================
# Core Acoustic Calculations
# ============================================================================


def calculate_spl_at_distance(
    source_dba: float,
    target_distance_m: float,
    ref_distance_m: float = DEFAULT_REF_DISTANCE_M,
    room_absorption_m2: Optional[float] = None,
    room_volume_m3: Optional[float] = None,
    include_reverberant_field: bool = True,
) -> SPLResult:
    """Calculate Sound Pressure Level at a given distance from a source.

    Uses the correct inverse square law formula:
        Lp(d) = Lp(ref) - 20 * log10(d / d_ref)

    NOT the consultant's incorrect formula (20*log10(d) which assumes ref=1m).

    Optionally includes reverberant field contribution for indoor spaces:

    V65 FIX: Added NaN/Inf input validation for source_dba, target_distance_m,
    ref_distance_m, and room_absorption_m2. These are life-safety calculations —
    NaN inputs produce NaN results which silently bypass compliance checks.
        Lp_total = 10 * log10(10^(Ld/10) + 10^(Lr/10))

    Where Ld = direct sound, Lr = reverberant sound.
    The reverberant field contribution depends on room absorption (Sabine).

    Args:
        source_dba: Speaker output in dBA at the reference distance.
        target_distance_m: Distance from speaker to listener.
        ref_distance_m: Reference distance for speaker spec (default 3m).
        room_absorption_m2: Room absorption in m² Sabine (A = α × S).
        room_volume_m3: Room volume in m³ (for reverberant field).
        include_reverberant_field: Include room reflections (indoor).

    Returns:
        SPLResult with calculated SPL and breakdown.

    """
    # V65 SAFETY: Reject NaN/Inf inputs — these are life-safety calculations.
    # NaN SPL values silently bypass compliance checks (NaN < threshold is False,
    # so non-compliant results appear compliant). This is catastrophic.
    if not math.isfinite(source_dba):
        raise ValueError(
            f"source_dba must be finite, got {source_dba}. "
            f"NaN/Inf in life-safety SPL calculations is catastrophic."
        )
    if not math.isfinite(target_distance_m):
        raise ValueError(
            f"target_distance_m must be finite, got {target_distance_m}. "
            f"NaN/Inf distance produces undefined SPL."
        )
    if not math.isfinite(ref_distance_m) or ref_distance_m <= 0:
        raise ValueError(
            f"ref_distance_m must be positive and finite, got {ref_distance_m}. "
            f"Non-positive or infinite reference distance makes SPL undefined."
        )
    if room_absorption_m2 is not None and (not math.isfinite(room_absorption_m2) or room_absorption_m2 < 0):
        raise ValueError(
            f"room_absorption_m2 must be non-negative and finite when provided, got {room_absorption_m2}. "
            f"Negative or infinite absorption is physically meaningless."
        )

    if target_distance_m <= 0:
        return SPLResult(
            effective_dba=source_dba,
            source_dba=source_dba,
            target_distance_m=0.0,
            ref_distance_m=ref_distance_m,
            direct_attenuation_dB=0.0,
            room_gain_dB=0.0,
        )

    # Direct sound: inverse square law
    # CORRECT formula: 20 * log10(d / d_ref), NOT 20 * log10(d)
    direct_attenuation_dB = 20.0 * math.log10(target_distance_m / ref_distance_m)
    direct_spl = source_dba - direct_attenuation_dB

    room_gain_dB = 0.0

    # Reverberant field contribution (indoor spaces only)
    if include_reverberant_field and room_absorption_m2 is not None and room_absorption_m2 > 0:
        # Reverberant SPL from a point source (Hopkins-Stryker):
        # Lr = Lw + 10*log10(4/A)
        # where Lw = source power level, A = room absorption
        #
        # Converting from Lp(ref) to Lw:
        # Lw = Lp(ref) + 20*log10(ref) + 11 (for point source in free field)
        # But simpler: the reverberant field adds a constant level
        # that depends on room absorption.
        #
        # For fire alarm speakers, a simplified approach:
        # L_rev = source_dba - 10*log10(room_absorption_m2 / ref_distance_m²) + 6
        # This is approximate but conservative for fire alarm design.
        reverberant_spl = source_dba + 10.0 * math.log10(4.0 / room_absorption_m2)
        reverberant_spl += 10.0 * math.log10(ref_distance_m**2)

        # Total SPL = energy sum of direct + reverberant
        total_spl = 10.0 * math.log10(10.0 ** (direct_spl / 10.0) + 10.0 ** (reverberant_spl / 10.0))
        room_gain_dB = total_spl - direct_spl
    else:
        total_spl = direct_spl

    return SPLResult(
        effective_dba=total_spl,
        source_dba=source_dba,
        target_distance_m=target_distance_m,
        ref_distance_m=ref_distance_m,
        direct_attenuation_dB=direct_attenuation_dB,
        room_gain_dB=room_gain_dB,
    )


def check_audibility_compliance(
    source_dba: float,
    target_distance_m: float,
    ambient_dba: float,
    mode: str = "public",
    ref_distance_m: float = DEFAULT_REF_DISTANCE_M,
    room_absorption_m2: Optional[float] = None,
    room_volume_m3: Optional[float] = None,
) -> AudibilityResult:
    """Check if a speaker/horn provides adequate audibility per NFPA 72.

    Args:
        source_dba: Speaker output in dBA at the reference distance.
        target_distance_m: Distance from speaker to farthest listener.
        ambient_dba: Average ambient noise level at listener position.
        mode: "public", "private", or "sleeping".
        ref_distance_m: Reference distance for speaker spec.
        room_absorption_m2: Room absorption (m² Sabine).
        room_volume_m3: Room volume for reverberant field.

    Returns:
        AudibilityResult with PASS/FAIL and details.

    """
    if mode not in AUDIBLE_REQUIREMENTS:
        mode = "public"  # Safe default

    min_above_ambient, absolute_min, nfpa_section = AUDIBLE_REQUIREMENTS[mode]

    # Calculate SPL at target distance
    spl_result = calculate_spl_at_distance(
        source_dba=source_dba,
        target_distance_m=target_distance_m,
        ref_distance_m=ref_distance_m,
        room_absorption_m2=room_absorption_m2,
        room_volume_m3=room_volume_m3,
    )

    effective_dba = spl_result.effective_dba

    # Determine required level
    required_from_ambient = ambient_dba + min_above_ambient
    required_dba = max(required_from_ambient, absolute_min)

    # Check maximum level (NFPA 72 §18.4.1.2)
    violations = []
    if effective_dba > MAX_SOUND_LEVEL_DBA:
        violations.append(
            f"Sound level {effective_dba:.1f} dBA exceeds maximum {MAX_SOUND_LEVEL_DBA} dBA per NFPA 72 §18.4.1.2"
        )

    # Check minimum level
    margin = effective_dba - required_dba
    compliant = margin >= 0

    if not compliant:
        violations.append(
            f"Sound level at {target_distance_m:.1f}m is {effective_dba:.1f} dBA. "
            f"Required: {required_dba:.1f} dBA ({min_above_ambient} dB above "
            f"ambient {ambient_dba} dBA per NFPA 72 {nfpa_section}). "
            f"Deficit: {abs(margin):.1f} dB."
        )

    return AudibilityResult(
        compliant=compliant,
        effective_dba=effective_dba,
        required_dba=required_dba,
        margin_dba=margin,
        mode=mode,
        nfpa_section=nfpa_section,
        ambient_dba=ambient_dba,
        violations=violations,
    )


def calculate_min_speakers_for_room(
    room_length_m: float,
    room_width_m: float,
    room_height_m: float,
    source_dba: float,
    ambient_dba: float,
    mode: str = "public",
    ref_distance_m: float = DEFAULT_REF_DISTANCE_M,
    room_absorption_m2: Optional[float] = None,
) -> SpeakerPlacementResult:
    """Calculate minimum number of speakers needed for a rectangular room.

    Uses iterative spacing reduction until all points in the room
    meet NFPA 72 audibility requirements. Replaces the hardcoded
    SPEAKER_COVERAGE = 30m constant.

    Args:
        room_length_m: Room length in meters.
        room_width_m: Room width in meters.
        room_height_m: Room height in meters.
        source_dba: Speaker output in dBA at reference distance.
        ambient_dba: Average ambient noise level.
        mode: "public", "private", or "sleeping".
        ref_distance_m: Reference distance for speaker spec.
        room_absorption_m2: Room absorption (m² Sabine).

    Returns:
        SpeakerPlacementResult with speaker count and spacing.

    """
    room_area = room_length_m * room_width_m

    # Estimate room absorption if not provided
    # Typical office: α ≈ 0.2-0.3, so A ≈ 0.25 × surface_area
    if room_absorption_m2 is None:
        surface_area = 2 * (room_length_m * room_width_m + room_length_m * room_height_m + room_width_m * room_height_m)
        room_absorption_m2 = 0.25 * surface_area  # Moderate absorption

    # Find maximum spacing that ensures compliance at the worst point
    # Worst point = corner of the speaker's coverage rectangle
    # For a grid of speakers spaced S apart, the farthest point is at
    # distance = sqrt((S/2)² + (S/2)² + h²) where h = height difference

    max_spacing = max(room_length_m, room_width_m)  # Start with 1 speaker
    min_spacing = 3.0  # Minimum practical spacing
    best_spacing = max_spacing
    best_count = 1

    for spacing in _frange(max_spacing, min_spacing, -1.0):
        if spacing <= 0:
            break

        # Worst-case distance from a speaker
        half_diag = math.sqrt((spacing / 2) ** 2 + (spacing / 2) ** 2)
        worst_distance = math.sqrt(half_diag**2 + room_height_m**2)

        # Check compliance at worst distance
        result = check_audibility_compliance(
            source_dba=source_dba,
            target_distance_m=worst_distance,
            ambient_dba=ambient_dba,
            mode=mode,
            ref_distance_m=ref_distance_m,
            room_absorption_m2=room_absorption_m2,
            room_volume_m3=room_length_m * room_width_m * room_height_m,
        )

        if result.compliant:
            best_spacing = spacing
            # Calculate speaker count for grid
            nx = max(1, math.ceil(room_length_m / spacing))
            ny = max(1, math.ceil(room_width_m / spacing))
            best_count = nx * ny
            break

    # Final verification
    final_result = check_audibility_compliance(
        source_dba=source_dba,
        target_distance_m=math.sqrt((best_spacing / 2) ** 2 + (best_spacing / 2) ** 2 + room_height_m**2),
        ambient_dba=ambient_dba,
        mode=mode,
        ref_distance_m=ref_distance_m,
        room_absorption_m2=room_absorption_m2,
        room_volume_m3=room_length_m * room_width_m * room_height_m,
    )

    return SpeakerPlacementResult(
        room_area_m2=room_area,
        room_height_m=room_height_m,
        ambient_dba=ambient_dba,
        mode=mode,
        speaker_count=best_count,
        speaker_spacing_m=round(best_spacing, 1),
        source_dba=source_dba,
        coverage_verified=final_result.compliant,
        violations=final_result.violations,
    )


def _frange(start: float, stop: float, step: float):
    """Float range generator."""
    if step > 0:
        while start <= stop:
            yield start
            start += step
    elif step < 0:
        while start >= stop:
            yield start
            start += step


# ============================================================================
# Backward-Compatible Speaker Coverage — Replaces SPEAKER_COVERAGE=30.0
# ============================================================================


def get_speaker_coverage_radius(
    source_dba: float = 95.0,
    ref_distance_m: float = DEFAULT_REF_DISTANCE_M,
    ambient_dba: float = 55.0,
    mode: str = "public",
    room_height_m: float = 3.0,
    room_absorption_m2: Optional[float] = None,
) -> float:
    """Compute the effective speaker coverage radius per NFPA 72 §18.4/§18.5.

    This function replaces the deprecated fixed SPEAKER_COVERAGE=30.0 constant.
    It calculates the maximum distance at which a speaker provides adequate
    audibility based on inverse-square-law attenuation, room absorption, and
    ambient noise levels.

    The old constant (30m general, 21m intelligible) was a rough estimate
    that ignored room acoustics, ambient noise, and speaker specifications.
    This function provides accurate, code-compliant coverage.

    NFPA 72 References:
        - §18.4.3: Public mode — min 15 dB above ambient
        - §18.4.4: Private mode — min 10 dB above ambient
        - §18.4.2: Sleeping areas — min 75 dBA at pillow
        - §18.4.1.2: Maximum 110 dBA

    Args:
        source_dba: Speaker output at reference distance (default 95 dBA at 3m).
        ref_distance_m: Reference distance for speaker spec (default 3m).
        ambient_dba: Ambient noise level in dBA (default 55 for office).
        mode: "public", "private", or "sleeping".
        room_height_m: Room ceiling height (default 3.0m).
        room_absorption_m2: Room absorption in m² Sabine. If None, estimated
            from a typical 10m×10m room with moderate absorption.

    Returns:
        Maximum coverage radius in metres where audibility is compliant.
        If no distance is compliant (speaker too quiet), returns 0.0.

    """
    if room_absorption_m2 is None:
        # Estimate: typical room 10m×10m, α≈0.25, surface ≈ 300m²
        room_absorption_m2 = 75.0

    # Binary search for maximum compliant distance
    lo, hi = 0.5, 100.0  # Search between 0.5m and 100m
    best_radius = 0.0

    for _ in range(50):  # ~50 iterations gives ~0.001m precision
        mid = (lo + hi) / 2.0
        # Worst case: listener at the farthest horizontal distance + height
        worst_dist = math.sqrt(mid**2 + room_height_m**2)

        result = check_audibility_compliance(
            source_dba=source_dba,
            target_distance_m=worst_dist,
            ambient_dba=ambient_dba,
            mode=mode,
            ref_distance_m=ref_distance_m,
            room_absorption_m2=room_absorption_m2,
        )

        if result.compliant:
            best_radius = mid
            lo = mid
        else:
            hi = mid

    return round(best_radius, 2)


# ============================================================================
# AcousticSPLCalculator — Multi-speaker room analysis with 3D barriers
# ============================================================================

# Barrier attenuation values (dBA) — based on ASHRAE / acoustic engineering data
# These represent the additional attenuation when sound passes through or around
# a barrier between source and listener.
BARRIER_ATTENUATION_DB = {
    "open_doorway": 3.0,  # Open doorway — minimal diffraction
    "standard_door": 15.0,  # Closed standard interior door (STC 25-30)
    "fire_door": 25.0,  # Fire-rated door (STC 40+)
    "glass_partition": 22.0,  # Single glazing (STC 26-32)
    "drywall_partition": 30.0,  # Standard drywall partition (STC 33-40)
    "concrete_wall": 45.0,  # Concrete or masonry wall (STC 50+)
}


@dataclass
class CheckPoint:
    """A point in space where SPL is evaluated (3D).

    Attributes:
        x: X coordinate in metres.
        y: Y coordinate in metres.
        z: Z coordinate in metres (height above floor).
        label: Optional label for identification.

    """

    x: float
    y: float
    z: float = 1.5  # Default: typical ear height for standing adult
    label: str = ""


@dataclass
class Speaker:
    """A fire alarm speaker/horn with position and specification.

    Attributes:
        x: X coordinate in metres.
        y: Y coordinate in metres.
        z: Z coordinate in metres (mounting height).
        rating_dba: Speaker output in dBA at the reference distance.
        ref_distance_m: Reference distance for the speaker spec (default 3m).
        speaker_id: Optional identifier.

    """

    x: float
    y: float
    z: float = 2.8  # Default: typical ceiling-mounted height
    rating_dba: float = 95.0
    ref_distance_m: float = DEFAULT_REF_DISTANCE_M
    speaker_id: str = ""


@dataclass
class Barrier:
    """A sound barrier between a speaker and listener.

    Attributes:
        barrier_type: Key from BARRIER_ATTENUATION_DB (e.g., "standard_door").
            Or a custom dBA value can be specified.
        attenuation_dba: Custom attenuation in dBA (overrides barrier_type).
        label: Optional label for identification.

    """

    barrier_type: str = "standard_door"
    attenuation_dba: Optional[float] = None
    label: str = ""

    @property
    def effective_attenuation_dba(self) -> float:
        """Get the effective attenuation for this barrier."""
        if self.attenuation_dba is not None:
            return self.attenuation_dba
        return BARRIER_ATTENUATION_DB.get(self.barrier_type, 15.0)


@dataclass
class RoomAcousticResult:
    """Result of acoustic analysis for a room with multiple speakers.

    Attributes:
        room_id: Room identifier.
        compliant: Whether ALL check points meet NFPA 72 requirements.
        worst_point_spl: SPL at the worst (lowest SPL) check point.
        worst_point_label: Label of the worst check point.
        required_dba: Required minimum SPL per NFPA 72.
        margin_dba: Worst margin (effective - required).
        violations: List of violation dicts for non-compliant points.
        point_results: Detailed results for each check point.

    """

    room_id: str
    compliant: bool
    worst_point_spl: float
    worst_point_label: str
    required_dba: float
    margin_dba: float
    violations: List[Dict[str, Any]] = field(default_factory=list)
    point_results: List[Dict[str, Any]] = field(default_factory=list)


class AcousticSPLCalculator:
    """Multi-speaker room SPL calculator with 3D barrier support.

    This class provides the integration interface for the orchestrator.
    Unlike the standalone functions (which check one speaker at one point),
    this class checks MULTIPLE speakers against MULTIPLE check points in a
    room, handling logarithmic SPL addition, 3D distances, and barrier
    attenuation.

    The consultant's proposed code had these errors:
      1. behind_closed_door flag on speaker (should be on the path/barrier)
      2. Only 2D (x,y) — ignored height/z dimension
      3. Wrong import path (fireai.v8_core → fireai.core.provenance)
      4. Wrong formula: 20*log10(dist_m) instead of 20*log10(dist_m/ref_dist)

    This implementation fixes ALL of those issues.

    Usage::

        from fireai.core.acoustic_calculator import (
            AcousticSPLCalculator, Speaker, CheckPoint, Barrier
        )

        calc = AcousticSPLCalculator(ambient_noise_db={"business": 55.0})
        result = calc.calculate_room_spl(
            room_id="R-101",
            occ_type="business",
            speakers=[Speaker(x=5, y=5, z=2.8, rating_dba=95)],
            check_points=[CheckPoint(x=1, y=1, z=1.5)],
            barriers=[Barrier(barrier_type="standard_door")],
        )
    """

    def __init__(
        self,
        room_ambient_noise: Optional[Dict[str, float]] = None,
    ) -> None:
        """Initialize the acoustic calculator.

        Args:
            room_ambient_noise: Dict mapping occupancy types to ambient noise
                levels in dBA. If None, uses AMBIENT_NOISE_LEVELS defaults.

        """
        self.ambient_levels = room_ambient_noise or dict(AMBIENT_NOISE_LEVELS)

    def _get_ambient_for_occ(self, occ_type: str) -> float:
        """Get ambient noise level for an occupancy type."""
        # Try exact match first
        if occ_type in self.ambient_levels:
            return self.ambient_levels[occ_type]
        # Try lowercase
        occ_lower = occ_type.lower()
        for key, val in self.ambient_levels.items():
            if key.lower() == occ_lower:
                return val
        # Partial match
        for key, val in self.ambient_levels.items():
            if occ_lower in key.lower() or key.lower() in occ_lower:
                return val
        # Default: 55 dBA (moderate office)
        return 55.0

    def calculate_room_spl(
        self,
        room_id: str,
        occ_type: str,
        speakers: List[Speaker],
        check_points: List[CheckPoint],
        barriers: Optional[List[Barrier]] = None,
        mode: str = "public",
        room_absorption_m2: Optional[float] = None,
    ) -> RoomAcousticResult:
        """Calculate SPL at all check points from all speakers in a room.

        For each check point:
          1. Calculate 3D distance to each speaker
          2. Apply inverse square law attenuation (with correct ref_distance)
          3. Apply barrier attenuation if barriers exist
          4. Sum SPL contributions from all speakers (logarithmic addition)
          5. Add reverberant field contribution if room absorption provided
          6. Check against NFPA 72 requirements

        Args:
            room_id: Room identifier.
            occ_type: Occupancy type (e.g., "business", "mechanical_room").
            speakers: List of Speaker objects with positions and ratings.
            check_points: List of CheckPoint objects where SPL is evaluated.
            barriers: Optional list of Barrier objects between speakers and
                check points. If provided, barrier attenuation is applied to
                ALL speaker→point paths. For per-path barriers, the caller
                should pre-process and provide separate rooms/zones.
            mode: "public", "private", or "sleeping" per NFPA 72 §18.4.
            room_absorption_m2: Room absorption in m² Sabine (for reverberant
                field calculation). If None, only direct sound is considered.

        Returns:
            RoomAcousticResult with compliance status for all check points.

        """
        ambient_dba = self._get_ambient_for_occ(occ_type)

        if mode not in AUDIBLE_REQUIREMENTS:
            mode = "public"

        min_above_ambient, absolute_min, nfpa_section = AUDIBLE_REQUIREMENTS[mode]
        required_dba = max(ambient_dba + min_above_ambient, absolute_min)

        # Total barrier attenuation (applied to all paths if barriers exist)
        total_barrier_dba = 0.0
        if barriers:
            for b in barriers:
                total_barrier_dba += b.effective_attenuation_dba

        violations: List[Dict[str, Any]] = []
        point_results: List[Dict[str, Any]] = []
        worst_spl = 200.0  # Track worst (lowest) SPL
        worst_label = ""

        for point in check_points:
            # Sum SPL contributions from all speakers (logarithmic addition)
            sum_power = 0.0

            for spkr in speakers:
                # 3D distance (not 2D like consultant's code)
                dist_m = max(
                    0.5,  # Minimum distance to avoid singularity
                    math.sqrt((point.x - spkr.x) ** 2 + (point.y - spkr.y) ** 2 + (point.z - spkr.z) ** 2),
                )

                # Inverse square law with correct reference distance
                # Lp(d) = Lp(ref) - 20*log10(d / d_ref)
                # NOT the consultant's formula: 20*log10(d)
                drop_dB = 20.0 * math.log10(dist_m / spkr.ref_distance_m)
                effective_dba = spkr.rating_dba - drop_dB

                # Apply barrier attenuation
                effective_dba -= total_barrier_dba

                # Logarithmic SPL addition: sum 10^(SPL/10)
                if effective_dba > 0:
                    sum_power += math.pow(10, effective_dba / 10.0)

            # Total SPL at this point from all speakers
            total_pt_spl = 10.0 * math.log10(sum_power) if sum_power > 0 else 0.0

            # V65 SAFETY: Guard against inf/NaN in computed SPL.
            # If sum_power overflows (extreme speaker ratings), log10(inf) = inf.
            # Inf SPL would bypass compliance checks incorrectly.
            if not math.isfinite(total_pt_spl):
                total_pt_spl = MAX_SOUND_LEVEL_DBA + 1.0  # Force non-compliant

            # Add reverberant field contribution if room absorption provided
            if room_absorption_m2 is not None and room_absorption_m2 > 0 and speakers:
                # Reverberant field adds to direct sound
                # Use average speaker power for reverberant estimate
                avg_rating = sum(s.rating_dba for s in speakers) / len(speakers)
                avg_ref = sum(s.ref_distance_m for s in speakers) / len(speakers)
                # V65 SAFETY: Validate avg_ref is positive and finite before log10
                if not math.isfinite(avg_ref) or avg_ref <= 0:
                    avg_ref = DEFAULT_REF_DISTANCE_M
                reverberant_spl = avg_rating + 10.0 * math.log10(4.0 / room_absorption_m2)
                reverberant_spl += 10.0 * math.log10(avg_ref**2)

                # V65 SAFETY: Guard reverberant SPL against NaN/Inf
                if not math.isfinite(reverberant_spl):
                    # Skip reverberant contribution if it's invalid
                    pass
                else:
                    combined = 10.0 * math.log10(
                        math.pow(10, total_pt_spl / 10.0) + math.pow(10, reverberant_spl / 10.0)
                    )
                    # V65 SAFETY: Only use combined if it's finite
                    if math.isfinite(combined):
                        total_pt_spl = combined

            # Track worst point
            if total_pt_spl < worst_spl:
                worst_spl = total_pt_spl
                worst_label = point.label or f"({point.x:.1f},{point.y:.1f},{point.z:.1f})"

            margin = total_pt_spl - required_dba
            pt_compliant = margin >= 0

            pt_result: Dict[str, Any] = {
                "point": point.label or f"({point.x:.1f},{point.y:.1f},{point.z:.1f})",
                "spl_dba": round(total_pt_spl, 1),
                "required_dba": round(required_dba, 1),
                "margin_dba": round(margin, 1),
                "compliant": pt_compliant,
            }
            point_results.append(pt_result)

            if not pt_compliant:
                msg = (
                    f"Room '{room_id}' check point '{pt_result['point']}': "
                    f"SPL = {total_pt_spl:.1f} dBA, required {required_dba:.1f} dBA "
                    f"({min_above_ambient} dB above ambient {ambient_dba:.0f} dBA "
                    f"per NFPA 72 {nfpa_section}). Deficit: {abs(margin):.1f} dB."
                )
                violations.append(
                    {
                        "code": "ACOUSTIC-INSUFFICIENT",
                        "message": msg,
                        "severity": "CRITICAL",
                        "point": pt_result["point"],
                        "deficit_dba": round(abs(margin), 1),
                    }
                )

            # Check maximum level
            # V20.2 FIX: NFPA 72 §18.4.1.2 "shall not exceed" = mandatory,
            # so severity is CRITICAL not WARNING.
            if total_pt_spl > MAX_SOUND_LEVEL_DBA:
                violations.append(
                    {
                        "code": "ACOUSTIC-EXCESSIVE",
                        "message": (
                            f"Room '{room_id}' SPL {total_pt_spl:.1f} dBA exceeds "
                            f"maximum {MAX_SOUND_LEVEL_DBA} dBA per NFPA 72 §18.4.1.2"
                        ),
                        "severity": "CRITICAL",
                        "point": pt_result["point"],
                    }
                )

        compliant = len(violations) == 0
        margin_dba = worst_spl - required_dba

        return RoomAcousticResult(
            room_id=room_id,
            compliant=compliant,
            worst_point_spl=round(worst_spl, 1),
            worst_point_label=worst_label,
            required_dba=round(required_dba, 1),
            margin_dba=round(margin_dba, 1),
            violations=violations,
            point_results=point_results,
        )


__all__ = [
    "AMBIENT_NOISE_LEVELS",
    "AUDIBLE_REQUIREMENTS",
    "BARRIER_ATTENUATION_DB",
    "DEFAULT_REF_DISTANCE_M",
    "MAX_SOUND_LEVEL_DBA",
    "AcousticSPLCalculator",
    "AudibilityResult",
    "Barrier",
    "CheckPoint",
    "RoomAcousticResult",
    "SPLResult",
    "Speaker",
    "SpeakerPlacementResult",
    "calculate_min_speakers_for_room",
    "calculate_spl_at_distance",
    "check_audibility_compliance",
    "get_speaker_coverage_radius",
]
