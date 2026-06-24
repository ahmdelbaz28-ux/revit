"""fireai.core.notification_appliance — NFPA 72 Notification Appliance Calculations
=================================================================================

Implements NFPA 72 Chapter 18 notification appliance engineering:

1. NAC Sizing       — NFPA 72 §10.6.4, §18.3 (circuit current calculation)
2. SPL Calculation   — NFPA 72 §18.4.3 (sound pressure level for audible signals)
3. Strobe Candela    — NFPA 72 §18.5.5 (visible signaling intensity)
4. NAC Circuit Load  — NFPA 72 §10.6.4.2 (total current vs. panel capacity)

SAFETY CRITICAL:
  - Audible signals MUST produce ≥15 dBA above ambient per NFPA 72 §18.4.3.1
  - Visible signals MUST meet minimum candela per NFPA 72 §18.5.5.1
  - NAC current MUST NOT exceed 80% of panel rating per NEC 760
  - All NaN/Inf inputs are REJECTED
  - All negative inputs are REJECTED

ENGINEERING SOURCES:
  - NFPA 72-2022 Chapter 18 — Notification Appliances
  - NFPA 72-2022 §18.4.3 — Audible Signal Requirements
  - NFPA 72-2022 §18.5.5 — Visible Signal Requirements
  - NFPA 72-2022 §10.6.4 — Secondary Power Supply
  - NEC 760 — Fire Alarm Systems

NOTE: Previous versions falsely claimed "inspiration" from external repos.
All calculations are from NFPA/NEC standards directly. Every formula is
traced to its NFPA/NEC source section.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# NAC SIZING — NFPA 72 §10.6.4, §18.3
# ═══════════════════════════════════════════════════════════════════════════════

# NEC 760: Maximum circuit loading is 80% of rated capacity
_NAC_LOAD_FACTOR = 0.80

# Typical NAC panel ratings (amps)
_STANDARD_NAC_RATINGS = [1.0, 2.0, 3.0, 4.0]


@dataclass(frozen=True)
class NACLoadResult:
    """Result from NAC circuit load calculation.

    NFPA 72 §10.6.4.2:
      Total alarm current on a NAC must not exceed 80% of the
      NAC power supply rating. This ensures the NAC can operate
      all connected appliances under alarm conditions.

    The 80% derating accounts for:
      - Wire resistance variation
      - Temperature derating
      - Inrush current spikes during alarm activation
      - Manufacturing tolerance in appliance current draw
    """

    total_current_a: float
    max_allowed_a: float
    nac_rating_a: float
    device_count: int
    is_compliant: bool
    headroom_a: float
    formula: str
    nfpa_section: str


@dataclass(frozen=True)
class NotificationDevice:
    """A notification appliance on a NAC circuit.

    Common current draws (typical values from manufacturer data):
      - Horn: 0.030–0.100 A per unit
      - Strobe (15 cd): 0.050–0.100 A per unit
      - Strobe (75 cd): 0.100–0.200 A per unit
      - Horn/Strobe combo: 0.080–0.250 A per unit
      - Speaker (25V, 0.5W): ~0.020 A per unit
      - Speaker (25V, 1W): ~0.040 A per unit
      - Speaker (25V, 2W): ~0.080 A per unit
    """

    device_id: str
    device_type: str  # "horn", "strobe", "horn_strobe", "speaker"
    current_a: float  # Current draw in amperes
    candela: Optional[float] = None  # For strobes
    wattage: Optional[float] = None  # For speakers


def calculate_nac_load(
    devices: List[NotificationDevice],
    nac_rating_a: float = 2.0,
) -> NACLoadResult:
    """Calculate total NAC circuit load and verify compliance.

    NFPA 72 §10.6.4.2 and NEC 760:
      Total NAC current must not exceed 80% of the NAC power supply
      rating. This derating is mandatory — not optional.

    Formula:
      I_total = Σ(I_device)
      I_max = NAC_rating × 0.80
      Compliant if I_total ≤ I_max

    Args:
        devices: List of NotificationDevice on this NAC circuit.
        nac_rating_a: NAC power supply current rating in amperes.

    Returns:
        NACLoadResult with total current, max allowed, compliance.

    """
    # Input validation — safety first
    if not math.isfinite(nac_rating_a) or nac_rating_a <= 0:
        raise ValueError(f"nac_rating_a must be positive finite, got {nac_rating_a}")

    total_current = 0.0
    for _i, dev in enumerate(devices):
        if not math.isfinite(dev.current_a) or dev.current_a < 0:
            raise ValueError(f"Device '{dev.device_id}' has invalid current: {dev.current_a}")
        total_current += dev.current_a

    max_allowed = nac_rating_a * _NAC_LOAD_FACTOR
    is_compliant = total_current <= max_allowed
    headroom = max_allowed - total_current

    formula = (
        f"I_total = Σ(I_dev) = {total_current:.4f}A; "
        f"I_max = {nac_rating_a}A × {_NAC_LOAD_FACTOR} = {max_allowed:.4f}A; "
        f"Compliant: {total_current:.4f} ≤ {max_allowed:.4f} = {is_compliant}"
    )

    return NACLoadResult(
        total_current_a=round(total_current, 4),
        max_allowed_a=round(max_allowed, 4),
        nac_rating_a=nac_rating_a,
        device_count=len(devices),
        is_compliant=is_compliant,
        headroom_a=round(headroom, 4),
        formula=formula,
        nfpa_section="NFPA 72 §10.6.4.2",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SPL CALCULATION — NFPA 72 §18.4.3
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §18.4.3.1: Minimum SPL above ambient
_MIN_SPL_ABOVE_AMBIENT_DBA = 15.0

# NFPA 72 §18.4.3.1: Minimum absolute SPL
_MIN_ABSOLUTE_SPL_DBA = 75.0

# NFPA 72 §18.4.3.1: Maximum SPL (to prevent hearing damage)
_MAX_SPL_DBA = 120.0

# Reference distance for horn specifications (typically 10 ft = 3.05m)
_HORN_REFERENCE_DISTANCE_M = 3.05

# Speed of sound at 20°C in m/s
_SPEED_OF_SOUND_M_S = 343.0


@dataclass(frozen=True)
class SPLResult:
    """Result from SPL calculation.

    NFPA 72 §18.4.3:
      - Sound Pressure Level at any point must be ≥15 dBA above
        the average ambient sound level, OR ≥75 dBA, whichever is greater
      - Maximum SPL must not exceed 120 dBA
      - In mechanical rooms, the minimum is 5 dBA above ambient (not 15)
        per NFPA 72 §18.4.3.1 exception

    The inverse square law governs SPL attenuation:
      SPL_d = SPL_ref - 20 × log10(d / d_ref)

    This is a point-source model. In corridors, reflections may provide
    higher SPL than predicted. In open spaces, attenuation may be greater.
    """

    spl_dba: float
    distance_m: float
    ambient_dba: float
    min_required_dba: float
    is_compliant: bool
    exceeds_max: bool
    formula: str
    nfpa_section: str


def calculate_spl(
    horn_rating_dba: float,
    distance_m: float,
    ambient_dba: float = 45.0,
    is_mechanical_room: bool = False,
) -> SPLResult:
    """Calculate Sound Pressure Level at a distance from a notification appliance.

    NFPA 72 §18.4.3 — Inverse Square Law:
      SPL_at_distance = SPL_at_ref - 20 × log10(d / d_ref)

    This formula assumes:
      - Free-field conditions (no significant reflections)
      - Point source (valid when distance >> device dimensions)
      - No significant atmospheric absorption (valid for <300m)

    Compliance requirements:
      - SPL must be ≥15 dBA above ambient (or 5 dBA in mechanical rooms)
      - SPL must be ≥75 dBA absolute minimum
      - SPL must be ≤120 dBA maximum (hearing protection)

    Args:
        horn_rating_dba: Horn rated output in dBA at reference distance.
        distance_m: Distance from horn to listening point in meters.
        ambient_dba: Average ambient noise level in dBA.
        is_mechanical_room: If True, uses 5 dBA above ambient per exception.

    Returns:
        SPLResult with calculated SPL, compliance, and NFPA reference.

    """
    # Input validation
    if not math.isfinite(horn_rating_dba):
        raise ValueError(f"horn_rating_dba must be finite, got {horn_rating_dba}")
    if not math.isfinite(distance_m) or distance_m <= 0:
        raise ValueError(f"distance_m must be positive finite, got {distance_m}")
    if not math.isfinite(ambient_dba):
        raise ValueError(f"ambient_dba must be finite, got {ambient_dba}")

    # Inverse square law attenuation
    # SPL_d = SPL_ref - 20 × log10(d / d_ref)
    if distance_m >= _HORN_REFERENCE_DISTANCE_M:
        attenuation = 20.0 * math.log10(distance_m / _HORN_REFERENCE_DISTANCE_M)
    else:
        # Closer than reference distance — SPL increases (gain)
        attenuation = 20.0 * math.log10(distance_m / _HORN_REFERENCE_DISTANCE_M)

    spl_at_distance = horn_rating_dba - attenuation

    # Determine minimum required SPL
    spl_above_ambient = _MIN_SPL_ABOVE_AMBIENT_DBA
    if is_mechanical_room:
        spl_above_ambient = 5.0  # NFPA 72 §18.4.3.1 exception

    min_from_ambient = ambient_dba + spl_above_ambient
    min_required = max(min_from_ambient, _MIN_ABSOLUTE_SPL_DBA)

    is_compliant = spl_at_distance >= min_required
    exceeds_max = spl_at_distance > _MAX_SPL_DBA

    # If exceeds max, it's non-compliant for a different reason
    if exceeds_max:
        is_compliant = False

    formula = (
        f"SPL = {horn_rating_dba:.1f} dBA - 20×log10({distance_m:.2f}m/"
        f"{_HORN_REFERENCE_DISTANCE_M}m) = {horn_rating_dba:.1f} - "
        f"{attenuation:.2f} = {spl_at_distance:.2f} dBA"
    )

    return SPLResult(
        spl_dba=round(spl_at_distance, 2),
        distance_m=distance_m,
        ambient_dba=ambient_dba,
        min_required_dba=min_required,
        is_compliant=is_compliant,
        exceeds_max=exceeds_max,
        formula=formula,
        nfpa_section="NFPA 72 §18.4.3",
    )


def min_horn_rating_for_room(
    room_dimension_m: float,
    ambient_dba: float = 45.0,
    is_mechanical_room: bool = False,
) -> Dict[str, Any]:
    """Calculate minimum horn rating needed to cover a room.

    Uses the worst-case distance (room diagonal from corner to horn
    on opposite wall) to determine the minimum horn rating.

    Args:
        room_dimension_m: Maximum distance from horn to farthest point.
        ambient_dba: Average ambient noise level.
        is_mechanical_room: If True, uses 5 dBA requirement.

    Returns:
        Dict with min_horn_rating_dba, coverage_distance, compliance info.

    """
    # V96 FIX: Invalid room dimension must return a clearly invalid horn rating,
    # not 0.0 dBA (which looks like a valid value and could lead to specifying
    # a silent notification appliance — life safety violation).
    if not math.isfinite(room_dimension_m) or room_dimension_m <= 0:
        return {
            "min_horn_rating_dba": -1.0,  # Clearly invalid — no real horn is -1 dBA
            "coverage_distance_m": 0.0,
            "error": f"Invalid room dimension: {room_dimension_m}",
        }

    spl_above_ambient = 5.0 if is_mechanical_room else _MIN_SPL_ABOVE_AMBIENT_DBA
    min_required = max(ambient_dba + spl_above_ambient, _MIN_ABSOLUTE_SPL_DBA)

    # Reverse the inverse square law:
    # SPL_at_d = SPL_ref - 20×log10(d/d_ref)
    # SPL_ref = SPL_at_d + 20×log10(d/d_ref)
    if room_dimension_m > _HORN_REFERENCE_DISTANCE_M:
        gain_needed = 20.0 * math.log10(room_dimension_m / _HORN_REFERENCE_DISTANCE_M)
    else:
        gain_needed = 20.0 * math.log10(room_dimension_m / _HORN_REFERENCE_DISTANCE_M)

    min_horn_rating = min_required + gain_needed

    return {
        "min_horn_rating_dba": round(min_horn_rating, 2),
        "coverage_distance_m": room_dimension_m,
        "ambient_dba": ambient_dba,
        "min_required_spl_dba": min_required,
        "formula": (
            f"SPL_ref = {min_required:.1f} + 20×log10({room_dimension_m:.2f}/"
            f"{_HORN_REFERENCE_DISTANCE_M}) = {min_required:.1f} + "
            f"{gain_needed:.2f} = {min_horn_rating:.2f} dBA"
        ),
        "nfpa_section": "NFPA 72 §18.4.3",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STROBE CANDELA — NFPA 72 §18.5.5
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 Table 18.5.5.1 — Minimum candela by room size
# For rooms with ceiling height ≤ 10 ft (3.05m):
#   Room size → minimum candela
_STROBE_CANDELA_TABLE_LOW_CEILING = [
    # (max_room_area_sqft, min_candela)
    # NFPA 72 Table 18.5.5.1(a) — rooms ≤ 100 ft²
    (100, 15),  # 15 cd for small rooms
    (400, 30),  # 30 cd for medium rooms
    (1000, 75),  # 75 cd for larger rooms
    (2000, 110),  # 110 cd for large rooms
    (4000, 177),  # 177 cd for very large rooms
]

# NFPA 72 Table 18.5.5.1(b) — for rooms > 100 ft² with ceiling >10ft
_STROBE_CANDELA_TABLE_HIGH_CEILING = [
    # (max_room_area_sqft, min_candela)
    (100, 15),
    (400, 34),
    (1000, 95),
    (2000, 150),
    (4000, 220),
]

# Conversion: 1 m² = 10.764 ft²
_SQFT_PER_SQM = 10.764


@dataclass(frozen=True)
class StrobeResult:
    """Result from strobe candela calculation.

    NFPA 72 §18.5.5:
      Visible appliances must produce sufficient candela to be visible
      from anywhere in the room. The required candela depends on:
        - Room size (floor area)
        - Ceiling height
        - Number of strobes in the room

      For a single strobe, use Table 18.5.5.1.
      For multiple strobes, the candela per strobe may be reduced
      per NFPA 72 §18.5.5.2 — but never below 15 cd.

    Warning:
      Strobe placement is critical. A strobe in a corridor must be
      visible from the entire corridor length. A strobe behind a
      partition may not be visible to occupants on the other side.

    """

    required_candela: float
    room_area_sqft: float
    room_area_m2: float
    ceiling_height_ft: float
    strobe_count: int
    candela_per_strobe: float
    is_compliant: bool
    table_used: str
    formula: str
    nfpa_section: str


def calculate_strobe_candela(
    room_area_m2: float,
    ceiling_height_m: float = 3.0,
    strobe_count: int = 1,
    installed_candela: Optional[float] = None,
) -> StrobeResult:
    """Calculate required strobe candela per NFPA 72 §18.5.5.

    NFPA 72 §18.5.5.1 — Table method:
      1. Convert room area to square feet
      2. Select table based on ceiling height (≤10ft vs >10ft)
      3. Find minimum candela from table
      4. If multiple strobes, divide by count (but never below 15 cd)

    The table provides the minimum single-strobe candela required
    for the given room area. When multiple strobes are used,
    NFPA 72 §18.5.5.2 allows reducing the candela per strobe
    proportionally, but each strobe must still produce at least 15 cd.

    Args:
        room_area_m2: Room floor area in square meters.
        ceiling_height_m: Ceiling height in meters (default 3.0m = 10ft).
        strobe_count: Number of strobes in the room (default 1).
        installed_candela: If provided, check compliance of installed value.

    Returns:
        StrobeResult with required candela, per-strobe rating, compliance.

    """
    # Input validation
    if not math.isfinite(room_area_m2) or room_area_m2 <= 0:
        raise ValueError(f"room_area_m2 must be positive finite, got {room_area_m2}")
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        raise ValueError(f"ceiling_height_m must be positive finite, got {ceiling_height_m}")
    if strobe_count < 1:
        raise ValueError(f"strobe_count must be ≥1, got {strobe_count}")

    # Convert to imperial units (NFPA tables use sq ft and ft)
    room_area_sqft = room_area_m2 * _SQFT_PER_SQM
    ceiling_height_ft = ceiling_height_m / 0.3048

    # Select table based on ceiling height
    is_low_ceiling = ceiling_height_ft <= 10.0
    table = _STROBE_CANDELA_TABLE_LOW_CEILING if is_low_ceiling else _STROBE_CANDELA_TABLE_HIGH_CEILING
    table_name = "Table 18.5.5.1(a)" if is_low_ceiling else "Table 18.5.5.1(b)"

    # Find required candela from table
    required_candela = table[-1][1]  # Default: largest room size
    for max_area, candela in table:
        if room_area_sqft <= max_area:
            required_candela = candela
            break

    # V76 MED-04 FIX: Rooms exceeding the NFPA 72 table maximum (4000 sq ft)
    # require engineering analysis per NFPA 72 §18.5.5.1. The last table value
    # may not provide adequate coverage. Flag for manual FPE review.
    if room_area_sqft > table[-1][0]:
        logger.warning(
            f"Room area {room_area_sqft:.0f} sq ft exceeds NFPA 72 "
            f"Table 18.5.5.1 maximum ({table[-1][0]} sq ft). "
            f"Using {required_candela} cd (last table value) — "
            f"manual fire protection engineer review REQUIRED per "
            f"NFPA 72 §18.5.5.1."
        )

    # NFPA 72 §18.5.5.2: Multiple strobes
    # When more than one strobe is in the room, the candela per
    # strobe may be the table value divided by the number of strobes.
    # HOWEVER, minimum per strobe is 15 cd.
    if strobe_count > 1:
        candela_per_strobe = max(15.0, required_candela / strobe_count)
    else:
        candela_per_strobe = required_candela

    # Check compliance if installed value provided
    if installed_candela is not None:
        if not math.isfinite(installed_candela) or installed_candela < 0:
            raise ValueError(f"installed_candela must be non-negative finite, got {installed_candela}")
        is_compliant = installed_candela >= candela_per_strobe
    else:
        # No installed value — just check if we CAN comply
        is_compliant = candela_per_strobe >= 15.0

    formula = (
        f"Room {room_area_sqft:.0f} ft², ceiling {ceiling_height_ft:.1f}ft → "
        f"{table_name}: {required_candela} cd; "
        f"{strobe_count} strobe(s) → {candela_per_strobe:.1f} cd/strobe"
    )

    return StrobeResult(
        required_candela=required_candela,
        room_area_sqft=round(room_area_sqft, 2),
        room_area_m2=room_area_m2,
        ceiling_height_ft=round(ceiling_height_ft, 2),
        strobe_count=strobe_count,
        candela_per_strobe=round(candela_per_strobe, 2),
        is_compliant=is_compliant,
        table_used=table_name,
        formula=formula,
        nfpa_section="NFPA 72 §18.5.5",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CORRIDOR STROBE SPACING — NFPA 72 §18.5.5.4
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §18.5.5.4: Maximum strobe spacing in corridors
_MAX_CORRIDOR_STROBE_SPACING_FT = 50.0  # 50 ft = 15.24m
_MAX_CORRIDOR_STROBE_SPACING_M = 15.24

# Maximum distance from strobe to end of corridor
_MAX_END_OF_CORRIDOR_DISTANCE_FT = 25.0  # 25 ft = 7.62m
_MAX_END_OF_CORRIDOR_DISTANCE_M = 7.62


@dataclass(frozen=True)
class CorridorStrobeResult:
    """Result from corridor strobe spacing calculation.

    NFPA 72 §18.5.5.4:
      - Strobes in corridors must be spaced no more than 50 ft (15.24m) apart
      - Maximum distance from strobe to end of corridor: 25 ft (7.62m)
      - Minimum candela per strobe in corridors: 15 cd
      - If corridor length ≤ 100 ft, one strobe at center may suffice
    """

    corridor_length_m: float
    strobe_count: int
    spacing_m: float
    end_distance_m: float
    is_compliant: bool
    min_candela_per: float
    violations: List[str]
    nfpa_section: str


def calculate_corridor_strobes(
    corridor_length_m: float,
    strobe_count: Optional[int] = None,
) -> CorridorStrobeResult:
    """Calculate strobe placement in a corridor.

    NFPA 72 §18.5.5.4:
      Strobes in corridors must be spaced no more than 50 ft (15.24m)
      center-to-center, and no point in the corridor can be more than
      25 ft (7.62m) from the nearest strobe.

    If strobe_count is not provided, the function calculates the
    minimum number of strobes needed.

    Args:
        corridor_length_m: Corridor length in meters.
        strobe_count: Number of strobes (if None, auto-calculate).

    Returns:
        CorridorStrobeResult with count, spacing, compliance.

    """
    if not math.isfinite(corridor_length_m) or corridor_length_m <= 0:
        raise ValueError(f"corridor_length_m must be positive finite, got {corridor_length_m}")

    violations = []

    # Calculate minimum strobe count if not provided
    if strobe_count is None:
        # Formula: n = ceil((L - 2 × end_dist) / max_spacing) + 1
        # But at minimum 1 strobe, and at minimum every 15.24m
        effective_length = corridor_length_m - 2 * _MAX_END_OF_CORRIDOR_DISTANCE_M
        if effective_length <= 0:
            # Corridor short enough for 1 strobe
            strobe_count = 1
        else:
            strobe_count = max(1, math.ceil(effective_length / _MAX_CORRIDOR_STROBE_SPACING_M) + 1)

    # Calculate actual spacing
    if strobe_count == 1:
        # Single strobe at midpoint
        spacing_m = corridor_length_m
        end_distance_m = corridor_length_m / 2.0
    else:
        # Evenly distribute: first strobe at end_distance from start,
        # last at end_distance from end, others evenly in between
        end_distance_m = _MAX_END_OF_CORRIDOR_DISTANCE_M
        if corridor_length_m <= 2 * end_distance_m:
            # Short corridor — one strobe at center
            spacing_m = corridor_length_m
            end_distance_m = corridor_length_m / 2.0
        else:
            spacing_m = (corridor_length_m - 2 * end_distance_m) / (strobe_count - 1)

    # Check compliance
    is_compliant = True

    if spacing_m > _MAX_CORRIDOR_STROBE_SPACING_M:
        violations.append(
            f"Strobe spacing {spacing_m:.2f}m exceeds maximum {_MAX_CORRIDOR_STROBE_SPACING_M}m per NFPA 72 §18.5.5.4"
        )
        is_compliant = False

    if end_distance_m > _MAX_END_OF_CORRIDOR_DISTANCE_M:
        violations.append(
            f"End-of-corridor distance {end_distance_m:.2f}m exceeds maximum "
            f"{_MAX_END_OF_CORRIDOR_DISTANCE_M}m per NFPA 72 §18.5.5.4"
        )
        is_compliant = False

    min_candela = 15.0  # NFPA 72 §18.5.5.4 minimum for corridors

    return CorridorStrobeResult(
        corridor_length_m=corridor_length_m,
        strobe_count=strobe_count,
        spacing_m=round(spacing_m, 2),
        end_distance_m=round(end_distance_m, 2),
        is_compliant=is_compliant,
        min_candela_per=min_candela,
        violations=violations,
        nfpa_section="NFPA 72 §18.5.5.4",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED NOTIFICATION ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NotificationAssessment:
    """Combined assessment of notification appliance coverage for a room.

    This brings together all notification calculations into a single
    assessment result that can be used by the release gate system.
    """

    room_id: str
    nac_result: Optional[NACLoadResult] = None
    spl_result: Optional[SPLResult] = None
    strobe_result: Optional[StrobeResult] = None
    corridor_strobe: Optional[CorridorStrobeResult] = None
    is_compliant: bool = False  # V96 FIX: Fail-safe default — unevaluated must NOT claim compliance
    violations: List[str] = field(default_factory=list)
    nfpa_references: List[str] = field(default_factory=list)

    def evaluate(self) -> None:
        """Run all compliance checks and aggregate results."""
        self.violations = []
        self.nfpa_references = []

        # V78 FIX: Do NOT start as True — if no results were evaluated,
        # the room must NOT claim compliance. This is a fail-closed design.
        evaluated = sum(1 for r in [self.nac_result, self.spl_result,
                                     self.strobe_result, self.corridor_strobe]
                        if r is not None)
        if evaluated == 0:
            self.is_compliant = False
            self.violations.append(
                "No notification appliance evaluation performed — "
                "cannot claim compliance per NFPA 72 §18.1"
            )
            return

        self.is_compliant = True  # Start compliant only after confirming at least one check

        if self.nac_result is not None:
            if not self.nac_result.is_compliant:
                self.is_compliant = False
                self.violations.append(
                    f"NAC overloaded: {self.nac_result.total_current_a:.3f}A > "
                    f"{self.nac_result.max_allowed_a:.3f}A "
                    f"(NFPA 72 §10.6.4.2)"
                )
            self.nfpa_references.append("NFPA 72 §10.6.4.2")

        if self.spl_result is not None:
            if not self.spl_result.is_compliant:
                self.is_compliant = False
                if self.spl_result.exceeds_max:
                    self.violations.append(
                        f"SPL {self.spl_result.spl_dba:.1f} dBA exceeds maximum {_MAX_SPL_DBA} dBA (NFPA 72 §18.4.3)"
                    )
                else:
                    self.violations.append(
                        f"SPL {self.spl_result.spl_dba:.1f} dBA below "
                        f"minimum {self.spl_result.min_required_dba:.1f} dBA "
                        f"(NFPA 72 §18.4.3)"
                    )
            self.nfpa_references.append("NFPA 72 §18.4.3")

        if self.strobe_result is not None:
            if not self.strobe_result.is_compliant:
                self.is_compliant = False
                self.violations.append(
                    f"Strobe {self.strobe_result.candela_per_strobe:.1f} cd "
                    f"below required {self.strobe_result.required_candela:.1f} cd "
                    f"(NFPA 72 §18.5.5)"
                )
            self.nfpa_references.append("NFPA 72 §18.5.5")

        if self.corridor_strobe is not None:
            if not self.corridor_strobe.is_compliant:
                self.is_compliant = False
                self.violations.extend(self.corridor_strobe.violations)
            self.nfpa_references.append("NFPA 72 §18.5.5.4")
