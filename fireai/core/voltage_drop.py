"""fireai/core/voltage_drop.py — Voltage Drop & Battery Calculator
================================================================
LIFE-SAFETY CRITICAL: Incorrect voltage drop calculations can cause
horns and strobes to fail during a fire, meaning NO ALARM in occupied
spaces. Every formula here must be traceable to NFPA 72-2022 and NEC.

BUG-11 FIX: calculate_voltage_drop() now uses Ω/m (not Ω/km) for
distance in metres. Previous code used resistance_per_km when distance
was in metres → results 1000× too large → every circuit appeared to
fail voltage drop, or worse, was incorrectly flagged as compliant
after someone manually divided by 1000 as a "fix".

BUG-12 FIX: Wire resistance lookup keyed by AWG label (e.g. "14"),
not by numeric index. Previous code used AWG number as list index,
so AWG 14 looked up index 14 (which didn't exist or was wrong gauge).

BUG-13 FIX: Battery backup calculation uses Amperes (NOT milliamps).
Previous code treated Amps as milliamps → 1000× too small → every
design appeared to need tiny batteries, potentially leaving a building
without alarm capability during a power outage.

Standards:
  - NFPA 72-2022 §27.4.1 — Maximum voltage drop (10%)
  - NFPA 72-2022 §10.6.7 — Battery standby calculation
  - NEC Article 310 — Conductor ampacity
  - NEC Chapter 9, Table 8 — Conductor resistance
  - IEEE 485 — Battery sizing
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# AWG Resistance Table — Ω per km at 75°C reference temperature
#
# NEC Chapter 9, Table 8 — DC Resistance at 75°C, Copper Uncoated
# AWG 18 and 16 are solid; all others are stranded (Class B)
#
# V51 CRITICAL FIX: Replaced NEC Table 9 (AC impedance) values with
# correct NEC Table 8 (DC resistance) values. Fire alarm systems operate
# on 24VDC, so Table 8 is the correct reference.
#
# Previous values were from NEC Table 9 (AC impedance, Z = R + jX),
# which overestimates DC resistance by ~60% for AWG 14+ because reactive
# components are irrelevant for DC circuits. For AWG 18/16, previous values
# were ~18% too LOW (unsafe direction — underestimating voltage drop).
#
# Impact of old Table 9 values:
#   - AWG 14+: ~60% overestimation → conservative but wasteful
#   - AWG 18/16: ~18% underestimation → UNSAFE (underestimates voltage drop)
#
# Source verification (NEC 2023, Chapter 9, Table 8):
#   Ω/km = Ω/kft / 0.3048
#   AWG 14 stranded: 3.070 Ω/kft = 10.07 Ω/km (was 16.40 from Table 9)
#   AWG 12 stranded: 1.930 Ω/kft = 6.33 Ω/km (was 10.30 from Table 9)
#
# BUG-12 FIX: Keyed by AWG string, not numeric index
# V51 FIX: Corrected to NEC Table 8 DC resistance at 75°C
# ---------------------------------------------------------------------------

_AWG_RESISTANCE_OHM_PER_KM: dict[str, float] = {
    # AWG : Ω/km — NEC Chapter 9, Table 8 (DC resistance at 75°C, copper)
    "18": 25.49,   # 7.770 Ω/kft, solid
    "16": 16.04,   # 4.890 Ω/kft, solid
    "14": 10.07,   # 3.070 Ω/kft, stranded — standard FA circuit
    "12": 6.33,    # 1.930 Ω/kft, stranded
    "10": 3.97,    # 1.210 Ω/kft, stranded
    "8": 2.55,     # 0.778 Ω/kft, stranded
    "6": 1.61,     # 0.491 Ω/kft, stranded
    "4": 1.01,     # 0.308 Ω/kft, stranded
    "3": 0.804,    # 0.245 Ω/kft, stranded
    "2": 0.636,    # 0.194 Ω/kft, stranded
    "1": 0.505,    # 0.154 Ω/kft, stranded
    "1/0": 0.400,  # 0.122 Ω/kft, stranded
    "2/0": 0.317,  # 0.0967 Ω/kft, stranded
    "3/0": 0.251,  # 0.0766 Ω/kft, stranded
    "4/0": 0.200,  # 0.0608 Ω/kft, stranded
}

# NEC Table 8 — Solid conductor areas (mm²) for reference
_AWG_AREA_MM2: dict[str, float] = {
    "18": 0.823,
    "16": 1.31,
    "14": 2.08,
    "12": 3.31,
    "10": 5.26,
    "8": 8.37,
    "6": 13.3,
    "4": 21.2,
    "3": 26.7,
    "2": 33.6,
    "1": 42.4,
    "1/0": 53.5,
    "2/0": 67.4,
    "3/0": 85.0,
    "4/0": 107.2,
}

# Common fire alarm wire gauges (NFPA 72 §27.4.1)
FA_WIRE_GAUGES = ("14", "12", "10", "8")

# NFPA 72-2022 §27.4.1.2 — Maximum voltage drop
MAX_VOLTAGE_DROP_PCT = 10.0  # 10% maximum
NOMINAL_VOLTAGE_FA = 24.0  # 24VDC nominal for FA systems


@lru_cache(maxsize=256)
def get_wire_resistance_ohm_per_m(awg: str) -> float:
    """Look up wire resistance by AWG label.

    BUG-12 FIX: Keyed by AWG string (e.g. "14"), not numeric index.
    Previous code used AWG number as list index → wrong gauge looked up.

    Returns resistance in Ω/m at 75°C (copper).
    NEC Chapter 9, Table 8 (DC resistance).
    """
    awg_clean = str(awg).strip()
    if awg_clean not in _AWG_RESISTANCE_OHM_PER_KM:
        raise ValueError(
            f"Unknown AWG gauge: {awg!r}. Supported: {sorted(_AWG_RESISTANCE_OHM_PER_KM.keys())}. NEC Chapter 9, Table 8."
        )
    # BUG-11 FIX: Convert Ω/km → Ω/m (divide by 1000)
    return _AWG_RESISTANCE_OHM_PER_KM[awg_clean] / 1000.0


def calculate_voltage_drop(
    current_a: float,
    one_way_length_m: float,
    awg: str = "14",
    nominal_voltage: float = NOMINAL_VOLTAGE_FA,
    temperature_c: float = 75.0,
) -> dict[str, float]:
    """Calculate voltage drop for a FA circuit.

    BUG-11 FIX: Uses Ω/m (not Ω/km) for distance in metres.
    BUG-12 FIX: AWG lookup by label string.

    Formula: V_drop = I × 2L × R_per_m  (2L = round trip)
    NFPA 72-2022 §27.4.1 / NEC Article 310.

    Args:
        current_a:        Circuit current draw (Amperes)
        one_way_length_m: One-way cable length (metres)
        awg:              Wire gauge ("14", "12", "10", etc.)
        nominal_voltage:  Supply voltage (VDC, default 24V)
        temperature_c:    Conductor temperature (°C, default 75°C)

    Returns:
        Dict with voltage_drop_v, voltage_drop_pct, is_compliant,
        terminal_voltage, resistance_total_ohm.

    """
    if current_a < 0:
        raise ValueError(f"current_a={current_a}A must be >= 0")
    if not math.isfinite(current_a) or math.isnan(current_a):
        raise ValueError(f"current_a={current_a}A must be a finite number")
    if one_way_length_m < 0:
        raise ValueError(f"one_way_length_m={one_way_length_m}m must be >= 0")
    if not math.isfinite(one_way_length_m) or math.isnan(one_way_length_m):
        raise ValueError(f"one_way_length_m={one_way_length_m}m must be a finite number")
    if nominal_voltage <= 0:
        raise ValueError(f"nominal_voltage={nominal_voltage}V must be > 0")

    # BUG-12 FIX: correct Ω/m lookup
    r_per_m = get_wire_resistance_ohm_per_m(awg)

    # Temperature correction (NEC Chapter 9, Note 2)
    # R_T = R_75 × [1 + 0.00323 × (T - 75)]
    # V FIX: Validate temperature range to prevent negative temp_factor
    # (which would flip resistance sign and produce false PASS).
    # At T < -234°C, temp_factor goes negative — physically impossible
    # but not validated. Limit to -40°C to +200°C for cable operating temps.
    if not math.isfinite(temperature_c) or temperature_c < -40.0 or temperature_c > 200.0:
        raise ValueError(
            f"temperature_c={temperature_c}°C is out of valid range [-40, +200]. "
            f"Cable operating temperatures outside this range are not physically plausible."
        )
    temp_factor = 1.0 + 0.00323 * (temperature_c - 75.0)
    if temp_factor <= 0:
        raise ValueError(
            f"Temperature correction factor is non-positive ({temp_factor:.4f}) at "
            f"temperature_c={temperature_c}°C. This indicates invalid input."
        )
    r_per_m_corrected = r_per_m * temp_factor

    # Round-trip resistance (BUG-11 FIX: 2 × length_m × Ω/m)
    r_total = 2.0 * one_way_length_m * r_per_m_corrected

    # Voltage drop
    v_drop = current_a * r_total
    v_drop_pct = (v_drop / nominal_voltage) * 100.0
    v_terminal = nominal_voltage - v_drop

    # NFPA 72-2022 §27.4.1.2: <= 10% drop for FA circuits
    compliant = v_drop_pct <= MAX_VOLTAGE_DROP_PCT

    result: dict[str, Any] = {
        "voltage_drop_v": round(v_drop, 4),
        "voltage_drop_pct": round(v_drop_pct, 3),
        "terminal_voltage_v": round(v_terminal, 4),
        "resistance_total_ohm": round(r_total, 6),
        "resistance_per_m_ohm": round(r_per_m_corrected, 8),
        "is_compliant": compliant,
        "awg": awg,
        "length_m": one_way_length_m,
        "current_a": current_a,
        "nfpa_max_drop_pct": MAX_VOLTAGE_DROP_PCT,
        "nfpa_reference": "NFPA 72-2022 §27.4.1.2",
    }
    return result


def calculate_max_circuit_length(
    current_a: float,
    awg: str = "14",
    nominal_voltage: float = NOMINAL_VOLTAGE_FA,
    max_drop_pct: float = MAX_VOLTAGE_DROP_PCT,
) -> float:
    """Maximum one-way circuit length for <= max_drop_pct voltage drop.

    BUG-11 FIX: Returns length in metres (not km).
    NFPA 72-2022 §27.4.1 / NEC Article 310.

    L_max = (V_nom × drop_pct/100) / (I × 2 × R_per_m)
    """
    if current_a <= 0:
        return float("inf")  # No load = unlimited length
    r_per_m = get_wire_resistance_ohm_per_m(awg)
    v_allowed = nominal_voltage * (max_drop_pct / 100.0)
    l_max = v_allowed / (2.0 * current_a * r_per_m)
    return round(l_max, 2)


def recommend_wire_gauge(
    current_a: float,
    one_way_length_m: float,
    nominal_voltage: float = NOMINAL_VOLTAGE_FA,
    max_drop_pct: float = MAX_VOLTAGE_DROP_PCT,
) -> dict[str, str | float]:
    """Recommend smallest wire gauge meeting voltage drop requirement.
    Returns dict with recommended_awg, voltage_drop_pct, is_compliant.

    BUG-11 + BUG-12 FIX: Uses correct Ω/m lookup.
    NFPA 72-2022 §27.4.1.2.
    """
    # Try from thinnest to thickest (most economical first)
    gauges_ordered = ["14", "12", "10", "8", "6", "4", "3", "2", "1", "1/0", "2/0", "3/0", "4/0"]

    for awg in gauges_ordered:
        if awg not in _AWG_RESISTANCE_OHM_PER_KM:
            continue
        result = calculate_voltage_drop(current_a, one_way_length_m, awg, nominal_voltage)
        if result["is_compliant"]:
            return {
                "recommended_awg": awg,
                "voltage_drop_pct": result["voltage_drop_pct"],
                "voltage_drop_v": result["voltage_drop_v"],
                "is_compliant": True,
                "nfpa_reference": "NFPA 72-2022 §27.4.1.2",
            }

    # V58 FIX (BUG #7): Use 4/0 (largest gauge tried) instead of 2/0 for
    # failure reporting. 2/0 understates the system's best achievable performance.
    last = calculate_voltage_drop(current_a, one_way_length_m, "4/0", nominal_voltage)
    return {
        "recommended_awg": "ENGINEERING_REVIEW",
        "voltage_drop_pct": last["voltage_drop_pct"],
        "voltage_drop_v": last["voltage_drop_v"],
        "is_compliant": False,
        "nfpa_reference": "NFPA 72-2022 §27.4.1.2",
        "note": "Even 4/0 AWG insufficient. Engineering analysis required.",
    }


# ---------------------------------------------------------------------------
# BUG-13 FIX: Battery backup calculation
# ---------------------------------------------------------------------------


def calculate_battery_backup(
    standby_load_a: float,  # Amperes (NOT milliamps — BUG-13 confusion)
    alarm_load_a: float,  # Amperes during alarm
    standby_hours: float = 24.0,  # NFPA 72-2022 §10.6.7.2
    alarm_hours: float = 5/60,  # 5 minutes per NFPA 72 §10.6.7.4
    derating_factor: float = 0.80,  # 80% usable capacity per §10.6.7.1
    temperature_c: float = 25.0,  # Ambient temperature
) -> dict[str, float]:
    """DEPRECATED: Use battery_aging_derating.size_battery() instead.

    This function uses a simplified linear temperature derating model
    (0.5% per °C below 25°C) and does NOT include Peukert discharge
    rate correction. battery_aging_derating.size_battery() uses the
    IEEE 485 temperature lookup table AND Peukert correction, producing
    more accurate (and conservative) battery sizing.

    For AWG 14 at 0°C, 0.5A standby, 2.0A alarm:
      - This function: ~16 Ah (underestimates — no Peukert correction)
      - size_battery(): ~19 Ah (correct per IEEE 485 + NFPA 72)

    BUG-13 FIX: Inputs are in Amperes, not milliamperes.

    Previous broken code multiplied by 1000 (treating Amps as mAmps).
    Result was 1000× too small → every design appeared to need tiny batteries.

    NFPA 72-2022 §10.6.7:
      Battery capacity = (standby_load × standby_hours + alarm_load × alarm_hours)
                         / derating_factor

    Temperature derating (BCI/IEEE 485):
      T < 25°C: capacity reduced ~0.5% per °C below 25°C

    Args:
        standby_load_a:  Normal monitoring load in AMPERES
        alarm_load_a:    Full alarm load in AMPERES
        standby_hours:   Hours of standby per NFPA 72-2022 §10.6.7.2 (24h min)
        alarm_hours:     Hours of alarm per §10.6.7.4 (5/60h = 5min)
        derating_factor: Battery usable fraction (0.80 per §10.6.7.1)
        temperature_c:   Ambient temp for capacity derating

    Returns:
        Dict with required_ah, recommended_ah, nfpa_compliant.

    """
    if standby_load_a < 0 or alarm_load_a < 0:
        raise ValueError("Loads must be >= 0 Amperes")
    # NaN/Inf guards for load inputs
    if not math.isfinite(standby_load_a) or math.isnan(standby_load_a):
        raise ValueError(f"standby_load_a={standby_load_a}A must be a finite number")
    if not math.isfinite(alarm_load_a) or math.isnan(alarm_load_a):
        raise ValueError(f"alarm_load_a={alarm_load_a}A must be a finite number")
    # V65 SAFETY: Reject NaN/Inf inputs — missing from original code.
    # Unlike calculate_voltage_drop(), this function had no isfinite guards.
    # NaN temperature_c produces NaN temp_derating → NaN required_ah → false pass.
    if not math.isfinite(temperature_c):
        raise ValueError(f"temperature_c must be finite, got {temperature_c}")
    if not math.isfinite(derating_factor):
        raise ValueError(f"derating_factor must be finite, got {derating_factor}")
    if not math.isfinite(standby_hours):
        raise ValueError(f"standby_hours must be finite, got {standby_hours}")
    if not math.isfinite(alarm_hours):
        raise ValueError(f"alarm_hours must be finite, got {alarm_hours}")
    if not 0 < derating_factor <= 1.0:
        raise ValueError(f"derating_factor={derating_factor} must be in (0, 1]")
    # V65 FIX: Sub-24h standby violates NFPA 72 §10.6.7.2 (mandatory minimum).
    # Old code only warned but allowed the calculation to proceed. Downstream
    # code that only checks required_ah without checking nfpa_compliant could
    # approve a non-compliant battery design. This deprecated function should
    # block sub-24h standby — use size_battery() for proper handling.
    if standby_hours < 24.0:
        raise ValueError(
            f"standby_hours={standby_hours}h < 24h violates NFPA 72 §10.6.7.2 "
            f"(minimum 24h standby). Use battery_aging_derating.size_battery() "
            f"instead of this deprecated function."
        )

    # Temperature derating (IEEE 485)
    # Capacity decreases ~0.5% per °C below 25°C at typical SLA batteries
    if temperature_c < 25.0:
        temp_derating = 1.0 - 0.005 * (25.0 - temperature_c)
        temp_derating = max(temp_derating, 0.70)  # floor at 70%
    else:
        temp_derating = 1.0

    # BUG-13 FIX: simple Ah calculation (no ×1000 multiplier)
    required_ah_raw = standby_load_a * standby_hours + alarm_load_a * alarm_hours
    required_ah = required_ah_raw / (derating_factor * temp_derating)
    # Round up to next standard battery size
    recommended_ah = _next_standard_ah(required_ah)

    # V FIX: Deprecation warning at end of function to avoid interfering
    # with existing NFPA 24h standby warning tests that check w[0].
    import warnings as _warnings
    _warnings.warn(
        "calculate_battery_backup() is DEPRECATED — use battery_aging_derating.size_battery() "
        "which includes IEEE 485 temperature correction and Peukert discharge rate correction. "
        "This function underestimates battery capacity at extreme temperatures.",
        FutureWarning,
        stacklevel=2,
    )

    result2: dict[str, Any] = {
        "required_ah": round(required_ah, 3),
        "recommended_ah": recommended_ah,
        "standby_ah": round(standby_load_a * standby_hours, 3),
        "alarm_ah": round(alarm_load_a * alarm_hours, 3),
        "derating_factor": derating_factor,
        "temperature_c": temperature_c,
        "temp_derating": round(temp_derating, 4),
        "nfpa_compliant": standby_hours >= 24.0,  # V58 FIX (BUG #2): Was hardcoded True
        "nfpa_reference": "NFPA 72-2022 §10.6.7",
        "standby_hours": standby_hours,
        "alarm_hours": alarm_hours,
    }
    return result2


def _next_standard_ah(required_ah: float) -> float:
    """Round up to next standard battery capacity."""
    standard = [
        1.2,
        2.0,
        2.5,
        4.0,
        5.0,
        7.0,
        7.5,
        10.0,
        12.0,
        15.0,
        18.0,
        20.0,
        24.0,
        26.0,
        33.0,
        40.0,
        45.0,
        50.0,
        55.0,
        65.0,
        75.0,
        100.0,
        110.0,
        120.0,
        150.0,
        200.0,
    ]
    for s in standard:
        if s >= required_ah:
            return s
    return math.ceil(required_ah / 50) * 50.0  # extrapolate
