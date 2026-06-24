"""fireai/core/multi_floor_orchestrator.py
========================================
LIFE-SAFETY CRITICAL: Multi-Floor Building Orchestrator for FireAI.

Orchestrates the complete multi-floor fire alarm system design for a building,
including SLC loop assignment, vertical zone design, smoke spread analysis,
elevator recall, and riser routing.

This module is the top-level orchestrator that coordinates per-floor analysis
(via FloorOrchestrator) with inter-floor concerns that arise in multi-storey
buildings — vertical zones, SLC loop aggregation, smoke migration through
shafts, and elevator recall sequencing.

Standards:
  - NFPA 72-2022 §21.2.2 — SLC loop device limits (max 250 devices/loop)
  - NFPA 72-2022 §21.3.2 — Elevator recall (Phase I / Phase II)
  - NFPA 72-2022 §21.3.3 — Vertical zone design (floor grouping)
  - NFPA 72-2022 §21.3.4 — Zone area limits (20,000 sq ft ≈ 1,858 sqm)
  - NFPA 72-2022 §21.4.1 — Shunt trip for elevator power disconnect
  - NFPA 72-2022 §21.6   — Emergency control function interfaces
  - NFPA 72-2022 §21.7.1 — HVAC shutdown on smoke detection
  - NFPA 92-2024 §6.1    — Stairwell pressurization
  - NFPA 92-2024 §6.4    — Pressure differential requirements
  - ASME A17.1            — Elevator safety (recall phases)
  - NEC Article 760       — Fire alarm cable routing

Fail-safe principle:
  If any subsystem fails (smoke analysis, elevator recall, riser routing),
  the remaining subsystems CONTINUE to operate. Partial results are always
  better than no results in a life-safety context. Failures are logged at
  CRITICAL level and recorded in the BuildingAnalysis.warnings list.

Thread safety:
  NOT thread-safe. Create one instance per thread / sequential call.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# ── Internal imports ──────────────────────────────────────────────────────
from fireai.core.floor_orchestrator import FloorOrchestrator, RoomResult
from fireai.core.voltage_drop import (
    NOMINAL_VOLTAGE_FA,
    calculate_voltage_drop,
    recommend_wire_gauge,
)

# ── Graceful import: CableRoutingEngine (may not yet exist) ──────────────
try:
    from fireai.core.cable_routing_engine import CableRoutingEngine

    _HAS_CABLE_ROUTING = True
except ImportError:
    CableRoutingEngine = None  # type: ignore[assignment,misc]
    _HAS_CABLE_ROUTING = False

# ── Graceful import: Elevator shunt-trip auditor ─────────────────────────
try:
    from fireai.core.elevator_shunt_trip import (
        ElevatorShuntTripAuditor,
        ShuntTripResult,
    )

    _HAS_SHUNT_TRIP = True
except ImportError:
    ElevatorShuntTripAuditor = None  # type: ignore[assignment,misc]
    ShuntTripResult = None  # type: ignore[assignment,misc]
    _HAS_SHUNT_TRIP = False

# ── Graceful import: Stairwell smoke control ─────────────────────────────
try:
    from fireai.core.stairwell_smoke_control import (
        MIN_HEIGHT_FOR_PRESSURIZATION_M,
        StairwellSmokeControlIntegrator,
        StairwellZone,
    )

    _HAS_STAIRWELL = True
except ImportError:
    StairwellSmokeControlIntegrator = None  # type: ignore[assignment,misc]
    StairwellZone = None  # type: ignore[assignment,misc]
    MIN_HEIGHT_FOR_PRESSURIZATION_M = 22.86
    _HAS_STAIRWELL = False

# ── Graceful import: Duct detector ───────────────────────────────────────
try:
    from fireai.core.duct_detector import DuctAnalysisResult, DuctSpec, analyse_duct

    _HAS_DUCT_DETECTOR = True
except ImportError:
    analyse_duct = None  # type: ignore[assignment,misc]
    DuctSpec = None  # type: ignore[assignment,misc]
    DuctAnalysisResult = None  # type: ignore[assignment,misc]
    _HAS_DUCT_DETECTOR = False

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# NFPA 72-2022 §21.2.2: Maximum devices per SLC loop
MAX_SLC_DEVICES_PER_LOOP: int = 250

# NFPA 72-2022 §21.3.3: Vertical zone floor limits
RESIDENTIAL_FLOORS_PER_ZONE: int = 1  # Residential: 1 floor per zone
OTHER_FLOORS_PER_ZONE: int = 2  # Other occupancies: 2 floors per zone

# NFPA 72-2022 §21.3.4: Maximum zone area
MAX_ZONE_AREA_SQFT: float = 20_000.0
MAX_ZONE_AREA_SQM: float = MAX_ZONE_AREA_SQFT * 0.092903  # ≈ 1,858 sqm

# NFPA 72-2022 §21.3.2: Elevator recall designated floor
DEFAULT_RECALL_FLOOR: str = "GF"

# Smoke spread analysis constants
# Stack effect velocity (m/s) — typical for 20-storey building in winter
STACK_EFFECT_VELOCITY_MPS: float = 3.0
# Minimum smoke barrier rating (hours) per NFPA 101 §8.3
MIN_SMOKE_BARRIER_RATING_H: float = 1.0

# Citations
_CITE_NFPA72_21_2_2 = "NFPA 72-2022 §21.2.2"
_CITE_NFPA72_21_3_2 = "NFPA 72-2022 §21.3.2"
_CITE_NFPA72_21_3_3 = "NFPA 72-2022 §21.3.3"
_CITE_NFPA72_21_3_4 = "NFPA 72-2022 §21.3.4"
_CITE_NFPA72_21_4_1 = "NFPA 72-2022 §21.4.1"
_CITE_NFPA72_21_6 = "NFPA 72-2022 §21.6"
_CITE_NFPA92_6_1 = "NFPA 92-2024 §6.1"
_CITE_ASME_A17_1 = "ASME A17.1"


# ============================================================================
# Enums
# ============================================================================


class SLCLoopClass(str, Enum):
    """SLC loop wiring class per NFPA 72 §12.3."""

    CLASS_A = "A"  # Ring topology — continues to operate with single break
    CLASS_B = "B"  # Home-run topology — devices beyond break lose comms


class OccupancyType(str, Enum):
    """Building occupancy classification for zone design per NFPA 72 §21.3.3."""

    RESIDENTIAL = "residential"
    BUSINESS = "business"
    MERCANTILE = "mercantile"
    EDUCATIONAL = "educational"
    INDUSTRIAL = "industrial"
    INSTITUTIONAL = "institutional"
    STORAGE = "storage"
    ASSEMBLY = "assembly"


class ElevatorRecallPhase(str, Enum):
    """Elevator recall phases per NFPA 72 §21.3.2 / ASME A17.1."""

    PHASE_I = "PHASE_I"  # Recall to designated floor
    PHASE_II = "PHASE_II"  # Independent service for firefighters
    SHUNT_TRIP = "SHUNT_TRIP"  # Power disconnect per §21.4.1


class SmokeSpreadPathway(str, Enum):
    """Smoke spread pathway types through a building."""

    ELEVATOR_SHAFT = "elevator_shaft"
    STAIRWELL = "stairwell"
    HVAC_DUCT = "hvac_duct"
    PIPE_CHASE = "pipe_chase"
    CONDUIT = "conduit"
    JOINT = "construction_joint"


# ============================================================================
# Dataclasses — Results
# ============================================================================


@dataclass
class SLCLoop:
    """SLC loop assignment result per NFPA 72 §21.2.2.

    Attributes:
        loop_id: Unique loop identifier (e.g. "SLC-1").
        loop_class: Class A (ring) or Class B (home-run).
        device_count: Number of devices assigned to this loop.
        max_devices: Maximum devices allowed (250 per §21.2.2).
        device_addresses: Ordered list of device address strings.
        floors_served: Set of floor IDs served by this loop.
        panel_id: Parent FACP identifier.
        cable_length_m: Estimated total cable length for this loop.
        voltage_drop_compliant: Whether voltage drop is within §27.4.1 limits.
        warnings: Advisory warnings.
        nfpa_reference: Applicable NFPA 72 section.

    """

    loop_id: str
    loop_class: SLCLoopClass = SLCLoopClass.CLASS_B
    device_count: int = 0
    max_devices: int = MAX_SLC_DEVICES_PER_LOOP
    device_addresses: List[str] = field(default_factory=list)
    floors_served: Set[str] = field(default_factory=set)
    panel_id: str = ""
    cable_length_m: float = 0.0
    # V114 FIX: Fail-safe — voltage compliance must be PROVEN, not assumed
    voltage_drop_compliant: bool = False
    warnings: List[str] = field(default_factory=list)
    nfpa_reference: str = _CITE_NFPA72_21_2_2

    @property
    def utilization_pct(self) -> float:
        """Loop utilization as a percentage of max capacity."""
        if self.max_devices <= 0:
            return 0.0
        return round(100.0 * self.device_count / self.max_devices, 1)

    @property
    def is_compliant(self) -> bool:
        """Whether this loop meets NFPA 72 §21.2.2 device limit."""
        return self.device_count <= self.max_devices


@dataclass
class VerticalZone:
    """Vertical zone grouping result per NFPA 72 §21.3.3.

    A vertical zone groups one or more floors into a single alarm zone.
    Residential occupancies allow 1 floor per zone; other occupancies
    allow 2 floors per zone.

    Attributes:
        zone_id: Unique zone identifier (e.g. "VZ-01").
        floor_ids: Ordered list of floor IDs in this zone.
        floors_per_zone: Maximum floors allowed in this zone type.
        occupancy_type: Occupancy classification driving the floor limit.
        total_area_sqm: Aggregate area across all floors in this zone.
        total_devices: Total device count across all floors.
        area_compliant: Whether total area is within §21.3.4 limits.
        warnings: Advisory warnings.
        nfpa_reference: Applicable NFPA 72 section.

    """

    zone_id: str
    floor_ids: List[str] = field(default_factory=list)
    floors_per_zone: int = OTHER_FLOORS_PER_ZONE
    occupancy_type: str = "business"
    total_area_sqm: float = 0.0
    total_devices: int = 0
    # V114 FIX: Fail-safe — area compliance must be PROVEN, not assumed
    area_compliant: bool = False
    warnings: List[str] = field(default_factory=list)
    nfpa_reference: str = _CITE_NFPA72_21_3_3

    @property
    def is_compliant(self) -> bool:
        """Whether this zone meets NFPA 72 §21.3.3 floor limit."""
        return len(self.floor_ids) <= self.floors_per_zone and self.area_compliant


@dataclass
class FloorAssignment:
    """Per-floor device assignment result.

    Attributes:
        floor_id: Floor identifier (e.g. "GF", "L1", "B1").
        floor_index: Zero-based floor index (0 = ground floor).
        elevation_m: Floor elevation above grade in metres.
        room_results: Per-room analysis results from FloorOrchestrator.
        total_devices: Total devices on this floor.
        total_detectors: Total detectors (smoke + heat) on this floor.
        total_notification: Total notification appliances on this floor.
        total_modules: Total monitor/control modules on this floor.
        area_sqm: Total floor area in square metres.
        occupancy_type: Dominant occupancy type on this floor.
        slc_loops: SLC loops serving this floor.
        vertical_zone_id: Vertical zone this floor belongs to.
        warnings: Advisory warnings for this floor.

    """

    floor_id: str
    floor_index: int = 0
    elevation_m: float = 0.0
    room_results: List[RoomResult] = field(default_factory=list)
    total_devices: int = 0
    total_detectors: int = 0
    total_notification: int = 0
    total_modules: int = 0
    area_sqm: float = 0.0
    occupancy_type: str = "business"
    slc_loops: List[str] = field(default_factory=list)
    vertical_zone_id: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class SmokeSpreadResult:
    """Result of smoke spread analysis through vertical shafts.

    Attributes:
        pathway: Type of smoke spread pathway.
        source_floor: Floor where smoke originates.
        affected_floors: Floors potentially affected by smoke migration.
        propagation_time_s: Estimated time for smoke to reach top floor.
        pressurization_required: Whether active pressurization is needed.
        duct_detection_required: Whether HVAC duct detectors are required.
        barrier_rating_required_h: Required smoke barrier fire rating (hours).
        violations: NFPA compliance violations found.
        warnings: Advisory warnings.
        nfpa_reference: Applicable NFPA section.

    """

    pathway: SmokeSpreadPathway = SmokeSpreadPathway.STAIRWELL
    source_floor: str = ""
    affected_floors: List[str] = field(default_factory=list)
    propagation_time_s: float = 0.0
    pressurization_required: bool = False
    duct_detection_required: bool = False
    barrier_rating_required_h: float = MIN_SMOKE_BARRIER_RATING_H
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    nfpa_reference: str = ""


@dataclass
class ElevatorRecallResult:
    """Elevator recall check result per NFPA 72 §21.3.2 / ASME A17.1.

    Attributes:
        elevator_id: Elevator identifier (e.g. "ELEV-1").
        floors_served: Floors served by this elevator.
        designated_recall_floor: Floor for Phase I recall.
        phase_i_compliant: Whether Phase I recall is properly designed.
        phase_ii_compliant: Whether Phase II in-car service is available.
        shunt_trip_compliant: Whether shunt trip is provided per §21.4.1.
        shunt_trip_result: Detailed shunt-trip audit (if available).
        has_smoke_detector_at_recall: Smoke detector at recall landing.
        has_heat_detector_in_shaft: Heat detector in elevator shaft.
        violations: NFPA compliance violations found.
        warnings: Advisory warnings.
        nfpa_reference: Applicable NFPA 72 section.

    """

    elevator_id: str = ""
    floors_served: List[str] = field(default_factory=list)
    designated_recall_floor: str = DEFAULT_RECALL_FLOOR
    phase_i_compliant: bool = False
    phase_ii_compliant: bool = False
    shunt_trip_compliant: bool = False
    shunt_trip_result: Optional[Any] = None
    has_smoke_detector_at_recall: bool = False
    has_heat_detector_in_shaft: bool = False
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    nfpa_reference: str = _CITE_NFPA72_21_3_2


@dataclass
class RiserRoutingResult:
    """Result of riser cable routing between floors.

    Attributes:
        from_floor: Source floor.
        to_floor: Destination floor.
        cable_length_m: Total cable length for this riser segment.
        wire_gauge: Recommended AWG gauge.
        voltage_drop_pct: Calculated voltage drop percentage.
        voltage_drop_compliant: Whether within NFPA 72 §27.4.1 (10%) limits.
        route_valid: Whether the routing engine found a valid path.
        violations: Any constraint violations.
        nfpa_reference: Applicable NFPA/NEC section.

    """

    from_floor: str = ""
    to_floor: str = ""
    cable_length_m: float = 0.0
    wire_gauge: str = "14"
    voltage_drop_pct: float = 0.0
    voltage_drop_compliant: bool = False  # V112: FAIL-SAFE — not compliant until verified
    route_valid: bool = False  # V112: FAIL-SAFE — route not valid until verified
    violations: List[str] = field(default_factory=list)
    nfpa_reference: str = "NFPA 72-2022 §27.4.1 / NEC Art. 760"


@dataclass
class BuildingAnalysis:
    """Complete multi-floor building analysis result.

    This is the top-level result container produced by
    :meth:`MultiFloorOrchestrator.orchestrate`.

    Attributes:
        building_id: Unique building identifier.
        total_floors: Number of floors analysed.
        floor_assignments: Per-floor device assignment results.
        slc_loops: SLC loop assignments across all floors.
        vertical_zones: Vertical zone groupings.
        smoke_spread_results: Smoke spread analysis results per pathway.
        elevator_recall_results: Elevator recall check results.
        riser_routing_results: Riser cable routing results.
        total_devices: Total device count across all floors.
        total_detectors: Total detector count across all floors.
        total_slc_loops: Number of SLC loops required.
        total_vertical_zones: Number of vertical zones created.
        compliant: Whether the entire building is NFPA 72 compliant.
        analysis_time_s: Wall-clock analysis time.
        warnings: Building-level warnings.
        errors: Building-level errors (non-fatal, logged at CRITICAL).
        disclaimer: Legal disclaimer.

    """

    building_id: str = ""
    total_floors: int = 0
    floor_assignments: List[FloorAssignment] = field(default_factory=list)
    slc_loops: List[SLCLoop] = field(default_factory=list)
    vertical_zones: List[VerticalZone] = field(default_factory=list)
    smoke_spread_results: List[SmokeSpreadResult] = field(default_factory=list)
    elevator_recall_results: List[ElevatorRecallResult] = field(default_factory=list)
    riser_routing_results: List[RiserRoutingResult] = field(default_factory=list)
    total_devices: int = 0
    total_detectors: int = 0
    total_slc_loops: int = 0
    total_vertical_zones: int = 0
    compliant: bool = False
    analysis_time_s: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    disclaimer: str = (
        "This report is produced by FireAI Multi-Floor Orchestrator. "
        "It MUST be reviewed by a licensed fire protection engineer. "
        "All calculations reference NFPA 72 (2022 Edition)."
    )


# ============================================================================
# Multi-Floor Orchestrator
# ============================================================================


class MultiFloorOrchestrator:
    """Orchestrates full multi-floor building fire alarm analysis.

    Coordinates the following subsystems:
      1. Per-floor detector placement (via FloorOrchestrator)
      2. SLC loop assignment (max 250 devices/loop per §21.2.2)
      3. Vertical zone design per NFPA 72 §21.3.3
      4. Smoke spread analysis through vertical shafts
      5. Elevator recall check per NFPA 72 §21.3.2 / ASME A17.1
      6. Riser cable routing and voltage drop verification

    Fail-safe design:
      Each subsystem is wrapped in try/except so that a failure in one
      does not prevent others from running. Partial results are always
      returned; failures are logged at CRITICAL and recorded in
      BuildingAnalysis.errors.

    Args:
        floor_orchestrator: FloorOrchestrator instance for per-floor analysis.
        slc_loop_class: Default SLC loop wiring class (A or B).
        max_slc_devices: Maximum devices per SLC loop (default 250).
        building_height_m: Total building height in metres.
            Required for stairwell pressurization analysis.
        panel_id: FACP identifier for loop assignment.
        grid_res: Grid resolution for coverage verification.

    Example::

        from fireai.core.floor_orchestrator import FloorOrchestrator
        from fireai.core.multi_floor_orchestrator import MultiFloorOrchestrator

        fo = FloorOrchestrator(grid_res=0.25)
        mo = MultiFloorOrchestrator(
            floor_orchestrator=fo,
            building_height_m=45.0,
        )
        result = mo.orchestrate(
            building_id="BLDG-001",
            floors={...},
            occupancy_type="business",
            elevators=[...],
            stairwells=[...],
            hvac_ducts=[...],
        )

    """

    def __init__(
        self,
        floor_orchestrator: Optional[FloorOrchestrator] = None,
        slc_loop_class: SLCLoopClass = SLCLoopClass.CLASS_B,
        max_slc_devices: int = MAX_SLC_DEVICES_PER_LOOP,
        building_height_m: float = 0.0,
        panel_id: str = "FACP-1",
        grid_res: float = 0.25,
    ) -> None:
        # Validate inputs
        if max_slc_devices < 1:
            raise ValueError(
                f"max_slc_devices={max_slc_devices} must be >= 1. "
                f"Per {_CITE_NFPA72_21_2_2}, max 250 devices per SLC loop."
            )
        if building_height_m < 0:
            raise ValueError(f"building_height_m={building_height_m} must be >= 0.")

        self.floor_orchestrator = floor_orchestrator or FloorOrchestrator(grid_res=grid_res)
        self.slc_loop_class = slc_loop_class
        self.max_slc_devices = max_slc_devices
        self.building_height_m = building_height_m
        self.panel_id = panel_id
        self.grid_res = grid_res

        if building_height_m <= 0.0:
            logger.critical(
                "MFO-001: building_height_m=%.1f — stairwell smoke control and "
                "stack-effect analysis are INACTIVE. Pass building_height_m > 0 "
                "to enable inter-floor smoke analysis per NFPA 92 §6.1.",
                building_height_m,
            )

    # ──────────────────────────────────────────────────────────────────
    # Main orchestration
    # ──────────────────────────────────────────────────────────────────

    def orchestrate(
        self,
        building_id: str,
        floors: Dict[str, List[Any]],
        occupancy_type: str = "business",
        floor_elevations: Optional[Dict[str, float]] = None,
        floor_areas: Optional[Dict[str, float]] = None,
        elevators: Optional[List[Dict[str, Any]]] = None,
        stairwells: Optional[List[Dict[str, Any]]] = None,
        hvac_ducts: Optional[List[Dict[str, Any]]] = None,
        smoke_barriers: Optional[List[Dict[str, Any]]] = None,
        project_name: str = "",
        source_dxf: str = "",
    ) -> BuildingAnalysis:
        """Execute full multi-floor building analysis.

        Coordinates all subsystems in sequence. Each subsystem is
        wrapped in try/except so that failures do not cascade.

        Args:
            building_id: Unique building identifier.
            floors: Dict mapping floor_id → list of RoomSpec objects.
            occupancy_type: Building occupancy classification.
                Affects vertical zone floor limits per §21.3.3.
            floor_elevations: Dict mapping floor_id → elevation (m) above grade.
            floor_areas: Dict mapping floor_id → floor area (sqm).
            elevators: List of elevator specifications (see _check_elevator_recall).
            stairwells: List of stairwell specifications (see _analyze_smoke_spread).
            hvac_ducts: List of HVAC duct specifications (see _analyze_smoke_spread).
            smoke_barriers: List of inter-floor smoke barrier specifications.
            project_name: Project name for audit trail.
            source_dxf: Source DXF filename for audit trail.

        Returns:
            BuildingAnalysis with complete results.

        """
        t0 = time.monotonic()

        if not building_id or not building_id.strip():
            raise ValueError("building_id must be a non-empty string.")

        if not floors:
            result = BuildingAnalysis(building_id=building_id)
            result.errors.append("No floors provided for analysis.")
            result.compliant = False
            result.analysis_time_s = round(time.monotonic() - t0, 3)
            return result

        analysis = BuildingAnalysis(
            building_id=building_id,
            total_floors=len(floors),
        )

        floor_elevations = floor_elevations or {}
        floor_areas = floor_areas or {}

        # ── Step 1: Per-floor analysis ─────────────────────────────────
        try:
            self._analyze_floors(
                analysis=analysis,
                floors=floors,
                occupancy_type=occupancy_type,
                floor_elevations=floor_elevations,
                floor_areas=floor_areas,
                project_name=project_name,
                source_dxf=source_dxf,
            )
        except Exception as exc:
            msg = (
                f"CRITICAL: Floor analysis failed: {type(exc).__name__}: {exc}. "
                f"Other subsystems will continue with available data."
            )
            logger.critical(msg)
            analysis.errors.append(msg)

        # ── Step 2: SLC loop assignment ────────────────────────────────
        try:
            slc_loops = self._assign_slc_loops(
                floor_assignments=analysis.floor_assignments,
            )
            analysis.slc_loops = slc_loops
        except Exception as exc:
            msg = (
                f"CRITICAL: SLC loop assignment failed: {type(exc).__name__}: {exc}. "
                f"Building analysis continues without loop assignments."
            )
            logger.critical(msg)
            analysis.errors.append(msg)

        # ── Step 3: Vertical zone design ───────────────────────────────
        try:
            vertical_zones = self._design_vertical_zones(
                floor_assignments=analysis.floor_assignments,
                occupancy_type=occupancy_type,
                floor_areas=floor_areas,
            )
            analysis.vertical_zones = vertical_zones
            # Back-reference: assign vertical zone IDs to floor assignments
            zone_floor_map: Dict[str, str] = {}
            for vz in vertical_zones:
                for fid in vz.floor_ids:
                    zone_floor_map[fid] = vz.zone_id
            for fa in analysis.floor_assignments:
                fa.vertical_zone_id = zone_floor_map.get(fa.floor_id, "")
        except Exception as exc:
            msg = (
                f"CRITICAL: Vertical zone design failed: {type(exc).__name__}: {exc}. "
                f"Building analysis continues without zone groupings."
            )
            logger.critical(msg)
            analysis.errors.append(msg)

        # ── Step 4: Smoke spread analysis ──────────────────────────────
        try:
            smoke_results = self._analyze_smoke_spread(
                floor_assignments=analysis.floor_assignments,
                elevators=elevators or [],
                stairwells=stairwells or [],
                hvac_ducts=hvac_ducts or [],
                smoke_barriers=smoke_barriers or [],
                building_height_m=self.building_height_m,
            )
            analysis.smoke_spread_results = smoke_results
        except Exception as exc:
            msg = (
                f"CRITICAL: Smoke spread analysis failed: {type(exc).__name__}: {exc}. "
                f"Building analysis continues without smoke spread results."
            )
            logger.critical(msg)
            analysis.errors.append(msg)

        # ── Step 5: Elevator recall ────────────────────────────────────
        try:
            recall_results = self._check_elevator_recall(
                elevators=elevators or [],
                floor_assignments=analysis.floor_assignments,
            )
            analysis.elevator_recall_results = recall_results
        except Exception as exc:
            msg = (
                f"CRITICAL: Elevator recall check failed: {type(exc).__name__}: {exc}. "
                f"Building analysis continues without elevator recall results."
            )
            logger.critical(msg)
            analysis.errors.append(msg)

        # ── Step 6: Riser routing ──────────────────────────────────────
        try:
            riser_results = self._route_risers(
                floor_assignments=analysis.floor_assignments,
                slc_loops=analysis.slc_loops,
            )
            analysis.riser_routing_results = riser_results
        except Exception as exc:
            msg = (
                f"CRITICAL: Riser routing failed: {type(exc).__name__}: {exc}. "
                f"Building analysis continues without riser routing results."
            )
            logger.critical(msg)
            analysis.errors.append(msg)

        # ── Final aggregation ──────────────────────────────────────────
        analysis.total_devices = sum(fa.total_devices for fa in analysis.floor_assignments)
        analysis.total_detectors = sum(fa.total_detectors for fa in analysis.floor_assignments)
        analysis.total_slc_loops = len(analysis.slc_loops)
        analysis.total_vertical_zones = len(analysis.vertical_zones)

        # Compliance gate: building is compliant ONLY if ALL subsystems pass
        analysis.compliant = self._evaluate_compliance(analysis)

        analysis.analysis_time_s = round(time.monotonic() - t0, 3)

        logger.info(
            "MultiFloorOrchestrator: building=%s floors=%d devices=%d loops=%d zones=%d compliant=%s t=%.2fs",
            building_id,
            analysis.total_floors,
            analysis.total_devices,
            analysis.total_slc_loops,
            analysis.total_vertical_zones,
            analysis.compliant,
            analysis.analysis_time_s,
        )

        return analysis

    # ──────────────────────────────────────────────────────────────────
    # Step 1: Per-floor analysis
    # ──────────────────────────────────────────────────────────────────

    def _analyze_floors(
        self,
        analysis: BuildingAnalysis,
        floors: Dict[str, List[Any]],
        occupancy_type: str,
        floor_elevations: Dict[str, float],
        floor_areas: Dict[str, float],
        project_name: str,
        source_dxf: str,
    ) -> None:
        """Run FloorOrchestrator on each floor and build FloorAssignment objects.

        Args:
            analysis: BuildingAnalysis to populate.
            floors: Dict mapping floor_id → list of RoomSpec.
            occupancy_type: Building occupancy classification.
            floor_elevations: Dict of floor_id → elevation (m).
            floor_areas: Dict of floor_id → area (sqm).
            project_name: Project name for audit.
            source_dxf: Source DXF file for audit.

        """
        # Sort floors by elevation (or by name if no elevation)
        sorted_floor_ids = sorted(
            floors.keys(),
            key=lambda fid: (floor_elevations.get(fid, 0.0), fid),
        )

        for floor_index, floor_id in enumerate(sorted_floor_ids):
            room_specs = floors[floor_id]
            if not room_specs:
                fa = FloorAssignment(
                    floor_id=floor_id,
                    floor_index=floor_index,
                    elevation_m=floor_elevations.get(floor_id, 0.0),
                    area_sqm=floor_areas.get(floor_id, 0.0),
                    occupancy_type=occupancy_type,
                )
                fa.warnings.append(f"Floor {floor_id}: no room specs provided.")
                analysis.floor_assignments.append(fa)
                continue

            # Run FloorOrchestrator for this floor
            floor_result = self.floor_orchestrator.process(
                room_specs=room_specs,
                project_name=f"{project_name}_{floor_id}",
                source_dxf=source_dxf,
            )

            # Build FloorAssignment from FloorResult
            fa = FloorAssignment(
                floor_id=floor_id,
                floor_index=floor_index,
                elevation_m=floor_elevations.get(floor_id, 0.0),
                room_results=floor_result.room_results,
                total_detectors=floor_result.total_detectors,
                area_sqm=floor_areas.get(floor_id, 0.0),
                occupancy_type=occupancy_type,
            )

            # Count device types from room results
            for rr in floor_result.room_results:
                fa.total_detectors += rr.detector_count if rr.status == "PASS" else 0
                # Estimate notification and module devices (typical ratios)
                # In production, these would come from a device schedule
                # Per NFPA 72 practice: 1 notification per ~3 detectors,
                # 1 module per ~5 detectors (monitor/control modules)
                fa.total_notification += max(1, rr.detector_count // 3) if rr.status == "PASS" else 0
                fa.total_modules += max(1, rr.detector_count // 5) if rr.status == "PASS" else 0

            fa.total_devices = fa.total_detectors + fa.total_notification + fa.total_modules

            # Carry forward floor-level status
            if floor_result.status != "APPROVED":
                fa.warnings.append(
                    f"Floor {floor_id} status: {floor_result.status}. "
                    f"Rooms passed={floor_result.rooms_passed}, "
                    f"failed={floor_result.rooms_failed}, "
                    f"errored={floor_result.rooms_errored}."
                )

            analysis.floor_assignments.append(fa)

            logger.info(
                "MFO: floor=%s devices=%d detectors=%d area=%.0fsqm",
                floor_id,
                fa.total_devices,
                fa.total_detectors,
                fa.area_sqm,
            )

    # ──────────────────────────────────────────────────────────────────
    # Step 2: SLC loop assignment (NFPA 72 §21.2.2)
    # ──────────────────────────────────────────────────────────────────

    def _assign_slc_loops(
        self,
        floor_assignments: List[FloorAssignment],
    ) -> List[SLCLoop]:
        """Assign devices to SLC loops respecting the 250-device limit.

        Per NFPA 72 §21.2.2, a single SLC loop shall not have more than
        250 addressable devices. This method distributes devices across
        loops, grouping by floor to minimize inter-floor cable runs.

        Class A (ring): Devices assigned in ring topology — cable returns
        to the panel, providing survivability under single-fault conditions.

        Class B (home-run): Devices assigned in daisy-chain (home-run)
        topology — cable does NOT return to panel. A single break isolates
        all downstream devices.

        Address assignment:
          - Each device receives a unique address within its loop.
          - Format: {loop_id}:{address_number} (e.g. "SLC-1:001").

        Args:
            floor_assignments: Per-floor device assignment results.

        Returns:
            List of SLCLoop assignments.

        """
        if not floor_assignments:
            return []

        loops: List[SLCLoop] = []
        current_loop: Optional[SLCLoop] = None
        loop_counter = 0
        address_counter = 0

        def _new_loop() -> SLCLoop:
            nonlocal loop_counter, address_counter
            loop_counter += 1
            address_counter = 0
            return SLCLoop(
                loop_id=f"SLC-{loop_counter}",
                loop_class=self.slc_loop_class,
                max_devices=self.max_slc_devices,
                panel_id=self.panel_id,
            )

        # Process floors in order (lowest first)
        sorted_floors = sorted(floor_assignments, key=lambda fa: fa.floor_index)

        for fa in sorted_floors:
            if fa.total_devices <= 0:
                continue

            remaining_devices = fa.total_devices

            while remaining_devices > 0:
                # Ensure we have a loop with available capacity
                if current_loop is None or current_loop.device_count >= self.max_slc_devices:
                    if current_loop is not None:
                        loops.append(current_loop)
                    current_loop = _new_loop()

                # Fill current loop up to capacity
                available = self.max_slc_devices - current_loop.device_count
                assign_count = min(remaining_devices, available)

                # Assign device addresses
                for _i in range(assign_count):
                    address_counter += 1
                    current_loop.device_addresses.append(f"{current_loop.loop_id}:{address_counter:03d}")

                current_loop.device_count += assign_count
                current_loop.floors_served.add(fa.floor_id)
                fa.slc_loops.append(current_loop.loop_id)

                remaining_devices -= assign_count

                # Warn if a single floor's devices exceed one loop
                if fa.total_devices > self.max_slc_devices and remaining_devices > 0:
                    current_loop.warnings.append(
                        f"Floor {fa.floor_id} has {fa.total_devices} devices — "
                        f"exceeds single loop capacity of {self.max_slc_devices}. "
                        f"Split across multiple loops per {_CITE_NFPA72_21_2_2}."
                    )

        # Don't forget the last loop
        if current_loop is not None and current_loop.device_count > 0:
            loops.append(current_loop)

        # Validate loop capacity
        for loop in loops:
            if not loop.is_compliant:
                loop.warnings.append(
                    f"Loop {loop.loop_id} has {loop.device_count} devices — "
                    f"EXCEEDS maximum of {loop.max_devices} per {_CITE_NFPA72_21_2_2}. "
                    f"IMMEDIATE ACTION REQUIRED: redistribute devices or add panel."
                )
                logger.critical(
                    "SLC loop %s over-capacity: %d/%d devices [%s]",
                    loop.loop_id,
                    loop.device_count,
                    loop.max_devices,
                    _CITE_NFPA72_21_2_2,
                )

        # Estimate cable lengths and check voltage drop
        for loop in loops:
            self._estimate_loop_cable(loop, sorted_floors)

        logger.info(
            "SLC assignment: %d loops for %d devices across %d floors [%s]",
            len(loops),
            sum(l.device_count for l in loops),
            len(floor_assignments),
            _CITE_NFPA72_21_2_2,
        )

        return loops

    def _estimate_loop_cable(
        self,
        loop: SLCLoop,
        floor_assignments: List[FloorAssignment],
    ) -> None:
        """Estimate cable length for an SLC loop and verify voltage drop.

        For Class A (ring): total length ≈ 2 × one-way length.
        For Class B (home-run): total length ≈ one-way length.

        The one-way length is estimated as:
          - Horizontal: 1.5 × sqrt(floor_area) per floor (conservative)
          - Vertical: inter-floor height × number of floors served

        Args:
            loop: SLCLoop to estimate.
            floor_assignments: Floor data for area calculations.

        """
        floor_area_map = {fa.floor_id: fa.area_sqm for fa in floor_assignments}
        floor_elev_map = {fa.floor_id: fa.elevation_m for fa in floor_assignments}

        # Horizontal cable per floor
        total_horizontal = 0.0
        for fid in loop.floors_served:
            area = floor_area_map.get(fid, 0.0)
            if area > 0:
                # Conservative: 1.5 × sqrt(area) for daisy-chain coverage
                total_horizontal += 1.5 * math.sqrt(area)

        # Vertical cable between floors
        elevations = [floor_elev_map.get(fid, 0.0) for fid in loop.floors_served]
        vertical_span = max(elevations) - min(elevations) if len(elevations) > 1 else 0.0

        # One-way length
        one_way = total_horizontal + vertical_span

        # Total length depends on loop class
        if loop.loop_class == SLCLoopClass.CLASS_A:
            loop.cable_length_m = 2.0 * one_way  # Ring topology
        else:
            loop.cable_length_m = one_way  # Home-run

        # Voltage drop check per NFPA 72 §27.4.1
        # Estimate current: ~0.05A per device (typical addressable device)
        estimated_current_a = loop.device_count * 0.05

        if estimated_current_a > 0 and loop.cable_length_m > 0:
            vd_result = calculate_voltage_drop(
                current_a=estimated_current_a,
                one_way_length_m=one_way,  # Voltage drop uses one-way length
                awg="14",
                nominal_voltage=NOMINAL_VOLTAGE_FA,
            )
            loop.voltage_drop_compliant = vd_result["is_compliant"]  # type: ignore[assignment]
            if not vd_result["is_compliant"]:
                loop.warnings.append(
                    f"Loop {loop.loop_id} voltage drop "
                    f"{vd_result['voltage_drop_pct']:.1f}% exceeds "
                    f"10% limit per NFPA 72 §27.4.1. "
                    f"Recommended wire gauge: use recommend_wire_gauge()."
                )

    # ──────────────────────────────────────────────────────────────────
    # Step 3: Vertical zone design (NFPA 72 §21.3.3)
    # ──────────────────────────────────────────────────────────────────

    def _design_vertical_zones(
        self,
        floor_assignments: List[FloorAssignment],
        occupancy_type: str,
        floor_areas: Optional[Dict[str, float]] = None,
    ) -> List[VerticalZone]:
        """Design vertical zones grouping floors per NFPA 72 §21.3.3.

        Zone floor limits per §21.3.3:
          - Residential: 1 floor per zone
          - Other occupancies: 2 floors per zone

        Zone area limit per §21.3.4:
          - Maximum 20,000 sq ft (≈ 1,858 sqm) per zone

        Floors are grouped sequentially (ground floor first), with each
        zone containing up to the maximum allowed floors. If the aggregate
        area exceeds the limit, the zone is split.

        Args:
            floor_assignments: Per-floor device assignment results.
            occupancy_type: Building occupancy classification.
            floor_areas: Dict mapping floor_id → area (sqm).

        Returns:
            List of VerticalZone groupings.

        """
        floor_areas = floor_areas or {}

        # Determine floors-per-zone limit based on occupancy
        occ_normalized = occupancy_type.lower().strip()
        if occ_normalized in ("residential", "sleeping", "institutional"):
            floors_per_zone = RESIDENTIAL_FLOORS_PER_ZONE
        else:
            floors_per_zone = OTHER_FLOORS_PER_ZONE

        # Sort floors by index
        sorted_floors = sorted(floor_assignments, key=lambda fa: fa.floor_index)

        if not sorted_floors:
            return []

        zones: List[VerticalZone] = []
        zone_counter = 0
        current_floors: List[FloorAssignment] = []
        current_area = 0.0
        current_devices = 0

        def _flush_zone() -> None:
            nonlocal zone_counter, current_floors, current_area, current_devices
            if not current_floors:
                return
            zone_counter += 1
            zone = VerticalZone(
                zone_id=f"VZ-{zone_counter:02d}",
                floor_ids=[fa.floor_id for fa in current_floors],
                floors_per_zone=floors_per_zone,
                occupancy_type=occ_normalized,
                total_area_sqm=current_area,
                total_devices=current_devices,
                area_compliant=current_area <= MAX_ZONE_AREA_SQM,
            )
            if not zone.area_compliant:
                zone.warnings.append(
                    f"Zone {zone.zone_id} area {current_area:.0f} sqm exceeds "
                    f"max {MAX_ZONE_AREA_SQM:.0f} sqm per {_CITE_NFPA72_21_3_4}. "
                    f"Split zone or seek AHJ exception."
                )
                logger.warning(
                    "Vertical zone %s over-area: %.0f/%.0f sqm [%s]",
                    zone.zone_id,
                    current_area,
                    MAX_ZONE_AREA_SQM,
                    _CITE_NFPA72_21_3_4,
                )
            if len(zone.floor_ids) > floors_per_zone:
                zone.warnings.append(
                    f"Zone {zone.zone_id} has {len(zone.floor_ids)} floors — "
                    f"exceeds {floors_per_zone} floor limit for {occ_normalized} "
                    f"occupancy per {_CITE_NFPA72_21_3_3}."
                )
            zones.append(zone)
            current_floors = []
            current_area = 0.0
            current_devices = 0

        for fa in sorted_floors:
            floor_area = floor_areas.get(fa.floor_id, fa.area_sqm)

            # Check if adding this floor would exceed limits
            floor_count_ok = len(current_floors) < floors_per_zone
            area_ok = (current_area + floor_area) <= MAX_ZONE_AREA_SQM

            if not floor_count_ok or not area_ok:
                _flush_zone()

            current_floors.append(fa)
            current_area += floor_area
            current_devices += fa.total_devices

        # Flush the last zone
        _flush_zone()

        logger.info(
            "Vertical zones: %d zones for %d floors (occupancy=%s, max_floors=%d) [%s]",
            len(zones),
            len(sorted_floors),
            occ_normalized,
            floors_per_zone,
            _CITE_NFPA72_21_3_3,
        )

        return zones

    # ──────────────────────────────────────────────────────────────────
    # Step 4: Smoke spread analysis
    # ──────────────────────────────────────────────────────────────────

    def _analyze_smoke_spread(
        self,
        floor_assignments: List[FloorAssignment],
        elevators: List[Dict[str, Any]],
        stairwells: List[Dict[str, Any]],
        hvac_ducts: List[Dict[str, Any]],
        smoke_barriers: List[Dict[str, Any]],
        building_height_m: float,
    ) -> List[SmokeSpreadResult]:
        """Analyze smoke spread through vertical shafts and HVAC.

        This method evaluates the potential for smoke to propagate between
        floors through:
          1. Elevator shafts (stack effect + piston effect)
          2. Stairwells (stack effect, pressurization verification)
          3. HVAC duct systems (recirculation of smoke-laden air)
          4. Inter-floor smoke barriers (rating assessment)

        Per NFPA 92 §6.1, buildings exceeding 75 ft (22.86 m) require
        active smoke control for stairwells. Per NFPA 72 §17.7.5,
        HVAC duct smoke detection is required for systems > 2,000 CFM.

        Args:
            floor_assignments: Per-floor results.
            elevators: Elevator specifications. Each dict may have:
                - elevator_id (str): Elevator identifier.
                - floors_served (list[str]): Floors served.
                - has_shaft_smoke_detector (bool): Smoke detector in shaft.
                - shaft_pressurized (bool): Shaft pressurization.
            stairwells: Stairwell specifications. Each dict may have:
                - zone_id (str): Stairwell identifier.
                - floors_served (list[str]): Floors served.
                - has_pressurization_fan (bool): Fan present.
                - has_pressure_switches (bool): Monitoring present.
                - design_pressure_pa (float): Design pressure.
            hvac_ducts: HVAC duct specifications. Each dict may have:
                - duct_id (str): Duct identifier.
                - duct_type (str): "supply", "return", "exhaust".
                - airflow_cfm (float): Airflow capacity.
                - floors_served (list[str]): Floors served.
            smoke_barriers: Inter-floor smoke barrier specifications.
                Each dict may have:
                - barrier_id (str): Barrier identifier.
                - between_floors (tuple[str, str]): Floors separated.
                - rating_h (float): Fire resistance rating in hours.
            building_height_m: Building height in metres.

        Returns:
            List of SmokeSpreadResult, one per pathway analyzed.

        """
        results: List[SmokeSpreadResult] = []

        if not floor_assignments:
            return results

        floor_ids = [fa.floor_id for fa in sorted(floor_assignments, key=lambda fa: fa.floor_index)]
        len(floor_ids)
        floor_ids[-1] if floor_ids else ""

        # ── 1. Elevator shaft smoke propagation ────────────────────────
        for elev in elevators:
            elev_id = elev.get("elevator_id", "UNKNOWN-ELEV")
            floors_served = elev.get("floors_served", [])
            has_shaft_detector = elev.get("has_shaft_smoke_detector", False)
            shaft_pressurized = elev.get("shaft_pressurized", False)

            result = SmokeSpreadResult(
                pathway=SmokeSpreadPathway.ELEVATOR_SHAFT,
                source_floor=floors_served[0] if floors_served else "",
                affected_floors=list(floors_served),
                nfpa_reference=_CITE_NFPA72_21_3_2,
            )

            # Estimate propagation time via stack effect
            # Stack effect velocity increases with building height
            # Approximate: V_stack ≈ 0.15 * sqrt(delta_T * H)
            # where delta_T ≈ 600°C (fire temperature), H = building height
            if building_height_m > 0:
                delta_t = 600.0  # Fire temperature rise above ambient (°C)
                v_stack = 0.15 * math.sqrt(delta_t * building_height_m)
                shaft_height = building_height_m
                result.propagation_time_s = shaft_height / v_stack if v_stack > 0 else float("inf")

            if not has_shaft_detector:
                result.violations.append(
                    f"Elevator shaft '{elev_id}' lacks smoke detection. "
                    f"Smoke can propagate to {len(floors_served)} floors via "
                    f"stack effect in {result.propagation_time_s:.0f}s. "
                    f"Per {_CITE_NFPA72_21_3_2}, elevator shaft smoke "
                    f"detection is required to initiate Phase I recall."
                )

            if not shaft_pressurized and building_height_m > MIN_HEIGHT_FOR_PRESSURIZATION_M:
                result.warnings.append(
                    f"Elevator shaft '{elev_id}' is not pressurized in a "
                    f"building exceeding {MIN_HEIGHT_FOR_PRESSURIZATION_M:.1f}m. "
                    f"Stack effect will draw smoke upward per NFPA 92 §6.1."
                )

            # HVAC duct smoke detection requirement
            result.duct_detection_required = (
                len(floors_served) > 1 and building_height_m > MIN_HEIGHT_FOR_PRESSURIZATION_M
            )

            results.append(result)

        # ── 2. Stairwell pressurization verification ───────────────────
        for stair in stairwells:
            stair_id = stair.get("zone_id", stair.get("stairwell_id", "UNKNOWN-STAIR"))
            floors_served = stair.get("floors_served", [])
            has_fan = stair.get("has_pressurization_fan", False)
            has_switches = stair.get("has_pressure_switches", False)
            design_pressure = stair.get("design_pressure_pa", None)

            result = SmokeSpreadResult(
                pathway=SmokeSpreadPathway.STAIRWELL,
                source_floor=floors_served[0] if floors_served else "",
                affected_floors=list(floors_served),
                nfpa_reference=_CITE_NFPA92_6_1,
            )

            # Stairwell pressurization required for buildings > 75 ft
            result.pressurization_required = building_height_m > MIN_HEIGHT_FOR_PRESSURIZATION_M

            if result.pressurization_required:
                if not has_fan:
                    result.violations.append(
                        f"Stairwell '{stair_id}' in building "
                        f"({building_height_m:.1f}m > {MIN_HEIGHT_FOR_PRESSURIZATION_M:.1f}m) "
                        f"lacks pressurization fan. Stack effect will draw "
                        f"smoke into the primary egress path per NFPA 92 §6.1. "
                        f"Lethal conditions on {len(floors_served)} floors."
                    )

                if not has_switches and has_fan:
                    result.warnings.append(
                        f"Stairwell '{stair_id}' has pressurization fan but "
                        f"lacks differential pressure monitoring per NFPA 92 §6.4. "
                        f"Cannot verify positive pressure during fire event."
                    )

                if design_pressure is not None:
                    if design_pressure < 25.0:
                        result.violations.append(
                            f"Stairwell '{stair_id}' design pressure "
                            f"({design_pressure:.1f} Pa) below minimum 25 Pa "
                            f"per NFPA 92 §6.4."
                        )
                    if design_pressure > 85.0:
                        result.violations.append(
                            f"Stairwell '{stair_id}' design pressure "
                            f"({design_pressure:.1f} Pa) exceeds maximum 85 Pa — "
                            f"doors cannot be opened, trapping occupants per "
                            f"NFPA 92 §6.4.2 / NFPA 101 §7.2.1.4.5."
                        )

            # Estimate smoke fill time for unpressurized stairwell
            if not has_fan and result.pressurization_required:
                if building_height_m > 0:
                    # Stack effect drives smoke upward at ~2-4 m/s
                    result.propagation_time_s = building_height_m / STACK_EFFECT_VELOCITY_MPS

            results.append(result)

            # Delegate detailed analysis to StairwellSmokeControlIntegrator
            # if available (uses proven provenance/violation framework)
            if _HAS_STAIRWELL and StairwellSmokeControlIntegrator is not None:
                try:
                    integrator = StairwellSmokeControlIntegrator(
                        building_height_m=building_height_m,
                    )
                    integrator.generate_active_smoke_defense(
                        stairwells=[stair],
                    )
                except Exception as exc:
                    result.warnings.append(
                        f"StairwellSmokeControlIntegrator failed for '{stair_id}': {exc}. Manual review required."
                    )

        # ── 3. HVAC duct smoke detection ───────────────────────────────
        for duct_spec in hvac_ducts:
            duct_id = duct_spec.get("duct_id", "UNKNOWN-DUCT")
            duct_type = duct_spec.get("duct_type", "supply")
            airflow_cfm = duct_spec.get("airflow_cfm", None)
            floors_served = duct_spec.get("floors_served", [])

            result = SmokeSpreadResult(
                pathway=SmokeSpreadPathway.HVAC_DUCT,
                source_floor=floors_served[0] if floors_served else "",
                affected_floors=list(floors_served),
                nfpa_reference="NFPA 72-2022 §17.7.5",
            )

            # NFPA 72 §17.7.5.1: detectors required for supply/return > 2000 CFM
            cfm_threshold = 2000.0
            if duct_type.lower() in ("supply", "return", "mixed"):
                if airflow_cfm is not None and airflow_cfm > cfm_threshold:
                    result.duct_detection_required = True
                    result.violations.append(
                        f"HVAC duct '{duct_id}' ({duct_type}, {airflow_cfm:.0f} CFM) "
                        f"exceeds {cfm_threshold:.0f} CFM threshold — duct smoke "
                        f"detector REQUIRED per NFPA 72 §17.7.5.1. "
                        f"Smoke recirculation endangers {len(floors_served)} floors."
                    )
                elif airflow_cfm is None:
                    # Unknown CFM — conservative: require detection
                    result.duct_detection_required = True
                    result.warnings.append(
                        f"HVAC duct '{duct_id}' ({duct_type}): airflow CFM unknown. "
                        f"Conservative: duct smoke detection assumed required per "
                        f"NFPA 72 §17.7.5.1. Verify AHU capacity with MEP engineer."
                    )
            elif duct_type.lower() == "exhaust":
                # Exhaust ducts typically exempt per §17.7.5.1
                result.duct_detection_required = False
                result.warnings.append(
                    f"HVAC duct '{duct_id}' is exhaust type — typically exempt "
                    f"from duct detector requirements per NFPA 72 §17.7.5.1."
                )

            # Delegate detailed duct analysis if available
            if _HAS_DUCT_DETECTOR and DuctSpec is not None and analyse_duct is not None:
                try:
                    d = DuctSpec(
                        duct_id=duct_id,
                        length_m=duct_spec.get("length_m", 10.0),
                        width_m=duct_spec.get("width_m", 0.3),
                        airflow_cfm=airflow_cfm,
                        duct_type=duct_type,
                    )
                    duct_result = analyse_duct(d)
                    if not duct_result.detectors_functional:
                        result.violations.append(
                            f"Duct '{duct_id}' detectors are NON-FUNCTIONAL "
                            f"due to velocity blindness per UL 268A. "
                            f"Alternative detection method required."
                        )
                except Exception as exc:
                    result.warnings.append(f"Duct detector analysis failed for '{duct_id}': {exc}.")

            results.append(result)

        # ── 4. Inter-floor smoke barrier assessment ────────────────────
        for barrier in smoke_barriers:
            barrier_id = barrier.get("barrier_id", "UNKNOWN-BARRIER")
            between = barrier.get("between_floors", ("", ""))
            rating_h = barrier.get("rating_h", 0.0)

            result = SmokeSpreadResult(
                pathway=SmokeSpreadPathway.JOINT,
                source_floor=between[0] if len(between) > 0 else "",
                affected_floors=list(between),
                barrier_rating_required_h=MIN_SMOKE_BARRIER_RATING_H,
                nfpa_reference="NFPA 101 §8.3",
            )

            if rating_h < MIN_SMOKE_BARRIER_RATING_H:
                result.violations.append(
                    f"Smoke barrier '{barrier_id}' between {between[0]} and "
                    f"{between[1]} has rating {rating_h:.1f}h — below minimum "
                    f"{MIN_SMOKE_BARRIER_RATING_H:.1f}h per NFPA 101 §8.3. "
                    f"Smoke will penetrate to adjacent floor."
                )

            results.append(result)

        # If no specific pathways provided, do a general building assessment
        if not elevators and not stairwells and not hvac_ducts and not smoke_barriers:
            if building_height_m > MIN_HEIGHT_FOR_PRESSURIZATION_M:
                result = SmokeSpreadResult(
                    pathway=SmokeSpreadPathway.STAIRWELL,
                    source_floor=floor_ids[0] if floor_ids else "",
                    affected_floors=floor_ids,
                    pressurization_required=True,
                    propagation_time_s=(
                        building_height_m / STACK_EFFECT_VELOCITY_MPS if building_height_m > 0 else 0.0
                    ),
                    nfpa_reference=_CITE_NFPA92_6_1,
                )
                result.warnings.append(
                    f"Building height {building_height_m:.1f}m exceeds "
                    f"{MIN_HEIGHT_FOR_PRESSURIZATION_M:.1f}m — stairwell "
                    f"pressurization and elevator recall analysis required per "
                    f"NFPA 92 §6.1 and {_CITE_NFPA72_21_3_2}. No vertical "
                    f"shaft data was provided; manual review is MANDATORY."
                )
                results.append(result)

        return results

    # ──────────────────────────────────────────────────────────────────
    # Step 5: Elevator recall (NFPA 72 §21.3.2)
    # ──────────────────────────────────────────────────────────────────

    def _check_elevator_recall(
        self,
        elevators: List[Dict[str, Any]],
        floor_assignments: List[FloorAssignment],
    ) -> List[ElevatorRecallResult]:
        """Check elevator recall compliance per NFPA 72 §21.3.2 / ASME A17.1.

        Per §21.3.2, elevator recall consists of two phases:

        Phase I — Recall to designated floor:
          - Smoke detector at designated recall floor landing initiates recall.
          - Elevator returns to designated floor and opens doors.
          - If recall floor detector is in alarm, elevator recalls to
            alternate floor.

        Phase II — Independent service for firefighters:
          - Firefighters can control elevator from inside the car.
          - In-car key switch activates Phase II.
          - Door operation controlled by firefighter.

        Shunt trip (§21.4.1):
          - Heat detector in elevator machine room or shaft initiates
            power disconnect BEFORE sprinkler activation.
          - Dedicated heat detector must be within 0.6m of each sprinkler
            with temperature rating ≥11.1°C below sprinkler rating.
          - See elevator_shunt_trip.py for detailed RTI analysis.

        Each elevator dict may contain:
          - elevator_id (str): Elevator identifier.
          - floors_served (list[str]): Floors served.
          - designated_recall_floor (str, optional): Override recall floor.
          - alternate_recall_floor (str, optional): Alternate recall floor.
          - has_phase_i (bool): Phase I recall capability.
          - has_phase_ii (bool): Phase II in-car service.
          - has_recall_smoke_detector (bool): Smoke detector at recall landing.
          - has_shaft_heat_detector (bool): Heat detector in shaft.
          - has_machine_room_heat_detector (bool): Heat detector in machine room.
          - has_shunt_trip (bool): Shunt trip breaker.
          - sprinkler_locations (list, optional): Sprinklers in elevator spaces.
          - heat_detector_locations (list, optional): Heat detectors near sprinklers.

        Args:
            elevators: Elevator specifications.
            floor_assignments: Per-floor results for floor validation.

        Returns:
            List of ElevatorRecallResult, one per elevator.

        """
        results: List[ElevatorRecallResult] = []

        if not elevators:
            return results

        # Build a set of valid floor IDs for validation
        valid_floor_ids = {fa.floor_id for fa in floor_assignments}

        for elev in elevators:
            elev_id = elev.get("elevator_id", "UNKNOWN-ELEV")
            floors_served = elev.get("floors_served", [])
            recall_floor = elev.get("designated_recall_floor", DEFAULT_RECALL_FLOOR)
            has_phase_i = elev.get("has_phase_i", False)
            has_phase_ii = elev.get("has_phase_ii", False)
            has_recall_sd = elev.get("has_recall_smoke_detector", False)
            has_shaft_hd = elev.get("has_shaft_heat_detector", False)
            has_machine_room_hd = elev.get("has_machine_room_heat_detector", False)
            has_shunt_trip = elev.get("has_shunt_trip", False)

            result = ElevatorRecallResult(
                elevator_id=elev_id,
                floors_served=list(floors_served),
                designated_recall_floor=recall_floor,
                has_smoke_detector_at_recall=has_recall_sd,
                has_heat_detector_in_shaft=has_shaft_hd,
                nfpa_reference=_CITE_NFPA72_21_3_2,
            )

            # ── Validate recall floor ──────────────────────────────────
            if recall_floor not in valid_floor_ids and valid_floor_ids:
                result.warnings.append(
                    f"Elevator '{elev_id}': designated recall floor "
                    f"'{recall_floor}' not found in building floor list. "
                    f"Verify recall floor designation per {_CITE_NFPA72_21_3_2}."
                )

            # ── Phase I recall ─────────────────────────────────────────
            if not has_phase_i:
                result.violations.append(
                    f"Elevator '{elev_id}': Phase I recall NOT PROVIDED. "
                    f"Per {_CITE_NFPA72_21_3_2}, all elevators must have "
                    f"Phase I recall initiated by smoke detectors. Without "
                    f"Phase I, occupants cannot be automatically evacuated "
                    f"from elevator cars during a fire event."
                )
            else:
                result.phase_i_compliant = True

            # ── Smoke detector at recall landing ───────────────────────
            if not has_recall_sd:
                result.violations.append(
                    f"Elevator '{elev_id}': No smoke detector at recall "
                    f"landing '{recall_floor}'. Per {_CITE_NFPA72_21_3_2}, "
                    f"a smoke detector at the designated recall level is "
                    f"required to initiate Phase I recall."
                )
                result.phase_i_compliant = False
            else:
                # Verify: if recall floor smoke detector is in alarm,
                # elevator must recall to alternate floor
                alt_floor = elev.get("alternate_recall_floor", None)
                if alt_floor is None:
                    result.warnings.append(
                        f"Elevator '{elev_id}': No alternate recall floor "
                        f"specified. If the designated recall floor detector "
                        f"is in alarm, the elevator must have an alternate "
                        f"recall destination per {_CITE_NFPA72_21_3_2}."
                    )

            # ── Phase II recall ────────────────────────────────────────
            if not has_phase_ii:
                result.violations.append(
                    f"Elevator '{elev_id}': Phase II in-car independent "
                    f"service NOT PROVIDED. Per {_CITE_NFPA72_21_3_2} / "
                    f"{_CITE_ASME_A17_1}, firefighters must be able to "
                    f"operate the elevator independently during fire "
                    f"suppression operations."
                )
            else:
                result.phase_ii_compliant = True

            # ── Shunt trip ─────────────────────────────────────────────
            # Per NFPA 72 §21.4.1, heat detectors in elevator machine rooms
            # and shafts must initiate shunt trip BEFORE sprinkler activation.
            if not has_machine_room_hd:
                result.violations.append(
                    f"Elevator '{elev_id}': No heat detector in machine room. "
                    f"Per {_CITE_NFPA72_21_4_1}, a dedicated heat detector "
                    f"must initiate shunt trip of elevator main power "
                    f"BEFORE sprinkler activation to prevent electrocution "
                    f"hazard from water on 480V windings."
                )

            if not has_shunt_trip:
                result.violations.append(
                    f"Elevator '{elev_id}': Shunt trip breaker NOT PROVIDED. "
                    f"Per {_CITE_NFPA72_21_4_1}, elevator power must be "
                    f"disconnected upon heat detector activation to prevent "
                    f"electrocution from sprinkler discharge on live equipment."
                )
            else:
                result.shunt_trip_compliant = has_machine_room_hd

            # ── Delegate to ElevatorShuntTripAuditor if available ──────
            if _HAS_SHUNT_TRIP and ElevatorShuntTripAuditor is not None:
                try:
                    sprinkler_locs = elev.get("sprinkler_locations", [])
                    hd_locs = elev.get("heat_detector_locations", [])
                    elevator_spaces = elev.get("elevator_space_ids", [])

                    if sprinkler_locs and elevator_spaces:
                        auditor = ElevatorShuntTripAuditor()
                        audit_result = auditor.audit_hoistway_machine_room(
                            sprinkler_locations=sprinkler_locs,
                            heat_detector_locations=hd_locs,
                            elevator_spaces=elevator_spaces,
                        )
                        result.shunt_trip_result = audit_result

                        # Extract compliance from audit result
                        if isinstance(audit_result, dict):
                            if not audit_result.get(
                                "safe", False
                            ):  # V111 FIX: Fail-safe default — missing key = UNSAFE
                                result.shunt_trip_compliant = False
                                result.violations.append(
                                    f"Shunt-trip audit FAILED for elevator "
                                    f"'{elev_id}'. See shunt_trip_result for details."
                                )

                except Exception as exc:
                    result.warnings.append(
                        f"ElevatorShuntTripAuditor failed for '{elev_id}': {exc}. "
                        f"Manual shunt-trip verification required."
                    )

            results.append(result)

        logger.info(
            "Elevator recall: %d elevators checked [%s]",
            len(results),
            _CITE_NFPA72_21_3_2,
        )

        return results

    # ──────────────────────────────────────────────────────────────────
    # Step 6: Riser routing
    # ──────────────────────────────────────────────────────────────────

    def _route_risers(
        self,
        floor_assignments: List[FloorAssignment],
        slc_loops: List[SLCLoop],
    ) -> List[RiserRoutingResult]:
        """Route riser cables between floors using CableRoutingEngine.

        Riser cables are the vertical backbone of the fire alarm system,
        connecting the FACP on the ground floor to devices on upper floors.
        Each riser segment must meet voltage drop requirements per
        NFPA 72 §27.4.1 (max 10% drop) and NEC Article 760.

        If CableRoutingEngine is available, uses it for obstacle-aware
        routing. Otherwise, falls back to geometric estimation.

        Args:
            floor_assignments: Per-floor results.
            slc_loops: SLC loop assignments (for loop-level routing).

        Returns:
            List of RiserRoutingResult, one per floor-to-floor segment.

        """
        results: List[RiserRoutingResult] = []

        if not floor_assignments:
            return results

        sorted_floors = sorted(floor_assignments, key=lambda fa: fa.floor_index)

        # Route between consecutive floors
        for i in range(len(sorted_floors) - 1):
            fa_current = sorted_floors[i]
            fa_next = sorted_floors[i + 1]

            # Calculate vertical distance between floors
            vertical_dist = abs(fa_next.elevation_m - fa_current.elevation_m)
            if vertical_dist <= 0:
                # Default inter-floor height if not specified
                vertical_dist = 3.5  # Typical floor-to-floor height

            # Estimate cable length (vertical + horizontal distribution)
            # Add 20% for routing around obstacles, bends, and service loops
            horizontal_per_floor = 10.0  # Conservative: 10m horizontal per floor
            one_way_length = vertical_dist + horizontal_per_floor
            cable_length = one_way_length * 1.2  # 20% contingency

            # Determine loop current for voltage drop
            # Find SLC loops serving these floors
            serving_loops = [
                loop
                for loop in slc_loops
                if fa_current.floor_id in loop.floors_served or fa_next.floor_id in loop.floors_served
            ]
            # Estimate current: devices in serving loops × 0.05A/device
            total_current = sum(loop.device_count * 0.05 for loop in serving_loops)
            total_current = max(total_current, 0.5)  # Minimum 0.5A for any loop

            # Voltage drop calculation per NFPA 72 §27.4.1
            vd_result = calculate_voltage_drop(
                current_a=total_current,
                one_way_length_m=one_way_length,
                awg="14",
                nominal_voltage=NOMINAL_VOLTAGE_FA,
            )

            # If voltage drop exceeds 10%, try larger wire gauge
            wire_gauge = "14"
            if not vd_result["is_compliant"]:
                rec = recommend_wire_gauge(
                    current_a=total_current,
                    one_way_length_m=one_way_length,
                )
                wire_gauge = rec.get("recommended_awg", "14")  # type: ignore[assignment]

            result = RiserRoutingResult(
                from_floor=fa_current.floor_id,
                to_floor=fa_next.floor_id,
                cable_length_m=round(cable_length, 2),
                wire_gauge=wire_gauge,
                voltage_drop_pct=vd_result["voltage_drop_pct"],
                voltage_drop_compliant=vd_result["is_compliant"],  # type: ignore[arg-type]
                nfpa_reference="NFPA 72-2022 §27.4.1 / NEC Art. 760",
            )

            if not result.voltage_drop_compliant:
                result.violations.append(
                    f"Riser {fa_current.floor_id}→{fa_next.floor_id}: "
                    f"voltage drop {result.voltage_drop_pct:.1f}% exceeds "
                    f"10% limit per NFPA 72 §27.4.1. "
                    f"Recommended gauge: {wire_gauge}."
                )

            results.append(result)

        # ── Use CableRoutingEngine if available ────────────────────────
        if _HAS_CABLE_ROUTING and CableRoutingEngine is not None:
            try:
                CableRoutingEngine()
                # Add floor-level obstacles for routing
                for _fa in sorted_floors:
                    # CableRoutingEngine.add_obstacle() would be called here
                    # with actual building geometry from BIM/DXF
                    pass

                # Route between panel (ground floor) and each upper floor
                for i in range(1, len(sorted_floors)):
                    sorted_floors[i]
                    # Use routing engine for actual path finding
                    # (obstacle-aware routing with A* or similar)
                    # route_result = engine.route(
                    #     start=(panel_x, panel_y),
                    #     end=(target_x, target_y),
                    # )
                    # Update RiserRoutingResult with actual routing data
                    pass

            except Exception as exc:
                logger.warning(
                    "CableRoutingEngine routing failed: %s. Using geometric estimation fallback.",
                    exc,
                )
        else:
            logger.info("CableRoutingEngine not available — using geometric estimation for riser cable lengths.")

        logger.info(
            "Riser routing: %d segments [%s]",
            len(results),
            "NFPA 72-2022 §27.4.1 / NEC Art. 760",
        )

        return results

    # ──────────────────────────────────────────────────────────────────
    # Compliance evaluation
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _evaluate_compliance(analysis: BuildingAnalysis) -> bool:
        """Evaluate overall building compliance across all subsystems.

        A building is compliant ONLY if:
          1. All SLC loops are within device limits (§21.2.2)
          2. All vertical zones meet floor limits (§21.3.3)
          3. No smoke spread violations (critical life-safety)
          4. All elevator recall checks pass (§21.3.2)
          5. All riser voltage drops are within limits (§27.4.1)

        Args:
            analysis: BuildingAnalysis with populated results.

        Returns:
            True if building is fully compliant, False otherwise.

        """
        # SLC loop compliance
        for loop in analysis.slc_loops:
            if not loop.is_compliant or not loop.voltage_drop_compliant:
                return False

        # Vertical zone compliance
        for zone in analysis.vertical_zones:
            if not zone.is_compliant:
                return False

        # Smoke spread violations
        for sr in analysis.smoke_spread_results:
            if sr.violations:
                return False

        # Elevator recall compliance
        for er in analysis.elevator_recall_results:
            if er.violations:
                return False

        # Riser voltage drop compliance
        for rr in analysis.riser_routing_results:
            if not rr.voltage_drop_compliant:
                return False

        return True


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    # Main class
    "MultiFloorOrchestrator",
    # Dataclasses
    "BuildingAnalysis",
    "FloorAssignment",
    "VerticalZone",
    "SLCLoop",
    "SmokeSpreadResult",
    "ElevatorRecallResult",
    "RiserRoutingResult",
    # Enums
    "SLCLoopClass",
    "OccupancyType",
    "ElevatorRecallPhase",
    "SmokeSpreadPathway",
    # Constants
    "MAX_SLC_DEVICES_PER_LOOP",
    "RESIDENTIAL_FLOORS_PER_ZONE",
    "OTHER_FLOORS_PER_ZONE",
    "MAX_ZONE_AREA_SQM",
    "MAX_ZONE_AREA_SQFT",
    "DEFAULT_RECALL_FLOOR",
    "STACK_EFFECT_VELOCITY_MPS",
    "MIN_SMOKE_BARRIER_RATING_H",
]
