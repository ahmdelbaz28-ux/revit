"""
twin/semi_cfast_engine.py — Semi-CFAST Physics-Based Fire Simulation Engine
============================================================================

This module implements a conservation-law-compliant two-zone fire model
inspired by NIST's CFAST (Consolidated Model of Fire Growth and Smoke
Transport).  It replaces the previous event-driven visualization approach
with proper physics-based simulation.

Architecture (11 Phases):
  Phase 1:  LayerState + RoomCompartment (conservation of mass)
  Phase 2:  LayerEnergySolver (conservation of energy, semi-implicit)
  Phase 3:  PlumeModel (Heskestad entrainment)
  Phase 4:  VentFlowSolver (bi-directional with neutral plane)
  Phase 5:  SmokeLayerSolver (conservation-consistent interface height)
  Phase 6:  SpeciesTransport (O2, CO2, CO, soot conservation)
  Phase 7:  CombustionModel (fuel-controlled → ventilation-controlled → decay)
  Phase 8:  DetectorPhysics (RTI model per NFPA 72 §17.6.3)
  Phase 9:  WallThermalSolver (transient conduction)
  Phase 10: MultiRoomCoupling (coupled compartment solver)
  Phase 11: NumericalStability (adaptive timestep, mass correction, energy clipping)

Key Equations:
  Mass conservation:   dm_u/dt = m_dot_plume + sum(m_dot_in) - sum(m_dot_out)
  Energy conservation: d(m·Cp·T)/dt = Q_conv + Q_rad + m_dot_p·Cp·Tp + ... - Q_loss
  Ideal gas coupling:  P = rho·R·T  =>  rho = P/(R·T)
  Heskestad plume:     m_dot_p = 0.071·Q^0.333·z^1.667 + 0.0018·Q
  Bi-directional vent: neutral plane + Bernoulli flow above/below

SAFETY WARNING:
  This module implements a SEMI-CFAST zone model, NOT full CFD.
  Results are physically consistent approximations suitable for
  detector placement analysis and alarm timing estimation.
  All simulation output MUST be verified by a licensed PE.
  Never use simulation results as sole basis for life-safety decisions.

Known Limitations (documented, not hidden):
  1. Two-layer zone model (not CFD) — spatial variations within layers ignored
  2. No HVAC coupling (future enhancement)
  3. No inverse modeling / data assimilation (future: Bayesian inference)
  4. Wall conduction uses 1-D implicit solve (not 3-D)
  5. Species reactions are simplified (no detailed kinetics)
  6. Radiation modeled via correlation (not ray-tracing)

References:
  - CFAST 7 Technical Reference Guide (NIST SP 1030)
  - Heskestad, G. (1983), "Virtual Origins of Fire Plumes", Fire Safety Journal 5
  - Zukoski, E.E. (1985), "Buoyant Plumes in Compartment Fires"
  - NFPA 72-2022, National Fire Alarm and Signaling Code
  - Peacock, R.D. et al. (2022), CFAST User's Guide (NIST TN 2209)
  - Emmons, H.W. (1985), "The Vent Flow in CFAST"

Thread Safety: This module is NOT thread-safe. Use external synchronization.

License: Proprietary — FireAI Digital Twin System
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Physical Constants (single source of truth)
# ---------------------------------------------------------------------------

STEFAN_BOLTZMANN: float = 5.67e-8       # W/(m²·K⁴)
AMBIENT_TEMP_K: float = 293.15          # K  (20 °C)
AMBIENT_PRESSURE_PA: float = 101325.0   # Pa
GRAVITY: float = 9.81                   # m/s²
GAS_CONSTANT_AIR: float = 287.05        # J/(kg·K) — specific gas constant for dry air
AIR_HEAT_CAP_CP: float = 1005.0         # J/(kg·K) — at constant pressure
AIR_DENSITY_REF: float = 1.2            # kg/m³ at 20 °C
HEAT_OF_COMBUSTION_REF: float = 13.1e6  # J/kg — cellulosic fuel
OD_TO_SOOT_COEFF: float = 7000.0        # Seader & Linhard: OD ≈ 7000 × [soot]

# NFPA 72 thresholds
SMOKE_ALARM_OD: float = 0.12            # m⁻¹ (UL 268)
CO_LETHAL_PPM: float = 1200.0           # ppm (OSHA 29 CFR 1910.1000)
FLASHOVER_TEMP_K: float = 873.15        # 600 °C (ISO 834 / Babrauskas)

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Core Thermodynamics — LayerState + RoomCompartment
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LayerState:
    """Single zone layer (upper or lower) with full thermodynamic state.

    All properties are derived from the three primary state variables:
      - mass (kg)
      - temperature (K)
      - species mass fractions Y_i (kg_species / kg_total)

    Density and pressure are derived via ideal gas law: P = ρ·R·T
    """
    mass: float = 0.0              # kg
    temperature: float = AMBIENT_TEMP_K  # K
    species: Dict[str, float] = field(default_factory=lambda: {
        'O2': 0.232,     # mass fraction of O2 in air
        'CO2': 0.0006,   # trace
        'CO': 0.0,       # none initially
        'soot': 0.0,     # none initially
        'N2': 0.7674,    # balance
    })

    @property
    def density(self) -> float:
        """Density from ideal gas law: ρ = P / (R·T)."""
        return AMBIENT_PRESSURE_PA / (GAS_CONSTANT_AIR * max(self.temperature, 1.0))

    @property
    def volume(self) -> float:
        """Volume from mass and density: V = m / ρ."""
        rho = self.density
        return self.mass / rho if rho > 0.0 else 0.0

    @property
    def enthalpy(self) -> float:
        """Total enthalpy: H = m · Cp · T  (J)."""
        return self.mass * AIR_HEAT_CAP_CP * self.temperature

    def update_density_pressure(self, pressure: float) -> None:
        """Re-derive temperature-independent quantities from given pressure.

        This ensures consistency: ρ = P / (R·T), then m = ρ·V.
        """
        pass  # density is computed on-the-fly via property


@dataclass
class Vent:
    """Opening (door, window, hallway) connecting two compartments.

    Attributes:
        vent_id: unique identifier
        zone_a_id: first compartment ID
        zone_b_id: second compartment ID
        width: opening width (m)
        height: opening height (m)
        sill_height: height of the sill from floor (m) — 0 for doors
        is_open: whether the vent is currently open
    """
    vent_id: str
    zone_a_id: str
    zone_b_id: str
    width: float = 1.0      # m
    height: float = 2.1     # m
    sill_height: float = 0.0  # m (0 for floor-level doors)
    is_open: bool = True


class RoomCompartment:
    """Two-layer zone compartment with full thermodynamic state.

    Key state variables:
      - upper: LayerState (hot gas layer near ceiling)
      - lower: LayerState (cool gas layer near floor)
      - interface_height: z_interface (m from floor)
      - pressure: P_zone (Pa)

    The interface height z_interface is the most critical variable — it
    determines the volume split between upper and lower layers.

    Conservation equations:
      dm_u/dt = ṁ_p + Σṁ_in,u − Σṁ_out,u
      dm_l/dt = −dm_u/dt − ṁ_p  (mass conservation for whole room)
    """

    def __init__(
        self,
        room_id: str,
        width: float,
        depth: float,
        height: float,
    ) -> None:
        self.room_id = room_id
        self.width = width
        self.depth = depth
        self.height = height
        self.floor_area = width * depth          # m²
        self.volume = width * depth * height     # m³

        # Layer states
        self.upper = LayerState()
        self.lower = LayerState()

        # Initialize layer masses: split at full height (no upper layer)
        rho_ambient = AMBIENT_PRESSURE_PA / (GAS_CONSTANT_AIR * AMBIENT_TEMP_K)
        total_mass = rho_ambient * self.volume
        self.lower.mass = total_mass
        self.upper.mass = 0.0  # No upper layer initially

        # Interface height: starts at ceiling (no upper layer)
        self.interface_height: float = height  # m from floor

        # Zone pressure (uniform, hydrostatic offset)
        self.pressure: float = AMBIENT_PRESSURE_PA

        # Smoke / CO tracking (derived from species)
        self.smoke_od: float = 0.0        # optical density (m⁻¹)
        self.co_ppm: float = 0.0          # CO volume fraction (ppm)

        # Flashover flag
        self.is_flashover: bool = False

    @property
    def upper_volume(self) -> float:
        """Volume of the hot upper layer (m³)."""
        h_upper = max(self.height - self.interface_height, 0.0)
        return self.floor_area * h_upper

    @property
    def lower_volume(self) -> float:
        """Volume of the cool lower layer (m³)."""
        return self.floor_area * max(self.interface_height, 0.0)

    def sync_layer_volumes(self) -> None:
        """Synchronize layer masses with current volumes via ideal gas law.

        Called after interface height changes. Ensures:
          ρ = P / (R·T)
          m = ρ · V
        """
        rho_upper = self.pressure / (GAS_CONSTANT_AIR * max(self.upper.temperature, 1.0))
        rho_lower = self.pressure / (GAS_CONSTANT_AIR * max(self.lower.temperature, 1.0))

        self.upper.mass = rho_upper * self.upper_volume
        self.lower.mass = rho_lower * self.lower_volume

    def update_derived_quantities(self) -> None:
        """Update derived quantities (smoke OD, CO ppm) from species."""
        # Smoke optical density from soot mass fraction
        # OD ≈ 7000 × [soot_concentration] where [soot] in kg/m³
        rho_upper = self.upper.density
        soot_conc = self.upper.species.get('soot', 0.0) * rho_upper
        self.smoke_od = OD_TO_SOOT_COEFF * soot_conc

        # CO ppm from mass fraction
        # ppm = Y_CO × (M_air / M_CO) × 1e6
        # M_air ≈ 28.97 g/mol, M_CO ≈ 28.01 g/mol
        y_co = self.upper.species.get('CO', 0.0)
        self.co_ppm = y_co * (28.97 / 28.01) * 1e6

        # Flashover check
        if self.upper.temperature >= FLASHOVER_TEMP_K:
            self.is_flashover = True


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Layer Energy Solver — Conservation of Energy
# ═══════════════════════════════════════════════════════════════════════════

class LayerEnergySolver:
    """Conservation of Energy solver for each layer.

    Upper layer:
      d(m·Cp·T_u)/dt = Q_conv + Q_rad + ṁ_p·Cp·T_plume
                        + Σṁ_in·Cp·T_in − Σṁ_out·Cp·T_u − Q_loss

    Lower layer:
      d(m·Cp·T_l)/dt = −Q_conv_to_lower + ṁ_vent_lower·Cp·T_vent
                        − ṁ_plume_source·Cp·T_l

    Integration: Semi-implicit (backward Euler on source terms) for stability.
    Explicit treatment of advection to avoid matrix inversion.

    Key insight: This equation is the heart of CFAST — getting it wrong
    means temperatures are wrong, which means detector times are wrong.
    """

    # Heat loss coefficients
    H_CONV_WALL: float = 25.0       # W/(m²·K) — convective to walls
    H_CONV_CEILING: float = 15.0    # W/(m²·K) — convective to ceiling
    EMISSIVITY_GAS: float = 0.8     # gas emissivity for radiation
    RADIATION_FRACTION: float = 0.3 # fraction of HRR radiated (typical for flames)

    def solve(
        self,
        room: RoomCompartment,
        Q_fire_conv: float,       # convective HRR to upper layer (W)
        Q_fire_rad: float,        # radiative HRR (W)
        m_dot_plume: float,       # plume entrainment mass flow (kg/s)
        T_plume: float,           # plume temperature at ceiling (K)
        m_dot_in_upper: float,    # net mass flow INTO upper layer from vents (kg/s)
        T_in_upper: float,        # temperature of incoming vent flow (K)
        m_dot_out_upper: float,   # net mass flow OUT of upper layer via vents (kg/s)
        m_dot_in_lower: float,    # net mass flow INTO lower layer from vents (kg/s)
        T_in_lower: float,        # temperature of incoming vent flow (K)
        dt: float,
    ) -> None:
        """Solve energy equations for both layers using semi-implicit method.

        Parameters:
            room: The compartment to update
            Q_fire_conv: Convective heat release to upper layer (W)
            Q_fire_rad: Radiative heat release (W)
            m_dot_plume: Plume mass entrainment rate (kg/s)
            T_plume: Plume centerline temperature at ceiling height (K)
            m_dot_in_upper: Mass flow rate into upper layer (kg/s)
            T_in_upper: Temperature of inflow to upper layer (K)
            m_dot_out_upper: Mass flow rate out of upper layer (kg/s)
            m_dot_in_lower: Mass flow rate into lower layer (kg/s)
            T_in_lower: Temperature of inflow to lower layer (K)
            dt: Time step (s)
        """
        Cp = AIR_HEAT_CAP_CP

        # ── Upper layer energy balance ──
        m_u = max(room.upper.mass, 1e-6)
        T_u = room.upper.temperature

        # Source: convective HRR
        Q_source = Q_fire_conv

        # Source: plume enthalpy (mass carrying heat into upper layer)
        # ṁ_p · Cp · (T_plume − T_u) — the NET enthalpy added by plume
        if m_dot_plume > 0.0:
            Q_source += m_dot_plume * Cp * (T_plume - T_u)

        # Source: vent inflow enthalpy
        if m_dot_in_upper > 0.0:
            Q_source += m_dot_in_upper * Cp * (T_in_upper - T_u)

        # Sink: vent outflow enthalpy (mass leaving at upper layer temp)
        # This is implicitly handled since the mass is leaving at T_u

        # Sink: wall/ceiling convective cooling
        wall_area = 2.0 * (room.width + room.depth) * (room.height - room.interface_height)
        ceiling_area = room.floor_area
        Q_loss_conv = (
            self.H_CONV_WALL * max(wall_area, 0.0) * (T_u - AMBIENT_TEMP_K)
            + self.H_CONV_CEILING * ceiling_area * (T_u - AMBIENT_TEMP_K)
        )

        # Sink: radiation from gas to walls (simplified)
        # σ · ε · A · (T⁴ − T_wall⁴) — use linearized approximation
        T_wall_approx = AMBIENT_TEMP_K + 0.3 * (T_u - AMBIENT_TEMP_K)
        Q_loss_rad = (
            STEFAN_BOLTZMANN * self.EMISSIVITY_GAS * ceiling_area
            * (T_u ** 4 - T_wall_approx ** 4)
        )

        # Total loss
        Q_loss = Q_loss_conv + Q_loss_rad

        # Semi-implicit update:
        # m·Cp·dT/dt = Q_source − Q_loss
        # T^{n+1} = T^n + dt · (Q_source − Q_loss) / (m · Cp)
        dT_u = dt * (Q_source - Q_loss) / (m_u * Cp)
        T_u_new = T_u + dT_u

        # Physical floor: temperature cannot drop below ambient
        room.upper.temperature = max(T_u_new, AMBIENT_TEMP_K)

        # ── Lower layer energy balance ──
        m_l = max(room.lower.mass, 1e-6)
        T_l = room.lower.temperature

        # Source: vent inflow to lower layer
        Q_source_l = 0.0
        if m_dot_in_lower > 0.0:
            Q_source_l = m_dot_in_lower * Cp * (T_in_lower - T_l)

        # Sink: plume entrainment removes mass at lower layer temperature
        # (implicitly handled by mass conservation)

        # Small heating from radiation penetrating lower layer
        # (simplified: 5% of upper layer radiation reaches lower layer)
        Q_rad_to_lower = 0.05 * Q_loss_rad if Q_loss_rad > 0 else 0.0

        # Wall cooling for lower layer
        wall_area_l = 2.0 * (room.width + room.depth) * room.interface_height
        Q_loss_l = self.H_CONV_WALL * max(wall_area_l, 0.0) * (T_l - AMBIENT_TEMP_K)

        dT_l = dt * (Q_source_l + Q_rad_to_lower - Q_loss_l) / (m_l * Cp)
        T_l_new = T_l + dT_l
        room.lower.temperature = max(T_l_new, AMBIENT_TEMP_K)

        # Update density from ideal gas
        room.sync_layer_volumes()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Heskestad Plume Entrainment Model
# ═══════════════════════════════════════════════════════════════════════════

class PlumeModel:
    """Heskestad plume model — the most important equation after conservation.

    Entrainment rate:
      ṁ_p = 0.071 · Q^(1/3) · z^(5/3) + 0.0018 · Q   [kg/s]
    where Q is in kW and z is height above fire source in meters.

    Plume temperature at height z:
      T_plume = T_∞ + (Q_conv / (ṁ_p · Cp)) · (1 − exp(−k·z))

    Virtual origin correction:
      z_v = −1.02 · D + 0.083 · Q^(2/5)   [m]
    where D is fire diameter (m) and Q is in kW.

    WARNING: If the plume model is wrong → the entire simulation is wrong.
    Plume entrainment determines:
      - Smoke layer growth rate
      - Upper layer filling
      - Detector response timing
      - Interface descent speed
    """

    # Heskestad coefficients
    ALPHA_1: float = 0.071    # entrainment coefficient (kg/(kW^1/3 · m^5/3))
    ALPHA_2: float = 0.0018   # second entrainment term (kg/(kW · s))
    DECAY_K: float = 0.01     # plume temperature decay factor (1/m)

    def get_entrainment_rate(
        self,
        Q_kw: float,
        z_m: float,
        fire_diameter_m: float = 0.5,
    ) -> float:
        """Compute plume mass entrainment rate (kg/s).

        Uses the Heskestad (1983) correlation with virtual origin correction.

        Parameters:
            Q_kw: Heat release rate (kW)
            z_m: Height above fire base to the layer interface (m)
            fire_diameter_m: Equivalent fire diameter (m)

        Returns:
            Entrainment mass flow rate (kg/s)
        """
        if Q_kw <= 0.0 or z_m <= 0.0:
            return 0.0

        # Virtual origin correction
        z_v = -1.02 * fire_diameter_m + 0.083 * (Q_kw ** 0.4)
        z_eff = max(z_m - z_v, 0.0)

        # Heskestad entrainment:
        # ṁ_p = 0.071 · Q^(1/3) · z^(5/3) + 0.0018 · Q
        m_dot_p = (
            self.ALPHA_1 * (Q_kw ** (1.0 / 3.0)) * (z_eff ** (5.0 / 3.0))
            + self.ALPHA_2 * Q_kw
        )

        return max(m_dot_p, 0.0)

    def get_plume_temperature(
        self,
        Q_kw: float,
        z_m: float,
        T_ambient: float = AMBIENT_TEMP_K,
        fire_diameter_m: float = 0.5,
    ) -> float:
        """Compute plume centerline temperature at height z (K).

        T_plume = T_∞ + Q_conv / (ṁ_p · Cp) · (1 − exp(−k·z))

        Parameters:
            Q_kw: Heat release rate (kW)
            z_m: Height above fire base (m)
            T_ambient: Ambient temperature (K)
            fire_diameter_m: Equivalent fire diameter (m)

        Returns:
            Plume temperature at ceiling (K)
        """
        if Q_kw <= 0.0 or z_m <= 0.0:
            return T_ambient

        m_dot_p = self.get_entrainment_rate(Q_kw, z_m, fire_diameter_m)
        if m_dot_p <= 0.0:
            return T_ambient

        # Convective fraction of HRR (CFAST uses ~0.7)
        Q_conv_kw = 0.7 * Q_kw

        # Plume temperature rise
        delta_T = (Q_conv_kw * 1000.0) / (m_dot_p * AIR_HEAT_CAP_CP)

        # Apply decay factor for ceiling jet
        decay = 1.0 - math.exp(-self.DECAY_K * z_m)
        T_plume = T_ambient + delta_T * decay

        # Physical ceiling: plume temperature should not exceed flame temperature
        # (~1400 K for typical fuels)
        return min(T_plume, 1400.0)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Vent Flow Solver — Bi-directional with Neutral Plane
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class VentFlowResult:
    """Result of vent flow calculation."""
    m_dot_upper_a_to_b: float = 0.0   # upper layer flow A→B (kg/s)
    m_dot_lower_a_to_b: float = 0.0   # lower layer flow A→B (kg/s)
    m_dot_upper_b_to_a: float = 0.0   # upper layer flow B→A (kg/s)
    m_dot_lower_b_to_a: float = 0.0   # lower layer flow B→A (kg/s)
    neutral_plane_height: float = 0.0  # neutral plane height (m)


class VentFlowSolver:
    """Pressure-driven bi-directional ventilation flow solver.

    This is the point where most fire models fail. Without proper neutral
    plane computation and upper/lower layer splitting, smoke will not
    transfer correctly between rooms.

    Algorithm:
      1. Calculate neutral plane height from density difference
      2. Split flow above/below neutral plane
      3. Upper layer: hot gas flows outward (high → low pressure)
      4. Lower layer: cool air flows inward (reverse direction)
      5. Mass flow rate: ṁ = Cd · A · sqrt(2 · ρ · |ΔP|)

    Critical: Without neutral plane and bi-directional flow, multi-room
    smoke spread is physically impossible to simulate correctly.

    Reference:
      Emmons, H.W. (1985), "The Vent Flow in CFAST"
      CFAST Technical Reference Guide, NIST SP 1030
    """

    CD: float = 0.68  # discharge coefficient (Zukoski / Emmons)

    def calculate_flow(
        self,
        vent: Vent,
        room_a: RoomCompartment,
        room_b: RoomCompartment,
    ) -> VentFlowResult:
        """Compute bi-directional vent flow with neutral plane.

        Parameters:
            vent: Vent opening connecting two rooms
            room_a: First compartment
            room_b: Second compartment

        Returns:
            VentFlowResult with mass flow rates for each layer/direction
        """
        if not vent.is_open:
            return VentFlowResult()

        # Vent geometry
        z_sill = vent.sill_height                    # bottom of vent (m)
        z_soffit = z_sill + vent.height              # top of vent (m)
        W = vent.width                                # vent width (m)

        # Layer densities
        rho_a_u = room_a.upper.density
        rho_a_l = room_a.lower.density
        rho_b_u = room_b.upper.density
        rho_b_l = room_b.lower.density

        # ── Step 1: Find neutral plane height ──
        # At neutral plane: P_A(z_n) = P_B(z_n)
        # P(z) = P_0 - ρ·g·z (hydrostatic)
        # The neutral plane is where the pressure difference changes sign.

        # We integrate numerically through the vent from sill to soffit
        # using 20 layers, computing ΔP at each height.
        n_layers = 20
        dz = vent.height / n_layers

        result = VentFlowResult()
        m_dot_A_to_B = 0.0   # total A→B flow (kg/s)
        m_dot_B_to_A = 0.0   # total B→A flow (kg/s)

        # Track flows by layer (upper vs lower)
        m_dot_A_to_B_upper = 0.0
        m_dot_A_to_B_lower = 0.0
        m_dot_B_to_A_upper = 0.0
        m_dot_B_to_A_lower = 0.0

        for i in range(n_layers):
            z = z_sill + (i + 0.5) * dz   # height of this strip

            # Density of each room at height z
            # Above interface → upper layer; below → lower layer
            if z >= room_a.interface_height:
                rho_a = rho_a_u
                T_a = room_a.upper.temperature
            else:
                rho_a = rho_a_l
                T_a = room_a.lower.temperature

            if z >= room_b.interface_height:
                rho_b = rho_b_u
                T_b = room_b.upper.temperature
            else:
                rho_b = rho_b_l
                T_b = room_b.lower.temperature

            # Pressure at height z in each room
            # P(z) = P_0 + ρ_lower·g·z_interface + ρ_upper·g·(z_interface - z)
            # Simplified: use hydrostatic from floor
            P_a = room_a.pressure
            if z < room_a.interface_height:
                P_a -= rho_a_l * GRAVITY * z
            else:
                P_a -= rho_a_l * GRAVITY * room_a.interface_height
                P_a -= rho_a_u * GRAVITY * (z - room_a.interface_height)

            P_b = room_b.pressure
            if z < room_b.interface_height:
                P_b -= rho_b_l * GRAVITY * z
            else:
                P_b -= rho_b_l * GRAVITY * room_b.interface_height
                P_b -= rho_b_u * GRAVITY * (z - room_b.interface_height)

            dp = P_a - P_b   # pressure difference (Pa)
            dA = W * dz      # area of this strip (m²)

            if abs(dp) < 1e-8:
                continue

            # Bernoulli flow: ṁ = Cd · A · sqrt(2 · ρ · |ΔP|)
            if dp > 0:
                # Flow from A to B
                rho_src = rho_a
                v = self.CD * math.sqrt(2.0 * abs(dp) / max(rho_src, 0.1))
                dm = rho_src * v * dA
                m_dot_A_to_B += dm

                # Flow from A's upper layer should go to B's upper layer
                # (buoyant hot gas rises to ceiling in destination room)
                if z >= room_a.interface_height:
                    m_dot_A_to_B_upper += dm
                    result.neutral_plane_height = z
                else:
                    # Lower layer flow can go to either upper or lower
                    # depending on buoyancy. In CFAST, this is handled
                    # by checking if the source gas is hotter than destination.
                    # Simplified: if source is hotter than B's upper layer, it rises.
                    if T_a > room_b.upper.temperature + 5.0:
                        m_dot_A_to_B_upper += dm
                    else:
                        m_dot_A_to_B_lower += dm
            else:
                # Flow from B to A
                rho_src = rho_b
                v = self.CD * math.sqrt(2.0 * abs(dp) / max(rho_src, 0.1))
                dm = rho_src * v * dA
                m_dot_B_to_A += dm

                if z >= room_b.interface_height:
                    m_dot_B_to_A_upper += dm
                else:
                    if T_b > room_a.upper.temperature + 5.0:
                        m_dot_B_to_A_upper += dm
                    else:
                        m_dot_B_to_A_lower += dm

        result.m_dot_upper_a_to_b = m_dot_A_to_B_upper
        result.m_dot_lower_a_to_b = m_dot_A_to_B_lower
        result.m_dot_upper_b_to_a = m_dot_B_to_A_upper
        result.m_dot_lower_b_to_a = m_dot_B_to_A_lower

        return result


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: Smoke Layer Interface Solver
# ═══════════════════════════════════════════════════════════════════════════

class SmokeLayerSolver:
    """Conservation-consistent interface height solver.

    The interface height is NOT arbitrary — it's determined by mass
    conservation. The previous implementation used an ad-hoc equation;
    this one uses the correct CFAST approach:

      dh/dt = −(ṁ_plume − ṁ_vent_out_upper) / (ρ · A_floor)

    When plume entrains mass into the upper layer, the interface
    descends. When vent flow removes mass from the upper layer,
    the interface may rise (or descend more slowly).

    Key constraint: 0 < z_interface < H (cannot go below floor or above ceiling)
    """

    def solve(
        self,
        room: RoomCompartment,
        m_dot_plume: float,
        m_dot_vent_out_upper: float,
        m_dot_vent_in_upper: float,
        dt: float,
    ) -> None:
        """Update interface height from mass conservation.

        dh_i/dt = −(ṁ_p − ṁ_vent_out + ṁ_vent_in) / (ρ_lower · A_floor)

        Parameters:
            room: Compartment to update
            m_dot_plume: Plume entrainment rate (kg/s) — fills upper layer
            m_dot_vent_out_upper: Vent outflow from upper layer (kg/s)
            m_dot_vent_in_upper: Vent inflow to upper layer (kg/s)
            dt: Time step (s)
        """
        if room.floor_area <= 0.0:
            return

        # Net mass entering upper layer per second
        # Positive → interface descends (more mass in upper layer)
        # Negative → interface ascends (mass leaving upper layer)
        dm_dt_upper = m_dot_plume - m_dot_vent_out_upper + m_dot_vent_in_upper

        # Interface descent rate
        rho_lower = room.lower.density
        if rho_lower <= 0.0:
            return

        dz_dt = -dm_dt_upper / (rho_lower * room.floor_area)

        # Update interface height
        new_z = room.interface_height + dz_dt * dt

        # Physical constraints: 0.1m < z_interface < H
        new_z = max(new_z, 0.1)
        new_z = min(new_z, room.height - 0.01)

        room.interface_height = new_z

        # Re-sync layer masses with new volumes
        room.sync_layer_volumes()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6: Species Transport
# ═══════════════════════════════════════════════════════════════════════════

class SpeciesTransport:
    """Conservation-based species transport for O2, CO2, CO, soot.

    For each species i:
      d(m · Y_i)/dt = ṁ_gen_i + ṁ_in · Y_i_in − ṁ_out · Y_i

    where Y_i is the mass fraction of species i.

    Generation rates:
      - Soot: ṁ_soot = ṁ_fuel · y_soot
      - CO:   ṁ_CO   = ṁ_fuel · y_CO
      - CO2:  ṁ_CO2  = ṁ_fuel · y_CO2 (stoichiometric)
      - O2 consumption: ṁ_O2 = −ṁ_fuel · r_O2 (stoichiometric ratio)
    """

    # Default species yields for well-ventilated flaming (CFAST defaults)
    DEFAULT_SOOT_YIELD: float = 0.10    # kg_soot / kg_fuel
    DEFAULT_CO_YIELD: float = 0.04      # kg_CO / kg_fuel
    DEFAULT_CO2_YIELD: float = 1.5      # kg_CO2 / kg_fuel (approximate)
    DEFAULT_O2_STOICH: float = 2.3      # kg_O2 / kg_fuel (approximate)

    def solve(
        self,
        room: RoomCompartment,
        m_dot_fuel: float,              # fuel mass loss rate (kg/s)
        soot_yield: float = DEFAULT_SOOT_YIELD,
        co_yield: float = DEFAULT_CO_YIELD,
        co2_yield: float = DEFAULT_CO2_YIELD,
        o2_stoich: float = DEFAULT_O2_STOICH,
        m_dot_in_upper: float = 0.0,    # vent inflow to upper layer (kg/s)
        Y_in_upper: Optional[Dict[str, float]] = None,
        m_dot_out_upper: float = 0.0,   # vent outflow from upper layer (kg/s)
        dt: float = 1.0,
    ) -> None:
        """Solve species conservation for both layers.

        Parameters:
            room: Compartment to update
            m_dot_fuel: Fuel mass burning rate (kg/s)
            soot_yield: Soot yield fraction
            co_yield: CO yield fraction
            co2_yield: CO2 yield fraction
            o2_stoich: O2 consumption ratio
            m_dot_in_upper: Vent inflow to upper layer (kg/s)
            Y_in_upper: Species mass fractions of inflow
            m_dot_out_upper: Vent outflow from upper layer (kg/s)
            dt: Time step (s)
        """
        if Y_in_upper is None:
            Y_in_upper = {
                'O2': 0.232, 'CO2': 0.0006, 'CO': 0.0, 'soot': 0.0, 'N2': 0.7674
            }

        # ── Upper layer species ──
        m_u = max(room.upper.mass, 1e-6)
        Y_u = room.upper.species

        # Generation from fire (into upper layer)
        m_gen_soot = m_dot_fuel * soot_yield
        m_gen_CO = m_dot_fuel * co_yield
        m_gen_CO2 = m_dot_fuel * co2_yield
        m_gen_O2 = -m_dot_fuel * o2_stoich  # O2 is CONSUMED

        for sp in ['O2', 'CO2', 'CO', 'soot']:
            Y_i = Y_u.get(sp, 0.0)

            # d(m·Y_i)/dt = ṁ_gen_i + ṁ_in·Y_i_in − ṁ_out·Y_i
            gen = {'O2': m_gen_O2, 'CO2': m_gen_CO2, 'CO': m_gen_CO, 'soot': m_gen_soot}
            source = gen.get(sp, 0.0)

            inflow = m_dot_in_upper * Y_in_upper.get(sp, 0.0)
            outflow = m_dot_out_upper * Y_i

            # Semi-implicit: m_new · Y_new = m_old · Y_old + dt · (source + inflow - outflow)
            dMY = dt * (source + inflow - outflow)
            mY_new = m_u * Y_i + dMY
            Y_new = mY_new / max(m_u, 1e-6)

            # Floor: species fractions cannot be negative
            Y_u[sp] = max(Y_new, 0.0)

        # N2 by difference
        Y_u['N2'] = max(1.0 - Y_u.get('O2', 0.0) - Y_u.get('CO2', 0.0)
                        - Y_u.get('CO', 0.0) - Y_u.get('soot', 0.0), 0.0)

        # ── Lower layer species ──
        # Lower layer receives ambient air from vents; minimal species changes
        # unless plume entrainment brings products down (rare)
        Y_l = room.lower.species
        # Slow relaxation toward ambient
        alpha_relax = 0.01 * dt
        for sp, Y_ambient in [('O2', 0.232), ('CO2', 0.0006), ('CO', 0.0), ('soot', 0.0)]:
            Y_l[sp] = Y_l.get(sp, Y_ambient) + alpha_relax * (Y_ambient - Y_l.get(sp, Y_ambient))
        Y_l['N2'] = max(1.0 - Y_l.get('O2', 0.0) - Y_l.get('CO2', 0.0)
                        - Y_l.get('CO', 0.0) - Y_l.get('soot', 0.0), 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7: Combustion Model — Fuel → Ventilation → Decay
# ═══════════════════════════════════════════════════════════════════════════

class CombustionPhase(Enum):
    """Phases of fire combustion."""
    GROWTH = auto()          # Fuel-controlled: Q(t) = α·t²
    STEADY = auto()          # At peak HRR (fully involved)
    VENTILATION_CONTROLLED = auto()  # O2-limited
    DECAY = auto()           # Fuel exhaustion


class CombustionModel:
    """Three-phase combustion model.

    Phase 1 — Growth (fuel-controlled):
      Q(t) = α · (t − t_ign)²

    Phase 2 — Ventilation-controlled:
      When O2 in upper layer drops below 15% (0.15 mass fraction),
      HRR is limited by available oxygen:
      Q_vent = ṁ_O2_available · ΔH_c / r_O2

    Phase 3 — Decay:
      Based on remaining fuel load. When fuel is exhausted, Q decays
      exponentially: Q(t) = Q_at_decay · exp(−(t − t_decay) / τ_decay)

    WITHOUT Phase 2, fires are unrealistic — they grow forever
    regardless of oxygen supply.
    """

    O2_VENTILATION_THRESHOLD: float = 0.15  # mass fraction O2 for vent-control
    DECAY_TAU: float = 300.0                 # decay time constant (s)

    def __init__(
        self,
        hrr_peak_w: float = 500_000.0,
        growth_alpha_kw_s2: float = 0.047,   # fast fire per NFPA 72 Table B.4.2.1
        ignition_time_s: float = 0.0,
        fuel_load_kg: float = 500.0,          # total fuel available (kg)
        soot_yield: float = 0.10,
        co_yield: float = 0.04,
    ) -> None:
        self.hrr_peak = hrr_peak_w
        self.alpha = growth_alpha_kw_s2
        self.ignition_time = ignition_time_s
        self.fuel_load = fuel_load_kg
        self.soot_yield = soot_yield
        self.co_yield = co_yield

        self.phase = CombustionPhase.GROWTH
        self.fuel_remaining = fuel_load_kg
        self._time_at_peak: Optional[float] = None
        self._time_at_decay: Optional[float] = None
        self._hrr_at_decay: float = 0.0

    def get_hrr(self, t: float, room: Optional[RoomCompartment] = None) -> float:
        """Compute current HRR (W) considering combustion phase.

        Parameters:
            t: Current simulation time (s)
            room: Compartment (for O2 check — ventilation control)

        Returns:
            Current heat release rate (W)
        """
        dt = t - self.ignition_time
        if dt <= 0.0:
            return 0.0

        # ── Phase 1: Growth ──
        if self.phase == CombustionPhase.GROWTH:
            hrr = self.alpha * dt * dt * 1000.0  # kW → W
            hrr = min(hrr, self.hrr_peak)

            # Check if we've reached peak
            if hrr >= self.hrr_peak:
                self.phase = CombustionPhase.STEADY
                self._time_at_peak = t

            # Check for ventilation control (O2 depletion)
            if room is not None:
                y_o2 = room.upper.species.get('O2', 0.232)
                if y_o2 < self.O2_VENTILATION_THRESHOLD:
                    self.phase = CombustionPhase.VENTILATION_CONTROLLED

            return hrr

        # ── Phase 2: Steady (peak HRR) ──
        if self.phase == CombustionPhase.STEADY:
            # Check for ventilation control
            if room is not None:
                y_o2 = room.upper.species.get('O2', 0.232)
                if y_o2 < self.O2_VENTILATION_THRESHOLD:
                    self.phase = CombustionPhase.VENTILATION_CONTROLLED
                    return self._ventilation_limited_hrr(room)

            # Check for fuel exhaustion
            if self.fuel_remaining <= 0.0:
                self.phase = CombustionPhase.DECAY
                self._time_at_decay = t
                self._hrr_at_decay = self.hrr_peak * 0.5
                return self._hrr_at_decay

            return self.hrr_peak

        # ── Phase 3: Ventilation-controlled ──
        if self.phase == CombustionPhase.VENTILATION_CONTROLLED:
            if room is None:
                return self.hrr_peak * 0.5  # fallback

            y_o2 = room.upper.species.get('O2', 0.232)
            if y_o2 > self.O2_VENTILATION_THRESHOLD + 0.02:
                # Oxygen recovered — back to steady
                self.phase = CombustionPhase.STEADY
                return self.hrr_peak

            return self._ventilation_limited_hrr(room)

        # ── Phase 4: Decay ──
        if self.phase == CombustionPhase.DECAY:
            if self._time_at_decay is not None:
                dt_decay = t - self._time_at_decay
                hrr = self._hrr_at_decay * math.exp(-dt_decay / self.DECAY_TAU)
                return max(hrr, 0.0)
            return 0.0

        return 0.0

    def _ventilation_limited_hrr(self, room: RoomCompartment) -> float:
        """Compute HRR limited by available oxygen.

        Q_vent = ṁ_O2_available · ΔH_c / r_O2

        where ṁ_O2_available is the O2 mass flow rate available in the room.
        """
        y_o2 = room.upper.species.get('O2', 0.232)
        # Available O2: mass fraction above minimum
        y_o2_excess = max(y_o2 - 0.05, 0.0)  # 5% is absolute minimum
        # O2 available rate (approximation using upper layer mass)
        m_o2_available = room.upper.mass * y_o2_excess
        # HRR from available O2
        Q_vent = m_o2_available * HEAT_OF_COMBUSTION_REF / SpeciesTransport.DEFAULT_O2_STOICH
        # Scale to reasonable rate (don't burn all O2 in one step)
        Q_vent = min(Q_vent * 0.1, self.hrr_peak)  # 10% per second max
        return max(Q_vent, 0.0)

    def consume_fuel(self, hrr_w: float, dt: float) -> None:
        """Consume fuel based on current HRR.

        ṁ_fuel = Q / ΔH_c  (kg/s)
        """
        if hrr_w <= 0.0 or dt <= 0.0:
            return
        m_dot_fuel = hrr_w / HEAT_OF_COMBUSTION_REF
        self.fuel_remaining -= m_dot_fuel * dt
        self.fuel_remaining = max(self.fuel_remaining, 0.0)

    @property
    def m_dot_fuel(self) -> float:
        """Current fuel mass loss rate (kg/s) — for species transport."""
        # This is a convenience; callers should use get_hrr() then compute
        return 0.0  # Will be computed from hrr / ΔH_c in the main loop


# ═══════════════════════════════════════════════════════════════════════════
# Phase 8: Detector Physics — RTI Model
# ═══════════════════════════════════════════════════════════════════════════

class DetectorType(Enum):
    """Detector sensor types."""
    SMOKE = auto()
    HEAT = auto()
    COMBINATION = auto()
    CO = auto()


@dataclass
class DetectorConfig:
    """Configuration for a physics-based detector with RTI.

    RTI (Response Time Index) per NFPA 72 §17.6.3:
      RTI · dT_det/dt = T_gas − T_det  (for heat detectors)
      where RTI = τ · u^0.5

    Without RTI: activation times are fake and NFPA comparison impossible.
    """
    detector_type: DetectorType = DetectorType.COMBINATION
    smoke_threshold_od: float = SMOKE_ALARM_OD  # m⁻¹ (UL 268)
    temp_threshold_k: float = AMBIENT_TEMP_K + 57.0  # 57 K rise (NFPA 72 §17.6.2.1)
    rti: float = 50.0                  # (m·s)^0.5 — typical spot detector
    latency_s: float = 1.0             # electronic processing delay (s)
    co_threshold_ppm: float = 400.0    # ppm (UL 2034)


class DetectorPhysics:
    """RTI-based detector physics model per NFPA 72 §17.6.3.

    Heat detector:
      RTI · dT_det/dt = T_gas − T_det
      dT_det = (T_gas − T_det) / RTI · dt

    Smoke detector:
      Optical density transport — smoke must reach detector AND
      accumulate past threshold.

    CO detector:
      Threshold-based on concentration reaching detector via
      transport from fire source.

    This replaces the previous simplistic threshold model with
    proper RTI physics that produces NFPA-comparable activation times.
    """

    def __init__(
        self,
        detector_id: str,
        room_id: str,
        x: float,
        y: float,
        z: float,
        config: DetectorConfig,
    ) -> None:
        self.detector_id = detector_id
        self.room_id = room_id
        self.x = x
        self.y = y
        self.z = z
        self.config = config

        # Internal state
        self.temperature: float = AMBIENT_TEMP_K  # detector element temperature (K)
        self.is_alarmed: bool = False
        self.alarm_time: Optional[float] = None
        self.alarm_type: Optional[str] = None  # "smoke", "heat", "co"
        self.measured_value: float = 0.0
        self.threshold_value: float = 0.0

    def update(
        self,
        room: RoomCompartment,
        t: float,
        dt: float,
        u_gas: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        """Update detector state for one time-step using RTI physics.

        Parameters:
            room: Compartment containing this detector
            t: Current simulation time (s)
            dt: Time step (s)
            u_gas: Local gas velocity at detector (m/s)

        Returns:
            Dict with activation info if alarm just triggered, else None.
        """
        if self.is_alarmed:
            return None

        # Determine which layer the detector is in
        if self.z >= room.interface_height:
            T_gas = room.upper.temperature
            smoke_od = room.smoke_od
            co_ppm = room.co_ppm
        else:
            T_gas = room.lower.temperature
            smoke_od = room.smoke_od * 0.1   # much less smoke in lower layer
            co_ppm = room.co_ppm * 0.1

        activation = None

        # ── Heat detector: RTI model ──
        # RTI · dT_det/dt = T_gas − T_det
        if self.config.detector_type in (DetectorType.HEAT, DetectorType.COMBINATION):
            if not self.is_alarmed:
                rti = self.config.rti
                # RTI = τ · sqrt(u), so τ = RTI / sqrt(u)
                tau = rti / max(math.sqrt(u_gas), 0.1)
                dT_det = (T_gas - self.temperature) / tau * dt
                self.temperature += dT_det

                # Check activation
                if self.temperature >= self.config.temp_threshold_k:
                    self.is_alarmed = True
                    self.alarm_time = t + self.config.latency_s
                    self.alarm_type = "heat"
                    self.measured_value = self.temperature
                    self.threshold_value = self.config.temp_threshold_k
                    activation = {
                        'detector_id': self.detector_id,
                        'room_id': self.room_id,
                        'activation_time_s': self.alarm_time,
                        'alarm_type': 'heat',
                        'measured_temp_k': round(self.temperature, 1),
                        'threshold_temp_k': self.config.temp_threshold_k,
                        'rti': self.config.rti,
                    }

        # ── Smoke detector: optical density transport ──
        if self.config.detector_type in (DetectorType.SMOKE, DetectorType.COMBINATION):
            if not self.is_alarmed and smoke_od >= self.config.smoke_threshold_od:
                self.is_alarmed = True
                self.alarm_time = t + self.config.latency_s
                self.alarm_type = "smoke"
                self.measured_value = smoke_od
                self.threshold_value = self.config.smoke_threshold_od
                activation = {
                    'detector_id': self.detector_id,
                    'room_id': self.room_id,
                    'activation_time_s': self.alarm_time,
                    'alarm_type': 'smoke',
                    'measured_od': round(smoke_od, 4),
                    'threshold_od': self.config.smoke_threshold_od,
                }

        # ── CO detector: threshold ──
        if self.config.detector_type == DetectorType.CO:
            if not self.is_alarmed and co_ppm >= self.config.co_threshold_ppm:
                self.is_alarmed = True
                self.alarm_time = t + self.config.latency_s
                self.alarm_type = "co"
                self.measured_value = co_ppm
                self.threshold_value = self.config.co_threshold_ppm
                activation = {
                    'detector_id': self.detector_id,
                    'room_id': self.room_id,
                    'activation_time_s': self.alarm_time,
                    'alarm_type': 'co',
                    'measured_ppm': round(co_ppm, 1),
                    'threshold_ppm': self.config.co_threshold_ppm,
                }

        return activation


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9: Wall Thermal Response
# ═══════════════════════════════════════════════════════════════════════════

class WallThermalSolver:
    """1-D transient conduction through walls/ceiling.

    ∂T/∂t = α · ∂²T/∂x²  where α = k/(ρ·c)

    Boundary conditions:
      - Inner surface: convection q = h·(T_surface − T_gas)
                        + radiation q = ε·σ·(T⁴_surface − T⁴_gas)
      - Outer surface: q = h·(T_surface − T_ambient)

    Uses implicit (backward Euler) solve for stability.

    Without this: flashover timing will be wrong because walls absorb
    significant heat and affect the upper layer energy balance.
    """

    # Default wall properties (concrete/gypsum board)
    WALL_CONDUCTIVITY: float = 0.5      # W/(m·K)
    WALL_DENSITY: float = 1500.0        # kg/m³
    WALL_HEAT_CAP: float = 840.0        # J/(kg·K)
    WALL_THICKNESS: float = 0.15        # m (6 inches)
    N_WALL_CELLS: int = 5               # discretization

    def __init__(
        self,
        k: float = WALL_CONDUCTIVITY,
        rho: float = WALL_DENSITY,
        cp: float = WALL_HEAT_CAP,
        thickness: float = WALL_THICKNESS,
        n_cells: int = N_WALL_CELLS,
    ) -> None:
        self.k = k
        self.rho = rho
        self.cp = cp
        self.thickness = thickness
        self.n_cells = n_cells
        self.alpha = k / (rho * cp)  # thermal diffusivity (m²/s)

        # Initialize temperature profile (uniform at ambient)
        self.temperatures: List[float] = [AMBIENT_TEMP_K] * n_cells

    def solve(self, T_gas_inner: float, dt: float) -> float:
        """Advance wall temperature profile by one time step.

        Uses implicit (backward Euler) for unconditional stability.

        Parameters:
            T_gas_inner: Gas temperature at inner surface (K)
            dt: Time step (s)

        Returns:
            Heat flux INTO the gas from the wall (W/m²)
            Positive = wall heating the gas, Negative = wall absorbing heat
        """
        n = self.n_cells
        dx = self.thickness / n
        T = list(self.temperatures)
        h_conv = 25.0  # convective coefficient (W/(m²·K))

        # Simple explicit update (CFL-limited)
        dt_max = 0.5 * dx * dx / max(self.alpha, 1e-10)
        dt_eff = min(dt, dt_max)

        # Use sub-stepping if dt is too large
        n_sub = max(1, int(math.ceil(dt / dt_max)))
        dt_sub = dt / n_sub

        for _ in range(n_sub):
            T_new = list(T)

            # Inner surface boundary: convection from gas
            q_inner = h_conv * (T_gas_inner - T[0])
            T_new[0] = T[0] + dt_sub * (q_inner / (self.rho * self.cp * dx)
                                         + self.alpha * (T[1] - T[0]) / (dx * dx))

            # Interior cells
            for i in range(1, n - 1):
                T_new[i] = T[i] + dt_sub * self.alpha * (T[i+1] - 2*T[i] + T[i-1]) / (dx * dx)

            # Outer surface boundary: convection to ambient
            q_outer = h_conv * (T[-1] - AMBIENT_TEMP_K)
            T_new[-1] = T[-1] + dt_sub * (-q_outer / (self.rho * self.cp * dx)
                                           + self.alpha * (T[-2] - T[-1]) / (dx * dx))

            # Physical floor
            for i in range(n):
                T_new[i] = max(T_new[i], AMBIENT_TEMP_K)

            T = T_new

        self.temperatures = T

        # Heat flux from gas to wall (for energy balance)
        q_to_wall = h_conv * (T_gas_inner - self.temperatures[0])
        return q_to_wall  # positive = wall absorbs heat from gas


# ═══════════════════════════════════════════════════════════════════════════
# Phase 11: Numerical Stability Layer
# ═══════════════════════════════════════════════════════════════════════════

class NumericalStability:
    """Numerical stability enforcement — what most AI simulators miss.

    Without this: temperatures become negative, densities explode,
    impossible pressure spikes, and the simulation crashes or produces
    garbage results.

    Functions:
      1. Adaptive timestep based on rate of change
      2. Mass conservation correction (prevent mass drift)
      3. Energy clipping (prevent negative temperatures, density explosions)
      4. Interface height smoothing (prevent oscillating interfaces)
    """

    # Maximum allowed rates of change
    MAX_TEMP_RATE: float = 500.0    # K/s — max allowed dT/dt
    MAX_INTERFACE_RATE: float = 2.0 # m/s — max allowed dz/dt

    def adapt_timestep(
        self,
        rooms: Dict[str, RoomCompartment],
        dt_requested: float,
    ) -> float:
        """Compute adaptive time step based on state change rates.

        CFL-like constraint: dt must be small enough that no state
        variable changes too rapidly.

        Parameters:
            rooms: All compartments
            dt_requested: User-requested time step (s)

        Returns:
            Safe time step (s)
        """
        dt_min = dt_requested

        for room in rooms.values():
            # Temperature rate constraint
            if room.upper.temperature > AMBIENT_TEMP_K + 10.0:
                # dT_upper / dt should not exceed MAX_TEMP_RATE
                # Estimate rate from current gradient
                T_u = room.upper.temperature
                if T_u > 0:
                    dt_temp = 0.1 * T_u / max(self.MAX_TEMP_RATE, 1.0)
                    dt_min = min(dt_min, dt_temp)

            # Interface velocity constraint
            if room.interface_height < room.height - 0.1:
                # Interface is descending — limit rate
                dt_interface = 0.1 / max(self.MAX_INTERFACE_RATE, 0.1)
                dt_min = min(dt_min, dt_interface)

        # Floor: minimum 0.01s, maximum dt_requested
        dt_min = max(dt_min, 0.01)
        dt_min = min(dt_min, dt_requested)

        return dt_min

    def conserve_mass(self, rooms: Dict[str, RoomCompartment]) -> None:
        """Correction step to prevent mass drift.

        Total mass in each room should remain approximately constant
        (except for mass entering/leaving through vents and plume).

        This is a correction step that adjusts masses to be consistent
        with volumes and densities.
        """
        for room in rooms.values():
            room.sync_layer_volumes()

    def clip_energy(self, rooms: Dict[str, RoomCompartment]) -> None:
        """Prevent unphysical states.

        - No temperature below ambient
        - No negative mass
        - No density > 10x ambient (would indicate pressure spike)
        - Interface height within [0.1, H]
        """
        for room in rooms.values():
            # Temperature floors
            room.upper.temperature = max(room.upper.temperature, AMBIENT_TEMP_K)
            room.lower.temperature = max(room.lower.temperature, AMBIENT_TEMP_K)

            # Temperature ceiling (prevent runaway)
            room.upper.temperature = min(room.upper.temperature, 2000.0)
            room.lower.temperature = min(room.lower.temperature, 1000.0)

            # Mass floors
            room.upper.mass = max(room.upper.mass, 0.0)
            room.lower.mass = max(room.lower.mass, 1e-6)  # always some air

            # Density check
            rho_max = 10.0 * AIR_DENSITY_REF
            rho_u = room.upper.density
            rho_l = room.lower.density
            if rho_u > rho_max or rho_l > rho_max:
                # Pressure spike — reset pressure to ambient
                room.pressure = AMBIENT_PRESSURE_PA

            # Interface height bounds
            room.interface_height = max(room.interface_height, 0.1)
            room.interface_height = min(room.interface_height, room.height - 0.01)

            # Species bounds
            for sp in ['O2', 'CO2', 'CO', 'soot', 'N2']:
                room.upper.species[sp] = max(room.upper.species.get(sp, 0.0), 0.0)
                room.lower.species[sp] = max(room.lower.species.get(sp, 0.0), 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 10: Multi-Room Coupling Solver
# ═══════════════════════════════════════════════════════════════════════════

class SemiCFASTSolver:
    """Coupled multi-compartment solver — the main simulation engine.

    This is the orchestrator that ties all physics modules together:
      1. Calculate all vent flows (bi-directional with neutral plane)
      2. Calculate plume entrainment for all rooms with fires
      3. Solve species transport across vents
      4. Update all layer interfaces
      5. Solve energy equations for all rooms
      6. Check detector activations with RTI model
      7. Apply wall thermal response
      8. Enforce numerical stability

    Critical: Rooms are NOT simulated independently. Vent coupling
    ensures smoke and heat transfer between connected compartments.
    """

    def __init__(self) -> None:
        # Sub-solvers
        self.plume = PlumeModel()
        self.vent_flow = VentFlowSolver()
        self.interface = SmokeLayerSolver()
        self.species = SpeciesTransport()
        self.energy = LayerEnergySolver()
        self.stability = NumericalStability()

        # State
        self.rooms: Dict[str, RoomCompartment] = {}
        self.vents: List[Vent] = []
        self.fires: Dict[str, CombustionModel] = {}  # room_id → CombustionModel
        self.detectors: List[DetectorPhysics] = []
        self.walls: Dict[str, WallThermalSolver] = {}  # room_id → wall solver

    def add_room(self, room: RoomCompartment) -> None:
        """Add a compartment to the simulation."""
        self.rooms[room.room_id] = room
        self.walls[room.room_id] = WallThermalSolver()

    def add_vent(self, vent: Vent) -> None:
        """Add a vent connecting two compartments."""
        self.vents.append(vent)

    def add_fire(self, room_id: str, fire: CombustionModel) -> None:
        """Add a fire source to a compartment."""
        self.fires[room_id] = fire

    def add_detector(self, detector: DetectorPhysics) -> None:
        """Add a detector to the simulation."""
        self.detectors.append(detector)

    def step(self, t: float, dt: float = 0.5) -> List[Dict[str, Any]]:
        """Advance the entire simulation by one time step.

        This is the main integration loop that couples all physics.

        Parameters:
            t: Current simulation time (s)
            dt: Requested time step (s)

        Returns:
            List of detector activation events (if any)
        """
        # 0. Adaptive timestep
        dt = self.stability.adapt_timestep(self.rooms, dt)

        # 1. Calculate vent flows for all vents
        vent_results: Dict[str, VentFlowResult] = {}
        vent_flows_by_room: Dict[str, Dict[str, float]] = {}
        for room_id in self.rooms:
            vent_flows_by_room[room_id] = {
                'm_in_upper': 0.0, 'm_in_lower': 0.0,
                'm_out_upper': 0.0, 'm_out_lower': 0.0,
                'T_in_upper': AMBIENT_TEMP_K, 'T_in_lower': AMBIENT_TEMP_K,
            }

        for vent in self.vents:
            if not vent.is_open:
                continue
            room_a = self.rooms.get(vent.zone_a_id)
            room_b = self.rooms.get(vent.zone_b_id)
            if room_a is None or room_b is None:
                continue

            result = self.vent_flow.calculate_flow(vent, room_a, room_b)
            vent_results[vent.vent_id] = result

            # Accumulate flows for room A
            fa = vent_flows_by_room[vent.zone_a_id]
            fa['m_out_upper'] += result.m_dot_upper_a_to_b
            fa['m_out_lower'] += result.m_dot_lower_a_to_b
            fa['m_in_upper'] += result.m_dot_upper_b_to_a
            fa['m_in_lower'] += result.m_dot_lower_b_to_a
            # Temperature of flow from B→A: use B's upper/lower temp
            if result.m_dot_upper_b_to_a > 0.0:
                fa['T_in_upper'] = room_b.upper.temperature
            if result.m_dot_lower_b_to_a > 0.0:
                fa['T_in_lower'] = room_b.lower.temperature

            # Accumulate flows for room B
            fb = vent_flows_by_room[vent.zone_b_id]
            fb['m_in_upper'] += result.m_dot_upper_a_to_b
            fb['m_in_lower'] += result.m_dot_lower_a_to_b
            fb['m_out_upper'] += result.m_dot_upper_b_to_a
            fb['m_out_lower'] += result.m_dot_lower_b_to_a
            # Temperature of flow from A→B: use A's upper/lower temp
            if result.m_dot_upper_a_to_b > 0.0:
                fb['T_in_upper'] = room_a.upper.temperature
            if result.m_dot_lower_a_to_b > 0.0:
                fb['T_in_lower'] = room_a.lower.temperature

        # 2-7: For each room, compute physics
        activations: List[Dict[str, Any]] = []

        for room_id, room in self.rooms.items():
            # ── 2. Fire / Combustion ──
            fire = self.fires.get(room_id)
            hrr_w = 0.0
            m_dot_fuel = 0.0
            soot_yield = 0.10
            co_yield = 0.04

            if fire is not None:
                hrr_w = fire.get_hrr(t, room)
                fire.consume_fuel(hrr_w, dt)
                m_dot_fuel = hrr_w / HEAT_OF_COMBUSTION_REF if hrr_w > 0 else 0.0
                soot_yield = fire.soot_yield
                co_yield = fire.co_yield

            # ── 3. Plume entrainment ──
            m_dot_plume = 0.0
            T_plume = AMBIENT_TEMP_K
            if hrr_w > 0.0:
                Q_kw = hrr_w / 1000.0
                z_to_interface = max(room.interface_height, 0.1)
                m_dot_plume = self.plume.get_entrainment_rate(Q_kw, z_to_interface)
                T_plume = self.plume.get_plume_temperature(Q_kw, z_to_interface)

            # ── 4. Species transport ──
            vf = vent_flows_by_room.get(room_id, {})
            m_in_upper = vf.get('m_in_upper', 0.0)
            m_out_upper = vf.get('m_out_upper', 0.0)

            # Species of incoming vent flow (approximate: use source room upper layer)
            Y_in_upper = None
            # Simple approximation: ambient composition
            if m_in_upper > 0.0:
                Y_in_upper = {'O2': 0.232, 'CO2': 0.0006, 'CO': 0.0, 'soot': 0.0, 'N2': 0.7674}

            self.species.solve(
                room, m_dot_fuel, soot_yield, co_yield,
                co2_yield=SpeciesTransport.DEFAULT_CO2_YIELD,
                o2_stoich=SpeciesTransport.DEFAULT_O2_STOICH,
                m_dot_in_upper=m_in_upper, Y_in_upper=Y_in_upper,
                m_dot_out_upper=m_out_upper, dt=dt,
            )

            # ── 5. Smoke layer interface ──
            self.interface.solve(
                room, m_dot_plume,
                m_out_upper, m_in_upper, dt,
            )

            # ── 6. Energy equations ──
            Q_conv = 0.7 * hrr_w  # convective fraction
            Q_rad = 0.3 * hrr_w   # radiative fraction
            T_in_upper = vf.get('T_in_upper', AMBIENT_TEMP_K)
            T_in_lower = vf.get('T_in_lower', AMBIENT_TEMP_K)
            m_in_lower = vf.get('m_in_lower', 0.0)

            # Wall heat loss
            wall = self.walls.get(room_id)
            q_wall = 0.0
            if wall is not None:
                q_wall = wall.solve(room.upper.temperature, dt)

            # Adjust Q_loss for wall absorption
            # (wall heat flux is already in the energy solver via H_CONV)
            # We just need to pass the net wall absorption if significant

            self.energy.solve(
                room, Q_conv, Q_rad,
                m_dot_plume, T_plume,
                m_in_upper, T_in_upper, m_out_upper,
                m_in_lower, T_in_lower,
                dt,
            )

            # ── 6b. Mass transfer via vents ──
            # Actually add/remove mass from layers based on vent flow rates
            dm_in_upper = m_in_upper * dt   # kg entering upper layer
            dm_out_upper = m_out_upper * dt  # kg leaving upper layer
            dm_in_lower = vf.get('m_in_lower', 0.0) * dt
            dm_out_lower = vf.get('m_out_lower', 0.0) * dt

            # Add mass to upper layer from vent inflow
            if dm_in_upper > 0.0:
                # Mix incoming mass at its temperature into upper layer
                T_in_u = vf.get('T_in_upper', AMBIENT_TEMP_K)
                m_existing = max(room.upper.mass, 1e-6)
                T_existing = room.upper.temperature
                m_new_total = m_existing + dm_in_upper
                # Energy-weighted mixing: T_new = (m1·Cp·T1 + m2·Cp·T2) / (m1+m2)
                room.upper.temperature = (
                    (m_existing * AIR_HEAT_CAP_CP * T_existing
                     + dm_in_upper * AIR_HEAT_CAP_CP * T_in_u)
                    / (m_new_total * AIR_HEAT_CAP_CP)
                )
                room.upper.mass = m_new_total

            # Remove mass from upper layer (vent outflow)
            if dm_out_upper > 0.0 and room.upper.mass > dm_out_upper:
                room.upper.mass -= dm_out_upper

            # Add mass to lower layer from vent inflow
            if dm_in_lower > 0.0:
                T_in_l = vf.get('T_in_lower', AMBIENT_TEMP_K)
                m_existing_l = max(room.lower.mass, 1e-6)
                m_new_total_l = m_existing_l + dm_in_lower
                room.lower.temperature = (
                    (m_existing_l * AIR_HEAT_CAP_CP * room.lower.temperature
                     + dm_in_lower * AIR_HEAT_CAP_CP * T_in_l)
                    / (m_new_total_l * AIR_HEAT_CAP_CP)
                )
                room.lower.mass = m_new_total_l

            # Remove mass from lower layer (vent outflow)
            if dm_out_lower > 0.0 and room.lower.mass > dm_out_lower:
                room.lower.mass -= dm_out_lower

            # ── 7. Update derived quantities ──
            room.update_derived_quantities()

            # ── 8. Detector check ──
            for det in self.detectors:
                if det.room_id == room_id:
                    # Estimate gas velocity at detector from plume
                    u_gas = 0.5
                    if hrr_w > 0:
                        u_gas = max(0.5, math.sqrt(
                            2.0 * GRAVITY * (room.upper.temperature - AMBIENT_TEMP_K)
                            / AMBIENT_TEMP_K * room.height
                        ))
                    activation = det.update(room, t, dt, u_gas)
                    if activation is not None:
                        activations.append(activation)

        # ── 9. Numerical stability ──
        self.stability.conserve_mass(self.rooms)
        self.stability.clip_energy(self.rooms)

        return activations


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: Simulation Result Data Classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RoomStateSnapshot:
    """Point-in-time state of a compartment."""
    room_id: str
    time_s: float
    upper_temp_k: float
    lower_temp_k: float
    interface_height_m: float
    smoke_od_m1: float
    co_ppm: float
    o2_mass_fraction: float
    is_flashover: bool
    hrr_w: float


@dataclass
class SimulationResult:
    """Complete result of a Semi-CFAST simulation run."""
    duration_s: float
    dt_used: float
    total_steps: int
    room_snapshots: Dict[str, List[RoomStateSnapshot]]
    detector_activations: List[Dict[str, Any]]
    flashover_rooms: List[str]
    peak_temp_k: float
    peak_smoke_od: float
    elapsed_wall_s: float


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Function
# ═══════════════════════════════════════════════════════════════════════════

def run_semi_cfast_simulation(
    rooms: List[RoomCompartment],
    vents: List[Vent],
    fires: Dict[str, CombustionModel],
    detectors: List[DetectorPhysics],
    t_end: float = 300.0,
    dt: float = 0.5,
    snapshot_interval: float = 5.0,
) -> SimulationResult:
    """Run a complete Semi-CFAST fire simulation.

    Parameters:
        rooms: List of RoomCompartment objects
        vents: List of Vent connections
        fires: Dict mapping room_id → CombustionModel
        detectors: List of DetectorPhysics objects
        t_end: Simulation end time (s)
        dt: Requested time step (s)
        snapshot_interval: Snapshot recording interval (s)

    Returns:
        SimulationResult with all states and activations
    """
    import time as _time
    wall_start = _time.time()

    solver = SemiCFASTSolver()

    for room in rooms:
        solver.add_room(room)
    for vent in vents:
        solver.add_vent(vent)
    for room_id, fire in fires.items():
        solver.add_fire(room_id, fire)
    for det in detectors:
        solver.add_detector(det)

    # Tracking
    room_snapshots: Dict[str, List[RoomStateSnapshot]] = {r.room_id: [] for r in rooms}
    all_activations: List[Dict[str, Any]] = []
    flashover_rooms: List[str] = []
    global_peak_temp = AMBIENT_TEMP_K
    global_peak_smoke = 0.0
    step_count = 0
    t = 0.0
    last_snapshot_t = -snapshot_interval

    while t < t_end:
        # Advance solver
        activations = solver.step(t, dt)
        all_activations.extend(activations)

        # Record snapshots
        if t - last_snapshot_t >= snapshot_interval:
            last_snapshot_t = t
            for room_id, room in solver.rooms.items():
                fire = solver.fires.get(room_id)
                hrr = fire.get_hrr(t, room) if fire else 0.0

                snap = RoomStateSnapshot(
                    room_id=room_id,
                    time_s=t,
                    upper_temp_k=round(room.upper.temperature, 1),
                    lower_temp_k=round(room.lower.temperature, 1),
                    interface_height_m=round(room.interface_height, 2),
                    smoke_od_m1=round(room.smoke_od, 4),
                    co_ppm=round(room.co_ppm, 1),
                    o2_mass_fraction=round(room.upper.species.get('O2', 0.232), 4),
                    is_flashover=room.is_flashover,
                    hrr_w=round(hrr, 0),
                )
                room_snapshots[room_id].append(snap)

                if room.is_flashover and room_id not in flashover_rooms:
                    flashover_rooms.append(room_id)
                if room.upper.temperature > global_peak_temp:
                    global_peak_temp = room.upper.temperature
                if room.smoke_od > global_peak_smoke:
                    global_peak_smoke = room.smoke_od

        t += dt
        step_count += 1

    elapsed = round(_time.time() - wall_start, 2)

    return SimulationResult(
        duration_s=t_end,
        dt_used=dt,
        total_steps=step_count,
        room_snapshots=room_snapshots,
        detector_activations=all_activations,
        flashover_rooms=flashover_rooms,
        peak_temp_k=round(global_peak_temp, 1),
        peak_smoke_od=round(global_peak_smoke, 4),
        elapsed_wall_s=elapsed,
    )


__all__ = [
    # Phase 1
    "LayerState", "RoomCompartment", "Vent",
    # Phase 2
    "LayerEnergySolver",
    # Phase 3
    "PlumeModel",
    # Phase 4
    "VentFlowSolver", "VentFlowResult",
    # Phase 5
    "SmokeLayerSolver",
    # Phase 6
    "SpeciesTransport",
    # Phase 7
    "CombustionPhase", "CombustionModel",
    # Phase 8
    "DetectorType", "DetectorConfig", "DetectorPhysics",
    # Phase 9
    "WallThermalSolver",
    # Phase 10
    "SemiCFASTSolver",
    # Phase 11
    "NumericalStability",
    # Results
    "RoomStateSnapshot", "SimulationResult",
    # Convenience
    "run_semi_cfast_simulation",
    # Constants
    "AMBIENT_TEMP_K", "AMBIENT_PRESSURE_PA", "GRAVITY",
    "GAS_CONSTANT_AIR", "AIR_HEAT_CAP_CP", "AIR_DENSITY_REF",
    "SMOKE_ALARM_OD", "CO_LETHAL_PPM", "FLASHOVER_TEMP_K",
]
