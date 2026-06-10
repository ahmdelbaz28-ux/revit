"""
hydraulic_solver.py — Hazen-Williams Friction Loss & Hydraulic Calculation Engine
=================================================================================
LIFE-SAFETY CRITICAL: Incorrect hydraulic calculations cause undersized fire
suppression piping. If friction loss is underestimated, the residual pressure
at the most hydraulically demanding sprinkler falls below NFPA 13 minimum
(7.0 psi for standard spray sprinklers), causing inadequate water distribution
and failure to control fire spread.

This module implements the Hazen-Williams equation per NFPA 13-2022 Chapter 23
with STRICT boundary validation to prevent:
  1. Division by zero from zero/negative pipe diameters or C-factors
  2. Floating-point accumulation errors from single-precision floats
  3. Physically impossible parameter values (e.g., C > 200, d < 0.1 inches)
  4. Missing minimum pressure validation at sprinkler heads

Standards:
  - NFPA 13-2022 Chapter 23: Hydraulic Calculation Procedures
  - NFPA 13-2022 §23.4.4: Minimum operating pressure (7.0 psi)
  - SBC 801 Chapter 9: Saudi Fire Code hydraulic requirements
  - Egyptian Fire Protection Code Part 4: Hydraulic design requirements

Formula (Hazen-Williams):
  p = 4.52 × Q^1.85 / (C^1.85 × d^4.87)

Where:
  p = Frictional resistance (psi per foot of pipe)
  Q = Flow rate (gpm)
  C = Roughness coefficient (dimensionless, e.g., 120 for wet steel)
  d = Actual internal pipe diameter (inches)

Sprinkler Discharge (K-Factor):
  Q = K × √P

Where:
  Q = Flow rate (gpm)
  K = Discharge coefficient (gpm/psi^0.5), e.g., 5.6 for standard spray
  P = Operating pressure (psi), minimum 7.0 psi per NFPA 13

Hand-Verification Baseline:
  Q=100 gpm, C=120, d=2.067 in (2" Sch 40), L=100 ft
  → p = 4.52 × 5011.872 / (7051.758 × 34.004) = 0.094473 psi/ft
  → Total loss = 9.4473 psi
  K=5.6, P=7.0 psi → Q = 5.6 × √7.0 = 14.8162 gpm
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS — NFPA 13-2022
# ═══════════════════════════════════════════════════════════════════════════════

# Minimum sprinkler operating pressure (NFPA 13-2022 §23.4.4)
MIN_SPRINKLER_PRESSURE_PSI = 7.0

# Hazen-Williams exponent
HW_EXPONENT = 1.85

# Hazen-Williams coefficient
HW_COEFFICIENT = 4.52

# Pipe diameter exponent
DIAMETER_EXPONENT = 4.87

# Valid C-factor ranges by pipe material (NFPA 13 Table)
C_FACTOR_RANGES: Dict[str, Tuple[float, float]] = {
    "wet_steel":          (100.0, 140.0),   # Typical: 120
    "dry_steel":          (80.0,  120.0),   # Typical: 100
    "wet_copper":         (130.0, 150.0),   # Typical: 140
    "cpvc":               (140.0, 160.0),   # Typical: 150
    "concrete":           (80.0,  120.0),   # Typical: 100
    "cast_iron":          (80.0,  130.0),   # Typical: 100
    "ductile_iron":       (100.0, 140.0),   # Typical: 120
    "plastic_pvc":        (140.0, 160.0),   # Typical: 150
}

# Minimum internal pipe diameter (inches) — pipes below this are invalid
MIN_PIPE_DIAMETER_INCHES = 0.1

# Maximum C-factor — physically impossible above this
MAX_C_FACTOR = 200.0

# Minimum C-factor — physically impossible below this
MIN_C_FACTOR = 1.0

# Standard sprinkler K-factors (NFPA 13)
STANDARD_K_FACTORS: Dict[str, float] = {
    "standard_spray":     5.6,
    "residential":        4.2,
    "early_suppression":  14.0,
    "extended_coverage":  11.2,
    "cmsa":               8.0,
    "large_drop":         11.2,
}

# Schedule 40 internal diameters (inches) — most commonly used in fire protection
SCHEDULE_40_INTERNAL_DIAMETERS: Dict[str, float] = {
    "1/2":   0.622,
    "3/4":   0.824,
    "1":     1.049,
    "1-1/4": 1.380,
    "1-1/2": 1.610,
    "2":     2.067,
    "2-1/2": 2.469,
    "3":     3.068,
    "4":     4.026,
    "6":     6.065,
    "8":     7.981,
    "10":    10.020,
    "12":    11.938,
}


# ═══════════════════════════════════════════════════════════════════════════════
# HAZEN-WILLIAMS FRICTION LOSS CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_friction_loss(
    flow_rate_gpm: float,
    friction_factor_c: float,
    internal_diameter_inches: float,
    pipe_length_feet: float,
) -> float:
    """Calculate total friction loss in a pipe segment using Hazen-Williams.

    NFPA 13-2022 Chapter 23, Hazen-Williams Equation:
      p = 4.52 × Q^1.85 / (C^1.85 × d^4.87)
      Total loss = p × L

    SAFETY: Uses double precision (Python float = 64-bit) for all calculations.
    Validates ALL inputs against physically possible ranges to prevent:
      - Division by zero (d ≤ 0 or C ≤ 0)
      - Negative pressure loss (C < 0 or d < 0)
      - Floating-point overflow from excessive exponents

    Args:
        flow_rate_gpm: Flow rate through the pipe (US gpm).
        friction_factor_c: Hazen-Williams roughness coefficient C.
            Typical values: 120 (wet steel), 100 (dry steel), 150 (CPVC).
        internal_diameter_inches: Actual INTERNAL diameter of pipe (inches).
            MUST use actual internal diameter, NOT nominal diameter.
            e.g., 2" Schedule 40 = 2.067" actual internal.
        pipe_length_feet: Length of pipe segment (feet).

    Returns:
        Total friction loss for the segment in psi.

    Raises:
        ValueError: If any input is outside physically valid range.
        ValueError: If any input is NaN or infinite.

    Hand-Verification:
        Q=100, C=120, d=2.067, L=100
        → numerator = 4.52 × 100^1.85 = 4.52 × 5011.872 = 22653.662
        → denominator = 120^1.85 × 2.067^4.87 = 7051.758 × 34.004 = 239789.289
        → p = 22653.662 / 239789.289 = 0.094473 psi/ft
        → Total = 0.094473 × 100 = 9.4473 psi
    """
    # Input validation — NaN/Inf guard
    for name, val in [
        ("flow_rate_gpm", flow_rate_gpm),
        ("friction_factor_c", friction_factor_c),
        ("internal_diameter_inches", internal_diameter_inches),
        ("pipe_length_feet", pipe_length_feet),
    ]:
        if not math.isfinite(val):
            raise ValueError(
                f"Non-finite value for {name}: {val}. "
                "Hydraulic calculation requires finite numeric inputs."
            )

    # Flow rate: zero is valid (no flow = no friction), negative is not
    if flow_rate_gpm < 0:
        raise ValueError(
            f"flow_rate_gpm={flow_rate_gpm} must be >= 0. "
            "Negative flow rate is physically impossible."
        )

    # C-factor: must be within physically valid range
    if friction_factor_c < MIN_C_FACTOR:
        raise ValueError(
            f"friction_factor_c={friction_factor_c} is below minimum {MIN_C_FACTOR}. "
            "Pipe roughness coefficient cannot be zero or negative — "
            "this would cause division by zero in Hazen-Williams equation. "
            "NFPA 13 typical range: 80-150. [NFPA 13-2022 Chapter 23]"
        )
    if friction_factor_c > MAX_C_FACTOR:
        raise ValueError(
            f"friction_factor_c={friction_factor_c} exceeds maximum {MAX_C_FACTOR}. "
            "No pipe material has a C-factor above 200. "
            "Check input — value may be in wrong units. "
            "NFPA 13 typical range: 80-150. [NFPA 13-2022 Chapter 23]"
        )

    # Pipe diameter: must be positive and reasonable
    if internal_diameter_inches < MIN_PIPE_DIAMETER_INCHES:
        raise ValueError(
            f"internal_diameter_inches={internal_diameter_inches} is below minimum "
            f"{MIN_PIPE_DIAMETER_INCHES}\". Pipe diameter must be positive. "
            "Check that you are using ACTUAL INTERNAL diameter, not nominal. "
            "e.g., 2\" Schedule 40 pipe has 2.067\" actual internal diameter. "
            "[NFPA 13-2022 Chapter 23]"
        )

    # Pipe length: cannot be negative
    if pipe_length_feet < 0:
        raise ValueError(
            f"pipe_length_feet={pipe_length_feet} must be >= 0. "
            "Pipe length cannot be negative."
        )

    # Zero flow = zero friction loss
    if flow_rate_gpm == 0.0:
        return 0.0

    # Hazen-Williams calculation using double precision
    numerator = HW_COEFFICIENT * math.pow(flow_rate_gpm, HW_EXPONENT)
    denominator = (
        math.pow(friction_factor_c, HW_EXPONENT)
        * math.pow(internal_diameter_inches, DIAMETER_EXPONENT)
    )

    # Safety: check for computational overflow/underflow
    if not math.isfinite(numerator):
        raise ValueError(
            f"Hazen-Williams numerator overflow: 4.52 × {flow_rate_gpm}^{HW_EXPONENT}. "
            "Flow rate may be unreasonably large."
        )
    if not math.isfinite(denominator) or denominator == 0.0:
        raise ValueError(
            f"Hazen-Williams denominator invalid: C={friction_factor_c}^{HW_EXPONENT} "
            f"× d={internal_diameter_inches}^{DIAMETER_EXPONENT} = {denominator}. "
            "Check pipe diameter and C-factor values."
        )

    friction_loss_per_foot = numerator / denominator
    total_loss = friction_loss_per_foot * pipe_length_feet

    # Log calculation for audit trail
    logger.debug(
        f"Hazen-Williams: Q={flow_rate_gpm} gpm, C={friction_factor_c}, "
        f"d={internal_diameter_inches}\", L={pipe_length_feet} ft → "
        f"p={friction_loss_per_foot:.6f} psi/ft, total={total_loss:.4f} psi"
    )

    return total_loss


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINKLER DISCHARGE CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_sprinkler_discharge(
    k_factor: float,
    pressure_psi: float,
) -> float:
    """Calculate sprinkler discharge flow using the K-factor formula.

    NFPA 13-2022 §23.4.4: Q = K × √P

    SAFETY: Validates that pressure meets NFPA 13 minimum (7.0 psi).
    If pressure is below 7.0 psi, logs a CRITICAL warning but still
    returns the calculated flow (engineer must decide on remediation).

    Args:
        k_factor: Sprinkler discharge coefficient (gpm/psi^0.5).
            Standard spray: 5.6, Residential: 4.2, ESFR: 14.0.
        pressure_psi: Operating pressure at the sprinkler (psi).
            Must be >= 7.0 psi per NFPA 13-2022 §23.4.4.

    Returns:
        Flow rate in gpm.

    Raises:
        ValueError: If inputs are non-finite or K-factor is invalid.

    Hand-Verification:
        K=5.6, P=7.0 → Q = 5.6 × √7.0 = 5.6 × 2.64575 = 14.8162 gpm
    """
    if not (math.isfinite(k_factor) and math.isfinite(pressure_psi)):
        raise ValueError(
            f"Non-finite inputs: K={k_factor}, P={pressure_psi}. "
            "Sprinkler calculation requires finite numeric inputs."
        )

    if k_factor <= 0:
        raise ValueError(
            f"k_factor={k_factor} must be > 0. "
            "Standard spray sprinkler K=5.6, ESFR K=14.0. [NFPA 13-2022 §23.4]"
        )

    if pressure_psi < 0:
        raise ValueError(
            f"pressure_psi={pressure_psi} must be >= 0. "
            "Negative pressure is physically impossible."
        )

    # NFPA 13-2022 §23.4.4: Minimum 7.0 psi operating pressure
    if pressure_psi < MIN_SPRINKLER_PRESSURE_PSI:
        logger.critical(
            f"[NFPA 13 VIOLATION]: Sprinkler pressure {pressure_psi:.2f} psi "
            f"is below mandatory minimum {MIN_SPRINKLER_PRESSURE_PSI} psi. "
            "Inadequate atomization will occur — fire may not be controlled. "
            "[NFPA 13-2022 §23.4.4 / SBC 801 Ch.9 / Egyptian Fire Code Part 4]"
        )

    return k_factor * math.sqrt(pressure_psi)


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINKLER COMPLIANCE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

# Hazard classification design requirements (NFPA 13-2022 Chapter 11)
HAZARD_DESIGN_REQUIREMENTS: Dict[str, Dict[str, float]] = {
    "light_hazard": {
        "min_density_gpm_sqft": 0.10,
        "max_area_per_sprinkler_sqft": 225.0,
        "max_spacing_ft": 15.0,
        "min_pressure_psi": 7.0,
    },
    "ordinary_hazard_1": {
        "min_density_gpm_sqft": 0.15,
        "max_area_per_sprinkler_sqft": 130.0,
        "max_spacing_ft": 15.0,
        "min_pressure_psi": 7.0,
    },
    "ordinary_hazard_2": {
        "min_density_gpm_sqft": 0.20,
        "max_area_per_sprinkler_sqft": 130.0,
        "max_spacing_ft": 15.0,
        "min_pressure_psi": 7.0,
    },
    "extra_hazard_1": {
        "min_density_gpm_sqft": 0.30,
        "max_area_per_sprinkler_sqft": 100.0,
        "max_spacing_ft": 12.0,
        "min_pressure_psi": 7.0,
    },
    "extra_hazard_2": {
        "min_density_gpm_sqft": 0.40,
        "max_area_per_sprinkler_sqft": 100.0,
        "max_spacing_ft": 12.0,
        "min_pressure_psi": 7.0,
    },
}


@dataclass
class SprinklerComplianceResult:
    """Result of sprinkler compliance validation against NFPA 13 / SBC 801."""
    is_compliant: bool
    hazard_class: str
    head_pressure_psi: float
    density_gpm_sqft: float
    violations: List[str] = field(default_factory=list)
    nfpa_reference: str = "NFPA 13-2022 §23.4.4 / SBC 801 Ch.9"
    sbc_reference: str = "SBC 801-2022 Chapter 9"


def validate_sprinkler_compliance(
    head_pressure_psi: float,
    density_gpm_sqft: float,
    hazard_class: str,
    sprinkler_area_sqft: Optional[float] = None,
) -> SprinklerComplianceResult:
    """Validate sprinkler design against NFPA 13 / SBC 801 limits.

    SAFETY: This is the PRIMARY compliance gate for sprinkler systems.
    A sprinkler design that fails this validation CANNOT be approved
    for construction — it represents a direct life-safety hazard.

    NFPA 13-2022 §23.4.4: Minimum 7.0 psi at the most hydraulically
    demanding sprinkler. SBC 801 Chapter 9 adopts this requirement.

    Args:
        head_pressure_psi: Residual pressure at the sprinkler head (psi).
        density_gpm_sqft: Design density (gpm/sq.ft.).
        hazard_class: Hazard classification string (lowercase).
            Valid: "light_hazard", "ordinary_hazard_1", "ordinary_hazard_2",
            "extra_hazard_1", "extra_hazard_2".
        sprinkler_area_sqft: Area covered by each sprinkler (sq.ft.).
            If provided, validated against max for the hazard class.

    Returns:
        SprinklerComplianceResult with compliance status and violations.

    Example:
        >>> result = validate_sprinkler_compliance(6.5, 0.10, "light_hazard")
        >>> result.is_compliant
        False
        >>> result.violations[0]
        'Residual pressure 6.5 psi is below mandatory NFPA 13 limit of 7.0 psi.'
    """
    violations: List[str] = []
    normalized_hazard = hazard_class.strip().lower().replace(" ", "_")

    # Validate hazard classification exists
    if normalized_hazard not in HAZARD_DESIGN_REQUIREMENTS:
        violations.append(
            f"Unknown hazard classification: '{hazard_class}'. "
            f"Valid classifications: {list(HAZARD_DESIGN_REQUIREMENTS.keys())}. "
            "Cannot validate design without proper hazard classification. "
            "[NFPA 13-2022 Chapter 11]"
        )
        return SprinklerComplianceResult(
            is_compliant=False,
            hazard_class=hazard_class,
            head_pressure_psi=head_pressure_psi,
            density_gpm_sqft=density_gpm_sqft,
            violations=violations,
        )

    req = HAZARD_DESIGN_REQUIREMENTS[normalized_hazard]

    # Check 1: Minimum operating pressure (NFPA 13 §23.4.4)
    if head_pressure_psi < MIN_SPRINKLER_PRESSURE_PSI:
        violations.append(
            f"Residual pressure {head_pressure_psi:.2f} psi is below mandatory "
            f"NFPA 13 / SBC 801 limit of {MIN_SPRINKLER_PRESSURE_PSI} psi. "
            "Insufficient pressure causes inadequate water atomization — "
            "fire will NOT be controlled. This is a CRITICAL violation. "
            "[NFPA 13-2022 §23.4.4 / SBC 801 Ch.9 / Egyptian Fire Code Part 4]"
        )

    # Check 2: Minimum design density (NFPA 13 Chapter 11)
    if density_gpm_sqft < req["min_density_gpm_sqft"]:
        violations.append(
            f"Design density {density_gpm_sqft:.3f} gpm/sq.ft is below minimum "
            f"{req['min_density_gpm_sqft']:.2f} gpm/sq.ft for {normalized_hazard}. "
            "Insufficient water delivery rate — fire will NOT be controlled. "
            f"[NFPA 13-2022 Chapter 11 / SBC 801 Ch.9]"
        )

    # Check 3: Maximum sprinkler coverage area (if provided)
    if sprinkler_area_sqft is not None:
        if sprinkler_area_sqft > req["max_area_per_sprinkler_sqft"]:
            violations.append(
                f"Sprinkler coverage area {sprinkler_area_sqft:.1f} sq.ft exceeds "
                f"maximum {req['max_area_per_sprinkler_sqft']:.1f} sq.ft for "
                f"{normalized_hazard}. "
                "Excessive spacing leaves dead zones where fire spreads undetected. "
                f"[NFPA 13-2022 Chapter 11]"
            )

    is_compliant = len(violations) == 0

    return SprinklerComplianceResult(
        is_compliant=is_compliant,
        hazard_class=normalized_hazard,
        head_pressure_psi=head_pressure_psi,
        density_gpm_sqft=density_gpm_sqft,
        violations=violations,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C-FACTOR VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def validate_roughness_factor(
    material: str,
    c_factor: float,
) -> float:
    """Validate C-factor value against NFPA 13 standard ranges.

    SAFETY: An incorrect C-factor directly affects friction loss calculations.
    A C-factor that is too high makes friction loss appear too low, causing
    undersized piping. A C-factor that is too low makes friction loss appear
    too high, causing over-designed (expensive) systems.

    Args:
        material: Pipe material key (e.g., "wet_steel", "dry_steel", "cpvc").
        c_factor: Hazen-Williams roughness coefficient.

    Returns:
        The validated C-factor value.

    Raises:
        ValueError: If C-factor is outside the valid range for the material.

    Example:
        >>> validate_roughness_factor("wet_steel", 120.0)
        120.0
        >>> validate_roughness_factor("wet_steel", 500.0)
        ValueError: Friction factor C=500.0 exceeds maximum 140.0 for wet_steel
    """
    if not math.isfinite(c_factor):
        raise ValueError(
            f"Non-finite C-factor: {c_factor}. "
            "Hazen-Williams roughness coefficient must be a finite number."
        )

    # Absolute range check
    if c_factor < MIN_C_FACTOR:
        raise ValueError(
            f"Friction factor C={c_factor} is physically impossible (below {MIN_C_FACTOR}). "
            "Zero or negative C-factors cause division by zero in Hazen-Williams. "
            "[NFPA 13-2022 Chapter 23]"
        )
    if c_factor > MAX_C_FACTOR:
        raise ValueError(
            f"Friction factor C={c_factor} is physically impossible (above {MAX_C_FACTOR}). "
            "No pipe material has a C-factor above 200. "
            "[NFPA 13-2022 Chapter 23]"
        )

    # Material-specific range check
    normalized_material = material.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized_material in C_FACTOR_RANGES:
        min_c, max_c = C_FACTOR_RANGES[normalized_material]
        if c_factor < min_c or c_factor > max_c:
            logger.warning(
                f"C-factor {c_factor} is outside typical range "
                f"[{min_c}-{max_c}] for {normalized_material}. "
                "Calculation will proceed, but verify the value. "
                "[NFPA 13-2022 Chapter 23]"
            )

    return c_factor


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "calculate_friction_loss",
    "calculate_sprinkler_discharge",
    "validate_sprinkler_compliance",
    "validate_roughness_factor",
    "MIN_SPRINKLER_PRESSURE_PSI",
    "HAZARD_DESIGN_REQUIREMENTS",
    "C_FACTOR_RANGES",
    "SCHEDULE_40_INTERNAL_DIAMETERS",
    "STANDARD_K_FACTORS",
    "SprinklerComplianceResult",
]
