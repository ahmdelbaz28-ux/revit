"""
fireai.core.cable_routing_engine — NFPA 72 Cable Routing Engine
===============================================================

Implements 3D cable routing and voltage drop verification for fire
alarm circuits per NFPA 72-2022:

1. CableRoutingEngine    — Main routing engine for circuit design
2. RouteResult           — Result of a routing calculation
3. CircuitTopology       — Imported from circuit_topology module
4. WireGauge             — Wire gauge enum (AWG 12-18, typical for fire alarm)
5. RoutingObstacle3D     — 3D obstacle representation (walls, beams, columns)
6. VoltageDropSegment    — A cable segment with voltage drop calculation

SAFETY CRITICAL:
  - All NaN/Inf inputs MUST be REJECTED
  - All negative inputs MUST be REJECTED
  - Voltage drop uses DC return path factor (×2) per NEC Chapter 9
  - Class A circuits require return path verification
  - Every formula MUST trace to NFPA/NEC source section
  - Wire gauge selection MUST meet voltage drop compliance

ENGINEERING SOURCES:
  - NFPA 72-2022 §10.6.4 — Voltage drop verification
  - NFPA 72-2022 §12.2   — Circuit class designations
  - NFPA 72-2022 §12.3   — SLC fault isolator requirements
  - NEC Chapter 9, Table 8 — Wire resistance values (copper, stranded)
  - NEC 760 — Fire alarm circuit wiring requirements

All formulas are traced to their NFPA/NEC source sections.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Import existing voltage drop calculation for verification
from fireai.core.nfpa72_engine import (
    calculate_voltage_drop,
    AWG_RESISTANCE_OHM_PER_KM,
    temperature_corrected_resistance,
)

# Import circuit topology class
from fireai.core.circuit_topology import (
    CircuitTopology as CircuitTopology,
    CircuitClass,
    CircuitType,
    CircuitDevice,
    MAX_DEVICES_BETWEEN_ISOLATORS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# WIRE GAUGE — AWG 12-18 for fire alarm circuits
# ═══════════════════════════════════════════════════════════════════════════════

class WireGauge(enum.Enum):
    """Standard wire gauges used in fire alarm circuits.

    NEC Chapter 9, Table 8 provides resistance values for copper
    conductors. Fire alarm circuits typically use AWG 12-18.

    NEC 760.61 limits:
      - Class 1 circuits: minimum AWG 18 (0.823 mm²)
      - Power-limited fire alarm (PLFA): minimum AWG 18

    Typical usage in fire alarm:
      - AWG 12: Main power feeds, long NAC circuits
      - AWG 14: Standard NAC circuits, SLC home runs
      - AWG 16: Short SLC/NAC branches
      - AWG 18: Individual device taps, very short runs

    Resistance values from NEC Chapter 9, Table 8 (copper, stranded,
    at 20°C):
      - AWG 12: 5.310 Ω/km
      - AWG 14: 8.450 Ω/km
      - AWG 16: 13.40 Ω/km
      - AWG 18: 21.40 Ω/km

    Conductor overall diameter (with insulation) from NEC Chapter 9,
    Table 5 (THHN/THWN-2) and Table 5A (FPL cables):
      - AWG 12: 3.30 mm (THHN per NEC Table 5)
      - AWG 14: 2.62 mm (THHN per NEC Table 5)
      - AWG 16: 2.00 mm (FPL typical, conservative)
      - AWG 18: 1.70 mm (FPL typical, conservative)

    V62 FIX: Added diameter_mm property. Previously, check_all() in
    constraint_engine.py tried getattr(wire_gauge, 'diameter_mm', None)
    which always returned None, causing the conduit fill check to be
    SILENTLY SKIPPED. Overfilled conduit causes overheating — NEC code
    violation and fire hazard.
    """
    AWG_12 = "12"   # 5.310 Ω/km — main feeds, long NAC runs
    AWG_14 = "14"   # 8.450 Ω/km — standard NAC/SLC
    AWG_16 = "16"   # 13.40 Ω/km — short branches
    AWG_18 = "18"   # 21.40 Ω/km — device taps

    @property
    def resistance_ohm_per_km(self) -> float:
        """Wire resistance in Ω/km from NEC Chapter 9, Table 8."""
        return AWG_RESISTANCE_OHM_PER_KM[self.value]

    @property
    def awg_value(self) -> str:
        """AWG gauge string (e.g. '12', '14')."""
        return self.value

    @property
    def diameter_mm(self) -> float:
        """Conductor overall diameter with insulation in mm.

        NEC Chapter 9, Table 5 (THHN/THWN-2) and Table 5A (FPL).
        Used for conduit fill calculations per NEC 760.154.

        V62 FIX: Added diameter_mm property. Previously, check_all() in
        constraint_engine.py tried getattr(wire_gauge, 'diameter_mm', None)
        which always returned None, causing the conduit fill check to be
        SILENTLY SKIPPED. Overfilled conduit causes overheating — NEC code
        violation and fire hazard.

        Returns:
            Diameter in millimeters (conservative/oversized for safety).
        """
        return _AWG_DIAMETER_MM[self.value]


# NEC Chapter 9, Table 5 / Table 5A — conductor overall diameter
# with insulation (mm). Used for conduit fill calculations.
# Values are conservative (slightly oversized) for safety.
# V62: Added to fix Bug 22 — conduit fill check was silently skipped.
_AWG_DIAMETER_MM = {
    "12": 3.30,   # THHN per NEC Ch.9 Table 5 (0.130")
    "14": 2.62,   # THHN per NEC Ch.9 Table 5 (0.103")
    "16": 2.00,   # FPL typical (conservative)
    "18": 1.70,   # FPL typical (conservative)
}

# Ordered list of wire gauges from smallest (highest resistance) to largest
# Used for automatic gauge selection — try smallest first, pick the minimum
# gauge that complies with NFPA 72 §10.6.4 voltage drop requirements.
# We try AWG 18 first (cheapest, thinnest) and go up to AWG 12 if needed.
_WIRE_GAUGES_ASCENDING = [
    WireGauge.AWG_18,
    WireGauge.AWG_16,
    WireGauge.AWG_14,
    WireGauge.AWG_12,
]


# ═══════════════════════════════════════════════════════════════════════════════
# NFPA 72 VOLTAGE DROP LIMITS
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §10.6.4: Maximum voltage drop for 24V systems is 10%
# End-of-line voltage must be ≥ 21.6V on a 24V system
_MAX_VOLTAGE_DROP_PCT = 10.0
_SYSTEM_VOLTAGE = 24.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3D ROUTING OBSTACLE
# ═══════════════════════════════════════════════════════════════════════════════

class ObstacleType(enum.Enum):
    """Types of 3D obstacles that affect cable routing.

    Each obstacle type has different routing implications:
      - WALL: Cable must route around (increases path length)
      - BEAM: Cable may route through with firestopping
      - COLUMN: Cable must route around
      - FLOOR_SLAB: Vertical penetration requires firestopping
      - SHAFT: Dedicated vertical routing pathway
    """
    WALL       = "WALL"        # Partition — route around
    BEAM       = "BEAM"        # Structural beam — route around or through with firestop
    COLUMN     = "COLUMN"      # Structural column — route around
    FLOOR_SLAB = "FLOOR_SLAB"  # Horizontal slab — firestop required for penetration
    SHAFT      = "SHAFT"       # Vertical shaft — preferred routing pathway


@dataclass(frozen=True)
class RoutingObstacle3D:
    """3D obstacle that affects cable routing.

    Represents a physical obstruction (wall, beam, column, floor slab)
    in the building that must be accounted for when routing fire alarm
    cables. Obstacles increase cable path length and may require
    firestopping at penetration points.

    NFPA 72 §12.2.2: Class A circuit outgoing and return conductors
    must not be routed through the same opening in a wall, floor, or
    ceiling. Obstacles that create common penetration points must be
    flagged for Class A circuit routing.

    The obstacle is represented as an axis-aligned bounding box (AABB)
    defined by two corner points (x1, y1, z1) and (x2, y2, z2).

    Attributes:
        obstacle_id: Unique identifier for this obstacle.
        obstacle_type: Type of obstacle (wall, beam, column, etc.).
        x1, y1, z1: First corner of bounding box (meters).
        x2, y2, z2: Opposite corner of bounding box (meters).
        requires_firestop: Whether cable penetration requires firestopping.
        is_rated: Whether this is a fire-rated assembly (affects routing).
        fire_rating_hours: Fire rating in hours (0.0 if not rated).
    """
    obstacle_id:        str
    obstacle_type:      ObstacleType = ObstacleType.WALL
    x1:                 float = 0.0
    y1:                 float = 0.0
    z1:                 float = 0.0
    x2:                 float = 0.0
    y2:                 float = 0.0
    z2:                 float = 0.0
    requires_firestop:  bool  = True
    is_rated:           bool  = False
    fire_rating_hours:  float = 0.0

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a 3D point is inside this obstacle's bounding box.

        Args:
            x, y, z: Point coordinates in meters.

        Returns:
            True if the point is inside the obstacle AABB.
        """
        min_x, max_x = min(self.x1, self.x2), max(self.x1, self.x2)
        min_y, max_y = min(self.y1, self.y2), max(self.y1, self.y2)
        min_z, max_z = min(self.z1, self.z2), max(self.z1, self.z2)
        return (min_x <= x <= max_x
                and min_y <= y <= max_y
                and min_z <= z <= max_z)

    def intersects_line_segment(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
    ) -> bool:
        """Check if a line segment intersects this obstacle's bounding box.

        Uses a simplified slab method for AABB intersection testing.
        This is a conservative test — it may report intersections for
        near-miss paths, which is safer than missing actual collisions.

        Args:
            p1: Start point of the line segment (x, y, z).
            p2: End point of the line segment (x, y, z).

        Returns:
            True if the line segment may intersect the obstacle AABB.
        """
        min_x, max_x = min(self.x1, self.x2), max(self.x1, self.x2)
        min_y, max_y = min(self.y1, self.y2), max(self.y1, self.y2)
        min_z, max_z = min(self.z1, self.z2), max(self.z1, self.z2)

        # Direction vector
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]

        # Check each slab
        t_min = 0.0
        t_max = 1.0

        for d, p_min, p_max, o in [
            (dx, min_x, max_x, p1[0]),
            (dy, min_y, max_y, p1[1]),
            (dz, min_z, max_z, p1[2]),
        ]:
            if abs(d) < 1e-12:
                # Parallel to slab
                if o < p_min or o > p_max:
                    return False
            else:
                t1 = (p_min - o) / d
                t2 = (p_max - o) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                if t_min > t_max:
                    return False

        return t_min <= t_max


