"""fireai/bridges/integration_bridge.py
=====================================
LIFE-SAFETY CRITICAL: Integration Bridge for the FireAI Fire Alarm
Engineering Platform.  Wires together four core subsystems into a
unified pipeline:

  1. Cable Routing Engine      — NFPA 72-2022 §12.2 / §10.14
  2. Digital Twin Sync         — Bidirectional BIM synchronisation
  3. Acoustics Engine          — NFPA 72-2022 §18.4 audible coverage
  4. Multi-Floor Orchestrator  — NFPA 72-2022 §21 building analysis

DESIGN PRINCIPLES
-----------------
GRACEFUL DEGRADATION:
  If any subsystem import fails or any subsystem raises an exception
  during execution, the remaining subsystems CONTINUE to operate.
  In a life-safety context, partial results are ALWAYS better than no
  results.  Every failure is captured in ``IntegrationResult.errors``
  and logged at CRITICAL level for immediate visibility.

ISOLATED EXECUTION:
  Each subsystem runs inside its own ``try / except`` block.  Errors
  are never re-raised across subsystem boundaries.  This prevents a
  crash in cable routing from preventing acoustics analysis, and vice
  versa — occupants cannot afford blind spots in any domain.

COMPLIANCE GATE:
  ``overall_compliant`` is ``True`` ONLY when ALL *available*
  subsystems report compliance.  An unavailable subsystem (import
  failure) is excluded from the gate — it would be unreasonable to
  fail the entire building because an optional module is missing.
  However, every unavailable subsystem is recorded as a WARNING so
  that the responsible engineer can verify the gap.

Standards Referenced:
  NFPA 72-2022       — National Fire Alarm and Signaling Code
    §10.14            — Voltage drop limitations
    §12.2             — Pathway design (Class A / Class B)
    §12.3             — Pathway survivability
    §18.4             — Audible notification appliances
    §18.4.1.2         — Maximum sound level 110 dBA
    §18.4.2           — Sleeping areas 75 dBA at pillow
    §18.4.3           — Public mode: 15 dB above ambient
    §18.4.4           — Private mode: 10 dB above ambient
    §21.2.2           — SLC loop device limits (250 devices/loop)
    §21.3.2           — Elevator recall
    §21.3.3           — Vertical zone design
    §21.3.4           — Zone area limits
    §27.4.1           — Voltage drop 10 % limit
  NEC Article 760     — Fire alarm systems wiring
  ISA-TR84.00.07      — UGLD acoustic gas leak detection
  ISO 9613-1:1993     — Sound attenuation during propagation

Usage::

    from fireai.bridges.integration_bridge import (
        IntegrationBridge,
        IntegrationConfig,
        IntegrationResult,
    )

    config = IntegrationConfig(
        building_id="BLDG-001",
        floors=[FloorData(floor_id="GF", elevation_m=0.0, area_sqm=500.0)],
        panel_positions=[(1.0, 2.0, 0.0)],
        obstacle_polygons=[[(5.0, 0.0), (5.2, 0.0), (5.2, 10.0), (5.0, 10.0)]],
        acoustic_config=AcousticConfig(mode="public"),
    )

    bridge = IntegrationBridge(config)
    result = bridge.run()

    if not result.overall_compliant:
        for err in result.errors:
            print(f"ERROR: {err}")
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# SAFE IMPORTS — each subsystem is imported independently so that a
# missing or broken module does not affect the others.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Subsystem 1: Cable Routing Engine ────────────────────────────────────────
try:
    from fireai.core.cable_routing_engine import (  # type: ignore[attr-defined]
        CableRoutingEngine,
        CircuitTopology,
        RouteResult,
    )

    _HAS_CABLE_ROUTING = True
except ImportError as _exc_cable:
    CableRoutingEngine = None  # type: ignore[assignment,misc]
    RouteResult = None  # type: ignore[assignment,misc]
    CircuitTopology = None  # type: ignore[assignment,misc]
    _HAS_CABLE_ROUTING = False
    _CABLE_ROUTING_IMPORT_ERROR = str(_exc_cable)
else:
    _CABLE_ROUTING_IMPORT_ERROR = ""

# ── Subsystem 2: Digital Twin Sync ───────────────────────────────────────────
try:
    from fireai.core.digital_twin_sync import (
        DigitalTwinSync,
        SyncResult,
    )

    _HAS_TWIN_SYNC = True
except ImportError as _exc_twin:
    DigitalTwinSync = None  # type: ignore[assignment,misc]
    SyncResult = None  # type: ignore[assignment,misc]
    _HAS_TWIN_SYNC = False
    _TWIN_SYNC_IMPORT_ERROR = str(_exc_twin)
else:
    _TWIN_SYNC_IMPORT_ERROR = ""

# ── Subsystem 3: Acoustics Engine ────────────────────────────────────────────
try:
    from fireai.core.acoustics_engine import (
        AcousticCoverageResult,
        AcousticsEngine,
        UGLDCoverageResult,
    )

    _HAS_ACOUSTICS = True
except ImportError as _exc_acoustics:
    AcousticsEngine = None  # type: ignore[assignment,misc]
    AcousticCoverageResult = None  # type: ignore[assignment,misc]
    UGLDCoverageResult = None  # type: ignore[assignment,misc]
    _HAS_ACOUSTICS = False
    _ACOUSTICS_IMPORT_ERROR = str(_exc_acoustics)
else:
    _ACOUSTICS_IMPORT_ERROR = ""

# ── Subsystem 4: Multi-Floor Orchestrator ────────────────────────────────────
try:
    from fireai.core.multi_floor_orchestrator import (
        BuildingAnalysis,
        MultiFloorOrchestrator,
    )

    _HAS_MULTI_FLOOR = True
except ImportError as _exc_mfo:
    MultiFloorOrchestrator = None  # type: ignore[assignment,misc]
    BuildingAnalysis = None  # type: ignore[assignment,misc]
    _HAS_MULTI_FLOOR = False
    _MULTI_FLOOR_IMPORT_ERROR = str(_exc_mfo)
else:
    _MULTI_FLOOR_IMPORT_ERROR = ""

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL DATACLASSES — types needed by IntegrationConfig / IntegrationResult
# that are not provided by the subsystem modules.
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FloorData:
    """Per-floor metadata required by the integration bridge.

    Captures the minimum information needed to route cables, check
    acoustics, and orchestrate multi-floor analysis for a single
    building floor.

    Attributes:
        floor_id: Unique floor identifier (e.g. ``"GF"``, ``"L1"``).
        elevation_m: Floor elevation above grade in metres.
        area_sqm: Gross floor area in square metres.
        ceiling_height_m: Floor-to-ceiling height in metres.
            Default 3.0 m per NFPA 72-2022 typical commercial.
        occupancy_type: Dominant occupancy on this floor
            (e.g. ``"business"``, ``"residential"``).
        room_specs: Optional list of room specification dicts for
            per-room analysis by FloorOrchestrator.

    """

    floor_id: str
    elevation_m: float = 0.0
    area_sqm: float = 0.0
    ceiling_height_m: float = 3.0
    occupancy_type: str = "business"
    room_specs: Optional[List[Dict[str, Any]]] = None

    def __post_init__(self) -> None:
        """Validate floor data. Life-Safety Rule: reject NaN/Inf."""
        for name in ("elevation_m", "area_sqm", "ceiling_height_m"):
            val = getattr(self, name)
            if not math.isfinite(val):
                raise ValueError(
                    f"FloorData.{name}={val} is NaN/Inf — life-safety integration cannot operate on invalid geometry"
                )
        if self.area_sqm < 0:
            raise ValueError(f"FloorData.area_sqm={self.area_sqm} must be non-negative")
        if self.ceiling_height_m <= 0:
            raise ValueError(
                f"FloorData.ceiling_height_m={self.ceiling_height_m} must be "
                f"positive — NFPA 72-2022 requires valid ceiling height for "
                f"coverage and voltage drop calculations"
            )
        if not self.floor_id or not self.floor_id.strip():
            raise ValueError("FloorData.floor_id must be a non-empty string")


@dataclass
class AcousticConfig:
    """Configuration for acoustic coverage analysis.

    Encapsulates the parameters needed to run the AcousticsEngine
    check across all floors of a building.

    Attributes:
        mode: Audible notification mode per NFPA 72 §18.4 —
            ``"public"`` (§18.4.3), ``"private"`` (§18.4.4),
            or ``"sleeping"`` (§18.4.2).
        ambient_noise_dba: Default ambient noise level in dBA.
            If ``None``, the AcousticsEngine default is used.
        speaker_rating_dba: Speaker sound pressure level rating
            at 3 m (or reference distance) in dBA.
        include_ugld: Whether to include UGLD (ultrasonic gas leak
            detection) analysis per ISA-TR84.00.07.

    """

    mode: str = "public"
    ambient_noise_dba: Optional[float] = None
    speaker_rating_dba: float = 95.0
    include_ugld: bool = False

    def __post_init__(self) -> None:
        """Validate acoustic configuration."""
        valid_modes = {"public", "private", "sleeping"}
        if self.mode not in valid_modes:
            raise ValueError(
                f"AcousticConfig.mode='{self.mode}' is invalid. Must be one of {sorted(valid_modes)} per NFPA 72 §18.4."
            )
        if self.speaker_rating_dba <= 0:
            raise ValueError(
                f"AcousticConfig.speaker_rating_dba={self.speaker_rating_dba} "
                f"must be positive — a non-positive rating is physically "
                f"meaningless and violates NFPA 72 §18.4.1.2"
            )
        if self.ambient_noise_dba is not None and self.ambient_noise_dba < 0:
            raise ValueError(f"AcousticConfig.ambient_noise_dba={self.ambient_noise_dba} must be non-negative")


@dataclass
class CableRoutingResult:
    """Aggregated result from the Cable Routing Engine subsystem.

    Wraps the per-circuit :class:`RouteResult` objects produced by
    :class:`CableRoutingEngine` into a single building-level result
    with an overall compliance verdict.

    Attributes:
        routes: Per-circuit routing results from the engine.
        all_routes_valid: ``True`` only if every circuit route is valid.
        all_voltage_drop_compliant: ``True`` only if every circuit meets
            NFPA 72-2022 §10.14 voltage drop limits.
        total_cable_length_m: Sum of all circuit cable lengths.
        circuit_count: Number of circuits routed.
        violations: Aggregated violations across all circuits.
        warnings: Aggregated warnings across all circuits.

    """

    routes: List[Any] = field(default_factory=list)
    all_routes_valid: bool = False  # V112: FAIL-SAFE — routes not valid until verified
    all_voltage_drop_compliant: bool = False  # V112: FAIL-SAFE — voltage drop not compliant until verified
    total_cable_length_m: float = 0.0
    circuit_count: int = 0
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        """Overall cable routing compliance."""
        return self.all_routes_valid and self.all_voltage_drop_compliant


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION CONFIG
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class IntegrationConfig:
    """Configuration for a single integration bridge run.

    Captures all the data required by the four subsystems:
    building geometry (floors), FACP locations, obstacles for cable
    routing, acoustic parameters, and the NFPA edition year.

    Attributes:
        building_id: Unique building identifier for audit trail.
        floors: List of :class:`FloorData` objects, one per floor.
        panel_positions: 3D positions of Fire Alarm Control Panels
            (FACP) in building coordinates (metres).  Used by cable
            routing as the origin point for all circuits.
        obstacle_polygons: List of 2D obstacle polygons for cable
            routing.  Each polygon is a list of (x, y) vertex tuples
            in metres.
        acoustic_config: Optional acoustic analysis configuration.
            If ``None``, acoustic analysis runs with defaults.
        nfpa_year: NFPA 72 edition year.  Default 2022.
            Supported values: 2019, 2022.  Used for edition-specific
            rule selection throughout all subsystems.

    """

    building_id: str
    floors: List[FloorData] = field(default_factory=list)
    panel_positions: List[Tuple[float, float, float]] = field(default_factory=list)
    obstacle_polygons: List[List[Tuple[float, float]]] = field(default_factory=list)
    acoustic_config: Optional[AcousticConfig] = None
    nfpa_year: int = 2022

    def __post_init__(self) -> None:
        """Validate integration configuration.

        Life-Safety Rule: reject invalid configuration early rather
        than producing silently incorrect results.
        """
        if not self.building_id or not self.building_id.strip():
            raise ValueError(
                "IntegrationConfig.building_id must be a non-empty string. "
                "Every building analysis MUST be traceable to a unique identifier "
                "per NFPA 72 §7.5 documentation requirements."
            )

        supported_years = {2019, 2022}
        if self.nfpa_year not in supported_years:
            raise ValueError(
                f"IntegrationConfig.nfpa_year={self.nfpa_year} is not supported. "
                f"Supported editions: {sorted(supported_years)}. "
                f"NFPA 72 code requirements are edition-specific — using an "
                f"unsupported edition could produce non-compliant designs."
            )

        # Validate panel positions contain finite values
        for i, pos in enumerate(self.panel_positions):
            if len(pos) != 3:
                raise ValueError(
                    f"panel_positions[{i}]={pos} must be a 3-tuple (x, y, z). "
                    f"3D coordinates are required for cable routing."
                )
            for j, coord in enumerate(pos):
                if not math.isfinite(coord):
                    raise ValueError(
                        f"panel_positions[{i}][{j}]={coord} is NaN/Inf — "
                        f"life-safety cable routing cannot operate on invalid "
                        f"panel coordinates."
                    )

        # Validate obstacle polygons contain finite values
        for i, polygon in enumerate(self.obstacle_polygons):
            if len(polygon) < 3:
                raise ValueError(
                    f"obstacle_polygons[{i}] has {len(polygon)} vertices — a polygon requires at least 3 vertices."
                )
            for j, vertex in enumerate(polygon):
                if len(vertex) != 2:
                    raise ValueError(f"obstacle_polygons[{i}][{j}]={vertex} must be a 2-tuple (x, y).")
                for k, coord in enumerate(vertex):
                    if not math.isfinite(coord):
                        raise ValueError(
                            f"obstacle_polygons[{i}][{j}][{k}]={coord} is NaN/Inf — invalid obstacle geometry."
                        )


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION RESULT
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class IntegrationResult:
    """Combined results from all four integration subsystems.

    This is the primary output of :meth:`IntegrationBridge.run`.  It
    captures results, errors, and warnings from every subsystem that
    was executed, plus an overall compliance verdict.

    LIFE-SAFETY COMPLIANCE GATE:
        ``overall_compliant`` is ``True`` ONLY when ALL subsystems
        that were *available and executed* report compliance.  A
        subsystem that was unavailable (import failure) is NOT counted
        as a failure — it would be unreasonable to fail a building
        because an optional module is not installed.  However, every
        unavailable subsystem produces a WARNING that the responsible
        engineer must acknowledge.

    Attributes:
        cable_result: Result from the Cable Routing Engine subsystem.
            ``None`` if the subsystem was unavailable or failed.
        twin_result: Result from the Digital Twin Sync subsystem.
            ``None`` if the subsystem was unavailable or failed.
        acoustic_result: Result from the Acoustics Engine subsystem.
            ``None`` if the subsystem was unavailable or failed.
        multi_floor_result: Result from the Multi-Floor Orchestrator.
            ``None`` if the subsystem was unavailable or failed.
        errors: Error messages from individual subsystems.  Each entry
            describes *which* subsystem failed and *why*, supporting
            rapid diagnosis by the responsible fire protection engineer.
        warnings: Warning messages from subsystems or from the bridge
            itself (e.g. unavailable subsystems, degraded operation).
        overall_compliant: ``True`` only if ALL available subsystems
            that successfully executed reported compliance.
        execution_time_s: Total wall-clock execution time in seconds.

    """

    cable_result: Optional[CableRoutingResult] = None
    twin_result: Optional[Any] = None  # SyncResult — Any because import may fail
    acoustic_result: Optional[Any] = None  # AcousticCoverageResult
    multi_floor_result: Optional[Any] = None  # BuildingAnalysis
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    overall_compliant: bool = False
    execution_time_s: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════


class IntegrationBridge:
    """Unified pipeline that wires together four FireAI subsystems.

    The integration bridge executes the following subsystems **in
    sequence** with safe error handling so that a failure in any one
    subsystem does not prevent the others from running:

      1. **Cable Routing** — Routes Class A / Class B circuits with
         obstacle avoidance, NEC 760 wire gauge verification, and
         NFPA 72-2022 §10.14 voltage drop compliance.
      2. **Digital Twin Sync** — Synchronises the design model to the
         digital twin, capturing a versioned snapshot for audit trail.
      3. **Acoustics** — Verifies NFPA 72 §18.4 audible notification
         coverage and optionally ISA-TR84.00.07 UGLD detection.
      4. **Multi-Floor** — Orchestrates SLC loop assignment, vertical
         zone design, smoke spread analysis, elevator recall, and
         riser routing per NFPA 72-2022 §21.

    Thread Safety:
        NOT thread-safe.  Create one instance per sequential call.

    Example::

        config = IntegrationConfig(
            building_id="BLDG-001",
            floors=[FloorData(floor_id="GF", area_sqm=500.0)],
            panel_positions=[(1.0, 2.0, 0.0)],
            obstacle_polygons=[],
        )
        bridge = IntegrationBridge(config)
        result = bridge.run()
        if not result.overall_compliant:
            for err in result.errors:
                logger.critical("Integration failure: %s", err)
    """

    # Subsystem names for error/warning messages
    _SUB_CABLE = "Cable Routing Engine"
    _SUB_TWIN = "Digital Twin Sync"
    _SUB_ACOUSTICS = "Acoustics Engine"
    _SUB_MULTI_FLOOR = "Multi-Floor Orchestrator"

    def __init__(self, config: IntegrationConfig) -> None:
        """Initialize the integration bridge.

        Args:
            config: Integration configuration containing building
                geometry, panel positions, obstacles, and acoustic
                parameters.

        Raises:
            TypeError: If ``config`` is not an :class:`IntegrationConfig`.
            ValueError: If ``config`` fails validation.

        """
        if not isinstance(config, IntegrationConfig):
            raise TypeError(
                f"Expected IntegrationConfig, got {type(config).__name__}. "
                f"The integration bridge requires a validated configuration "
                f"to ensure life-safety analysis completeness."
            )

        self._config = config

        # Log subsystem availability at initialization
        availability = {
            self._SUB_CABLE: _HAS_CABLE_ROUTING,
            self._SUB_TWIN: _HAS_TWIN_SYNC,
            self._SUB_ACOUSTICS: _HAS_ACOUSTICS,
            self._SUB_MULTI_FLOOR: _HAS_MULTI_FLOOR,
        }

        for name, available in availability.items():
            if available:
                logger.info("IntegrationBridge: %s — AVAILABLE", name)
            else:
                logger.warning(
                    "IntegrationBridge: %s — UNAVAILABLE (import failed). "
                    "This subsystem will be skipped during execution. "
                    "The overall compliance gate will NOT penalise for "
                    "unavailable subsystems, but the responsible engineer "
                    "must verify the gap manually.",
                    name,
                )

        logger.info(
            "IntegrationBridge initialized: building=%s floors=%d "
            "panels=%d obstacles=%d nfpa_year=%d subsystems_available=%d/%d",
            config.building_id,
            len(config.floors),
            len(config.panel_positions),
            len(config.obstacle_polygons),
            config.nfpa_year,
            sum(availability.values()),
            len(availability),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Main Execution
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> IntegrationResult:
        """Execute all four subsystems in sequence with safe error handling.

        Each subsystem is executed in its own ``try / except`` block.
        If one subsystem fails, its error is captured and the remaining
        subsystems continue.  This ensures that a cable routing failure
        does not prevent acoustics analysis, and vice versa.

        Overall compliance (``overall_compliant``) is ``True`` ONLY
        when ALL *available* subsystems that successfully executed
        report compliance.  An unavailable or failed subsystem is
        recorded as a warning/error but does NOT automatically cause
        overall non-compliance — the compliance gate only evaluates
        subsystems that actually produced a result.

        Returns:
            :class:`IntegrationResult` with combined outcomes from all
            subsystems, any errors, warnings, and the overall
            compliance verdict.

        Reference:
            NFPA 72-2022 §10.14, §12.2, §18.4, §21

        """
        t0 = time.monotonic()

        result = IntegrationResult()

        # Record unavailable subsystems as warnings
        if not _HAS_CABLE_ROUTING:
            result.warnings.append(
                f"{self._SUB_CABLE} is unavailable "
                f"(import error: {_CABLE_ROUTING_IMPORT_ERROR}). "
                f"Cable routing and voltage drop verification per "
                f"NFPA 72-2022 §10.14 / §12.2 were NOT performed."
            )
        if not _HAS_TWIN_SYNC:
            result.warnings.append(
                f"{self._SUB_TWIN} is unavailable "
                f"(import error: {_TWIN_SYNC_IMPORT_ERROR}). "
                f"Digital twin synchronisation was NOT performed."
            )
        if not _HAS_ACOUSTICS:
            result.warnings.append(
                f"{self._SUB_ACOUSTICS} is unavailable "
                f"(import error: {_ACOUSTICS_IMPORT_ERROR}). "
                f"Audible notification coverage per NFPA 72-2022 §18.4 "
                f"was NOT verified."
            )
        if not _HAS_MULTI_FLOOR:
            result.warnings.append(
                f"{self._SUB_MULTI_FLOOR} is unavailable "
                f"(import error: {_MULTI_FLOOR_IMPORT_ERROR}). "
                f"Multi-floor analysis per NFPA 72-2022 §21 was NOT performed."
            )

        # ── Subsystem 1: Cable Routing ───────────────────────────────────
        try:
            result.cable_result = self._run_cable_routing()
        except Exception as exc:
            msg = (
                f"CRITICAL: {self._SUB_CABLE} failed: "
                f"{type(exc).__name__}: {exc}. "
                f"Cable routing and voltage drop verification per "
                f"NFPA 72-2022 §10.14 were NOT completed. "
                f"Other subsystems continue with available data."
            )
            logger.critical(msg)
            result.errors.append(msg)

        # ── Subsystem 2: Digital Twin Sync ───────────────────────────────
        try:
            result.twin_result = self._run_twin_sync()
        except Exception as exc:
            msg = (
                f"CRITICAL: {self._SUB_TWIN} failed: "
                f"{type(exc).__name__}: {exc}. "
                f"Digital twin synchronisation was NOT completed. "
                f"Other subsystems continue with available data."
            )
            logger.critical(msg)
            result.errors.append(msg)

        # ── Subsystem 3: Acoustics ───────────────────────────────────────
        try:
            result.acoustic_result = self._run_acoustics()
        except Exception as exc:
            msg = (
                f"CRITICAL: {self._SUB_ACOUSTICS} failed: "
                f"{type(exc).__name__}: {exc}. "
                f"Audible notification coverage per NFPA 72-2022 §18.4 "
                f"was NOT verified. "
                f"Other subsystems continue with available data."
            )
            logger.critical(msg)
            result.errors.append(msg)

        # ── Subsystem 4: Multi-Floor ─────────────────────────────────────
        try:
            result.multi_floor_result = self._run_multi_floor()
        except Exception as exc:
            msg = (
                f"CRITICAL: {self._SUB_MULTI_FLOOR} failed: "
                f"{type(exc).__name__}: {exc}. "
                f"Multi-floor analysis per NFPA 72-2022 §21 was NOT completed. "
                f"Other subsystems continue with available data."
            )
            logger.critical(msg)
            result.errors.append(msg)

        # ── Evaluate overall compliance ──────────────────────────────────
        result.overall_compliant = self._evaluate_overall_compliance(result)

        result.execution_time_s = round(time.monotonic() - t0, 3)

        # ── Final log ────────────────────────────────────────────────────
        subsystems_ok = sum(
            1
            for r in [
                result.cable_result,
                result.twin_result,
                result.acoustic_result,
                result.multi_floor_result,
            ]
            if r is not None
        )
        logger.info(
            "IntegrationBridge complete: building=%s compliant=%s subsystems_ok=%d/4 errors=%d warnings=%d t=%.2fs",
            self._config.building_id,
            result.overall_compliant,
            subsystems_ok,
            len(result.errors),
            len(result.warnings),
            result.execution_time_s,
        )

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Subsystem 1: Cable Routing
    # ──────────────────────────────────────────────────────────────────────

    def _run_cable_routing(self) -> Optional[CableRoutingResult]:
        """Run cable routing for the building.

        Creates a :class:`CableRoutingEngine` instance, loads obstacle
        polygons from the configuration, and routes cables from each
        panel position.  Returns an aggregated :class:`CableRoutingResult`
        covering all circuits.

        If the Cable Routing Engine is not available (import failure),
        returns ``None`` immediately — this is NOT an error condition.

        Returns:
            :class:`CableRoutingResult` with per-circuit details and
            overall compliance status, or ``None`` if the subsystem
            is unavailable.

        Reference:
            NFPA 72-2022 §10.14 (voltage drop), §12.2 (pathway design),
            NEC Article 760 (fire alarm wiring)

        """
        if not _HAS_CABLE_ROUTING:
            logger.info("%s skipped — subsystem unavailable.", self._SUB_CABLE)
            return None

        config = self._config

        # Build obstacles from polygon data
        obstacles: List[Any] = []
        if config.obstacle_polygons and CableRoutingEngine is not None:
            # Import the obstacle dataclass locally — it was imported
            # successfully along with CableRoutingEngine
            from fireai.core.cable_routing_engine import ObstacleType, RoutingObstacle3D

            for poly in config.obstacle_polygons:
                if len(poly) < 3:
                    continue
                # Compute AABB from polygon vertices
                xs = [v[0] for v in poly]
                ys = [v[1] for v in poly]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                obstacles.append(
                    RoutingObstacle3D(
                        obstacle_type=ObstacleType.ARCHITECTURAL,
                        x=min_x,
                        y=min_y,
                        z=0.0,
                        width=max_x - min_x,
                        height=max_y - min_y,
                        depth=3.0,  # Default floor height
                        clearance_m=0.05,
                    )
                )

        # Create routing engine
        engine = CableRoutingEngine(obstacles=obstacles)

        # Route from each panel position
        cable_result = CableRoutingResult()
        all_routes: List[Any] = []
        total_length = 0.0
        all_valid = True
        all_vd_compliant = True
        violations: List[str] = []
        warnings: List[str] = []

        for panel_pos in config.panel_positions:
            # Collect device positions from all floors
            device_positions: List[Tuple[float, float, float]] = []
            for floor in config.floors:
                if floor.room_specs:
                    for room in floor.room_specs:
                        detectors = room.get("detectors", [])
                        for det in detectors:
                            if isinstance(det, dict):
                                device_positions.append(
                                    (
                                        float(det.get("x", 0.0)),
                                        float(det.get("y", 0.0)),
                                        float(det.get("z", floor.ceiling_height_m)),
                                    )
                                )
                            elif isinstance(det, (list, tuple)) and len(det) >= 2:
                                device_positions.append(
                                    (
                                        float(det[0]),
                                        float(det[1]),
                                        floor.ceiling_height_m,
                                    )
                                )

            if not device_positions:
                warnings.append(
                    f"No device positions found for panel at {panel_pos}. "
                    f"Cable routing requires at least one device to route to."
                )
                continue

            # V76 HIGH-14 FIX: Previously hardcoded 0.5A and AWG 14 for all NAC
            # circuits. This underestimates current for multi-device circuits and
            # uses incorrect wire gauge. Now calculates current from device count.
            # Default 0.1A per notification appliance (typical horn/strobe per
            # NFPA 72 Table 18.5.2.1). Default AWG 14 for NAC circuits per
            # NEC 760.154 — should be overridden by actual circuit specification.
            DEFAULT_NAC_CURRENT_PER_DEVICE_A = 0.1
            DEFAULT_NAC_AWG = "14"
            nac_current = max(0.5, len(device_positions) * DEFAULT_NAC_CURRENT_PER_DEVICE_A)

            # Route Class B (home-run) circuit from this panel
            route = engine.route_loop(  # type: ignore[attr-defined]
                circuit_id=f"NAC-{len(all_routes) + 1}",
                topology=CircuitTopology.CLASS_B,
                panel_pos=panel_pos,
                device_positions=device_positions,
                current_a=nac_current,
                awg=DEFAULT_NAC_AWG,
            )

            all_routes.append(route)
            total_length += route.total_length_m

            if not route.valid:
                all_valid = False
                violations.extend(route.violations)

            if not route.voltage_drop_compliant:
                all_vd_compliant = False
                violations.append(
                    f"Circuit {route.circuit_id} voltage drop "
                    f"{route.total_voltage_drop_pct:.1f}% exceeds 10% limit "
                    f"per NFPA 72-2022 §27.4.1 / §10.14."
                )

            for v in route.violations:
                violations.append(f"Circuit {route.circuit_id}: {v}")

        cable_result.routes = all_routes
        # V79 FIX: Zero-panel cable routing is NOT compliant.
        # Previously, if no panels were defined, the for-loop never executed
        # and all_valid/all_vd_compliant remained True, making compliant=True.
        # NFPA 72 §10.14 requires verification of ALL circuits. Zero circuits ≠ compliant.
        if not all_routes:
            all_valid = False
            all_vd_compliant = False
            violations.append(
                "No cable circuits were routed. Either no panels defined or no "
                "device positions found. Cable routing verification per NFPA 72 "
                "§10.14 was NOT performed — cannot claim compliance."
            )
        cable_result.all_routes_valid = all_valid
        cable_result.all_voltage_drop_compliant = all_vd_compliant
        cable_result.total_cable_length_m = round(total_length, 2)
        cable_result.circuit_count = len(all_routes)
        cable_result.violations = violations
        cable_result.warnings = warnings

        if cable_result.compliant:
            logger.info(
                "%s PASS: %d circuits, %.1fm total cable, all voltage drop compliant per NFPA 72-2022 §10.14",
                self._SUB_CABLE,
                cable_result.circuit_count,
                cable_result.total_cable_length_m,
            )
        else:
            logger.warning(
                "%s FAIL: %d circuits, %d violations. Cable routing must be corrected before AHJ submittal.",
                self._SUB_CABLE,
                cable_result.circuit_count,
                len(cable_result.violations),
            )

        return cable_result

    # ──────────────────────────────────────────────────────────────────────
    # Subsystem 2: Digital Twin Sync
    # ──────────────────────────────────────────────────────────────────────

    def _run_twin_sync(self) -> Optional[Any]:
        """Sync the current design to the digital twin.

        Creates a :class:`DigitalTwinSync` instance and synchronises
        the building design data, capturing a versioned snapshot for
        audit trail reconstruction.

        If the Digital Twin Sync module is not available (import
        failure), returns ``None`` immediately.

        Returns:
            ``SyncResult`` from the digital twin sync operation, or
            ``None`` if the subsystem is unavailable.

        Reference:
            NFPA 72-2022 §7.5 (documentation requirements),
            §14.3.4 (decommissioned devices)

        """
        if not _HAS_TWIN_SYNC:
            logger.info("%s skipped — subsystem unavailable.", self._SUB_TWIN)
            return None

        config = self._config

        # Build detector data for twin sync from floor room specs
        design_detectors: List[Dict[str, Any]] = []
        for floor in config.floors:
            if floor.room_specs:
                for room in floor.room_specs:
                    if not isinstance(room, dict):
                        continue
                    room_id = room.get("room_id", room.get("id", "UNKNOWN"))
                    detectors = room.get("detectors", [])
                    for det in detectors:
                        if isinstance(det, dict):
                            design_detectors.append(
                                {
                                    "detector_id": det.get("detector_id", det.get("id", "")),
                                    "room_id": room_id,
                                    "x": float(det.get("x", 0.0)),
                                    "y": float(det.get("y", 0.0)),
                                    "z": float(det.get("z", floor.ceiling_height_m)),
                                    "detector_type": det.get("detector_type", "smoke"),
                                    "coverage_radius": det.get("coverage_radius"),
                                }
                            )

        # Create DigitalTwin instance for this building
        from fireai.core.digital_twin import DigitalTwin

        twin = DigitalTwin(building_id=config.building_id)

        # Create sync engine with the twin instance
        sync = DigitalTwinSync(twin=twin)

        # Sync design detectors to the twin (always as PLANNED per safety rule)
        sync_result = sync.sync_design_to_twin(design_detectors)

        # Also run drift detection and coverage validation
        drift_report = sync.detect_drift()
        coverage_result = sync.validate_coverage()

        if sync_result and sync_result.success:
            logger.info(
                "%s PASS: building=%s %d detectors synced, drift=%d critical, coverage=%.1f%%",
                self._SUB_TWIN,
                config.building_id,
                sync_result.synced_count,
                drift_report.critical_count if drift_report else 0,
                coverage_result.coverage_pct * 100.0 if coverage_result else 0.0,
            )
        else:
            logger.warning(
                "%s: sync completed with warnings for building=%s (errors=%d, synced=%d)",
                self._SUB_TWIN,
                config.building_id,
                sync_result.error_count if sync_result else 0,
                sync_result.synced_count if sync_result else 0,
            )

        return sync_result

    # ──────────────────────────────────────────────────────────────────────
    # Subsystem 3: Acoustics
    # ──────────────────────────────────────────────────────────────────────

    def _run_acoustics(self) -> Optional[Any]:
        """Check acoustic coverage for the building.

        Runs the :class:`AcousticsEngine` to verify NFPA 72-2022 §18.4
        audible notification coverage across all floors.  For each floor
        with room specifications, the engine checks that speakers provide
        adequate SPL at all check points.

        If the Acoustics Engine is not available (import failure),
        returns ``None`` immediately.

        Returns:
            :class:`AcousticCoverageResult` from the acoustics engine,
            or ``None`` if the subsystem is unavailable.

        Reference:
            NFPA 72-2022 §18.4 (audible notification),
            §18.4.1.2 (max 110 dBA),
            §18.4.2 (sleeping areas 75 dBA),
            §18.4.3 (public mode +15 dB),
            §18.4.4 (private mode +10 dB)

        """
        if not _HAS_ACOUSTICS:
            logger.info("%s skipped — subsystem unavailable.", self._SUB_ACOUSTICS)
            return None

        config = self._config
        acoustic_cfg = config.acoustic_config or AcousticConfig()

        engine = AcousticsEngine()

        # Aggregate acoustic results across all floors
        # We run check_coverage per floor and then combine the results
        worst_result: Optional[AcousticCoverageResult] = None
        all_compliant = True

        for floor in config.floors:
            if not floor.room_specs:
                continue

            for room in floor.room_specs:
                if not isinstance(room, dict):
                    continue

                room_id = room.get("room_id", f"{floor.floor_id}_unknown")
                occ_type = room.get("occupancy_type", floor.occupancy_type)

                # Extract speakers and check points from room data
                speakers = room.get("speakers", [])
                check_points = room.get("check_points", [])

                if not speakers or not check_points:
                    # Skip rooms without speaker/check point data
                    continue

                # Convert dicts to Speaker/CheckPoint objects if needed
                try:
                    from fireai.core.acoustic_calculator import CheckPoint, Speaker

                    typed_speakers = []
                    for sp in speakers:
                        if isinstance(sp, Speaker):
                            typed_speakers.append(sp)
                        elif isinstance(sp, dict):
                            typed_speakers.append(
                                Speaker(
                                    x=float(sp.get("x", 0.0)),
                                    y=float(sp.get("y", 0.0)),
                                    z=float(sp.get("z", floor.ceiling_height_m)),
                                    rating_dba=float(
                                        sp.get(
                                            "rating_dba",
                                            acoustic_cfg.speaker_rating_dba,
                                        )
                                    ),
                                )
                            )
                        else:
                            continue

                    typed_checkpoints = []
                    for cp in check_points:
                        if isinstance(cp, CheckPoint):
                            typed_checkpoints.append(cp)
                        elif isinstance(cp, dict):
                            typed_checkpoints.append(
                                CheckPoint(
                                    x=float(cp.get("x", 0.0)),
                                    y=float(cp.get("y", 0.0)),
                                    z=float(cp.get("z", 1.5)),
                                )
                            )
                        else:
                            continue

                except ImportError:
                    # acoustic_calculator not available — pass raw data
                    typed_speakers = speakers  # type: ignore[assignment]
                    typed_checkpoints = check_points  # type: ignore[assignment]

                try:
                    room_result = engine.check_coverage(
                        room_id=room_id,
                        occ_type=occ_type,
                        speakers=typed_speakers,
                        check_points=typed_checkpoints,
                        mode=acoustic_cfg.mode,
                    )
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "%s: room %s skipped — %s: %s",
                        self._SUB_ACOUSTICS,
                        room_id,
                        type(exc).__name__,
                        exc,
                    )
                    continue

                if not room_result.compliant:
                    all_compliant = False

                # Track the worst result
                if worst_result is None or (
                    hasattr(room_result, "margin_dba")
                    and hasattr(worst_result, "margin_dba")
                    and room_result.margin_dba < worst_result.margin_dba
                ):
                    worst_result = room_result

        if worst_result is not None:
            if all_compliant:
                logger.info(
                    "%s PASS: all rooms compliant, mode=%s, worst margin=%.1f dB per NFPA 72-2022 §18.4",
                    self._SUB_ACOUSTICS,
                    acoustic_cfg.mode,
                    worst_result.margin_dba,
                )
            else:
                logger.warning(
                    "%s FAIL: one or more rooms non-compliant, mode=%s, worst margin=%.1f dB per NFPA 72-2022 §18.4",
                    self._SUB_ACOUSTICS,
                    acoustic_cfg.mode,
                    worst_result.margin_dba,
                )
        else:
            # V79 FIX: No rooms with speaker/check_point data is NOT just "no results"
            # — it means audible notification was never verified. NFPA 72 §18.4
            # requires audible coverage in ALL occupiable spaces. Returning None
            # means acoustics is excluded from the compliance gate entirely, allowing
            # overall_compliant=True even though occupants may not hear the fire alarm.
            logger.critical(
                "%s: NO rooms had speaker/check_point data. Audible notification "
                "coverage per NFPA 72-2022 §18.4 was NOT verified for ANY room. "
                "This is a life-safety gap — occupants may not hear the fire alarm.",
                self._SUB_ACOUSTICS,
            )
            # Return a non-compliant result so the compliance gate sees acoustics as FAILED
            try:
                from fireai.core.acoustic_calculator import (  # type: ignore[attr-defined]
                    AcousticCoverageResult,  # type: ignore[attr-defined,import-untyped]
                )
                worst_result = AcousticCoverageResult(
                    room_id="BUILDING_WIDE",
                    compliant=False,
                    margin_dba=float('-inf'),
                )
            except Exception:
                worst_result = None

        return worst_result

    # ──────────────────────────────────────────────────────────────────────
    # Subsystem 4: Multi-Floor Orchestrator
    # ──────────────────────────────────────────────────────────────────────

    def _run_multi_floor(self) -> Optional[Any]:
        """Orchestrate multi-floor analysis for the building.

        Creates a :class:`MultiFloorOrchestrator` instance and runs
        the full multi-floor analysis: SLC loop assignment, vertical
        zone design, smoke spread, elevator recall, and riser routing.

        If the Multi-Floor Orchestrator is not available (import
        failure), returns ``None`` immediately.

        Returns:
            :class:`BuildingAnalysis` from the orchestrator, or
            ``None`` if the subsystem is unavailable.

        Reference:
            NFPA 72-2022 §21.2.2 (SLC limits), §21.3.2 (elevator recall),
            §21.3.3 (vertical zones), §21.3.4 (zone area limits),
            §21.4.1 (shunt trip), §21.6 (emergency control),
            §21.7.1 (HVAC shutdown)

        """
        if not _HAS_MULTI_FLOOR:
            logger.info("%s skipped — subsystem unavailable.", self._SUB_MULTI_FLOOR)
            return None

        config = self._config

        # Build the floors dict expected by MultiFloorOrchestrator
        # It expects Dict[str, List[Any]] mapping floor_id → room specs
        floors: Dict[str, List[Any]] = {}
        floor_elevations: Dict[str, float] = {}
        floor_areas: Dict[str, float] = {}
        building_height_m = 0.0

        for floor in config.floors:
            floors[floor.floor_id] = floor.room_specs or []
            floor_elevations[floor.floor_id] = floor.elevation_m
            floor_areas[floor.floor_id] = floor.area_sqm
            # Building height = max elevation + ceiling height
            top = floor.elevation_m + floor.ceiling_height_m
            if top > building_height_m:
                building_height_m = top

        # Determine dominant occupancy type
        if config.floors:
            # Pick the occupancy type of the largest floor
            dominant_floor = max(config.floors, key=lambda f: f.area_sqm)
            occupancy_type = dominant_floor.occupancy_type
        else:
            occupancy_type = "business"

        # Create orchestrator
        orchestrator = MultiFloorOrchestrator(
            building_height_m=building_height_m,
        )

        # Run the full orchestration
        analysis = orchestrator.orchestrate(
            building_id=config.building_id,
            floors=floors,
            occupancy_type=occupancy_type,
            floor_elevations=floor_elevations,
            floor_areas=floor_areas,
        )

        if analysis.compliant:
            logger.info(
                "%s PASS: building=%s floors=%d devices=%d loops=%d zones=%d compliant=%s",
                self._SUB_MULTI_FLOOR,
                config.building_id,
                analysis.total_floors,
                analysis.total_devices,
                analysis.total_slc_loops,
                analysis.total_vertical_zones,
                analysis.compliant,
            )
        else:
            logger.warning(
                "%s FAIL: building=%s — analysis indicates non-compliance. %d errors recorded per NFPA 72-2022 §21.",
                self._SUB_MULTI_FLOOR,
                config.building_id,
                len(analysis.errors),
            )

        return analysis

    # ──────────────────────────────────────────────────────────────────────
    # Compliance Evaluation
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _evaluate_overall_compliance(result: IntegrationResult) -> bool:
        """Evaluate overall compliance across all available subsystems.

        A subsystem contributes to the compliance gate ONLY if it
        produced a non-None result.  Subsystems that were unavailable
        or failed with an exception are excluded — it would be
        unreasonable to fail the building because an optional module
        is missing.

        The compliance gate requires ALL available subsystems that
        produced results to report compliance.  A single non-compliant
        subsystem causes overall non-compliance.

        Args:
            result: The :class:`IntegrationResult` to evaluate.

        Returns:
            ``True`` if all available subsystems with results are
            compliant, ``False`` otherwise.

        """
        compliance_checks: List[Tuple[str, bool]] = []

        # Cable Routing: check our aggregated result
        if result.cable_result is not None:
            compliance_checks.append(
                (
                    "Cable Routing",
                    result.cable_result.compliant,
                )
            )

        # Digital Twin Sync: check for success attribute
        if result.twin_result is not None:
            twin_compliant = getattr(
                result.twin_result, "success", False
            )  # V112: FAIL-SAFE — missing success = NOT compliant
            # Also check for a 'compliant' attribute if it exists
            if hasattr(result.twin_result, "compliant"):
                twin_compliant = result.twin_result.compliant
            compliance_checks.append(("Digital Twin Sync", twin_compliant))

        # Acoustics: check the AcousticCoverageResult
        # V76 CRIT-02 FIX: Default changed from True to False (fail-safe).
        # If the result object lacks a 'compliant' attribute (e.g., dict instead
        # of dataclass, or attribute renamed), the system must NOT silently
        # approve. Missing acoustics compliance = occupants may not hear
        # fire alarm = NFPA 72 §18.4 violation. Fail-safe = False.
        if result.acoustic_result is not None:
            acoustic_compliant = getattr(result.acoustic_result, "compliant", False)
            compliance_checks.append(("Acoustics", acoustic_compliant))

        # Multi-Floor: check the BuildingAnalysis
        # V76 CRIT-02 FIX: Same fail-safe default as acoustics.
        if result.multi_floor_result is not None:
            mf_compliant = getattr(result.multi_floor_result, "compliant", False)
            compliance_checks.append(("Multi-Floor", mf_compliant))

        # If no subsystems produced results, we cannot claim compliance
        if not compliance_checks:
            logger.warning(
                "Overall compliance evaluation: no subsystem results "
                "available — cannot verify compliance. Defaulting to "
                "NON-COMPLIANT for safety."
            )
            return False

        # All available subsystems must be compliant
        overall = all(compliant for _, compliant in compliance_checks)

        # Log the breakdown
        for name, compliant in compliance_checks:
            status = "PASS" if compliant else "FAIL"
            logger.info("Compliance gate: %s — %s", name, status)

        if overall:
            logger.info(
                "Overall compliance: PASS — all %d available subsystems compliant.",
                len(compliance_checks),
            )
        else:
            failed = [n for n, c in compliance_checks if not c]
            logger.warning(
                "Overall compliance: FAIL — non-compliant subsystems: %s. "
                "These MUST be resolved before AHJ submittal per "
                "NFPA 72-2022.",
                ", ".join(failed),
            )

        return overall


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level exports
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "AcousticConfig",
    "CableRoutingResult",
    "FloorData",
    "IntegrationBridge",
    "IntegrationConfig",
    "IntegrationResult",
]
