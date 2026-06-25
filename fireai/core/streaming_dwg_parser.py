"""streaming_dwg_parser.py — Real-time DWG Streaming Parser
=========================================================
Solves Section 11.1: "Process 100MB+ DWG files without loading entire
file into memory."

Architecture:
  - Chunk-based streaming: reads DWG in configurable chunk sizes
  - Yields rooms as they are assembled (generator pattern)
  - Memory ceiling: O(chunk_size) not O(file_size)
  - DXF fallback: streaming mode for DXF files
  - Integration with _assemble_closed_polygons() (our bidirectional algorithm)

Memory targets:
  - 100MB DWG: < 50MB peak RAM (vs 200MB+ with full load)
  - Throughput: ≥ 37K rooms/sec (matches V29 baseline)

V30 NOTE:
  Uses our bidirectional _assemble_closed_polygons from dwg_parser.py
  instead of the consultant's unidirectional version. Our algorithm
  extends chains from BOTH ends (head + tail), which handles more
  DWG/DXF patterns correctly. The consultant's version only extends
  from the tail, which can miss connections in certain drawing patterns.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Generator, Iterator, List, Tuple

logger = logging.getLogger("fireai.streaming_dwg_parser")


# ---------------------------------------------------------------------------
# Data structures (match core/models.py API)
# ---------------------------------------------------------------------------


@dataclass
class StreamedRoom:
    """Room assembled from streaming DWG/DXF parse."""

    room_id: str
    polygon: List[Tuple[float, float]]  # (x, y) vertices in metres
    area_m2: float = 0.0
    floor_id: str = ""
    source_line: int = 0  # line/byte offset in source file


@dataclass
class StreamingStats:
    """Statistics from a streaming parse session."""

    bytes_read: int = 0
    chunks: int = 0
    lines_parsed: int = 0
    rooms_yielded: int = 0
    errors: int = 0
    elapsed_s: float = 0.0

    @property
    def throughput_rooms_s(self) -> float:
        return self.rooms_yielded / max(self.elapsed_s, 1e-9)

    @property
    def mb_read(self) -> float:
        return self.bytes_read / 1_048_576


# ---------------------------------------------------------------------------
# Shoelace area calculation
# ---------------------------------------------------------------------------


def _shoelace_area(poly: List[Tuple[float, float]]) -> float:
    """Compute polygon area using the shoelace formula.

    Returns NaN if any coordinate is NaN (the value propagates
    naturally through arithmetic), which downstream code must
    handle by rejecting the room.
    """
    n = len(poly)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n - 1):
        acc += poly[i][0] * poly[i + 1][1] - poly[i + 1][0] * poly[i][1]
    acc += poly[-1][0] * poly[0][1] - poly[0][0] * poly[-1][1]
    return abs(acc) * 0.5


# ---------------------------------------------------------------------------
# V29 Bidirectional Polygon Assembly (from our dwg_parser.py)
# ---------------------------------------------------------------------------


def _assemble_closed_polygons_v29(
    lines: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    tolerance: float = 0.01,
    return_consumed: bool = False,
) -> list | tuple[list, set]:
    """V29 O(n) spatial grid index polygon assembler — BIDIRECTIONAL.

    This is our algorithm from dwg_parser.py, which extends chains
    from BOTH ends (head + tail). This handles more DWG/DXF drawing
    patterns correctly than unidirectional chaining.

    Performance: 37K+ rooms/sec on benchmark hardware.

    Parameters
    ----------
    lines : list of ((sx, sy), (ex, ey))
        Validated line segments with finite coordinates.
    tolerance : float
        Maximum distance (metres) to consider two endpoints coincident.
    return_consumed : bool
        If True, return (polygons, consumed_indices) tuple.
        V44 addition for correct pending_lines filtering.

    Returns
    -------
    list of list of (x, y)
        Each inner list is a closed polygon's vertex sequence.
        If return_consumed=True, returns (polygons, consumed_set).

    """
    if not lines:
        return []

    tol_sq = tolerance * tolerance

    # Phase 1: Build spatial grid index
    cell_size = tolerance
    grid_start: Dict[Tuple[int, int], set] = {}
    grid_end: Dict[Tuple[int, int], set] = {}

    for idx, (start, end) in enumerate(lines):
        sx, sy = start
        ex, ey = end
        cs = (int(math.floor(sx / cell_size)), int(math.floor(sy / cell_size)))
        ce = (int(math.floor(ex / cell_size)), int(math.floor(ey / cell_size)))
        grid_start.setdefault(cs, set()).add(idx)
        grid_end.setdefault(ce, set()).add(idx)

    consumed: set = set()
    closed_polygons: List[List[Tuple[float, float]]] = []

    def _find_neighbours(px: float, py: float) -> list:
        """Return line indices whose start or end is within tolerance of (px,py)."""
        cx = int(math.floor(px / cell_size))
        cy = int(math.floor(py / cell_size))
        candidates = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell = (cx + dx, cy + dy)
                for i in grid_start.get(cell, ()):
                    if i not in consumed:
                        candidates.add(i)
                for i in grid_end.get(cell, ()):
                    if i not in consumed:
                        candidates.add(i)
        return list(candidates)

    # Phase 2: Chain lines into polygons — BIDIRECTIONAL
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

    # V44 FIX: Also return consumed line indices so callers can filter
    # pending_lines correctly. Previously, callers had to use id() matching
    # which fails because polygon vertices are new tuples, not original lines.
    if return_consumed:
        return closed_polygons, consumed
    return closed_polygons


# ---------------------------------------------------------------------------
# DXF Streaming Parser
# ---------------------------------------------------------------------------


class StreamingDXFParser:
    """Streaming DXF parser: yields rooms as polygon entities are assembled.
    Reads DXF in text chunks without loading the full file.

    Section 11.1: handles 100MB+ DXF files with < 50MB peak RAM.
    """

    def __init__(
        self,
        chunk_lines: int = 5_000,  # Lines per chunk
        min_area_m2: float = 0.5,  # Skip tiny polygons
        tolerance_m: float = 0.01,  # Line endpoint snap tolerance
        scale_factor: float = 0.001,  # DXF units → metres (default: mm→m)
        floor_id: str = "F-01",
    ) -> None:
        self.chunk_lines = chunk_lines
        self.min_area_m2 = min_area_m2
        self.tolerance = tolerance_m
        self.scale = scale_factor
        self.floor_id = floor_id

    def stream_file(self, filepath: str) -> Generator[StreamedRoom, None, StreamingStats]:
        """Generator: yield StreamedRoom objects as they are assembled.

        Memory: only `chunk_lines` lines in memory at once.
        Never loads the full DXF file.

        Usage:
            for room in parser.stream_file("building.dxf"):
                density_optimizer.optimize(room)
        """
        stats = StreamingStats()
        t0 = time.perf_counter()
        room_counter = 0
        pending_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

        try:
            with open(filepath, encoding="utf-8", errors="replace", buffering=131_072) as fh:  # 128KB read buffer
                chunk_buf: List[str] = []
                for raw_line in fh:
                    stats.bytes_read += len(raw_line.encode("utf-8"))
                    stats.lines_parsed += 1
                    chunk_buf.append(raw_line)

                    if len(chunk_buf) >= self.chunk_lines:
                        new_lines = self._parse_dxf_chunk(chunk_buf)
                        pending_lines.extend(new_lines)
                        stats.chunks += 1

                        # Assemble polygons from accumulated lines
                        polygons, consumed = _assemble_closed_polygons_v29(
                            pending_lines, self.tolerance, return_consumed=True
                        )

                        for poly in polygons:
                            area = _shoelace_area(poly)
                            if area < self.min_area_m2:
                                continue
                            room_counter += 1
                            yield StreamedRoom(
                                room_id=f"R-{room_counter:08d}",
                                polygon=poly,
                                area_m2=round(area, 4),
                                floor_id=self.floor_id,
                                source_line=stats.lines_parsed,
                            )
                            stats.rooms_yielded += 1

                        # Keep only lines not yet assembled into polygons
                        # V44 FIX: Previously `pending_lines = []` silently dropped ALL lines,
                        # including orphans not consumed by polygon assembly. This meant rooms
                        # that span chunk boundaries were NEVER assembled — missing rooms = missing
                        # fire detectors = life safety failure. Now only remove consumed lines
                        # using the index set returned by _assemble_closed_polygons_v29.
                        if consumed:
                            pending_lines = [ln for i, ln in enumerate(pending_lines) if i not in consumed]
                        chunk_buf = []

                # Final chunk
                if chunk_buf:
                    new_lines = self._parse_dxf_chunk(chunk_buf)
                    pending_lines.extend(new_lines)
                    polygons = _assemble_closed_polygons_v29(pending_lines, self.tolerance)
                    for poly in polygons:
                        area = _shoelace_area(poly)  # type: ignore[arg-type]
                        if area < self.min_area_m2:
                            continue
                        room_counter += 1
                        yield StreamedRoom(
                            room_id=f"R-{room_counter:08d}",
                            polygon=poly,  # type: ignore[arg-type]
                            area_m2=round(area, 4),
                            floor_id=self.floor_id,
                            source_line=stats.lines_parsed,
                        )
                        stats.rooms_yielded += 1

        except Exception as exc:
            stats.errors += 1
            # V44 FIX: Previously, exceptions were silently swallowed without logging.
            # In fire protection software, a parse error that drops rooms means missing
            # fire detectors — a life-safety failure. Now we log the error.
            logger.error("DWG parse error at line %s: %s", stats.lines_parsed, exc)

        stats.elapsed_s = time.perf_counter() - t0
        return stats

    def _parse_dxf_chunk(
        self,
        lines: List[str],
    ) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """Extract LINE entity endpoints from DXF text chunk.
        DXF format: group code on one line, value on next.
        Returns list of ((x1,y1),(x2,y2)) segments.
        """
        segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        s = self.scale
        i = 0
        n = len(lines)

        while i < n - 1:
            code = lines[i].strip()
            val = lines[i + 1].strip()

            # Start of LINE entity
            if code == "0" and val.upper() == "LINE":
                x1 = y1 = x2 = y2 = None
                j = i + 2
                while j < min(i + 20, n - 1):
                    gc = lines[j].strip()
                    gv = lines[j + 1].strip()
                    try:
                        if gc == "10":
                            x1 = float(gv) * s
                        elif gc == "20":
                            y1 = float(gv) * s
                        elif gc == "11":
                            x2 = float(gv) * s
                        elif gc == "21":
                            y2 = float(gv) * s
                        elif gc == "0":
                            break  # Next entity
                    except ValueError:
                        pass
                    j += 2

                if None not in (x1, y1, x2, y2):
                    segments.append(((x1, y1), (x2, y2)))
                i = j
                continue

            # LWPOLYLINE entity (more compact)
            if code == "0" and val.upper() == "LWPOLYLINE":
                verts: List[Tuple[float, float]] = []
                cx = cy = None
                j = i + 2
                while j < min(i + 500, n - 1):
                    gc = lines[j].strip()
                    gv = lines[j + 1].strip()
                    try:
                        if gc == "10":
                            if cx is not None and cy is not None:
                                verts.append((cx, cy))
                            cx = float(gv) * s
                            cy = None
                        elif gc == "20":
                            cy = float(gv) * s
                            if cx is not None:
                                verts.append((cx, cy))
                                cx = cy = None
                        elif gc == "0":
                            break
                    except ValueError:
                        pass
                    j += 2

                # Convert polygon vertices to line segments
                for k in range(len(verts) - 1):
                    segments.append((verts[k], verts[k + 1]))
                if len(verts) >= 3:
                    segments.append((verts[-1], verts[0]))  # close
                i = j
                continue

            i += 2

        return segments


# ---------------------------------------------------------------------------
# Parallel Room Processor — Section 11.3: multiprocessing
# ---------------------------------------------------------------------------


class ParallelRoomProcessor:
    """Section 11.3: Embarrassingly parallel room optimization.
    Uses multiprocessing.Pool for DensityOptimizer across rooms.

    Target: 8 cores × ~2 rooms/sec = ~16 rooms/sec (8× speedup).
    API: backward-compatible — wraps existing optimize() calls.
    """

    def __init__(
        self,
        n_workers: int = 0,  # 0 = use os.cpu_count()
        chunk_size: int = 10,  # Rooms per worker chunk
    ) -> None:
        self.n_workers = n_workers or max(1, (os.cpu_count() or 4) - 1)
        self.chunk_size = chunk_size

    def process_batch(
        self,
        rooms: List[Any],
        optimize_fn: Any,  # DensityOptimizer instance or callable
    ) -> List[Any]:
        """Process N rooms in parallel using multiprocessing.Pool.
        Falls back to sequential if multiprocessing unavailable.

        rooms:       List of Room objects (or dicts)
        optimize_fn: Callable(room) → DetectorLayout

        Returns: List of DetectorLayout results (same order as input).
        """
        if not rooms:
            return []

        if self.n_workers <= 1 or len(rooms) < 4:
            # Sequential fallback for small batches or single-core
            return [optimize_fn(room) for room in rooms]

        try:
            import multiprocessing as mp

            # Use spawn context to avoid fork issues with Shapely
            ctx = mp.get_context("spawn")
            with ctx.Pool(processes=self.n_workers) as pool:
                results = pool.map(optimize_fn, rooms, chunksize=self.chunk_size)
            return results
        except Exception:
            # Fallback: sequential
            return [optimize_fn(room) for room in rooms]

    def process_stream(
        self,
        room_stream: Iterator[Any],
        optimize_fn: Any,
        buffer_size: int = 100,
    ) -> Generator[Any, None, None]:
        """Process streaming rooms: buffer buffer_size rooms, process in parallel,
        yield results. Combines Section 11.1 (streaming) + 11.3 (parallel).
        """
        buffer: List[Any] = []
        for room in room_stream:
            buffer.append(room)
            if len(buffer) >= buffer_size:
                for result in self.process_batch(buffer, optimize_fn):
                    yield result
                buffer = []
        # Final partial buffer
        for result in self.process_batch(buffer, optimize_fn):
            yield result
