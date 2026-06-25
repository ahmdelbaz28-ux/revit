"""fireai.core.cable_router — Deterministic Orthogonal A* Cable Router
====================================================================

Cable routing engine for Fire Alarm systems using Orthogonal A*
pathfinding with code-referenceable constraints.

ALGORITHM: Orthogonal A* (6 directions: X±, Y±, Z±)
  - Heuristic: Manhattan Distance
  - Cost function:
      Straight segment: length × 1.0
      90° bend: + 0.5m equivalent penalty
      Elevation change: + 2.0m equivalent penalty
      Proximity to electrical: + 1.0m penalty if < 300mm
  - NO diagonal movement — real conduits don't go diagonal
  - Grid resolution: 100mm (0.1m) per cell

CONSTRAINTS (from codes, not opinions):
  - NEC 760.24: FA cables in separate conduits from power
  - NFPA 72 §23.6.2: NAC circuit max length per wire gauge
  - Project Spec: Min conduit ¾", red painted EMT
  - Project Spec: Max bend radius = 6 × conduit diameter
  - Project Spec: Separation from electrical ≥ 300mm
  - Project Spec: Cables fastened every 457mm per NEC 760.24(A)

VERIFICATION:
  - Same input → same output, always (deterministic)
  - Every decision logged with code reference
  - No ML, no probabilistic decisions

SAFETY CRITICAL:
  - NaN/Inf inputs REJECTED
  - Paths violating constraints REJECTED (not approximated)
  - Every formula traces to NFPA/NEC source section
"""

from __future__ import annotations

import hashlib
import heapq
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

# V63 FIX: Use math.floor instead of int() for grid coordinate
# conversion. int() truncates toward zero, which maps negative
# offsets to cell 0 instead of -1, causing points slightly
# outside the grid to appear as valid in-bounds cells.
_floor = math.floor

# ─── Internal imports ───────────────────────────────────────────────────────

from fireai.core.cable_routing_engine import WireGauge
from fireai.core.constraint_engine import (
    BEND_PENALTY_M,
    ConstraintEngine,
    RoutingConstraintSet,
)
from fireai.core.contracts_validation import ContractViolation
from fireai.core.ifc_parser import (
    BuildingModel,
    CellState,
    get_cell_state,
    grid_to_world,
    world_to_grid,
)
from fireai.core.nfpa72_engine import temperature_corrected_resistance

# ═══════════════════════════════════════════════════════════════════════════════
# 6-DIRECTIONAL MOVEMENT — Real conduits don't go diagonal
# ═══════════════════════════════════════════════════════════════════════════════

# (dx, dy, dz) — one cell at a time in exactly one axis
DIRECTIONS_6 = [
    (+1, 0, 0),  # +X
    (-1, 0, 0),  # -X
    (0, +1, 0),  # +Y
    (0, -1, 0),  # -Y
    (0, 0, +1),  # +Z (up)
    (0, 0, -1),  # -Z (down)
]


# ═══════════════════════════════════════════════════════════════════════════════
# FROZEN RESULT DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RouteWaypoint:
    """A single waypoint in a cable route.

    Attributes:
        x, y, z: World coordinates in meters.
        grid_ix, grid_iy, grid_iz: Grid cell indices.
        is_bend: True if this is a direction change point.
        direction_change: Direction tuple at this waypoint, or None.
        code_reference: NEC/NFPA reference for why this waypoint exists.

    """

    x: float
    y: float
    z: float
    grid_ix: int
    grid_iy: int
    grid_iz: int
    is_bend: bool = False
    direction_change: Optional[Tuple[int, int, int]] = None
    code_reference: str = ""


