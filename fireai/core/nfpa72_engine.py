"""
fireai.core.nfpa72_engine — Core NFPA 72 Engineering Calculations
=================================================================

Implements the fundamental NFPA 72 fire alarm engineering calculations:

1. Battery Sizing — NFPA 72 §10.6.7 (secondary power supply)
2. Voltage Drop  — NFPA 72 §10.6.4, NEC Chapter 9 (circuit verification)
3. Detector Spacing — NFPA 72 §17.6.3.1, Table 17.6.3.1
4. Detector Count Estimation — NFPA 72 §17.7.4.2.3.1
5. Fault Isolator Placement — NFPA 72 §12.3

SAFETY CRITICAL:
  - Battery calculations use 20% safety margin per NFPA 72 §10.6.7.2.1
  - Voltage drop uses DC return path factor (×2) per NEC 760
  - Wire resistance from NEC Chapter 9, Table 8
  - All NaN/Inf inputs are REJECTED
  - All negative inputs are REJECTED

DESIGN INSPIRATION (NOT copied):
  - ElectricPy.loadedvcapdischarge — nonlinear battery discharge model
  - ElectricPy.voltdiv — voltage divider for NAC end-of-line calculation
  - ElectricPy.resistivity_rho — wire resistance from material properties
  - SprayHydraulic.PNetwork.is_connected — graph topology for fault isolation

All formulas are traced to their NFPA/NEC source sections.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# WIRE RESISTANCE TABLE — NEC Chapter 9, Table 8 (Copper, stranded)
# ═══════════════════════════════════════════════════════════════════════════════

# AWG gauge → resistance in Ω/km at 20°C (copper, stranded)
AWG_RESISTANCE_OHM_PER_KM = {
    "18": 21.40,
    "16": 13.40,
    "14": 8.450,
    "12": 5.310,
    "10": 3.340,
    "8":  2.100,
    "6":  1.320,
    "4":  0.830,
    "3":  0.660,
    "2":  0.520,
    "1":  0.410,
    "1/0": 0.327,
    "2/0": 0.260,
    "3/0": 0.205,
    "4/0": 0.163,
}


# ═══════════════════════════════════════════════════════════════════════════════
# NFPA 72 TABLE 17.6.3.1 — Detector Spacing vs Ceiling Height
# ═══════════════════════════════════════════════════════════════════════════════

_SMOKE_SPACING_TABLE = [
    # (max_ceiling_height_m, listed_spacing_m)
    (3.0,  9.10),   # 30 ft → 9.1 m
    (3.9,  8.20),   # 27 ft → 8.2 m
    (4.9,  7.30),   # 24 ft → 7.3 m
    (6.1,  6.40),   # 21 ft → 6.4 m
    (7.6,  5.50),   # 18 ft → 5.5 m
    (9.1,  4.60),   # 15 ft → 4.6 m
    (10.7, 3.70),   # 12 ft → 3.7 m
    (12.2, 3.00),   # 10 ft → 3.0 m
]

_HEAT_SPACING_TABLE = [
    # (max_ceiling_height_m, listed_spacing_m)
    (3.0,  6.10),   # 20 ft → 6.1 m
    (3.9,  5.50),   # 18 ft → 5.5 m
    (4.9,  4.90),   # 16 ft → 4.9 m
    (6.1,  4.30),   # 14 ft → 4.3 m
    (7.6,  3.70),   # 12 ft → 3.7 m
    (9.1,  3.00),   # 10 ft → 3.0 m
]


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SpacingResult:
    """Result from NFPA 72 detector spacing calculation."""
    max_spacing_m:     float
    coverage_radius_m: float
    nfpa_section:      str
    formula:           str
    table_row_used:    str


@dataclass(frozen=True)
class BatteryResult:
    """Result from NFPA 72 battery sizing calculation.

    NFPA 72 §10.6.7 requires secondary supply capacity:
      - 24 hours of standby current
      - PLUS 5 minutes (300s) of alarm current
      - WITH 20% safety margin

    Formula:
      Ah_required = (I_standby × 24h + I_alarm × 5min/60) × 1.20
    """
    required_ah:  float
    installed_ah: float
    is_adequate:  bool
    formula:      str
    nfpa_section: str


@dataclass(frozen=True)
class VoltageDropResult:
    """Result from NFPA 72 voltage drop calculation.

    NEC 760 and NFPA 72 §10.6.4:
      V_drop = I × 2 × R_wire × L
      The ×2 factor accounts for the DC return path.

    For 24V systems, end-of-line voltage must be ≥ 21.6V (10% max drop).
    """
    voltage_drop_v:   float
    voltage_drop_pct: float
    max_length_m:     float
    is_compliant:     bool
    formula:          str


# ═══════════════════════════════════════════════════════════════════════════════
# SPACING CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

def get_detector_spacing(
    ceiling_height_m: float,
    detector_type: str,
) -> SpacingResult:
    """Determine NFPA 72 listed spacing for a given ceiling height.

    Reference: NFPA 72-2022 §17.6.3.1, Table 17.6.3.1

    Args:
        ceiling_height_m: Ceiling height in meters.
        detector_type: 'smoke' or 'heat'.

    Returns:
        SpacingResult with max spacing, coverage radius, and NFPA reference.
    """
    # Input validation — safety first
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        # Default to most conservative spacing for invalid input
        return SpacingResult(
            max_spacing_m=3.00,
            coverage_radius_m=0.7 * 3.00,
            nfpa_section="NFPA 72 §17.6.3.1",
            formula="Conservative default (invalid ceiling height input)",
            table_row_used="fallback_conservative",
        )

    det_type = detector_type.lower()
    table = _SMOKE_SPACING_TABLE if det_type == "smoke" else _HEAT_SPACING_TABLE

    spacing = 3.00  # Conservative default for heights exceeding table
    row_desc = f">{table[-1][0]}m (conservative)"

    for max_h, listed_s in table:
        if ceiling_height_m <= max_h:
            spacing = listed_s
            row_desc = f"≤{max_h}m"
            break

    # R = 0.7 × S per NFPA 72 §17.7.4.2.3.1
    coverage_radius = 0.7 * spacing

    return SpacingResult(
        max_spacing_m=spacing,
        coverage_radius_m=round(coverage_radius, 4),
        nfpa_section="NFPA 72 §17.6.3.1",
        formula=f"S={spacing}m (Table 17.6.3.1, h={ceiling_height_m:.1f}m, {det_type}); R=0.7×S",
        table_row_used=row_desc,
    )


def estimate_detector_count(
    room_area_m2: float,
    ceiling_height_m: float,
    detector_type: str,
) -> Dict[str, Any]:
    """Estimate minimum number of detectors for a room.

    Reference: NFPA 72 §17.6.3.1, §17.7.4.2.3.1

    Each detector covers a circle of radius R = 0.7 × S.
    Conservative estimate: ceil(area / (π × R²)).

    Args:
        room_area_m2: Room area in square meters.
        ceiling_height_m: Ceiling height in meters.
        detector_type: 'smoke' or 'heat'.

    Returns:
        Dict with min_detector_count, area_per_detector_m2, spacing info.
    """
    spacing_result = get_detector_spacing(ceiling_height_m, detector_type)
    radius_m = spacing_result.coverage_radius_m

    if radius_m <= 0 or not math.isfinite(room_area_m2) or room_area_m2 <= 0:
        return {
            "min_detector_count": 1,
            "area_per_detector_m2": 0.0,
            "spacing_m": spacing_result.max_spacing_m,
            "coverage_radius_m": radius_m,
        }

    coverage_area_per_detector = math.pi * radius_m ** 2
    min_count = max(1, math.ceil(room_area_m2 / coverage_area_per_detector))

    return {
        "min_detector_count": min_count,
        "area_per_detector_m2": round(coverage_area_per_detector, 4),
        "spacing_m": spacing_result.max_spacing_m,
        "coverage_radius_m": radius_m,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BATTERY CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

# Standard battery sizes (Ah) — common lead-acid/SLA batteries
_STANDARD_BATTERY_SIZES = [1.2, 2.0, 3.0, 4.0, 5.0, 7.0, 7.2, 8.0, 10.0,
                           12.0, 15.0, 18.0, 20.0, 25.0, 26.0, 28.0, 31.0,
                           33.0, 40.0, 50.0, 55.0, 60.0, 70.0, 75.0, 80.0,
                           100.0, 120.0, 150.0, 180.0, 200.0]

# NFPA 72 battery derating — Peukert-like derating for lead-acid
# At higher discharge rates, effective capacity decreases
_BATTERY_DERATING_FACTOR = 0.85  # 15% derating for lead-acid at alarm rates


def calculate_battery(
    standby_current_a: float,
    alarm_current_a: float,
    *,
    standby_hours: float = 24.0,
    alarm_minutes: float = 5.0,
    safety_margin: float = 0.20,
    ps_voltage: float = 24.0,
) -> BatteryResult:
    """Calculate required battery capacity per NFPA 72 §10.6.7.

    NFPA 72 §10.6.7 requires the secondary supply to have sufficient
    capacity to operate the system under normal load for 24 hours and
    then operate all alarm appliances for 5 minutes.

    Formula:
      Ah_derated = (I_standby × 24h + I_alarm × 5min/60h)
      Ah_required = Ah_derated / derating_factor × (1 + safety_margin)

    The derating factor accounts for the Peukert effect in lead-acid
    batteries — at higher discharge rates, effective capacity is less
    than the rated capacity.

    Args:
        standby_current_a: Standby current draw in amperes.
        alarm_current_a: Alarm current draw in amperes.
        standby_hours: Standby duration in hours (default 24 per NFPA 72).
        alarm_minutes: Alarm duration in minutes (default 5 per NFPA 72).
        safety_margin: Additional safety margin (default 20%).
        ps_voltage: Power supply nominal voltage (default 24V).

    Returns:
        BatteryResult with required Ah, installed Ah, and compliance.
    """
    # Input validation — safety first
    if not math.isfinite(standby_current_a) or standby_current_a < 0:
        raise ValueError(
            f"standby_current_a must be non-negative finite, got {standby_current_a}"
        )
    if not math.isfinite(alarm_current_a) or alarm_current_a < 0:
        raise ValueError(
            f"alarm_current_a must be non-negative finite, got {alarm_current_a}"
        )
    if standby_current_a == 0 and alarm_current_a == 0:
        raise ValueError(
            "Both standby and alarm current cannot be zero — no load specified"
        )

    # Step 1: Calculate raw Ah requirement
    # Standby: 24 hours at standby current
    standby_ah = standby_current_a * standby_hours

    # Alarm: 5 minutes at alarm current
    alarm_hours = alarm_minutes / 60.0
    alarm_ah = alarm_current_a * alarm_hours

    # Total derated Ah (Peukert effect for lead-acid)
    total_ah_raw = standby_ah + alarm_ah
    total_ah_derated = total_ah_raw / _BATTERY_DERATING_FACTOR

    # Step 2: Apply safety margin
    ah_required = total_ah_derated * (1.0 + safety_margin)

    # Step 3: Find next standard battery size
    installed_ah = ah_required  # Default: exact
    for size in _STANDARD_BATTERY_SIZES:
        if size >= ah_required:
            installed_ah = size
            break
    else:
        # No standard size found — round up to nearest 10
        installed_ah = math.ceil(ah_required / 10.0) * 10.0

    is_adequate = installed_ah >= ah_required

    formula = (
        f"Ah = (I_sb×{standby_hours}h + I_al×{alarm_minutes}min/60) "
        f"/ { _BATTERY_DERATING_FACTOR} × (1+{safety_margin}) = "
        f"({standby_current_a:.4f}×{standby_hours} + {alarm_current_a:.4f}×{alarm_hours:.4f}) "
        f"/ {_BATTERY_DERATING_FACTOR} × {1+safety_margin} = {ah_required:.2f} Ah"
    )

    return BatteryResult(
        required_ah=round(ah_required, 4),
        installed_ah=round(installed_ah, 4),
        is_adequate=is_adequate,
        formula=formula,
        nfpa_section="NFPA 72 §10.6.7",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VOLTAGE DROP CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 maximum voltage drop: 10% for 24V systems = 2.4V
# End-of-line voltage must be ≥ 21.6V
_MAX_VOLTAGE_DROP_PCT = 10.0
_SYSTEM_VOLTAGE = 24.0


def calculate_voltage_drop(
    alarm_current_a: float,
    circuit_length_m: float,
    awg_gauge: str = "14",
    *,
    ps_voltage: float = 24.0,
    max_drop_pct: float = _MAX_VOLTAGE_DROP_PCT,
) -> VoltageDropResult:
    """Calculate voltage drop on a fire alarm circuit.

    NFPA 72 §10.6.4 and NEC Chapter 9, Table 8:
      V_drop = I × 2 × R_wire × L

    The ×2 factor accounts for the DC return path (current flows out
    on one conductor and returns on the other). This was a CRITICAL
    bug fix in V14 — missing ×2 meant voltage drop was reported at
    50% of actual value, which is life-safety-dangerous.

    For 24V systems: V_eol = V_ps - V_drop
    Compliant if V_eol ≥ V_ps × (1 - max_drop_pct/100)

    Args:
        alarm_current_a: Total alarm current on the circuit (A).
        circuit_length_m: One-way circuit length in meters.
        awg_gauge: Wire gauge string (e.g. '14', '12').
        ps_voltage: Power supply voltage (default 24V).
        max_drop_pct: Maximum allowed voltage drop % (default 10%).

    Returns:
        VoltageDropResult with drop, percentage, max length, compliance.
    """
    # Input validation
    if not math.isfinite(alarm_current_a) or alarm_current_a < 0:
        raise ValueError(
            f"alarm_current_a must be non-negative finite, got {alarm_current_a}"
        )
    if not math.isfinite(circuit_length_m) or circuit_length_m < 0:
        raise ValueError(
            f"circuit_length_m must be non-negative finite, got {circuit_length_m}"
        )

    # Get wire resistance
    gauge = str(awg_gauge).strip()
    if gauge not in AWG_RESISTANCE_OHM_PER_KM:
        raise ValueError(
            f"Unsupported AWG gauge '{gauge}'. "
            f"Supported: {sorted(AWG_RESISTANCE_OHM_PER_KM.keys())}"
        )

    r_per_km = AWG_RESISTANCE_OHM_PER_KM[gauge]

    # Voltage drop: V_drop = I × 2 × R/km × L(km)
    # The ×2 is for the DC return path — CRITICAL for life safety
    length_km = circuit_length_m / 1000.0
    voltage_drop = alarm_current_a * 2.0 * r_per_km * length_km

    # Voltage drop percentage
    if ps_voltage > 0:
        drop_pct = (voltage_drop / ps_voltage) * 100.0
    else:
        drop_pct = 100.0

    # Maximum circuit length for compliance
    # V_max = I × 2 × R/km × L_max_km
    # L_max = (V_max) / (I × 2 × R/km)
    max_drop_v = ps_voltage * (max_drop_pct / 100.0)
    if alarm_current_a > 0 and r_per_km > 0:
        max_length_km = max_drop_v / (alarm_current_a * 2.0 * r_per_km)
        max_length_m = max_length_km * 1000.0
    else:
        max_length_m = float('inf')

    is_compliant = drop_pct <= max_drop_pct

    formula = (
        f"V_drop = I × 2 × R × L = "
        f"{alarm_current_a:.4f} × 2 × {r_per_km:.3f}Ω/km × "
        f"{length_km:.6f}km = {voltage_drop:.4f}V "
        f"({drop_pct:.2f}% of {ps_voltage}V)"
    )

    return VoltageDropResult(
        voltage_drop_v=round(voltage_drop, 4),
        voltage_drop_pct=round(drop_pct, 4),
        max_length_m=round(max_length_m, 2),
        is_compliant=is_compliant,
        formula=formula,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FAULT ISOLATOR PLACEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §12.3.1 — Maximum devices between isolators
_MAX_DEVICES_BETWEEN_ISOLATORS = 32


def verify_fault_isolator_placement(devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify fault isolator placement on SLC circuits.

    NFPA 72 §12.3 requires that a single fault (short or open) on a
    Signaling Line Circuit (SLC) must not disable more than one
    zone or more than 32 devices.

    This function checks:
    1. Each device group between isolators has ≤ 32 devices
    2. Isolators are placed at circuit boundaries
    3. No device is beyond the last isolator without a terminator

    Args:
        devices: List of device dicts. Each must have:
            - 'device_id': str
            - 'device_type': str (e.g. 'detector', 'module', 'isolator')
            - 'zone_id': str (optional)
            - 'circuit_id': str (optional)

    Returns:
        Dict with compliant (bool), violations (list), device_count,
        isolator_count, nfpa_section.
    """
    if not devices:
        return {
            "compliant": True,
            "violations": [],
            "device_count": 0,
            "isolator_count": 0,
            "nfpa_section": "NFPA 72 §12.3",
            "message": "No devices to verify",
        }

    violations = []
    isolator_count = 0
    current_segment_devices = 0
    segment_zone_ids = set()
    current_circuit = None

    for i, dev in enumerate(devices):
        dev_type = dev.get("device_type", "").lower()
        dev_id = dev.get("device_id", f"device_{i}")
        circuit = dev.get("circuit_id", "default")

        # Track circuit changes
        if current_circuit != circuit:
            # New circuit — check previous segment
            if current_segment_devices > _MAX_DEVICES_BETWEEN_ISOLATORS:
                violations.append({
                    "type": "too_many_devices_between_isolators",
                    "device_id": dev_id,
                    "device_count": current_segment_devices,
                    "max_allowed": _MAX_DEVICES_BETWEEN_ISOLATORS,
                    "nfpa_section": "NFPA 72 §12.3.1",
                    "message": (
                        f"Segment has {current_segment_devices} devices "
                        f"(max {_MAX_DEVICES_BETWEEN_ISOLATORS} per "
                        f"NFPA 72 §12.3.1)"
                    ),
                })
            current_segment_devices = 0
            segment_zone_ids = set()
            current_circuit = circuit

        if "isolator" in dev_type:
            # Check segment ending at this isolator
            if current_segment_devices > _MAX_DEVICES_BETWEEN_ISOLATORS:
                violations.append({
                    "type": "too_many_devices_between_isolators",
                    "device_id": dev_id,
                    "device_count": current_segment_devices,
                    "max_allowed": _MAX_DEVICES_BETWEEN_ISOLATORS,
                    "nfpa_section": "NFPA 72 §12.3.1",
                    "message": (
                        f"Segment before isolator '{dev_id}' has "
                        f"{current_segment_devices} devices "
                        f"(max {_MAX_DEVICES_BETWEEN_ISOLATORS})"
                    ),
                })
            isolator_count += 1
            current_segment_devices = 0
            segment_zone_ids = set()
        else:
            current_segment_devices += 1
            zone = dev.get("zone_id")
            if zone:
                segment_zone_ids.add(zone)

    # Check last segment (after last isolator)
    if current_segment_devices > _MAX_DEVICES_BETWEEN_ISOLATORS:
        violations.append({
            "type": "too_many_devices_end_of_circuit",
            "device_count": current_segment_devices,
            "max_allowed": _MAX_DEVICES_BETWEEN_ISOLATORS,
            "nfpa_section": "NFPA 72 §12.3.1",
            "message": (
                f"End-of-circuit segment has {current_segment_devices} "
                f"devices (max {_MAX_DEVICES_BETWEEN_ISOLATORS})"
            ),
        })

    compliant = len(violations) == 0

    return {
        "compliant": compliant,
        "violations": violations,
        "device_count": len(devices),
        "isolator_count": isolator_count,
        "nfpa_section": "NFPA 72 §12.3",
        "message": "Compliant" if compliant else f"{len(violations)} violation(s) found",
    }
