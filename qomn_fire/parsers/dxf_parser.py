"""
QOMN-FIRE DXF GEOMETRY PARSER
Parses DXF files and extracts boundary shapes (rooms, walls, openings).

Safety-Critical: Wrong DXF parsing = wrong room geometry = wrong detector coverage.
BUG-4 FIX: Area is now CALCULATED from boundary vertices using Shoelace formula,
NOT hardcoded to 100.0 m2. A hardcoded area is a safety lie — it claims
a room is 100m2 when it could be 5m2 or 500m2, producing WRONG NFPA coverage.

BUG-9 FIX: has_fallback_geometry flag is now set when fallback room is used.
Downstream systems MUST check this flag — design based on fallback geometry is INVALID.

BUG-10 FIX: _dxf_group_pairs() now preserves multi-value group codes (like repeated
group code 10/20 for LWPOLYLINE vertices) using lists instead of overwriting.

BUG-11 FIX: _extract_polyline_points() now actually extracts vertices from the
multi-value group codes, instead of always returning an empty list.

Standards: AutoCAD DXF Specification, NFPA 72 (2022)
"""

import logging
import re
from typing import Tuple, List

from qomn_fire.core.types import Point3D, Wall, Room, Opening, Building
from qomn_fire.core.errors import Result, GeometryError

logger = logging.getLogger("qomn_fire.dxf_parser")


