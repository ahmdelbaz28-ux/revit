"""
dwg_parser.py — FireAI DWG Parser
SAFETY-CRITICAL: Reads DWG via LibreDWG tools.

DEPENDENCY: LibreDWG tools (dxf-out) must be installed.
Installation: sudo apt install libredwg-tools

If not available, converts DWG to DXF using external tools,
then delegates to DXFParser.
"""

import subprocess
import tempfile
import os
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger("fireai.dwg_parser")


# ═══════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════

class DWGConversionError(Exception):
    """Raised when DWG → DXF conversion fails."""
    pass


# ═══════════════════════════════════════════════════════
# DATA CLASS
# ═══════════════════════════════════════════════════════

@dataclass
class DWGParseResult:
    """Result of parsing a DWG file."""
    source_file: str
    success: bool
    room_count: int = 0
    conversion_time_s: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════
# DWG PARSER
# ═══════════════════════════════════════════════════════

class DWGParser:
    """
    Parses DWG files via LibreDWG conversion.

    USAGE:
        parser = DWGParser()
        result = parser.parse("building.dwg")

        if result.success:
            print(f"Found {result.room_count} rooms")

    SAFETY NOTE:
        extract_rooms_from_chaos() sanitizes NaN/infinite coordinates from
        adversarial or corrupted input data.  Poisoned entities are silently
        skipped so that downstream NFPA analysis never receives geometrically
        invalid rooms — a safety-critical requirement per NFPA 72 §17.7.
    """

    DXF_OUT_CMD = "dxf-out"

    def __init__(self):
        """Initialize parser."""
        self._tool_checked = False
        self._tool_available = False

    def _check_tool(self) -> bool:
        """Check if dxf-out is available."""
        if self._tool_checked:
            return self._tool_available
            
        try:
            result = subprocess.run(
                [self.DXF_OUT_CMD, "--version"],
                capture_output=True,
                timeout=5
            )
            self._tool_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._tool_available = False
            
        self._tool_checked = True
        return self._tool_available

    # ───────────────────────────────────────────────────────────────
    # Chaos / adversarial input handler (safety-critical)
    # ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_coordinate(value) -> bool:
        """Return True if *value* is a finite float (not NaN, not inf)."""
        try:
            f = float(value)
            import math
            return math.isfinite(f)
        except (TypeError, ValueError):
            return False

    def extract_rooms_from_chaos(self, doc) -> list:
        """Extract rooms from a potentially-corrupted or adversarial document.

        This method is the **chaos-safe** entry point.  It iterates over
        entities in ``doc.modelspace()``, skips any entity whose coordinates
        contain NaN or ±Infinity, and returns a list of
        :class:`core.models.UniversalElement` objects with clean geometry.

        Parameters
        ----------
        doc : object
            Any object with a ``modelspace()`` method that returns an
            iterable of entity-like objects.  Each entity must have a
            ``dxftype()`` method and a ``dxf`` attribute with start/end
            coordinates for LINE entities, or appropriate attributes for
            other entity types.

        Returns
        -------
        list[UniversalElement]
            Rooms extracted from valid (non-poisoned) entities only.
            Entities with NaN / Inf coordinates are silently dropped so
            that downstream NFPA analysis never receives invalid geometry.

        Safety rationale
        ----------------
        A NaN coordinate in a room polygon would silently propagate
        through Shapely operations, producing zero-area coverage results
        that could allow a building to be signed off as "protected" when
        it is not.  Rejecting poisoned data at the parser boundary is
        the conservative (safer) choice per Life-Safety Rule 5.
        """
        # Lazy import — use project-root resolution to avoid
        # fireai/core/ shadowing top-level core/ when setuptools
        # adds fireai/ to sys.path.
        import sys as _sys
        import importlib
        _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if _project_root not in _sys.path:
            _sys.path.insert(0, _project_root)
        # Also remove fireai/ if it shadows the project root
        _fireai_path = os.path.join(_project_root, 'fireai')
        while _fireai_path in _sys.path:
            _sys.path.remove(_fireai_path)
        # Clear cached 'core' module if it resolved to fireai/core/
        if 'core' in _sys.modules:
            _mod = _sys.modules['core']
            if hasattr(_mod, '__file__') and _mod.__file__ and '/fireai/core/' in _mod.__file__:
                for _k in [k for k in list(_sys.modules.keys()) if k == 'core' or k.startswith('core.')]:
                    del _sys.modules[_k]

        from core.models import UniversalElement, Geometry, Point3D, ElementType

        rooms: list = []

        try:
            modelspace = doc.modelspace()
        except Exception:
            logger.warning("extract_rooms_from_chaos: doc.modelspace() failed — returning empty list")
            return rooms

        for entity in modelspace:
            try:
                etype = entity.dxftype()
            except Exception:
                continue

            if etype == 'LINE':
                # ── Validate start / end coordinates ──
                try:
                    sx = float(entity.dxf.start.x)
                    sy = float(entity.dxf.start.y)
                    ex = float(entity.dxf.end.x)
                    ey = float(entity.dxf.end.y)
                except (AttributeError, TypeError, ValueError):
                    logger.debug("extract_rooms_from_chaos: LINE entity missing coords — skipped")
                    continue

                if not (self._is_valid_coordinate(sx) and self._is_valid_coordinate(sy)
                        and self._is_valid_coordinate(ex) and self._is_valid_coordinate(ey)):
                    logger.warning(
                        "extract_rooms_from_chaos: LINE with NaN/Inf coords "
                        "(%.4g,%.4g)→(%.4g,%.4g) — poisoned entity dropped",
                        sx, sy, ex, ey
                    )
                    continue

                # A single line does not form a closed room — skip it.
                # Only closed polylines / polygons become rooms.
                continue

            elif etype in ('LWPOLYLINE', 'POLYLINE'):
                # ── Validate polyline vertices ──
                try:
                    vertices = []
                    # LWPOLYLINE: entity.get_points() or iterate
                    if hasattr(entity, 'get_points'):
                        raw_pts = entity.get_points()
                    elif hasattr(entity, '__iter__'):
                        raw_pts = list(entity)
                    else:
                        continue

                    for pt in raw_pts:
                        if hasattr(pt, 'dxf'):
                            vx, vy = float(pt.dxf.location.x), float(pt.dxf.location.y)
                        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            vx, vy = float(pt[0]), float(pt[1])
                        else:
                            continue

                        if not (self._is_valid_coordinate(vx) and self._is_valid_coordinate(vy)):
                            logger.warning(
                                "extract_rooms_from_chaos: POLYLINE vertex NaN/Inf — entity dropped"
                            )
                            vertices = []  # reject entire entity
                            break
                        vertices.append((vx, vy))

                    if len(vertices) >= 3:
                        points_3d = [Point3D(x=vx, y=vy, z=0.0) for vx, vy in vertices]
                        geom = Geometry(points=points_3d, polyline_closed=True)
                        room = UniversalElement(geometry=geom)
                        rooms.append(room)

                except Exception as exc:
                    logger.warning("extract_rooms_from_chaos: POLYLINE parse error: %s — skipped", exc)
                    continue

            # Other entity types (CIRCLE, ARC, TEXT, etc.) are not rooms.
            # They are silently ignored.

        return rooms

    def parse(self, dwg_path: str) -> DWGParseResult:
        """
        Parse DWG file to rooms.
        
        Args:
            dwg_path: Path to .dwg file
            
        Returns:
            DWGParseResult with room count
        """
        import time
        start = time.monotonic()
        
        result = DWGParseResult(source_file=dwg_path, success=False)
        
        # Step 0: Verify file exists
        if not Path(dwg_path).exists():
            result.errors.append(f"File not found: {dwg_path}")
            return result
            
        # Step 1: Check LibreDWG
        if not self._check_tool():
            result.errors.append(
                "LibreDWG not installed. Install with: sudo apt install libredwg-tools"
            )
            return result
            
        # Step 2: Convert DWG → DXF
        try:
            dxf_path = self._convert_to_dxf(dwg_path)
        except DWGConversionError as e:
            result.errors.append(str(e))
            return result
            
        # Step 3: Parse DXF
        try:
            from parsers.dxf_parser import DXFParser
            parser = DXFParser(min_area=2.0)
            dxf_result = parser.parse(dxf_path)
            
            result.room_count = dxf_result.room_count
            result.warnings = dxf_result.warnings
            result.success = dxf_result.room_count > 0
            result.errors = dxf_result.errors
            
        finally:
            # Clean up temp file
            if dxf_path != dwg_path:
                try:
                    os.unlink(dxf_path)
                except:
                    pass
                    
        result.conversion_time_s = round(time.monotonic() - start, 3)
        return result

    def _convert_to_dxf(self, dwg_path: str) -> str:
        """Convert DWG to DXF using dxf-out."""
        # Create temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".dxf", prefix="fireai_dwg_")
        os.close(temp_fd)
        
        cmd = [self.DXF_OUT_CMD, "--file", dwg_path, "--output", temp_path]
        
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if proc.returncode != 0:
                error = proc.stderr.decode() or proc.stdout.decode()
                raise DWGConversionError(f"dxf-out failed: {error}")
                
            if not Path(temp_path).exists() or Path(temp_path).stat().st_size == 0:
                raise DWGConversionError("Empty DXF output")
                
            return temp_path
            
        except subprocess.TimeoutExpired:
            raise DWGConversionError("Conversion timeout")


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════

def parse_dwg(dwg_path: str) -> DWGParseResult:
    """Quick parse DWG file."""
    parser = DWGParser()
    return parser.parse(dwg_path)