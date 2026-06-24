"""unit_converter.py — Safety-Critical Unit Conversion Utility
============================================================
LIFE-SAFETY CRITICAL: Incorrect unit conversions in BIM/Revit integration
lead to catastrophic engineering errors. A pipe sized in feet instead of
metres, or a pressure in psf instead of psi, can cause undersized fire
suppression systems that fail during a real fire, costing lives.

This module centralizes ALL unit conversions used in the FireAI system
to prevent the following failure modes:
  1. Magic number typos (0.3048 vs 0.3084) — caused by retyping instead of calling a function
  2. Revit internal units (decimal feet) confused with engineering units (metres, mm, psi)
  3. Imperial/metric mix-ups in hydraulic calculations (gpm vs L/min, psi vs bar)
  4. Missing conversion factors (e.g., ft²→m² uses 0.0929, not 0.3048²)

Standards:
  - Revit API: All internal lengths are decimal feet (1 ft = 0.3048 m exactly)
  - NFPA 13: Uses US customary units (gpm, psi, feet, inches)
  - SBC 801 / Egyptian Fire Code: May use SI units (L/min, bar, metres, mm)
  - IEC 60079: Uses SI units exclusively

References:
  - NIST Special Publication 811: Guide for the Use of the International System of Units
  - Revit API SDK: UnitUtils.Convert() for version-safe conversions
  - NFPA 13-2022 Chapter 23: Hydraulic calculation units

"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# EXACT CONVERSION FACTORS (NIST SP 811)
# ═══════════════════════════════════════════════════════════════════════════════

# Length
FEET_TO_METRES       = 0.3048      # Exact definition (1 ft = 0.3048 m since 1959)
METRES_TO_FEET       = 1.0 / 0.3048
INCHES_TO_MM         = 25.4        # Exact (1 in = 25.4 mm since 1959)
MM_TO_INCHES         = 1.0 / 25.4
FEET_TO_MM           = FEET_TO_METRES * 1000.0
MM_TO_FEET           = 1.0 / FEET_TO_MM
METRES_TO_MM         = 1000.0
MM_TO_METRES         = 0.001

# Area
SQFT_TO_SQM          = 0.09290304  # Exact (0.3048²)
SQM_TO_SQFT          = 1.0 / 0.09290304
SQIN_TO_SQMM         = 645.16      # Exact (25.4²)
SQMM_TO_SQIN         = 1.0 / 645.16

# Volume
CUBIC_FT_TO_CUBIC_M  = 0.028316846592  # Exact (0.3048³)
CUBIC_M_TO_CUBIC_FT  = 1.0 / 0.028316846592
GALLONS_US_TO_LITRES = 3.785411784      # Exact (1 US gal = 3.785411784 L)
LITRES_TO_GALLONS_US = 1.0 / 3.785411784

# Pressure
PSI_TO_BAR           = 0.0689476   # Approximate (1 psi ≈ 0.0689476 bar)
BAR_TO_PSI           = 1.0 / 0.0689476
PSI_TO_KPA           = 6.89476     # Approximate (1 psi ≈ 6.89476 kPa)
KPA_TO_PSI           = 1.0 / 6.89476
PSF_TO_PSI           = 1.0 / 144.0  # 1 psf = 1 lbf/ft², 1 psi = 144 psf
PSI_TO_PSF           = 144.0
PA_TO_PSI            = 1.0 / 6894.76

# Flow rate
GPM_TO_LPM           = 3.785411784  # 1 US gpm = 3.785411784 L/min
LPM_TO_GPM           = 1.0 / 3.785411784

# Temperature
FAHRENHEIT_OFFSET    = 32.0
FAHRENHEIT_SCALE     = 5.0 / 9.0  # °C = (°F - 32) × 5/9


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY-CRITICAL CONVERSION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def revit_internal_to_metres(internal_feet: float) -> float:
    """Convert Revit internal decimal feet to metres.

    SAFETY: This is the MOST CRITICAL conversion in the system.
    Revit stores ALL length measurements internally as decimal feet.
    If this conversion is wrong, ALL pipe sizes, room dimensions, and
    detector spacing calculations will be incorrect.

    NFPA 13 §23.4.4: Sprinkler spacing in feet must be correctly
    converted when the BIM model uses Revit internal units.

    Args:
        internal_feet: Length in Revit internal decimal feet.

    Returns:
        Length in metres.

    Raises:
        ValueError: If input is NaN or infinite.

    """
    if not math.isfinite(internal_feet):
        raise ValueError(
            f"Cannot convert non-finite value to metres: {internal_feet}. "
            "BIM model may contain corrupt geometry data."
        )
    return internal_feet * FEET_TO_METRES


def metres_to_revit_internal(metres: float) -> float:
    """Convert metres to Revit internal decimal feet.

    SAFETY: Reverse conversion for writing back to Revit model.
    An incorrect conversion here writes wrong pipe sizes into the BIM model.

    Args:
        metres: Length in metres.

    Returns:
        Length in Revit internal decimal feet.

    Raises:
        ValueError: If input is NaN, infinite, or negative (lengths must be >= 0).

    """
    if not math.isfinite(metres):
        raise ValueError(
            f"Cannot convert non-finite value to Revit feet: {metres}. "
            "Engineering calculation produced invalid result."
        )
    if metres < 0:
        raise ValueError(
            f"Negative metres value: {metres}. Physical length cannot be negative. "
            "Check engineering calculation for sign error."
        )
    return metres * METRES_TO_FEET


def revit_internal_to_mm(internal_feet: float) -> float:
    """Convert Revit internal decimal feet to millimetres.

    SAFETY: Used for pipe diameter display and specification.
    Confusing mm with inches causes 25.4x errors in pipe sizing.

    Args:
        internal_feet: Length in Revit internal decimal feet.

    Returns:
        Length in millimetres.

    Raises:
        ValueError: If input is NaN or infinite.

    """
    if not math.isfinite(internal_feet):
        raise ValueError(
            f"Cannot convert non-finite value to mm: {internal_feet}. "
            "BIM model may contain corrupt geometry data."
        )
    return internal_feet * FEET_TO_MM


def mm_to_revit_internal(mm: float) -> float:
    """Convert millimetres to Revit internal decimal feet.

    Args:
        mm: Length in millimetres.

    Returns:
        Length in Revit internal decimal feet.

    """
    if not math.isfinite(mm):
        raise ValueError(
            f"Cannot convert non-finite value to Revit feet: {mm}. "
            "Engineering specification contains invalid value."
        )
    return mm * MM_TO_FEET


def inches_to_mm(inches: float) -> float:
    """Convert inches to millimetres.

    SAFETY: Used for pipe diameter conversion in NFPA 13 hydraulic
    calculations. Internal pipe diameters in inches (e.g., 2.067" for
    2" Schedule 40) must be correctly converted for metric code compliance.

    Args:
        inches: Length in inches.

    Returns:
        Length in millimetres.

    """
    if not math.isfinite(inches):
        raise ValueError(f"Cannot convert non-finite inches: {inches}")
    if inches < 0:
        raise ValueError(f"Negative inches value: {inches}. Pipe diameter cannot be negative.")
    return inches * INCHES_TO_MM


def psi_to_bar(psi: float) -> float:
    """Convert psi to bar.

    SAFETY: Used when converting NFPA 13 (US customary) pressure values
    to SBC 801 / Egyptian Fire Code (SI) pressure values.

    Args:
        psi: Pressure in pounds per square inch.

    Returns:
        Pressure in bar.

    """
    if not math.isfinite(psi):
        raise ValueError(f"Cannot convert non-finite pressure: {psi}")
    return psi * PSI_TO_BAR


def bar_to_psi(bar: float) -> float:
    """Convert bar to psi.

    Args:
        bar: Pressure in bar.

    Returns:
        Pressure in pounds per square inch.

    """
    if not math.isfinite(bar):
        raise ValueError(f"Cannot convert non-finite pressure: {bar}")
    return bar * BAR_TO_PSI


def gpm_to_lpm(gpm: float) -> float:
    """Convert US gallons per minute to litres per minute.

    SAFETY: NFPA 13 uses gpm; SBC 801 / Egyptian Code may use L/min.
    Incorrect conversion causes undersized or oversized pipe networks.

    Args:
        gpm: Flow rate in US gallons per minute.

    Returns:
        Flow rate in litres per minute.

    """
    if not math.isfinite(gpm):
        raise ValueError(f"Cannot convert non-finite flow rate: {gpm}")
    if gpm < 0:
        raise ValueError(f"Negative flow rate: {gpm}. Flow cannot be negative.")
    return gpm * GPM_TO_LPM


def sqft_to_sqm(sqft: float) -> float:
    """Convert square feet to square metres.

    SAFETY: NFPA 13 design density is in gpm/sq.ft.; SBC 801 may use
    mm/min/m². Area conversion errors propagate into sprinkler count
    and pipe sizing calculations.

    Args:
        sqft: Area in square feet.

    Returns:
        Area in square metres.

    """
    if not math.isfinite(sqft):
        raise ValueError(f"Cannot convert non-finite area: {sqft}")
    if sqft < 0:
        raise ValueError(f"Negative area: {sqft}. Room area cannot be negative.")
    return sqft * SQFT_TO_SQM


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius.

    SAFETY: Used for ambient temperature in Burgess-Wheeler LFL correction
    and battery temperature derating. An incorrect temperature conversion
    causes wrong hazard zone extents or wrong battery sizing.

    Args:
        f: Temperature in degrees Fahrenheit.

    Returns:
        Temperature in degrees Celsius.

    """
    if not math.isfinite(f):
        raise ValueError(f"Cannot convert non-finite temperature: {f}")
    return (f - FAHRENHEIT_OFFSET) * FAHRENHEIT_SCALE


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit.

    Args:
        c: Temperature in degrees Celsius.

    Returns:
        Temperature in degrees Fahrenheit.

    """
    if not math.isfinite(c):
        raise ValueError(f"Cannot convert non-finite temperature: {c}")
    return c / FAHRENHEIT_SCALE + FAHRENHEIT_OFFSET


# ═══════════════════════════════════════════════════════════════════════════════
# BULK CONVERSION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def convert_polygon_revit_to_metres(
    polygon_revit: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Convert an entire polygon from Revit internal feet to metres.

    SAFETY: Room boundary polygons extracted from Revit are in decimal feet.
    ALL FireAI calculations (detector spacing, coverage, egress) expect metres.
    If this conversion is skipped or wrong, EVERY spatial calculation fails.

    Args:
        polygon_revit: List of (x, y) coordinate tuples in Revit decimal feet.

    Returns:
        List of (x, y) coordinate tuples in metres.

    Raises:
        ValueError: If any coordinate is non-finite.

    """
    result = []
    for i, (x, y) in enumerate(polygon_revit):
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(
                f"Non-finite coordinate at index {i}: ({x}, {y}). "
                "BIM model contains corrupt room boundary geometry."
            )
        result.append((x * FEET_TO_METRES, y * FEET_TO_METRES))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Conversion factors
    "FEET_TO_METRES", "METRES_TO_FEET",
    "INCHES_TO_MM", "MM_TO_INCHES",
    "FEET_TO_MM", "MM_TO_FEET",
    "SQFT_TO_SQM", "SQM_TO_SQFT",
    "CUBIC_FT_TO_CUBIC_M", "CUBIC_M_TO_CUBIC_FT",
    "GALLONS_US_TO_LITRES", "LITRES_TO_GALLONS_US",
    "PSI_TO_BAR", "BAR_TO_PSI",
    "PSI_TO_KPA", "KPA_TO_PSI",
    "GPM_TO_LPM", "LPM_TO_GPM",
    # Functions
    "revit_internal_to_metres",
    "metres_to_revit_internal",
    "revit_internal_to_mm",
    "mm_to_revit_internal",
    "inches_to_mm",
    "psi_to_bar",
    "bar_to_psi",
    "gpm_to_lpm",
    "sqft_to_sqm",
    "fahrenheit_to_celsius",
    "celsius_to_fahrenheit",
    "convert_polygon_revit_to_metres",
]