class DxfParser:
    """Parses DXF entities (LINES and LWPOLYLINES) into standard structural types."""

    @staticmethod
    def parse_dxf(filepath: str, file_hash: str) -> Result[Building, GeometryError]:
        """
        Parses DXF entities (LINES and LWPOLYLINES) into standard structural types.
        Citing: AutoCAD DXF Standards, NFPA 72 §17.
        """
        walls: List[Wall] = []
        rooms: List[Room] = []
        openings: List[Opening] = []

        # ── Try ezdxf first (production path) ──
        try:
            import ezdxf
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()

            # Extract closed LWPOLYLINE boundaries representing rooms
            for idx, lwpoly in enumerate(msp.query("LWPOLYLINE")):
                if lwpoly.closed:
                    pts = tuple([Point3D(p[0], p[1], 0.0) for p in lwpoly.get_points(format='xy')])
                    if len(pts) >= 3:
                        area = DxfParser._calculate_polygon_area(pts)
                        rooms.append(Room(
                            id=f"DXF_ROOM_{idx:03d}",
                            name=f"Room {idx}",
                            boundary=pts,
                            area_m2=area,  # BUG-4 FIX: Calculated, not hardcoded
                            height_m=3.0
                        ))

            # Extract LINE structures representing wall paths
            for idx, line in enumerate(msp.query("LINE")):
                walls.append(Wall(
                    id=f"DXF_WALL_{idx:03d}",
                    start=Point3D(line.dxf.start[0], line.dxf.start[1], 0.0),
                    end=Point3D(line.dxf.end[0], line.dxf.end[1], 0.0),
                    height_m=3.0,
                    thickness_m=0.20
                ))

        except ImportError:
            # ezdxf not available — fall back to text-based DXF parsing
            DxfParser._parse_dxf_text(filepath, walls, rooms)
        except Exception:
            # ezdxf failed — fall back to text-based DXF parsing
            DxfParser._parse_dxf_text(filepath, walls, rooms)

        # BUG-9 FIX: Set has_fallback_geometry flag when fallback room is injected.
        # Downstream systems MUST check this flag — fire protection design based
        # on fallback geometry is INVALID and must be rejected.
        has_fallback = False
        if not rooms:
            fallback_boundary = (
                Point3D(0.0, 0.0, 0.0),
                Point3D(10.0, 0.0, 0.0),
                Point3D(10.0, 10.0, 0.0),
                Point3D(0.0, 10.0, 0.0)
            )
            rooms.append(Room(
                id="DXF_ROOM_FALLBACK",
                name="Fallback Room (DXF parsing found no rooms)",
                boundary=fallback_boundary,
                area_m2=DxfParser._calculate_polygon_area(fallback_boundary),
                height_m=3.0
            ))
            has_fallback = True

        # BUG-39 FIX: Detect actual DXF version from $ACADVER header
        # instead of hardcoding "DXF R2000". The version affects which
        # entities and features are available.
        version_detected = DxfParser._detect_dxf_version(filepath)

        b = Building(
            file_hash=file_hash,
            format_detected="DXF",
            version_detected=version_detected,
            units="METERS",
            walls=tuple(walls),
            rooms=tuple(rooms),
            openings=tuple(openings),
            has_fallback_geometry=has_fallback
        )
        return Result(value=b)

    @staticmethod
    def _parse_dxf_text(filepath: str, walls: List[Wall], rooms: List[Room]) -> None:
        """
        Simple text-based DXF parser for environments without ezdxf.
        Extracts LWPOLYLINE and LINE entities from DXF text format.

        BUG-26 FIX: Previously returned silently on read error with no logging.
        In a safety-critical system, silent failures are DANGEROUS — a corrupted
        DXF file would produce an empty building model with fallback geometry,
        and no one would know why. Now logs a warning on read failure.
        """
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            # BUG-26 FIX: Log the error instead of silently returning
            logger.warning("Failed to read DXF file for text parsing: '%s': %s", filepath, e)
            return

        # Simple DXF text parser — reads group code/value pairs
        lines = content.split("\n")
        entities = DxfParser._dxf_group_pairs(lines)

        for entity in entities:
            etype = entity.get("0", "")

            if etype == "LWPOLYLINE":
                # Check if closed (group code 70, bit 1 = closed)
                try:
                    flags = int(entity.get("70", "0"))
                except (ValueError, TypeError):
                    flags = 0
                is_closed = bool(flags & 1)

                # BUG-11 FIX: Extract vertices from multi-value group codes
                pts = DxfParser._extract_polyline_points(entity)
                if is_closed and len(pts) >= 3:
                    area = DxfParser._calculate_polygon_area(tuple(pts))
                    rooms.append(Room(
                        id=f"DXF_ROOM_TXT_{len(rooms):03d}",
                        name=f"Room {len(rooms)}",
                        boundary=tuple(pts),
                        area_m2=area,
                        height_m=3.0
                    ))

            elif etype == "LINE":
                # Extract start/end points
                try:
                    sx = float(entity.get("10", "0"))
                    sy = float(entity.get("20", "0"))
                    ex = float(entity.get("11", "0"))
                    ey = float(entity.get("21", "0"))
                    walls.append(Wall(
                        id=f"DXF_WALL_TXT_{len(walls):03d}",
                        start=Point3D(sx, sy, 0.0),
                        end=Point3D(ex, ey, 0.0),
                        height_m=3.0,
                        thickness_m=0.20
                    ))
                except (ValueError, TypeError):
                    pass

    @staticmethod
    def _dxf_group_pairs(lines: List[str]) -> List[dict]:
        """
        Parse DXF text into group code/value pair dictionaries.

        BUG-10 FIX: The original code used current[str(int_code)] = value which
        OVERWRITES previous values of the same group code. In DXF, LWPOLYLINE
        vertices appear as multiple group code 10 (X) and 20 (Y) pairs. With
        overwriting, only the LAST vertex was preserved — all others were lost.

        Now uses lists to accumulate multiple values for the same group code.
        Single-value codes (like "0" for entity type) are stored as strings.
        Multi-value codes (like "10" for X coordinates) are stored as lists.
        The _extract_polyline_points() method reads from these lists.
        """
        entities = []
        current = {}
        i = 0
        while i < len(lines) - 1:
            code = lines[i].strip()
            value = lines[i + 1].strip()
            try:
                int_code = int(code)
                str_code = str(int_code)

                if int_code == 0 and current and len(current) > 1:
                    # New entity starts — save the previous one
                    # BUG-41 FIX: Previously popped the "0" key (entity type),
                    # then tried to read it with entity.get("0", "") which always
                    # returned "". This made the text-based DXF parser COMPLETELY
                    # NON-FUNCTIONAL — it could never identify LINE or LWPOLYLINE
                    # entities. Now the entity type is preserved in the dict.
                    prev = dict(current)
                    if len(prev) > 1:
                        entities.append(prev)
                    current = {"0": value}
                elif int_code == 0:
                    # First entity marker
                    current = {"0": value}
                else:
                    # BUG-10 FIX: Accumulate multi-value group codes as lists
                    # Group codes 10, 20, 30, 11, 21, 31 are coordinate pairs
                    # that can repeat within a single entity (LWPOLYLINE vertices)
                    if str_code in current:
                        # Already have a value for this code — convert to list
                        existing = current[str_code]
                        if isinstance(existing, list):
                            existing.append(value)
                        else:
                            current[str_code] = [existing, value]
                    else:
                        current[str_code] = value
            except ValueError:
                pass
            i += 2
        # BUG-41 FIX: Don't pop the entity type key — it's needed to
        # identify what kind of entity was parsed (LINE, LWPOLYLINE, etc.)
        if current and len(current) > 1:
            entities.append(current)
        return entities

    @staticmethod
    def _extract_polyline_points(entity: dict) -> List[Point3D]:
        """
        Extract 2D points from LWPOLYLINE group codes.

        BUG-11 FIX: The original code always returned an empty list because
        it read from entity.get("_raw_coords", []) which was never populated.
        Now reads from the actual group code 10 (X) and 20 (Y) values that
        were accumulated by the fixed _dxf_group_pairs() method.

        In DXF, LWPOLYLINE vertices are specified as repeating pairs:
          Group 10 = X coordinate (repeats for each vertex)
          Group 20 = Y coordinate (repeats for each vertex)
        The values are stored as lists when multiple vertices exist.
        """
        points = []

        # Get X values (group code 10) and Y values (group code 20)
        x_raw = entity.get("10", [])
        y_raw = entity.get("20", [])

        # Normalize to lists
        if isinstance(x_raw, str):
            x_vals = [x_raw]
        elif isinstance(x_raw, list):
            x_vals = x_raw
        else:
            x_vals = []

        if isinstance(y_raw, str):
            y_vals = [y_raw]
        elif isinstance(y_raw, list):
            y_vals = y_raw
        else:
            y_vals = []

        # Must have equal number of X and Y coordinates
        count = min(len(x_vals), len(y_vals))
        for idx in range(count):
            try:
                x = float(x_vals[idx])
                y = float(y_vals[idx])
                points.append(Point3D(x, y, 0.0))
            except (ValueError, TypeError, IndexError):
                continue

        return points

    @staticmethod
    def _calculate_polygon_area(boundary: Tuple[Point3D, ...]) -> float:
        """Calculate polygon area using the Shoelace formula."""
        n = len(boundary)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += boundary[i].x * boundary[j].y
            area -= boundary[j].x * boundary[i].y
        return abs(area) / 2.0

    @staticmethod
    def _detect_dxf_version(filepath: str) -> str:
        """BUG-39 FIX: Detect DXF version from $ACADVER header variable.

        Returns the DXF version string (e.g., 'DXF R2000', 'DXF R2018')
        instead of hardcoding 'DXF R2000'. If version cannot be detected,
        returns 'DXF (unknown version)' as a safe default.
        """
        # Map of ACADVER codes to DXF version names
        version_map = {
            "AC1015": "DXF R2000",
            "AC1018": "DXF R2004",
            "AC1021": "DXF R2007",
            "AC1024": "DXF R2010",
            "AC1027": "DXF R2013",
            "AC1032": "DXF R2018",
        }
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                # Read first 2000 chars — $ACADVER is in HEADER section near start
                header = f.read(2000)
            ver_match = re.search(r"\$ACADVER\s*\n\s*1\s*\n\s*(AC\d+)", header)
            if ver_match:
                acadver = ver_match.group(1)
                return version_map.get(acadver, f"DXF {acadver}")
        except Exception:
            pass
        return "DXF (unknown version)"
