"""
fireai/core/bps_allocator.py
=============================
NAC Booster Power Supply (BPS) Auto-Allocator for High-Rise Buildings.

V19.1 FIX: Added iterative voltage drop calculation along the circuit path.
The original V19 implementation only checked current capacity (amperage)
and distributed boosters by floor-level current aggregation.  This is
INSUFFICIENT because even when total current fits within the BPS rating,
voltage drops along the wire due to cumulative resistance.  At the
end of a long NAC circuit, the voltage may fall below the minimum
operating voltage of notification appliances (typically 16 VDC for a
24 VDC system), causing horns and strobes to fail silently.

Physics:
  Voltage drop across a DC circuit wire:
    V_drop = 2 × I × R × L
  where:
    - Factor 2 accounts for the return path (DC circuits)
    - I is the aggregate downstream current (amps)
    - R is the wire resistance per metre (ohm/m)
    - L is the segment length (metres)

  Wire resistance per NFPA 72 §10.14 / NEC Chapter 9 Table 8:
    AWG 14: 0.0103 ohm/m  (8.282 ohm/1000ft)
    AWG 12: 0.0065 ohm/m  (5.211 ohm/1000ft)
    AWG 10: 0.0041 ohm/m  (3.277 ohm/1000ft)

Code references:
  - NFPA 72-2022 §10.6   — Power supplies
  - NFPA 72-2022 §10.14  — Voltage drop limitations
  - NFPA 72-2022 §18.5.5 — Synchronization of notification appliances
  - NFPA 72-2022 §21.2   — Emergency voice/alarm communication systems
  - NEC Chapter 9 Table 8 — Conductor properties (DC resistance)
  - UL 864 10th Edition  — Control units and accessories

Provenance:
  Returns ``DecisionProvenance`` via the ``.new()`` factory when
  ``src.v8_core`` is available; degrades gracefully to plain dict otherwise.
"""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        DecisionProvenance,
        RuleApplied,
        Violation,
        ConfidenceScore,
        ConfidenceLevel,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Default FACP PSU NAC current limit (amps)
DEFAULT_FACP_LIMIT_AMPS: float = 8.0

# Default BPS (booster power supply) per-unit capacity (amps)
DEFAULT_BOOSTER_CAPACITY_AMPS: float = 6.0

# Default BPS offset from stairwell centroid for placement (metres)
DEFAULT_BPS_OFFSET_X: float = 1.5
DEFAULT_BPS_OFFSET_Y: float = 1.0

# Source voltage (24 VDC nominal for fire alarm NAC circuits)
DEFAULT_SOURCE_VOLTAGE: float = 24.0

# Minimum terminal voltage for notification appliances (VDC)
# Per NFPA 72-2022 §10.14.1: "All circuits shall be designed such that
# the voltage at the farthest device under maximum load is not less than
# 85 percent of the nominal system voltage."
# For 24 VDC nominal: 0.85 × 24.0 = 20.4 VDC.
# NOTE: UL-listed appliances may operate down to 16 VDC (appliance minimum),
# but NFPA 72 §10.14.1 imposes the stricter 85% requirement on CIRCUIT DESIGN.
# Using 16V would allow circuits that violate NFPA 72 — end-of-line devices
# could have voltage between 16V and 20.4V, which NFPA deems non-compliant.
DEFAULT_MIN_TERMINAL_VOLTAGE: float = 20.4

# Wire resistance table (ohm per metre) per NEC Chapter 9 Table 8
# Copper conductors, uncoated, DC resistance at 75°C
# V43 FIX: AWG 18 and AWG 16 values were ~10% too low (matched ~50°C, not 75°C).
# Correct values per NEC Ch.9 Table 8: AWG 18 solid = 25.5 Ω/km, AWG 16 solid = 16.1 Ω/km.
# AWG 14/12/10 values are reasonable for stranded conductors (slightly conservative).
WIRE_RESISTANCE_OHM_PER_M: Dict[int, float] = {
    18: 0.0255,  # 25.5 ohm/km (NEC Ch.9 Table 8 solid at 75°C)
    16: 0.0161,  # 16.1 ohm/km (NEC Ch.9 Table 8 solid at 75°C)
    14: 0.0103,  # 10.3 ohm/km  (standard fire alarm, stranded at 75°C)
    12: 0.0065,  #  6.5 ohm/km  (stranded at 75°C)
    10: 0.0041,  #  4.1 ohm/km  (stranded at 75°C)
}

# Default wire gauge for NAC circuits
DEFAULT_AWG: int = 14