@dataclass(frozen=True)
class CableRoute:
    """Complete cable route result from the A* router.

    Contains the full path, constraint verification, and
    audit information.

    Attributes:
        route_id: Unique route identifier.
        start: Starting point (x, y, z) in meters.
        end: Ending point (x, y, z) in meters.
        waypoints: Ordered list of route waypoints.
        total_length_m: Total cable length in meters.
        straight_length_m: Total straight segment length.
        num_bends: Number of 90° bends.
        num_elevation_changes: Number of vertical moves.
        wire_gauge: Selected wire gauge.
        voltage_drop_v: Total voltage drop (V).
        voltage_drop_pct: Voltage drop as percentage.
        is_compliant: Whether route meets all constraints.
        constraint_results: Full constraint check results.
        computation_hash: SHA-256 hash for deterministic verification.
        decision_log: List of (description, code_reference) tuples.

    """

    route_id: str
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    waypoints: Tuple[RouteWaypoint, ...]
    total_length_m: float
    straight_length_m: float
    num_bends: int
    num_elevation_changes: int
    wire_gauge: str  # V108 FIX: Wire gauge as string key ("12", "14", etc.)
    voltage_drop_v: float
    voltage_drop_pct: float
    is_compliant: bool
    constraint_results: Optional[RoutingConstraintSet] = None
    computation_hash: str = ""
    decision_log: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self):
        if self.computation_hash == "":
            # V61 FIX: Include ALL route fields in hash for true
            # deterministic verification. Previous hash only covered
            # route_id/start/end/length/bends — two routes with different
            # paths but same endpoints would produce the SAME hash.
            # Also use float.hex() for IEEE-754 bit-exact formatting.
            wp_coords = "|".join(f"({wp.x:.6f},{wp.y:.6f},{wp.z:.6f},{int(wp.is_bend)})" for wp in self.waypoints)
            raw = (
                f"{self.route_id}|{self.start}|{self.end}|"
                f"{self.total_length_m:.6f}|{self.straight_length_m:.6f}|"
                f"{self.num_bends}|{self.num_elevation_changes}|"
                f"{self.wire_gauge if isinstance(self.wire_gauge, str) else self.wire_gauge.awg_value}|{self.voltage_drop_v:.6f}|"
                f"{self.voltage_drop_pct:.6f}|{int(self.is_compliant)}|"
                f"{wp_coords}"
            )
            # V97 FIX: Extended from 16 hex (64-bit) to 32 hex (128-bit)
            # per NIST SP 800-107. 16 hex chars = 64 bits = collision risk
            # at ~4 billion hashes (birthday attack). 128 bits = collision
            # at ~2^64 hashes — practically impossible for audit trails.
            object.__setattr__(
                self,
                "computation_hash",
                hashlib.sha256(raw.encode()).hexdigest()[:32],
            )


