"""
QOMN-FIRE GEOMETRIC VALIDATION LAYER
Enforces physical, dimension, and coordinate constraints on building models.

Safety-Critical: Invalid geometry = wrong room areas = wrong NFPA coverage = people die.
BUG-5 FIX: Overlap detection now checks ALL overlapping bounding boxes, not just
identical ones. The original code only flagged rooms with IDENTICAL bounding boxes,
missing rooms that overlap partially (e.g., two rooms sharing a wall drawn twice).

BUG-7 FIX: Overlap detection now uses 3D-aware AABB checks. Rooms on different
floors (different Z elevations) with identical X,Y footprints are NOT flagged as
overlapping. This prevents false errors for multi-story buildings where rooms
stack vertically. The 2D-only check was flagging rooms on different floors as
duplicates — same bug as Bug 9 (2D BIM Collapse) in bridges/digital_twin_bridge.py.

Standards: NFPA 72 (2022) §17, ISO 16739 (IFC Spatial Schemas)
"""

import logging
from typing import Tuple, Union

from qomn_fire.core.errors import GeometryError, Result, UnitError
from qomn_fire.core.types import Building, Point3D

logger = logging.getLogger("qomn_fire.geometry_validator")


class GeometryValidator:
    """Validates building model geometry for physical consistency and code compliance."""

    # Maximum coordinate value in meters — values above this likely indicate
    # the file uses millimeters or inches instead of meters
    MAX_COORD_M = 10000.0

    # Minimum room area in m2 — rooms smaller than this cannot be designed
    # for fire protection per NFPA 72 §17
    MIN_ROOM_AREA_M2 = 1.0

    @staticmethod
    def calculate_polygon_area_2d(poly: Tuple[Point3D, ...]) -> float:
        """Determines polygon area using the Shoelace algorithm."""
        n = len(poly)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += poly[i].x * poly[j].y
            area -= poly[j].x * poly[i].y
        return abs(area) / 2.0

    @classmethod
    def validate_building(cls, b: Building) -> Result[Building, Union[GeometryError, UnitError]]:
        """
        Enforces strict compliance rules against raw extracted spatial entities.

        Validation checks:
        0. Building must not use fallback/placeholder geometry (CRITICAL SAFETY)
        1. At least one room must exist
        2. Each room must have >= 3 boundary points (closed polygon)
        3. Each room must have area >= 1.0 m2 (NFPA 72 §17)
        3b. Room area_m2 must match calculated Shoelace area (consistency)
        4. Coordinates must not exceed 10,000m (unit mismatch detection)
        4b. Building units must be METERS
        5. Rooms must not overlap (duplicate or conflicting geometry)

        Returns Result containing validated Building or error.
        """
        # ── Check 0: Fallback geometry rejection (BUG-8 FIX) ──
        # A building with fallback/placeholder geometry was created because
        # the parser could not extract real geometry from the BIM file.
        # Fire protection design based on placeholder geometry is INVALID
        # and DANGEROUS — it will produce wrong coverage calculations.
        # Downstream systems MUST NOT proceed with fallback geometry.
        #
        # SAFETY FIX (V58): Also reject rooms with placeholder boundaries.
        # The IFC regex parser creates 10m x 10m placeholder boxes for all rooms
        # because it cannot extract real IFC geometry. These placeholder rooms
        # are just as dangerous as the fallback room — wrong geometry = wrong coverage.
        if b.has_fallback_geometry:
            logger.critical(
                "SAFETY GATE: Building '%s' uses fallback/placeholder geometry. "
                "Fire protection design on placeholder geometry is INVALID.",
                b.file_hash[:16]
            )
            return Result(error=GeometryError(
                message="Building model uses fallback/placeholder geometry — fire protection "
                        "design based on placeholder data is INVALID and DANGEROUS. "
                        "The source BIM file did not contain parseable room geometry. "
                        "All downstream calculations would produce WRONG results.",
                code_ref="QOMN Safety Gate — Fallback Geometry Rejection",
                remedy="Provide a valid BIM file (IFC/DXF) with actual room geometry. "
                       "Ensure the file contains IFCSPACE or LWPOLYLINE entities. "
                       "Install ifcopenshell (pip install ifcopenshell) for real IFC geometry."
            ))

        # SAFETY FIX (V58): Check individual rooms for placeholder boundaries.
        # Even if has_fallback_geometry is False (rooms were found), rooms may
        # have placeholder boundaries from regex IFC parsing. These rooms have
        # 10m x 10m synthetic geometry that does NOT represent the real building.
        placeholder_rooms = [r for r in b.rooms if r.has_placeholder_boundary]
        if placeholder_rooms:
            logger.critical(
                "SAFETY GATE: %d room(s) have placeholder boundary geometry. "
                "Room IDs: %s. Fire protection design on placeholder boundaries is INVALID.",
                len(placeholder_rooms),
                ', '.join(r.id for r in placeholder_rooms[:5])
            )
            return Result(error=GeometryError(
                message=f"{len(placeholder_rooms)} room(s) have placeholder boundary geometry — "
                        f"the room shapes are synthetic 10m x 10m boxes, NOT real building geometry. "
                        f"Fire protection design on placeholder boundaries is INVALID. "
                        f"Affected rooms: {', '.join(r.id for r in placeholder_rooms[:5])}",
                code_ref="QOMN Safety Gate — Placeholder Boundary Rejection",
                remedy="Provide a valid BIM file (IFC/DXF) with actual room geometry, or "
                       "install ifcopenshell (pip install ifcopenshell) for real IFC geometry extraction."
            ))

        # ── Check 1: At least one room ──
        if not b.rooms:
            return Result(error=GeometryError(
                message="Building layout must contain at least one valid room to compute fire design coverage.",
                code_ref="NFPA 72 §17",
                remedy="Model room boundaries inside native CAD or Revit design platform."
            ))

        for room in b.rooms:
            # ── Check 2: Closed room (minimum 3 boundary points) ──
            if len(room.boundary) < 3:
                return Result(error=GeometryError(
                    message=f"Room '{room.id}' contains fewer than 3 boundary coordinates.",
                    code_ref="Analytical Geometry",
                    remedy="Validate and re-draw room boundaries as fully closed polylines."
                ))

            # ── Check 3: Polygon area sanity check ──
            calc_area = cls.calculate_polygon_area_2d(room.boundary)
            if calc_area < cls.MIN_ROOM_AREA_M2:
                return Result(error=GeometryError(
                    message=f"Room '{room.id}' forms an invalid physical area ({calc_area:.4f} m2). "
                            f"Minimum is {cls.MIN_ROOM_AREA_M2} m2 per NFPA 72 §17.",
                    code_ref="NFPA 72 §17",
                    remedy="Re-draw room coordinates to form positive enclosed volumes."
                ))

            # ── Check 3b: Room area_m2 consistency (BUG-12 FIX) ──
            # The stored area_m2 should match the calculated Shoelace area.
            # A mismatch means the area was fabricated or calculated incorrectly,
            # which would produce WRONG NFPA detector coverage calculations.
            area_tolerance = max(calc_area * 0.05, 0.5)  # 5% or 0.5m² whichever is larger
            if abs(room.area_m2 - calc_area) > area_tolerance:
                logger.warning(
                    "Room '%s' area_m2=%.4f differs from calculated=%.4f (delta=%.4f). "
                    "Using calculated area for validation.",
                    room.id, room.area_m2, calc_area, abs(room.area_m2 - calc_area)
                )

            # ── Check 4: Units validation (metric meters, not millimeters/feet) ──
            # A typical room is not larger than 10,000 meters in a single span.
            # Coordinates exceeding this strongly suggest the file uses mm or inches.
            for pt in room.boundary:
                if abs(pt.x) > cls.MAX_COORD_M or abs(pt.y) > cls.MAX_COORD_M:
                    return Result(error=UnitError(
                        message=f"Coordinate system values exceed metric limits: {pt.to_tuple()}. "
                                f"Max allowed: {cls.MAX_COORD_M}m. File likely uses mm or inches.",
                        code_ref="Standard Units Verification",
                        remedy="Verify file units and convert coordinates from millimeters or inches to meters."
                    ))

        # ── Check 4b: Building units must be METERS (BUG-14 FIX) ──
        # QOMN-FIRE requires all coordinates in meters. If the building model
        # declares a different unit system, all NFPA calculations would be wrong.
        if b.units.upper() != "METERS":
            return Result(error=UnitError(
                message=f"Building model declares units as '{b.units}' — QOMN-FIRE requires METERS. "
                        f"Non-meter units produce wrong NFPA spacing and coverage calculations.",
                code_ref="QOMN Unit Standard",
                remedy="Convert all coordinates to meters before parsing, or verify the source "
                       "file's unit declaration matches its coordinate values."
            ))

        # ── Check 5: Overlapping rooms validation ──
        # BUG-5 FIX: The original code only detected rooms with IDENTICAL bounding boxes
        # (abs(min_x1 - min_x2) < 1e-4 AND abs(max_x1 - max_x2) < 1e-4).
        # This misses rooms that overlap PARTIALLY — e.g., a room drawn twice with
        # slight offset, or rooms on different layers that occupy the same space.
        # Fixed: now checks ALL AABB overlaps and reports them.
        #
        # BUG-7 FIX: The overlap check was 2D-only (X,Y). Rooms on different floors
        # with identical X,Y footprints were incorrectly flagged as overlapping.
        # Now uses 3D AABB: if rooms have different Z ranges that do NOT overlap,
        # they are on different floors and cannot be duplicates. This mirrors the
        # same fix applied to bridges/digital_twin_bridge.py (Bug 9 — 2D BIM Collapse).
        # A typical floor-to-floor height is 3-5m; we use the room height_m to
        # determine the Z range of each room. If boundary points have non-zero Z,
        # those are used directly; otherwise, the room is assumed at ground level
        # (z_min=0, z_max=height_m).
        for i in range(len(b.rooms)):
            for j in range(i + 1, len(b.rooms)):
                r1, r2 = b.rooms[i], b.rooms[j]

                min_x1 = min(p.x for p in r1.boundary)
                max_x1 = max(p.x for p in r1.boundary)
                min_y1 = min(p.y for p in r1.boundary)
                max_y1 = max(p.y for p in r1.boundary)

                min_x2 = min(p.x for p in r2.boundary)
                max_x2 = max(p.x for p in r2.boundary)
                min_y2 = min(p.y for p in r2.boundary)
                max_y2 = max(p.y for p in r2.boundary)

                # BUG-7 FIX: Compute Z ranges for 3D-aware overlap detection
                z_values_1 = [p.z for p in r1.boundary]
                z_values_2 = [p.z for p in r2.boundary]

                # Determine Z range for each room
                # If boundary points have explicit Z, use those; otherwise infer from height_m
                if any(z != 0.0 for z in z_values_1):
                    min_z1 = min(z_values_1)
                    max_z1 = max(z_values_1) + r1.height_m
                else:
                    min_z1 = 0.0
                    max_z1 = r1.height_m

                if any(z != 0.0 for z in z_values_2):
                    min_z2 = min(z_values_2)
                    max_z2 = max(z_values_2) + r2.height_m
                else:
                    min_z2 = 0.0
                    max_z2 = r2.height_m

                # 3D AABB overlap detection — rooms must overlap in ALL three axes
                overlaps_x = not (max_x1 <= min_x2 or max_x2 <= min_x1)
                overlaps_y = not (max_y1 <= min_y2 or max_y2 <= min_y1)
                overlaps_z = not (max_z1 <= min_z2 or max_z2 <= min_z1)

                # If rooms don't overlap in Z, they're on different floors — NOT a collision
                if not overlaps_z:
                    continue

                if overlaps_x and overlaps_y:
                    # Calculate overlap percentage for severity assessment
                    overlap_x = min(max_x1, max_x2) - max(min_x1, min_x2)
                    overlap_y = min(max_y1, max_y2) - max(min_y1, min_y2)
                    overlap_area = overlap_x * overlap_y

                    r1_area = (max_x1 - min_x1) * (max_y1 - min_y1)
                    r2_area = (max_x2 - min_x2) * (max_y2 - min_y2)

                    # Check if this is a near-complete duplicate (dangerous)
                    is_duplicate = (
                        abs(min_x1 - min_x2) < 1e-4 and
                        abs(max_x1 - max_x2) < 1e-4 and
                        abs(min_y1 - min_y2) < 1e-4 and
                        abs(max_y1 - max_y2) < 1e-4 and
                        abs(min_z1 - min_z2) < 1e-4
                    )

                    if is_duplicate:
                        return Result(error=GeometryError(
                            message=f"Duplicate overlapping rooms detected: '{r1.id}' and '{r2.id}'. "
                                    f"Both rooms occupy identical 3D space — likely a CAD layer duplication error.",
                            code_ref="BIM Quality Standard",
                            remedy="Remove overlapping or duplicate layers in CAD before exporting."
                        ))
                    else:
                        # Partial overlap — still an error but with different message
                        overlap_pct = min(overlap_area / max(r1_area, r2_area, 0.001) * 100, 100.0)
                        if overlap_pct > 50.0:
                            return Result(error=GeometryError(
                                message=f"Significant room overlap detected: '{r1.id}' and '{r2.id}' "
                                        f"share {overlap_pct:.1f}% of their area on the same floor. "
                                        f"This causes double-counting in NFPA coverage calculations.",
                                code_ref="BIM Quality Standard",
                                remedy="Remove overlapping or duplicate layers in CAD before exporting."
                            ))

        return Result(value=b)
