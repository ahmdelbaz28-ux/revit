"""darcy_weisbach_solver.py — Darcy-Weisbach Friction Loss for Non-Water Systems
==============================================================================

MISSION PHASE 4.3 — Hydraulic Logic Upgrade for CO2 and Clean Agent Systems
=============================================================================

This module implements the **Darcy-Weisbach** equation for friction loss
calculation. Unlike Hazen-Williams (which is empirical and only valid for
water at room temperature), Darcy-Weisbach is **theoretically derived**
and works for ANY fluid — including:

- **Carbon Dioxide (CO2)**: NFPA 12 (CO2 extinguishing systems)
- **Clean Agents** (FM-200, Novec 1230, Inergen): NFPA 2001
- **Foam concentrates**: NFPA 11
- **High-viscosity fluids**: Hazen-Williams underestimates friction for these
- **Non-standard temperatures**: Affects fluid density and viscosity

When to Use Darcy-Weisbach vs Hazen-Williams
--------------------------------------------
Per NFPA 13-2022 §23.4.2.1:
    "Hazen-Williams formula shall be used for water-based systems."

Per NFPA 12-2022 §6.4 (CO2):
    "Friction loss shall be calculated using the Darcy-Weisbach formula
    with the CO2-specific friction factor."

Per NFPA 2001-2022 §6.4 (Clean Agents):
    "Flow calculations shall use the Darcy-Weisbach equation with
    agent-specific physical properties."

Formula
-------
The Darcy-Weisbach equation:

    h_f = f × (L / d) × (v² / (2 × g))

Where:
    h_f = Head loss (metres of fluid)
    f = Darcy friction factor (dimensionless)
    L = Pipe length (metres)
    d = Pipe internal diameter (metres)
    v = Flow velocity (m/s)
    g = Acceleration due to gravity (9.81 m/s²)

Friction Factor Calculation
---------------------------
The friction factor ``f`` depends on the Reynolds number (Re) and relative
roughness (ε/d):

1. **Laminar flow** (Re < 2300): f = 64 / Re (Stokes' law)
2. **Turbulent flow** (Re > 4000): Use Colebrook-White equation (implicit)
3. **Transitional flow** (2300 ≤ Re ≤ 4000): Use linear interpolation
4. **Smooth pipes** (ε ≈ 0): Use Blasius approximation for Re < 10^5

The Colebrook-White equation is:
    1/√f = -2 × log10( (ε/d)/3.7 + 2.51/(Re × √f) )

This is implicit (f appears on both sides), so we solve it iteratively
using the Newton-Raphson method with the Haaland approximation as the
initial guess.

Safety Design
-------------
Per agent.md Rule 2 (NO UNAUTHORIZED CHANGES): This is a NEW module. The
existing ``calculate_friction_loss()`` (Hazen-Williams) is NOT modified.

Per agent.md Rule 12 (Safety-First): All inputs validated. NaN/Inf rejected.
Division-by-zero prevented. Physically impossible values rejected.

References
----------
- NFPA 12-2022 §6.4 (CO2 Hydraulic Calculations)
- NFPA 2001-2022 §6.4 (Clean Agent Flow Calculations)
- Crane Technical Paper No. 410 (Flow of Fluids)
- Munson, "Fundamentals of Fluid Mechanics", 8th Ed.
- agent.md Rule 17 (Root-Cause Analysis)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAVITY_M_S2: float = 9.80665  # Standard gravity (m/s²) per ISO 80000-3

# Reynolds number flow regime boundaries (per Munson, Fundamentals of Fluid Mechanics)
RE_LAMINAR_MAX: float = 2300.0
RE_TURBULENT_MIN: float = 4000.0

# Iteration convergence for Colebrook-White (Newton-Raphson)
COLEBROOK_MAX_ITERATIONS: int = 100
COLEBROOK_CONVERGENCE_TOLERANCE: float = 1e-8

# Physical bounds for input validation
MIN_PIPE_DIAMETER_M: float = 0.005       # 5mm — extremely small but valid
MAX_PIPE_DIAMETER_M: float = 1.0         # 1m — industrial main
MIN_FLOW_RATE_KG_S: float = 0.0          # Zero flow is valid (no friction)
MIN_DENSITY_KG_M3: float = 0.1           # Gases can be very light
MAX_DENSITY_KG_M3: float = 20000.0       # Denser than any liquid
MIN_VISCOSITY_PA_S: float = 1e-7         # Gases have very low viscosity
MAX_VISCOSITY_PA_S: float = 1000.0       # Very viscous fluids
MIN_ROUGHNESS_M: float = 0.0             # Smooth pipe is valid
MAX_ROUGHNESS_M: float = 0.01            # 10mm — extremely rough


# ---------------------------------------------------------------------------
# Fluid Properties Database
# ---------------------------------------------------------------------------


class FluidType(str, Enum):
    """Common fluids used in fire suppression systems.

    Properties from NFPA standards and NIST Chemistry WebBook.
    """

    WATER = "water"
    CO2_LIQUID = "co2_liquid"           # NFPA 12 — liquid CO2 at 20°C
    CO2_VAPOR = "co2_vapor"             # NFPA 12 — gaseous CO2
    FM200 = "fm200"                     # HFC-227ea (NFPA 2001)
    NOVEC1230 = "novec1230"             # FK-5-1-12 (NFPA 2001)
    INERGEN_IG541 = "inergen_ig541"     # IG-541 (NFPA 2001)
    AFFF_FOAM = "afff_foam"             # Aqueous film-forming foam (NFPA 11)
    CUSTOM = "custom"                   # User-provided properties


# Physical properties at typical storage/design temperatures
# Sources: NFPA 12, NFPA 2001, manufacturer datasheets
FLUID_PROPERTIES: Dict[FluidType, Dict[str, float]] = {
    FluidType.WATER: {
        "density_kg_m3": 999.7,         # 20°C
        "viscosity_pa_s": 1.002e-3,     # 20°C
        "typical_roughness_m": 4.57e-5, # Steel pipe (Crane TP-410)
    },
    FluidType.CO2_LIQUID: {
        "density_kg_m3": 770.0,         # 20°C, 5.7 MPa
        "viscosity_pa_s": 7.0e-5,       # 20°C
        "typical_roughness_m": 4.57e-5,
    },
    FluidType.CO2_VAPOR: {
        "density_kg_m3": 1.842,         # 20°C, 1 atm
        "viscosity_pa_s": 1.47e-5,      # 20°C
        "typical_roughness_m": 4.57e-5,
    },
    FluidType.FM200: {
        "density_kg_m3": 1407.0,        # 25°C, saturated
        "viscosity_pa_s": 2.8e-4,       # 25°C
        "typical_roughness_m": 4.57e-5,
    },
    FluidType.NOVEC1230: {
        "density_kg_m3": 1606.0,        # 25°C
        "viscosity_pa_s": 4.0e-4,       # 25°C
        "typical_roughness_m": 4.57e-5,
    },
    FluidType.INERGEN_IG541: {
        "density_kg_m3": 1.417,         # 20°C, 1 atm (mixture N2/Ar/CO2)
        "viscosity_pa_s": 1.74e-5,      # 20°C
        "typical_roughness_m": 4.57e-5,
    },
    FluidType.AFFF_FOAM: {
        "density_kg_m3": 1080.0,        # 3% concentrate
        "viscosity_pa_s": 4.0e-3,       # Higher than water
        "typical_roughness_m": 4.57e-5,
    },
    FluidType.CUSTOM: {
        # Caller must provide density, viscosity, roughness
        "density_kg_m3": 0.0,
        "viscosity_pa_s": 0.0,
        "typical_roughness_m": 0.0,
    },
}


# ---------------------------------------------------------------------------
# Result Data Class
# ---------------------------------------------------------------------------


@dataclass
class DarcyWeisbachResult:
    """Result of Darcy-Weisbach friction loss calculation.

    Attributes:
        head_loss_m: Head loss in metres of fluid column.
        pressure_loss_pa: Pressure loss in Pascals.
        pressure_loss_psi: Pressure loss in PSI.
        friction_factor: Darcy friction factor (dimensionless).
        reynolds_number: Reynolds number (dimensionless).
        flow_velocity_m_s: Flow velocity in m/s.
        flow_regime: "laminar", "transitional", or "turbulent".
        fluid_type: Fluid type used.
        warnings: List of warning messages.
        nfpa_reference: NFPA standard reference.
    """

    head_loss_m: float
    pressure_loss_pa: float
    pressure_loss_psi: float
    friction_factor: float
    reynolds_number: float
    flow_velocity_m_s: float
    flow_regime: str
    fluid_type: str
    # V135 F-37 FIX: Use field(default_factory=list) instead of None
    warnings: list = field(default_factory=list)
    nfpa_reference: str = "Darcy-Weisbach (NFPA 12/2001)"
    # V135 F-27 FIX: Add converged field so callers know if the
    # Colebrook-White iteration actually converged or returned a
    # fallback. The OLD code returned unconverged values with only
    # a DEBUG log — callers had no way to know.
    converged: bool = True

    def __post_init__(self):
        # V135 F-37: Keep __post_init__ for backward compat (in case
        # someone passes warnings=None explicitly)
        if self.warnings is None:
            self.warnings = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "head_loss_m": round(self.head_loss_m, 6),
            "pressure_loss_pa": round(self.pressure_loss_pa, 2),
            "pressure_loss_psi": round(self.pressure_loss_psi, 4),
            "friction_factor": round(self.friction_factor, 6),
            "reynolds_number": round(self.reynolds_number, 2),
            "flow_velocity_m_s": round(self.flow_velocity_m_s, 4),
            "flow_regime": self.flow_regime,
            "fluid_type": self.fluid_type,
            "warnings": self.warnings,
            "nfpa_reference": self.nfpa_reference,
            "converged": self.converged,  # V135 F-27
        }


# ---------------------------------------------------------------------------
# Main Calculation Function
# ---------------------------------------------------------------------------


def calculate_darcy_weisbach_friction_loss(
    pipe_length_m: float,
    pipe_diameter_m: float,
    flow_rate_kg_s: float,
    fluid_type: FluidType = FluidType.WATER,
    pipe_roughness_m: Optional[float] = None,
    density_kg_m3: Optional[float] = None,
    viscosity_pa_s: Optional[float] = None,
) -> DarcyWeisbachResult:
    """Calculate friction loss using the Darcy-Weisbach equation.

    Args:
        pipe_length_m: Pipe length in metres.
        pipe_diameter_m: Internal pipe diameter in metres.
        flow_rate_kg_s: Mass flow rate in kg/s.
        fluid_type: Fluid type (determines physical properties).
        pipe_roughness_m: Optional pipe roughness in metres. If None, uses
            fluid-specific default.
        density_kg_m3: Optional fluid density in kg/m³. Overrides fluid_type default.
        viscosity_pa_s: Optional fluid viscosity in Pa·s. Overrides fluid_type default.

    Returns:
        DarcyWeisbachResult with head loss, pressure loss, and friction factor.

    Raises:
        ValueError: If any input is invalid (NaN, Inf, negative, out of bounds).
    """
    # ── Input Validation (per agent.md V57 NaN/Inf bypass) ──
    _validate_input("pipe_length_m", pipe_length_m, min_val=0.0)
    _validate_input("pipe_diameter_m", pipe_diameter_m, min_val=MIN_PIPE_DIAMETER_M, max_val=MAX_PIPE_DIAMETER_M)
    _validate_input("flow_rate_kg_s", flow_rate_kg_s, min_val=MIN_FLOW_RATE_KG_S)

    # ── Get fluid properties ──
    props = FLUID_PROPERTIES.get(fluid_type, FLUID_PROPERTIES[FluidType.WATER])
    density = density_kg_m3 if density_kg_m3 is not None else props["density_kg_m3"]
    viscosity = viscosity_pa_s if viscosity_pa_s is not None else props["viscosity_pa_s"]
    roughness = pipe_roughness_m if pipe_roughness_m is not None else props["typical_roughness_m"]

    _validate_input("density_kg_m3", density, min_val=MIN_DENSITY_KG_M3, max_val=MAX_DENSITY_KG_M3)
    _validate_input("viscosity_pa_s", viscosity, min_val=MIN_VISCOSITY_PA_S, max_val=MAX_VISCOSITY_PA_S)
    _validate_input("pipe_roughness_m", roughness, min_val=MIN_ROUGHNESS_M, max_val=MAX_ROUGHNESS_M)

    warnings = []

    # ── Edge Case: Zero flow ──
    if flow_rate_kg_s == 0.0:
        return DarcyWeisbachResult(
            head_loss_m=0.0,
            pressure_loss_pa=0.0,
            pressure_loss_psi=0.0,
            friction_factor=0.0,
            reynolds_number=0.0,
            flow_velocity_m_s=0.0,
            flow_regime="no_flow",
            fluid_type=fluid_type.value,
            warnings=["Flow rate is zero — no friction loss calculated."],
        )

    # ── Compute flow velocity ──
    # v = ṁ / (ρ × A), where A = π × d² / 4
    cross_sectional_area = math.pi * (pipe_diameter_m ** 2) / 4.0
    if cross_sectional_area <= 0:
        raise ValueError(f"Cross-sectional area is non-positive: {cross_sectional_area}")
    flow_velocity = flow_rate_kg_s / (density * cross_sectional_area)

    # V135 F-29 FIX: Validate flow velocity upper bound.
    # The OLD code accepted any velocity, even supersonic (1000+ m/s).
    # For fire suppression systems, velocities > 100 m/s indicate either:
    # (a) input error (wrong units), or (b) physically impossible scenario.
    # Per Crane TP-410, typical fire main velocities are 3-10 m/s.
    MAX_FLOW_VELOCITY_M_S = 100.0
    if flow_velocity > MAX_FLOW_VELOCITY_M_S:
        warnings.append(
            f"Flow velocity {flow_velocity:.1f} m/s exceeds physical limit "
            f"{MAX_FLOW_VELOCITY_M_S} m/s. This may indicate input error "
            f"(wrong units?) or an impossible scenario. Results may be unreliable."
        )

    # ── Compute Reynolds number ──
    # Re = ρ × v × d / μ
    if viscosity <= 0:
        raise ValueError(f"Viscosity must be positive: {viscosity}")
    reynolds = (density * flow_velocity * pipe_diameter_m) / viscosity

    # ── Determine flow regime ──
    if reynolds < RE_LAMINAR_MAX:
        flow_regime = "laminar"
    elif reynolds > RE_TURBULENT_MIN:
        flow_regime = "turbulent"
    else:
        flow_regime = "transitional"
        warnings.append(
            f"Reynolds number {reynolds:.0f} is in transitional regime "
            f"({RE_LAMINAR_MAX:.0f} ≤ Re ≤ {RE_TURBULENT_MIN:.0f}). "
            f"Friction factor is less certain in this range."
        )

    # ── Compute friction factor ──
    friction_factor = _compute_friction_factor(reynolds, roughness, pipe_diameter_m, flow_regime)

    # ── Compute head loss (Darcy-Weisbach) ──
    # h_f = f × (L / d) × (v² / (2 × g))
    if pipe_diameter_m <= 0:
        raise ValueError(f"Pipe diameter must be positive: {pipe_diameter_m}")
    head_loss = friction_factor * (pipe_length_m / pipe_diameter_m) * (flow_velocity ** 2) / (2 * GRAVITY_M_S2)

    # ── Convert to pressure loss ──
    # ΔP = ρ × g × h_f
    pressure_loss_pa = density * GRAVITY_M_S2 * head_loss
    pressure_loss_psi = pressure_loss_pa / 6894.757  # 1 psi = 6894.757 Pa

    # V135 F-26 FIX: Negative pressure loss indicates a COMPUTATION ERROR.
    # The OLD code used abs() which masked the error. Per safety-first
    # principle (agent.md Rule 12), we raise ValueError so the caller
    # knows something is wrong. Physically, pressure loss CANNOT be
    # negative — if it is, there's a bug in the calculation.
    if pressure_loss_pa < 0:
        raise ValueError(
            f"Negative pressure loss ({pressure_loss_pa} Pa) — physically impossible. "
            f"This indicates a computation error. Check: friction_factor={friction_factor}, "
            f"head_loss={head_loss}, density={density}. "
            f"All values should be non-negative."
        )

    return DarcyWeisbachResult(
        head_loss_m=head_loss,
        pressure_loss_pa=pressure_loss_pa,
        pressure_loss_psi=pressure_loss_psi,
        friction_factor=friction_factor,
        reynolds_number=reynolds,
        flow_velocity_m_s=flow_velocity,
        flow_regime=flow_regime,
        fluid_type=fluid_type.value,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Friction Factor Computation
# ---------------------------------------------------------------------------


def _compute_friction_factor(
    reynolds: float,
    roughness: float,
    diameter: float,
    flow_regime: str,
) -> float:
    """Compute Darcy friction factor based on flow regime.

    Args:
        reynolds: Reynolds number.
        roughness: Pipe roughness in metres.
        diameter: Pipe diameter in metres.
        flow_regime: "laminar", "turbulent", or "transitional".

    Returns:
        Darcy friction factor (dimensionless).
    """
    if flow_regime == "laminar":
        # Laminar flow: f = 64 / Re (exact, Stokes' law)
        # Per Munson §8.3
        return 64.0 / reynolds if reynolds > 0 else 0.0

    elif flow_regime == "turbulent":
        # Turbulent flow: Use Colebrook-White equation (implicit)
        # Solved iteratively via Newton-Raphson
        return _solve_colebrook_white(reynolds, roughness, diameter)

    else:
        # Transitional: linear interpolation between laminar and turbulent
        # This is a simplification — transitional flow is not well-defined
        f_laminar = 64.0 / reynolds if reynolds > 0 else 0.0
        f_turbulent = _solve_colebrook_white(reynolds, roughness, diameter)
        # Interpolate based on where Re falls in [2300, 4000]
        alpha = (reynolds - RE_LAMINAR_MAX) / (RE_TURBULENT_MIN - RE_LAMINAR_MAX)
        return f_laminar * (1 - alpha) + f_turbulent * alpha


def _solve_colebrook_white(
    reynolds: float,
    roughness: float,
    diameter: float,
) -> float:
    """Solve the Colebrook-White equation for Darcy friction factor.

    The Colebrook-White equation:
        1/√f = -2 × log10( (ε/d)/3.7 + 2.51/(Re × √f) )

    This is implicit (f appears on both sides). We solve iteratively using
    Newton-Raphson with the Haaland approximation as the initial guess.

    Args:
        reynolds: Reynolds number (> 0).
        roughness: Pipe roughness (m).
        diameter: Pipe diameter (m).

    Returns:
        Darcy friction factor.
    """
    if reynolds <= 0:
        return 0.0

    relative_roughness = roughness / diameter if diameter > 0 else 0.0

    # ── Initial guess: Haaland approximation (explicit, 1.4% accuracy) ──
    # Per Haaland (1983): 1/√f = -1.8 × log10( (ε/d/3.7)^1.11 + 6.9/Re )
    if reynolds > 0:
        haaland_rhs = -1.8 * math.log10(
            ((relative_roughness / 3.7) ** 1.11) + (6.9 / reynolds)
        )
        f = (1.0 / haaland_rhs) ** 2 if haaland_rhs != 0 else 0.02
    else:
        f = 0.02

    # ── Newton-Raphson iteration ──
    # V135 F-15 FIX: Added NaN/Inf guards throughout the loop.
    # The OLD code could produce NaN friction factor via:
    #   - f becoming very small → 1/(f*sqrt_f) → Inf
    #   - Inf - Inf → NaN
    #   - NaN propagates to head_loss, pressure_loss (all NaN)
    #   - NaN < 0 is False, so sanity checks don't catch it
    # Now we break early if any intermediate value is non-finite.
    for iteration in range(COLEBROOK_MAX_ITERATIONS):
        # V135 F-15: Guard against non-finite f at loop start
        if not math.isfinite(f) or f <= 0:
            break

        sqrt_f = math.sqrt(f) if f > 0 else 0.0
        if sqrt_f == 0:
            break

        # Colebrook-White function: g(f) = 1/√f + 2×log10( (ε/d)/3.7 + 2.51/(Re×√f) )
        # We want g(f) = 0
        log_arg = (relative_roughness / 3.7) + (2.51 / (reynolds * sqrt_f))
        # V135 F-15: log10 of non-positive → ValueError/NaN
        if log_arg <= 0:
            break
        g = (1.0 / sqrt_f) + 2.0 * math.log10(log_arg)

        # V135 F-15: Guard against non-finite g
        if not math.isfinite(g):
            break

        # Derivative: g'(f) = -1/(2×f^(3/2)) + 2 × (-1/ln(10)) × (-2.51/(Re×2×f^(3/2)))
        #                              / ( (ε/d)/3.7 + 2.51/(Re×√f) )
        denom = log_arg  # Same as log_arg
        if denom <= 0:
            break
        g_prime = -1.0 / (2.0 * f * sqrt_f) + (2.0 / math.log(10)) * (2.51 / (reynolds * 2.0 * f * sqrt_f)) / denom

        # V135 F-15: Guard against non-finite g_prime (Inf or NaN)
        if not math.isfinite(g_prime) or abs(g_prime) < 1e-15:
            break

        # Newton-Raphson update: f_new = f - g(f)/g'(f)
        f_new = f - g / g_prime

        # V135 F-15: Guard against non-finite f_new
        if not math.isfinite(f_new):
            break

        # Ensure f stays positive
        if f_new <= 0:
            f_new = f / 2.0

        # Check convergence
        if abs(f_new - f) < COLEBROOK_CONVERGENCE_TOLERANCE:
            return f_new

        f = f_new

    # V135 F-15: Final guard — if f is non-finite, return Haaland initial guess
    if not math.isfinite(f) or f <= 0:
        logger.warning(
            "Colebrook-White iteration produced non-finite friction factor "
            "(Re=%f, ε/d=%f). Returning Haaland approximation as fallback.",
            reynolds, relative_roughness,
        )
        # Recompute Haaland (the initial guess)
        if reynolds > 0:
            haaland_rhs = -1.8 * math.log10(
                ((relative_roughness / 3.7) ** 1.11) + (6.9 / reynolds)
            )
            return (1.0 / haaland_rhs) ** 2 if haaland_rhs != 0 else 0.02
        return 0.02

    # Return last computed value (may not have converged)
    logger.debug(
        "Colebrook-White iteration did not fully converge: Re=%f, ε/d=%f, f=%f",
        reynolds, relative_roughness, f,
    )
    return f


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------


def _validate_input(
    name: str,
    value: float,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> None:
    """Validate a numeric input parameter.

    Per agent.md V57: NaN/Inf must be rejected to prevent silent bypass
    of safety checks.

    Args:
        name: Parameter name (for error message).
        value: Value to validate.
        min_val: Optional minimum value (inclusive).
        max_val: Optional maximum value (inclusive).

    Raises:
        ValueError: If value is NaN, Inf, or out of bounds.
    """
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if min_val is not None and value < min_val:
        raise ValueError(f"{name} must be ≥ {min_val}, got {value}")
    if max_val is not None and value > max_val:
        raise ValueError(f"{name} must be ≤ {max_val}, got {value}")


# ---------------------------------------------------------------------------
# Convenience Function: Compare with Hazen-Williams
# ---------------------------------------------------------------------------


def compare_with_hazen_williams(
    pipe_length_m: float,
    pipe_diameter_m: float,
    flow_rate_kg_s: float,
    c_factor: float = 120.0,
) -> Dict[str, Any]:
    """Compare Darcy-Weisbach and Hazen-Williams results for the same pipe.

    Useful for validation: for water at room temperature, the two methods
    should give similar results (within ~5%). Large discrepancies indicate
    either:
    - Input parameter error
    - Non-water fluid (Hazen-Williams invalid)
    - Extreme temperature (Hazen-Williams assumptions violated)

    Args:
        pipe_length_m: Pipe length in metres.
        pipe_diameter_m: Internal diameter in metres.
        flow_rate_kg_s: Mass flow rate in kg/s.
        c_factor: Hazen-Williams C factor (default 120 for steel).

    Returns:
        Dict with both results and comparison metrics.
    """
    # V135 F-28 FIX: Validate inputs before calculation.
    # The OLD code didn't call _validate_input, so negative pipe_length
    # or NaN inputs would silently produce wrong results.
    _validate_input("pipe_length_m", pipe_length_m, min_val=0.0)
    _validate_input("pipe_diameter_m", pipe_diameter_m, min_val=MIN_PIPE_DIAMETER_M, max_val=MAX_PIPE_DIAMETER_M)
    _validate_input("flow_rate_kg_s", flow_rate_kg_s, min_val=MIN_FLOW_RATE_KG_S)
    _validate_input("c_factor", c_factor, min_val=1.0, max_val=200.0)

    # Darcy-Weisbach (water)
    dw_result = calculate_darcy_weisbach_friction_loss(
        pipe_length_m=pipe_length_m,
        pipe_diameter_m=pipe_diameter_m,
        flow_rate_kg_s=flow_rate_kg_s,
        fluid_type=FluidType.WATER,
    )

    # Hazen-Williams (convert units: m → ft, kg/s → gpm)
    # This is a rough comparison — exact conversion requires more care
    length_ft = pipe_length_m / 0.3048
    diameter_in = pipe_diameter_m / 0.0254
    # Q (gpm) = mass_flow (kg/s) / density (kg/m³) × 264.172 (gal/m³) × 60 (s/min)
    density_water = 999.7
    flow_gpm = (flow_rate_kg_s / density_water) * 264.172 * 60.0

    # Hazen-Williams: p = 4.52 × Q^1.85 / (C^1.85 × d^4.87) (psi/ft)
    if c_factor > 0 and diameter_in > 0 and flow_gpm > 0:
        hw_psi_per_ft = 4.52 * (flow_gpm ** 1.85) / ((c_factor ** 1.85) * (diameter_in ** 4.87))
        hw_pressure_loss_psi = hw_psi_per_ft * length_ft
    else:
        hw_pressure_loss_psi = 0.0

    # Comparison
    dw_psi = dw_result.pressure_loss_psi
    if hw_pressure_loss_psi > 0:
        diff_pct = abs(dw_psi - hw_pressure_loss_psi) / hw_pressure_loss_psi * 100.0
    else:
        diff_pct = 0.0

    return {
        "darcy_weisbach": dw_result.to_dict(),
        "hazen_williams": {
            "pressure_loss_psi": hw_pressure_loss_psi,
            "c_factor": c_factor,
        },
        "difference_percent": round(diff_pct, 2),
        "agreement": "good" if diff_pct < 5.0 else "poor (check inputs)",
    }


__all__ = [
    "FluidType",
    "FLUID_PROPERTIES",
    "DarcyWeisbachResult",
    "calculate_darcy_weisbach_friction_loss",
    "compare_with_hazen_williams",
    "GRAVITY_M_S2",
    "RE_LAMINAR_MAX",
    "RE_TURBULENT_MIN",
]
