"""api_stability.py — FireAI Public API Stability Layer
=====================================================
Section 11.4: "Freeze the public API so Revit plugin development can proceed."

Provides:
  - Versioned, stable public API surface (V29+)
  - Deprecation warnings for changed signatures
  - Adapter layer that insulates plugin code from internal refactors
  - Type-stable dataclasses for all plugin-facing data
  - Semantic versioning: MAJOR.MINOR.PATCH
    MAJOR: breaking changes (plugin must update)
    MINOR: new features (backward compatible)
    PATCH: bug fixes (transparent)
"""

from __future__ import annotations

import functools
import logging
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API version
# ---------------------------------------------------------------------------

API_VERSION = "29.0.0"
API_VERSION_TUPLE = (29, 0, 0)
MIN_PLUGIN_VERSION = "28.0.0"  # Oldest plugin version supported


# ---------------------------------------------------------------------------
# Stable plugin-facing dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginRoom:
    """Stable room representation for plugin API.
    Fields will not be removed in MINOR versions.
    New optional fields may be added without breaking existing plugins.
    """

    room_id: str
    width_m: float
    length_m: float
    ceiling_height_m: float
    area_m2: float
    polygon: Tuple[Tuple[float, float], ...]  # (x,y) vertices
    floor_id: str = ""
    name: str = ""
    detector_type: str = "smoke"


@dataclass(frozen=True)
class PluginDetectorLayout:
    """Stable detector layout for plugin API."""

    room_id: str
    detectors: Tuple[Tuple[float, float], ...]  # (x,y) positions
    count: int
    coverage_pct: float
    proof_valid: bool
    method: str
    # V114 FIX: Fail-safe default — no compliance until proven
    nfpa_compliant: bool = False
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginBuildingResult:
    """Stable building analysis result for plugin API."""

    building_id: str
    total_detectors: int
    total_rooms: int
    compliant_rooms: int
    non_compliant: Tuple[str, ...]
    safe_to_submit: bool
    api_version: str = API_VERSION


@dataclass(frozen=True)
class PluginCableRoute:
    """Stable cable route for plugin API."""

    route_id: str
    from_device: str
    to_device: str
    waypoints: Tuple[Tuple[float, float], ...]
    length_m: float
    cable_type: str
    circuit_class: str  # "A" or "B"


# ---------------------------------------------------------------------------
# Deprecation decorator
# ---------------------------------------------------------------------------


def deprecated(
    replacement: str,
    since: str = API_VERSION,
    removed_in: str = "",
) -> Callable:
    """Mark a public API function as deprecated.
    Emits DeprecationWarning on first call (not every call — uses set).
    """
    _warned: set = set()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if fn.__name__ not in _warned:
                msg = f"FireAI API: {fn.__name__}() is deprecated since v{since}. Use {replacement} instead."
                if removed_in:
                    msg += f" Will be removed in v{removed_in}."
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                _warned.add(fn.__name__)
            return fn(*args, **kwargs)

        wrapper._deprecated = True  # type: ignore[attr-defined]
        wrapper._replacement = replacement  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Stable API class
# ---------------------------------------------------------------------------


