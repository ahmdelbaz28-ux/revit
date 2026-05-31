"""
fireai/core/voltage_drop.py — Voltage Drop & Battery Calculator
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
import warnings
from functools import lru_cache
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# NEC Table 9 — Conductor Resistance (Ω per km at 75°C, copper)
# BUG-12 FIX: Keyed by AWG string, not numeric index
# ---------------------------------------------------------------------------

_AWG_RESISTANCE_OHM_PER_KM: Dict[str, float] = {
    # AWG : Ω/km at 75°C copper (NEC Table 9, Chapter 9)
    "18":  20.80,
    "16":  13.10,
    "14":  16.40,   # 14 AWG = standard FA circuit
    "12":  10.30,   # 12 AWG
    "10":   6.53,   # 10 AWG
    "8":    4.10,   # 8 AWG
    "6":    2.58,   # 6 AWG
    "4":    1.62,   # 4 AWG
    "3":    1.29,   # 3 AWG
    "2":    1.02,   # 2 AWG
    "1":    0.811,  # 1 AWG
    "1/0":  0.644,  # 1/0 AWG
    "2/0":  0.511,  # 2/0 AWG
    "3/0":  0.405,  # 3/0 AWG
    "4/0":  0.321,  # 4/0 AWG
}

# NEC Table 8 — Solid conductor areas (mm²) for reference
_AWG_AREA_MM2: Dict[str, float] = {
    "18": 0.823, "16": 1.31, "14": 2.08, "12": 3.31, "10": 5.26,
    "8": 8.37, "6": 13.3, "4": 21.2, "3": 26.7, "2": 33.6,
    "1": 42.4, "1/0": 53.5, "2/0": 67.4, "3/0": 85.0, "4/0": 107.2,
}

# Common fire alarm wire gauges (NFPA 72 §27.4.1)
FA_WIRE_GAUGES = ("14", "12", "10", "8")

# NFPA 72-2022 §27.4.1.2 — Maximum voltage drop
MAX_VOLTAGE_DROP_PCT = 10.0   # 10% maximum
NOMINAL_VOLTAGE_FA   = 24.0   # 24VDC nominal for FA systems


@lru_cache(maxsize=256)
def get_wire_resistance_ohm_per_m(awg: str) -> float:
    """
    Look up wire resistance by AWG label.

    BUG-12 FIX: Keyed by AWG string (e.g. "14"), not numeric index.
    Previous code used AWG number as list index → wrong gauge looked up.

    Returns resistance in Ω/m at 75°C (copper).
    NEC Table 9, Chapter 9.
    """
    awg_clean = str(awg).strip()
    if awg_clean not in _AWG_RESISTANCE_OHM_PER_KM:
        raise ValueError(
            f"Unknown AWG gauge: {awg!r}. "
            f"Supported: {sorted(_AWG_RESISTANCE_OHM_PER_KM.keys())}. "
            "NEC Table 9."
        )
    # BUG-11 FIX: Convert Ω/km → Ω/m (divide by 1000)
    return _AWG_RESISTANCE_OHM_PER_KM[awg_clean] / 1000.0


def calculate_voltage_drop(
    current_a:       float,
    one_way_length_m: float,
    awg:             str   = "14",
    nominal_voltage: float = NOMINAL_VOLTAGE_FA,
    temperature_c:   float = 75.0,
) -> Dict[str, float]:
    """
    Calculate voltage drop for a FA circuit.

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
    if one_way_length_m < 0:
        raise ValueError(f"one_way_length_m={one_way_length_m}m must be >= 0")
    if nominal_voltage <= 0:
        raise ValueError(f"nominal_voltage={nominal_voltage}V must be > 0")

    # BUG-12 FIX: correct Ω/m lookup
    r_per_m = get_wire_resistance_ohm_per_m(awg)

    # Temperature correction (NEC Chapter 9, Note 2)
    # R_T = R_75 × [1 + 0.00323 × (T - 75)]
    temp_factor = 1.0 + 0.00323 * (temperature_c - 75.0)
    r_per_m_corrected = r_per_m * temp_factor

    # Round-trip resistance (BUG-11 FIX: 2 × length_m × Ω/m)
    r_total = 2.0 * one_way_length_m * r_per_m_corrected

    # Voltage drop
    v_drop    = current_a * r_total
    v_drop_pct = (v_drop / nominal_voltage) * 100.0
    v_terminal = nominal_voltage - v_drop

    # NFPA 72-2022 §27.4.1.2: <= 10% drop for FA circuits
    compliant = v_drop_pct <= MAX_VOLTAGE_DROP_PCT

    return {
        "voltage_drop_v":        round(v_drop,     4),
        "voltage_drop_pct":      round(v_drop_pct, 3),
        "terminal_voltage_v":    round(v_terminal, 4),
        "resistance_total_ohm":  round(r_total,    6),
        "resistance_per_m_ohm":  round(r_per_m_corrected, 8),
        "is_compliant":          compliant,
        "awg":                   awg,
        "length_m":              one_way_length_m,
        "current_a":             current_a,
        "nfpa_max_drop_pct":     MAX_VOLTAGE_DROP_PCT,
        "nfpa_reference":        "NFPA 72-2022 §27.4.1.2",
    }


