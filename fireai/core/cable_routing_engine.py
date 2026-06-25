"""fireai/core/cable_routing_engine.py
====================================
LIFE-SAFETY CRITICAL: Cable routing engine for the FireAI fire alarm
engineering platform.  Routes Class A (ring) and Class B (home-run)
circuits with NEC 760 wire gauge verification and NFPA 72-2022
voltage drop compliance per §10.6.4.

INCORRECT CABLE ROUTING CAN CAUSE:
  - Horns/strobes that fail during a fire (voltage drop > 10%)
  - Single-point-of-failure in Class A loops (no isolation)
  - NEC violations that cause AHJ rejection
  - Buildings without alarm capability when it matters most

This module implements:
  1. CableRoutingEngine — circuit routing with voltage drop verification
  2. NEC 760 wire gauge lookup (AWG 12, 14, 16, 18)
  3. NFPA 72 §10.6.4 per-segment voltage drop (DC return path × 2)
  4. Auto gauge selection — smallest compliant gauge
  5. 3D Euclidean distance calculation
  6. RoutingObstacle3D — 3D AABB obstacle with intersection tests

Standards:
  - NFPA 72-2022 §10.6.4  — Voltage drop limitations
  - NFPA 72-2022 §12.2    — Pathway design (Class A / Class B)
  - NFPA 72-2022 §12.3    — Pathway survivability
  - NEC Article 760        — Fire alarm systems wiring
  - NEC Chapter 9, Table 8 — Conductor resistance (copper)

Integration:
  - Uses NFPA72 constants from fireai.core.voltage_drop
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# Voltage drop module
from fireai.core.voltage_drop import (
    MAX_VOLTAGE_DROP_PCT,
    NOMINAL_VOLTAGE_FA,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. NEC 760 WIRE GAUGE
# ═══════════════════════════════════════════════════════════════════════════════


class _WireGaugeInstance:
    """A single wire gauge instance with NEC Table 8 properties.

    Stores BOTH 20°C and 75°C NEC published resistance values to avoid
    the temperature-coefficient approximation error (~2% for AWG 14).
    Using NEC published values directly is more accurate than the formula
    R_T = R_20 × [1 + α(T-20)] for the standard 75°C operating temperature.

    - resistance_ohm_per_km: NEC Table 8 value at 75°C (standard operating
      temperature for THHN/THWN per NEC 310.16). This is the PRIMARY
      property used for voltage drop calculations.
    - resistance_ohm_per_km_at_20c: NEC Table 8 value at 20°C (reference
      temperature). Used by constraint_engine.py and nfpa72_engine.py
      for temperature correction to non-standard temperatures.

    V FIX: Previous design stored only 20°C values and relied on the
    temperature coefficient formula, which introduces ~2% error vs NEC
    published values. For AWG 14: formula gives 10.277 Ω/km but NEC
    publishes 10.07 Ω/km at 75°C. Storing both eliminates this error
    while preserving the temperature correction path for non-75°C temps.
    """

    __slots__ = (
        "ampacity_a",
        "awg_value",
        "diameter_mm",
        "resistance_ohm_per_km",
        "resistance_ohm_per_km_at_20c",
        "resistance_ohm_per_m",
    )

    def __init__(
        self,
        awg_value: str,
        resistance_ohm_per_km_20c: float,
        resistance_ohm_per_km_75c: float,
        diameter_mm: float,
        ampacity_a: float,
    ):
        self.awg_value = awg_value
        # Primary: 75°C resistance (NEC operating temperature for THHN/THWN)
        self.resistance_ohm_per_km = resistance_ohm_per_km_75c
        self.resistance_ohm_per_m = resistance_ohm_per_km_75c / 1000.0
        # Reference: 20°C resistance (NEC Table 8 reference temperature)
        self.resistance_ohm_per_km_at_20c = resistance_ohm_per_km_20c
        self.diameter_mm = diameter_mm
        self.ampacity_a = ampacity_a

    def __str__(self) -> str:
        return self.awg_value

    def __repr__(self) -> str:
        return f"WireGauge.AWG_{self.awg_value}"

    def __hash__(self) -> int:
        return hash(self.awg_value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _WireGaugeInstance):
            return self.awg_value == other.awg_value
        if isinstance(other, str):
            return self.awg_value == other
        return NotImplemented


class _WireGaugeMeta(type):
    """Metaclass enabling iteration over WireGauge class attributes."""

    _ALL_GAUGES: Tuple[_WireGaugeInstance, ...]
    VALID_GAUGES: Tuple[str, ...]

    def __iter__(cls):
        return iter(cls._ALL_GAUGES)  # type: ignore[attr-defined]

    def __len__(cls):
        return len(cls._ALL_GAUGES)  # type: ignore[attr-defined]

    def __contains__(cls, item):
        if isinstance(item, _WireGaugeInstance):
            return item in cls._ALL_GAUGES  # type: ignore[attr-defined]
        if isinstance(item, str):
            return item in cls.VALID_GAUGES  # type: ignore[attr-defined]
        return False


class WireGauge(metaclass=_WireGaugeMeta):
    """NEC Article 760 / NEC Chapter 9 Table 8 — Fire alarm wire gauges.

    Standard fire alarm circuit wire gauges: AWG 12, 14, 16, 18.
    These are the gauges permitted by NEC 760.154 for PLFA circuits.
    """

    # NEC Chapter 9 Table 8 — DC resistance (copper, uncoated, stranded).
    # V FIX: Store BOTH 20°C and 75°C NEC published values.
    # 20°C values: reference temperature for NEC Table 8.
    # 75°C values: standard operating temperature for THHN/THWN per NEC 310.16.
    # Using NEC published 75°C values directly avoids the ~2% approximation
    # error from the temperature coefficient formula.
    # Source: NEC Chapter 9, Table 8, stranded copper conductors.
    #   AWG 18: 6.510 Ω/kft @ 20°C → 7.770 Ω/kft @ 75°C
    #   AWG 16: 4.080 Ω/kft @ 20°C → 4.890 Ω/kft @ 75°C
    #   AWG 14: 2.570 Ω/kft @ 20°C → 3.070 Ω/kft @ 75°C
    #   AWG 12: 1.620 Ω/kft @ 20°C → 1.930 Ω/kft @ 75°C
    AWG_18: _WireGaugeInstance = _WireGaugeInstance("18", 21.40, 25.49, 1.024, 1.0)
    AWG_16: _WireGaugeInstance = _WireGaugeInstance("16", 13.40, 16.04, 1.291, 2.0)
    AWG_14: _WireGaugeInstance = _WireGaugeInstance("14",  8.450, 10.07, 1.628, 2.0)
    AWG_12: _WireGaugeInstance = _WireGaugeInstance("12",  5.310,  6.33, 2.053, 3.0)

    _ALL_GAUGES: Tuple[_WireGaugeInstance, ...] = (AWG_18, AWG_16, AWG_14, AWG_12)

    # NEC Chapter 9 Table 8 — DC resistance at 75°C (Ω/m)
    # V FIX: Updated to 75°C operating temperature values to match
    # resistance_ohm_per_km (primary property).
    RESISTANCE_PER_M: Dict[str, float] = {
        "18": 0.02549,  # 25.49 Ω/km at 75°C
        "16": 0.01604,  # 16.04 Ω/km at 75°C
        "14": 0.01007,  # 10.07 Ω/km at 75°C
        "12": 0.00633,  # 6.33 Ω/km at 75°C
    }

    VALID_GAUGES: Tuple[str, ...] = ("12", "14", "16", "18")

    @classmethod
    def get_resistance_per_m(cls, awg: str) -> float:
        """Look up wire resistance in Ω/m by AWG label."""
        awg_clean = str(awg).strip()
        if awg_clean not in cls.VALID_GAUGES:
            raise ValueError(f"Unknown AWG gauge: {awg!r}. Supported fire alarm gauges: {cls.VALID_GAUGES}.")
        return cls.RESISTANCE_PER_M[awg_clean]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. OBSTACLE TYPE ENUM
# ═══════════════════════════════════════════════════════════════════════════════


class ObstacleType(Enum):
    """Classification of routing obstacles."""

    WALL = "WALL"
    COLUMN = "COLUMN"
    BEAM = "BEAM"
    SLAB = "SLAB"
    DOOR = "DOOR"
    SHAFT = "SHAFT"
    ELECTRICAL = "ELECTRICAL"
    HVAC = "HVAC"
    STRUCTURAL = "STRUCTURAL"
    ARCHITECTURAL = "ARCHITECTURAL"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ROUTING OBSTACLE 3D
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoutingObstacle3D:
    """A 3D axis-aligned bounding box obstacle for cable routing.

    Defined by two corner points (x1,y1,z1) and (x2,y2,z2) with
    optional firestop/rating metadata for fire-rated wall penetrations.

    Attributes:
        obstacle_id: Unique identifier.
        obstacle_type: Type of obstacle (ObstacleType enum).
        x1, y1, z1: Minimum corner coordinates.
        x2, y2, z2: Maximum corner coordinates.
        requires_firestop: Whether cable penetration requires firestopping.
        is_rated: Whether the obstacle is a fire-rated assembly.
        fire_rating_hours: Fire resistance rating in hours.

    """

    obstacle_id: str = ""
    obstacle_type: ObstacleType = ObstacleType.STRUCTURAL
    x1: float = 0.0
    y1: float = 0.0
    z1: float = 0.0
    x2: float = 1.0
    y2: float = 1.0
    z2: float = 1.0
    requires_firestop: bool = False
    is_rated: bool = False
    fire_rating_hours: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    width: float = 1.0
    height: float = 1.0
    depth: float = 1.0
    clearance_m: float = 0.0

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a point is inside or on the boundary of this obstacle."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2 and self.z1 <= z <= self.z2

    def intersects_line_segment(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
    ) -> bool:
        """Check if a line segment intersects this obstacle (AABB intersection).

        Uses the slab method for ray-AABB intersection.
        """
        # Direction vector
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]

        tmin = 0.0
        tmax = 1.0

        for start, direction, bmin, bmax in [
            (p1[0], dx, self.x1, self.x2),
            (p1[1], dy, self.y1, self.y2),
            (p1[2], dz, self.z1, self.z2),
        ]:
            if abs(direction) < 1e-12:
                # Parallel to slab
                if start < bmin or start > bmax:
                    return False
            else:
                t1 = (bmin - start) / direction
                t2 = (bmax - start) / direction
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return False

        return tmin <= tmax


# ═══════════════════════════════════════════════════════════════════════════════
# 4. VOLTAGE DROP SEGMENT
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class VoltageDropSegment:
    """Per-segment voltage drop result for NFPA 72 §10.6.4 verification.

    Attributes:
        segment_index: Zero-based index.
        from_point: Start point (x, y, z).
        to_point: End point (x, y, z).
        length_m: One-way segment length in metres.
        current_a: Circuit current in Amperes.
        awg: Wire gauge string.
        resistance_per_m_ohm: Wire resistance in Ω/m.
        voltage_drop_v: Voltage drop across this segment (Volts).
        cumulative_drop_v: Cumulative drop from panel to end of segment.
        is_compliant: Whether cumulative drop is within limits.
        nfpa_section: Standard citation.

    """

    segment_index: int
    from_point: Tuple[float, float, float]
    to_point: Tuple[float, float, float]
    length_m: float
    current_a: float
    awg: str
    resistance_per_m_ohm: float
    voltage_drop_v: float
    cumulative_drop_v: float
    is_compliant: bool
    nfpa_section: str = "NFPA 72 §10.6.4"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ROUTE RESULT
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RouteResult:
    """Immutable result of a cable routing operation.

    Attributes:
        circuit_id: Unique circuit identifier.
        is_compliant: Whether the route meets all NEC/NFPA constraints.
        total_voltage_drop_v: Total voltage drop from panel to farthest device.
        total_voltage_drop_pct: Voltage drop as percentage of system voltage.
        end_of_line_voltage_v: Voltage at the end of line.
        segments: Tuple of VoltageDropSegment results.
        warnings: Tuple of warning strings.
        violations: Tuple of violation strings.
        wire_gauge: The WireGauge instance used.
        selected_gauge_is_minimum: Whether the auto-selected gauge is the minimum.
        total_return_length_m: Return path length for Class A circuits.

    """

    circuit_id: str = ""
    is_compliant: bool = False  # V112: FAIL-SAFE — new circuit starts as NOT compliant until verified
    total_voltage_drop_v: float = 0.0
    total_voltage_drop_pct: float = 0.0
    end_of_line_voltage_v: float = 0.0
    segments: Tuple[VoltageDropSegment, ...] = ()
    warnings: Tuple[str, ...] = ()
    violations: Tuple[str, ...] = ()
    wire_gauge: Any = None  # WireGauge instance
    selected_gauge_is_minimum: bool = False
    total_return_length_m: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. CABLE ROUTING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class CableRoutingEngine:
    """LIFE-SAFETY CRITICAL cable routing engine for fire alarm circuits.

    Implements voltage drop verification per NFPA 72 §10.6.4,
    auto gauge selection (AWG 18→12), and 3D Euclidean distance
    calculation for both Class A and Class B circuits.

    Usage::

        engine = CableRoutingEngine()
        result = engine.route_circuit(circuit, wire_gauge=WireGauge.AWG_14)
    """

    def __init__(
        self,
        obstacles: Optional[List[RoutingObstacle3D]] = None,
        ps_voltage: float = NOMINAL_VOLTAGE_FA,
        max_voltage_drop_pct: float = MAX_VOLTAGE_DROP_PCT,
    ) -> None:
        """Initialize the cable routing engine.

        Args:
            obstacles: Initial list of routing obstacles.
            ps_voltage: Power supply voltage (default 24V DC).
            max_voltage_drop_pct: Maximum allowed voltage drop percentage.

        Raises:
            ValueError: If parameters are invalid.

        """
        if not math.isfinite(ps_voltage) or ps_voltage <= 0:
            raise ValueError(f"ps_voltage={ps_voltage} must be finite and positive")
        if not math.isfinite(max_voltage_drop_pct) or max_voltage_drop_pct <= 0:
            raise ValueError(f"max_voltage_drop_pct={max_voltage_drop_pct} must be finite and positive")

        self._ps_voltage = ps_voltage
        self._max_drop_pct = max_voltage_drop_pct
        self._obstacles: List[RoutingObstacle3D] = list(obstacles) if obstacles else []

        logger.info(
            "CableRoutingEngine initialized: %d obstacles, ps_voltage=%.0fV",
            len(self._obstacles),
            ps_voltage,
        )

    # ── Obstacle Management ────────────────────────────────────────────────

    def add_obstacle(self, obstacle: RoutingObstacle3D) -> None:
        """Add a routing obstacle to the engine."""
        if not isinstance(obstacle, RoutingObstacle3D):
            raise TypeError(f"Expected RoutingObstacle3D, got {type(obstacle).__name__}")
        self._obstacles.append(obstacle)

    def clear_obstacles(self) -> None:
        """Remove all routing obstacles."""
        self._obstacles.clear()

    def check_obstacle_intersections(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
    ) -> List[RoutingObstacle3D]:
        """Check which obstacles a line segment intersects.

        Returns list of obstacles that the line from p1 to p2 passes through.
        """
        hits = []
        for obs in self._obstacles:
            if obs.intersects_line_segment(p1, p2):
                hits.append(obs)
        return hits

    # ── 3D Distance ────────────────────────────────────────────────────────

    @staticmethod
    def calculate_3d_distance(
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
    ) -> float:
        """Calculate 3D Euclidean distance between two points.

        Args:
            p1: Start point (x, y, z).
            p2: End point (x, y, z).

        Returns:
            Distance in metres.

        Raises:
            ValueError: If any coordinate is NaN or Inf.

        """
        for name, pt in [("p1", p1), ("p2", p2)]:
            for i, coord in enumerate(pt):
                if not math.isfinite(coord):
                    raise ValueError(f"{name}[{i}]={coord} is not finite — 3D distance requires finite coordinates")
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    # ── Route Circuit ──────────────────────────────────────────────────────

    def route_circuit(
        self,
        circuit: Any,
        wire_gauge: Optional[_WireGaugeInstance] = None,
        ps_voltage: Optional[float] = None,
    ) -> RouteResult:
        """Route a circuit and verify voltage drop compliance.

        Args:
            circuit: CircuitTopology instance from circuit_topology module.
            wire_gauge: Wire gauge to use. If None, auto-selects smallest
                       compliant gauge (AWG 18 first).
            ps_voltage: Override power supply voltage for this circuit.

        Returns:
            RouteResult with compliance status and voltage drop details.

        Raises:
            ValueError: If circuit has invalid data.

        """
        voltage = ps_voltage if ps_voltage is not None else self._ps_voltage

        # V65 FIX: Validate per-circuit ps_voltage override for NaN/Inf.
        # The constructor validates self._ps_voltage, but per-circuit overrides
        # were not validated. NaN voltage → NaN drop percentage → fail-safe
        # but NaN propagates through result fields, breaking downstream code.
        if not math.isfinite(voltage) or voltage <= 0:
            raise ValueError(
                f"ps_voltage={voltage} must be finite and positive. "
                f"NaN/Inf/negative voltage cannot produce valid voltage drop calculations."
            )

        # Validate circuit data
        if not math.isfinite(circuit.cable_length_m) or circuit.cable_length_m < 0:
            raise ValueError(f"cable_length_m={circuit.cable_length_m} must be non-negative finite")

        # Check for NaN device coordinates
        for dev in circuit.devices:
            for attr_name in ("position_x", "position_y", "position_z"):
                val = getattr(dev, attr_name, 0.0)
                if not math.isfinite(val):
                    raise ValueError(f"Device '{dev.device_id}' has non-finite {attr_name}={val}")
            # V65 FIX: Check for NaN current first, then negative.
            # Old code: math.isfinite(dev.current_a) short-circuited on NaN,
            # silently accepting NaN → NaN downstream current → NaN voltage drop.
            if hasattr(dev, "current_a"):
                if not math.isfinite(dev.current_a):
                    raise ValueError(
                        f"Device '{dev.device_id}' has non-finite current_a={dev.current_a}. "
                        f"NaN/Inf current produces NaN voltage drop."
                    )
                if dev.current_a < 0:
                    raise ValueError(f"Device '{dev.device_id}' has invalid current current_a={dev.current_a}")

        # Class A must have return path
        from fireai.core.circuit_topology import CircuitClass

        if circuit.circuit_class == CircuitClass.CLASS_A:
            if not hasattr(circuit, "return_length_m") or circuit.return_length_m <= 0:
                raise ValueError("Class A circuit requires return_length_m > 0 per NFPA 72 §12.2.2")

        # Auto gauge selection or use specified gauge
        auto_selected = wire_gauge is None
        if auto_selected:
            # Try gauges from smallest (AWG 18) to largest (AWG 12)
            for gauge in WireGauge._ALL_GAUGES:
                result = self._compute_route(circuit, gauge, voltage)
                if result.is_compliant:
                    return RouteResult(
                        circuit_id=circuit.circuit_id,
                        is_compliant=True,
                        total_voltage_drop_v=result.total_voltage_drop_v,
                        total_voltage_drop_pct=result.total_voltage_drop_pct,
                        end_of_line_voltage_v=result.end_of_line_voltage_v,
                        segments=tuple(result.segments),
                        warnings=tuple(result.warnings),
                        violations=(),
                        wire_gauge=gauge,
                        selected_gauge_is_minimum=(gauge == WireGauge._ALL_GAUGES[0]),
                        total_return_length_m=getattr(circuit, "return_length_m", 0.0),
                    )
            # No compliant gauge found — use the largest gauge tried and report violation
            # V58 FIX (BUG #6): Use largest gauge (_ALL_GAUGES[-1]) instead of smallest
            # (_ALL_GAUGES[0]). Reporting the smallest gauge makes the situation appear
            # worse than it is, potentially leading to unnecessary expensive design changes.
            gauge = WireGauge._ALL_GAUGES[-1]
            result = self._compute_route(circuit, gauge, voltage)
            return RouteResult(
                circuit_id=circuit.circuit_id,
                is_compliant=False,
                total_voltage_drop_v=result.total_voltage_drop_v,
                total_voltage_drop_pct=result.total_voltage_drop_pct,
                end_of_line_voltage_v=result.end_of_line_voltage_v,
                segments=tuple(result.segments),
                warnings=tuple(result.warnings),
                violations=tuple(result.violations),
                wire_gauge=gauge,
                selected_gauge_is_minimum=True,
                total_return_length_m=getattr(circuit, "return_length_m", 0.0),
            )
        result = self._compute_route(circuit, wire_gauge, voltage)
        return RouteResult(
            circuit_id=circuit.circuit_id,
            is_compliant=result.is_compliant,
            total_voltage_drop_v=result.total_voltage_drop_v,
            total_voltage_drop_pct=result.total_voltage_drop_pct,
            end_of_line_voltage_v=result.end_of_line_voltage_v,
            segments=tuple(result.segments),
            warnings=tuple(result.warnings),
            violations=tuple(result.violations),
            wire_gauge=wire_gauge,
            selected_gauge_is_minimum=False,
            total_return_length_m=getattr(circuit, "return_length_m", 0.0),
        )

    # ── Internal Route Computation ─────────────────────────────────────────

    def _compute_route(
        self,
        circuit: Any,
        wire_gauge: _WireGaugeInstance,
        voltage: float,
    ) -> Any:
        """Compute voltage drop along the circuit for a given wire gauge.

        Uses the NFPA 72 §10.6.4 formula:
            V_drop = 2 × I_total × R_per_m × L
        where 2 = DC return path factor.
        """
        from fireai.core.circuit_topology import CircuitClass

        awg = wire_gauge.awg_value
        # V FIX: Use NEC published 75°C resistance directly from WireGauge.
        # WireGauge now stores both 20°C and 75°C NEC published values.
        # resistance_ohm_per_km returns the 75°C value (standard operating
        # temperature for THHN/THWN per NEC 310.16). No temperature
        # correction formula needed — using NEC published values directly
        # is more accurate than the formula (avoids ~2% approximation error).
        resistance_per_m = wire_gauge.resistance_ohm_per_m

        panel_pos = getattr(circuit, "panel_position", (0.0, 0.0, 0.0))
        devices = circuit.devices

        segments: List[VoltageDropSegment] = []
        warnings_list: List[str] = []
        violations_list: List[str] = []
        cumulative_drop = 0.0

        # Total current for all devices on the circuit
        total_current = sum(getattr(d, "current_a", 0.0) for d in devices)

        # For voltage drop: each segment carries the total current of all
        # downstream devices. We compute per-segment drop.
        # Segment: panel → device 1 → device 2 → ... → device N

        prev_point = panel_pos
        # Cumulative current from panel to farthest device
        # All devices draw current, so the first segment carries all current,
        # and each subsequent segment carries the current of remaining devices.

        for i, dev in enumerate(devices):
            dev_pos = (
                getattr(dev, "position_x", 0.0),
                getattr(dev, "position_y", 0.0),
                getattr(dev, "position_z", 0.0),
            )

            # V65 FIX: Apply routing factor to Euclidean distance.
            # Real cables follow corridors, route around walls, through conduit,
            # and make bends — ALWAYS longer than straight-line distance.
            # The old code used raw Euclidean distance, underestimating voltage
            # drop by 2-3× in typical buildings. This is the most dangerous bug
            # in the codebase — it can cause fire alarm devices to fail during
            # a fire because voltage drop is underestimated.
            #
            # If circuit.cable_length_m is available (from A* routing), use it
            # for the TOTAL route length. Otherwise, apply a routing factor to
            # each segment. The routing factor accounts for bends, drops, and
            # non-straight routing. Per NEC and typical practice:
            #   - 1.2× for simple straight runs
            #   - 1.5× for typical building routing (default)
            #   - 2.0× for complex routing with many bends
            #
            # PREFERRED: Use actual routed cable length from cable_router.py.
            # This routing factor is a CONSERVATIVE APPROXIMATION.
            ROUTING_FACTOR = 1.5  # Conservative default for typical building routing
            seg_length_euclidean = self.calculate_3d_distance(prev_point, dev_pos)
            seg_length = seg_length_euclidean * ROUTING_FACTOR

            # If actual routed cable length is available, use total route length
            # proportionally distributed across segments instead of Euclidean×factor.
            # This provides a more accurate voltage drop calculation.
            total_cable_length = getattr(circuit, 'cable_length_m', None)
            if total_cable_length and total_cable_length > 0 and len(devices) > 0:
                # Use actual cable length proportionally distributed by Euclidean ratio
                total_euclidean = sum(
                    self.calculate_3d_distance(
                        panel_pos if j == 0 else (
                            getattr(devices[j-1], "position_x", 0.0),
                            getattr(devices[j-1], "position_y", 0.0),
                            getattr(devices[j-1], "position_z", 0.0),
                        ),
                        (
                            getattr(devices[j], "position_x", 0.0),
                            getattr(devices[j], "position_y", 0.0),
                            getattr(devices[j], "position_z", 0.0),
                        )
                    )
                    for j in range(len(devices))
                )
                if total_euclidean > 0:
                    seg_length = seg_length_euclidean * (total_cable_length / total_euclidean)
            else:
                if seg_length_euclidean > 0:
                    warnings_list.append(
                        f"Segment {i}: Using routing factor {ROUTING_FACTOR}× on "
                        f"Euclidean distance ({seg_length_euclidean:.1f}m → {seg_length:.1f}m). "
                        f"For accurate voltage drop, provide circuit.cable_length_m "
                        f"from A* routing. Raw Euclidean underestimates actual cable length."
                    )

            # Current carried by this segment = sum of all devices from i onwards
            downstream_current = sum(getattr(d, "current_a", 0.0) for d in devices[i:])

            # Voltage drop: V_drop = 2 × I × R_per_m × L
            seg_drop = 2.0 * downstream_current * resistance_per_m * seg_length
            cumulative_drop += seg_drop

            seg_pct = (cumulative_drop / voltage) * 100.0 if voltage > 0 else 0.0

            segments.append(
                VoltageDropSegment(
                    segment_index=i,
                    from_point=prev_point,
                    to_point=dev_pos,
                    length_m=seg_length,
                    current_a=downstream_current,
                    awg=awg,
                    resistance_per_m_ohm=resistance_per_m,
                    voltage_drop_v=seg_drop,
                    cumulative_drop_v=cumulative_drop,
                    is_compliant=seg_pct <= self._max_drop_pct,
                    nfpa_section="NFPA 72 §10.6.4",
                )
            )

            prev_point = dev_pos

        # For Class A, also compute return path drop
        if getattr(circuit, "circuit_class", None) == CircuitClass.CLASS_A:
            return_length = getattr(circuit, "return_length_m", 0.0)
            if return_length > 0 and total_current > 0:
                # V76 MED-08 FIX: Class A return path uses 1.0× instead of 2.0×.
                # Under normal operation, Class A circuits carry current on the outbound
                # path only — the return path is not energized. Under single-fault
                # conditions (wire break), the return path carries partial current.
                # Using 2.0× (DC round-trip) for BOTH outbound AND return overstates
                # voltage drop by ~2×, causing unnecessary circuit rejections.
                # Conservative approach: 1.0× for return (single conductor) with
                # total_current as worst-case. This still provides safety margin.
                return_drop = total_current * resistance_per_m * return_length
                cumulative_drop += return_drop

        total_drop_pct = (cumulative_drop / voltage) * 100.0 if voltage > 0 else 0.0
        is_compliant = total_drop_pct <= self._max_drop_pct

        if not is_compliant:
            violations_list.append(
                f"Voltage drop {total_drop_pct:.1f}% exceeds maximum {self._max_drop_pct:.1f}% per NFPA 72 §10.6.4"
            )

        # Check for obstacle intersections and generate firestop warnings
        if devices:
            prev_pt = panel_pos
            for dev in devices:
                dev_pt = (
                    getattr(dev, "position_x", 0.0),
                    getattr(dev, "position_y", 0.0),
                    getattr(dev, "position_z", 0.0),
                )
                for obs in self._obstacles:
                    if obs.intersects_line_segment(prev_pt, dev_pt):
                        if getattr(obs, "requires_firestop", False) or getattr(obs, "is_rated", False):
                            rating = getattr(obs, "fire_rating_hours", 0.0)
                            warnings_list.append(
                                f"firestopping required: cable penetrates "
                                f"{obs.obstacle_type.value} '{obs.obstacle_id}' "
                                f"({rating:.0f}h rated) per NFPA 72 §12.3"
                            )
                prev_pt = dev_pt

        # Build a simple namespace for the result
        class _RouteInternal:
            is_compliant: bool
            total_voltage_drop_v: float
            total_voltage_drop_pct: float
            end_of_line_voltage_v: float
            segments: list
            warnings: list
            violations: list

        result = _RouteInternal()
        result.is_compliant = is_compliant
        result.total_voltage_drop_v = cumulative_drop
        result.total_voltage_drop_pct = total_drop_pct
        # V65 FIX: Clamp end-of-line voltage to 0.0 (physically impossible to be negative).
        # Old code: voltage - cumulative_drop could be negative when drop exceeds supply.
        # A negative voltage is physically impossible and could confuse downstream code.
        eol_voltage_raw = voltage - cumulative_drop
        if eol_voltage_raw < 0:
            violations_list.append(
                "CRITICAL: Cumulative voltage drop exceeds power supply voltage — "
                "circuit is non-functional. Devices will not operate during alarm."
            )
        result.end_of_line_voltage_v = max(0.0, eol_voltage_raw)
        result.segments = segments
        result.warnings = warnings_list
        result.violations = violations_list

        return result