class FireAIPluginAPI:
    """Versioned, stable public API for Revit plugin integration.

    Section 11.4: This class is the ONLY interface plugins should use.
    Internal modules may change; this class provides a stable adapter.

    Compatibility guarantee:
      - All methods in this class will exist in all v29.x.x releases
      - Method signatures will not change (new params are keyword-only with defaults)
      - Return types are stable frozen dataclasses
    """

    def __init__(self, building_engine: Any = None) -> None:
        """Args:
        building_engine: BuildingEngine instance (optional — auto-created)

        """
        self._engine = building_engine
        self._version = API_VERSION

    @property
    def version(self) -> str:
        """API version string. Safe to check for compatibility."""
        return self._version

    @property
    def version_tuple(self) -> Tuple[int, int, int]:
        return API_VERSION_TUPLE

    def is_compatible_with(self, plugin_version: str) -> bool:
        """Check if this API is compatible with a plugin built for plugin_version.
        MAJOR version must match exactly.
        """
        try:
            parts = tuple(int(x) for x in plugin_version.split(".")[:3])
            return parts[0] == API_VERSION_TUPLE[0]
        except (ValueError, IndexError):
            return False

    def analyse_room(
        self,
        room: PluginRoom,
        *,
        coverage_radius: Optional[float] = None,
    ) -> PluginDetectorLayout:
        """Analyse a single room and return detector placement.

        Stable API: signature guaranteed not to change in v29.x.x.
        New optional parameters may be added as keyword-only with defaults.
        """
        if self._engine is None:
            return self._fallback_analyse_room(room, coverage_radius)

        try:
            result = self._engine.analyse_room(
                room_id=room.room_id,
                width=room.width_m,
                length=room.length_m,
                ceiling_height=room.ceiling_height_m,
                detector_type=room.detector_type,
                coverage_radius=coverage_radius,
            )
            return PluginDetectorLayout(
                room_id=room.room_id,
                detectors=tuple((x, y) for x, y in getattr(result, "detectors", [])),
                count=getattr(result, "count", 0),
                coverage_pct=getattr(result, "coverage_pct", 0.0),
                proof_valid=getattr(result, "proof_valid", False),
                method=getattr(result, "method", "unknown"),
                # V114 FIX: Fail-safe — missing nfpa_valid = NOT compliant
                nfpa_compliant=getattr(result, "nfpa_valid", False),
                warnings=tuple(getattr(result, "warnings", [])),
            )
        except Exception as exc:
            return PluginDetectorLayout(
                room_id=room.room_id,
                detectors=(),
                count=0,
                coverage_pct=0.0,
                proof_valid=False,
                method=f"error:{exc}",
                nfpa_compliant=False,
                warnings=(str(exc),),
            )

    def analyse_rooms_batch(
        self,
        rooms: List[PluginRoom],
        *,
        coverage_radius: Optional[float] = None,
        n_workers: int = 0,
    ) -> List[PluginDetectorLayout]:
        """Analyse multiple rooms. Parallelised internally when n_workers > 1.

        Stable API: always returns list of same length as input.
        Order preserved. Failed rooms return PluginDetectorLayout with proof_valid=False.

        Thread Safety (V0.3 Safety Guard):
          - ProcessPoolExecutor is FORBIDDEN: CBC (PuLP solver) is a C-level
            library that does NOT release the GIL; forking with CBC causes
            deadlocks (see building_engine.py V0.3 Safety Guard).
          - ThreadPoolExecutor is used ONLY in fallback mode (no engine).
            The fallback path (_fallback_analyse_room) is pure Python with
            no shared mutable state, so concurrent execution is safe.
          - When an engine is present, parallelisation is NOT safe because
            DensityOptimizer.optimize() temporarily mutates instance state
            (self.R, self.R_place, self.S_g, self.Ry_g) and restores it in
            a finally block — a classic race condition under concurrency.
            A WARNING is logged and execution falls back to sequential.
        """
        if n_workers <= 1 or len(rooms) <= 1:
            return [self.analyse_room(room, coverage_radius=coverage_radius) for room in rooms]

        # Engine path: DensityOptimizer.optimize() has mutable instance state
        # that is temporarily overridden per call — NOT thread-safe.
        if self._engine is not None:
            logger.warning(
                "analyse_rooms_batch: n_workers=%d ignored — parallelisation "
                "unsafe with engine present (DensityOptimizer mutable state "
                "race condition). Falling back to sequential execution. "
                "See building_engine.py V0.3 Safety Guard.",
                n_workers,
            )
            return [self.analyse_room(room, coverage_radius=coverage_radius) for room in rooms]

        # Fallback path: pure Python, no shared mutable state — thread-safe.
        # ProcessPoolExecutor is FORBIDDEN per V0.3 Safety Guard (CBC deadlock).
        # ThreadPoolExecutor is safe here because _fallback_analyse_room
        # only reads self-level constants and creates new objects per call.
        max_workers = max(1, min(n_workers, len(rooms)))
        indexed_results: List[Optional[PluginDetectorLayout]] = [None] * len(rooms)

        def _analyse_indexed(idx: int, room: PluginRoom) -> Tuple[int, PluginDetectorLayout]:
            result = self.analyse_room(room, coverage_radius=coverage_radius)
            return (idx, result)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_analyse_indexed, i, room): i for i, room in enumerate(rooms)}
            for future in as_completed(futures):
                idx, result = future.result()
                indexed_results[idx] = result

        # Guarantee: every slot filled (analyse_room never returns None)
        return list(indexed_results)  # type: ignore[arg-type]

    def analyse_building(
        self,
        building_id: str,
        rooms: List[PluginRoom],
        *,
        generate_pdf: bool = False,
    ) -> PluginBuildingResult:
        """Analyse full building. Stable API."""
        layouts = self.analyse_rooms_batch(rooms)
        compliant = sum(1 for l in layouts if l.nfpa_compliant)
        non_comp = tuple(l.room_id for l in layouts if not l.nfpa_compliant)
        total_det = sum(l.count for l in layouts)

        return PluginBuildingResult(
            building_id=building_id,
            total_detectors=total_det,
            total_rooms=len(rooms),
            compliant_rooms=compliant,
            non_compliant=non_comp,
            safe_to_submit=(compliant == len(rooms)),
            api_version=API_VERSION,
        )

    # ------------------------------------------------------------------
    # Deprecated methods (backward compat)
    # ------------------------------------------------------------------

    @deprecated("analyse_room()", since="29.0.0")
    def compute_detector_layout(self, room: PluginRoom) -> PluginDetectorLayout:
        """Deprecated: use analyse_room()."""
        return self.analyse_room(room)

    # ------------------------------------------------------------------
    # Fallback implementations (no engine)
    # ------------------------------------------------------------------

    def _fallback_analyse_room(
        self,
        room: PluginRoom,
        coverage_radius: Optional[float],
    ) -> PluginDetectorLayout:
        """Conservative fallback: place detectors on a grid when no engine available.
        Always places MORE detectors than needed (safety rule).
        """
        R = coverage_radius or 6.37
        spacing = R * 1.2  # Conservative: 20% margin
        w = room.width_m
        l = room.length_m
        dets = []
        x = spacing / 2.0
        while x < w:
            y = spacing / 2.0
            while y < l:
                dets.append((round(x, 3), round(y, 3)))
                y += spacing
            x += spacing

        return PluginDetectorLayout(
            room_id=room.room_id,
            detectors=tuple(dets),
            count=len(dets),
            coverage_pct=0.0,  # V44 FIX: Unknown coverage — was 95.0 (fabricated). Actual coverage depends on room geometry and detector type.
            proof_valid=False,  # Not mathematically proven
            method="fallback_grid",
            nfpa_compliant=False,  # V44 FIX: Cannot claim compliance without proof — was True (FALSE COMPLIANCE CLAIM). Per NFPA 72, compliance requires mathematical verification.
            warnings=("Fallback mode: no engine available. Verify coverage before submission.",),
        )


# ---------------------------------------------------------------------------
# API version check helper for plugins
# ---------------------------------------------------------------------------


def check_api_compatibility(plugin_requires: str) -> None:
    """Call at plugin startup to verify API compatibility.
    Raises RuntimeError if MAJOR version mismatch.

    Usage in plugin:
        from fireai.core.api_stability import check_api_compatibility
        check_api_compatibility("29.0.0")  # Plugin was built for v29
    """
    try:
        req = tuple(int(x) for x in plugin_requires.split(".")[:1])
        cur = (API_VERSION_TUPLE[0],)
        if req != cur:
            raise RuntimeError(
                f"FireAI API version mismatch: plugin requires v{plugin_requires}, "
                f"installed v{API_VERSION}. "
                f"Plugin must be updated for MAJOR version {API_VERSION_TUPLE[0]}."
            )
    except ValueError:
        raise ValueError(f"Invalid plugin_requires version: {plugin_requires!r}")
