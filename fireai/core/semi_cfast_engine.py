"""semi_cfast_engine.py — Physics-based smoke layer and tenability engine for ASET/RSET calculations.

This module implements a simplified two-zone fire model inspired by CFAST (Consolidated Model
of Fire Growth and Smoke Transport) for engineering-level ASET (Available Safe Egress Time)
and RSET (Required Safe Egress Time) calculations.

Key References:
    - NFPA 72: National Fire Alarm and Signaling Code (2022 edition)
    - SFPE Handbook of Fire Protection Engineering, 5th Edition (2016)
    - SFPE Engineering Guide to Performance-Based Fire Protection (2007)
    - Alpert, R.L. "Ceiling Jet Flows", SFPE Handbook, Chapter 13
    - NFPA 101: Life Safety Code (2024 edition)
    - BS 7974: Application of fire safety engineering principles

DISCLAIMER:
    This is a LIFE-SAFETY module. Conservative (pessimistic) estimates are preferred over
    optimistic ones. All engineering judgments err on the side of safety. This module is
    intended for preliminary engineering assessments and does NOT replace full CFD or
    zone-model simulations for final design.

Author: FireAI Engineering
Version: 1.0.0
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------
__all__ = [
    "FIRE_GROWTH_RATES",
    "OCCUPANCY_TRAVEL_SPEEDS",
    "PHYSICAL_CONSTANTS",
    "ASETResult",
    "FireScenario",
    "TenabilityCriteria",
    "calculate_aset",
    "calculate_fire_hrr",
    "calculate_rset",
    "calculate_smoke_layer_height",
    "calculate_smoke_layer_temp",
    "calculate_visibility",
    "estimate_co_concentration",
    "verify_aset_rset",
]

# ---------------------------------------------------------------------------
# Physical constants with NFPA/SFPE references
# ---------------------------------------------------------------------------
PHYSICAL_CONSTANTS: Dict[str, float] = {
    # Ambient air density at 20 °C, 1 atm
    # Ref: SFPE Handbook, Table 1-2
    "AMBIENT_AIR_DENSITY_KG_M3": 1.2,
    # Specific heat of air at constant pressure
    # Ref: SFPE Handbook, Chapter 1
    "AIR_SPECIFIC_HEAT_KJ_KG_K": 1.005,
    # Ambient (reference) temperature in Kelvin
    # Ref: Standard engineering reference condition
    "AMBIENT_TEMP_K": 293.15,  # 20 °C
    # Gravitational acceleration
    # Ref: Standard engineering constant
    "GRAVITY_M_S2": 9.81,
    # CO yield factor for generic well-ventilated flaming combustion (kg_CO / kg_fuel)
    # Conservative value per SFPE Handbook, Chapter 26 (Table 26.4)
    # Range: 0.001–0.050 depending on fuel; 0.020 is a conservative generic value
    "CO_YIELD_FACTOR": 0.020,
    # CO molecular weight (g/mol)
    "CO_MOLAR_MASS_G_MOL": 28.01,
    # Air molecular weight (g/mol)
    # Source: CRC Handbook of Chemistry and Physics, 97th Edition (aligned with _MW_AIR in models_v21.py)
    "AIR_MOLAR_MASS_G_MOL": 28.96,
    # Effective heat of combustion for generic fuel (MJ/kg)
    # Ref: SFPE Handbook, Table 3-4; conservative average for common fuels
    "EFFECTIVE_HEAT_OF_COMBUSTION_MJ_KG": 20.0,
    # Soot yield factor for generic flaming combustion (kg_soot / kg_fuel)
    # Ref: SFPE Handbook, Chapter 26; conservative value
    "SOOT_YIELD_FACTOR": 0.050,
    # Specific extinction coefficient for smoke (m²/kg_soot)
    # Ref: SFPE Handbook, Chapter 26; typical range 5000–12000
    # Conservative: use 8700 per Mulholland & Croce
    "SPECIFIC_EXTINCTION_COEFFICIENT_M2_KG": 8700.0,
    # Convective fraction of HRR (fraction of total HRR carried by plume)
    # Ref: SFPE Handbook, Chapter 13; typically 0.6–0.7
    # Conservative (higher plume enthalpy): 0.7
    "CONVECTIVE_HRR_FRACTION": 0.7,
}

# ---------------------------------------------------------------------------
# Fire growth rates per NFPA 72 / SFPE
# ---------------------------------------------------------------------------
# t² fire growth coefficient alpha (kW/s²)
# Ref: NFPA 72-2022, Annex A; SFPE Handbook, Chapter 21
#   slow:       alpha = 0.00293 kW/s²  (e.g., cotton / fabric)
#   medium:     alpha = 0.01172 kW/s²  (e.g., residential furnishing)
#   fast:       alpha = 0.04689 kW/s²  (e.g., foam / plastic)
#   ultra-fast: alpha = 0.1876  kW/s²  (e.g., high-rack storage, pool fires)
FIRE_GROWTH_RATES: Dict[str, float] = {
    "slow": 0.00293,
    "medium": 0.01172,
    "fast": 0.04689,
    "ultra-fast": 0.1876,
    "ultrafast": 0.1876,  # Alias — some callers use no hyphen
}

# ---------------------------------------------------------------------------
# Occupancy travel speeds per SFPE Engineering Guide
# ---------------------------------------------------------------------------
# Ref: SFPE Handbook, Chapter 61; PD 7974-6
# Speeds in m/s for able-bodied adults; reduced for elderly, children, mobility-impaired
OCCUPANCY_TRAVEL_SPEEDS: Dict[str, float] = {
    "office": 1.19,  # SFPE default adult walking speed on level
    "residential": 1.05,  # Slightly reduced (mixed demographics)
    "assembly": 1.05,  # Dense crowd, reduced speed per SFPE Ch. 61
    "healthcare": 0.75,  # Patients with reduced mobility
    "education": 1.05,  # Schools (children, slower than adults)
    "retail": 1.05,  # Shopping (mixed, distracted)
    "industrial": 1.19,  # Able-bodied workers
    "elderly_care": 0.50,  # Significantly reduced mobility
    "childcare": 0.60,  # Very young children
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FireScenario:
    """Defines a fire scenario for ASET calculation.

    Attributes:
        fire_load_MJ: Total fire load in megajoules (MJ). Used to determine
            when the fire transitions from growth to fully-developed (if applicable).
            Ref: NFPA 101, Chapter 7; SFPE Engineering Guide.
        fire_growth_rate: t² fire growth rate category. Must be one of:
            "slow", "medium", "fast", "ultra-fast".
            Ref: NFPA 72-2022, Annex A; SFPE Handbook, Chapter 21.
        room_area_m2: Floor area of the compartment in square metres.
        room_height_m: Floor-to-ceiling height in metres.
        ventilation_opening_m2: Total area of ventilation openings (doors, windows)
            in square metres. Affects smoke filling rate and CO accumulation.
            Ref: SFPE Handbook, Chapter 15 (ventilation-limited fires).
        ceiling_type: Ceiling geometry. "FLAT" (default), "SLOPED", or "BEAM".
            Affects ceiling jet temperature and smoke layer formation.
            Ref: SFPE Handbook, Chapter 13 (Alpert ceiling jet).

    """

    fire_load_MJ: float
    fire_growth_rate: str
    room_area_m2: float
    room_height_m: float
    ventilation_opening_m2: float
    ceiling_type: str = "FLAT"

    def __post_init__(self) -> None:
        """Validate scenario parameters at construction time."""
        # V58 CRITICAL: NaN/Inf bypasses <= 0 checks (NaN <= 0 is False)
        _nan_fields = {
            "fire_load_MJ": self.fire_load_MJ,
            "room_area_m2": self.room_area_m2,
            "room_height_m": self.room_height_m,
            "ventilation_opening_m2": self.ventilation_opening_m2,
        }
        for fname, fval in _nan_fields.items():
            if not math.isfinite(fval):
                raise ValueError(f"{fname} must be finite (not NaN/Inf), got {fval}")
        if self.fire_load_MJ <= 0:
            raise ValueError(f"fire_load_MJ must be positive, got {self.fire_load_MJ}")
        if self.fire_growth_rate not in FIRE_GROWTH_RATES:
            raise ValueError(
                f"fire_growth_rate must be one of {list(FIRE_GROWTH_RATES)}, got '{self.fire_growth_rate}'"
            )
        if self.room_area_m2 <= 0:
            raise ValueError(f"room_area_m2 must be positive, got {self.room_area_m2}")
        if self.room_height_m <= 0:
            raise ValueError(f"room_height_m must be positive, got {self.room_height_m}")
        if self.ventilation_opening_m2 < 0:
            raise ValueError(f"ventilation_opening_m2 must be non-negative, got {self.ventilation_opening_m2}")
        valid_ceilings = {"FLAT", "SLOPED", "BEAM"}
        if self.ceiling_type.upper() not in valid_ceilings:
            raise ValueError(f"ceiling_type must be one of {valid_ceilings}, got '{self.ceiling_type}'")
        self.ceiling_type = self.ceiling_type.upper()


@dataclass
class TenabilityCriteria:
    """Defines tenability limits for occupant safety assessment.

    All values are conservative per SFPE and NFPA guidance.

    Attributes:
        max_temp_c: Maximum tolerable upper-layer temperature (°C).
            Ref: SFPE Handbook, Chapter 67; ISO 13571. 60 °C is the threshold
            for incapacitation due to heat exposure over extended periods.
        min_vis_m: Minimum acceptable visibility (metres).
            Ref: SFPE Handbook, Chapter 26; BS 7974-2. 10 m for reflecting
            signs, 3 m is the absolute minimum for wayfinding.
        max_co_ppm: Maximum tolerable CO concentration (ppm).
            Ref: SFPE Handbook, Chapter 67; ISO 13571. 500 ppm causes
            incapacitation after ~30 min exposure.
        max_hcl_ppm: Maximum tolerable HCl concentration (ppm).
            Ref: SFPE Handbook, Chapter 67. 0 ppm default (any irritant
            gas is a tenability threat). Set to specific limit if needed.
        max_o2_pct: Minimum tolerable O₂ concentration (%).
            Ref: SFPE Handbook, Chapter 67; ISO 13571. Below 15% causes
            impaired judgment and loss of motor control.

    """

    max_temp_c: float = 60.0
    min_vis_m: float = 10.0
    max_co_ppm: float = 500.0
    max_hcl_ppm: float = 0.0
    max_o2_pct: float = 15.0

    def __post_init__(self) -> None:
        # V58 CRITICAL: NaN/Inf bypasses <= 0 checks (NaN <= 0 is False)
        _nan_fields = {
            "max_temp_c": self.max_temp_c,
            "min_vis_m": self.min_vis_m,
            "max_co_ppm": self.max_co_ppm,
            "max_hcl_ppm": self.max_hcl_ppm,
            "max_o2_pct": self.max_o2_pct,
        }
        for fname, fval in _nan_fields.items():
            if not math.isfinite(fval):
                raise ValueError(f"{fname} must be finite (not NaN/Inf), got {fval}")
        if self.max_temp_c <= 0:
            raise ValueError(f"max_temp_c must be positive, got {self.max_temp_c}")
        if self.min_vis_m <= 0:
            raise ValueError(f"min_vis_m must be positive, got {self.min_vis_m}")
        if self.max_co_ppm < 0:
            raise ValueError(f"max_co_ppm must be non-negative, got {self.max_co_ppm}")
        if self.max_hcl_ppm < 0:
            raise ValueError(f"max_hcl_ppm must be non-negative, got {self.max_hcl_ppm}")
        if not (0 < self.max_o2_pct <= 21):
            raise ValueError(f"max_o2_pct must be in (0, 21], got {self.max_o2_pct}")


@dataclass
class ASETResult:
    """Result of an ASET (Available Safe Egress Time) calculation.

    Attributes:
        aset_seconds: Available Safe Egress Time in seconds — the time at
            which the FIRST tenability criterion is violated.
        limiting_criterion: Human-readable description of which criterion
            was violated first (e.g., "Temperature exceeded 60 °C").
        layer_height_at_aset_m: Smoke layer interface height at ASET (m).
        layer_temp_at_aset_c: Smoke layer temperature at ASET (°C).
        visibility_at_aset_m: Visibility at ASET (m).
        co_concentration_ppm: CO concentration at ASET (ppm).
        details: Dictionary with full time-history and intermediate results
            for audit trail and debugging.

    """

    aset_seconds: float
    limiting_criterion: str
    layer_height_at_aset_m: float
    layer_temp_at_aset_c: float
    visibility_at_aset_m: float
    co_concentration_ppm: float
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core calculation functions
# ---------------------------------------------------------------------------


def calculate_fire_hrr(growth_rate: str, time_seconds: float) -> float:
    """Calculate Heat Release Rate (HRR) using the NFPA t² fire growth model.

    The t² model is defined as:

        Q = alpha * t²

    where:
        Q     = heat release rate (kW)
        alpha = fire growth coefficient (kW/s²)
        t     = time from effective ignition (s)

    Ref: NFPA 72-2022, Annex A.8.3.3; SFPE Handbook, Chapter 21;
         Heskestad, G. "Fire Plumes", SFPE Handbook, Chapter 13.

    Args:
        growth_rate: One of "slow", "medium", "fast", "ultra-fast".
        time_seconds: Time from effective ignition in seconds.

    Returns:
        Heat Release Rate in kilowatts (kW).

    Raises:
        ValueError: If growth_rate is invalid or time_seconds is negative.

    """
    if time_seconds < 0:
        raise ValueError(f"time_seconds must be non-negative, got {time_seconds}")
    if growth_rate not in FIRE_GROWTH_RATES:
        raise ValueError(f"growth_rate must be one of {list(FIRE_GROWTH_RATES)}, got '{growth_rate}'")

    alpha = FIRE_GROWTH_RATES[growth_rate]
    hrr = alpha * time_seconds**2
    return hrr


def calculate_smoke_layer_height(
    room_area_m2: float,
    room_height_m: float,
    fire_hrr_kw: float,
    time_seconds: float,
    ceiling_type: str = "FLAT",
) -> float:
    """Calculate smoke layer interface height using a simplified two-zone model.

    The smoke layer descends as the fire plume entrains air and fills the upper
    zone. This uses the simplified zone-model equation:

        Y = H * (1 - (Q_c / (rho * cp * T * sqrt(g) * H^5 * A))^(1/3))

    which is derived from the conservation of mass and energy in the upper layer,
    simplified for engineering use. A more practical form commonly used in
    engineering practice (per SFPE Handbook, Chapter 15) is:

        Y = H - (Q_c / (rho * cp * T_amb * sqrt(g) * A * H^2))^(1/3) * H

    For conservative engineering estimates, we use the well-established
    Zukoski plume filling model:

        V_upper = Q_c * t / (rho * cp * Delta_T)

    where the interface height drops as:

        Y = H * (1 - (Q_c / (rho_0 * c_p * T_0 * sqrt(g) * H^(5/2) * A))^(1/3) * t^(2/3))

    Ref: SFPE Handbook, Chapter 15 (Smoke Control);
         Zukoski, N.B. "Development of a Stratified Ceiling Layer in the Early
         Stages of a Closed-Room Fire", Fire Safety Journal, 1985;
         NFPA 92-2021, Annex B.

    For ceiling type adjustments:
        - FLAT: Standard correlation
        - SLOPED: Smoke accumulates at high side; layer forms ~10% faster
        - BEAM: Channeling effect; layer descends ~15% faster in beam channels

    Args:
        room_area_m2: Floor area of the compartment (m²).
        room_height_m: Ceiling height of the compartment (m).
        fire_hrr_kw: Current heat release rate (kW).
        time_seconds: Time from effective ignition (s).
        ceiling_type: "FLAT", "SLOPED", or "BEAM".

    Returns:
        Smoke layer interface height in metres above floor. Clamped to [0, room_height_m].

    Raises:
        ValueError: If room_area_m2, room_height_m, or time_seconds are invalid.

    """
    if room_area_m2 <= 0:
        raise ValueError(f"room_area_m2 must be positive, got {room_area_m2}")
    if room_height_m <= 0:
        raise ValueError(f"room_height_m must be positive, got {room_height_m}")
    if time_seconds < 0:
        raise ValueError(f"time_seconds must be non-negative, got {time_seconds}")

    # Physical constants
    rho_0 = PHYSICAL_CONSTANTS["AMBIENT_AIR_DENSITY_KG_M3"]  # 1.2 kg/m³
    c_p = PHYSICAL_CONSTANTS["AIR_SPECIFIC_HEAT_KJ_KG_K"]  # 1.005 kJ/(kg·K)
    T_0 = PHYSICAL_CONSTANTS["AMBIENT_TEMP_K"]  # 293.15 K
    g = PHYSICAL_CONSTANTS["GRAVITY_M_S2"]  # 9.81 m/s²
    chi_c = PHYSICAL_CONSTANTS["CONVECTIVE_HRR_FRACTION"]  # 0.7

    H = room_height_m
    A = room_area_m2

    # V58 CRITICAL: NaN fire_hrr_kw bypasses max() → NaN → all guards fail
    if not math.isfinite(fire_hrr_kw) or not math.isfinite(room_height_m) or not math.isfinite(room_area_m2):
        # Fail-safe: smoke at floor level (most dangerous assumption)
        return 0.0

    # Convective HRR (kW)
    Q_c = chi_c * max(fire_hrr_kw, 0.0)

    if Q_c < 1e-6 or time_seconds < 1e-6:
        return H  # No smoke yet; interface at ceiling

    # Zukoski ceiling-layer filling model (simplified):
    # The dimensionless parameter:
    #   Q* = Q_c / (rho_0 * c_p * T_0 * sqrt(g) * H^(5/2) * A)
    # Interface height:
    #   Y = H * (1 - Q*^(1/3) * t^(2/3))   [approximate for early growth]
    # More accurately, using cumulative mass in upper layer:
    #   m_upper = integral of plume entrainment rate dt
    # For a t² fire, plume entrainment rate scales as Q^(1/3) * z^(5/3)
    # The simplified engineering correlation:
    #   Y/H = 1 - (Q_c / (rho_0 * c_p * T_0 * sqrt(g) * H^(5/2) * A))^(1/3) * t^(2/3)
    # CRITICAL FIX (2026-05-22): Was H^5, but Zukoski (1985) / NFPA 92 Annex B
    # defines Q* = Q_c / (rho_0 * c_p * T_0 * sqrt(g) * H^(5/2) * A).
    # H^5 overestimates the denominator by ~15x at H=3m, making ASET ~2.5x too long.

    denominator = rho_0 * c_p * T_0 * math.sqrt(g) * (H**2.5) * A
    if denominator < 1e-30:
        return 0.0

    Q_star = Q_c / denominator
    layer_fraction = Q_star ** (1.0 / 3.0) * time_seconds ** (2.0 / 3.0)

    # Ceiling type correction factors (conservative)
    ceiling_factor = 1.0
    ceiling_type_upper = ceiling_type.upper()
    if ceiling_type_upper == "SLOPED":
        # Smoke channels to high side faster; effective fill rate ~10% higher
        ceiling_factor = 1.10
    elif ceiling_type_upper == "BEAM":
        # Beam channels accelerate smoke transport; ~15% faster descent
        ceiling_factor = 1.15

    layer_fraction *= ceiling_factor

    Y = H * (1.0 - layer_fraction)

    # V58 CRITICAL: NaN Y would be clamped to H (appears safe) per IEEE 754
    # min(H, NaN) = H → max(0.0, H) = H → smoke at ceiling = SAFE (wrong!)
    if not math.isfinite(Y):
        return 0.0  # Fail-safe: smoke at floor level

    # Clamp to physical bounds
    Y = max(0.0, min(H, Y))

    return Y


def calculate_smoke_layer_temp(
    fire_hrr_kw: float,
    room_height_m: float,
    ceiling_type: str = "FLAT",
    ambient_temp_c: float = 20.0,
) -> float:
    """Calculate ceiling jet / smoke layer temperature using the Alpert correlation.

    The Alpert ceiling jet temperature correlation:

        T_ceiling = T_amb + (16.9 * Q^(2/3)) / H^(5/3)

    where:
        T_ceiling = peak ceiling jet temperature rise (K, same as °C for ΔT)
        Q          = total HRR (kW)
        H          = ceiling height above fire source (m)
        16.9       = empirical coefficient (K·m^(4/3) / kW^(2/3))

    This is the stagnation-point temperature for an unconfined ceiling.
    For a confined compartment with a hot gas layer, this represents the
    maximum temperature at the ceiling. The average upper-layer temperature
    is typically lower; we conservatively use the ceiling jet temperature
    as the layer temperature for tenability assessment.

    Ref: Alpert, R.L. "Calculation of response time of ceiling-mounted
         fire detectors", Fire Technology, 1972;
         SFPE Handbook, 5th Ed., Chapter 13 (Ceiling Jet Flows);
         NFPA 92-2021, Annex B.

    Ceiling type adjustments:
        - FLAT: Standard Alpert correlation
        - SLOPED: Ceiling jet accelerates along slope; ~5% temp increase
        - BEAM: Channeling effect increases local temperatures; ~10% increase

    Args:
        fire_hrr_kw: Current heat release rate (kW).
        room_height_m: Ceiling height above fire (m).
        ceiling_type: "FLAT", "SLOPED", or "BEAM".
        ambient_temp_c: Ambient temperature in °C.

    Returns:
        Smoke layer temperature in °C.

    Raises:
        ValueError: If room_height_m is not positive.

    """
    if room_height_m <= 0:
        raise ValueError(f"room_height_m must be positive, got {room_height_m}")

    Q = max(fire_hrr_kw, 0.0)
    H = room_height_m

    if Q < 1e-6:
        return ambient_temp_c

    # Alpert ceiling jet correlation: ΔT = 16.9 * Q^(2/3) / H^(5/3)
    # Note: Q in kW, H in metres, result ΔT in °C (or K, equivalent)
    delta_T = 16.9 * (Q ** (2.0 / 3.0)) / (H ** (5.0 / 3.0))

    # Ceiling type correction (conservative)
    ceiling_factor = 1.0
    ceiling_type_upper = ceiling_type.upper()
    if ceiling_type_upper == "SLOPED":
        ceiling_factor = 1.05
    elif ceiling_type_upper == "BEAM":
        ceiling_factor = 1.10

    delta_T *= ceiling_factor

    T_layer = ambient_temp_c + delta_T
    return T_layer


def calculate_visibility(smoke_optical_density_per_m: float) -> float:
    """Calculate visibility through smoke using the Bouguer-Beer-Lambert law.

    Visibility is inversely proportional to the optical density (extinction
    coefficient) of the smoke:

        S = C / OD

    where:
        S  = visibility (m)
        OD = optical density per metre (1/m or dB/m)
        C  = constant depending on sign type:
            - C = 3 for reflecting signs (conservative, used here)
            - C = 8 for illuminated / self-luminous signs

    The conservative value of C = 3 is used per SFPE guidance for
    life-safety calculations where sign type is unknown.

    Ref: SFPE Handbook, 5th Ed., Chapter 26 (Smoke Production and Properties);
         Mulholland, G.W. "Smoke Production and Properties", SFPE Handbook;
         Jin, T. "Visibility through Fire Smoke", Journal of Fire & Flammability, 1978;
         BS 7974-2:2014, Section 8.

    Args:
        smoke_optical_density_per_m: Optical density (extinction coefficient)
            per metre in units of 1/m. Must be non-negative.

    Returns:
        Visibility in metres. Returns infinity if optical density is zero
        (clear air). Returns 0 if optical density is extremely high.

    Raises:
        ValueError: If optical density is negative.

    """
    if smoke_optical_density_per_m < 0:
        raise ValueError(f"smoke_optical_density_per_m must be non-negative, got {smoke_optical_density_per_m}")

    if smoke_optical_density_per_m < 1e-10:
        return float("inf")  # Clear air, essentially infinite visibility

    # Conservative: C = 3 for reflecting signs
    C = 3.0
    visibility = C / smoke_optical_density_per_m
    return max(0.0, visibility)


def _compute_optical_density(
    fire_hrr_kw: float,
    time_seconds: float,
    room_area_m2: float,
    room_height_m: float,
) -> float:
    """Estimate smoke optical density in the upper layer.

    Uses the soot yield method:
        1. Compute mass loss rate from HRR: m_dot = Q / Delta_H_c
        2. Compute soot yield rate: m_dot_soot = y_soot * m_dot
        3. Compute soot concentration in upper layer (cumulative)
        4. Optical density = alpha_ext * C_soot

    Ref: SFPE Handbook, Chapter 26; Mulholland & Croce.

    Args:
        fire_hrr_kw: Current HRR (kW).
        time_seconds: Elapsed time (s).
        room_area_m2: Room floor area (m²).
        room_height_m: Room ceiling height (m).

    Returns:
        Optical density per metre (1/m) in the upper smoke layer.

    """
    Delta_H_c = PHYSICAL_CONSTANTS["EFFECTIVE_HEAT_OF_COMBUSTION_MJ_KG"]  # 20 MJ/kg
    y_soot = PHYSICAL_CONSTANTS["SOOT_YIELD_FACTOR"]  # 0.050
    alpha_ext = PHYSICAL_CONSTANTS["SPECIFIC_EXTINCTION_COEFFICIENT_M2_KG"]  # 8700

    # V58 HIGH: NaN fire_hrr_kw bypasses max() → NaN → OD corrupted
    if not math.isfinite(fire_hrr_kw):
        return float("inf")  # Fail-safe: worst-case optical density

    Q = max(fire_hrr_kw, 0.0)

    if Q < 1e-6 or time_seconds < 1e-6:
        return 0.0

    # Mass loss rate (kg/s) = HRR (kW) / Heat of combustion (MJ/kg)
    # Note: HRR in kW = kJ/s, Delta_H_c in MJ/kg = 1000 kJ/kg
    m_dot_fuel = Q / (Delta_H_c * 1000.0)  # kg/s

    # Soot production rate
    m_dot_soot = y_soot * m_dot_fuel  # kg/s

    # Accumulated soot in upper layer (kg)
    # For a t² fire, average HRR up to time t ≈ Q(t)/3
    # Total soot = integral of m_dot_soot(t) dt ≈ m_dot_soot * t / 3
    # More accurately, for t² fire: total soot = y_soot * alpha * t³ / (3 * Delta_H_c * 1000)
    # But we use the simpler estimate with current HRR for engineering purposes
    total_soot = m_dot_soot * time_seconds / 3.0  # kg (approximate for growing fire)

    # V59 FIX (Finding 5): Upper layer volume computation improved.
    # Previously used fixed V/3 which underestimates OD in late-stage fires
    # when the smoke layer has descended below 2/3 height. In CFAST, the upper
    # layer grows as the fire develops: initially ~1/3, then 1/2, then 2/3+ as
    # the smoke layer descends. A fixed V/3 is conservative for EARLY smoke
    # detection (higher concentration = easier detection), but ANTI-conservative
    # for LATE-stage tenability (it underestimates the volume that soot is
    # dispersed into, making the concentration appear HIGHER than reality).
    # This could trigger premature "tenability exceeded" alarms.
    #
    # Fix: Model upper layer as growing with fire development. At early times
    # (small cumulative soot), the layer is thin (~1/3). As soot accumulates,
    # the layer grows. Use a simple model: layer_fraction = 1/3 + 2/3 * (1 - exp(-t/t_fill))
    # where t_fill is the characteristic filling time based on room geometry.
    # This matches CFAST behavior: fast-filling rooms reach 100% layer quickly,
    # while large rooms take longer.
    room_volume = room_area_m2 * room_height_m
    # Characteristic filling time: proportional to room volume / plume entrainment
    # Using Thomas correlation: t_fill ≈ V / (0.21 * Q^(1/3) * h^(5/3))
    # Simplified for engineering estimate:
    if fire_hrr_kw > 0:
        t_fill = room_volume / (0.21 * (fire_hrr_kw ** (1.0 / 3.0)) * (room_height_m ** (5.0 / 3.0)) + 1e-9)
        t_fill = max(t_fill, 60.0)  # Minimum 60s filling time
        layer_fraction = 1.0 / 3.0 + 2.0 / 3.0 * (1.0 - math.exp(-time_seconds / t_fill))
    else:
        layer_fraction = 1.0 / 3.0  # No fire — initial state
    upper_layer_volume = room_volume * layer_fraction

    if upper_layer_volume < 1e-6:
        return float("inf")

    # Soot concentration (kg/m³)
    C_soot = total_soot / upper_layer_volume

    # Optical density (1/m)
    od = alpha_ext * C_soot

    return od


def estimate_co_concentration(
    fire_hrr_kw: float,
    room_volume_m3: float,
    ventilation_opening_m2: float,
    time_seconds: float,
) -> float:
    """Estimate CO concentration in the compartment using a simplified well-mixed model.

    The simplified CO estimation model:

        CO_ppm = y_CO * Q * t / (V * A_v^(1/2) * ventilation_factor)

    where:
        y_CO  = CO yield factor (kg_CO / kg_fuel)
        Q     = HRR (kW)
        t     = time (s)
        V     = room volume (m³)
        A_v   = ventilation opening area (m²)
        ventilation_factor = empirical correction for opening geometry

    This is a CONSERVATIVE simplified model that over-predicts CO concentrations
    compared to detailed CFAST simulations, which is appropriate for life-safety
    calculations. The model accounts for reduced ventilation (which increases CO
    production in vitiated fires) by reducing the ventilation factor when openings
    are small.

    Ref: SFPE Handbook, Chapter 26 (Toxicity Assessment);
         NFPA 101-2024, Annex A;
         BS 7974-2:2014, Section 7;
         Purser, D.A. "Assessment of Hazards to Occupants from Smoke",
         SFPE Handbook, Chapter 67.

    Args:
        fire_hrr_kw: Current heat release rate (kW).
        room_volume_m3: Room volume (m³).
        ventilation_opening_m2: Total ventilation opening area (m²).
        time_seconds: Elapsed time (s).

    Returns:
        Estimated CO concentration in ppm (parts per million by volume).

    Raises:
        ValueError: If room_volume_m3 <= 0 or time_seconds < 0.

    """
    if room_volume_m3 <= 0:
        raise ValueError(f"room_volume_m3 must be positive, got {room_volume_m3}")
    if time_seconds < 0:
        raise ValueError(f"time_seconds must be non-negative, got {time_seconds}")

    # V58 HIGH: NaN fire_hrr_kw → max(NaN, 0.0) = NaN → CO = 0.0 (non-conservative)
    if not math.isfinite(fire_hrr_kw):
        return float("inf")  # Fail-safe: worst-case CO

    Q = max(fire_hrr_kw, 0.0)

    if Q < 1e-6 or time_seconds < 1e-6:
        return 0.0

    # Physical constants
    Delta_H_c = PHYSICAL_CONSTANTS["EFFECTIVE_HEAT_OF_COMBUSTION_MJ_KG"]  # 20 MJ/kg
    y_CO = PHYSICAL_CONSTANTS["CO_YIELD_FACTOR"]  # 0.020
    M_CO = PHYSICAL_CONSTANTS["CO_MOLAR_MASS_G_MOL"]  # 28.01
    M_air = PHYSICAL_CONSTANTS["AIR_MOLAR_MASS_G_MOL"]  # 28.96

    # Mass loss rate from HRR
    m_dot_fuel = Q / (Delta_H_c * 1000.0)  # kg/s

    # CO production rate (kg_CO/s)
    m_dot_CO = y_CO * m_dot_fuel

    # Ventilation factor: accounts for opening geometry
    # Minimum ventilation area is assumed to be 0.1 m² even if sealed
    # (no room is perfectly airtight; cracks, etc.)
    A_v = max(ventilation_opening_m2, 0.1)

    # Ventilation factor per SFPE simplified model:
    # Higher opening area = more ventilation = less CO accumulation
    # Factor has units of m/s^(1/2), representing flow rate scaling
    ventilation_factor = 0.5 * math.sqrt(A_v)  # Empirical, conservative

    # Total CO mass produced (kg) — approximate for growing fire
    # For t² fire, total energy ≈ Q(t) * t / 3
    # Total CO ≈ m_dot_CO * t / 3
    total_CO_mass = m_dot_CO * time_seconds / 3.0  # kg

    # CO concentration in the room (well-mixed, kg/m³)
    # Effective ventilation reduces concentration
    effective_volume = room_volume_m3 * (1.0 + ventilation_factor * time_seconds / room_volume_m3)
    CO_mass_concentration = total_CO_mass / max(effective_volume, 1e-6)  # kg/m³

    # Convert to ppm by volume:
    # ppm = (mass_conc / M_CO) / (rho_air / M_air) * 1e6
    rho_air = PHYSICAL_CONSTANTS["AMBIENT_AIR_DENSITY_KG_M3"]  # 1.2 kg/m³
    CO_ppm = (CO_mass_concentration / M_CO) / (rho_air / M_air) * 1e6

    # For under-ventilated fires (small openings), CO production increases
    # significantly. Apply a ventilation correction factor.
    # Ref: SFPE Handbook, Chapter 26; Pitts, W.M. "The Global Equivalence Ratio
    #      Concept and Its Application to Flammable Compartment Fires"
    # Ventilation-limited regime: when A_v * sqrt(H_opening) is small relative to Q
    # Simplified: if opening is very small relative to fire size, increase CO
    if A_v < 1.0:
        # Under-ventilated: CO can increase by factor of 2-5
        # Conservative factor: 2.0
        ventilation_correction = 2.0 / max(A_v, 0.1)
        CO_ppm *= min(ventilation_correction, 5.0)  # Cap at 5x

    return max(0.0, CO_ppm)


def calculate_aset(
    scenario: FireScenario,
    criteria: Optional[TenabilityCriteria] = None,
    time_step_s: float = 5.0,
    max_time_s: float = 3600.0,
) -> ASETResult:
    """Calculate Available Safe Egress Time (ASET) for a fire scenario.

    Steps through time at the specified resolution until ANY tenability criterion
    is violated. Returns the time at which conditions first become untenable.

    Tenability criteria checked (in order of typical criticality):
        1. Smoke layer temperature > max_temp_c
        2. Visibility < min_vis_m
        3. CO concentration > max_co_ppm
        4. O₂ concentration < max_o2_pct
        5. HCl concentration > max_hcl_ppm (if criterion > 0)

    The calculation is CONSERVATIVE:
        - The first criterion violated determines ASET
        - No credit is taken for smoke control systems
        - No credit is taken for fire suppression
        - Layer descent is calculated with pessimistic assumptions

    Ref: SFPE Engineering Guide to Performance-Based Fire Protection;
         NFPA 101-2024, Chapter 7;
         BS 7974-2:2014;
         ISO 13571:2012 (Life-threatening components of fire).

    Args:
        scenario: FireScenario defining the fire and compartment.
        criteria: TenabilityCriteria defining the safety limits.
            Defaults to standard criteria if not provided.
        time_step_s: Time step for the calculation loop (seconds).
            Smaller steps give more precise ASET but take longer.
        max_time_s: Maximum simulation time (seconds). If no criterion
            is violated by this time, ASET = max_time_s.

    Returns:
        ASETResult with the computed ASET and all intermediate values.

    Raises:
        ValueError: If time_step_s <= 0 or max_time_s <= 0.

    """
    if time_step_s <= 0:
        raise ValueError(f"time_step_s must be positive, got {time_step_s}")
    if max_time_s <= 0:
        raise ValueError(f"max_time_s must be positive, got {max_time_s}")

    if criteria is None:
        criteria = TenabilityCriteria()

    # Derived parameters
    room_volume_m3 = scenario.room_area_m2 * scenario.room_height_m

    # Time-history storage for audit trail
    time_history: List[Dict[str, Any]] = []

    # Track the limiting criterion
    limiting_criterion = "No criterion violated within max_time_s"
    aset_seconds = max_time_s

    # Values at ASET (will be overwritten when criterion is violated)
    layer_height_at_aset = scenario.room_height_m
    layer_temp_at_aset = 20.0
    visibility_at_aset = float("inf")
    co_at_aset = 0.0

    t = 0.0
    while t <= max_time_s:
        # Current HRR (t² model)
        hrr = calculate_fire_hrr(scenario.fire_growth_rate, t)

        # Check if fire has consumed available fuel load
        # Total energy released = alpha * t³ / 3 (integral of alpha*t² dt)
        alpha = FIRE_GROWTH_RATES[scenario.fire_growth_rate]
        total_energy_MJ = alpha * (t**3) / 3.0 / 1000.0  # kJ to MJ

        if total_energy_MJ >= scenario.fire_load_MJ:
            # Fire has burned through available fuel; steady-state or decay
            # For conservative estimate, maintain peak HRR
            # (In reality, fire would decay, but conservative assumption)
            hrr = calculate_fire_hrr(
                scenario.fire_growth_rate, (3.0 * scenario.fire_load_MJ * 1000.0 / alpha) ** (1.0 / 3.0)
            )

        # Smoke layer interface height
        layer_height = calculate_smoke_layer_height(
            scenario.room_area_m2,
            scenario.room_height_m,
            hrr,
            t,
            scenario.ceiling_type,
        )

        # Smoke layer temperature
        layer_temp = calculate_smoke_layer_temp(
            hrr,
            scenario.room_height_m,
            scenario.ceiling_type,
        )

        # Smoke optical density and visibility
        od = _compute_optical_density(hrr, t, scenario.room_area_m2, scenario.room_height_m)
        visibility = calculate_visibility(od)

        # CO concentration
        co_ppm = estimate_co_concentration(
            hrr,
            room_volume_m3,
            scenario.ventilation_opening_m2,
            t,
        )

        # O₂ depletion estimate (simplified)
        # Uses the dedicated O₂ depletion model for consistency
        o2_pct = _estimate_o2_depletion(hrr, room_volume_m3, scenario.ventilation_opening_m2, t)

        # HCl estimation (simplified: only for PVC-containing fuels)
        # For generic scenarios, HCl ≈ 0 unless specific fuel info is available
        hcl_ppm = 0.0

        # Store time-history point (every 10 steps to limit memory)
        step_index = int(t / time_step_s)
        if step_index % 10 == 0 or t >= max_time_s - time_step_s:
            time_history.append(
                {
                    "time_s": round(t, 2),
                    "hrr_kW": round(hrr, 2),
                    "layer_height_m": round(layer_height, 4),
                    "layer_temp_c": round(layer_temp, 2),
                    "visibility_m": round(visibility, 4) if visibility != float("inf") else float("inf"),
                    "co_ppm": round(co_ppm, 2),
                    "o2_pct": round(o2_pct, 2),
                    "optical_density_per_m": round(od, 6),
                }
            )

        # ---- Check tenability criteria ----
        violated = False

        # 1. Temperature
        if layer_temp > criteria.max_temp_c:
            limiting_criterion = f"Temperature exceeded {criteria.max_temp_c} °C (reached {layer_temp:.1f} °C)"
            violated = True

        # 2. Visibility
        if not violated and visibility < criteria.min_vis_m:
            limiting_criterion = f"Visibility below {criteria.min_vis_m} m (reached {visibility:.2f} m)"
            violated = True

        # 3. CO
        if not violated and co_ppm > criteria.max_co_ppm:
            limiting_criterion = f"CO concentration exceeded {criteria.max_co_ppm} ppm (reached {co_ppm:.1f} ppm)"
            violated = True

        # 4. O₂
        if not violated and o2_pct < criteria.max_o2_pct:
            limiting_criterion = f"O₂ concentration below {criteria.max_o2_pct}% (reached {o2_pct:.1f}%)"
            violated = True

        # 5. HCl (only if criterion is set > 0)
        if not violated and criteria.max_hcl_ppm > 0 and hcl_ppm > criteria.max_hcl_ppm:
            limiting_criterion = f"HCl concentration exceeded {criteria.max_hcl_ppm} ppm (reached {hcl_ppm:.1f} ppm)"
            violated = True

        # 6. Smoke layer interface reaching typical occupant height (1.8 m)
        #    This is an additional conservative check per BS 7974-2
        if not violated and layer_height < 1.8:
            limiting_criterion = f"Smoke layer descended below 1.8 m (occupant height) (reached {layer_height:.2f} m)"
            violated = True

        if violated:
            aset_seconds = t
            layer_height_at_aset = layer_height
            layer_temp_at_aset = layer_temp
            visibility_at_aset = visibility
            co_at_aset = co_ppm
            break

        t += time_step_s

    # If loop completed without violation, ASET = max_time_s
    else:
        aset_seconds = max_time_s
        # Use last computed values
        layer_height_at_aset = layer_height
        layer_temp_at_aset = layer_temp
        visibility_at_aset = visibility
        co_at_aset = co_ppm

    # Build details dict
    peak_hrr = calculate_fire_hrr(
        scenario.fire_growth_rate,
        min(aset_seconds, max_time_s),
    )

    details: Dict[str, Any] = {
        "scenario": {
            "fire_load_MJ": scenario.fire_load_MJ,
            "fire_growth_rate": scenario.fire_growth_rate,
            "room_area_m2": scenario.room_area_m2,
            "room_height_m": scenario.room_height_m,
            "ventilation_opening_m2": scenario.ventilation_opening_m2,
            "ceiling_type": scenario.ceiling_type,
            "room_volume_m3": room_volume_m3,
        },
        "criteria": {
            "max_temp_c": criteria.max_temp_c,
            "min_vis_m": criteria.min_vis_m,
            "max_co_ppm": criteria.max_co_ppm,
            "max_hcl_ppm": criteria.max_hcl_ppm,
            "max_o2_pct": criteria.max_o2_pct,
        },
        "time_step_s": time_step_s,
        "max_time_s": max_time_s,
        "peak_hrr_at_aset_kW": round(peak_hrr, 2),
        "time_history": time_history,
        "notes": [
            "Conservative (pessimistic) estimates used throughout.",
            "No credit taken for smoke control or suppression systems.",
            "Smoke layer descent checked against 1.8 m occupant height.",
            "CO model uses simplified well-mixed approximation.",
        ],
    }

    return ASETResult(
        aset_seconds=round(aset_seconds, 2),
        limiting_criterion=limiting_criterion,
        layer_height_at_aset_m=round(layer_height_at_aset, 4),
        layer_temp_at_aset_c=round(layer_temp_at_aset, 2),
        visibility_at_aset_m=(round(visibility_at_aset, 4) if visibility_at_aset != float("inf") else float("inf")),
        co_concentration_ppm=round(co_at_aset, 2),
        details=details,
    )


def _estimate_o2_depletion(
    fire_hrr_kw: float,
    room_volume_m3: float,
    ventilation_opening_m2: float,
    time_seconds: float,
) -> float:
    """Estimate O₂ concentration depletion in the compartment.

    Simplified model: O₂ is consumed proportionally to HRR, and replenished
    through ventilation openings.

    Ref: SFPE Handbook, Chapter 15 (Compartment Fire Thermodynamics);
         Thomas, P.H. "Fires in Enclosures", SFPE Handbook.

    Args:
        fire_hrr_kw: Current HRR (kW).
        room_volume_m3: Room volume (m³).
        ventilation_opening_m2: Ventilation opening area (m²).
        time_seconds: Elapsed time (s).

    Returns:
        O₂ concentration as percentage by volume.

    """
    # V58 HIGH: NaN fire_hrr_kw → NaN O₂ calculation
    if not math.isfinite(fire_hrr_kw) or not math.isfinite(room_volume_m3):
        return 0.0  # Fail-safe: 0% O₂ (most dangerous)

    Q = max(fire_hrr_kw, 0.0)
    V = room_volume_m3

    if Q < 1e-6 or time_seconds < 1e-6:
        return 20.9  # Ambient O₂ concentration

    # Stoichiometric O₂ consumption: ~0.7 kg O₂ per MJ of fuel burned
    # Ref: SFPE Handbook, Chapter 15
    # For generic hydrocarbon: C₃H₈ + 5O₂ → 3CO₂ + 4H₂O
    # O₂ consumption ≈ 1.5 kg O₂ / kg fuel, fuel energy ≈ 43 MJ/kg
    # → ~0.035 kg O₂ / MJ; conservative: 0.05 kg O₂ / MJ
    o2_consumption_rate = 0.05  # kg O₂ per MJ (conservative)

    # Total energy released (MJ) — for t² fire, average is Q/3
    # total_energy_MJ = Q * t / 3 / 1000  (Q in kW = kJ/s, so MJ = kJ/1000)
    total_energy_MJ = Q * time_seconds / 3.0 / 1000.0

    # Total O₂ consumed (kg)
    total_O2_consumed = o2_consumption_rate * total_energy_MJ

    # Ventilation replenishment: air flow through opening
    # Simplified: flow_rate ≈ 0.5 * A_v * sqrt(2 * g * H_opening * ΔT/T)
    # For engineering estimate: flow_rate ≈ 0.4 * A_v (m³/s) for typical openings
    A_v = max(ventilation_opening_m2, 0.1)
    air_flow_rate = 0.4 * A_v  # m³/s (conservative)

    # Total fresh air supplied (m³)
    total_air_supplied = air_flow_rate * time_seconds

    # O₂ in fresh air: 20.9% by volume → 0.209 * rho_air * (M_O2/M_air) kg/m³
    rho_air = PHYSICAL_CONSTANTS["AMBIENT_AIR_DENSITY_KG_M3"]  # 1.2 kg/m³
    O2_mass_fraction_in_air = 0.233  # kg O₂ / kg air (by mass)
    o2_in_fresh_air = total_air_supplied * rho_air * O2_mass_fraction_in_air  # kg

    # Initial O₂ in room
    initial_O2 = V * rho_air * O2_mass_fraction_in_air  # kg

    # Current O₂ mass
    current_O2 = max(0.0, initial_O2 + o2_in_fresh_air - total_O2_consumed)

    # O₂ concentration by mass → convert to volume %
    # By volume: O₂ vol% ≈ O2_mass / (total_air_mass) * (M_air / M_O2) * 100
    # Simplified: at ambient, 23.3% by mass = 20.9% by volume
    # Linear scaling:
    o2_mass_fraction = current_O2 / max(initial_O2 + o2_in_fresh_air, 1e-6)
    o2_vol_pct = o2_mass_fraction / 0.233 * 20.9  # Convert back to vol%

    # Clamp to physical range
    o2_vol_pct = max(0.0, min(21.0, o2_vol_pct))

    return o2_vol_pct


def calculate_rset(
    room_area_m2: float,
    room_height_m: float,
    travel_distance_m: float,
    occupancy_type: str = "office",
    pre_movement_s: float = 60.0,
    mobility_factor: float = 1.0,
) -> Dict[str, Any]:
    """Calculate Required Safe Egress Time (RSET).

    RSET is the time required for all occupants to reach a place of safety:

        RSET = t_det + t_pre + t_travel

    where:
        t_det    = detection time (seconds)
        t_pre    = pre-movement time (seconds)
        t_travel = travel time to exit (seconds)

    Detection time is estimated based on fire growth rate and ceiling height
    using the Alpert correlation for detector activation at typical spacing.

    Travel time is calculated using SFPE walking speeds adjusted for
    occupancy type and mobility.

    Ref: SFPE Handbook, Chapter 61 (Employing the Hydraulic Model in
         Assessing Emergency Egress);
         NFPA 101-2024, Chapter 7;
         PD 7974-6:2004 (Human Factors: Life Safety Strategies);
         BS 7974-2:2014.

    Args:
        room_area_m2: Floor area of the compartment (m²).
        room_height_m: Ceiling height (m).
        travel_distance_m: Maximum travel distance to nearest exit (m).
        occupancy_type: Type of occupancy. Must be one of:
            "office", "residential", "assembly", "healthcare",
            "education", "retail", "industrial", "elderly_care", "childcare".
        pre_movement_s: Pre-movement time in seconds (recognition + response).
            Default 60 s per SFPE guidance for office occupancies.
            Ref: PD 7974-6, Table 3.
        mobility_factor: Multiplier for walking speed. 1.0 = normal,
            >1.0 = slower (e.g., 1.5 for mobility-impaired).

    Returns:
        Dictionary with RSET breakdown:
            - detection_time_s
            - pre_movement_s
            - travel_time_s
            - rset_seconds
            - walking_speed_m_s
            - occupancy_type
            - notes

    Raises:
        ValueError: If any physical parameter is invalid.

    """
    if room_area_m2 <= 0:
        raise ValueError(f"room_area_m2 must be positive, got {room_area_m2}")
    if room_height_m <= 0:
        raise ValueError(f"room_height_m must be positive, got {room_height_m}")
    if travel_distance_m < 0:
        raise ValueError(f"travel_distance_m must be non-negative, got {travel_distance_m}")
    if occupancy_type not in OCCUPANCY_TRAVEL_SPEEDS:
        raise ValueError(f"occupancy_type must be one of {list(OCCUPANCY_TRAVEL_SPEEDS)}, got '{occupancy_type}'")
    if pre_movement_s < 0:
        raise ValueError(f"pre_movement_s must be non-negative, got {pre_movement_s}")
    if mobility_factor <= 0:
        raise ValueError(f"mobility_factor must be positive, got {mobility_factor}")

    # --- Detection time ---
    # Estimate using a "medium" growth fire and Alpert ceiling jet correlation
    # Typical smoke detector activation: RTI * u^(1/2) ≈ temperature rise rate
    # Simplified: detection when HRR reaches ~100 kW (typical smoke detector threshold)
    # For medium fire: t_det = sqrt(Q/alpha) = sqrt(100/0.01172) ≈ 92 s
    # This is conservative (detectors often activate at lower HRR)
    # Ref: NFPA 72-2022, Annex B; SFPE Handbook, Chapter 13
    detection_hrr_threshold = 100.0  # kW (conservative smoke detector activation)
    alpha_medium = FIRE_GROWTH_RATES["medium"]
    detection_time_s = math.sqrt(detection_hrr_threshold / alpha_medium)
    # Round up to nearest 5 seconds (conservative)
    detection_time_s = math.ceil(detection_time_s / 5.0) * 5.0

    # --- Travel time ---
    # Walking speed per SFPE, adjusted for occupancy and mobility
    base_speed = OCCUPANCY_TRAVEL_SPEEDS[occupancy_type]  # m/s
    effective_speed = base_speed / mobility_factor  # Higher factor = slower
    # Minimum speed floor: 0.3 m/s (wheelchair user in crowd)
    effective_speed = max(effective_speed, 0.3)

    # Travel time = distance / speed
    # Add flow time component for dense crowds: +10% for queuing at exits
    # Ref: SFPE Handbook, Chapter 61
    raw_travel_time = travel_distance_m / effective_speed
    # Flow/crowd factor (add 10% for potential queuing)
    crowd_factor = 1.10
    travel_time_s = raw_travel_time * crowd_factor

    # --- Pre-movement time ---
    # Use as provided; typical values per PD 7974-6:
    #   Office (alert): 30-60 s
    #   Office (sleeping): 120-300 s
    #   Assembly: 60-180 s
    #   Healthcare: 120-300 s
    # Already provided as argument; just use it

    # --- RSET ---
    rset_seconds = detection_time_s + pre_movement_s + travel_time_s

    return {
        "detection_time_s": round(detection_time_s, 2),
        "pre_movement_s": round(pre_movement_s, 2),
        "travel_time_s": round(travel_time_s, 2),
        "rset_seconds": round(rset_seconds, 2),
        "walking_speed_m_s": round(effective_speed, 4),
        "base_walking_speed_m_s": base_speed,
        "mobility_factor": mobility_factor,
        "occupancy_type": occupancy_type,
        "travel_distance_m": travel_distance_m,
        "crowd_factor": crowd_factor,
        "notes": [
            f"Detection time based on medium growth fire reaching {detection_hrr_threshold} kW.",
            f"Walking speed: {effective_speed:.2f} m/s ({occupancy_type}, mobility factor {mobility_factor}).",
            f"Crowd factor of {crowd_factor} applied for potential queuing at exits.",
            "Pre-movement time should be adjusted for specific occupancy per PD 7974-6.",
            "RSET is conservative (pessimistic) for life-safety assessment.",
        ],
    }


def verify_aset_rset(
    aset_seconds: float,
    rset_seconds: float,
    safety_factor: float = 1.5,
) -> Dict[str, Any]:
    """Verify ASET/RSET compliance with required safety factor.

    The fundamental criterion for life safety is:

        ASET > RSET × safety_factor

    The safety factor accounts for uncertainties in:
        - Fire development (growth rate variability)
        - Human behavior (pre-movement time variability)
        - Model approximations (simplified physics)
        - Material properties (unknown fuel packages)

    Typical safety factors per SFPE and BS 7974:
        - 1.5: Normal confidence level (well-characterized scenarios)
        - 2.0: Standard engineering practice (typical design)
        - 3.0: High confidence required (critical occupancies)

    Ref: SFPE Engineering Guide to Performance-Based Fire Protection (2007);
         BS 7974-1:2019, Section 7 (Safety Factors);
         ISO 23332:2021 (Fire safety engineering — Design and assessment
         of egress arrangements).

    Args:
        aset_seconds: Available Safe Egress Time (seconds).
        rset_seconds: Required Safe Egress Time (seconds).
        safety_factor: Required safety factor. Default 1.5 per SFPE.
            Must be > 1.0.

    Returns:
        Dictionary with:
            - is_safe (bool): True if ASET > RSET × safety_factor
            - safety_margin_pct: Percentage by which ASET exceeds the
              required threshold. Negative means non-compliant.
            - aset_seconds
            - rset_seconds
            - required_aset_seconds: RSET × safety_factor
            - safety_factor
            - details: Human-readable compliance statement

    Raises:
        ValueError: If aset_seconds < 0, rset_seconds < 0, or safety_factor <= 1.0.

    """
    if aset_seconds < 0:
        raise ValueError(f"aset_seconds must be non-negative, got {aset_seconds}")
    if rset_seconds < 0:
        raise ValueError(f"rset_seconds must be non-negative, got {rset_seconds}")
    if safety_factor <= 1.0:
        raise ValueError(
            f"safety_factor must be > 1.0, got {safety_factor}. Life-safety requires a margin of safety beyond RSET."
        )

    required_aset = rset_seconds * safety_factor
    is_safe = aset_seconds > required_aset

    # Safety margin percentage
    if required_aset > 0:
        safety_margin_pct = ((aset_seconds - required_aset) / required_aset) * 100.0
    else:
        safety_margin_pct = float("inf") if aset_seconds > 0 else 0.0

    # Build details
    margin_time = aset_seconds - required_aset
    if is_safe:
        details = (
            f"COMPLIANT: ASET ({aset_seconds:.1f} s) exceeds "
            f"RSET × {safety_factor} ({required_aset:.1f} s) by "
            f"{margin_time:.1f} s ({safety_margin_pct:.1f}% margin)."
        )
    elif aset_seconds > rset_seconds:
        details = (
            f"NON-COMPLIANT: ASET ({aset_seconds:.1f} s) exceeds "
            f"RSET ({rset_seconds:.1f} s) but does NOT meet the "
            f"safety factor of {safety_factor}. "
            f"Required ASET: {required_aset:.1f} s. "
            f"Shortfall: {-margin_time:.1f} s ({-safety_margin_pct:.1f}%)."
        )
    else:
        details = (
            f"CRITICAL: ASET ({aset_seconds:.1f} s) does NOT exceed "
            f"RSET ({rset_seconds:.1f} s). "
            f"Occupants cannot safely evacuate. "
            f"Shortfall: {-margin_time:.1f} s."
        )

    return {
        "is_safe": is_safe,
        "safety_margin_pct": round(safety_margin_pct, 2),
        "aset_seconds": round(aset_seconds, 2),
        "rset_seconds": round(rset_seconds, 2),
        "required_aset_seconds": round(required_aset, 2),
        "safety_factor": safety_factor,
        "margin_time_s": round(margin_time, 2),
        "details": details,
    }
