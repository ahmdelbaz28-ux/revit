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

    INSUNITS_TO_METERS = {
        0: 1.0, 1: 0.0254, 2: 0.3048, 4: 0.001,
        5: 0.01, 6: 1.0, 8: 1000.0,
    }

    def __init__(self, min_area: float = MIN_ROOM_AREA_M2,
                 max_area: float = MAX_ROOM_AREA_M2):
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
                raise RuntimeError(
                    f"DXF '{dxf_path}' unrecoverable. "
                    f"Errors: {len(auditor.errors)}"
                )

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
            rid = f"ROOM_{i+1:03d}"

            if poly.area < self.min_area:
                skipped += 1
                continue
            if poly.area > self.max_area:
                logger.warning(f"{rid}: area {poly.area:.1f}m² > max")

            rooms.append(ParsedRoom(
                room_id=rid,
                polygon=poly,
                source_layer="A-WALL",
                warnings=[],
            ))

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
        """Detect DXF units code (not name)"""
        return doc.header.get("$INSUNITS", 6)  # Default to Meters (6)

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
                    pts = [(p[0]*scale, p[1]*scale) for p in ent.get_points()]
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
        return lines

    def _circle_to_polygon(self, entity, scale):
        """Convert CIRCLE to Polygon approximation (36 points)"""
        c = Point(entity.dxf.center.x * scale, entity.dxf.center.y * scale)
        r = entity.dxf.radius * scale
        return c.buffer(r, resolution=36)  # 36 points

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