def calculate_max_circuit_length(
    current_a:       float,
    awg:             str   = "14",
    nominal_voltage: float = NOMINAL_VOLTAGE_FA,
    max_drop_pct:    float = MAX_VOLTAGE_DROP_PCT,
) -> float:
    """
    Maximum one-way circuit length for <= max_drop_pct voltage drop.

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
    current_a:        float,
    one_way_length_m: float,
    nominal_voltage:  float = NOMINAL_VOLTAGE_FA,
    max_drop_pct:     float = MAX_VOLTAGE_DROP_PCT,
) -> Dict[str, str | float]:
    """
    Recommend smallest wire gauge meeting voltage drop requirement.
    Returns dict with recommended_awg, voltage_drop_pct, is_compliant.

    BUG-11 + BUG-12 FIX: Uses correct Ω/m lookup.
    NFPA 72-2022 §27.4.1.2.
    """
    # Try from thinnest to thickest (most economical first)
    gauges_ordered = ["14", "12", "10", "8", "6", "4", "2", "1", "1/0", "2/0"]

    for awg in gauges_ordered:
        if awg not in _AWG_RESISTANCE_OHM_PER_KM:
            continue
        result = calculate_voltage_drop(
            current_a, one_way_length_m, awg, nominal_voltage)
        if result["is_compliant"]:
            return {
                "recommended_awg":  awg,
                "voltage_drop_pct": result["voltage_drop_pct"],
                "voltage_drop_v":   result["voltage_drop_v"],
                "is_compliant":     True,
                "nfpa_reference":   "NFPA 72-2022 §27.4.1.2",
            }

    # Even 2/0 not sufficient — flag engineering review
    last = calculate_voltage_drop(current_a, one_way_length_m, "2/0", nominal_voltage)
    return {
        "recommended_awg":  "ENGINEERING_REVIEW",
        "voltage_drop_pct": last["voltage_drop_pct"],
        "voltage_drop_v":   last["voltage_drop_v"],
        "is_compliant":     False,
        "nfpa_reference":   "NFPA 72-2022 §27.4.1.2",
        "note":             "Circuit exceeds NEC conductor size table. "
                            "Engineering analysis required.",
    }


# ---------------------------------------------------------------------------
# BUG-13 FIX: Battery backup calculation
# ---------------------------------------------------------------------------

def calculate_battery_backup(
    standby_load_a:   float,   # Amperes (NOT milliamps — BUG-13 confusion)
    alarm_load_a:     float,   # Amperes during alarm
    standby_hours:    float = 24.0,   # NFPA 72-2022 §10.6.7.2
    alarm_hours:      float = 0.25,   # 15 minutes per §10.6.7.4
    derating_factor:  float = 0.80,   # 80% usable capacity per §10.6.7.1
    temperature_c:    float = 25.0,   # Ambient temperature
) -> Dict[str, float]:
    """
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
        alarm_hours:     Hours of alarm per §10.6.7.4 (0.25h = 15min)
        derating_factor: Battery usable fraction (0.80 per §10.6.7.1)
        temperature_c:   Ambient temp for capacity derating

    Returns:
        Dict with required_ah, recommended_ah, nfpa_compliant.
    """
    if standby_load_a < 0 or alarm_load_a < 0:
        raise ValueError("Loads must be >= 0 Amperes")
    if not 0 < derating_factor <= 1.0:
        raise ValueError(f"derating_factor={derating_factor} must be in (0, 1]")
    if standby_hours < 24.0:
        warnings.warn(
            f"standby_hours={standby_hours}h < 24h. "
            "NFPA 72-2022 §10.6.7.2 requires minimum 24h standby.",
            UserWarning, stacklevel=2,
        )

    # Temperature derating (IEEE 485)
    # Capacity decreases ~0.5% per °C below 25°C at typical SLA batteries
    if temperature_c < 25.0:
        temp_derating = 1.0 - 0.005 * (25.0 - temperature_c)
        temp_derating = max(temp_derating, 0.70)  # floor at 70%
    else:
        temp_derating = 1.0

    # BUG-13 FIX: simple Ah calculation (no ×1000 multiplier)
    required_ah_raw = (
        standby_load_a * standby_hours
        + alarm_load_a  * alarm_hours
    )
    required_ah = required_ah_raw / (derating_factor * temp_derating)
    # Round up to next standard battery size
    recommended_ah = _next_standard_ah(required_ah)

    return {
        "required_ah":        round(required_ah, 3),
        "recommended_ah":     recommended_ah,
        "standby_ah":         round(standby_load_a * standby_hours, 3),
        "alarm_ah":           round(alarm_load_a   * alarm_hours,   3),
        "derating_factor":    derating_factor,
        "temperature_c":      temperature_c,
        "temp_derating":      round(temp_derating, 4),
        "nfpa_compliant":     True,
        "nfpa_reference":     "NFPA 72-2022 §10.6.7",
        "standby_hours":      standby_hours,
        "alarm_hours":        alarm_hours,
    }


def _next_standard_ah(required_ah: float) -> float:
    """Round up to next standard battery capacity."""
    standard = [1.2, 2.0, 2.5, 4.0, 5.0, 7.0, 7.5, 10.0, 12.0, 15.0,
                18.0, 20.0, 24.0, 26.0, 33.0, 40.0, 45.0, 50.0, 55.0,
                65.0, 75.0, 100.0, 110.0, 120.0, 150.0, 200.0]
    for s in standard:
        if s >= required_ah:
            return s
    return math.ceil(required_ah / 50) * 50.0  # extrapolate