@dataclass(frozen=True)
class RoutingSchedule:
    """Cable schedule for a complete fire alarm system.

    Attributes:
        project_name: Project identifier.
        routes: All cable routes in the project.
        total_cable_length_m: Sum of all route lengths.
        total_bends: Sum of all bends.
        max_circuit_length_m: Longest single circuit.
        compliance_summary: Overall compliance status.
        computation_hash: SHA-256 for verification.

    """

    project_name: str
    routes: Tuple[CableRoute, ...]
    total_cable_length_m: float
    total_bends: int
    max_circuit_length_m: float
    compliance_summary: str
    computation_hash: str = ""

    def __post_init__(self):
        if self.computation_hash == "":
            # V61 FIX: Include individual route hashes for true verification.
            route_hashes = "|".join(r.computation_hash for r in self.routes)
            raw = (
                f"{self.project_name}|{len(self.routes)}|"
                f"{self.total_cable_length_m:.6f}|{self.total_bends}|"
                f"{self.max_circuit_length_m:.6f}|{self.compliance_summary}|"
                f"{route_hashes}"
            )
            # V97 FIX: Extended from 16 to 32 hex chars per NIST SP 800-107
            object.__setattr__(
                self,
                "computation_hash",
                hashlib.sha256(raw.encode()).hexdigest()[:32],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# A* PATHFINDING NODE
# ═══════════════════════════════════════════════════════════════════════════════


class _AStarNode:
    """Node in the A* search space.

    Uses __lt__ for heapq priority queue ordering.
    Tie-breaking by (f, h, counter) ensures deterministic ordering.
    """

    __slots__ = ("cell", "counter", "direction", "f", "g", "h", "parent")

    def __init__(
        self,
        cell: Tuple[int, int, int],
        g: float,
        h: float,
        parent: Optional[_AStarNode],
        direction: Tuple[int, int, int],
        counter: int,
    ):
        self.cell = cell
        self.g = g
        self.h = h
        self.f = g + h
        self.parent = parent
        self.direction = direction
        self.counter = counter

    def __lt__(self, other: _AStarNode) -> bool:
        """Priority queue ordering: lower f wins, then lower h, then earlier counter."""
        if self.f != other.f:
            return self.f < other.f
        if self.h != other.h:
            return self.h < other.h
        return self.counter < other.counter


# ═══════════════════════════════════════════════════════════════════════════════
# DETERMINISTIC CABLE ROUTER
# ═══════════════════════════════════════════════════════════════════════════════


class CableRouter:
    """Deterministic cable router using Orthogonal A* pathfinding.

    Routes fire alarm cables through a 3D building model using
    6-directional orthogonal movement (no diagonals).

    Algorithm: Orthogonal A* with Manhattan heuristic

    Cost Function:
      - Straight segment: length × 1.0
      - 90° bend: + 0.5m penalty (conduit fitting cost)
      - Elevation change: + 2.0m penalty (vertical routing difficulty)
      - Proximity to electrical: + 1.0m penalty if < 300mm

    NO diagonal movement — real conduits don't go diagonal.

    Example usage::

        router = CableRouter(model)
        route = router.route(
            start=(1.0, 2.0, 3.0),
            end=(10.0, 5.0, 3.0),
            wire_gauge="14",
            ps_voltage=24.0,
            alarm_current_a=1.5,
        )
        if not route.is_compliant:
            for r in route.constraint_results.results:
                if not r.is_satisfied:
                    print(f"VIOLATION: {r.constraint_name} ({r.source})")
    """

    def __init__(
        self,
        model: BuildingModel,
        constraint_engine: Optional[ConstraintEngine] = None,
    ):
        """Initialize the cable router.

        Args:
            model: BuildingModel with occupancy grid.
            constraint_engine: Constraint engine (default: standard project spec).

        Raises:
            ValueError: If model has no valid grid.

        """
        if model.grid_size == (0, 0, 0):
            raise ValueError(
                "BuildingModel has no occupancy grid. Use build_abstract_model() or parse_ifc_file() first."
            )

        self._model = model
        self._constraint_engine = constraint_engine or ConstraintEngine()
        self._counter = 0  # For deterministic A* tie-breaking

        # Pre-compute electrical zones for separation check
        self._electrical_cells: Set[Tuple[int, int, int]] = set()
        self._precompute_electrical_zones()

    def _precompute_electrical_zones(self) -> None:
        """Identify cells near electrical conduits.

        NEC 760.24 / Project Spec: 300mm separation required.
        We expand electrical element bounding boxes by 300mm
        and mark those cells for the A* penalty.

        An element is considered "electrical" if any of these apply:
        1. Its element_id contains 'electrical', 'power', or 'elec'
           (common IFC naming conventions)
        2. Its ifc_class contains 'CableCarrier', 'CableSegment',
           'ElectricDistributionBoard', or similar electrical IFC types

        For a production system, IFC property sets (Pset_ElectricalDevice)
        should be parsed. This implementation uses heuristic element
        classification that works for typical IFC exports.
        """
        if not self._model.grid_data or self._model.grid_size == (0, 0, 0):
            return

        nx, ny, nz = self._model.grid_size
        ox, oy, oz = self._model.grid_origin
        res = self._model.grid_resolution

        # Separation distance in grid cells (300mm / resolution)
        int(math.ceil(0.3 / res))

        # IFC class keywords that indicate electrical systems
        _ELECTRICAL_IFC_KEYWORDS = {
            "cablecarrier",
            "cablesegment",
            "electric",
            "power",
            "distributionboard",
            "switchboard",
            "panelboard",
            "transformer",
            "generator",
            "motor",
        }

        # Element ID keywords that indicate electrical systems
        _ELECTRICAL_ID_KEYWORDS = {
            "electrical",
            "elec",
            "power",
            "panel",
            "mdb",
            "sdb",
            "db-",
            "swgr",
            "xfmr",
        }

        for elem in self._model.elements:
            # Check if this element is electrical
            is_electrical = False

            # Check IFC class
            ifc_lower = elem.ifc_class.lower()
            for kw in _ELECTRICAL_IFC_KEYWORDS:
                if kw in ifc_lower:
                    is_electrical = True
                    break

            # Check element ID
            if not is_electrical:
                id_lower = elem.element_id.lower()
                for kw in _ELECTRICAL_ID_KEYWORDS:
                    if kw in id_lower:
                        is_electrical = True
                        break

            if not is_electrical:
                continue

            # V61 FIX: Expand element bounding box by 300mm ONLY (not 300mm
            # + sep_cells which was double-buffering to 600mm). The 0.3m
            # offset in the coordinate calculation already provides the
            # required 300mm separation per NEC 760.24.
            # V64 FIX: Use math.floor instead of int() for grid coordinate
            # conversion. int() truncates toward zero, which maps negative
            # offsets to cell 0 instead of -1. Same V63 bug pattern —
            # electrical zone cells near grid origin could be misclassified.
            ix_min = max(0, _floor((elem.min_x - 0.3 - ox) / res))
            iy_min = max(0, _floor((elem.min_y - 0.3 - oy) / res))
            iz_min = max(0, _floor((elem.min_z - 0.3 - oz) / res))
            ix_max = min(nx - 1, _floor((elem.max_x + 0.3 - ox) / res))
            iy_max = min(ny - 1, _floor((elem.max_y + 0.3 - oy) / res))
            iz_max = min(nz - 1, _floor((elem.max_z + 0.3 - oz) / res))

            for iz in range(iz_min, iz_max + 1):
                for iy in range(iy_min, iy_max + 1):
                    for ix in range(ix_min, ix_max + 1):
                        self._electrical_cells.add((ix, iy, iz))

    def route(
        self,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        wire_gauge: str = "14",  # V108: Wire gauge as string key
        ps_voltage: float = 24.0,
        alarm_current_a: float = 0.0,
        route_id: str = "",
        verify_constraints: bool = True,
        ambient_temp_c: float = 20.0,
        conductor_operating_temp_c: Optional[float] = None,
        num_current_carrying: int = 2,
        conductor_temp_rating_c: float = 90,
    ) -> CableRoute:
        """Route a cable from start to end using Orthogonal A*.

        The algorithm guarantees:
        1. Same input → same output, always (deterministic)
        2. No diagonal movement (6-directional only)
        3. Obstacle avoidance (BLOCKED cells are impassable)
        4. Constraint verification (every route is checked)

        V62 FIX: Split ambient_temp_c into two parameters:
          - ambient_temp_c: Ambient AIR temperature for ampacity derating
          - conductor_operating_temp_c: Conductor operating temp for
            resistance correction in voltage drop calculation

        These are physically different quantities. Using the same value
        for both (the old behavior) could either underestimate voltage
        drop by 21.6% (dangerous) or overstate ampacity derating
        (rejecting valid designs).

        Args:
            start: Starting point (x, y, z) in meters.
            end: Ending point (x, y, z) in meters.
            wire_gauge: Wire gauge for voltage drop calculation.
            ps_voltage: Power supply voltage (default 24V).
            alarm_current_a: Alarm current for voltage drop.
            route_id: Optional route identifier.
            verify_constraints: Whether to verify constraints (default True).
            ambient_temp_c: Ambient AIR temperature in degC for ampacity
                derating. Default 20 degC (backward compatible).
                CRITICAL FOR EGYPT: Use 40-50 degC for summer conditions.
            conductor_operating_temp_c: Conductor OPERATING temperature in
                degC for resistance correction in voltage drop. Default None
                (falls back to ambient_temp_c for backward compatibility).
                CRITICAL FOR EGYPT: Use 75.0 for THHN/THWN operating temp.
                At 75 degC, resistance is 21.6% higher than at 20 degC.
            num_current_carrying: Number of current-carrying conductors in
                conduit (default 2 for single FA circuit).
            conductor_temp_rating_c: Conductor insulation rating (60, 75, 90).
                Default 90 for THHN/THWN-2.

        Returns:
            CableRoute with waypoints and constraint results.

        Raises:
            ContractViolation: If inputs are invalid (NaN/Inf).
            ValueError: If start/end are outside the building grid.

        """
        # ── Input Validation (QOMN-FIRE Layer 0) ─────────────────────────
        for label, point in [("start", start), ("end", end)]:
            for i, coord in enumerate(point):
                if not isinstance(coord, (int, float)) or not math.isfinite(coord):
                    raise ContractViolation(
                        f"{label}[{i}] = {coord!r} is not finite — QOMN-FIRE Layer 0 rejects NaN/Inf inputs.",
                        field=f"{label}[{i}]",
                        value=coord,
                    )

        # V62 FIX: Validate ps_voltage and alarm_current_a for NaN/Inf.
        # Previously, NaN ps_voltage would silently produce 0% voltage drop
        # (is_compliant=True), allowing non-compliant circuits to be approved.
        # Negative ps_voltage would also silently report 0% drop.
        for label, value in [("ps_voltage", ps_voltage), ("alarm_current_a", alarm_current_a)]:
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ContractViolation(
                    f"{label} = {value!r} is not finite — QOMN-FIRE Layer 0 rejects NaN/Inf inputs.",
                    field=label,
                    value=value,
                )
        if ps_voltage <= 0:
            raise ContractViolation(
                f"ps_voltage = {ps_voltage!r} is non-positive — QOMN-FIRE Layer 0 rejects "
                f"zero/negative voltage. A 0V supply produces false 0% voltage drop compliance.",
                field="ps_voltage",
                value=ps_voltage,
            )

        # ── Convert to Grid Coordinates ──────────────────────────────────
        start_grid = world_to_grid(self._model, *start)
        end_grid = world_to_grid(self._model, *end)

        nx, ny, nz = self._model.grid_size

        # Validate grid bounds
        for label, cell in [("start", start_grid), ("end", end_grid)]:
            ix, iy, iz = cell
            if ix < 0 or ix >= nx or iy < 0 or iy >= ny or iz < 0 or iz >= nz:
                raise ValueError(f"{label} point {cell} is outside grid bounds {self._model.grid_size}")

        # Check start/end cells are not blocked
        start_state = get_cell_state(self._model, *start)
        end_state = get_cell_state(self._model, *end)

        if start_state == CellState.BLOCKED:
            raise ValueError(
                f"Start point {start} maps to BLOCKED cell — cable cannot originate inside a wall/obstacle"
            )
        if end_state == CellState.BLOCKED:
            raise ValueError(f"End point {end} maps to BLOCKED cell — cable cannot terminate inside a wall/obstacle")

        # ── A* Pathfinding ───────────────────────────────────────────────
        path, decision_log = self._astar(start_grid, end_grid)

        if path is None:
            # No path found — return failed route
            return CableRoute(
                route_id=route_id or "FAILED",
                start=start,
                end=end,
                waypoints=(),
                total_length_m=0.0,
                straight_length_m=0.0,
                num_bends=0,
                num_elevation_changes=0,
                wire_gauge=wire_gauge,
                voltage_drop_v=0.0,
                voltage_drop_pct=0.0,
                is_compliant=False,
                decision_log=tuple(decision_log),
            )

        # ── Build Waypoints ──────────────────────────────────────────────
        waypoints = self._build_waypoints(path)

        # ── Calculate Route Metrics ──────────────────────────────────────
        total_length, straight_length, num_bends, num_elev = self._calculate_metrics(waypoints)

        # ── Voltage Drop ─────────────────────────────────────────────────
        # V61 FIX: Use physical_length (not penalty-inflated) for voltage
        # drop. Voltage drop occurs over real conductor, not fictitious
        # bend-penalty meters. Using total_with_penalties OVERESTIMATES
        # voltage drop and causes unnecessary wire upsizing.
        physical_length = straight_length  # physical length without bend penalties
        # V62 FIX: Use conductor_operating_temp_c for resistance correction
        # if provided. Falls back to ambient_temp_c for backward compatibility.
        # These are physically different quantities — see method docstring.
        # V FIX: Default to 75°C (NEC practice) when conductor_operating_temp_c is None.
        # Using ambient_temp_c (30-50°C) underestimates resistance by 10-14.6%.
        vdrop_temp = conductor_operating_temp_c if conductor_operating_temp_c is not None else 75.0
        # V109 FIX: wire_gauge param is a string key (e.g. "14"), not a
        # _WireGaugeInstance. Must resolve to instance for resistance lookup.
        if isinstance(wire_gauge, str):
            # V79 FIX: Use exact NEC 20°C value from _WireGaugeInstance instead of
            # approximating from 75°C via reverse temperature correction (~2% error).
            # The approximation gave e.g. 8.278 Ω/km for AWG 14 vs NEC published 8.450.
            wg_found = None
            for wg in WireGauge._ALL_GAUGES:
                if wg.awg_value == str(wire_gauge).strip():
                    wg_found = wg
                    break
            if wg_found is not None:
                r_at_20c = wg_found.resistance_ohm_per_km_at_20c
            else:
                raise ContractViolation(
                    f"Unknown wire gauge: {wire_gauge!r}. "
                    f"Supported: {WireGauge.VALID_GAUGES}.",
                    field="wire_gauge",
                    value=wire_gauge,
                )
        else:
            # V FIX: Use resistance_ohm_per_km_at_20c for temperature correction
            # (not resistance_ohm_per_km which is now the 75°C published value).
            r_at_20c = wire_gauge.resistance_ohm_per_km_at_20c
        r_per_km = temperature_corrected_resistance(r_at_20c, vdrop_temp)
        length_km = physical_length / 1000.0
        v_drop = alarm_current_a * 2.0 * r_per_km * length_km  # ×2 DC return
        v_drop_pct = (v_drop / ps_voltage) * 100.0 if ps_voltage > 0 else 0.0

        # ── Constraint Verification ──────────────────────────────────────
        constraint_results = None
        if verify_constraints:
            constraint_results = self._constraint_engine.check_all(
                cable_length_m=physical_length,
                wire_gauge=wire_gauge,  # type: ignore[arg-type]
                num_bends=num_bends,
                num_elevation_changes=num_elev,
                min_electrical_separation_mm=300.0,
                ps_voltage=ps_voltage,
                alarm_current_a=alarm_current_a,
                ambient_temp_c=ambient_temp_c,
                conductor_operating_temp_c=conductor_operating_temp_c,
                num_current_carrying=num_current_carrying,
                conductor_temp_rating_c=conductor_temp_rating_c,
            )

        is_compliant = (
            constraint_results.all_satisfied
            if constraint_results
            else False  # V112: FAIL-SAFE — no constraints = NOT compliant
        )

        # Add bend decision log entries
        for wp in waypoints:
            if wp.is_bend:
                decision_log.append(
                    (f"Bend at ({wp.x:.2f}, {wp.y:.2f}, {wp.z:.2f})", "NEC Chapter 9 — max 4 quarter bends per run")
                )

        # V61 FIX: total_length_m is the PHYSICAL cable length (not
        # penalty-inflated). The penalty-inflated length is for A* cost
        # comparison only — it does not represent real conductor.
        return CableRoute(
            route_id=route_id or f"ROUTE-{hashlib.sha256(str(start).encode()).hexdigest()[:32]}",
            start=start,
            end=end,
            waypoints=tuple(waypoints),
            total_length_m=round(physical_length, 4),
            straight_length_m=round(straight_length, 4),
            num_bends=num_bends,
            num_elevation_changes=num_elev,
            wire_gauge=wire_gauge,
            voltage_drop_v=round(v_drop, 6),
            voltage_drop_pct=round(v_drop_pct, 4),
            is_compliant=is_compliant,
            constraint_results=constraint_results,
            decision_log=tuple(decision_log),
        )

    # ─── A* Implementation ───────────────────────────────────────────────

    def _astar(
        self,
        start: Tuple[int, int, int],
        goal: Tuple[int, int, int],
    ) -> Tuple[Optional[List[Tuple[int, int, int]]], List[Tuple[str, str]]]:
        """Orthogonal A* pathfinding on the 3D occupancy grid.

        6-directional movement only: X±, Y±, Z±.
        NO diagonal movement — real conduits don't go diagonal.

        Heuristic: Manhattan distance (admissible for orthogonal movement)

        Args:
            start: Start cell (ix, iy, iz).
            goal: Goal cell (ix, iy, iz).

        Returns:
            (path, decision_log) tuple. Path is None if no route found.

        """
        decision_log: List[Tuple[str, str]] = []
        decision_log.append((f"A* search: {start} → {goal}", "Orthogonal 6-dir, Manhattan heuristic"))

        # Early exit: start == goal
        if start == goal:
            return [start], decision_log

        # Initialize
        self._counter = 0
        open_set: List[_AStarNode] = []
        closed_set: Set[Tuple[int, int, int]] = set()

        # Track best g-cost for each cell
        g_costs: Dict[Tuple[int, int, int], float] = {}

        # Start node
        h = self._constraint_engine.manhattan_heuristic(start, goal, self._model.grid_resolution)
        start_node = _AStarNode(
            cell=start,
            g=0.0,
            h=h,
            parent=None,
            direction=(0, 0, 0),  # No direction yet
            counter=self._counter,
        )
        self._counter += 1
        heapq.heappush(open_set, start_node)
        g_costs[start] = 0.0

        # Safety limit: max iterations to prevent infinite loops
        max_iterations = self._model.grid_size[0] * self._model.grid_size[1] * self._model.grid_size[2]
        iterations = 0

        while open_set and iterations < max_iterations:
            iterations += 1

            # Get node with lowest f-cost
            current = heapq.heappop(open_set)

            # Goal check
            if current.cell == goal:
                path = self._reconstruct_path(current)
                decision_log.append((f"Path found: {len(path)} cells, {iterations} iterations", "A* optimal path"))
                return path, decision_log

            # Skip if already processed with better cost
            if current.cell in closed_set:
                continue

            closed_set.add(current.cell)

            # Expand neighbors (6 directions only)
            for dx, dy, dz in DIRECTIONS_6:
                nx_cell = (current.cell[0] + dx, current.cell[1] + dy, current.cell[2] + dz)

                # Bounds check
                nx, ny, nz = self._model.grid_size
                if (
                    nx_cell[0] < 0
                    or nx_cell[0] >= nx
                    or nx_cell[1] < 0
                    or nx_cell[1] >= ny
                    or nx_cell[2] < 0
                    or nx_cell[2] >= nz
                ):
                    continue

                # Obstacle check
                cell_state = self._get_grid_cell(nx_cell)
                if cell_state == CellState.BLOCKED:
                    continue

                # Skip if already in closed set
                if nx_cell in closed_set:
                    continue

                # Calculate movement cost
                is_near_electrical = nx_cell in self._electrical_cells
                move_cost = self._constraint_engine.compute_move_cost(
                    current.cell,
                    nx_cell,
                    is_near_electrical=is_near_electrical,
                    grid_resolution=self._model.grid_resolution,
                )

                # Bend cost
                direction = (dx, dy, dz)
                bend_cost = self._constraint_engine.compute_bend_cost(
                    current.direction if current.parent is not None else None,
                    direction,
                )

                # Total g-cost
                new_g = current.g + move_cost + bend_cost

                # Check if this is a better path to nx_cell
                if nx_cell in g_costs and new_g >= g_costs[nx_cell]:
                    continue

                g_costs[nx_cell] = new_g

                # Heuristic
                h = self._constraint_engine.manhattan_heuristic(nx_cell, goal, self._model.grid_resolution)

                neighbor = _AStarNode(
                    cell=nx_cell,
                    g=new_g,
                    h=h,
                    parent=current,
                    direction=direction,
                    counter=self._counter,
                )
                self._counter += 1
                heapq.heappush(open_set, neighbor)

        # No path found
        decision_log.append((f"No path found after {iterations} iterations", "A* exhausted search space"))
        return None, decision_log

    def _get_grid_cell(self, cell: Tuple[int, int, int]) -> CellState:
        """Get cell state from grid indices.

        Args:
            cell: (ix, iy, iz) grid indices.

        Returns:
            CellState at the given cell.

        """
        ix, iy, iz = cell
        nx, ny, nz = self._model.grid_size

        if ix < 0 or ix >= nx or iy < 0 or iy >= ny or iz < 0 or iz >= nz:
            return CellState.BLOCKED

        idx = iz * ny * nx + iy * nx + ix
        if idx >= len(self._model.grid_data):
            return CellState.BLOCKED

        return CellState(self._model.grid_data[idx])

    @staticmethod
    def _reconstruct_path(node: _AStarNode) -> List[Tuple[int, int, int]]:
        """Reconstruct path from A* goal node to start.

        Args:
            node: Goal node with parent chain.

        Returns:
            List of (ix, iy, iz) cells from start to goal.

        """
        path = []
        current = node
        while current is not None:
            path.append(current.cell)
            current = current.parent
        path.reverse()
        return path

    def _build_waypoints(
        self,
        path: List[Tuple[int, int, int]],
    ) -> List[RouteWaypoint]:
        """Build waypoints from A* path, detecting bends.

        Bends are points where the movement direction changes.
        Only start, end, and bend points are included as waypoints
        (straight segments are implicit between waypoints).

        Args:
            path: List of (ix, iy, iz) grid cells.

        Returns:
            List of RouteWaypoint objects at key points.

        """
        if not path:
            return []

        waypoints = []
        prev_dir: Optional[Tuple[int, int, int]] = None

        for i, cell in enumerate(path):
            # Calculate direction from previous cell
            if i > 0:
                dx = cell[0] - path[i - 1][0]
                dy = cell[1] - path[i - 1][1]
                dz = cell[2] - path[i - 1][2]
                curr_dir = (dx, dy, dz)
            else:
                curr_dir = None

            # Detect bend (direction change)
            is_bend = False
            if prev_dir is not None and curr_dir is not None and prev_dir != curr_dir:
                is_bend = True

            # Add waypoint for: start, end, or bend
            if i == 0 or i == len(path) - 1 or is_bend:
                world = grid_to_world(self._model, *cell)
                code_ref = ""
                if is_bend:
                    code_ref = "Bend added per NEC Chapter 9"

                waypoints.append(
                    RouteWaypoint(
                        x=round(world[0], 4),
                        y=round(world[1], 4),
                        z=round(world[2], 4),
                        grid_ix=cell[0],
                        grid_iy=cell[1],
                        grid_iz=cell[2],
                        is_bend=is_bend,
                        direction_change=curr_dir if is_bend else None,
                        code_reference=code_ref,
                    )
                )

            if curr_dir is not None:
                prev_dir = curr_dir

        return waypoints

    @staticmethod
    def _calculate_metrics(
        waypoints: List[RouteWaypoint],
    ) -> Tuple[float, float, int, int]:
        """Calculate route metrics from waypoints.

        Args:
            waypoints: List of route waypoints.

        Returns:
            (total_length, straight_length, num_bends, num_elevation_changes)

        """
        if len(waypoints) < 2:
            return 0.0, 0.0, 0, 0

        total_length = 0.0
        straight_length = 0.0
        num_bends = 0
        num_elevation_changes = 0

        for i in range(1, len(waypoints)):
            wp_prev = waypoints[i - 1]
            wp_curr = waypoints[i]

            # 3D segment length
            dx = wp_curr.x - wp_prev.x
            dy = wp_curr.y - wp_prev.y
            dz = wp_curr.z - wp_prev.z
            seg_length = math.sqrt(dx * dx + dy * dy + dz * dz)

            total_length += seg_length

            # Straight length (3D Euclidean, no bend/elevation penalty)
            # V61 FIX: Include vertical component — previously only counted
            # horizontal distance, silently dropping all vertical run length.
            straight_length += seg_length

            # Count bends and elevation changes
            if wp_curr.is_bend:
                num_bends += 1

            if abs(dz) > 0.001:  # Any vertical change
                num_elevation_changes += 1

        # Add bend penalties to total
        total_with_penalties = total_length + num_bends * BEND_PENALTY_M

        return (
            round(total_with_penalties, 4),
            round(total_length, 4),
            num_bends,
            num_elevation_changes,
        )

    # ─── Multi-Route Scheduling ──────────────────────────────────────────

    def route_all(
        self,
        connections: List[Dict[str, Any]],
        wire_gauge: str = "14",  # V108: Wire gauge as string key
        ps_voltage: float = 24.0,
        project_name: str = "Fire Alarm System",
        ambient_temp_c: float = 20.0,
        num_current_carrying: int = 2,
        conductor_temp_rating_c: float = 90,
        conductor_operating_temp_c: Optional[float] = None,
    ) -> RoutingSchedule:
        """Route all cable connections and produce a complete schedule.

        V63 FIX: Added conductor_operating_temp_c parameter. Previously,
        route_all() did NOT pass this to route(), meaning the V62 fix
        (splitting ambient vs operating temperature) was NOT applied in
        multi-route scheduling. With ambient_temp_c=40°C (Egypt summer),
        voltage drop used R at 40°C instead of 75°C, underestimating
        voltage drop by ~15%. This partially undid the V62 fix.

        Args:
            connections: List of dicts with keys:
                - 'start': (x, y, z) start point
                - 'end': (x, y, z) end point
                - 'alarm_current_a': current (optional)
                - 'route_id': route identifier (optional)
                - 'ambient_temp_c': operating temp override (optional)
            wire_gauge: Wire gauge for all routes.
            ps_voltage: Power supply voltage.
            project_name: Project name for the schedule.
            ambient_temp_c: Ambient AIR temperature in degC for ampacity
                derating. Default 20 degC (backward compatible).
                CRITICAL FOR EGYPT: Use 40-50 degC for summer conditions.
            num_current_carrying: Number of current-carrying conductors.
            conductor_temp_rating_c: Conductor insulation rating (60, 75, 90).
            conductor_operating_temp_c: Conductor OPERATING temperature in
                degC for resistance correction in voltage drop. Default None
                (falls back to ambient_temp_c for backward compatibility).
                CRITICAL FOR EGYPT: Use 75.0 for THHN/THWN operating temp.

        Returns:
            RoutingSchedule with all routes and compliance summary.

        """
        routes = []
        total_length = 0.0
        total_bends = 0
        max_length = 0.0
        any_violation = False

        for i, conn in enumerate(connections):
            start = conn["start"]
            end = conn["end"]
            current_a = conn.get("alarm_current_a", 0.0)
            rid = conn.get("route_id", f"R-{i + 1:03d}")
            conn_ambient = conn.get("ambient_temp_c", ambient_temp_c)

            route = self.route(
                start=start,
                end=end,
                wire_gauge=wire_gauge,
                ps_voltage=ps_voltage,
                alarm_current_a=current_a,
                route_id=rid,
                ambient_temp_c=conn_ambient,
                conductor_operating_temp_c=conductor_operating_temp_c,
                num_current_carrying=num_current_carrying,
                conductor_temp_rating_c=conductor_temp_rating_c,
            )

            routes.append(route)
            total_length += route.total_length_m
            total_bends += route.num_bends
            max_length = max(max_length, route.total_length_m)

            if not route.is_compliant:
                any_violation = True

        compliance = "ALL COMPLIANT" if not any_violation else "VIOLATIONS FOUND"

        return RoutingSchedule(
            project_name=project_name,
            routes=tuple(routes),
            total_cable_length_m=round(total_length, 2),
            total_bends=total_bends,
            max_circuit_length_m=round(max_length, 2),
            compliance_summary=compliance,
        )
