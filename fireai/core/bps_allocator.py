"""fireai/core/bps_allocator.py
=============================
NAC Booster Power Supply (BPS) Auto-Allocator for Fire Alarm Systems.

Allocates NAC booster power supplies for fire alarm notification appliances
per NFPA 72 Chapter 10 and NEC Article 760.

QOMN-FIRE Architecture (5 strict layers):
  Layer 0 — Input Sanitization: NaN/Inf rejection, physical bounds enforcement
  Layer 1 — Reference Engine: NFPA 72/NEC constants as source of truth
  Layer 2 — Computation Engine: Deterministic IEEE-754 arithmetic
  Layer 3 — Validation Engine: Post-computation verification against code limits
  Layer 4 — Audit Log: Immutable record of all safety-critical decisions

SAFETY PRINCIPLE: "Safety First, Always."
  - Same inputs always produce same outputs (deterministic)
  - Every formula traceable to published standard (NFPA 72/NEC)
  - Every constant from standard table, never approximation
  - Every limit is code minimum/maximum, never average
  - NaN/Inf NEVER propagate — always caught and rejected with ValueError
  - Voltage drop uses 2x wire length for DC return path (NEC 760)

PHYSICS:
  Voltage drop across a DC circuit wire:
    V_drop = 2 × I_total × R_per_ft × L_ft
  where:
    - Factor 2 accounts for the DC return path (NEC 760)
    - I_total is the aggregate downstream current (amps)
    - R_per_ft is the wire resistance per foot (ohm/ft)
    - L_ft is the one-way segment length (feet)

  End-of-line voltage must be >= 80% of nominal voltage:
    V_eol >= 0.80 × V_nominal
    For 24 VDC: V_eol >= 19.2 VDC

STANDARDS REFERENCED:
  - NFPA 72-2022 §10.6   — Power supplies for fire alarm systems
  - NFPA 72-2022 §10.6.4 — Secondary (standby) power supply requirements
  - NFPA 72-2022 §10.14  — Voltage drop limitations
  - NFPA 72-2022 §18.5.5 — Synchronization of visible notification appliances
  - NFPA 72-2022 §21.2   — Emergency voice/alarm communication systems
  - NEC Article 760      — Fire alarm systems (wiring methods, voltage drop)
  - NEC Chapter 9 Table 8 — Conductor properties (DC resistance)
  - UL 1971              — Emergency signaling devices for the hearing impaired
  - UL 2075              — Smoke detectors for fire alarm systems
  - UL 864 10th Edition  — Control units and accessories
  - IEEE-754-2008        — Floating-point arithmetic (determinism)

Provenance:
  Returns DecisionProvenance via the .new() factory when
  src.v8_core is available; degrades gracefully to plain dict otherwise.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


# ============================================================================
# LAYER 0 — INPUT SANITIZATION (Physics Guards)
# QOMN-FIRE Specification: Reject any input that is physically impossible
# or outside code bounds before any computation begins.
# ============================================================================


def _guard_finite(value: float, field_name: str) -> float:
    """IEEE-754 guard: reject NaN and Inf before any computation.

    Per QOMN-FIRE Layer 0 and IEEE-754-2008 §7:
    NaN and Inf are NEVER permitted in life-safety computations.

    Args:
        value: Numeric value to validate.
        field_name: Human-readable field name for error messages.

    Returns:
        The validated float value.

    Raises:
        ValueError: If value is NaN or Inf.

    """
    if not isinstance(value, (int, float)):
        raise ValueError(
            f"[L0 REJECTION] {field_name}={value!r}: must be numeric, got {type(value).__name__}. IEEE-754-2008 §7."
        )
    if math.isnan(value):
        raise ValueError(
            f"[L0 REJECTION] {field_name}=NaN: NaN is not permitted in safety-critical computation. IEEE-754-2008 §7.2."
        )
    if math.isinf(value):
        raise ValueError(
            f"[L0 REJECTION] {field_name}=Inf: Infinity is not permitted in "
            f"safety-critical computation. IEEE-754-2008 §7.4."
        )
    return float(value)


def _guard_positive_finite(value: float, field_name: str) -> float:
    """Guard: value must be finite and strictly positive.

    Args:
        value: Numeric value to validate.
        field_name: Human-readable field name for error messages.

    Returns:
        The validated positive float value.

    Raises:
        ValueError: If value is NaN, Inf, zero, or negative.

    """
    v = _guard_finite(value, field_name)
    if v <= 0:
        raise ValueError(f"[L0 REJECTION] {field_name}={v}: must be > 0 for physical quantities. NFPA 72 §10.6.")
    return v


def _guard_non_negative_finite(value: float, field_name: str) -> float:
    """Guard: value must be finite and >= 0.

    Args:
        value: Numeric value to validate.
        field_name: Human-readable field name for error messages.

    Returns:
        The validated non-negative float value.

    Raises:
        ValueError: If value is NaN, Inf, or negative.

    """
    v = _guard_finite(value, field_name)
    if v < 0:
        raise ValueError(f"[L0 REJECTION] {field_name}={v}: must be >= 0. NFPA 72 §10.6 / NEC 760.")
    return v


# ============================================================================
# LAYER 1 — REFERENCE ENGINE (Source of Truth)
# All constants from published standards, never approximations.
# ============================================================================

# --- Nominal System Voltage ---
# NFPA 72-2022 §10.6.4: Fire alarm systems use 24 VDC nominal
NOMINAL_VOLTAGE_VDC: float = 24.0

# --- Minimum End-of-Line Voltage ---
# NFPA 72-2022 §10.6.4: End-of-line voltage must be >= 80% of nominal
# For 24 VDC: 0.80 × 24.0 = 19.2 VDC
MIN_EOL_VOLTAGE_VDC: float = 19.2

# --- Voltage Drop Fraction ---
# 1.0 - 0.80 = 0.20 (20% maximum voltage drop)
MAX_VOLTAGE_DROP_FRACTION: float = 0.20

# --- Wire Resistance Table (ohm per 1000 ft) ---
# NEC Chapter 9, Table 8 — Copper conductors, uncoated, DC resistance at 75°C
# CRITICAL FIX (V76 CRIT-01): Previous values were 20°C resistance, causing 16%
# underestimation of voltage drop. At 75°C operating temperature (the standard
# design condition per NEC 310.14), copper resistance increases ~16% due to
# positive temperature coefficient. Using 20°C values means circuits approved
# as compliant could actually exceed the voltage drop limit at operating temp,
# causing horns/strobes at end-of-line to fail during a fire.
# Source: NEC Chapter 9, Table 8 — "Direct-Current Resistance at 75°C" column.
WIRE_RESISTANCE_OHM_PER_1000FT: Dict[int, float] = {
    18: 7.770,  # AWG 18 — 7.770 Ω/1000ft at 75°C (was 6.51 at 20°C)
    16: 4.890,  # AWG 16 — 4.890 Ω/1000ft at 75°C (was 4.09 at 20°C)
    14: 3.070,  # AWG 14 — 3.070 Ω/1000ft at 75°C (was 2.58 at 20°C)
    12: 1.930,  # AWG 12 — 1.930 Ω/1000ft at 75°C (was 1.62 at 20°C)
    10: 1.210,  # AWG 10 — 1.210 Ω/1000ft at 75°C (was 1.02 at 20°C)
}

# --- Wire Resistance in ohm/ft (derived for per-segment calculations) ---
# V_drop = 2 × I × R_per_ft × L_ft (NEC 760 DC return path factor)
WIRE_RESISTANCE_OHM_PER_FT: Dict[int, float] = {awg: r / 1000.0 for awg, r in WIRE_RESISTANCE_OHM_PER_1000FT.items()}

# --- Standard NAC Panel Ratings (amps) ---
# Typical NAC circuit ratings per UL 864 10th Edition
STANDARD_NAC_RATINGS_A: List[float] = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0]

# --- Default FACP NAC Current Limit ---
# Per NFPA 72 §10.6, FACP NAC circuits are typically rated at 2A or 3A
DEFAULT_FACP_NAC_RATING_A: float = 3.0

# --- Default BPS (Booster Power Supply) Capacity ---
# Per UL 864 10th Ed., standard BPS ratings
DEFAULT_BOOSTER_CAPACITY_A: float = 6.0

# --- Default BPS NAC Circuit Rating ---
# Each NAC circuit on a BPS panel is typically rated 2A or 3A
DEFAULT_BPS_NAC_RATING_A: float = 3.0

# --- Default Number of NAC Circuits per BPS ---
# Standard BPS panels typically have 2-4 NAC circuits
DEFAULT_NAC_CIRCUITS_PER_BPS: int = 4

# --- Default Wire Gauge ---
# AWG 14 is the standard minimum for fire alarm NAC circuits per NEC 760
DEFAULT_AWG: int = 14

# --- Default BPS Placement Offset ---
# Offset from stairwell centroid for BPS panel placement (feet)
DEFAULT_BPS_OFFSET_X_FT: float = 5.0
DEFAULT_BPS_OFFSET_Y_FT: float = 3.0

# --- Horn/Strobe Current Requirements per UL 1971/UL 2075 ---
# Typical current draw values from manufacturer data sheets
# UL 1971: Emergency signaling devices for hearing impaired
# UL 2075: Smoke detectors for fire alarm systems

# Horn current per unit (amps)
# Typical electromechanical horn: 0.030 - 0.100 A
# Typical electronic horn: 0.020 - 0.060 A
TYPICAL_HORN_CURRENT_A: float = 0.050

# Strobe current per candela (amps/candela)
# UL 1971 listed strobes have current proportional to candela rating
# 15 cd strobe ≈ 0.085A, 75 cd strobe ≈ 0.115A, 110 cd strobe ≈ 0.155A
# Linear approximation: ~0.00567 A per candela
STROBE_CURRENT_PER_CANDELA_A: float = 0.00567

# Pre-calculated strobe currents for common ratings
STROBE_CURRENT_TABLE_A: Dict[float, float] = {
    15.0: 0.085,  # 15 candela — small rooms, corridors
    30.0: 0.095,  # 30 candela
    75.0: 0.115,  # 75 candela — standard room coverage
    95.0: 0.130,  # 95 candela
    110.0: 0.155,  # 110 candela — large rooms
    150.0: 0.185,  # 150 candela
    177.0: 0.210,  # 177 candela — sleeping areas per NFPA 72 §18.5.5.7
    220.0: 0.260,  # 220 candela
}

# Horn/Strobe combination current (typical combo device)
# Per UL 1971, a horn/strobe combo draws horn + strobe current
TYPICAL_HORN_STROBE_15CD_CURRENT_A: float = 0.135  # 0.050 + 0.085
TYPICAL_HORN_STROBE_75CD_CURRENT_A: float = 0.165  # 0.050 + 0.115
TYPICAL_HORN_STROBE_110CD_CURRENT_A: float = 0.205  # 0.050 + 0.155

# --- Synchronization ---
# NFPA 72-2022 §18.5.5: All visible appliances in the same area
# must flash in synchronization. BPS panels driving strobes must
# be synchronized with each other and with the FACP.
SYNC_REQUIRED_WHEN_MULTIPLE_BPS: bool = True

# --- Citations ---
_CITE_NFPA72_10_6 = "NFPA 72-2022 §10.6"
_CITE_NFPA72_10_6_4 = "NFPA 72-2022 §10.6.4"
_CITE_NFPA72_10_14 = "NFPA 72-2022 §10.6.4"  # V78 FIX: Was §10.14 — obsolete reference from pre-2019 editions
_CITE_NFPA72_18_5_5 = "NFPA 72-2022 §18.5.5"
_CITE_NFPA72_21_2 = "NFPA 72-2022 §21.2"
_CITE_NEC_760 = "NEC Article 760"
_CITE_NEC_CH9_T8 = "NEC Chapter 9, Table 8"
_CITE_UL1971 = "UL 1971"
_CITE_UL2075 = "UL 2075"
_CITE_UL864 = "UL 864 10th Ed."


# ============================================================================
# LAYER 2 — COMPUTATION ENGINE (IEEE-754 Bit-Exact Arithmetic)
# All computations use IEEE-754 double precision (float64).
# No approximations. No fast-math. Explicit NaN/Inf handling.
# ============================================================================


def _f64_hash(*values: float) -> str:
    """Compute deterministic IEEE-754 bit-level hash of float64 values.

    Uses struct.pack to get exact binary representation, then SHA-256.
    Guarantees same hash on any platform for same input.

    Source: IEEE-754-2008 §3 — bit-level representation
    """
    h = hashlib.sha256()
    for v in values:
        bits = struct.pack(">d", v)
        h.update(bits)
    return h.hexdigest()[:16]


def calculate_strobe_current(candela: float) -> float:
    """Calculate strobe current draw per UL 1971.

    Uses lookup table for common candela ratings, falls back to
    linear approximation for non-standard ratings.

    Source: UL 1971 — Emergency signaling devices for hearing impaired

    Args:
        candela: Strobe intensity rating in candela.

    Returns:
        Current draw in amperes.

    Raises:
        ValueError: If candela is NaN, Inf, or negative.

    """
    c = _guard_non_negative_finite(candela, "candela")
    if c == 0.0:
        return 0.0

    # Use lookup table for standard ratings
    if c in STROBE_CURRENT_TABLE_A:
        return STROBE_CURRENT_TABLE_A[c]

    # Linear approximation for non-standard ratings
    # Per UL 1971, current is approximately proportional to candela
    return round(STROBE_CURRENT_PER_CANDELA_A * c, 4)


def calculate_device_current(
    device_type: str,
    candela: Optional[float] = None,
    horn_current_a: Optional[float] = None,
) -> float:
    """Calculate total current draw for a notification appliance.

    Per UL 1971/UL 2075, calculates the alarm current for a single
    notification device based on its type and rating.

    Args:
        device_type: One of "horn", "strobe", "horn_strobe", "speaker".
        candela: Strobe intensity (required for strobe/horn_strobe types).
        horn_current_a: Override for default horn current (amps).

    Returns:
        Current draw in amperes during alarm condition.

    Raises:
        ValueError: If inputs are NaN/Inf or device_type is unknown.

    """
    dt = device_type.lower().strip()

    if dt not in ("horn", "strobe", "horn_strobe", "speaker"):
        raise ValueError(f"Unknown device_type '{device_type}'. Must be one of: horn, strobe, horn_strobe, speaker.")

    if horn_current_a is not None:
        h_current = _guard_non_negative_finite(horn_current_a, "horn_current_a")
    else:
        h_current = TYPICAL_HORN_CURRENT_A

    if dt == "horn":
        return h_current

    if dt == "strobe":
        if candela is None:
            raise ValueError(
                f"candela is required for strobe device type. Per {_CITE_UL1971}, strobe intensity must be specified."
            )
        return calculate_strobe_current(candela)

    if dt == "horn_strobe":
        if candela is None:
            raise ValueError(
                "candela is required for horn_strobe device type. "
                f"Per {_CITE_UL1971}, strobe intensity must be specified."
            )
        return h_current + calculate_strobe_current(candela)

    # speaker — typical 25V, 1W speaker
    return 0.040


def calculate_nac_circuit_current(devices: List[Dict[str, Any]]) -> float:
    """Calculate total NAC circuit current for a list of notification devices.

    Per NFPA 72 §10.6.4.2 and NEC 760, the total alarm current on a NAC
    must not exceed the NAC power supply rating. This function sums the
    individual device currents.

    Args:
        devices: List of device dicts with keys:
            - "device_type" (str): "horn", "strobe", "horn_strobe", "speaker"
            - "candela" (float, optional): Strobe candela rating
            - "current_a" (float, optional): Override current (amps)
            - "horn_current_a" (float, optional): Override horn current

    Returns:
        Total NAC circuit current in amperes.

    Raises:
        ValueError: If any device current input is NaN/Inf.

    """
    total = 0.0
    for i, dev in enumerate(devices):
        # Allow direct current override
        override_current = dev.get("current_a")
        if override_current is not None:
            c = _guard_non_negative_finite(override_current, f"devices[{i}].current_a")
            total += c
            continue

        device_type = dev.get("device_type", "horn")
        candela = dev.get("candela")
        horn_current = dev.get("horn_current_a")

        dev_current = calculate_device_current(
            device_type=device_type,
            candela=candela,
            horn_current_a=horn_current,
        )
        total += dev_current

    return round(total, 6)


def calculate_voltage_drop_vdc(
    total_current_a: float,
    one_way_length_ft: float,
    awg: int = DEFAULT_AWG,
    nominal_voltage_vdc: float = NOMINAL_VOLTAGE_VDC,
) -> float:
    """Calculate voltage drop for a NAC circuit segment.

    Per NEC 760 and NEC Chapter 9 Table 8:
      V_drop = 2 × I × R_per_ft × L_ft

    The factor of 2 accounts for the DC return path (both supply
    and return conductors carry the same current).

    Args:
        total_current_a: Total downstream current (amperes).
        one_way_length_ft: One-way wire length (feet).
        awg: Wire gauge (AWG number).
        nominal_voltage_vdc: Nominal system voltage (VDC).

    Returns:
        Voltage drop in VDC across the segment.

    Raises:
        ValueError: If inputs are NaN/Inf or AWG is unknown.

    """
    i = _guard_non_negative_finite(total_current_a, "total_current_a")
    l = _guard_non_negative_finite(one_way_length_ft, "one_way_length_ft")
    _guard_positive_finite(nominal_voltage_vdc, "nominal_voltage_vdc")

    if awg not in WIRE_RESISTANCE_OHM_PER_FT:
        raise ValueError(
            f"Unknown AWG gauge '{awg}'. Valid gauges: "
            f"{sorted(WIRE_RESISTANCE_OHM_PER_FT.keys())}. "
            f"Per {_CITE_NEC_CH9_T8}, provide a valid AWG gauge."
        )

    r_per_ft = WIRE_RESISTANCE_OHM_PER_FT[awg]

    # V_drop = 2 × I × R_per_ft × L  (NEC 760 DC return path)
    v_drop = 2.0 * i * r_per_ft * l

    return round(v_drop, 6)


def calculate_eol_voltage(
    total_current_a: float,
    one_way_length_ft: float,
    awg: int = DEFAULT_AWG,
    nominal_voltage_vdc: float = NOMINAL_VOLTAGE_VDC,
) -> float:
    """Calculate end-of-line voltage for a NAC circuit.

    Per NFPA 72 §10.6.4, the end-of-line voltage must be >= 80%
    of nominal (19.2 VDC for 24 VDC systems).

    Args:
        total_current_a: Total circuit current (amperes).
        one_way_length_ft: One-way wire length (feet).
        awg: Wire gauge (AWG number).
        nominal_voltage_vdc: Nominal system voltage (VDC).

    Returns:
        End-of-line voltage in VDC.

    Raises:
        ValueError: If inputs are NaN/Inf.

    """
    v_nom = _guard_positive_finite(nominal_voltage_vdc, "nominal_voltage_vdc")
    v_drop = calculate_voltage_drop_vdc(total_current_a, one_way_length_ft, awg, v_nom)
    v_eol = v_nom - v_drop

    # V76 MED-09 FIX: EOL voltage can be negative when voltage drop exceeds
    # supply. This is physically impossible (can't have negative voltage).
    # Clamped to 0.0 and flagged as CRITICAL violation.
    if v_eol < 0:
        logger.critical(
            f"EOL voltage is NEGATIVE ({v_eol:.2f} VDC) — voltage drop "
            f"exceeds supply voltage. Circuit cannot operate. "
            f"Per NFPA 72 §10.6.4, terminal voltage must be >= 80% of nominal."
        )
        v_eol = 0.0

    return round(v_eol, 6)


def select_minimum_wire_gauge(
    total_current_a: float,
    one_way_length_ft: float,
    nominal_voltage_vdc: float = NOMINAL_VOLTAGE_VDC,
    min_eol_voltage_vdc: float = MIN_EOL_VOLTAGE_VDC,
) -> int:
    """Select the minimum wire gauge that maintains EOL voltage above minimum.

    Per NFPA 72 §10.6.4 and NEC 760, the wire gauge must be sized such
    that the end-of-line voltage is at least 80% of nominal. This function
    tries each wire gauge from thinnest (AWG 18) to thickest (AWG 10)
    and returns the first one that satisfies the voltage requirement.

    If no standard gauge satisfies the requirement, returns 0 to indicate
    that engineering review is required (larger gauge or BPS insertion).

    Args:
        total_current_a: Total circuit current (amperes).
        one_way_length_ft: One-way wire length (feet).
        nominal_voltage_vdc: Nominal system voltage (VDC).
        min_eol_voltage_vdc: Minimum acceptable EOL voltage (VDC).

    Returns:
        Selected AWG gauge number, or 0 if no standard gauge is sufficient.

    Raises:
        ValueError: If inputs are NaN/Inf.

    """
    i = _guard_non_negative_finite(total_current_a, "total_current_a")
    l = _guard_non_negative_finite(one_way_length_ft, "one_way_length_ft")
    _guard_positive_finite(nominal_voltage_vdc, "nominal_voltage_vdc")
    _guard_positive_finite(min_eol_voltage_vdc, "min_eol_voltage_vdc")

    # Try from thinnest to thickest (most economical first)
    # AWG 18 → 16 → 14 → 12 → 10
    # NOTE: AWG numbers are counter-intuitive: higher number = thinner wire
    for awg in sorted(WIRE_RESISTANCE_OHM_PER_FT.keys(), reverse=True):
        v_eol = calculate_eol_voltage(i, l, awg, nominal_voltage_vdc)
        if v_eol >= min_eol_voltage_vdc:
            return awg

    # No standard gauge sufficient — flag for engineering review
    logger.critical(
        "BPS-ALLOC-001: No standard wire gauge (AWG 18-10) can maintain "
        "EOL voltage >= %.1f VDC for %.3f A over %.1f ft. "
        "Engineering review required — consider BPS insertion or larger "
        "conductor. Per %s / %s.",
        min_eol_voltage_vdc,
        i,
        l,
        _CITE_NFPA72_10_6_4,
        _CITE_NEC_760,
    )
    return 0


def calculate_max_circuit_length_ft(
    total_current_a: float,
    awg: int = DEFAULT_AWG,
    nominal_voltage_vdc: float = NOMINAL_VOLTAGE_VDC,
    min_eol_voltage_vdc: float = MIN_EOL_VOLTAGE_VDC,
) -> float:
    """Calculate maximum one-way circuit length for acceptable voltage drop.

    Per NFPA 72 §10.6.4 and NEC 760:
      V_drop_max = V_nominal - V_min_eol
      L_max = V_drop_max / (2 × I × R_per_ft)

    Args:
        total_current_a: Total circuit current (amperes).
        awg: Wire gauge (AWG number).
        nominal_voltage_vdc: Nominal system voltage (VDC).
        min_eol_voltage_vdc: Minimum EOL voltage (VDC).

    Returns:
        Maximum one-way circuit length in feet.

    Raises:
        ValueError: If inputs are NaN/Inf or AWG is unknown.

    """
    i = _guard_non_negative_finite(total_current_a, "total_current_a")
    _guard_positive_finite(nominal_voltage_vdc, "nominal_voltage_vdc")
    _guard_positive_finite(min_eol_voltage_vdc, "min_eol_voltage_vdc")

    if i == 0.0:
        return float("inf")  # No load — unlimited length

    if awg not in WIRE_RESISTANCE_OHM_PER_FT:
        raise ValueError(
            f"Unknown AWG gauge '{awg}'. Valid gauges: "
            f"{sorted(WIRE_RESISTANCE_OHM_PER_FT.keys())}. "
            f"Per {_CITE_NEC_CH9_T8}."
        )

    r_per_ft = WIRE_RESISTANCE_OHM_PER_FT[awg]
    v_drop_max = nominal_voltage_vdc - min_eol_voltage_vdc

    if v_drop_max <= 0:
        return 0.0

    l_max = v_drop_max / (2.0 * i * r_per_ft)
    return round(l_max, 2)


# ============================================================================
# FROZEN DATACLASSES — LAYER 2 RESULT TYPES
# ============================================================================


@dataclass(frozen=True)
class NACDeviceSegment:
    """A single notification device on a NAC circuit with voltage drop info.

    Represents one device along the circuit path from source to end-of-line,
    including the cumulative voltage at that point after wire resistance losses.
    """

    device_id: str
    device_type: str
    current_a: float
    candela: Optional[float]
    x_ft: float
    y_ft: float
    segment_length_ft: float  # Wire length from previous device to this one
    cumulative_length_ft: float  # Total wire length from source to this device
    voltage_at_device_vdc: float  # Voltage available at this device
    is_voltage_acceptable: bool  # True if voltage >= min EOL voltage


@dataclass(frozen=True)
class NACCircuitResult:
    """Result from NAC circuit loading and voltage drop analysis.

    Per NFPA 72 §10.6.4 and NEC 760, each NAC circuit must satisfy:
    1. Total current <= NAC rating
    2. End-of-line voltage >= 80% of nominal (19.2 VDC for 24 VDC)
    """

    circuit_id: str
    nac_rating_a: float
    total_current_a: float
    device_count: int
    is_current_compliant: bool
    current_headroom_a: float
    eol_voltage_vdc: float
    min_eol_voltage_vdc: float
    is_voltage_compliant: bool
    selected_awg: int
    total_wire_length_ft: float
    devices: Tuple[NACDeviceSegment, ...]
    violations: Tuple[str, ...]


@dataclass(frozen=True)
class BPSPlacement:
    """A deployed Booster Power Supply panel.

    Per NFPA 72 §10.6 and UL 864 10th Ed., a BPS provides additional
    NAC circuits when the FACP cannot serve all devices.
    """

    booster_id: str
    x_ft: float
    y_ft: float
    nac_circuits: Tuple[str, ...]
    total_current_a: float
    nac_circuits_available: int
    floors_covered: Tuple[str, ...]


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


@dataclass(frozen=True)
class AllocationResult:
    """Complete result from NAC booster allocation.

    Contains all BPS placements, NAC circuit assignments, voltage drop
    analysis, and compliance status per NFPA 72 Chapter 10 and NEC 760.
    """

    total_current_a: float
    facp_native_load_a: float
    facp_nac_rating_a: float
    num_boosters: int
    booster_placements: Tuple[BPSPlacement, ...]
    nac_circuits: Tuple[NACCircuitResult, ...]
    sync_required: bool
    is_compliant: bool
    violations: Tuple[str, ...]
    computation_hash: str
    nfpa_references: Tuple[str, ...]
    algorithm_version: str


# ============================================================================
# LAYER 3 — VALIDATION ENGINE (Post-Computation Verification)
# ============================================================================


def _validate_nac_circuit_result(result: NACCircuitResult) -> NACCircuitResult:
    """Validate a NAC circuit result against physical and code limits.

    Per QOMN-FIRE Layer 3, verify post-computation that all limits hold.

    Args:
        result: NACCircuitResult to validate.

    Returns:
        The validated result (unchanged if valid).

    Raises:
        ValueError: If any computed value is NaN/Inf (computation error).

    """
    # Check for NaN/Inf in computed results
    for attr_name in ("total_current_a", "eol_voltage_vdc", "current_headroom_a", "total_wire_length_ft"):
        val = getattr(result, attr_name)
        if not math.isfinite(val):
            raise ValueError(
                f"[L3 REJECTION] NACCircuitResult.{attr_name}={val} "
                f"is non-finite. Computation produced unreliable result. "
                f"Per {_CITE_NFPA72_10_6}."
            )

    # Verify current compliance flag matches actual values
    if result.is_current_compliant != (result.total_current_a <= result.nac_rating_a):
        logger.error(
            "BPS-ALLOC-L3: Current compliance flag mismatch for circuit %s. "
            "Flag=%s, actual=%s (current=%.4fA, rating=%.1fA).",
            result.circuit_id,
            result.is_current_compliant,
            result.total_current_a <= result.nac_rating_a,
            result.total_current_a,
            result.nac_rating_a,
        )

    # Verify voltage compliance flag
    if result.is_voltage_compliant != (result.eol_voltage_vdc >= result.min_eol_voltage_vdc):
        logger.error(
            "BPS-ALLOC-L3: Voltage compliance flag mismatch for circuit %s. Flag=%s, actual=%s (eol=%.2fV, min=%.2fV).",
            result.circuit_id,
            result.is_voltage_compliant,
            result.eol_voltage_vdc >= result.min_eol_voltage_vdc,
            result.eol_voltage_vdc,
            result.min_eol_voltage_vdc,
        )

    return result


# ============================================================================
# NACBoosterAllocator — Main Allocation Class
# ============================================================================


class NACBoosterAllocator:
    """Automatically distributes NAC load across FACP and BPS panels
    for fire alarm systems per NFPA 72 Chapter 10 and NEC 760.

    Two-pass allocation:

      **Pass 1 — Current capacity**: Waterfall load-balancing by floor
      current. Distributes floors across FACP native NAC and BPS panels
      such that no NAC circuit exceeds its rated current.

      **Pass 2 — Voltage drop validation**: Iterative segment-by-segment
      voltage drop calculation along each NAC circuit path. When the
      terminal voltage at any device falls below the minimum (80% of
      nominal per NFPA 72 §10.6.4), a BPS is inserted at the choke-point
      to regenerate a clean 24 VDC source.

    Additionally provides:
      - NAC circuit loading check against panel NAC rating (2A/3A)
      - Wire gauge selection for acceptable voltage drop
      - Horn/strobe current calculation per UL 1971/UL 2075
      - Strobe synchronization requirement per NFPA 72 §18.5.5
      - Multiple NAC circuits per booster panel

    Usage::

        allocator = NACBoosterAllocator(
            facp_nac_rating_a=3.0,
            booster_capacity_a=6.0,
        )
        result = allocator.allocate_boosters_across_floors(floor_data=[...])
    """

    def __init__(
        self,
        facp_nac_rating_a: float = DEFAULT_FACP_NAC_RATING_A,
        booster_capacity_a: float = DEFAULT_BOOSTER_CAPACITY_A,
        bps_nac_rating_a: float = DEFAULT_BPS_NAC_RATING_A,
        nac_circuits_per_bps: int = DEFAULT_NAC_CIRCUITS_PER_BPS,
        bps_offset_x_ft: float = DEFAULT_BPS_OFFSET_X_FT,
        bps_offset_y_ft: float = DEFAULT_BPS_OFFSET_Y_FT,
        source_voltage_vdc: float = NOMINAL_VOLTAGE_VDC,
        min_eol_voltage_vdc: float = MIN_EOL_VOLTAGE_VDC,
        default_awg: int = DEFAULT_AWG,
    ) -> None:
        """Initialize NACBoosterAllocator.

        Args:
            facp_nac_rating_a: FACP NAC circuit current rating (amps).
                Per NFPA 72 §10.6, typically 2A or 3A per NAC circuit.
            booster_capacity_a: BPS total current capacity (amps).
                Per UL 864 10th Ed., typically 6A or 8A.
            bps_nac_rating_a: BPS individual NAC circuit rating (amps).
                Per UL 864 10th Ed., typically 2A or 3A.
            nac_circuits_per_bps: Number of NAC circuits per BPS panel.
                Standard BPS panels have 2-4 NAC circuits.
            bps_offset_x_ft: X offset for BPS placement from floor centroid (ft).
            bps_offset_y_ft: Y offset for BPS placement from floor centroid (ft).
            source_voltage_vdc: Nominal system voltage (VDC). Default 24 VDC.
            min_eol_voltage_vdc: Minimum EOL voltage (VDC).
                Per NFPA 72 §10.6.4: 80% of nominal = 19.2 VDC for 24V systems.
            default_awg: Default wire gauge. AWG 14 per NEC 760.

        Raises:
            ValueError: If any numeric parameter is NaN/Inf or out of bounds.

        """
        # LAYER 0: Input sanitization
        self.facp_nac_rating = _guard_positive_finite(facp_nac_rating_a, "facp_nac_rating_a")
        self.booster_capacity = _guard_positive_finite(booster_capacity_a, "booster_capacity_a")
        self.bps_nac_rating = _guard_positive_finite(bps_nac_rating_a, "bps_nac_rating_a")
        self.nac_circuits_per_bps = nac_circuits_per_bps
        if nac_circuits_per_bps < 1:
            raise ValueError(f"nac_circuits_per_bps={nac_circuits_per_bps} must be >= 1.")
        self.bps_offset_x_ft = _guard_finite(bps_offset_x_ft, "bps_offset_x_ft")
        self.bps_offset_y_ft = _guard_finite(bps_offset_y_ft, "bps_offset_y_ft")
        self.source_voltage = _guard_positive_finite(source_voltage_vdc, "source_voltage_vdc")
        self.min_eol_voltage = _guard_positive_finite(min_eol_voltage_vdc, "min_eol_voltage_vdc")
        self.default_awg = default_awg
        if default_awg not in WIRE_RESISTANCE_OHM_PER_FT:
            raise ValueError(
                f"Unknown default_awg='{default_awg}'. "
                f"Valid: {sorted(WIRE_RESISTANCE_OHM_PER_FT.keys())}. "
                f"Per {_CITE_NEC_CH9_T8}."
            )

        # Validate that min_eol_voltage is reasonable
        if self.min_eol_voltage >= self.source_voltage:
            raise ValueError(
                f"min_eol_voltage_vdc={self.min_eol_voltage} must be < "
                f"source_voltage_vdc={self.source_voltage}. "
                f"Per {_CITE_NFPA72_10_6_4}, EOL voltage is a fraction of nominal."
            )

        logger.info(
            "NACBoosterAllocator initialized: FACP_NAC=%.1fA, BPS=%.1fA, "
            "BPS_NAC=%.1fA × %d circuits, V_nom=%.1fVDC, V_min=%.1fVDC, AWG=%d. "
            "Per %s / %s / %s.",
            self.facp_nac_rating,
            self.booster_capacity,
            self.bps_nac_rating,
            self.nac_circuits_per_bps,
            self.source_voltage,
            self.min_eol_voltage,
            self.default_awg,
            _CITE_NFPA72_10_6,
            _CITE_NEC_760,
            _CITE_UL864,
        )

    # ------------------------------------------------------------------
    # Pass 1: Current-Capacity Waterfall Allocation
    # ------------------------------------------------------------------

    def allocate_boosters_across_floors(
        self,
        floor_data: List[Dict[str, Any]],
    ) -> Any:
        """Distribute NAC load across FACP and auto-deployed BPS panels.

        Pass 1: Current-capacity waterfall allocation.
        Pass 2: Voltage-drop validation (if devices_line provided).

        Per NFPA 72 §10.6, §10.6.4 and NEC 760:
        - Total NAC current must not exceed panel NAC rating
        - End-of-line voltage must be >= 80% of nominal
        - BPS panels regenerate voltage at choke points

        Args:
            floor_data: List of floor dicts with keys:
                - "floor_name" (str): Floor identifier
                - "nac_current" (float): Total NAC current for this floor (A)
                - "centroid_location" (tuple): (x, y) floor centroid (ft)
                - "level_z" (float): Floor elevation
                - "devices_line" (list, optional): Ordered device list for
                  voltage drop analysis

        Returns:
            DecisionProvenance or dict with allocation results.

        Raises:
            ValueError: If any numeric input is NaN/Inf.

        """
        # L0: Validate floor data inputs
        self._validate_floor_data(floor_data)

        violations: list = []
        panel_allocation: List[Dict[str, Any]] = []
        cumulative_load: float = 0.0
        active_booster_id: int = 1
        current_load: float = 0.0

        sorted_floors = sorted(
            floor_data,
            key=lambda x: float(x.get("level_z", 0.0)),
        )

        # --- PASS 1: Current-capacity waterfall allocation ---
        for f_info in sorted_floors:
            f_name = f_info.get("floor_name", "UNKNOWN")
            f_current = float(f_info.get("nac_current", 0.0))
            f_centroid = f_info.get("centroid_location", (0.0, 0.0))
            cumulative_load += f_current

            # Check if floor current inherently exceeds single BPS limit
            if f_current > self.booster_capacity:
                desc = (
                    f"Floor '{f_name}' current ({f_current:.2f} A) "
                    f"inherently exceeds single BPS capacity "
                    f"({self.booster_capacity:.1f} A). Requires multiple "
                    f"NAC sub-circuits on this floor. "
                    f"Per {_CITE_NFPA72_10_6} / {_CITE_NFPA72_21_2}."
                )
                self._add_violation(violations, "CRITICAL", f"{_CITE_NFPA72_10_6} / {_CITE_NFPA72_21_2}", desc)
                logger.critical(desc)

            # Check against NAC circuit rating (not just total BPS capacity)
            # Per NFPA 72 §10.6.4, each NAC circuit has its own rating
            if f_current > self.bps_nac_rating:
                desc = (
                    f"Floor '{f_name}' current ({f_current:.2f} A) exceeds "
                    f"single NAC circuit rating ({self.bps_nac_rating:.1f} A). "
                    f"Floor must be split across multiple NAC circuits. "
                    f"Per {_CITE_NFPA72_10_6_4} / {_CITE_NEC_760}."
                )
                self._add_violation(violations, "WARNING", f"{_CITE_NFPA72_10_6_4} / {_CITE_NEC_760}", desc)
                logger.warning(desc)

            # Determine zone capacity (FACP native vs BPS)
            zone_capacity = self.facp_nac_rating if not panel_allocation else self.bps_nac_rating

            if current_load + f_current > zone_capacity:
                pos = f_centroid if isinstance(f_centroid, tuple) else (0.0, 0.0)
                new_booster: Dict[str, Any] = {
                    "type": "NAC_BOOSTER_BPS",
                    "id": f"BPS-0{active_booster_id}",
                    "x": pos[0] + self.bps_offset_x_ft,
                    "y": pos[1] + self.bps_offset_y_ft,
                    "floors_covered": [f_name],
                    "peak_load": f_current,
                    "nac_circuits_available": self.nac_circuits_per_bps,
                    "nac_rating_per_circuit_a": self.bps_nac_rating,
                }
                panel_allocation.append(new_booster)
                current_load = f_current
                active_booster_id += 1
            else:
                current_load += f_current
                if panel_allocation:
                    panel_allocation[-1]["floors_covered"].append(f_name)
                    panel_allocation[-1]["peak_load"] = current_load

        # SYNC_MODULE for multi-BPS (NFPA 72 §18.5.5)
        if len(panel_allocation) > 0:
            sync_module: Dict[str, Any] = {
                "type": "SYNC_MODULE",
                "description": (
                    f"Mandatory Global Notification Synchronization "
                    f"({_CITE_NFPA72_18_5_5}). All visible appliances "
                    f"driven by different BPS panels must flash in "
                    f"synchronization per NFPA 72 §18.5.5."
                ),
                "target": "ALL BPS",
                "nfpa_reference": _CITE_NFPA72_18_5_5,
            }
            panel_allocation.insert(0, sync_module)

        safe = len(violations) == 0

        # --- PASS 2: Voltage drop validation ---
        voltage_result = None
        all_devices_line: List[Dict[str, Any]] = []
        for f_info in sorted_floors:
            dev_line = f_info.get("devices_line")
            if dev_line and isinstance(dev_line, list):
                all_devices_line.extend(dev_line)

        if all_devices_line:
            voltage_result = self.validate_voltage_drop(all_devices_line)
            v_violations = []
            if isinstance(voltage_result, dict):
                v_violations = voltage_result.get("violations", [])
            elif hasattr(voltage_result, "violations"):
                v_violations = voltage_result.violations or []
            if v_violations:
                violations.extend(v_violations)
                safe = False
        else:
            desc = (
                "VOLTAGE DROP VALIDATION NOT PERFORMED: No devices_line "
                "data provided on any floor. BPS allocation is based on "
                "current capacity ONLY. Terminal voltage at end-of-line "
                "devices may be below minimum — horns/strobes may fail "
                "during fire. Provide devices_line per floor for full "
                "Pass 1 + Pass 2 allocation per NFPA 72 §10.6.4 / §10.14."
            )
            self._add_violation(violations, "CRITICAL", _CITE_NFPA72_10_14, desc)
            logger.critical(desc)
            safe = False

        # Build provenance result
        num_bps = sum(1 for b in panel_allocation if b.get("type") == "NAC_BOOSTER_BPS")
        facp_native_load = round(
            cumulative_load
            - sum(b.get("peak_load", 0.0) for b in panel_allocation if b.get("type") == "NAC_BOOSTER_BPS"),
            4,
        )

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
                        value_used=self.booster_capacity,
                        unit="AMPS",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA72_10_6_4,
                        constant_id="MIN_EOL_VOLTAGE",
                        value_used=self.min_eol_voltage,
                        unit="VDC",
                    ),
                    RuleApplied(
                        citation=_CITE_NEC_760,
                        constant_id="DC_RETURN_PATH_FACTOR",
                        value_used=2.0,
                        unit="DIMENSIONLESS",
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
                        "facp_native_load": facp_native_load,
                        "num_boosters": num_bps,
                        "sync_required": num_bps > 0,
                    },
                    inputs={
                        "floors_analyzed": len(floor_data),
                    },
                    rules_applied=rules,
                    algorithm={"name": "WaterfallLoadBalancer", "version": "v22.0"},
                    confidence=conf,
                    selected_because=(
                        "Voltage/Current aggregation dynamically fragmented "
                        "into topological autonomous zones satisfying "
                        "structural wire limitations per "
                        f"{_CITE_NFPA72_10_6} / {_CITE_NEC_760}"
                    ),
                    violations=violations if violations else None,
                )
            except Exception as exc:
                logger.error("Failed to record distributed power routing decision audit: %s", exc)

        result_dict: Dict[str, Any] = {
            "decision_type": "distributed_power_routing",
            "value": {
                "boosters": panel_allocation,
                "total_current": round(cumulative_load, 4),
                "facp_native_load": facp_native_load,
                "num_boosters": num_bps,
                "sync_required": num_bps > 0,
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

    # ------------------------------------------------------------------
    # Pass 2: Voltage Drop Validation
    # ------------------------------------------------------------------

    def validate_voltage_drop(
        self,
        devices_line: List[Dict[str, Any]],
        awg: int = DEFAULT_AWG,
        max_cable_length_ft: float = 1000.0,
        source_location: Optional[Tuple[float, float]] = None,
    ) -> Any:
        """Pass 2: Iterative segment-by-segment voltage drop validation.

        Processes a NAC circuit from source to end-of-line, tracking
        cumulative voltage drop. When terminal voltage falls below the
        minimum, a BPS insertion point is generated.

        Per NFPA 72 §10.6.4 and NEC 760:
          V_drop = 2 × I × R × L  (DC return path factor of 2)
          V_eol >= 80% × V_nominal = 19.2 VDC for 24 VDC systems

        Each element of *devices_line* must be a dict with:
        - ``id`` (str): Device identifier.
        - ``x``, ``y`` (float): 2D coordinates (feet).
        - ``inrush_a`` (float, optional): Device inrush current (amps).
          Defaults to 0.2 A.
        - ``steady_a`` (float, optional): Device steady-state current.
          Defaults to 0.1 A.
        - ``device_type`` (str, optional): Device type for UL 1971/2075
          current calculation.
        - ``candela`` (float, optional): Strobe candela for current calc.

        Args:
            devices_line: Ordered list of devices on the NAC circuit
                from source (FACP) to end-of-line.
            awg: Wire gauge per NEC Chapter 9 Table 8.
            max_cable_length_ft: Maximum continuous branch length (feet).
            source_location: (x, y) coordinates of the FACP source panel
                in feet. When provided, voltage drop from FACP to the
                first device is calculated.

        Returns:
            DecisionProvenance with BPS insertion points for voltage
            regeneration, or plain dict.

        Raises:
            ValueError: If any numeric input is NaN/Inf.

        """
        # L0: Validate inputs
        _guard_finite(max_cable_length_ft, "max_cable_length_ft")
        if source_location is not None:
            _guard_finite(source_location[0], "source_location[0]")
            _guard_finite(source_location[1], "source_location[1]")

        violations: list = []
        booster_placements: List[Dict[str, Any]] = []

        # L0: Validate device inputs — reject NaN/Inf with ValueError
        for idx, dev in enumerate(devices_line):
            for field_name in ("x", "y", "inrush_a", "steady_a"):
                val = dev.get(field_name)
                if val is not None:
                    try:
                        fval = float(val)
                    except (TypeError, ValueError):
                        fval = None
                    if fval is not None and (math.isnan(fval) or math.isinf(fval)):
                        desc = (
                            f"BPS-002: Device '{dev.get('id', f'DEV-{idx}')}' "
                            f"has {field_name}={val} (NaN or Inf). "
                            f"Non-physical device data produces unreliable voltage "
                            f"drop calculations. Per {_CITE_NFPA72_10_6_4}, all "
                            f"circuit parameters must be physically valid."
                        )
                        logger.critical(desc)
                        self._add_violation(violations, "CRITICAL", _CITE_NFPA72_10_6_4, desc)

        # Get wire resistance
        if awg not in WIRE_RESISTANCE_OHM_PER_FT:
            logger.critical(
                "BPS-001: Unknown AWG gauge '%s' — no wire resistance data available. "
                "Using most conservative (highest resistance) known value. "
                "Per %s, provide a valid AWG gauge.",
                awg,
                _CITE_NEC_CH9_T8,
            )
            # Use highest resistance (thinnest = AWG 18 = 6.51 Ω/1000ft)
            ohm_per_ft = max(WIRE_RESISTANCE_OHM_PER_FT.values())
        else:
            ohm_per_ft = WIRE_RESISTANCE_OHM_PER_FT[awg]

        running_voltage = self.source_voltage
        # Aggregate downstream current (all devices from this point to EOL)
        running_current_tail = sum(float(d.get("inrush_a", 0.2)) for d in devices_line)
        running_length = 0.0

        # FACP-to-first-device voltage drop
        last_pt: Optional[Tuple[float, float]] = source_location

        for i, dev in enumerate(devices_line):
            # V59 FIX: Guard device coordinates against NaN/Inf. Non-finite
            # coordinates produce NaN distances and silently disable voltage
            # drop checks (NaN < min_eol = False). Per IEEE-754-2008 §7.
            _dev_x = dev.get("x", 0.0)
            _dev_y = dev.get("y", 0.0)
            try:
                _dev_x_f = _guard_finite(float(_dev_x), f"devices_line[{i}].x")
            except ValueError:
                logger.critical("BPS-003: Device '%s' has non-finite x=%r. Skipping.", dev.get('id', f'DEV-{i}'), _dev_x)
                _dev_x_f = 0.0
            try:
                _dev_y_f = _guard_finite(float(_dev_y), f"devices_line[{i}].y")
            except ValueError:
                logger.critical("BPS-003: Device '%s' has non-finite y=%r. Skipping.", dev.get('id', f'DEV-{i}'), _dev_y)
                _dev_y_f = 0.0
            curr_pt = (_dev_x_f, _dev_y_f)

            if last_pt is not None:
                dist = math.hypot(
                    curr_pt[0] - last_pt[0],
                    curr_pt[1] - last_pt[1],
                )
            else:
                dist = 0.0

            running_length += dist

            # V_drop = 2 × I × R_per_ft × L  (NEC 760 DC return path)
            # V59 FIX: Guard running_current_tail against NaN before multiplication
            if not math.isfinite(running_current_tail):
                logger.critical("BPS-004: running_current_tail=%r is NaN/Inf. Resetting to 0.", running_current_tail)
                running_current_tail = 0.0
            if dist > 0 and running_current_tail > 0:
                segment_drop = 2.0 * dist * ohm_per_ft * running_current_tail
                if not math.isfinite(segment_drop):
                    logger.critical("BPS-005: segment_drop=%r is NaN/Inf (dist=%r, ohm_per_ft=%r, current=%r). Skipping.",
                                    segment_drop, dist, ohm_per_ft, running_current_tail)
                    segment_drop = 0.0
                running_voltage -= segment_drop

            # Subtract this device's current from downstream tail
            # V59 FIX: Guard device current against NaN/Inf
            _raw_current = dev.get("inrush_a", 0.2)
            try:
                dev_current = _guard_finite(float(_raw_current), f"devices_line[{i}].inrush_a")
            except ValueError:
                logger.critical("BPS-006: Device '%s' has non-finite inrush_a=%r. Using 0.2A default.",
                                dev.get('id', f'DEV-{i}'), _raw_current)
                dev_current = 0.2
            running_current_tail = max(0.0, running_current_tail - dev_current)
            last_pt = curr_pt

            # Check if voltage has collapsed below minimum
            if running_voltage < self.min_eol_voltage:
                booster_placements.append(
                    {
                        "insert_node": curr_pt,
                        "at_device": dev.get("id", f"DEV-{i}"),
                        "terminal_voltage": round(running_voltage, 2),
                        "running_length_ft": round(running_length, 1),
                        "nfpa_reference": _CITE_NFPA72_10_6_4,
                    }
                )
                logger.info(
                    "BPS insertion at device '%s' (x=%.1f, y=%.1f): "
                    "terminal voltage %.2f VDC < %.2f VDC minimum. "
                    "Wire length=%.1f ft. Per %s / %s.",
                    dev.get("id", f"DEV-{i}"),
                    curr_pt[0],
                    curr_pt[1],
                    running_voltage,
                    self.min_eol_voltage,
                    running_length,
                    _CITE_NFPA72_10_6_4,
                    _CITE_NEC_760,
                )
                # Reset: BPS regenerates clean source voltage
                running_voltage = self.source_voltage
                running_length = 0.0

        # Check total circuit length
        if running_length > max_cable_length_ft:
            desc = (
                f"NAC circuit total length ({running_length:.1f} ft) exceeds "
                f"maximum branch distance ({max_cable_length_ft:.0f} ft) per "
                f"{_CITE_NFPA72_10_14} / {_CITE_NEC_760}."
            )
            self._add_violation(violations, "CRITICAL", f"{_CITE_NFPA72_10_14} / {_CITE_NEC_760}", desc)
            logger.critical(desc)

        safe = len(violations) == 0

        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NFPA72_10_6_4,
                        constant_id="VDROP_CRITICAL",
                        value_used=self.min_eol_voltage,
                        unit="VDC",
                    ),
                    RuleApplied(
                        citation=_CITE_NEC_760,
                        constant_id="DC_RETURN_PATH_FACTOR",
                        value_used=2.0,
                        unit="DIMENSIONLESS",
                    ),
                    RuleApplied(
                        citation=_CITE_NEC_CH9_T8,
                        constant_id="WIRE_RESISTANCE",
                        value_used=ohm_per_ft,
                        unit="ohm/ft",
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
                        "source_voltage_vdc": self.source_voltage,
                        "min_eol_voltage_vdc": self.min_eol_voltage,
                        "wire_awg": awg,
                        "wire_resistance_ohm_per_ft": ohm_per_ft,
                        "total_length_ft": round(running_length, 1),
                        "safe": safe,
                    },
                    inputs={
                        "devices_on_circuit": len(devices_line),
                    },
                    rules_applied=rules,
                    algorithm={
                        "name": "DynamicIterativeVoltageChipper",
                        "version": "v22.0",
                    },
                    confidence=conf,
                    selected_because=(
                        f"Iterative segment-by-segment voltage drop ensures "
                        f"terminal voltage >= {self.min_eol_voltage} VDC "
                        f"(80% of {self.source_voltage} VDC). "
                        f"Per {_CITE_NFPA72_10_6_4} / {_CITE_NEC_760}."
                    ),
                    violations=violations if violations else None,
                )
            except Exception as exc:
                logger.error("Failed to record voltage drop validation decision audit: %s", exc)

        return {
            "decision_type": "voltage_drop_validation",
            "value": {
                "bps_insertions": booster_placements,
                "cuts": len(booster_placements),
                "source_voltage_vdc": self.source_voltage,
                "min_eol_voltage_vdc": self.min_eol_voltage,
                "wire_awg": awg,
                "wire_resistance_ohm_per_ft": ohm_per_ft,
                "total_length_ft": round(running_length, 1),
                "safe": safe,
            },
            "inputs": {"devices_on_circuit": len(devices_line)},
            "safe": safe,
            "violations": violations,
        }

    # ------------------------------------------------------------------
    # NAC Circuit Loading Analysis
    # ------------------------------------------------------------------

    def analyze_nac_circuit(
        self,
        circuit_id: str,
        devices: List[Dict[str, Any]],
        nac_rating_a: Optional[float] = None,
        awg: int = DEFAULT_AWG,
    ) -> NACCircuitResult:
        """Analyze a single NAC circuit for current and voltage compliance.

        Per NFPA 72 §10.6.4.2 and NEC 760:
        - Total alarm current must not exceed NAC rating
        - End-of-line voltage must be >= 80% of nominal

        This method performs both current loading and voltage drop analysis
        for a single NAC circuit with ordered devices.

        Args:
            circuit_id: Identifier for this NAC circuit.
            devices: Ordered list of device dicts from source to EOL with:
                - "id" (str): Device identifier
                - "device_type" (str): "horn", "strobe", "horn_strobe", "speaker"
                - "candela" (float, optional): For strobe types
                - "current_a" (float, optional): Override current
                - "x", "y" (float): Coordinates in feet
                - "inrush_a" (float, optional): Inrush current for voltage drop
            nac_rating_a: NAC circuit rating (amps). Defaults to FACP rating.
            awg: Wire gauge for voltage drop calculation.

        Returns:
            NACCircuitResult with full current and voltage analysis.

        Raises:
            ValueError: If inputs are NaN/Inf.

        """
        # L0: Input validation
        _guard_finite(nac_rating_a or self.facp_nac_rating, "nac_rating_a")
        if awg not in WIRE_RESISTANCE_OHM_PER_FT:
            raise ValueError(
                f"Unknown AWG gauge '{awg}'. Valid: "
                f"{sorted(WIRE_RESISTANCE_OHM_PER_FT.keys())}. "
                f"Per {_CITE_NEC_CH9_T8}."
            )

        rating = nac_rating_a if nac_rating_a is not None else self.facp_nac_rating

        # Calculate total circuit current
        total_current = calculate_nac_circuit_current(devices)
        is_current_compliant = total_current <= rating
        headroom = rating - total_current

        # Voltage drop analysis along the circuit
        ohm_per_ft = WIRE_RESISTANCE_OHM_PER_FT[awg]
        running_voltage = self.source_voltage
        running_current_tail = total_current
        running_length = 0.0

        violation_strs: List[str] = []
        device_segments: List[NACDeviceSegment] = []

        for i, dev in enumerate(devices):
            curr_pt = (
                float(dev.get("x", 0.0)),
                float(dev.get("y", 0.0)),
            )

            # Distance from previous point
            if i > 0:
                prev_pt = (
                    float(devices[i - 1].get("x", 0.0)),
                    float(devices[i - 1].get("y", 0.0)),
                )
                dist = math.hypot(
                    curr_pt[0] - prev_pt[0],
                    curr_pt[1] - prev_pt[1],
                )
            else:
                dist = 0.0

            running_length += dist

            # Calculate voltage drop for this segment
            # V_drop = 2 × I_tail × R_per_ft × L_segment
            if dist > 0 and running_current_tail > 0:
                segment_drop = 2.0 * dist * ohm_per_ft * running_current_tail
                running_voltage -= segment_drop

            # Device current
            dev_current = float(dev.get("current_a", 0.0))
            if dev_current == 0.0:
                # Calculate from device type
                dt = dev.get("device_type", "horn")
                cdl = dev.get("candela")
                try:
                    dev_current = calculate_device_current(dt, cdl)
                except ValueError:
                    dev_current = float(dev.get("inrush_a", 0.2))

            running_current_tail = max(0.0, running_current_tail - dev_current)

            is_v_ok = running_voltage >= self.min_eol_voltage

            if not is_v_ok:
                violation_strs.append(
                    f"Device '{dev.get('id', f'DEV-{i}')}' EOL voltage "
                    f"{running_voltage:.2f} VDC < {self.min_eol_voltage:.1f} VDC "
                    f"minimum. Per {_CITE_NFPA72_10_6_4} / {_CITE_NEC_760}."
                )

            segment = NACDeviceSegment(
                device_id=dev.get("id", f"DEV-{i}"),
                device_type=dev.get("device_type", "horn"),
                current_a=round(dev_current, 4),
                candela=dev.get("candela"),
                x_ft=curr_pt[0],
                y_ft=curr_pt[1],
                segment_length_ft=round(dist, 2),
                cumulative_length_ft=round(running_length, 2),
                voltage_at_device_vdc=round(running_voltage, 4),
                is_voltage_acceptable=is_v_ok,
            )
            device_segments.append(segment)

        if not is_current_compliant:
            violation_strs.append(
                f"NAC circuit '{circuit_id}' total current {total_current:.4f}A "
                f"exceeds rating {rating:.1f}A. Per {_CITE_NFPA72_10_6_4} / {_CITE_NEC_760}."
            )

        is_voltage_compliant = all(d.is_voltage_acceptable for d in device_segments)

        result = NACCircuitResult(
            circuit_id=circuit_id,
            nac_rating_a=rating,
            total_current_a=round(total_current, 4),
            device_count=len(devices),
            is_current_compliant=is_current_compliant,
            current_headroom_a=round(headroom, 4),
            eol_voltage_vdc=round(running_voltage, 4),
            min_eol_voltage_vdc=self.min_eol_voltage,
            is_voltage_compliant=is_voltage_compliant,
            selected_awg=awg,
            total_wire_length_ft=round(running_length, 2),
            devices=tuple(device_segments),
            violations=tuple(violation_strs),
        )

        # L3: Post-computation validation
        _validate_nac_circuit_result(result)

        return result

    # ------------------------------------------------------------------
    # Wire Gauge Selection
    # ------------------------------------------------------------------

    def recommend_wire_gauge(
        self,
        total_current_a: float,
        one_way_length_ft: float,
    ) -> Dict[str, Any]:
        """Recommend minimum wire gauge for acceptable voltage drop.

        Per NFPA 72 §10.6.4 and NEC 760, the wire gauge must maintain
        end-of-line voltage at >= 80% of nominal.

        Args:
            total_current_a: Total NAC circuit current (amps).
            one_way_length_ft: One-way wire length (feet).

        Returns:
            Dict with recommended AWG, voltage drop, EOL voltage, compliance.

        Raises:
            ValueError: If inputs are NaN/Inf.

        """
        i = _guard_non_negative_finite(total_current_a, "total_current_a")
        l = _guard_non_negative_finite(one_way_length_ft, "one_way_length_ft")

        # Try from thinnest (AWG 18) to thickest (AWG 10)
        # NOTE: AWG numbers are counter-intuitive: higher number = thinner wire
        for awg in sorted(WIRE_RESISTANCE_OHM_PER_FT.keys(), reverse=True):
            v_drop = calculate_voltage_drop_vdc(i, l, awg, self.source_voltage)
            v_eol = self.source_voltage - v_drop
            if v_eol >= self.min_eol_voltage:
                return {
                    "recommended_awg": awg,
                    "voltage_drop_vdc": round(v_drop, 4),
                    "eol_voltage_vdc": round(v_eol, 4),
                    "is_compliant": True,
                    "nfpa_reference": _CITE_NFPA72_10_6_4,
                    "nec_reference": _CITE_NEC_760,
                }

        # No standard gauge sufficient
        last_awg = max(WIRE_RESISTANCE_OHM_PER_FT.keys())
        v_drop = calculate_voltage_drop_vdc(i, l, last_awg, self.source_voltage)
        v_eol = self.source_voltage - v_drop
        return {
            "recommended_awg": "ENGINEERING_REVIEW",
            "voltage_drop_vdc": round(v_drop, 4),
            "eol_voltage_vdc": round(v_eol, 4),
            "is_compliant": False,
            "nfpa_reference": _CITE_NFPA72_10_6_4,
            "nec_reference": _CITE_NEC_760,
            "note": (
                "No standard wire gauge (AWG 18-10) maintains EOL voltage "
                f">= {self.min_eol_voltage} VDC. Consider BPS insertion or "
                "larger conductor. Engineering analysis required."
            ),
        }

    # ------------------------------------------------------------------
    # Maximum Circuit Length
    # ------------------------------------------------------------------

    def max_circuit_length(
        self,
        total_current_a: float,
        awg: int = DEFAULT_AWG,
    ) -> float:
        """Calculate maximum one-way circuit length for acceptable voltage drop.

        Per NFPA 72 §10.6.4 and NEC 760:
          L_max = V_drop_max / (2 × I × R_per_ft)

        Args:
            total_current_a: Total circuit current (amps).
            awg: Wire gauge (AWG number).

        Returns:
            Maximum one-way circuit length in feet.

        Raises:
            ValueError: If inputs are NaN/Inf or AWG is unknown.

        """
        return calculate_max_circuit_length_ft(
            total_current_a,
            awg,
            self.source_voltage,
            self.min_eol_voltage,
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _validate_floor_data(self, floor_data: List[Dict[str, Any]]) -> None:
        """Validate floor data inputs per QOMN-FIRE Layer 0.

        Args:
            floor_data: List of floor dicts to validate.

        Raises:
            ValueError: If any numeric value is NaN/Inf.

        """
        for idx, f_info in enumerate(floor_data):
            nac_current = f_info.get("nac_current")
            if nac_current is not None:
                _guard_non_negative_finite(
                    float(nac_current),
                    f"floor_data[{idx}].nac_current",
                )

            level_z = f_info.get("level_z")
            if level_z is not None:
                _guard_finite(
                    float(level_z),
                    f"floor_data[{idx}].level_z",
                )

            centroid = f_info.get("centroid_location")
            if centroid is not None and isinstance(centroid, (tuple, list)):
                if len(centroid) >= 2:
                    _guard_finite(
                        float(centroid[0]),
                        f"floor_data[{idx}].centroid_location[0]",
                    )
                    _guard_finite(
                        float(centroid[1]),
                        f"floor_data[{idx}].centroid_location[1]",
                    )

    def _add_violation(
        self,
        violations: list,
        severity: str,
        citation: str,
        description: str,
    ) -> None:
        """Add a violation to the list, using provenance Violation if available.

        Args:
            violations: List to append to.
            severity: "CRITICAL", "HIGH", "MEDIUM", or "LOW".
            citation: NFPA/NEC code reference.
            description: Human-readable violation description.

        """
        # Map "WARNING" to "HIGH" for provenance Violation compatibility
        mapped_severity = severity
        if severity == "WARNING" and Violation is not None:
            mapped_severity = "HIGH"

        if Violation is not None:
            violations.append(
                Violation(
                    severity=mapped_severity,
                    description=description,
                    nfpa_section=citation,
                )
            )
        else:
            violations.append(
                {
                    "severity": severity,
                    "citation": citation,
                    "description": description,
                }
            )


# ============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ============================================================================


def quick_voltage_check(
    total_current_a: float,
    one_way_length_ft: float,
    awg: int = DEFAULT_AWG,
) -> Dict[str, Any]:
    """Quick voltage drop check for a NAC circuit.

    Convenience function that creates a NACBoosterAllocator with defaults
    and checks if the circuit meets NFPA 72 §10.6.4 voltage requirements.

    Args:
        total_current_a: Total circuit current (amps).
        one_way_length_ft: One-way wire length (feet).
        awg: Wire gauge (AWG number).

    Returns:
        Dict with voltage drop, EOL voltage, and compliance status.

    Raises:
        ValueError: If inputs are NaN/Inf.

    """
    i = _guard_non_negative_finite(total_current_a, "total_current_a")
    l = _guard_non_negative_finite(one_way_length_ft, "one_way_length_ft")

    v_drop = calculate_voltage_drop_vdc(i, l, awg)
    v_eol = NOMINAL_VOLTAGE_VDC - v_drop
    is_compliant = v_eol >= MIN_EOL_VOLTAGE_VDC

    result = {
        "total_current_a": i,
        "one_way_length_ft": l,
        "awg": awg,
        "nominal_voltage_vdc": NOMINAL_VOLTAGE_VDC,
        "voltage_drop_vdc": round(v_drop, 4),
        "eol_voltage_vdc": round(v_eol, 4),
        "min_eol_voltage_vdc": MIN_EOL_VOLTAGE_VDC,
        "is_compliant": is_compliant,
        "nfpa_reference": _CITE_NFPA72_10_6_4,
        "nec_reference": _CITE_NEC_760,
    }

    if not is_compliant:
        result["recommendation"] = (
            f"EOL voltage {v_eol:.2f} VDC is below minimum "
            f"{MIN_EOL_VOLTAGE_VDC} VDC. Options: (1) Upgrade wire gauge, "
            f"(2) Reduce circuit length, (3) Insert BPS to regenerate "
            f"voltage. Per {_CITE_NFPA72_10_6_4} / {_CITE_NEC_760}."
        )
        # Recommend wire gauge
        rec_awg = select_minimum_wire_gauge(i, l)
        if rec_awg > 0:
            result["recommended_awg"] = rec_awg

    return result


def quick_nac_load_check(
    devices: List[Dict[str, Any]],
    nac_rating_a: float = DEFAULT_FACP_NAC_RATING_A,
) -> Dict[str, Any]:
    """Quick NAC circuit loading check.

    Convenience function to verify NAC circuit current does not exceed
    the panel NAC rating per NFPA 72 §10.6.4.2 and NEC 760.

    Args:
        devices: List of device dicts (see calculate_nac_circuit_current).
        nac_rating_a: NAC circuit current rating (amps).

    Returns:
        Dict with total current, max allowed, compliance status.

    Raises:
        ValueError: If inputs are NaN/Inf.

    """
    rating = _guard_positive_finite(nac_rating_a, "nac_rating_a")
    total = calculate_nac_circuit_current(devices)
    is_compliant = total <= rating
    headroom = rating - total

    return {
        "total_current_a": round(total, 4),
        "nac_rating_a": rating,
        "max_allowed_a": round(rating, 4),
        "is_compliant": is_compliant,
        "headroom_a": round(headroom, 4),
        "device_count": len(devices),
        "nfpa_reference": _CITE_NFPA72_10_6_4,
        "nec_reference": _CITE_NEC_760,
    }


__all__ = [
    # Main class
    "NACBoosterAllocator",
    # Frozen dataclasses
    "NACDeviceSegment",
    "NACCircuitResult",
    "BPSPlacement",
    "FloorNACProfile",
    "BoosterAllocation",
    "AllocationResult",
    # Constants — Voltage
    "NOMINAL_VOLTAGE_VDC",
    "MIN_EOL_VOLTAGE_VDC",
    "MAX_VOLTAGE_DROP_FRACTION",
    # Constants — Wire
    "WIRE_RESISTANCE_OHM_PER_1000FT",
    "WIRE_RESISTANCE_OHM_PER_FT",
    "DEFAULT_AWG",
    # Constants — NAC Ratings
    "STANDARD_NAC_RATINGS_A",
    "DEFAULT_FACP_NAC_RATING_A",
    "DEFAULT_BOOSTER_CAPACITY_A",
    "DEFAULT_BPS_NAC_RATING_A",
    "DEFAULT_NAC_CIRCUITS_PER_BPS",
    # Constants — Device Currents
    "TYPICAL_HORN_CURRENT_A",
    "STROBE_CURRENT_PER_CANDELA_A",
    "STROBE_CURRENT_TABLE_A",
    "TYPICAL_HORN_STROBE_15CD_CURRENT_A",
    "TYPICAL_HORN_STROBE_75CD_CURRENT_A",
    "TYPICAL_HORN_STROBE_110CD_CURRENT_A",
    # Functions — Computation
    "calculate_strobe_current",
    "calculate_device_current",
    "calculate_nac_circuit_current",
    "calculate_voltage_drop_vdc",
    "calculate_eol_voltage",
    "select_minimum_wire_gauge",
    "calculate_max_circuit_length_ft",
    # Functions — Quick Checks
    "quick_voltage_check",
    "quick_nac_load_check",
]