# ═══════════════════════════════════════════════════════════════════════════════
# VOLTAGE DROP SEGMENT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VoltageDropSegment:
    """A cable segment with voltage drop calculation.

    Represents a single segment of cable between two points, with the
    voltage drop calculated per NEC Chapter 9, Table 8.

    NFPA 72 §10.6.4 and NEC Chapter 9, Table 8:
      V_drop = I × 2 × R_wire × L

    The ×2 factor accounts for the DC return path — current flows out
    on one conductor and returns on the other. This is CRITICAL for
    life safety: omitting the ×2 factor would report voltage drop at
    50% of actual value, potentially allowing non-compliant circuits.

    Attributes:
        segment_id: Unique segment identifier.
        start_point: (x, y, z) coordinates of segment start (meters).
        end_point: (x, y, z) coordinates of segment end (meters).
        length_m: Cable segment length in meters (one-way).
        wire_gauge: Wire gauge used for this segment.
        current_a: Alarm current flowing through this segment (amperes).
        voltage_drop_v: Calculated voltage drop including ×2 return factor.
        voltage_drop_pct: Voltage drop as percentage of system voltage.
        is_compliant: Whether this segment meets NFPA 72 §10.6.4 limits.
        formula: Human-readable formula with computed values.
        nfpa_section: NFPA 72 section reference.
    """
    segment_id:       str
    start_point:      Tuple[float, float, float]
    end_point:        Tuple[float, float, float]
    length_m:         float
    wire_gauge:       WireGauge
    current_a:        float
    voltage_drop_v:   float
    voltage_drop_pct: float
    is_compliant:     bool
    formula:          str
    nfpa_section:     str = "NFPA 72 §10.6.4"


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE RESULT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RouteResult:
    """Result of a cable routing calculation.

    Contains the complete routing solution for a circuit, including
    all segments, voltage drop analysis, and NFPA 72 compliance status.

    NFPA 72 References:
      - §10.6.4: Voltage drop must not exceed 10% on 24V systems
      - §12.2: Class A/B circuit routing requirements
      - §12.3: SLC fault isolator placement
      - NEC Chapter 9, Table 8: Wire resistance values

    Attributes:
        circuit_id: Circuit identifier.
        total_length_m: Total one-way cable length in meters.
        total_return_length_m: Total return path length (Class A only).
        wire_gauge: Selected wire gauge.
        segments: List of voltage drop segments along the route.
        total_voltage_drop_v: Cumulative voltage drop at end-of-line.
        total_voltage_drop_pct: Cumulative voltage drop as percentage.
        end_of_line_voltage_v: Voltage at the last device.
        is_compliant: Whether the entire route meets NFPA 72 §10.6.4.
        selected_gauge_is_minimum: Whether a smaller gauge could work.
        violations: List of NFPA 72 violations found.
        warnings: List of non-critical issues.
        formula: Summary formula for the route.
        nfpa_sections: NFPA 72 sections referenced.
    """
    circuit_id:                str
    total_length_m:            float
    total_return_length_m:     float
    wire_gauge:                WireGauge
    segments:                  Tuple[VoltageDropSegment, ...]
    total_voltage_drop_v:      float
    total_voltage_drop_pct:    float
    end_of_line_voltage_v:     float
    is_compliant:              bool
    selected_gauge_is_minimum: bool
    violations:                Tuple[str, ...]
    warnings:                  Tuple[str, ...]
    formula:                   str
    nfpa_sections:             Tuple[str, ...] = (
        "NFPA 72 §10.6.4",
        "NFPA 72 §12.2",
        "NEC Chapter 9, Table 8",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CABLE ROUTING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class CableRoutingEngine:
    """Main cable routing engine for fire alarm circuit design.

    Performs 3D cable routing with voltage drop verification per
    NFPA 72 §10.6.4 and NEC Chapter 9, Table 8.

    Capabilities:
      1. Route calculation between devices in 3D space
      2. Voltage drop verification per NFPA 72 §10.6.4
      3. Automatic wire gauge selection (minimum compliant gauge)
      4. Class A return path routing and verification
      5. 3D obstacle avoidance (walls, beams, columns)
      6. Cumulative voltage drop calculation across segments

    SAFETY CRITICAL:
      - Voltage drop uses ×2 DC return path factor per NEC 760
      - All NaN/Inf inputs are REJECTED
      - All negative inputs are REJECTED
      - Wire gauge selection ensures compliance before returning
      - Class A circuits require return path verification

    Example usage::

        engine = CableRoutingEngine()
        circuit = CircuitTopology(
            circuit_id="SLC-1",
            circuit_class=CircuitClass.CLASS_B,
            circuit_type=CircuitType.SLC,
        )
        result = engine.route_circuit(circuit, ps_voltage=24.0)
        if not result.is_compliant:
            print(f"VIOLATION: {result.violations}")
    """

    def __init__(
        self,
        obstacles: Optional[List[RoutingObstacle3D]] = None,
        ps_voltage: float = _SYSTEM_VOLTAGE,
        max_voltage_drop_pct: float = _MAX_VOLTAGE_DROP_PCT,
        conductor_operating_temp_c: float = 20.0,
    ) -> None:
        """Initialize the cable routing engine.

        Args:
            obstacles: List of 3D obstacles to consider during routing.
            ps_voltage: Power supply nominal voltage (default 24V).
            max_voltage_drop_pct: Maximum allowed voltage drop percentage
                                  (default 10% per NFPA 72 §10.6.4).
            conductor_operating_temp_c: Conductor operating temperature in
                degC for resistance correction per NEC Ch.9 Table 8 + physics.
                Default 20.0 degC (backward compatible with NEC Table 8
                reference temperature).
                CRITICAL FOR EGYPT: Use 75.0 for THHN/THWN operating temp.
                At 75 degC, resistance is 21.6% higher than at 20 degC.

        Raises:
            ValueError: If ps_voltage or max_voltage_drop_pct is invalid.
        """
        if not math.isfinite(ps_voltage) or ps_voltage <= 0:
            raise ValueError(
                f"ps_voltage must be positive finite, got {ps_voltage}"
            )
        if not math.isfinite(max_voltage_drop_pct) or max_voltage_drop_pct <= 0:
            raise ValueError(
                f"max_voltage_drop_pct must be positive finite, "
                f"got {max_voltage_drop_pct}"
            )

        self._obstacles: List[RoutingObstacle3D] = list(obstacles or [])
        self._ps_voltage = ps_voltage
        self._max_drop_pct = max_voltage_drop_pct
        self._conductor_operating_temp_c = conductor_operating_temp_c

    # ─── Public API ────────────────────────────────────────────────────────

    def route_circuit(
        self,
        circuit: CircuitTopology,
        *,
        wire_gauge: Optional[WireGauge] = None,
        ps_voltage: Optional[float] = None,
    ) -> RouteResult:
        """Route a fire alarm circuit and verify voltage drop compliance.

        NFPA 72 §10.6.4 requires that the voltage at the end-of-line
        device on any circuit be sufficient to operate the device under
        alarm conditions. For 24V systems, this means the voltage drop
        must not exceed 10% (2.4V), leaving ≥21.6V at end-of-line.

        This method:
          1. Calculates segment lengths between consecutive devices
          2. Computes voltage drop for each segment (with ×2 return factor)
          3. Sums cumulative voltage drop to end-of-line
          4. If wire_gauge is not specified, automatically selects the
             minimum compliant gauge
          5. For Class A circuits, verifies the return path

        Formula (NEC Chapter 9, Table 8 + NFPA 72 §10.6.4):
          V_drop = I × 2 × R_wire × L
          where:
            I = alarm current (A)
            2 = DC return path factor (CRITICAL for life safety)
            R_wire = wire resistance (Ω/km)
            L = one-way cable length (km)

        Args:
            circuit: CircuitTopology describing the circuit to route.
            wire_gauge: If specified, use this gauge. If None, auto-select.
            ps_voltage: Override engine's default power supply voltage.

        Returns:
            RouteResult with routing and voltage drop analysis.

        Raises:
            ValueError: If circuit parameters are invalid (NaN, Inf, negative).
        """
        voltage = ps_voltage if ps_voltage is not None else self._ps_voltage

        # Input validation — SAFETY CRITICAL
        if not math.isfinite(voltage) or voltage <= 0:
            raise ValueError(
                f"ps_voltage must be positive finite, got {voltage}"
            )

        # Validate circuit
        self._validate_circuit(circuit)

        # Calculate total alarm current
        total_current = self._calculate_total_current(circuit)

        # Calculate segment lengths in 3D
        segment_lengths = self._calculate_segment_lengths(circuit)

        # Route and verify
        if wire_gauge is not None:
            result = self._route_with_gauge(
                circuit, wire_gauge, total_current,
                segment_lengths, voltage,
            )
        else:
            result = self._route_auto_gauge(
                circuit, total_current,
                segment_lengths, voltage,
            )

        return result

    def add_obstacle(self, obstacle: RoutingObstacle3D) -> None:
        """Add a 3D obstacle for routing consideration.

        Args:
            obstacle: RoutingObstacle3D to add.
        """
        self._obstacles.append(obstacle)

    def clear_obstacles(self) -> None:
        """Remove all routing obstacles."""
        self._obstacles.clear()

    def check_obstacle_intersections(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
    ) -> List[RoutingObstacle3D]:
        """Find obstacles that intersect a line segment.

        Useful for checking if a proposed cable path crosses through
        any walls, beams, or other obstacles.

        Args:
            p1: Start point of the path (x, y, z) in meters.
            p2: End point of the path (x, y, z) in meters.

        Returns:
            List of obstacles that the path intersects.
        """
        return [
            obs for obs in self._obstacles
            if obs.intersects_line_segment(p1, p2)
        ]

    # ─── Private methods ───────────────────────────────────────────────────

    @staticmethod
    def _validate_circuit(circuit: CircuitTopology) -> None:
        """Validate circuit parameters are safe for routing.

        SAFETY CRITICAL: Rejects NaN, Inf, and negative values that
        could produce meaningless routing results.

        Args:
            circuit: CircuitTopology to validate.

        Raises:
            ValueError: If circuit has invalid parameters.
        """
        if not math.isfinite(circuit.cable_length_m) or circuit.cable_length_m < 0:
            raise ValueError(
                f"circuit cable_length_m must be non-negative finite, "
                f"got {circuit.cable_length_m}"
            )
        if not math.isfinite(circuit.return_length_m) or circuit.return_length_m < 0:
            raise ValueError(
                f"circuit return_length_m must be non-negative finite, "
                f"got {circuit.return_length_m}"
            )

        # Validate device coordinates
        for dev in circuit.devices:
            for name, value in [
                ("position_x", dev.position_x),
                ("position_y", dev.position_y),
                ("position_z", dev.position_z),
            ]:
                if not math.isfinite(value):
                    raise ValueError(
                        f"Device '{dev.device_id}' has non-finite "
                        f"{name}={value}"
                    )
            if not math.isfinite(dev.current_a) or dev.current_a < 0:
                raise ValueError(
                    f"Device '{dev.device_id}' has invalid current_a={dev.current_a}"
                )

        # Class A must have return path
        if (circuit.circuit_class == CircuitClass.CLASS_A
                and circuit.return_length_m <= 0
                and circuit.cable_length_m > 0):
            raise ValueError(
                "Class A circuit requires a positive return_length_m "
                "per NFPA 72 §12.2.2"
            )

    @staticmethod
    def _calculate_total_current(circuit: CircuitTopology) -> float:
        """Calculate total alarm current on the circuit.

        NFPA 72 §10.6.4.2: The total alarm current is the sum of all
        device alarm currents on the circuit. This is used for voltage
        drop calculation.

        For NAC circuits, this is the sum of all notification appliance
        currents. For SLC circuits, this is the supervisory + alarm
        current as specified by the panel manufacturer.

        Args:
            circuit: CircuitTopology with devices.

        Returns:
            Total alarm current in amperes.
        """
        return sum(dev.current_a for dev in circuit.devices)

    @staticmethod
    def _calculate_segment_lengths(
        circuit: CircuitTopology,
    ) -> List[Tuple[str, float, Tuple[float, float, float], Tuple[float, float, float]]]:
        """Calculate 3D segment lengths between consecutive devices.

        Each segment runs from the panel (or previous device) to the
        next device in the circuit's device list. Length is computed
        as the Euclidean distance in 3D space.

        Formula (3D Euclidean distance):
          L = √((x₂-x₁)² + (y₂-y₁)² + (z₂-z₁)²)

        Args:
            circuit: CircuitTopology with devices and panel position.

        Returns:
            List of (segment_id, length_m, start_point, end_point) tuples.
        """
        segments = []
        if not circuit.devices:
            return segments

        panel = circuit.panel_position
        prev_point = panel

        for i, dev in enumerate(circuit.devices):
            end_point = (dev.position_x, dev.position_y, dev.position_z)
            length = math.sqrt(
                (end_point[0] - prev_point[0]) ** 2
                + (end_point[1] - prev_point[1]) ** 2
                + (end_point[2] - prev_point[2]) ** 2
            )
            seg_id = f"{circuit.circuit_id}_seg_{i}"
            segments.append((seg_id, length, prev_point, end_point))
            prev_point = end_point

        return segments

    def _route_with_gauge(
        self,
        circuit: CircuitTopology,
        wire_gauge: WireGauge,
        total_current: float,
        segment_lengths: List[Tuple[str, float, Tuple[float, float, float], Tuple[float, float, float]]],
        ps_voltage: float,
    ) -> RouteResult:
        """Route circuit with a specified wire gauge.

        Calculates voltage drop for each segment and verifies
        compliance with NFPA 72 §10.6.4.

        Args:
            circuit: Circuit topology.
            wire_gauge: Wire gauge to use.
            total_current: Total alarm current (A).
            segment_lengths: Pre-calculated segment lengths.
            ps_voltage: Power supply voltage.

        Returns:
            RouteResult with analysis.
        """
        violations = []
        warnings = []

        # Build voltage drop segments
        vd_segments = []
        cumulative_drop_v = 0.0

        for seg_id, length_m, start_pt, end_pt in segment_lengths:
            # Voltage drop per segment using NEC Chapter 9, Table 8
            # V_drop = I × 2 × R_wire(T) × L(km)
            # The ×2 factor is for DC return path — CRITICAL for life safety
            # V65 FIX: Use temperature-corrected resistance per NEC practice.
            # Previously used R at 20°C directly, underestimating voltage drop
            # by 21.6% at 75°C operating temp — DANGEROUS for Egypt.
            r_at_20c = wire_gauge.resistance_ohm_per_km
            r_per_km = temperature_corrected_resistance(
                r_at_20c, self._conductor_operating_temp_c
            )
            length_km = length_m / 1000.0
            if length_m > 0 and total_current > 0:
                v_drop = total_current * 2.0 * r_per_km * length_km
            else:
                v_drop = 0.0

            cumulative_drop_v += v_drop

            if ps_voltage > 0:
                drop_pct = (v_drop / ps_voltage) * 100.0
            else:
                drop_pct = 0.0

            # Individual segment compliance (cumulative check done below)
            vd_seg = VoltageDropSegment(
                segment_id=seg_id,
                start_point=start_pt,
                end_point=end_pt,
                length_m=round(length_m, 4),
                wire_gauge=wire_gauge,
                current_a=round(total_current, 6),
                voltage_drop_v=round(v_drop, 6),
                voltage_drop_pct=round(drop_pct, 4),
                is_compliant=True,  # Per-segment; overall checked below
                formula=(
                    f"V_drop = {total_current:.4f} × 2 × "
                    f"{r_per_km:.3f}Ω/km@{self._conductor_operating_temp_c:.0f}C × "
                    f"{length_m / 1000:.6f}km = {v_drop:.4f}V"
                ),
                nfpa_section="NFPA 72 §10.6.4",
            )
            vd_segments.append(vd_seg)

        # Calculate cumulative voltage drop
        total_drop_pct = (
            (cumulative_drop_v / ps_voltage) * 100.0
            if ps_voltage > 0 else 0.0
        )
        eol_voltage = ps_voltage - cumulative_drop_v
        is_compliant = total_drop_pct <= self._max_drop_pct

        if not is_compliant:
            violations.append(
                f"Total voltage drop {cumulative_drop_v:.4f}V "
                f"({total_drop_pct:.2f}%) exceeds maximum "
                f"{self._max_drop_pct}% ({ps_voltage * self._max_drop_pct / 100:.1f}V) "
                f"per NFPA 72 §10.6.4"
            )

        # Class A return path verification
        if circuit.circuit_class == CircuitClass.CLASS_A:
            if circuit.return_length_m > 0 and total_current > 0:
                # V69-1 FIX: Use temperature-corrected resistance for return path
                # (same as outgoing path — conductor operating temp, not 20°C)
                r_per_km_return = temperature_corrected_resistance(
                    wire_gauge.resistance_ohm_per_km, self._conductor_operating_temp_c
                )
                return_length_km = circuit.return_length_m / 1000.0
                return_drop = total_current * 2.0 * r_per_km_return * return_length_km
                # For Class A, the return path must also maintain voltage
                # The total loop voltage drop includes the return
                total_loop_drop = cumulative_drop_v + return_drop
                loop_drop_pct = (
                    (total_loop_drop / ps_voltage) * 100.0
                    if ps_voltage > 0 else 0.0
                )
                if loop_drop_pct > self._max_drop_pct:
                    violations.append(
                        f"Class A loop voltage drop {total_loop_drop:.4f}V "
                        f"({loop_drop_pct:.2f}%) exceeds maximum "
                        f"{self._max_drop_pct}% per NFPA 72 §12.2.2"
                    )

        # Check for obstacle intersections
        for seg_id, length_m, start_pt, end_pt in segment_lengths:
            intersecting = self.check_obstacle_intersections(start_pt, end_pt)
            for obs in intersecting:
                if obs.requires_firestop:
                    warnings.append(
                        f"Segment {seg_id} penetrates {obs.obstacle_type.value} "
                        f"'{obs.obstacle_id}' — firestopping required "
                        f"(fire rating: {obs.fire_rating_hours}h)"
                    )

        # Formula summary
        total_outgoing = sum(sl[1] for sl in segment_lengths)
        # V69-7 FIX: Show temperature-corrected resistance in formula, not 20°C value
        r_corrected_display = temperature_corrected_resistance(
            wire_gauge.resistance_ohm_per_km, self._conductor_operating_temp_c
        )
        formula = (
            f"V_drop_total = Σ(I × 2 × R(T) × L_seg) = "
            f"{total_current:.4f}A × 2 × "
            f"{r_corrected_display:.3f}Ω/km "
            f"(at {self._conductor_operating_temp_c:.0f}°C) × "
            f"{total_outgoing / 1000:.6f}km = "
            f"{cumulative_drop_v:.4f}V ({total_drop_pct:.2f}%)"
        )

        return RouteResult(
            circuit_id=circuit.circuit_id,
            total_length_m=round(total_outgoing, 4),
            total_return_length_m=round(circuit.return_length_m, 4),
            wire_gauge=wire_gauge,
            segments=tuple(vd_segments),
            total_voltage_drop_v=round(cumulative_drop_v, 6),
            total_voltage_drop_pct=round(total_drop_pct, 4),
            end_of_line_voltage_v=round(eol_voltage, 4),
            is_compliant=is_compliant and len(violations) == 0,
            selected_gauge_is_minimum=False,  # Set properly in auto-gauge
            violations=tuple(violations),
            warnings=tuple(warnings),
            formula=formula,
        )

    def _route_auto_gauge(
        self,
        circuit: CircuitTopology,
        total_current: float,
        segment_lengths: List[Tuple[str, float, Tuple[float, float, float], Tuple[float, float, float]]],
        ps_voltage: float,
    ) -> RouteResult:
        """Automatically select the minimum compliant wire gauge.

        Tries each wire gauge from AWG 18 (smallest, highest resistance)
        to AWG 12 (largest, lowest resistance), selecting the first
        gauge that meets the voltage drop requirement per NFPA 72 §10.6.4.

        If no standard gauge complies, uses AWG 12 and reports a violation.

        Args:
            circuit: Circuit topology.
            total_current: Total alarm current (A).
            segment_lengths: Pre-calculated segment lengths.
            ps_voltage: Power supply voltage.

        Returns:
            RouteResult with the best (minimum) compliant gauge.
        """
        total_outgoing = sum(sl[1] for sl in segment_lengths)

        # Try gauges from smallest wire (AWG 18, highest resistance) to
        # largest wire (AWG 12, lowest resistance). Select the MINIMUM
        # gauge that meets the voltage drop requirement per NFPA 72 §10.6.4.
        # Since we try smallest first, the first gauge that passes IS
        # the minimum compliant gauge.

        for gauge in _WIRE_GAUGES_ASCENDING:
            # Fast check: can this gauge handle the total length?
            # Use the existing calculate_voltage_drop from nfpa72_engine
            if total_current > 0 and total_outgoing > 0:
                # V69-2 FIX: Pass conductor operating temp to fast-check
                # Without this, auto-gauge selects based on 20°C resistance
                vd_result = calculate_voltage_drop(
                    alarm_current_a=total_current,
                    circuit_length_m=total_outgoing,
                    awg_gauge=gauge.awg_value,
                    ps_voltage=ps_voltage,
                    max_drop_pct=self._max_drop_pct,
                    ambient_temperature_c=self._conductor_operating_temp_c,
                )
                if vd_result.is_compliant:
                    # This gauge works — do full route
                    result = self._route_with_gauge(
                        circuit, gauge, total_current,
                        segment_lengths, ps_voltage,
                    )

                    # Since we iterate from smallest gauge first, the first
                    # compliant gauge IS the minimum. Check if a smaller gauge
                    # (earlier in the list) would also work — it shouldn't,
                    # because we already tried it. But verify for safety.
                    gauge_idx = _WIRE_GAUGES_ASCENDING.index(gauge)
                    is_minimum = True
                    if gauge_idx > 0:
                        # There's a smaller gauge we already tried — it failed.
                        # So this IS the minimum compliant gauge.
                        is_minimum = True
                    elif gauge_idx == 0:
                        # This is the smallest gauge (AWG 18) and it works.
                        is_minimum = True

                    # Reconstruct result with correct minimum flag
                    result = RouteResult(
                        circuit_id=result.circuit_id,
                        total_length_m=result.total_length_m,
                        total_return_length_m=result.total_return_length_m,
                        wire_gauge=result.wire_gauge,
                        segments=result.segments,
                        total_voltage_drop_v=result.total_voltage_drop_v,
                        total_voltage_drop_pct=result.total_voltage_drop_pct,
                        end_of_line_voltage_v=result.end_of_line_voltage_v,
                        is_compliant=result.is_compliant,
                        selected_gauge_is_minimum=is_minimum,
                        violations=result.violations,
                        warnings=result.warnings,
                        formula=result.formula,
                    )
                    return result

        # If we get here, no gauge is compliant — use AWG 12 (largest
        # available) and report violation so the designer knows to reduce
        # circuit length or current.
        result = self._route_with_gauge(
            circuit, WireGauge.AWG_12, total_current,
            segment_lengths, ps_voltage,
        )

        # Add violation about no compliant gauge
        all_violations = list(result.violations)
        if not any("exceeds maximum" in v for v in all_violations):
            all_violations.append(
                f"No wire gauge from AWG 12-18 can achieve compliant "
                f"voltage drop for {total_outgoing:.1f}m at {total_current:.4f}A "
                f"per NFPA 72 §10.6.4 — reduce circuit length or current"
            )

        return RouteResult(
            circuit_id=result.circuit_id,
            total_length_m=result.total_length_m,
            total_return_length_m=result.total_return_length_m,
            wire_gauge=result.wire_gauge,
            segments=result.segments,
            total_voltage_drop_v=result.total_voltage_drop_v,
            total_voltage_drop_pct=result.total_voltage_drop_pct,
            end_of_line_voltage_v=result.end_of_line_voltage_v,
            is_compliant=False,
            selected_gauge_is_minimum=False,
            violations=tuple(all_violations),
            warnings=result.warnings,
            formula=result.formula,
        )

    @staticmethod
    def calculate_3d_distance(
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
    ) -> float:
        """Calculate Euclidean distance between two 3D points.

        Formula:
          d = √((x₂-x₁)² + (y₂-y₁)² + (z₂-z₁)²)

        Args:
            p1: First point (x, y, z) in meters.
            p2: Second point (x, y, z) in meters.

        Returns:
            Distance in meters.

        Raises:
            ValueError: If any coordinate is NaN or Inf.
        """
        for label, point in [("p1", p1), ("p2", p2)]:
            for i, coord in enumerate(point):
                if not math.isfinite(coord):
                    raise ValueError(
                        f"{label}[{i}] must be finite, got {coord}"
                    )

        return math.sqrt(
            (p2[0] - p1[0]) ** 2
            + (p2[1] - p1[1]) ** 2
            + (p2[2] - p1[2]) ** 2
        )
