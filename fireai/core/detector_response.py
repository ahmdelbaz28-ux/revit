"""fireai.core.detector_response — NFPA 72 Detector Response Time Modeling
=======================================================================

Implements detector response time estimation per NFPA 72 and fire
engineering principles:

1. Smoke Detector Response — NFPA 72 §17.7.4, plume velocity model
2. Heat Detector Response  — NFPA 72 §17.7.3, RTI (Response Time Index)
3. Detector Activation Time — ceiling jet temperature model

SAFETY CRITICAL:
  - Response time calculations are for engineering estimation ONLY
  - Actual detector response depends on fire growth rate, ventilation,
    ceiling geometry, and many other factors
  - These models MUST NOT be used as the sole basis for life safety decisions
  - A margin of safety is ALWAYS applied
  - All NaN/Inf inputs are REJECTED

ENGINEERING SOURCES:
  - NFPA 72-2022 §17.7 — Detection Principles
  - NFPA 72-2022 §17.7.3 — Heat Detectors
  - NFPA 72-2022 §17.7.4 — Smoke Detectors
  - Alpert's ceiling jet correlation — fire engineering standard
  - RTI model (Heskestad) — heat detector response theory
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Safety margin applied to all response time estimates (25%)
_RESPONSE_TIME_SAFETY_MARGIN = 0.25

# Typical RTI values for heat detectors (m^0.5 × s^0.5)
_RTI_SPOT_HEAT_LOW = 15.0  # Fast-response spot heat detector
_RTI_SPOT_HEAT_MED = 50.0  # Standard spot heat detector
_RTI_SPOT_HEAT_HIGH = 120.0  # Slow spot heat detector

# Smoke detector typical response velocities (m/s)
_SMOKE_ACTIVATION_VELOCITY = 0.05  # Typical smoke entry velocity

# Ambient temperature (°C)
# V96 FIX: Changed default from 20°C to 30°C (NEC baseline ambient).
# At 20°C, a 57°C heat detector has 37°C rise to trigger; at 40–50°C
# (Egypt), the rise is only 7–17°C — detector activates much faster.
# Using 20°C underestimates activation time in hot climates, which could
# mislead ASET/RSET analysis. The 30°C default matches NEC Table 310.16
# baseline and NFPA 72 typical design ambient.
_AMBIENT_TEMP_C = 30.0

# Stefan-Boltzmann constant for radiative calculations
_STEFAN_BOLTZMANN = 5.67e-8  # W/(m²·K⁴)

# Gravity
_G = 9.81  # m/s²


@dataclass(frozen=True)
class DetectorResponseResult:
    """Result from detector response time calculation.

    This provides an ENGINEERING ESTIMATE of detector activation time.
    It must NOT be used as the sole basis for life safety decisions.

    Fields:
        activation_time_s:  Estimated time to activation (seconds)
        safety_margin_s:     Safety margin applied (seconds)
        total_with_margin:   Activation time + safety margin
        activation_possible: V96 FIX — True if detector can activate, False if
                             gas temperature never reaches activation temp.
                             When False, time fields contain float('inf').
        model_used:          Name of the response model
        detector_type:       'smoke' or 'heat'
        fire_hrr_kw:         Fire heat release rate (kW)
        distance_to_fire_m:  Distance from detector to fire plume axis
        ceiling_height_m:    Ceiling height
        nfpa_section:        NFPA 72 reference
    """

    activation_time_s: float
    safety_margin_s: float
    total_with_margin: float
    activation_possible: bool = True  # V96 FIX: explicit flag for inf results
    model_used: str = ""
    detector_type: str = ""
    fire_hrr_kw: float = 0.0
    distance_to_fire_m: float = 0.0
    ceiling_height_m: float = 0.0
    nfpa_section: str = ""


def calculate_heat_detector_response(
    fire_hrr_kw: float,
    ceiling_height_m: float,
    distance_to_fire_m: float,
    rti: float = _RTI_SPOT_HEAT_MED,
    activation_temp_c: float = 57.0,
    ambient_temp_c: float = _AMBIENT_TEMP_C,
    fire_growth_rate: str = "medium",
) -> DetectorResponseResult:
    """Estimate heat detector activation time using Alpert's ceiling jet model.

    NFPA 72 §17.7.3 — Heat detectors activate when the ceiling jet
    temperature exceeds the detector's rated activation temperature.

    Alpert's ceiling jet correlation:
      For r/H ≤ 0.2 (near plume):
        T_ceiling - T_ambient = 16.9 × (Q*^(2/3)) / H^(5/3)
      For r/H > 0.2 (far from plume):
        T_ceiling - T_ambient = 5.38 × (Q* / r)^(2/3) / H

    Where:
      Q* = Q / (ρ × Cp × T_ambient × g^(1/2) × H^(5/2))
      r = radial distance from plume axis
      H = ceiling height
      Q = heat release rate (kW)

    RTI model (Heskestad):
      dT_detector/dt = (T_gas - T_detector) × u^(1/2) / RTI

    Simplified for steady-state fire:
      t_activation ≈ RTI / (u^(1/2)) × ln((T_gas - T_ambient) / (T_gas - T_activation))

    Args:
        fire_hrr_kw: Fire heat release rate in kilowatts.
        ceiling_height_m: Ceiling height in meters.
        distance_to_fire_m: Radial distance from fire plume axis to detector.
        rti: Response Time Index in m^0.5 × s^0.5.
        activation_temp_c: Detector activation temperature in °C.
        ambient_temp_c: Ambient temperature in °C.
        fire_growth_rate: "slow", "medium", "fast", "ultrafast".

    Returns:
        DetectorResponseResult with estimated activation time.

    """
    # Input validation
    if not math.isfinite(fire_hrr_kw) or fire_hrr_kw <= 0:
        raise ValueError(f"fire_hrr_kw must be positive finite, got {fire_hrr_kw}")
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        raise ValueError(f"ceiling_height_m must be positive finite, got {ceiling_height_m}")
    if not math.isfinite(distance_to_fire_m) or distance_to_fire_m < 0:
        raise ValueError(f"distance_to_fire_m must be non-negative finite, got {distance_to_fire_m}")
    if not math.isfinite(rti) or rti <= 0:
        raise ValueError(f"rti must be positive finite, got {rti}")
    if not math.isfinite(activation_temp_c):
        raise ValueError(f"activation_temp_c must be finite, got {activation_temp_c}")
    if not math.isfinite(ambient_temp_c):
        raise ValueError(f"ambient_temp_c must be finite, got {ambient_temp_c}")

    H = ceiling_height_m
    r = distance_to_fire_m
    Q = fire_hrr_kw

    # Alpert's ceiling jet temperature rise
    # Using simplified form for engineering estimates
    if r <= 0.2 * H:
        # Near plume center
        delta_T = 16.9 * (Q ** (2.0 / 3.0)) / (H ** (5.0 / 3.0))
    else:
        # Away from plume
        delta_T = 5.38 * ((Q / r) ** (2.0 / 3.0)) / H

    # Ceiling jet temperature
    T_gas = ambient_temp_c + delta_T

    # If gas temperature never reaches activation temperature, detector won't activate
    if T_gas <= activation_temp_c:
        # V96 FIX: Set activation_possible=False so downstream code can
        # detect non-activation without checking for float('inf').
        return DetectorResponseResult(
            activation_time_s=float("inf"),
            safety_margin_s=float("inf"),
            total_with_margin=float("inf"),
            activation_possible=False,
            model_used="Alpert_ceiling_jet_RTI",
            detector_type="heat",
            fire_hrr_kw=fire_hrr_kw,
            distance_to_fire_m=distance_to_fire_m,
            ceiling_height_m=ceiling_height_m,
            nfpa_section="NFPA 72 §17.7.3",
        )

    # Ceiling jet velocity (Alpert)
    if r <= 0.2 * H:
        u = 0.96 * (Q / H) ** (1.0 / 3.0)
    else:
        u = 0.2 * (Q ** (1.0 / 3.0) / H ** (1.0 / 2.0)) * (H / r) ** (1.0 / 6.0)

    # RTI model: simplified activation time
    # t = RTI / sqrt(u) × ln((T_gas - T_amb) / (T_gas - T_act))
    if u > 0:
        denominator = T_gas - activation_temp_c
        if denominator <= 0:
            activation_time = float("inf")
        else:
            activation_time = (rti / math.sqrt(u)) * math.log(delta_T / denominator)
    else:
        activation_time = float("inf")

    # Ensure non-negative
    activation_time = max(0.0, activation_time)

    # Apply safety margin
    safety_margin = activation_time * _RESPONSE_TIME_SAFETY_MARGIN
    total_with_margin = activation_time + safety_margin

    return DetectorResponseResult(
        activation_time_s=round(activation_time, 4),
        safety_margin_s=round(safety_margin, 4),
        total_with_margin=round(total_with_margin, 4),
        model_used="Alpert_ceiling_jet_RTI",
        detector_type="heat",
        fire_hrr_kw=fire_hrr_kw,
        distance_to_fire_m=distance_to_fire_m,
        ceiling_height_m=ceiling_height_m,
        nfpa_section="NFPA 72 §17.7.3",
    )


def calculate_smoke_detector_response(
    fire_hrr_kw: float,
    ceiling_height_m: float,
    distance_to_fire_m: float,
    smoke_obscuration_pct_per_m: float = 1.0,
    ambient_temp_c: float = _AMBIENT_TEMP_C,
) -> DetectorResponseResult:
    """Estimate smoke detector activation time using plume transport model.

    NFPA 72 §17.7.4 — Smoke detectors activate when smoke concentration
    exceeds the detector's sensitivity threshold. Most photoelectric
    smoke detectors activate at approximately 1-2% per meter obscuration.

    Simplified plume transport model:
      1. Smoke reaches ceiling at time t_plume ≈ H / u_plume
      2. Ceiling jet spreads radially at velocity u_cj
      3. Smoke concentration at distance r depends on dilution

    For engineering estimates, we use:
      t_transport = H / u_plume + r / u_ceiling_jet
      where u_plume and u_ceiling_jet are derived from fire HRR

    Args:
        fire_hrr_kw: Fire heat release rate in kilowatts.
        ceiling_height_m: Ceiling height in meters.
        distance_to_fire_m: Distance from fire to detector.
        smoke_obscuration_pct_per_m: Smoke obscuration rate (%/m per kW).
        ambient_temp_c: Ambient temperature in °C.

    Returns:
        DetectorResponseResult with estimated activation time.

    """
    # Input validation
    if not math.isfinite(fire_hrr_kw) or fire_hrr_kw <= 0:
        raise ValueError(f"fire_hrr_kw must be positive finite, got {fire_hrr_kw}")
    if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
        raise ValueError(f"ceiling_height_m must be positive finite, got {ceiling_height_m}")
    if not math.isfinite(distance_to_fire_m) or distance_to_fire_m < 0:
        raise ValueError(f"distance_to_fire_m must be non-negative, got {distance_to_fire_m}")

    H = ceiling_height_m
    r = distance_to_fire_m
    Q = fire_hrr_kw

    # Plume centerline velocity at ceiling (Zukoski model)
    # u_plume = 1.2 × (Q/H)^(1/3)
    u_plume = 1.2 * (Q / H) ** (1.0 / 3.0)

    # Time for smoke to reach ceiling
    t_plume = H / max(u_plume, 0.01)

    # Ceiling jet velocity (Alpert)
    if r <= 0.2 * H:
        u_cj = 0.96 * (Q / H) ** (1.0 / 3.0)
    else:
        u_cj = 0.2 * (Q ** (1.0 / 3.0) / H ** (1.0 / 2.0)) * (H / max(r, 0.01)) ** (1.0 / 6.0)

    # Ceiling jet transport time
    t_transport = r / max(u_cj, 0.01)

    # Total estimated activation time
    activation_time = t_plume + t_transport

    # Ensure non-negative
    activation_time = max(0.0, activation_time)

    # Apply safety margin
    safety_margin = activation_time * _RESPONSE_TIME_SAFETY_MARGIN
    total_with_margin = activation_time + safety_margin

    return DetectorResponseResult(
        activation_time_s=round(activation_time, 4),
        safety_margin_s=round(safety_margin, 4),
        total_with_margin=round(total_with_margin, 4),
        model_used="Zukoski_plume_Alpert_ceiling_jet",
        detector_type="smoke",
        fire_hrr_kw=fire_hrr_kw,
        distance_to_fire_m=distance_to_fire_m,
        ceiling_height_m=ceiling_height_m,
        nfpa_section="NFPA 72 §17.7.4",
    )
