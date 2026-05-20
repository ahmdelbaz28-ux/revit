"""
acoustic_calculator.py — NFPA 72 Audible Notification Compliance
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
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# NFPA 72 Audible Requirements
# ============================================================================

# Minimum sound levels per NFPA 72 §18.4
AUDIBLE_REQUIREMENTS = {
    # mode: (min_above_ambient_dB, absolute_min_dBA, nfpa_section)
    "public":   (15,  0, "§18.4.3"),  # 15 dB above average ambient OR 5 dB above max ambient
    "private":  (10, 45, "§18.4.4"),  # 10 dB above ambient, min 45 dBA
    "sleeping": (15, 75, "§18.4.2"),  # 75 dBA at pillow level, OR 15 dB above ambient
}

MAX_SOUND_LEVEL_DBA = 110.0  # NFPA 72 §18.4.1.2

# Default ambient noise levels by space type (dBA)
# Based on ASHRAE Handbook and acoustic engineering data
AMBIENT_NOISE_LEVELS = {
    "office_quiet":     40,
    "office_normal":    50,
    "office_loud":      60,
    "corridor":         50,
    "mechanical_room":  85,
    "warehouse":        70,
    "assembly_quiet":   45,
    "assembly_loud":    80,
    "educational":      50,
    "healthcare":       50,
    "industrial":       85,
    "kitchen":          75,
    "sleeping_area":    40,
    "stairwell":        55,
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
    effective_dba: float              # SPL at target distance
    source_dba: float                 # Source SPL at reference distance
    target_distance_m: float          # Distance from source
    ref_distance_m: float             # Reference distance for source spec
    direct_attenuation_dB: float      # Attenuation from inverse square law
    room_gain_dB: float               # Reverberant field contribution
    method: str = "inverse_square_law"


@dataclass
class AudibilityResult:
    """Audibility compliance check result."""
    compliant: bool
    effective_dba: float              # SPL at listener position
    required_dba: float               # Required minimum per NFPA 72
    margin_dba: float                 # effective_dba - required_dba
    mode: str                         # "public", "private", "sleeping"
    nfpa_section: str                 # Applicable NFPA 72 section
    ambient_dba: float                # Ambient noise level used
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
        reverberant_spl += 10.0 * math.log10(ref_distance_m ** 2)

        # Total SPL = energy sum of direct + reverberant
        total_spl = 10.0 * math.log10(
            10.0 ** (direct_spl / 10.0) + 10.0 ** (reverberant_spl / 10.0)
        )
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
            f"Sound level {effective_dba:.1f} dBA exceeds maximum "
            f"{MAX_SOUND_LEVEL_DBA} dBA per NFPA 72 §18.4.1.2"
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
        surface_area = 2 * (room_length_m * room_width_m +
                           room_length_m * room_height_m +
                           room_width_m * room_height_m)
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
        worst_distance = math.sqrt(half_diag ** 2 + room_height_m ** 2)

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
        target_distance_m=math.sqrt(
            (best_spacing / 2) ** 2 + (best_spacing / 2) ** 2 + room_height_m ** 2
        ),
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


__all__ = [
    "AUDIBLE_REQUIREMENTS",
    "AMBIENT_NOISE_LEVELS",
    "MAX_SOUND_LEVEL_DBA",
    "DEFAULT_REF_DISTANCE_M",
    "SPLResult",
    "AudibilityResult",
    "SpeakerPlacementResult",
    "calculate_spl_at_distance",
    "check_audibility_compliance",
    "calculate_min_speakers_for_room",
]
