"""
dwg_parser.py — FireAI DWG Parser
SAFETY-CRITICAL: Reads DWG via LibreDWG tools.

DEPENDENCY: LibreDWG tools (dxf-out) must be installed.
Installation: sudo apt install libredwg-tools

If not available, converts DWG to DXF using external tools,
then delegates to DXFParser.

V122 SECURITY HARDENING (Finding #5):
    Path inputs are now validated by parsers._path_security before
    reaching subprocess. This closes:
      - Argument injection (paths starting with '-')
      - Path traversal (../, /etc/, etc.)
      - Null-byte truncation
      - Files outside FIREAI_ALLOWED_UPLOAD_DIRS
      - DoS via oversized files (configurable cap)
    Same security contract as parsers/ddc_adapter.py.
"""

import logging
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from parsers._path_security import (
    UnsafePathError,
    validate_file_size,
    validate_input_path,
)

logger = logging.getLogger("fireai.dwg_parser")

# V122: Allowed extensions for DWG parser entry point. The parser also
# supports DXF as a fast-path (see parse() — skips LibreDWG when input
# is already DXF).
_DWG_ALLOWED_EXTENSIONS = frozenset({".dwg", ".dxf"})

# V122: Hard cap on input file size. DWG/DXF files larger than this are
# either malformed, malicious, or beyond the engineering scope of this
# system (a fire alarm floor plan does not need 500 MB of geometry).
# Configurable via env var for legitimate edge cases.
_DWG_MAX_FILE_SIZE_BYTES = int(
    os.getenv("FIREAI_DWG_MAX_FILE_SIZE_BYTES", str(100 * 1024 * 1024))  # 100 MB
)


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
            result = subprocess.run(  # noqa: S603 — command from class constant, not user input
                [self.DXF_OUT_CMD, "--version"], capture_output=True, timeout=5
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

    @staticmethod
    def _assemble_closed_polygons(lines: list, tolerance: float = 0.01) -> list:
        """
        Chain LINE segments into closed polygons by matching endpoints.

        This solves the classic DWG/DXF problem where walls are drawn as
        separate LINE entities instead of closed polylines.  The algorithm
        uses a spatial grid index for O(n) expected-time endpoint lookup,
        then chains segments greedily and returns only closed loops.

        Safety rationale
        ----------------
        Missing a room because its walls were drawn as LINEs (not polylines)
        means zero fire protection for that space — potentially fatal per
        Life-Safety Rule 5 (conservative interpretation).

        Performance
        -----------
        V29 optimisation: replaced O(n²) brute-force scan with a grid-based
        spatial index.  Each endpoint is binned into a grid cell of size
        *tolerance*.  To find a neighbour within *tolerance* we only check
        the 9 surrounding cells (3×3 Moore neighbourhood), giving O(1)
        expected lookup and O(n) total expected runtime for well-separated
        buildings.

        Parameters
        ----------
        lines : list of ((sx, sy), (ex, ey))
            Validated line segments with finite coordinates.
        tolerance : float
            Maximum distance (metres) to consider two endpoints coincident.

        Returns
        -------
        list of list of (x, y)
            Each inner list is a closed polygon's vertex sequence
            (first vertex == last vertex NOT duplicated; closing
            is implied by polyline_closed=True downstream).

        """
        if not lines:
            return []

        tol_sq = tolerance * tolerance

        # ── Phase 1: Build spatial grid index ──
        # Grid cell size = tolerance.  Each cell stores the line indices
        # whose start or end point falls inside that cell.
        cell_size = tolerance
        # We index BOTH endpoints of every line so we can find lines
        # whose start or end is near a query point.
        # grid_start[(cx,cy)] = set of line indices whose start is in cell (cx,cy)
        # grid_end[(cx,cy)]   = set of line indices whose end is in cell (cx,cy)
        grid_start: dict = {}
        grid_end: dict = {}

        for idx, (start, end) in enumerate(lines):
            sx, sy = start
            ex, ey = end
            cs = (math.floor(sx / cell_size), math.floor(sy / cell_size))
            ce = (math.floor(ex / cell_size), math.floor(ey / cell_size))
            grid_start.setdefault(cs, set()).add(idx)
            grid_end.setdefault(ce, set()).add(idx)

        consumed = set()  # indices of lines already used
        closed_polygons = []

        def _find_neighbours(px: float, py: float) -> list:
            """Return line indices whose start or end is within tolerance of (px,py)."""
            cx = math.floor(px / cell_size)
            cy = math.floor(py / cell_size)
            candidates = set()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cell = (cx + dx, cy + dy)
                    # Lines whose START is near
                    for i in grid_start.get(cell, ()):
                        if i not in consumed:
                            candidates.add(i)
                    # Lines whose END is near
                    for i in grid_end.get(cell, ()):
                        if i not in consumed:
                            candidates.add(i)
            return list(candidates)

        # ── Phase 2: Chain lines into polygons ──
        for seed_idx in range(len(lines)):
            if seed_idx in consumed:
                continue

            start, end = lines[seed_idx]
            chain_vertices = [start, end]
            consumed.add(seed_idx)

            # Extend chain from both ends until no more connections
            changed = True
            while changed:
                changed = False
                head = chain_vertices[0]
                tail = chain_vertices[-1]

                # Try to extend from tail first
                for idx in _find_neighbours(tail[0], tail[1]):
                    if idx in consumed:
                        continue
                    ls, le = lines[idx]

                    d_ts = (ls[0] - tail[0]) ** 2 + (ls[1] - tail[1]) ** 2
                    d_te = (le[0] - tail[0]) ** 2 + (le[1] - tail[1]) ** 2

                    if d_ts <= tol_sq:
                        chain_vertices.append(le)
                        consumed.add(idx)
                        changed = True
                        break
                    if d_te <= tol_sq:
                        chain_vertices.append(ls)
                        consumed.add(idx)
                        changed = True
                        break

                if changed:
                    continue

                # Try to extend from head
                for idx in _find_neighbours(head[0], head[1]):
                    if idx in consumed:
                        continue
                    ls, le = lines[idx]

                    d_hs = (ls[0] - head[0]) ** 2 + (ls[1] - head[1]) ** 2
                    d_he = (le[0] - head[0]) ** 2 + (le[1] - head[1]) ** 2

                    if d_hs <= tol_sq:
                        chain_vertices.insert(0, le)
                        consumed.add(idx)
                        changed = True
                        break
                    if d_he <= tol_sq:
                        chain_vertices.insert(0, ls)
                        consumed.add(idx)
                        changed = True
                        break

            # Check if chain is closed (head ≈ tail)
            if len(chain_vertices) >= 3:
                head = chain_vertices[0]
                tail = chain_vertices[-1]
                close_dist_sq = (head[0] - tail[0]) ** 2 + (head[1] - tail[1]) ** 2
                if close_dist_sq <= tol_sq:
                    closed_polygons.append(chain_vertices[:-1])

        return closed_polygons

    def extract_rooms_from_chaos(self, doc) -> list:
        """
        Extract rooms from a potentially-corrupted or adversarial document.

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
        # V82 FIX: core.models now exists at project root — no sys.path
        # manipulation needed. The old code hacked sys.path to work around
        # the missing core/models.py, which was fragile and unsafe.
        from core.models import Geometry, Point3D, UniversalElement

        rooms: list = []
        valid_lines: list = []  # Collect LINE segments for polygon assembly

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

            if etype == "LINE":
                # ── Validate start / end coordinates ──
                try:
                    sx = float(entity.dxf.start.x)
                    sy = float(entity.dxf.start.y)
                    ex = float(entity.dxf.end.x)
                    ey = float(entity.dxf.end.y)
                except (AttributeError, TypeError, ValueError):
                    logger.debug("extract_rooms_from_chaos: LINE entity missing coords — skipped")
                    continue

                if not (
                    self._is_valid_coordinate(sx)
                    and self._is_valid_coordinate(sy)
                    and self._is_valid_coordinate(ex)
                    and self._is_valid_coordinate(ey)
                ):
                    logger.warning(
                        "extract_rooms_from_chaos: LINE with NaN/Inf coords "
                        "(%.4g,%.4g)→(%.4g,%.4g) — poisoned entity dropped",
                        sx,
                        sy,
                        ex,
                        ey,
                    )
                    continue

                # Collect valid line segments for later polygon assembly.
                # Individual LINE entities can form closed rooms when their
                # endpoints chain together (common in DWG/DXF files where
                # walls are drawn as separate LINE entities, not polylines).
                valid_lines.append(((sx, sy), (ex, ey)))

            elif etype in ("LWPOLYLINE", "POLYLINE"):
                # ── Validate polyline vertices ──
                try:
                    vertices = []
                    # LWPOLYLINE: entity.get_points() or iterate
                    if hasattr(entity, "get_points"):
                        raw_pts = entity.get_points()
                    elif hasattr(entity, "__iter__"):
                        raw_pts = list(entity)
                    else:
                        continue

                    for pt in raw_pts:
                        if hasattr(pt, "dxf"):
                            vx, vy = float(pt.dxf.location.x), float(pt.dxf.location.y)
                        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            vx, vy = float(pt[0]), float(pt[1])
                        else:
                            continue

                        if not (self._is_valid_coordinate(vx) and self._is_valid_coordinate(vy)):
                            logger.warning("extract_rooms_from_chaos: POLYLINE vertex NaN/Inf — entity dropped")
                            vertices = []  # reject entire entity
                            break
                        vertices.append((vx, vy))

                    if len(vertices) >= 3:
                        points_3d = [Point3D(x=vx, y=vy, z=0.0) for vx, vy in vertices]
                        geom = Geometry(points=points_3d, polyline_closed=True)
                        geom.calculate_area()  # Must compute for downstream NFPA analysis
                        room = UniversalElement(geometry=geom)
                        rooms.append(room)

                except Exception as exc:
                    logger.warning("extract_rooms_from_chaos: POLYLINE parse error: %s — skipped", exc)
                    continue

            # Other entity types (CIRCLE, ARC, TEXT, etc.) are not rooms.
            # They are silently ignored.

        # ── Assemble closed polygons from LINE segments ──
        # In many DWG/DXF files, walls are drawn as separate LINE entities
        # rather than closed polylines.  We must chain their endpoints to
        # discover rooms.  This is safety-critical: missing a room means
        # zero fire protection for that space.
        if valid_lines:
            closed_chains = self._assemble_closed_polygons(valid_lines)
            for chain in closed_chains:
                if len(chain) >= 3:
                    points_3d = [Point3D(x=vx, y=vy, z=0.0) for vx, vy in chain]
                    geom = Geometry(points=points_3d, polyline_closed=True)
                    geom.calculate_area()  # Must compute for downstream NFPA analysis
                    room = UniversalElement(geometry=geom)
                    rooms.append(room)

        return rooms

    def parse(self, dwg_path: str) -> DWGParseResult:
        """
        Parse DWG or DXF file to rooms with enhanced security.

        Args:
            dwg_path: Path to .dwg or .dxf file. MUST be under one of
                the directories listed in FIREAI_ALLOWED_UPLOAD_DIRS
                (defaults: /tmp, /var/tmp, /var/fireai/uploads) and MUST
                have a .dwg or .dxf extension.

        Returns:
            DWGParseResult with room count. On security/validation
            failure, returns a result with success=False and the
            specific error in result.errors.

        Raises:
            (no longer raises directly — see Returns)
        """
        import time

        start = time.monotonic()
        result = DWGParseResult(source_file=dwg_path, success=False)

        # V122 SECURITY: Validate path BEFORE any file/subprocess access.
        # This catches argument injection, path traversal, null bytes,
        # bad extensions, and paths outside FIREAI_ALLOWED_UPLOAD_DIRS.
        try:
            safe_path = validate_input_path(
                dwg_path,
                allowed_extensions=_DWG_ALLOWED_EXTENSIONS,
                parser_name="DWGParser",
            )
            # V122 SECURITY: Also validate file size (DoS protection)
            validate_file_size(
                safe_path,
                max_size_bytes=_DWG_MAX_FILE_SIZE_BYTES,
                parser_name="DWGParser",
            )
        except FileNotFoundError as e:
            result.errors.append(str(e))
            return result
        except UnsafePathError as e:
            result.errors.append(f"SECURITY: {e}")
            logger.warning("DWGParser rejected unsafe path: %s", e)
            return result

        # Use the RESOLVED (canonical) path for all subsequent operations.
        # This prevents TOCTOU between validation and subprocess call:
        # even if the original `dwg_path` symlink changes after our check,
        # we hand the subprocess the resolved target instead.
        dwg_path = str(safe_path.resolve())

        # V46 FIX: If file is already DXF, skip LibreDWG conversion and
        # parse directly with ezdxf. This handles the common case where
        # tests create DXF files and pass them to DWGParser.
        if dwg_path.lower().endswith(".dxf"):
            return self._parse_dxf_directly(dwg_path, start)

        # Step 1: Check LibreDWG
        if not self._check_tool():
            result.errors.append("LibreDWG not installed. Install with: sudo apt install libredwg-tools")
            return result

        # Step 2: Convert DWG → DXF
        try:
            dxf_path = self._convert_to_dxf(dwg_path)
        except DWGConversionError as e:
            result.errors.append(str(e))
            return result

        # Step 3: Parse DXF
        try:
            return self._parse_dxf_directly(dxf_path, start)
        finally:
            # Clean up temp file
            if dxf_path != dwg_path:
                try:
                    os.unlink(dxf_path)
                except Exception as exc:
                    logger.debug("Temp file cleanup failed: %s", exc)

    def _parse_dxf_directly(self, dxf_path: str, start_time: Optional[float] = None) -> DWGParseResult:
        """
        Parse DXF file directly using ezdxf without LibreDWG conversion.

        V46: Extracted from parse() to support both DWG→DXF pipeline and
        direct DXF input. Also provides extract_rooms_from_chaos() for
        adversarial/chaotic input handling.
        """
        import time

        if start_time is None:
            start_time = time.monotonic()

        result = DWGParseResult(source_file=dxf_path, success=False)

        try:
            import ezdxf

            doc = ezdxf.readfile(dxf_path)

            # Use chaos-safe extractor for robust room extraction
            rooms = self.extract_rooms_from_chaos(doc)

            result.room_count = len(rooms)
            result.success = len(rooms) > 0
        except Exception as e:
            result.errors.append(f"DXF parse error: {e}")

        if start_time is not None:
            result.conversion_time_s = round(time.monotonic() - start_time, 3)
        return result

    # V46: Backward compatibility alias — some tests use parse_dwg()
    # instead of parse(). Returns a list of UniversalElement objects
    # (from extract_rooms_from_chaos) for backward compatibility with
    # tests that expect list output.
    #
    # V122 SECURITY: parse_dwg() now applies the same path validation
    # as parse() before calling ezdxf.readfile. ezdxf is robust against
    # malformed DXF content, but the path-level checks (extension,
    # allowed dirs, no null bytes, no leading dash) are still required.
    def parse_dwg(self, dwg_path: str) -> list:
        """
        Parse DWG/DXF file and return list of room elements.
        Backward compatibility alias — returns list, not DWGParseResult.

        Raises:
            UnsafePathError: if the input path fails security validation
            FileNotFoundError: if the file does not exist

        """
        # V122 SECURITY: validation happens BEFORE the ezdxf import so
        # that a malicious path is rejected even on systems without
        # ezdxf installed. Order matters — validation is the first line
        # of defense and must not be gated on optional dependencies.
        safe_path = validate_input_path(
            dwg_path,
            allowed_extensions=_DWG_ALLOWED_EXTENSIONS,
            parser_name="DWGParser.parse_dwg",
        )
        validate_file_size(
            safe_path,
            max_size_bytes=_DWG_MAX_FILE_SIZE_BYTES,
            parser_name="DWGParser.parse_dwg",
        )

        import ezdxf
        doc = ezdxf.readfile(str(safe_path))
        return self.extract_rooms_from_chaos(doc)

    def _convert_to_dxf(self, dwg_path: str) -> str:
        """
        Convert DWG to DXF using dxf-out with strict path validation.

        SECURITY:
            This method enforces multiple layers of security:
            1. Path validation at the entry point via validate_input_path()
            2. Additional checks for path injection patterns
            3. Secure tempfile creation
            4. Explicit argument separation to prevent command injection
        """
        # V122 SECURITY: Validate path at the entry point
        # This ensures even if a future caller bypasses the class's public methods,
        # we still validate the path before any subprocess operations
        try:
            safe_path = validate_input_path(
                dwg_path,
                allowed_extensions=_DWG_ALLOWED_EXTENSIONS,
                parser_name="DWGParser._convert_to_dxf",
            )
            # Use the validated/sanitized path
            dwg_path = str(safe_path.resolve())
        except UnsafePathError as e:
            raise DWGConversionError(
                f"SECURITY: Invalid path in DWG conversion: {e}"
            ) from e

        # V122 SECURITY: Additional checks for path injection patterns
        if dwg_path.startswith("-") or "\x00" in dwg_path:
            raise DWGConversionError(
                f"SECURITY: Refused to execute dxf-out with unsafe path: {dwg_path!r}"
            )

        # Create secure temporary file in allowed directory
        try:
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=".dxf",
                prefix="fireai_dwg_",
                dir=tempfile.gettempdir()  # Explicitly use secure temp directory
            )
            os.close(temp_fd)

            # V122 SECURITY: Use Path operations to ensure no path traversal occurs
            temp_path = Path(temp_path).resolve()

            # V122 SECURITY: Explicitly separate command arguments to prevent injection
            # Use "--" to mark the end of options and ensure the path is treated as a positional argument
            cmd = [self.DXF_OUT_CMD, "--", "--file", str(dwg_path), "--output", str(temp_path)]

            logger.debug(f"Executing command: {' '.join(cmd)}")

            proc = subprocess.run(cmd, capture_output=True, timeout=60)

            if proc.returncode != 0:
                error = proc.stderr.decode() or proc.stdout.decode()
                raise DWGConversionError(f"dxf-out failed: {error}")

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise DWGConversionError("Empty DXF output")

            return str(temp_path)

        except Exception:
            # Clean up temp file on failure
            try:
                if 'temp_path' in locals():
                    temp_path.unlink(missing_ok=True)
            finally:
                raise


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════


def parse_dwg(dwg_path: str) -> DWGParseResult:
    """Quick parse DWG file."""
    parser = DWGParser()
    return parser.parse(dwg_path)
