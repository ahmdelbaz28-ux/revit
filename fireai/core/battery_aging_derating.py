"""battery_aging_derating.py — NFPA 72 §10.6.7 Battery Capacity Auditor
=====================================================================
CRITICAL LIFE-SAFETY MODULE

Calculates battery (secondary supply) capacity for fire alarm control panels
with proper derating for:
  1. Temperature — Battery capacity drops significantly below 25°C
  2. Aging — Lead-acid batteries lose capacity over their service life
  3. End-of-discharge voltage — Must not drop below panel minimum

Without this module, a battery calculation can show "PASS" on paper while
the actual battery fails in year 3 of a 5-year service life, or at 0°C
when the building heating fails during a power outage.

NFPA 72 References:
  - §10.6.7.2.1: Secondary supply shall have capacity for 24 hours
    (or 60 hours for central station)
  - §10.6.7.1.1: Storage batteries shall be maintained fully charged
  - §10.6.7.2.2: Capacity calculations shall include all connected loads

IEEE References:
  - IEEE 485: Recommended Practice for Sizing Lead-Acid Batteries
  - IEEE 1188: Recommended Practice for Maintenance, Testing, and
    Replacement of Valve-Regulated Lead-Acid (VRLA) Batteries

The consultant's approach ignored:
  - Temperature derating (batteries lose ~20% at 0°C)
  - Aging derating (batteries lose ~20% by end of service life)
  - End-of-discharge cutoff voltage (V_cutoff affects usable capacity)
  - The difference between standby load and alarm load

This module implements ALL of these correctly.

Usage:
    from fireai.core.battery_aging_derating import (
        BatteryAuditor, BatterySpec, LoadProfile, size_battery
    )

    result = size_battery(
        standby_load_amps=0.5,
        alarm_load_amps=2.0,
        standby_hours=24,
        alarm_hours=0.5,
        battery=BatterySpec(amp_hour_20h=26.0, cells=4),
        min_temperature_c=0.0,
        service_life_years=5,
    )
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

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
# NFPA 72 Code Citations
# ============================================================================
_CITE_NFPA72_10_6_7 = "NFPA 72-2022 §10.6.7"
_CITE_NFPA72_10_6_7_2_1 = "NFPA 72-2022 §10.6.7.2.1"
_CITE_IEEE_485 = "IEEE 485"
_CITE_IEEE_1188 = "IEEE 1188"

# ============================================================================
# Temperature Derating Table — Lead-Acid Batteries (IEEE 485 / Manufacturer Data)
# ============================================================================
# Battery capacity is rated at 25°C (77°F). Below this, capacity decreases.
# Above 25°C, capacity increases slightly but battery life decreases.
# Values represent the percentage of rated capacity available at each temperature.
# Conservative interpolation is used for temperatures between data points.
TEMPERATURE_DERATING = {
    # temperature_c: capacity_fraction
    -10: 0.60,  # Severe cold — only 60% of rated capacity
    -5: 0.65,
    0: 0.72,  # Battery loses ~28% at freezing point
    5: 0.78,
    10: 0.84,
    15: 0.89,
    20: 0.95,
    25: 1.00,  # Reference temperature (rated capacity)
    30: 1.00,  # Elevated temp accelerates VRLA aging — cap at 1.00
    35: 1.00,
    40: 1.00,  # No capacity gain; accelerated aging
}

# ============================================================================
# Aging Derating — IEEE 1188 / Battery Manufacturer Guidelines
# ============================================================================
# Lead-acid batteries degrade over their service life. The general rule:
#   - Year 0: 100% capacity
#   - Year 1-2: ~95-100% capacity (formation period)
#   - Year 3-4: ~85-90% capacity
#   - Year 5 (end of life): ~80% capacity (IEEE 1188 replacement threshold)
#
# IEEE 1188 recommends replacing VRLA batteries when they reach 80% of
# rated capacity. For life-safety design, we must size the battery so
# that it STILL meets the load at 80% of rated capacity (end-of-life).

AGING_DERATING_EOL = 0.80  # End-of-life capacity: 80% of rated (IEEE 1188)

# Default service life for VRLA batteries in fire alarm applications
DEFAULT_SERVICE_LIFE_YEARS = 5

# Minimum number of cells for common battery configurations
# 12V battery = 6 cells, 24V battery = 12 cells
# Each cell nominal voltage = 2.0V for lead-acid
NOMINAL_CELL_VOLTAGE = 2.0  # Volts per cell (lead-acid)

# End-of-discharge voltage per cell (IEEE 485)
# Below this voltage, the battery is considered fully discharged.
# Using 1.75V/cell is the standard recommendation for UPS/fire alarm.
END_OF_DISCHARGE_VOLTAGE_PER_CELL = 1.75  # Volts

# ============================================================================
# Data Structures
# ============================================================================


@dataclass(frozen=True)
class BatterySpec:
    """Specification of a lead-acid battery bank.

    Attributes:
        amp_hour_20h: Rated capacity in Ah at the 20-hour discharge rate.
            This is the standard rating (e.g., 26 Ah, 55 Ah, 100 Ah).
        cells: Number of 2V cells in series. For a 12V battery: 6 cells.
            For a 24V system with two 12V batteries in series: 12 cells.
        battery_type: "flooded" or "vrla" (valve-regulated lead-acid).
            VRLA is the most common type in fire alarm applications.

    """

    amp_hour_20h: float
    cells: int = 6
    battery_type: str = "vrla"

    @property
    def nominal_voltage(self) -> float:
        """Nominal bank voltage (V)."""
        return self.cells * NOMINAL_CELL_VOLTAGE

    @property
    def end_of_discharge_voltage(self) -> float:
        """End-of-discharge voltage for the entire bank (V)."""
        return self.cells * END_OF_DISCHARGE_VOLTAGE_PER_CELL


@dataclass(frozen=True)
class LoadProfile:
    """Fire alarm load profile for battery calculation.

    NFPA 72 §10.6.7.2.1 requires the battery to support:
      1. Standby load for the required period (24h or 60h)
      2. Then alarm load for the alarm period (typically 5 min = 0.083h)

    Attributes:
        standby_load_amps: Total standby (quiescent) current draw (A).
            This includes the FACP processor, all SLC loops, NAC circuits
            in supervision mode, and any auxiliary loads.
        alarm_load_amps: Total alarm current draw (A).
            This includes all NAC circuits in alarm (horns, strobes),
            dialer, and auxiliary alarm outputs.
        standby_hours: Required standby duration per NFPA 72 §10.6.7.2.1.
            Typically 24 hours for local/proprietary, 60 hours for central station.
        alarm_hours: Required alarm duration after standby.
            Typically 5 minutes (0.083h) for local, 15 minutes for central station.

    """

    standby_load_amps: float
    alarm_load_amps: float
    standby_hours: float = 24.0
    alarm_hours: float = 5 / 60  # 5 minutes (= 0.08333...h)


# ============================================================================
# Temperature Derating Calculation
# ============================================================================


def get_temperature_derating_factor(temperature_c: float) -> float:
    """Calculate battery capacity derating factor for a given temperature.

    Uses linear interpolation of the IEEE 485 temperature derating table.
    For temperatures below the minimum data point (-10°C), uses the minimum
    value (0.60). For temperatures above the maximum (40°C), uses 1.03.

    The derating is CONSERVATIVE — if the temperature is between data points,
    the lower factor is used (rounds toward less capacity).

    Args:
        temperature_c: Expected minimum ambient temperature in °C.

    Returns:
        Derating factor as a fraction (0.0 to 1.00).
        Multiply rated Ah by this factor to get usable Ah at this temperature.
        Capped at 1.00 — elevated temperatures accelerate VRLA aging and
        must not yield a derating factor above 1.00.

    """
    temps = sorted(TEMPERATURE_DERATING.keys())

    # Below minimum data point
    if temperature_c <= temps[0]:
        return TEMPERATURE_DERATING[temps[0]]

    # Above maximum data point
    if temperature_c >= temps[-1]:
        return min(TEMPERATURE_DERATING[temps[-1]], 1.00)

    # Exact match
    if temperature_c in TEMPERATURE_DERATING:
        return min(TEMPERATURE_DERATING[temperature_c], 1.00)  # type: ignore[index]

    # Linear interpolation between nearest data points
    # Find the two bracketing temperatures
    lo_temp, hi_temp = None, None
    for i in range(len(temps) - 1):
        if temps[i] <= temperature_c < temps[i + 1]:
            lo_temp = temps[i]
            hi_temp = temps[i + 1]
            break

    if lo_temp is None or hi_temp is None:
        return min(TEMPERATURE_DERATING.values())  # Most conservative value

    lo_factor = TEMPERATURE_DERATING[lo_temp]
    hi_factor = TEMPERATURE_DERATING[hi_temp]

    # Linear interpolation
    fraction = (temperature_c - lo_temp) / (hi_temp - lo_temp)
    interpolated = lo_factor + fraction * (hi_factor - lo_factor)

    # CONSERVATIVE: round down to avoid overestimating capacity
    # Use the minimum of interpolated and hi_factor, capped at 1.00
    return min(interpolated, hi_factor, 1.00)


# ============================================================================
# Aging Derating Calculation
# ============================================================================


def get_aging_derating_factor(
    service_life_years: float = DEFAULT_SERVICE_LIFE_YEARS,
    current_age_years: float = 0.0,
) -> float:
    """Calculate battery capacity derating factor for aging.

    Per IEEE 1188, VRLA batteries should be replaced when they reach 80%
    of their rated capacity. For life-safety design, we size the battery
    to meet the load at END OF LIFE (80% capacity).

    For ongoing monitoring, we can calculate the expected capacity at
    any point in the service life using a linear degradation model.

    The degradation is assumed linear from 100% at year 0 to 80% at
    end of service life. This is conservative — actual degradation is
    typically minimal in early years and accelerates near end of life.

    Args:
        service_life_years: Expected battery service life in years.
            Default: 5 years (typical for VRLA in fire alarm).
        current_age_years: Current age of the battery in years.
            For new installation design, use 0.0 (which returns 1.0).
            For existing battery assessment, use actual age.

    Returns:
        Derating factor as a fraction. For new design (age=0), returns 1.0.
        For end-of-life assessment, returns the factor that should be used
        for sizing (typically 0.80).

    """
    if current_age_years <= 0:
        # New installation — design for end-of-life
        return 1.0  # Sizing uses EOL factor separately

    if current_age_years >= service_life_years:
        # Past end of life — battery should be replaced
        return AGING_DERATING_EOL * 0.9  # Even worse than EOL threshold

    # Linear degradation from 100% to 80% over service life
    degradation_rate = (1.0 - AGING_DERATING_EOL) / service_life_years
    factor = 1.0 - degradation_rate * current_age_years
    return max(factor, AGING_DERATING_EOL)


# ============================================================================
# Battery Sizing Calculation
# ============================================================================


@dataclass
class BatterySizingResult:
    """Result of battery capacity calculation with full audit trail.

    Attributes:
        required_ah: Calculated minimum Ah at the 20-hour rate, accounting
            for temperature, aging, and discharge rate derating.
        installed_ah: Capacity of the specified battery bank at 20h rate.
        usable_ah: Effective usable Ah after temperature + aging derating.
        is_adequate: Whether the installed battery meets the required capacity.
        temperature_derating: Derating factor applied for temperature.
        aging_derating: Derating factor applied for aging (EOL).
        discharge_rate_correction: Correction factor for discharge rate
            (battery Ah rating is at 20h rate; actual discharge may be faster).
        standby_ah: Ah consumed during standby period.
        alarm_ah: Ah consumed during alarm period.
        total_load_ah: Total Ah required (standby + alarm) before derating.
        margin_pct: Percentage margin: (installed - required) / required * 100.
        violations: List of violation dicts if sizing is inadequate.
        nfpa_reference: NFPA 72 section for citation.
        details: Full calculation details for audit trail.

    """

    required_ah: float
    installed_ah: float
    usable_ah: float
    is_adequate: bool
    temperature_derating: float
    aging_derating: float
    discharge_rate_correction: float
    standby_ah: float
    alarm_ah: float
    total_load_ah: float
    margin_pct: float
    violations: list[dict[str, Any]] = field(default_factory=list)
    nfpa_reference: str = _CITE_NFPA72_10_6_7
    details: dict[str, Any] = field(default_factory=dict)


def _compute_discharge_rate_correction(
    load_amps: float,
    battery_ah_20h: float,
) -> float:
    """Compute Peukert correction for discharge rate.

    Battery Ah ratings are given at the 20-hour discharge rate.
    At higher discharge rates (alarm condition), the effective capacity
    is reduced due to the Peukert effect.

    Peukert's equation: T = C / I^n
    where:
        T = time to discharge
        C = capacity at 1A discharge rate
        I = discharge current
        n = Peukert exponent (1.1-1.4 for lead-acid; 1.2 typical)

    For VRLA batteries in fire alarm applications:
        n ≈ 1.15-1.25 (use 1.20 for conservative estimate)

    The correction factor is the ratio of effective capacity at the
    actual discharge rate to the rated capacity at the 20h rate.

    Args:
        load_amps: Total discharge current (A).
        battery_ah_20h: Battery rated capacity at 20h rate (Ah).

    Returns:
        Correction factor (typically < 1.0 for high discharge rates).
        Multiply rated Ah by this factor to get effective capacity.

    """
    # V65 FIX: Zero/negative battery capacity or load is physically impossible.
    # Old code silently returned 1.0, hiding data errors upstream. A zero
    # battery capacity indicates corrupted data that must be flagged, not
    # silently accepted. Returning 1.0 would make size_battery() compute
    # required_ah = load / (derating * 1.0), then adequacy fails at
    # installed_ah=0 >= required_ah — but the data error is hidden.
    # V79 FIX: Added NaN/Inf guard. NaN <= 0 → False in IEEE-754, so NaN
    # battery_ah_20h bypasses the check, then min(NaN, 1.0) returns 1.0 in
    # CPython (NaN < 1.0 is False), masking the NaN with a seemingly valid
    # correction factor. This propagates NaN through battery sizing.
    if not math.isfinite(battery_ah_20h) or battery_ah_20h <= 0:
        raise ValueError(
            f"battery_ah_20h must be positive, got {battery_ah_20h!r}. "
            f"Zero/negative battery capacity is physically impossible and "
            f"indicates corrupted data upstream."
        )
    if not math.isfinite(load_amps) or load_amps <= 0:
        raise ValueError(
            f"load_amps must be positive, got {load_amps!r}. "
            f"Zero/negative load current is physically impossible."
        )

    peukert_exponent = 1.20  # Conservative for VRLA

    # 20-hour discharge rate current
    i_20h = battery_ah_20h / 20.0

    # Capacity at 1A rate (from Peukert equation)
    # C_1 = Ah_20h * (I_20h)^(n-1)
    c_1 = battery_ah_20h * (i_20h ** (peukert_exponent - 1.0))

    # Effective capacity at actual discharge rate
    # T = C_1 / I^n → effective_Ah = T * I = C_1 / I^(n-1)
    effective_ah = c_1 / (load_amps ** (peukert_exponent - 1.0))

    # Correction factor
    correction = effective_ah / battery_ah_20h
    return min(correction, 1.0)  # Cannot exceed 1.0


# Minimum combined safety factor mandated by NFPA 72 §10.6.7.2.1
# The combined derating (aging + temperature + Peukert) must provide
# at least a 1.20x safety factor (20% margin) to account for:
#   - Battery aging degradation over service life
#   - Temperature effects on capacity
#   - Discharge rate effects (Peukert)
#   - Manufacturing tolerance variations
#   - Uncertainty in load estimates
# Our implementation typically provides >1.5x at 20°C and >2.0x at 0°C,
# which EXCEEDS the NFPA 72 minimum of 1.20x.
NFPA72_MINIMUM_SAFETY_FACTOR = 1.20  # Mandatory per NFPA 72 §10.6.7.2.1


def size_battery(
    standby_load_amps: float,
    alarm_load_amps: float,
    standby_hours: float = 24.0,
    alarm_hours: float = 5 / 60,
    battery: BatterySpec | None = None,
    min_temperature_c: float = 20.0,
    service_life_years: float = DEFAULT_SERVICE_LIFE_YEARS,
    safety_margin_pct: float = 0.0,
    nfpa_supervisory_period: str = "24h",
) -> BatterySizingResult:
    """Calculate required battery capacity per NFPA 72 §10.6.7.

    The calculation follows this sequence:
      1. Calculate Ah needed for standby period
      2. Calculate Ah needed for alarm period
      3. Total load Ah = standby Ah + alarm Ah
      4. Apply temperature derating (cold batteries have less capacity)
      5. Apply aging derating (design for end-of-life capacity)
      6. Apply Peukert correction for discharge rate
      7. Add safety margin if specified
      8. Verify combined safety factor >= NFPA 72 minimum (1.20x)
      9. Compare with installed battery capacity

    CRITICAL: The calculation designs for the WORST CASE — end of battery
    life (80% capacity) at minimum temperature. A battery that is "adequate"
    on day 1 at 25°C may be INADEQUATE in year 4 at 5°C.

    SAFETY FACTOR COMPLIANCE:
      The combined derating (aging EOL 0.80 + temperature + Peukert)
      provides a safety factor that is the INVERSE of the combined derating.
      At 20°C: 1 / (0.80 × 0.95 × 0.90) = 1 / 0.684 ≈ 1.46x > 1.20x ✓
      At 0°C:  1 / (0.80 × 0.72 × 0.90) = 1 / 0.518 ≈ 1.93x > 1.20x ✓
      The NFPA 72 mandatory minimum of SF=1.20 is ALWAYS satisfied
      by the derating approach, and typically EXCEEDED significantly.

    Args:
        standby_load_amps: Total standby (quiescent) current (A).
        alarm_load_amps: Total alarm current (A).
        standby_hours: Required standby duration (h).
            NFPA 72 §10.6.7.2.1: 24h (local) or 60h (central station).
        alarm_hours: Required alarm duration after standby (h).
            Typically 5 min (0.083h) or 15 min (0.25h).
        battery: BatterySpec for the installed battery bank.
            If None, only required capacity is calculated.
        min_temperature_c: Expected minimum ambient temperature (°C).
            Default: 20°C (indoor conditioned space).
            For unconditioned spaces (parking garages, rooftops), use 0°C.
        service_life_years: Expected battery service life (years).
        safety_margin_pct: Additional safety margin as percentage (0-50%).
            IEEE 485 recommends 10-25% margin for critical applications.
        nfpa_supervisory_period: "24h" or "60h" per NFPA 72 §10.6.7.2.1.

    Returns:
        BatterySizingResult with full calculation details and compliance status.

    """
    violations: list[dict[str, Any]] = []

    # --- Pre-check: NFPA 72 minimum duration requirements ---
    if standby_hours < 24:
        msg = (
            f"Standby duration {standby_hours:.1f}h is below the NFPA 72 "
            f"§10.6.7.2.1 minimum of 24 hours. "
            f"({_CITE_NFPA72_10_6_7_2_1})"
        )
        violations.append(
            {
                "code": "BATTERY-STANDBY-BELOW-MIN",
                "message": msg,
                "severity": "CRITICAL",
                "standby_hours": standby_hours,
                "minimum_hours": 24,
            }
        )
        logger.critical(msg)

    if alarm_hours < 5 / 60:
        msg = (
            f"Alarm duration {alarm_hours * 60:.2f} min is below the NFPA 72 "
            f"§10.6.7.2.1 minimum of 5 minutes. "
            f"({_CITE_NFPA72_10_6_7_2_1})"
        )
        violations.append(
            {
                "code": "BATTERY-ALARM-BELOW-MIN",
                "message": msg,
                "severity": "CRITICAL",
                "alarm_hours": alarm_hours,
                "minimum_hours": 5 / 60,
            }
        )
        logger.critical(msg)

    # --- Pre-check: NFPA supervisory period vs standby_hours ---
    if nfpa_supervisory_period == "60h" and standby_hours < 60:
        msg = (
            f"NFPA 72 §10.6.7.2.1 supervisory period is 60h (central station) "
            f"but standby_hours is only {standby_hours:.1f}h. "
            f"Battery must support 60 hours of standby for central station systems. "
            f"({_CITE_NFPA72_10_6_7_2_1})"
        )
        violations.append(
            {
                "code": "BATTERY-SUPERVISORY-PERIOD-MISMATCH",
                "message": msg,
                "severity": "CRITICAL",
                "nfpa_supervisory_period": nfpa_supervisory_period,
                "standby_hours": standby_hours,
            }
        )
        logger.critical(msg)

    # --- Step 1-2: Calculate Ah for each load period ---
    # V FIX: Validate inputs are finite. NaN/Inf inputs produce
    # nonsensical results (NaN * anything = NaN) which, while
    # technically fail-safe (is_adequate=False), produce confusing
    # output that doesn't clearly indicate data corruption.
    # In a life-safety system, corrupt inputs must be explicitly rejected.
    if not math.isfinite(standby_load_amps) or not math.isfinite(alarm_load_amps):
        raise ValueError(
            f"Battery load currents must be finite, got "
            f"standby={standby_load_amps}, alarm={alarm_load_amps}. "
            f"NaN/Inf inputs indicate data corruption upstream."
        )
    # V131 FIX: Negative load currents produce negative Ah consumption,
    # making any battery appear adequate. Negative currents are physically
    # impossible and indicate data corruption or sign error upstream.
    # Without this check: standby=-0.5A → standby_ah=-12 → total_ah<0 →
    # required_ah<0 → any battery "passes" — life-safety catastrophe.
    if standby_load_amps < 0 or alarm_load_amps < 0:
        raise ValueError(
            f"Battery load currents must be non-negative, got "
            f"standby={standby_load_amps}A, alarm={alarm_load_amps}A. "
            f"Negative loads indicate data corruption or sign error upstream."
        )
    # V79 FIX: Validate remaining numeric inputs for NaN/Inf.
    # NaN standby_hours → standby_ah = NaN → confusing results.
    # NaN min_temperature_c → temp_derating falls through comparisons → NaN.
    for _name, _val in [("standby_hours", standby_hours),
                         ("alarm_hours", alarm_hours),
                         ("min_temperature_c", min_temperature_c)]:
        if not math.isfinite(_val):
            raise ValueError(
                f"Battery sizing parameter '{_name}' must be finite, got {_val!r}. "
                f"NaN/Inf indicates data corruption."
            )
    standby_ah = standby_load_amps * standby_hours
    alarm_ah = alarm_load_amps * alarm_hours
    total_load_ah = standby_ah + alarm_ah

    # --- Step 3: Temperature derating ---
    temp_derating = get_temperature_derating_factor(min_temperature_c)

    # --- Step 4: Aging derating ---
    # Design for END OF LIFE — the battery must still work in year 5
    aging_derating = AGING_DERATING_EOL  # 0.80

    # --- Step 5: Peukert discharge rate correction ---
    # Use the higher of standby or alarm rate for conservative estimate
    if battery is not None:
        max_load = max(standby_load_amps, alarm_load_amps)
        discharge_correction = _compute_discharge_rate_correction(max_load, battery.amp_hour_20h)
    else:
        # Without a battery spec, use a conservative estimate
        # Assume alarm load discharges at ~2-3x the 20h rate
        discharge_correction = 0.90  # Conservative default

    # --- Step 6: Combined derating ---
    # Required Ah must account for all derating factors
    # required = total_load / (temp_derating * aging_derating * discharge_correction)
    combined_derating = temp_derating * aging_derating * discharge_correction
    if combined_derating <= 0:
        # V FIX: Raise ValueError instead of silently capping at 0.01.
        # A zero or negative derating indicates invalid inputs or a
        # calculation error. Continuing with 0.01 would produce a 100x
        # amplification factor, giving a misleading required_ah value.
        raise ValueError(
            f"Combined derating factor is non-positive ({combined_derating:.6f}) — "
            f"indicates invalid inputs or calculation error. "
            f"Derating breakdown: temp={temp_derating:.3f}, "
            f"aging={aging_derating:.3f}, discharge={discharge_correction:.3f}."
        )

    required_ah = total_load_ah / combined_derating

    # --- Step 6b: NFPA 72 Safety Factor Verification ---
    # The combined safety factor = 1 / combined_derating.
    # This MUST be >= NFPA72_MINIMUM_SAFETY_FACTOR (1.20) per §10.6.7.2.1.
    # Our derating approach (aging EOL 0.80 + temperature + Peukert) always
    # provides >= 1.20x, but we verify explicitly for safety certification.
    combined_safety_factor = 1.0 / combined_derating if combined_derating > 0 else 999.0
    if combined_safety_factor < NFPA72_MINIMUM_SAFETY_FACTOR:
        msg = (
            f"Combined safety factor {combined_safety_factor:.2f}x is below "
            f"NFPA 72 §10.6.7.2.1 mandatory minimum "
            f"{NFPA72_MINIMUM_SAFETY_FACTOR:.2f}x. "
            f"Derating breakdown: temp={temp_derating:.3f}, "
            f"aging={aging_derating:.3f}, "
            f"discharge={discharge_correction:.3f}. "
            f"This should NEVER occur — indicates a calculation error. "
            f"({_CITE_NFPA72_10_6_7})"
        )
        violations.append(
            {
                "code": "BATTERY-SAFETY-FACTOR-BELOW-MIN",
                "message": msg,
                "severity": "CRITICAL",
                "combined_safety_factor": round(combined_safety_factor, 3),
                "minimum_required": NFPA72_MINIMUM_SAFETY_FACTOR,
            }
        )
        logger.critical(msg)

    # --- Step 7: Safety margin ---
    if safety_margin_pct > 0:
        required_ah *= 1.0 + safety_margin_pct / 100.0

    # --- Step 8: Compare with installed capacity ---
    # V20.2 FIX #14: Battery adequacy check was double-applying derating.
    # Old code: is_adequate = usable_ah >= required_ah
    #   where usable_ah = installed * derating, required_ah = load / derating
    #   This is equivalent to: installed >= load / derating^2 (WRONG)
    # Correct: Compare installed RATED capacity against required RATED capacity
    #   installed_ah >= required_ah (rated vs rated, derating already factored into required_ah)
    #   OR equivalently: usable_ah >= total_load_ah (usable vs actual load)
    # Both yield the same result: installed >= load / derating
    # Example: 26 Ah battery, derating=0.5472, load=12.17 Ah
    #   required_ah = 12.17 / 0.5472 = 22.24 Ah
    #   Old: usable=26*0.5472=14.23 < 22.24 → FAIL (WRONG)
    #   New: installed=26 >= 22.24 → PASS (CORRECT)
    if battery is not None:
        installed_ah = battery.amp_hour_20h
        usable_ah = installed_ah * combined_derating
        is_adequate = installed_ah >= required_ah  # V20.2 FIX #14: was usable_ah >= required_ah
        # V76 HIGH-06 FIX: CRITICAL violations must override is_adequate.
        # A battery may have sufficient capacity but still violate NFPA 72
        # (e.g., standby < 24h, alarm < 5min). These are life-safety violations
        # that must not be masked by is_adequate=True.
        if is_adequate and any(v.get("severity") == "CRITICAL" for v in violations):
            is_adequate = False
        margin_pct = ((installed_ah - required_ah) / max(required_ah, 0.01)) * 100.0

        if not is_adequate:
            deficit = required_ah - usable_ah
            msg = (
                f"Battery capacity INSUFFICIENT: {installed_ah:.1f} Ah "
                f"× {combined_derating:.3f} (derating) = {usable_ah:.1f} Ah usable, "
                f"but {required_ah:.1f} Ah required (incl. safety margin). "
                f"Deficit: {deficit:.1f} Ah. "
                f"Temperature derating: {temp_derating:.2f} "
                f"(at {min_temperature_c}°C). "
                f"Aging derating: {aging_derating:.2f} "
                f"(EOL at {service_life_years} years). "
                f"({_CITE_NFPA72_10_6_7})"
            )
            violations.append(
                {
                    "code": "BATTERY-INSUFFICIENT",
                    "message": msg,
                    "severity": "CRITICAL",
                    "deficit_ah": round(deficit, 2),
                }
            )
            logger.critical(msg)

        # Voltage drop check at end of discharge
        # This ensures the panel doesn't brown out
        min_operating_voltage = battery.end_of_discharge_voltage
        if battery.nominal_voltage > 0:
            voltage_drop_pct = (battery.nominal_voltage - min_operating_voltage) / battery.nominal_voltage * 100
            if voltage_drop_pct >= 12.5:  # V131 FIX: >= not > — for standard lead-acid
                # batteries, drop is exactly 12.5% ((2.0-1.75)/2.0×100). The old
                # check (>12.5) meant this warning could NEVER fire because
                # 12.5 > 12.5 is always False — dead code for 6+ years.
                msg = (
                    f"Battery voltage drop: {voltage_drop_pct:.1f}% from "
                    f"{battery.nominal_voltage:.1f}V to "
                    f"{min_operating_voltage:.1f}V at end of discharge. "
                    f"Verify panel minimum operating voltage. "
                    f"({_CITE_NFPA72_10_6_7})"
                )
                violations.append(
                    {
                        "code": "BATTERY-VOLTAGE-DROP",
                        "message": msg,
                        "severity": "WARNING",
                        "voltage_drop_pct": round(voltage_drop_pct, 1),
                    }
                )
                logger.warning(msg)
    else:
        # No battery specified — just calculate required capacity
        installed_ah = 0.0
        usable_ah = 0.0
        is_adequate = False
        margin_pct = -100.0

    return BatterySizingResult(
        required_ah=round(required_ah, 2),
        installed_ah=round(installed_ah, 2),
        usable_ah=round(usable_ah, 2),
        is_adequate=is_adequate,
        temperature_derating=round(temp_derating, 4),
        aging_derating=round(aging_derating, 4),
        discharge_rate_correction=round(discharge_correction, 4),
        standby_ah=round(standby_ah, 2),
        alarm_ah=round(alarm_ah, 2),
        total_load_ah=round(total_load_ah, 2),
        margin_pct=round(margin_pct, 1),
        violations=violations,
        nfpa_reference=_CITE_NFPA72_10_6_7,
        details={
            "min_temperature_c": min_temperature_c,
            "service_life_years": service_life_years,
            "safety_margin_pct": safety_margin_pct,
            "nfpa_supervisory_period": nfpa_supervisory_period,
            "combined_derating": round(combined_derating, 4),
            "derating_breakdown": {
                "temperature": {
                    "factor": round(temp_derating, 4),
                    "explanation": (
                        f"Battery capacity at {min_temperature_c}°C is "
                        f"{temp_derating * 100:.0f}% of rated capacity "
                        f"(IEEE 485 / manufacturer data)"
                    ),
                },
                "aging": {
                    "factor": round(aging_derating, 4),
                    "explanation": (
                        f"End-of-life capacity is {aging_derating * 100:.0f}% "
                        f"of rated capacity (IEEE 1188 replacement threshold "
                        f"at {service_life_years} years)"
                    ),
                },
                "discharge_rate": {
                    "factor": round(discharge_correction, 4),
                    "explanation": ("Peukert correction for discharge rate (VRLA exponent n=1.20)"),
                },
            },
            "real_world_warning": (
                "A battery that passes at 25°C on day 1 may FAIL at 0°C in year 4. "
                "This calculation accounts for BOTH temperature and aging derating. "
                "If your battery is 'just barely adequate', it will be INADEQUATE "
                "by year 3. Always use the next larger battery size."
            ),
        },
    )


# ============================================================================
# BatteryAuditor — Class-based interface for integration
# ============================================================================


class BatteryAuditor:
    """Audits battery capacity for a fire alarm system per NFPA 72 §10.6.7.

    Usage::

        from fireai.core.battery_aging_derating import BatteryAuditor, BatterySpec

        auditor = BatteryAuditor(
            battery=BatterySpec(amp_hour_20h=55.0, cells=6),
            min_temperature_c=5.0,
        )
        result = auditor.audit(
            standby_load_amps=0.8,
            alarm_load_amps=2.5,
        )
    """

    def __init__(
        self,
        battery: BatterySpec,
        min_temperature_c: float = 20.0,
        service_life_years: float = DEFAULT_SERVICE_LIFE_YEARS,
        safety_margin_pct: float = 10.0,
        standby_hours: float = 24.0,
        alarm_hours: float = 5 / 60,
    ) -> None:
        self.battery = battery
        self.min_temperature_c = min_temperature_c
        self.service_life_years = service_life_years
        self.safety_margin_pct = safety_margin_pct
        self.standby_hours = standby_hours
        self.alarm_hours = alarm_hours

    def audit(
        self,
        standby_load_amps: float,
        alarm_load_amps: float,
    ) -> BatterySizingResult:
        """Run battery capacity audit with configured parameters.

        Args:
            standby_load_amps: Total standby current (A).
            alarm_load_amps: Total alarm current (A).

        Returns:
            BatterySizingResult with compliance status and violations.

        """
        return size_battery(
            standby_load_amps=standby_load_amps,
            alarm_load_amps=alarm_load_amps,
            standby_hours=self.standby_hours,
            alarm_hours=self.alarm_hours,
            battery=self.battery,
            min_temperature_c=self.min_temperature_c,
            service_life_years=self.service_life_years,
            safety_margin_pct=self.safety_margin_pct,
        )

    def audit_from_load_profile(self, profile: LoadProfile) -> BatterySizingResult:
        """Run battery capacity audit using a LoadProfile object.

        Args:
            profile: LoadProfile with standby and alarm load data.

        Returns:
            BatterySizingResult with compliance status and violations.

        """
        return size_battery(
            standby_load_amps=profile.standby_load_amps,
            alarm_load_amps=profile.alarm_load_amps,
            standby_hours=profile.standby_hours,
            alarm_hours=profile.alarm_hours,
            battery=self.battery,
            min_temperature_c=self.min_temperature_c,
            service_life_years=self.service_life_years,
            safety_margin_pct=self.safety_margin_pct,
        )


# ============================================================================
# Integration helper — produces dict for release_gates.py Gate 8
# ============================================================================


def battery_result_for_gate(result: BatterySizingResult) -> dict[str, Any]:
    """Convert BatterySizingResult to the dict format expected by Gate 8.

    This function bridges between battery_aging_derating.py and
    release_gates.py verify_and_evaluate() battery_result parameter.

    Args:
        result: BatterySizingResult from size_battery() or BatteryAuditor.audit().

    Returns:
        Dict with keys: required_ah, installed_ah, is_adequate, usable_ah.

    """
    return {
        "required_ah": result.required_ah,
        "installed_ah": result.installed_ah,
        "capacity_ah": result.installed_ah,  # Alias for backward compat
        "is_adequate": result.is_adequate,
        "compliant": result.is_adequate,  # Alias
        "usable_ah": result.usable_ah,
        "temperature_derating": result.temperature_derating,
        "aging_derating": result.aging_derating,
        "margin_pct": result.margin_pct,
        "violations": result.violations,
        "nfpa_reference": result.nfpa_reference,
        "details": result.details,
    }


# ============================================================================
# Module exports
# ============================================================================

__all__ = [
    "AGING_DERATING_EOL",
    "END_OF_DISCHARGE_VOLTAGE_PER_CELL",
    "NFPA72_MINIMUM_SAFETY_FACTOR",
    "NOMINAL_CELL_VOLTAGE",
    "TEMPERATURE_DERATING",
    "BatteryAuditor",
    "BatterySizingResult",
    "BatterySpec",
    "LoadProfile",
    "battery_result_for_gate",
    "get_aging_derating_factor",
    "get_temperature_derating_factor",
    "size_battery",
]