# Citations
_CITE_NFPA72_10_6 = "NFPA 72-2022 §10.6"
_CITE_NFPA72_10_14 = "NFPA 72-2022 §10.14"
_CITE_NFPA72_18_5_5 = "NFPA 72-2022 §18.5.5"
_CITE_NFPA72_21_2 = "NFPA 72-2022 §21.2"
_CITE_NEC_CH9 = "NEC Chapter 9 Table 8"
_CITE_UL864 = "UL 864 10th Ed."


@dataclass(frozen=True)
class FloorNACProfile:
    """NAC current demand profile for a single floor."""
    floor_name: str
    nac_current: float
    centroid_location: Tuple[float, float] = (0.0, 0.0)
    level_z: float = 0.0


@dataclass(frozen=True)
class BoosterAllocation:
    """Represents a single deployed BPS panel."""
    booster_id: str
    x: float
    y: float
    floors_covered: List[str]
    peak_load: float


class NACBoosterAllocator:
    """Automatically distributes NAC load across FACP and BPS panels
    for high-rise and large-footprint buildings.

    V19.1 ENHANCEMENT: Two-pass allocation:

      **Pass 1 — Current capacity**: Waterfall load-balancing by floor
      current, same as V19.

      **Pass 2 — Voltage drop validation**: Iterative segment-by-segment
      voltage drop calculation along the NAC circuit path.  If the
      terminal voltage at any device falls below the minimum, a BPS is
      inserted at the choke-point to regenerate a clean 24 VDC source.

    Usage::

        allocator = NACBoosterAllocator(facp_limit_amps=10.0)
        result = allocator.allocate_boosters_across_floors(floor_data=[...])
    """

    def __init__(
        self,
        facp_limit_amps: float = DEFAULT_FACP_LIMIT_AMPS,
        booster_capacity_amps: float = DEFAULT_BOOSTER_CAPACITY_AMPS,
        bps_offset_x: float = DEFAULT_BPS_OFFSET_X,
        bps_offset_y: float = DEFAULT_BPS_OFFSET_Y,
        source_voltage: float = DEFAULT_SOURCE_VOLTAGE,
        min_terminal_voltage: float = DEFAULT_MIN_TERMINAL_VOLTAGE,
        default_awg: int = DEFAULT_AWG,
    ) -> None:
        self.facp_limit = facp_limit_amps
        self.booster_limit = booster_capacity_amps
        self.bps_offset_x = bps_offset_x
        self.bps_offset_y = bps_offset_y
        self.source_voltage = source_voltage
        self.min_terminal_voltage = min_terminal_voltage
        self.default_awg = default_awg

    def allocate_boosters_across_floors(
        self,
        floor_data: List[Dict[str, Any]],
    ) -> Any:
        """Distribute NAC load across FACP and auto-deployed BPS panels.

        Pass 1: Current-capacity waterfall allocation.
        Pass 2: Voltage-drop validation (if devices_line provided).
        """
        violations: list = []
        panel_allocation: List[Dict[str, Any]] = []
        cumulative_load: float = 0.0
        active_booster_id: int = 1
        current_load: float = 0.0

        sorted_floors = sorted(
            floor_data,
            key=lambda x: float(x.get("level_z", 0.0)),
        )

        for f_info in sorted_floors:
            f_name = f_info.get("floor_name", "UNKNOWN")
            f_current = float(f_info.get("nac_current", 0.0))
            f_centroid = f_info.get("centroid_location", (0.0, 0.0))
            cumulative_load += f_current

            if f_current > self.booster_limit:
                desc = (
                    f"Floor '{f_name}' current ({f_current:.2f} A) "
                    f"inherently exceeds single BPS booster limit "
                    f"({self.booster_limit:.1f} A). Requires internal "
                    f"NAC sub-division on this floor."
                )
                if Violation is not None:
                    violations.append(Violation(
                        severity="CRITICAL",
                        citation=f"{_CITE_NFPA72_10_6} / {_CITE_NFPA72_21_2}",
                        description=desc,
                    ))
                else:
                    violations.append({
                        "severity": "CRITICAL",
                        "citation": f"{_CITE_NFPA72_10_6} / {_CITE_NFPA72_21_2}",
                        "description": desc,
                    })
                logger.critical(desc)

            zone_capacity = (
                self.facp_limit if not panel_allocation
                else self.booster_limit
            )

            if current_load + f_current > zone_capacity:
                pos = f_centroid if isinstance(f_centroid, tuple) else (0.0, 0.0)
                new_booster: Dict[str, Any] = {
                    "type": "NAC_BOOSTER_BPS",
                    "id": f"BPS-0{active_booster_id}",
                    "x": pos[0] + self.bps_offset_x,
                    "y": pos[1] + self.bps_offset_y,
                    "floors_covered": [f_name],
                    "peak_load": f_current,
                }
                panel_allocation.append(new_booster)
                current_load = f_current
                active_booster_id += 1
            else:
                current_load += f_current
                if panel_allocation:
                    panel_allocation[-1]["floors_covered"].append(f_name)
                    panel_allocation[-1]["peak_load"] = current_load

        # SYNC_MODULE for multi-BPS
        if len(panel_allocation) > 0:
            sync_module: Dict[str, Any] = {
                "type": "SYNC_MODULE",
                "description": (
                    "Mandatory Global Notification Synchronization "
                    f"({_CITE_NFPA72_18_5_5})"
                ),
                "target": "ALL BPS",
            }
            panel_allocation.insert(0, sync_module)

        safe = len(violations) == 0

        # V43 FIX: Move Pass 2 voltage drop validation BEFORE provenance
        # construction. The previous code structure had an early return inside
        # the provenance try block (line ~309), which meant Pass 2 never
        # executed in production (only on ImportError). This rendered the
        # entire V20.2 voltage-drop safety enhancement inoperative.
        # NFPA 72 §10.14 requires voltage drop validation, not just current.
        voltage_result = None
        all_devices_line: List[Dict[str, Any]] = []
        for f_info in sorted_floors:
            dev_line = f_info.get("devices_line")
            if dev_line and isinstance(dev_line, list):
                all_devices_line.extend(dev_line)

        if all_devices_line:
            voltage_result = self.validate_voltage_drop(all_devices_line)
            # Merge voltage violations into main violations list
            v_violations = []
            if isinstance(voltage_result, dict):
                v_violations = voltage_result.get("violations", [])
            elif hasattr(voltage_result, "violations"):
                v_violations = voltage_result.violations or []
            if v_violations:
                violations.extend(v_violations)
                safe = False
        else:
            # V20.2: CRITICAL WARNING when voltage drop validation
            # cannot be performed — current-only allocation is incomplete.
            desc = (
                "VOLTAGE DROP VALIDATION NOT PERFORMED: No devices_line "
                "data provided on any floor. BPS allocation is based on "
                "current capacity ONLY. Terminal voltage at end-of-line "
                "devices may be below minimum — horns/strobes may fail "
                "during fire. Provide devices_line per floor for full "
                "Pass 1 + Pass 2 allocation per NFPA 72 §10.14."
            )
            if Violation is not None:
                violations.append(Violation(
                    severity="CRITICAL",
                    citation=f"{_CITE_NFPA72_10_14}",
                    description=desc,
                ))
            else:
                violations.append({
                    "severity": "CRITICAL",
                    "citation": _CITE_NFPA72_10_14,
                    "description": desc,
                })
            safe = False

        # Build provenance result
        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NFPA72_18_5_5,
                        constant_id="STROBE_SYNC",
                        value_used=1.0,
                        unit="BOOLEAN",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA72_10_6,
                        constant_id="PSU_BPS_SPLIT",
                        value_used=self.booster_limit,
                        unit="AMPS",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="distributed_power_routing",
                    value={
                        "boosters": panel_allocation,
                        "total_current": round(cumulative_load, 4),
                        "facp_native_load": round(
                            cumulative_load - sum(
                                b.get("peak_load", 0.0)
                                for b in panel_allocation
                                if b.get("type") == "NAC_BOOSTER_BPS"
                            ),
                            4,
                        ),
                        "num_boosters": sum(
                            1 for b in panel_allocation
                            if b.get("type") == "NAC_BOOSTER_BPS"
                        ),
                        "sync_required": len(panel_allocation) > 1,
                    },
                    inputs={
                        "floors_analyzed": len(floor_data),
                    },
                    rules_applied=rules,
                    algorithm={"name": "WaterfallLoadBalancer", "version": "v19.1"},
                    confidence=conf,
                    selected_because=(
                        "Voltage/Current aggregation dynamically fragmented "
                        "into topological autonomous zones satisfying "
                        "structural wire limitations per NFPA 72 §10.6 / §21.2"
                    ),
                    violations=violations if violations else None,
                )
            except Exception:
                pass

        result_dict = {
            "decision_type": "distributed_power_routing",
            "value": {
                "boosters": panel_allocation,
                "total_current": round(cumulative_load, 4),
            },
            "inputs": {"floors_analyzed": len(floor_data)},
            "safe": safe,
            "violations": violations,
        }
        if voltage_result is not None:
            if isinstance(voltage_result, dict):
                result_dict["voltage_drop_validation"] = voltage_result
            elif hasattr(voltage_result, "to_dict"):
                result_dict["voltage_drop_validation"] = voltage_result.to_dict()
        return result_dict

    def validate_voltage_drop(
        self,
        devices_line: List[Dict[str, Any]],
        awg: int = DEFAULT_AWG,
        max_cable_length_m: float = 300.0,
        source_location: Optional[Tuple[float, float]] = None,
    ) -> Any:
        """Pass 2: Iterative segment-by-segment voltage drop validation.

        Processes a NAC circuit from source to end-of-line, tracking
        cumulative voltage drop.  When terminal voltage falls below the
        minimum, a BPS insertion point is generated.

        Each element of *devices_line* must be a dict with:
        - ``id`` (str): Device identifier.
        - ``x``, ``y`` (float): 2D coordinates (metres).
        - ``inrush_a`` (float, optional): Device inrush current (amps).
          Defaults to 0.2 A.
        - ``steady_a`` (float, optional): Device steady-state current.
          Defaults to 0.1 A.

        Args:
            devices_line: Ordered list of devices on the NAC circuit
                from source (FACP) to end-of-line.
            awg: Wire gauge per NEC Chapter 9 Table 8.
            max_cable_length_m: Maximum continuous branch length.
            source_location: (x, y) coordinates of the FACP source panel.
                When provided, voltage drop from FACP to the first device
                is calculated.  When None, the first device is assumed
                to be at the FACP (zero distance) — this is the legacy
                behavior and may underestimate total voltage drop.

        Returns:
            ``DecisionProvenance`` with BPS insertion points for voltage
            regeneration, or plain dict.
        """
        violations: list = []
        booster_placements: List[Dict[str, Any]] = []

        # V51 FIX: NaN/Inf validation for critical device inputs.
        # NaN comparisons always return False, bypassing ALL safety checks:
        #   NaN > 0 = False (no voltage drop calculated)
        #   NaN < 20.4 = False (no low-voltage violation detected)
        # This allows non-physical inputs to silently pass through the
        # entire validation pipeline, producing a false PASS result.
        for idx, dev in enumerate(devices_line):
            for field in ("x", "y", "inrush_a", "steady_a"):
                val = dev.get(field)
                if val is not None:
                    try:
                        fval = float(val)
                    except (TypeError, ValueError):
                        fval = None
                    if fval is not None and (math.isnan(fval) or math.isinf(fval)):
                        desc = (
                            f"BPS-002: Device '{dev.get('id', f'DEV-{idx}')}' "
                            f"has {field}={val} (NaN or Inf). "
                            f"Non-physical device data produces unreliable voltage "
                            f"drop calculations. Per NFPA 72 §10.14, all circuit "
                            f"parameters must be physically valid."
                        )
                        logger.critical(desc)
                        if Violation is not None:
                            violations.append(Violation(
                                severity="CRITICAL",
                                citation=_CITE_NFPA72_10_14,
                                description=desc,
                            ))
                        else:
                            violations.append({
                                "severity": "CRITICAL",
                                "citation": _CITE_NFPA72_10_14,
                                "description": desc,
                            })

        # Get wire resistance
        # V48 FIX: Unknown AWG no longer silently falls back to AWG 14 (0.0103 Ω/m).
        # A thinner wire (e.g., AWG 22, ~0.026 Ω/m) would have 2.5× higher resistance,
        # UNDERESTIMATING voltage drop → end-of-line horns/strobes fail silently.
        if awg not in WIRE_RESISTANCE_OHM_PER_M:
            import logging as _log
            _log.getLogger(__name__).critical(
                "BPS-001: Unknown AWG gauge '%s' — no wire resistance data available. "
                "Using most conservative (highest resistance) known value. "
                "Per NEC Chapter 9 Table 8, provide a valid AWG gauge.",
                awg,
            )
            # Use the highest resistance (thinnest known wire = AWG 18 = 0.0255)
            ohm_per_m = max(WIRE_RESISTANCE_OHM_PER_M.values())
        else:
            ohm_per_m = WIRE_RESISTANCE_OHM_PER_M[awg]

        running_voltage = self.source_voltage
        # Aggregate downstream current (all devices from this point to EOL)
        running_current_tail = sum(
            float(d.get("inrush_a", 0.2)) for d in devices_line
        )
        running_length = 0.0

        # V51 FIX: FACP-to-first-device voltage drop.
        # Previously, last_pt started as None, so the first device always
        # had dist=0.0 regardless of its actual distance from the FACP.
        # In a high-rise building, the FACP may be on Floor 1 and the first
        # NAC device on Floor 30 (100+ metres away). This uncalculated drop
        # could be the largest single segment in the circuit.
        # When source_location is provided, use it as the initial last_pt
        # so the FACP-to-first-device segment is properly calculated.
        last_pt: Optional[Tuple[float, float]] = source_location

        for i, dev in enumerate(devices_line):
            curr_pt = (float(dev.get("x", 0.0)), float(dev.get("y", 0.0)))

            if last_pt is not None:
                dist = math.hypot(
                    curr_pt[0] - last_pt[0],
                    curr_pt[1] - last_pt[1],
                )
            else:
                dist = 0.0

            running_length += dist

            # V_drop = 2 × I × R × L  (DC return path)
            # Using downstream aggregate current for this segment
            if dist > 0 and running_current_tail > 0:
                segment_drop = 2.0 * dist * ohm_per_m * running_current_tail
                running_voltage -= segment_drop

            # Subtract this device's current from downstream tail
            dev_current = float(dev.get("inrush_a", 0.2))
            running_current_tail = max(0.0, running_current_tail - dev_current)
            last_pt = curr_pt

            # Check if voltage has collapsed below minimum
            if running_voltage < self.min_terminal_voltage:
                booster_placements.append({
                    "insert_node": curr_pt,
                    "at_device": dev.get("id", f"DEV-{i}"),
                    "terminal_voltage": round(running_voltage, 2),
                    "running_length_m": round(running_length, 1),
                })
                # Reset: BPS regenerates clean source voltage
                running_voltage = self.source_voltage
                running_length = 0.0

        # Check total circuit length
        if running_length > max_cable_length_m:
            desc = (
                f"NAC circuit total length ({running_length:.1f} m) exceeds "
                f"maximum branch distance ({max_cable_length_m:.0f} m) per "
                f"{_CITE_NFPA72_10_14}."
            )
            if Violation is not None:
                violations.append(Violation(
                    severity="CRITICAL",
                    citation=_CITE_NFPA72_10_14,
                    description=desc,
                ))
            else:
                violations.append({
                    "severity": "CRITICAL",
                    "citation": _CITE_NFPA72_10_14,
                    "description": desc,
                })

        # V20.2 FIX: Previous code: `safe = len(violations) == 0 and len(booster_placements) == 0`
        # This penalized valid BPS insertions — even when BPS correctly regenerated
        # voltage at choke points, `safe` was False. BPS insertions are a VALID
        # correction, not a failure. Only violations make the result unsafe.
        safe = len(violations) == 0

        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NFPA72_10_14,
                        constant_id="VDROP_CRITICAL",
                        value_used=self.min_terminal_voltage,
                        unit="Volts",
                    ),
                    RuleApplied(
                        citation=_CITE_NEC_CH9,
                        constant_id="WIRE_RESISTANCE",
                        value_used=ohm_per_m,
                        unit="ohm/m",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="voltage_drop_validation",
                    value={
                        "bps_insertions": booster_placements,
                        "cuts": len(booster_placements),
                        "source_voltage": self.source_voltage,
                        "min_terminal_voltage": self.min_terminal_voltage,
                        "wire_awg": awg,
                        "wire_resistance_ohm_per_m": ohm_per_m,
                        "total_length_m": round(running_length, 1),
                        "safe": safe,
                    },
                    inputs={
                        "devices_on_circuit": len(devices_line),
                    },
                    rules_applied=rules,
                    algorithm={
                        "name": "DynamicIterativeVoltageChipper",
                        "version": "v19.1",
                    },
                    confidence=conf,
                    selected_because=(
                        "Absolute precision on resistive current bleeding replaces "
                        "basic floor capacity grouping.  Iterative segment-by-segment "
                        f"voltage drop ensures terminal voltage ≥ {self.min_terminal_voltage} VDC."
                    ),
                    violations=violations if violations else None,
                )
            except Exception:
                pass

        return {
            "decision_type": "voltage_drop_validation",
            "value": {
                "bps_insertions": booster_placements,
                "cuts": len(booster_placements),
                "safe": safe,
            },
            "inputs": {"devices_on_circuit": len(devices_line)},
            "safe": safe,
            "violations": violations,
        }


__all__ = [
    "NACBoosterAllocator",
    "FloorNACProfile",
    "BoosterAllocation",
    "DEFAULT_FACP_LIMIT_AMPS",
    "DEFAULT_BOOSTER_CAPACITY_AMPS",
    "DEFAULT_SOURCE_VOLTAGE",
    "DEFAULT_MIN_TERMINAL_VOLTAGE",
    "WIRE_RESISTANCE_OHM_PER_M",
    "DEFAULT_AWG",
]
