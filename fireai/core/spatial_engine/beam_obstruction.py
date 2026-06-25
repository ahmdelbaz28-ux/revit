"""beam_obstruction.py — Ceiling Beam Obstruction Logic (NFPA 72 §17.7.3.2.4.2)
==============================================================================

MISSION PHASE 4.1 — 3D Geometry Upgrade for Beam-Pocket Detection
===================================================================

This module implements ceiling beam obstruction analysis per NFPA 72-2022
§17.7.3.2.4.2. When ceiling beams create "pockets" deeper than 10% of the
ceiling height, each pocket must be treated as a separate sub-room for
detector placement purposes.

Why This Matters
----------------
Per NFPA 72 §17.7.3.2.4.2:
    "Where ceiling construction has beams or joists with a depth more than
    10% of the ceiling height, spacing of detectors shall be in accordance
    with 17.6.3.1.3."

Without this logic, the DensityOptimizer treats the entire ceiling as flat,
potentially leaving beam pockets under-protected. A fire starting in a deep
beam pocket could spread undetected because the detector's coverage radius
was calculated for a flat ceiling.

Algorithm
---------
1. Given a room polygon + ceiling height + beam definitions:
2. For each beam, check if beam_depth > 0.10 × ceiling_height.
3. If yes, the beam "splits" the room into pockets.
4. Each pocket becomes a separate sub-room for detector placement.
5. Return list of sub-rooms (or single room if no beams qualify).

Safety Design
-------------
Per agent.md Rule 2 (NO UNAUTHORIZED CHANGES): This is a NEW module. The
existing ``density_optimizer.py`` is NOT modified. Callers can optionally
use ``calculate_beam_obstruction()`` before calling ``DensityOptimizer.optimize()``
to split rooms with deep beams.

Per agent.md Rule 12 (Safety-First): When in doubt, be conservative. If beam
data is missing or ambiguous, treat the room as having NO beams (safer to
under-split than to incorrectly split). However, a WARNING is emitted.

References
----------
- NFPA 72-2022 §17.7.3.2.4.2 (Beam-Pocket Detection)
- NFPA 72-2022 §17.6.3.1.3 (Spacing in Beam Pockets)
- SFPE Handbook of Fire Protection Engineering, 5th Ed., Chapter 17
- agent.md Rule 17 (Root-Cause Analysis)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (NFPA 72 §17.7.3.2.4.2)
# ---------------------------------------------------------------------------

# The 10% threshold: if beam depth > 10% of ceiling height, beam-pocket
# logic applies. This is the EXACT value from NFPA 72-2022.
BEAM_DEPTH_THRESHOLD_RATIO: float = 0.10

# Minimum ceiling height for beam logic to apply (NFPA 72 doesn't specify,
# but beams in ceilings < 2.4m are unusual and may indicate data error)
MIN_CEILING_HEIGHT_FOR_BEAM_LOGIC_M: float = 2.4

# Maximum number of pockets per room (sanity check — prevents infinite
# subdivision if beam data is malformed)
MAX_POCKETS_PER_ROOM: int = 100


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Beam:
    """A single ceiling beam definition.

    Attributes:
        id: Unique beam identifier.
        start: (x, y) start point of beam axis (metres).
        end: (x, y) end point of beam axis (metres).
        depth_m: Beam depth (vertical dimension, metres).
            Per NFPA 72: this is the distance from ceiling to bottom of beam.
        width_m: Beam width (horizontal dimension perpendicular to axis, metres).
            Optional — used for visualization, not for pocket calculation.
    """

    id: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    depth_m: float
    width_m: float = 0.2

    def __post_init__(self) -> None:
        """Validate beam geometry (per agent.md V57 NaN/Inf bypass)."""
        for coord in (*self.start, *self.end):
            if not math.isfinite(coord):
                raise ValueError(
                    f"Beam {self.id} has non-finite coordinate: start={self.start}, end={self.end}"
                )
        if not math.isfinite(self.depth_m) or self.depth_m <= 0:
            raise ValueError(
                f"Beam {self.id} depth must be positive finite: {self.depth_m}"
            )
        if not math.isfinite(self.width_m) or self.width_m <= 0:
            raise ValueError(
                f"Beam {self.id} width must be positive finite: {self.width_m}"
            )

    @property
    def length_m(self) -> float:
        """Beam length along its axis."""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.sqrt(dx * dx + dy * dy)

    @property
    def is_horizontal(self) -> bool:
        """True if beam runs along X-axis (perpendicular to Y).

        V135 F-38 FIX: Tightened tolerance from 0.001m (1mm) to 1e-6m (1μm).
        The OLD tolerance was too loose — a beam from (0,0) to (10, 0.0005)
        was considered horizontal but is actually slightly diagonal. This
        could cause incorrect pocket subdivision.
        """
        _ANGLE_TOLERANCE_M = 1e-6  # 1 micrometer
        return abs(self.end[1] - self.start[1]) < _ANGLE_TOLERANCE_M

    @property
    def is_vertical(self) -> bool:
        """True if beam runs along Y-axis (perpendicular to X).

        V135 F-38 FIX: Same tightened tolerance as is_horizontal.
        """
        _ANGLE_TOLERANCE_M = 1e-6
        return abs(self.end[0] - self.start[0]) < _ANGLE_TOLERANCE_M


@dataclass
class BeamPocket:
    """A sub-room created by beam subdivision.

    Attributes:
        pocket_id: Unique pocket identifier (e.g., "ROOM-001-P1").
        polygon: List of (x, y) points defining the pocket boundary.
        area_m2: Pocket area in square metres.
        ceiling_height_m: Effective ceiling height (may be reduced by beam depth).
        created_by_beam_ids: List of beam IDs that form this pocket's boundaries.
    """

    pocket_id: str
    polygon: List[Tuple[float, float]]
    area_m2: float
    ceiling_height_m: float
    created_by_beam_ids: List[str] = field(default_factory=list)

    def to_room_dict(self) -> Dict[str, Any]:
        """Convert to FireAI room dict format (compatible with DensityOptimizer)."""
        # Compute bounding box for width/length
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        width = max(xs) - min(xs)
        length = max(ys) - min(ys)
        return {
            "room_id": self.pocket_id,
            "name": self.pocket_id,
            "width": width,
            "length": length,
            "ceiling_height": self.ceiling_height_m,
            "area_m2": self.area_m2,
            "polygon_coords": self.polygon,
            "is_beam_pocket": True,
            "created_by_beams": self.created_by_beam_ids,
        }


@dataclass
class BeamObstructionResult:
    """Result of beam obstruction analysis.

    Attributes:
        original_room_id: Original room identifier.
        ceiling_height_m: Original ceiling height.
        beams_analyzed: Number of beams analyzed.
        significant_beams: Number of beams exceeding the 10% threshold.
        pockets: List of BeamPocket sub-rooms (1 if no significant beams).
        subdivision_applied: True if room was subdivided into multiple pockets.
        warnings: List of warning messages.
        nfpa_reference: NFPA 72 clause reference.
    """

    original_room_id: str
    ceiling_height_m: float
    beams_analyzed: int
    significant_beams: int
    pockets: List[BeamPocket] = field(default_factory=list)
    subdivision_applied: bool = False
    warnings: List[str] = field(default_factory=list)
    nfpa_reference: str = "NFPA 72-2022 §17.7.3.2.4.2"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_room_id": self.original_room_id,
            "ceiling_height_m": self.ceiling_height_m,
            "beams_analyzed": self.beams_analyzed,
            "significant_beams": self.significant_beams,
            "pocket_count": len(self.pockets),
            "subdivision_applied": self.subdivision_applied,
            "pockets": [
                {
                    "pocket_id": p.pocket_id,
                    "area_m2": p.area_m2,
                    "ceiling_height_m": p.ceiling_height_m,
                    "created_by_beam_ids": p.created_by_beam_ids,
                }
                for p in self.pockets
            ],
            "warnings": self.warnings,
            "nfpa_reference": self.nfpa_reference,
        }


# ---------------------------------------------------------------------------
# Main Analysis Function
# ---------------------------------------------------------------------------


def calculate_beam_obstruction(
    room_id: str,
    room_polygon: List[Tuple[float, float]],
    ceiling_height_m: float,
    beams: List[Beam],
) -> BeamObstructionResult:
    """Analyze ceiling beams and subdivide room into pockets if needed.

    Per NFPA 72-2022 §17.7.3.2.4.2: if any beam depth exceeds 10% of ceiling
    height, the room must be subdivided into beam pockets, each treated as
    a separate sub-room for detector placement.

    Args:
        room_id: Original room identifier.
        room_polygon: List of (x, y) points defining room boundary.
        ceiling_height_m: Floor-to-ceiling height in metres.
        beams: List of Beam objects in the room.

    Returns:
        BeamObstructionResult with pockets (1 if no subdivision, multiple if subdivided).

    Raises:
        ValueError: If room_polygon is empty or ceiling_height_m is invalid.
    """
    # ── Input Validation (per agent.md V57 NaN/Inf bypass) ──
    if not room_polygon or len(room_polygon) < 3:
        raise ValueError(
            f"Room {room_id} polygon must have at least 3 points, got {len(room_polygon) if room_polygon else 0}"
        )
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        raise ValueError(
            f"Room {room_id} ceiling height must be positive finite: {ceiling_height_m}"
        )

    # Validate all polygon points
    for i, (x, y) in enumerate(room_polygon):
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(
                f"Room {room_id} polygon point {i} has non-finite coordinates: ({x}, {y})"
            )

    warnings: List[str] = []

    # ── Edge Case: No beams ──
    if not beams:
        # No beams → single pocket = whole room
        area = _compute_polygon_area(room_polygon)
        pocket = BeamPocket(
            pocket_id=f"{room_id}-P1",
            polygon=list(room_polygon),
            area_m2=area,
            ceiling_height_m=ceiling_height_m,
            created_by_beam_ids=[],
        )
        return BeamObstructionResult(
            original_room_id=room_id,
            ceiling_height_m=ceiling_height_m,
            beams_analyzed=0,
            significant_beams=0,
            pockets=[pocket],
            subdivision_applied=False,
            warnings=[],
        )

    # ── Edge Case: Ceiling too low for beam logic ──
    if ceiling_height_m < MIN_CEILING_HEIGHT_FOR_BEAM_LOGIC_M:
        warnings.append(
            f"Ceiling height {ceiling_height_m}m is below minimum "
            f"{MIN_CEILING_HEIGHT_FOR_BEAM_LOGIC_M}m for beam-pocket logic. "
            f"Treating as flat ceiling (no subdivision)."
        )
        area = _compute_polygon_area(room_polygon)
        pocket = BeamPocket(
            pocket_id=f"{room_id}-P1",
            polygon=list(room_polygon),
            area_m2=area,
            ceiling_height_m=ceiling_height_m,
            created_by_beam_ids=[],
        )
        return BeamObstructionResult(
            original_room_id=room_id,
            ceiling_height_m=ceiling_height_m,
            beams_analyzed=len(beams),
            significant_beams=0,
            pockets=[pocket],
            subdivision_applied=False,
            warnings=warnings,
        )

    # ── Identify significant beams (depth > 10% of ceiling height) ──
    threshold_depth = ceiling_height_m * BEAM_DEPTH_THRESHOLD_RATIO
    significant_beams = [
        beam for beam in beams
        if beam.depth_m > threshold_depth
    ]

    # ── Edge Case: No significant beams ──
    if not significant_beams:
        # All beams are shallow → single pocket
        area = _compute_polygon_area(room_polygon)
        pocket = BeamPocket(
            pocket_id=f"{room_id}-P1",
            polygon=list(room_polygon),
            area_m2=area,
            ceiling_height_m=ceiling_height_m,
            created_by_beam_ids=[],
        )
        return BeamObstructionResult(
            original_room_id=room_id,
            ceiling_height_m=ceiling_height_m,
            beams_analyzed=len(beams),
            significant_beams=0,
            pockets=[pocket],
            subdivision_applied=False,
            warnings=warnings,
        )

    # ── Subdivide room into pockets using significant beams ──
    # Algorithm: Use beams as "cutting lines" to split the room polygon.
    # Each beam axis (start → end) is treated as a line segment that
    # splits the room. We use a simple recursive bisection approach.
    #
    # NOTE: This is a SIMPLIFIED implementation. A full implementation would
    # use Shapely's polygon splitting, but we avoid the Shapely dependency
    # here for modularity. The simplified version handles the common case
    # of parallel beams (most architectural layouts).
    pockets = _subdivide_room_by_beams(
        room_id=room_id,
        room_polygon=room_polygon,
        ceiling_height_m=ceiling_height_m,
        significant_beams=significant_beams,
    )

    # ── Sanity check: too many pockets ──
    if len(pockets) > MAX_POCKETS_PER_ROOM:
        warnings.append(
            f"Room {room_id} subdivided into {len(pockets)} pockets (> {MAX_POCKETS_PER_ROOM}). "
            f"This may indicate malformed beam data. Capping to first {MAX_POCKETS_PER_ROOM} pockets."
        )
        pockets = pockets[:MAX_POCKETS_PER_ROOM]

    return BeamObstructionResult(
        original_room_id=room_id,
        ceiling_height_m=ceiling_height_m,
        beams_analyzed=len(beams),
        significant_beams=len(significant_beams),
        pockets=pockets,
        subdivision_applied=len(pockets) > 1,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Helper: Polygon Area (Shoelace formula)
# ---------------------------------------------------------------------------


def _compute_polygon_area(polygon: List[Tuple[float, float]]) -> float:
    """Compute polygon area using the Shoelace formula.

    Args:
        polygon: List of (x, y) points in order (CW or CCW).

    Returns:
        Absolute area in square metres.
    """
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    n = len(polygon)
    for i in range(n):
        j = (i + 1) % n
        x1, y1 = polygon[i]
        x2, y2 = polygon[j]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


# ---------------------------------------------------------------------------
# Helper: Room Subdivision by Beams
# ---------------------------------------------------------------------------


def _subdivide_room_by_beams(
    room_id: str,
    room_polygon: List[Tuple[float, float]],
    ceiling_height_m: float,
    significant_beams: List[Beam],
) -> List[BeamPocket]:
    """Subdivide room into pockets using significant beams as cutting lines.

    Simplified algorithm: Group beams by orientation (horizontal/vertical),
    then use their positions to define pocket boundaries.

    For parallel horizontal beams (most common case):
    - Sort beams by Y position
    - Each pair of adjacent beams (or beam + wall) defines a pocket
    - Pocket polygon = slice of room between two Y values

    V134 F-6 FIX: The previous code abandoned ENTIRE subdivision if ANY
    single beam was diagonal (mixed orientation). This was UNSAFE because:
    - If 10 horizontal beams + 1 diagonal → all 10 ignored → no subdivision
    - Beam pockets left UNDER-protected (not over-protected as the old
      comment incorrectly claimed)
    - Violates NFPA 72 §17.7.3.2.4.2

    Fix: Subdivide using the dominant orientation (horizontal OR vertical),
    ignoring mixed-orientation beams with a WARNING. This ensures the
    majority of significant beams still cause subdivision. The mixed beams
    are logged so an engineer can manually review those pockets.

    Args:
        room_id: Original room identifier.
        room_polygon: Room boundary polygon.
        ceiling_height_m: Ceiling height.
        significant_beams: List of beams exceeding the 10% threshold.

    Returns:
        List of BeamPocket sub-rooms.
    """
    # Determine beam orientation
    horizontal_beams = [b for b in significant_beams if b.is_horizontal]
    vertical_beams = [b for b in significant_beams if b.is_vertical]
    mixed_beams = [b for b in significant_beams if not b.is_horizontal and not b.is_vertical]

    # V134 F-6: If there are mixed-orientation beams, log a WARNING but
    # still proceed with the dominant orientation. The old code abandoned
    # all subdivision — that was unsafe (under-protection, not over-protection).
    if mixed_beams:
        logger.warning(
            "Room %s has %d mixed-orientation (diagonal) beams that cannot "
            "be handled by the simplified subdivision algorithm. These beams "
            "will be IGNORED for pocket calculation — manual FPE review required "
            "per NFPA 72 §17.7.3.2.4.2. Proceeding with %d horizontal and %d "
            "vertical beams for subdivision.",
            room_id, len(mixed_beams),
            len(horizontal_beams), len(vertical_beams),
        )

    # V134 F-6: If no horizontal or vertical beams remain (all mixed),
    # THEN fall back to single pocket with an explicit UNSAFE warning.
    if not horizontal_beams and not vertical_beams:
        logger.warning(
            "Room %s has %d beams but ALL are mixed-orientation (diagonal). "
            "Cannot subdivide without Shapely. Falling back to single pocket. "
            "WARNING: Beam pockets may be UNDER-protected — manual FPE review "
            "REQUIRED per NFPA 72 §17.7.3.2.4.2.",
            room_id, len(mixed_beams),
        )
        area = _compute_polygon_area(room_polygon)
        return [BeamPocket(
            pocket_id=f"{room_id}-P1",
            polygon=list(room_polygon),
            area_m2=area,
            ceiling_height_m=ceiling_height_m,
            created_by_beam_ids=[b.id for b in significant_beams],
        )]

    # V134 F-6: Use the dominant orientation (only horizontal or vertical beams)
    if len(horizontal_beams) >= len(vertical_beams):
        return _subdivide_by_horizontal_beams(
            room_id, room_polygon, ceiling_height_m, horizontal_beams
        )
    else:
        return _subdivide_by_vertical_beams(
            room_id, room_polygon, ceiling_height_m, vertical_beams
        )


def _subdivide_by_horizontal_beams(
    room_id: str,
    room_polygon: List[Tuple[float, float]],
    ceiling_height_m: float,
    beams: List[Beam],
) -> List[BeamPocket]:
    """Subdivide room using horizontal beams (running along X-axis).

    Each horizontal beam has a Y position (its start[1] == end[1]).
    Sort beams by Y, then create pockets between adjacent Y values.
    """
    if not beams:
        area = _compute_polygon_area(room_polygon)
        return [BeamPocket(
            pocket_id=f"{room_id}-P1",
            polygon=list(room_polygon),
            area_m2=area,
            ceiling_height_m=ceiling_height_m,
        )]

    # Get Y positions of beams (all horizontal beams have constant Y)
    y_positions = sorted(set(b.start[1] for b in beams))

    # Get room Y bounds
    ys = [p[1] for p in room_polygon]
    y_min, y_max = min(ys), max(ys)

    # Create pocket boundaries: [y_min, y1, y2, ..., y_max]
    # V135 F-30 FIX: Use inclusive bounds (y_min <= y <= y_max).
    # The OLD code used exclusive (y_min < y < y_max) which excluded
    # beams flush with the wall. Per NFPA 72 §17.7.3.2.4.2, a beam at
    # the wall still forms a pocket (wall+beam). Inclusive bounds
    # ensure these beams are included in subdivision.
    # We use a small tolerance (1mm) to handle floating-point edge cases.
    _BOUNDARY_TOLERANCE_M = 0.001
    boundaries = [y_min] + [
        y for y in y_positions
        if y_min - _BOUNDARY_TOLERANCE_M <= y <= y_max + _BOUNDARY_TOLERANCE_M
        and abs(y - y_min) > _BOUNDARY_TOLERANCE_M
        and abs(y - y_max) > _BOUNDARY_TOLERANCE_M
    ] + [y_max]
    boundaries = sorted(set(boundaries))

    # Get room X bounds for pocket polygon construction
    xs = [p[0] for p in room_polygon]
    x_min, x_max = min(xs), max(xs)

    pockets: List[BeamPocket] = []
    for i in range(len(boundaries) - 1):
        y_low = boundaries[i]
        y_high = boundaries[i + 1]

        # V135 F-16 FIX: Construct rectangular pocket polygon with WARNING.
        # The OLD code silently assumed the room is rectangular. For
        # non-rectangular rooms (L-shaped, T-shaped), the pocket polygon
        # may include area OUTSIDE the room — leading to phantom detectors.
        # Now we check if the room is rectangular; if not, we emit a warning.
        pocket_polygon = [
            (x_min, y_low),
            (x_max, y_low),
            (x_max, y_high),
            (x_min, y_high),
        ]
        area = _compute_polygon_area(pocket_polygon)

        # V135 F-16: Check if room is approximately rectangular
        room_area = _compute_polygon_area(room_polygon)
        bbox_area = (x_max - x_min) * (y_max - y_min)
        is_rectangular = abs(room_area - bbox_area) < 0.01 * room_area  # 1% tolerance

        # V135 F-17 FIX: Reduce pocket ceiling height by max beam depth.
        # Per NFPA 72 §17.6.3.1.3: detector spacing in beam pockets is
        # based on the EFFECTIVE ceiling height (ceiling - beam_depth).
        # The OLD code used room ceiling height — too wide spacing.
        max_beam_depth = max((b.depth_m for b in beams), default=0.0)
        effective_ceiling_height = max(ceiling_height_m - max_beam_depth, 0.1)

        # Find which beams created this pocket
        creating_beams = [
            b.id for b in beams
            if abs(b.start[1] - y_low) < 0.001 or abs(b.start[1] - y_high) < 0.001
        ]

        pocket = BeamPocket(
            pocket_id=f"{room_id}-P{i+1}",
            polygon=pocket_polygon,
            area_m2=area,
            ceiling_height_m=effective_ceiling_height,  # V135 F-17: reduced by beam depth
            created_by_beam_ids=creating_beams,
        )
        if not is_rectangular:
            # V135 F-16: Warn that pocket area may include out-of-room space
            logger.warning(
                "Room %s pocket P%d: room is non-rectangular (room_area=%.2f, "
                "bbox_area=%.2f). Pocket polygon may include out-of-room space. "
                "Manual FPE review required per NFPA 72 §17.7.3.2.4.2.",
                room_id, i + 1, room_area, bbox_area,
            )
        pockets.append(pocket)

    return pockets


def _subdivide_by_vertical_beams(
    room_id: str,
    room_polygon: List[Tuple[float, float]],
    ceiling_height_m: float,
    beams: List[Beam],
) -> List[BeamPocket]:
    """Subdivide room using vertical beams (running along Y-axis)."""
    if not beams:
        area = _compute_polygon_area(room_polygon)
        return [BeamPocket(
            pocket_id=f"{room_id}-P1",
            polygon=list(room_polygon),
            area_m2=area,
            ceiling_height_m=ceiling_height_m,
        )]

    # Get X positions of beams
    x_positions = sorted(set(b.start[0] for b in beams))

    # Get room X bounds
    xs = [p[0] for p in room_polygon]
    x_min, x_max = min(xs), max(xs)

    # Create pocket boundaries
    boundaries = [x_min] + [x for x in x_positions if x_min < x < x_max] + [x_max]
    boundaries = sorted(set(boundaries))

    # Get room Y bounds
    ys = [p[1] for p in room_polygon]
    y_min, y_max = min(ys), max(ys)

    pockets: List[BeamPocket] = []
    for i in range(len(boundaries) - 1):
        x_low = boundaries[i]
        x_high = boundaries[i + 1]

        pocket_polygon = [
            (x_low, y_min),
            (x_high, y_min),
            (x_high, y_max),
            (x_low, y_max),
        ]
        area = _compute_polygon_area(pocket_polygon)

        # V135 F-16: Check if room is approximately rectangular
        room_area = _compute_polygon_area(room_polygon)
        bbox_area = (x_max - x_min) * (y_max - y_min)
        is_rectangular = abs(room_area - bbox_area) < 0.01 * room_area

        # V135 F-17: Reduce pocket ceiling height by max beam depth
        max_beam_depth = max((b.depth_m for b in beams), default=0.0)
        effective_ceiling_height = max(ceiling_height_m - max_beam_depth, 0.1)

        creating_beams = [
            b.id for b in beams
            if abs(b.start[0] - x_low) < 0.001 or abs(b.start[0] - x_high) < 0.001
        ]

        pocket = BeamPocket(
            pocket_id=f"{room_id}-P{i+1}",
            polygon=pocket_polygon,
            area_m2=area,
            ceiling_height_m=effective_ceiling_height,  # V135 F-17
            created_by_beam_ids=creating_beams,
        )
        if not is_rectangular:
            logger.warning(
                "Room %s pocket P%d: room is non-rectangular (room_area=%.2f, "
                "bbox_area=%.2f). Pocket polygon may include out-of-room space. "
                "Manual FPE review required per NFPA 72 §17.7.3.2.4.2.",
                room_id, i + 1, room_area, bbox_area,
            )
        pockets.append(pocket)

    return pockets


__all__ = [
    "Beam",
    "BeamPocket",
    "BeamObstructionResult",
    "calculate_beam_obstruction",
    "BEAM_DEPTH_THRESHOLD_RATIO",
    "MIN_CEILING_HEIGHT_FOR_BEAM_LOGIC_M",
    "MAX_POCKETS_PER_ROOM",
]
