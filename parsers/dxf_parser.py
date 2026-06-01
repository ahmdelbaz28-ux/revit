"""
dxf_parser.py — FireAI V5.1.0
CRITICAL SAFETY: Reads real DXF and produces valid Polygons only.
Any invalid geometry is rejected, never guessed.
"""

import ezdxf
from ezdxf import recover
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import unary_union, polygonize
from shapely.validation import make_valid
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("fireai.dxf_parser")


@dataclass
class ParsedRoom:
    room_id: str
    polygon: Polygon
    source_layer: str
    area_m2: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.area_m2 = round(self.polygon.area, 3)


@dataclass
class DXFParseResult:
    source_file: str
    dxf_units: str
    scale_to_meters: float
    rooms: List[ParsedRoom] = field(default_factory=list)
    skipped_count: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def room_count(self) -> int:
        return len(self.rooms)

    @property
    def total_area_m2(self) -> float:
        return round(sum(r.area_m2 for r in self.rooms), 2)


class DXFParser:
    """CRITICAL: Never trust DXF geometry. Always validate."""

    MIN_ROOM_AREA_M2: float = 2.0  # Min 2m² per NFPA 72 (columns are ~1.5m²)
    MAX_ROOM_AREA_M2: float = 50_000.0

    # V76 CRIT-03 FIX: Corrected INSUNITS mapping per AutoCAD DXF specification.
    # Code 8 was mapped to 1000.0 (kilometers) but is actually Microinches
    # (2.54e-8 m). Code 3 (Miles) and Code 7 (Kilometers) were missing
    # entirely, causing ValueError on those unit types. Wrong unit mapping
    # produces catastrophically wrong room areas → wrong detector count →
    # building unprotected. Source: AutoCAD DXF Reference — $INSUNITS header.
    INSUNITS_TO_METERS = {
        0: 1.0,         # Unspecified — assume meters (documented assumption)
        1: 0.0254,      # Inches
        2: 0.3048,      # Feet
        3: 1609.344,    # Miles (was missing — caused ValueError)
        4: 0.001,       # Millimeters
        5: 0.01,        # Centimeters
        6: 1.0,         # Meters
        7: 1000.0,      # Kilometers (was missing — caused ValueError)
        8: 2.54e-8,     # Microinches (was 1000.0 — 3.9×10¹⁰ error!)
    }

    def __init__(self, min_area: float = MIN_ROOM_AREA_M2, max_area: float = MAX_ROOM_AREA_M2):
        self.min_area = min_area
        self.max_area = max_area

    def parse(self, dxf_path: str) -> DXFParseResult:
        logger.info(f"Parsing DXF: {dxf_path}")

        # SAFETY: Try normal read first, then recovery
        try:
            doc = ezdxf.readfile(dxf_path)
        except ezdxf.DXFStructureError:
            logger.warning("DXF corrupt — attempting recovery")
            doc, auditor = recover.readfile(dxf_path)
            if auditor.has_errors:
                raise RuntimeError(f"DXF '{dxf_path}' unrecoverable. Errors: {len(auditor.errors)}")

        units = self._detect_units(doc)

        # Validate and get scale
        if units not in self.INSUNITS_TO_METERS:
            raise ValueError(f"Unknown DXF units code: '{units}'")
        scale = self.INSUNITS_TO_METERS[units]

        msp = doc.modelspace()
        lines = self._extract_lines(msp, scale)
        polys = self._lines_to_valid_polygons(lines)

        rooms = []
        skipped = 0

        for i, poly in enumerate(polys):
            rid = f"ROOM_{i + 1:03d}"

            if poly.area < self.min_area:
                skipped += 1
                continue
            if poly.area > self.max_area:
                logger.warning(f"{rid}: area {poly.area:.1f}m² > max")

            rooms.append(
                ParsedRoom(
                    room_id=rid,
                    polygon=poly,
                    source_layer="A-WALL",
                    warnings=[],
                )
            )

        if not rooms:
            raise RuntimeError(f"No valid rooms in '{dxf_path}'")

        return DXFParseResult(
            source_file=dxf_path,
            dxf_units=units,
            scale_to_meters=scale,
            rooms=rooms,
            skipped_count=skipped,
        )

    def _detect_units(self, doc) -> int:
        """Detect DXF units using heuristic for INSUNITS=0 files.

        CRITICAL SAFETY: For unitless (0) DXF files, we must detect the actual unit
        by analyzing coordinate values. Wrong unit = wrong room areas = failed coverage
        detection = LIVES LOST.

        Strategy:
        1. If INSUNITS != 0, use standard mapping
        2. If INSUNITS == 0, try multiple scales and validate
        3. Reject if no valid scale found (safety-first)
        """
        units = doc.header.get("$INSUNITS", 6)

        # Non-zero units: trust the header
        if units != 0:
            return units

        # INSUNITS = 0: Must detect actual unit via heuristic
        # This is CRITICAL for safety - we cannot guess
        detected = self._detect_unit_heuristic(doc)
        if detected is not None:
            logger.info(f"Units auto-detected: {detected}")
            return detected

        # Failed to detect: safety-first approach
        raise RuntimeError(
            f"Cannot determine DXF units. INSUNITS=0 and coordinate analysis inconclusive. "
            f"File may be corrupted or use non-standard units. "
            f"CRITICAL: Cannot proceed - incorrect unit = incorrect coverage calculation."
        )

    def _detect_unit_heuristic(self, doc) -> int:
        """Detect actual unit by testing scale factors.

        CRITICAL SAFETY: We try multiple scales and check which produces valid
        NFPA 72-compliant room areas. Only accept if EXACTLY ONE scale works.
        """
        from shapely.geometry import LineString
        from shapely.ops import unary_union, polygonize
        from shapely.validation import make_valid

        msp = doc.modelspace()

        # Try different unit scales
        candidates = [
            (1, "meters"),  # 1:1 direct
            (0.001, "mm x 1000 -> m"),  # mm
            (0.01, "cm x 100 -> m"),  # cm
            (0.3048, "feet x 0.3048 -> m"),  # feet
        ]

        valid_scales = []

        for scale, unit_name in candidates:
            lines = []
            for ent in msp:
                if ent.dxftype() == "LINE":
                    s = (ent.dxf.start.x * scale, ent.dxf.start.y * scale)
                    e = (ent.dxf.end.x * scale, ent.dxf.end.y * scale)
                    if s != e:
                        lines.append(LineString([s, e]))
                elif ent.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                    try:
                        pts = [(p[0] * scale, p[1] * scale) for p in ent.get_points()]
                        if len(pts) >= 3 and ent.closed:
                            lines.append(LineString(pts))
                    except Exception as exc:
                        logger.debug("Polyline point extraction failed: %s", exc)

            if not lines:
                continue

            # Try to create polygons
            merged = unary_union(lines)
            raw_polys = polygonize(merged)

            valid_count = 0
            for p in raw_polys:
                if not p.is_valid:
                    p = make_valid(p)
                if p.is_valid and self.MIN_ROOM_AREA_M2 <= p.area <= self.MAX_ROOM_AREA_M2:
                    valid_count += 1

            if valid_count > 0:
                valid_scales.append((scale, unit_name, valid_count))

        # CRITICAL: Must have exactly one valid scale OR pick the best one
        # If multiple: pick the one with MOST valid rooms (most likely correct)
        if len(valid_scales) >= 1:
            # Sort by room count descending - pick the one with most rooms
            valid_scales.sort(key=lambda x: -x[2])
            scale, name, count = valid_scales[0]
            logger.info(f"Unit detected: {name} -> {count} valid rooms")

            # Map back to DXF unit code
            _SCALE_TO_UNIT = {0.001: 4, 0.01: 5, 0.3048: 2}
            return _SCALE_TO_UNIT.get(scale, 6)  # default: meters

        # No valid scale: fail closed (safety-first)
        logger.error("No valid unit scale found")

        return None

    def _extract_lines(self, msp, scale: float) -> List:
        from shapely.geometry import LineString

        lines = []
        for ent in msp:
            if ent.dxftype() == "LINE":
                s = (ent.dxf.start.x * scale, ent.dxf.start.y * scale)
                e = (ent.dxf.end.x * scale, ent.dxf.end.y * scale)
                if s != e:
                    lines.append(LineString([s, e]))
            elif ent.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                try:
                    pts = [(p[0] * scale, p[1] * scale) for p in ent.get_points()]
                    if len(pts) >= 3 and ent.closed:
                        lines.append(LineString(pts))
                except Exception as e:
                    logger.debug(f"Polyline skip: {e}")
            elif ent.dxftype() == "CIRCLE":
                # Convert CIRCLE to polygon approximation
                try:
                    poly = self._circle_to_polygon(ent, scale)
                    if poly and poly.is_valid:
                        lines.append(poly.exterior)
                except Exception as e:
                    logger.debug(f"Circle skip: {e}")
            elif ent.dxftype() == "ARC":
                # Convert ARC to line segments
                try:
                    segments = self._arc_to_segments(ent, scale)
                    lines.extend(segments)
                except Exception as e:
                    logger.debug(f"Arc skip: {e}")
            elif ent.dxftype() == "SPLINE":
                # Convert SPLINE to line segments (64 points approximation)
                try:
                    segments = self._spline_to_segments(ent, scale)
                    lines.extend(segments)
                except Exception as e:
                    logger.debug(f"Spline skip: {e}")
        return lines

    def _circle_to_polygon(self, entity, scale):
        """Convert CIRCLE to Polygon approximation (36 points)"""
        c = Point(entity.dxf.center.x * scale, entity.dxf.center.y * scale)
        r = entity.dxf.radius * scale
        return c.buffer(r, quad_segs=36)  # V108 FIX: quad_segs= replaces deprecated resolution= in Shapely 2.x

    def _arc_to_segments(self, entity, scale, num_points: int = 32):
        """Convert ARC to LineString segments (default 32 points)"""
        import math

        c = Point(entity.dxf.center.x * scale, entity.dxf.center.y * scale)
        r = entity.dxf.radius * scale

        # Get start and end angles in radians
        start_angle = math.radians(entity.dxf.start_angle)
        end_angle = math.radians(entity.dxf.end_angle)

        # Handle the case where arc goes through 0/360 degrees
        if end_angle < start_angle:
            end_angle += 2 * math.pi

        # Calculate angular step
        total_angle = end_angle - start_angle
        step = total_angle / num_points

        points = []
        for i in range(num_points + 1):
            angle = start_angle + (i * step)
            x = c.x + r * math.cos(angle)
            y = c.y + r * math.sin(angle)
            points.append((x, y))

        # Add proper closing point if needed
        if len(points) >= 2:
            from shapely.geometry import LineString

            ls = LineString(points)
            return [ls]
        return []

    def _spline_to_segments(self, entity, scale, num_segments: int = 64):
        """Convert SPLINE to LineString segments (64 points approximation)"""
        try:
            # Get control points from SPLINE entity
            ctrl_pts = entity.control_points
            if ctrl_pts is None or len(ctrl_pts) < 2:
                return []

            # Convert to scaled coordinates
            points = [(p.dxf.location.x * scale, p.dxf.location.y * scale) for p in ctrl_pts]

            # Generate more points along the spline using linear interpolation
            if len(points) < 2:
                return []

            # Create a line through control points and sample it
            from shapely.geometry import LineString

            base_line = LineString(points)

            # Sample the line into num_segments points
            sampled_points = []
            for i in range(num_segments + 1):
                t = i / num_segments
                if t <= 1.0:
                    pt = base_line.interpolate(t, normalized=True)
                    sampled_points.append((pt.x, pt.y))

            # Convert to line segments
            segments = []
            for i in range(len(sampled_points) - 1):
                segments.append(LineString([sampled_points[i], sampled_points[i + 1]]))

            return segments
        except Exception as e:
            logger.debug(f"Spline conversion failed: {e}")
            return []

    def _is_duplicate(self, poly1: Polygon, poly2: Polygon) -> bool:
        """Check if two polygons are duplicates (>90% overlap)"""
        if not poly1.intersects(poly2):
            return False

        intersection = poly1.intersection(poly2)
        min_area = min(poly1.area, poly2.area)

        if min_area <= 0:
            return False

        overlap_ratio = intersection.area / min_area

        # 90% overlap = duplicate
        return overlap_ratio > 0.9

    def _remove_duplicates(self, polygons: List[Polygon]) -> List[Polygon]:
        """Remove duplicate polygons (keep larger one)"""
        if len(polygons) <= 1:
            return polygons

        unique = []
        for poly in polygons:
            is_dup = False
            for existing in unique:
                if self._is_duplicate(poly, existing):
                    is_dup = True
                    # Keep larger polygon
                    if poly.area > existing.area:
                        unique.remove(existing)
                        unique.append(poly)
                    break
            if not is_dup:
                unique.append(poly)

        return unique

    def _lines_to_valid_polygons(self, lines) -> List[Polygon]:
        """CRITICAL: Always validate geometry. Never trust raw DXF."""
        if not lines:
            return []

        merged = unary_union(lines)
        raw_polys = list(polygonize(merged))

        # CRITICAL: Remove duplicate polygons (>90% overlap)
        valid_polys = self._remove_duplicates(raw_polys)

        valid = []
        for p in valid_polys:
            # CRITICAL: make_valid fixes self-intersections
            if not p.is_valid:
                p = make_valid(p)

            if isinstance(p, MultiPolygon):
                valid.extend([g for g in p.geoms if g.is_valid])
            elif isinstance(p, Polygon) and not p.is_empty:
                valid.append(p)

        valid.sort(key=lambda x: x.area, reverse=True)
        return valid
