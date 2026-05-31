"""
fireai/core/cable_routing_engine.py
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
    """A single wire gauge instance with NEC Table 8 properties."""

    __slots__ = ("awg_value", "resistance_ohm_per_km", "resistance_ohm_per_m", "diameter_mm", "ampacity_a")

    def __init__(
        self,
        awg_value: str,
        resistance_ohm_per_km: float,
        diameter_mm: float,
        ampacity_a: float,
    ):
        self.awg_value = awg_value
        self.resistance_ohm_per_km = resistance_ohm_per_km
        self.resistance_ohm_per_m = resistance_ohm_per_km / 1000.0
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

    def __iter__(cls):
        return iter(cls._ALL_GAUGES)

    def __len__(cls):
        return len(cls._ALL_GAUGES)

    def __contains__(cls, item):
        if isinstance(item, _WireGaugeInstance):
            return item in cls._ALL_GAUGES
        if isinstance(item, str):
            return item in cls.VALID_GAUGES
        return False


class WireGauge(metaclass=_WireGaugeMeta):
    """
    NEC Article 760 / NEC Chapter 9 Table 8 — Fire alarm wire gauges.

    Standard fire alarm circuit wire gauges: AWG 12, 14, 16, 18.
    These are the gauges permitted by NEC 760.154 for PLFA circuits.
    """

    AWG_18: _WireGaugeInstance = _WireGaugeInstance("18", 21.40, 1.024, 1.0)
    AWG_16: _WireGaugeInstance = _WireGaugeInstance("16", 13.40, 1.291, 2.0)
    AWG_14: _WireGaugeInstance = _WireGaugeInstance("14", 8.450, 1.628, 2.0)
    AWG_12: _WireGaugeInstance = _WireGaugeInstance("12", 5.310, 2.053, 3.0)

    _ALL_GAUGES: Tuple[_WireGaugeInstance, ...] = (AWG_18, AWG_16, AWG_14, AWG_12)

    RESISTANCE_PER_M: Dict[str, float] = {
        "18": 0.02140,
        "16": 0.01340,
        "14": 0.00845,
        "12": 0.00531,
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


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ROUTING OBSTACLE 3D
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoutingObstacle3D:
    """
    A 3D axis-aligned bounding box obstacle for cable routing.

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

    obstacle_id: str
    obstacle_type: ObstacleType
    x1: float = 0.0
    y1: float = 0.0
    z1: float = 0.0
    x2: float = 1.0
    y2: float = 1.0
    z2: float = 1.0
    requires_firestop: bool = False
    is_rated: bool = False
    fire_rating_hours: float = 0.0

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
    """
    Immutable result of a cable routing operation.

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
    """
    LIFE-SAFETY CRITICAL cable routing engine for fire alarm circuits.

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
        """
        Initialize the cable routing engine.

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

        # Validate circuit data
        if not math.isfinite(circuit.cable_length_m) or circuit.cable_length_m < 0:
            raise ValueError(f"cable_length_m={circuit.cable_length_m} must be non-negative finite")

        # Check for NaN device coordinates
        for dev in circuit.devices:
            for attr_name in ("position_x", "position_y", "position_z"):
                val = getattr(dev, attr_name, 0.0)
                if not math.isfinite(val):
                    raise ValueError(f"Device '{dev.device_id}' has non-finite {attr_name}={val}")
            # Check for negative current
            if hasattr(dev, "current_a") and math.isfinite(dev.current_a) and dev.current_a < 0:
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
            # No compliant gauge found — use the smallest and report violation
            gauge = WireGauge._ALL_GAUGES[0]
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
        else:
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

            # Distance from previous point to this device
            seg_length = self.calculate_3d_distance(prev_point, dev_pos)

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
                return_drop = 2.0 * total_current * resistance_per_m * return_length
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
            pass

        result = _RouteInternal()
        result.is_compliant = is_compliant
        result.total_voltage_drop_v = cumulative_drop
        result.total_voltage_drop_pct = total_drop_pct
        result.end_of_line_voltage_v = voltage - cumulative_drop
        result.segments = segments
        result.warnings = warnings_list
        result.violations = violations_list

        return result
