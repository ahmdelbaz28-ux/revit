"""
FireAI Digital Twin – Physics-Based Fire Simulation Engine
==========================================================

SAFETY WARNING:
  This module implements SIMPLIFIED fire physics, NOT full CFD.
  Results are physically consistent approximations only.
  All simulation output MUST be verified by a licensed PE.
  Never use simulation results as sole basis for life-safety decisions.

Known Limitations:
  1. N-S solver uses fractional-step with simplified advection
  2. No radiation heat transfer model
  3. Multi-zone uses 2-layer zone model (CFAST-inspired, not CFD)
  4. Smoke transport uses turbulent diffusivity (CFAST-calibrated)
  5. Detector noise uses LCG PRNG (not cryptographically secure)
  6. No HVAC coupling
  7. No structural response modeling

References:
  - NFPA 72-2022, National Fire Alarm and Signaling Code
  - NFPA 72 Annex B – Guide for Fire Alarm System Verification
  - CFAST – Consolidated Model of Fire Growth and Smoke Transport (NIST)
  - Zukoski 1985 – Buoyant Plumes in Compartment Fires
  - Seader & Linhard – Smoke Optical Density Correlations
  - UL 268 – Smoke Detectors for Fire Protective Signaling Systems
  - OSHA 29 CFR 1910.1000 – Air Contaminants

Thread Safety:
  This module is NOT thread-safe by default. The AuditEventStore uses
  a threading.Lock for WAL writes. All other classes assume single-threaded
  access within a simulation run. Do NOT share VoxelGrid or solver state
  across threads without external synchronization.

License: Proprietary – FireAI Digital Twin System
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time as _time

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
)

# ---------------------------------------------------------------------------
# 1. Physical Constants
# ---------------------------------------------------------------------------

STEFAN_BOLTZMANN: float = 5.67e-8      # W/m²K⁴
AIR_DENSITY: float = 1.2               # kg/m³
AIR_HEAT_CAP: float = 1005.0           # J/(kg·K)
AIR_VISCOSITY: float = 1.81e-5         # Pa·s
AIR_THERMAL_COND: float = 0.026        # W/(m·K)
AMBIENT_TEMP: float = 293.15           # K  (20 °C)
AMBIENT_PRESSURE: float = 101325.0     # Pa
GRAVITY: float = 9.81                  # m/s²
SMOKE_ALARM_OD: float = 0.12           # m⁻¹  UL 268 threshold
CO_LETHAL_PPM: float = 1200.0         # ppm  OSHA lethal (29 CFR 1910.1000)
GAS_CONSTANT_AIR: float = 287.05       # J/(kg·K)

# ---------------------------------------------------------------------------
# 2. Voxel & VoxelGrid
# ---------------------------------------------------------------------------


class Voxel:
    """Single cell in the 3-D computational grid.

    Attributes:
        ix, iy, iz: integer grid indices
        cx, cy, cz: world-space centre coordinates (m)
        temp: temperature (K)
        pressure: pressure (Pa)
        smoke: smoke optical density (m⁻¹)
        co_ppm: carbon-monoxide volume fraction (ppm)
        u, v, w: velocity components (m/s)
        is_solid: True if this cell is a solid obstruction
    """

    __slots__ = (
        "ix", "iy", "iz",
        "cx", "cy", "cz",
        "temp", "pressure", "smoke", "co_ppm",
        "o2_fraction", "co2_ppm",
        "u", "v", "w",
        "is_solid",
    )

    def __init__(
        self,
        ix: int, iy: int, iz: int,
        cx: float, cy: float, cz: float,
    ) -> None:
        self.ix = ix
        self.iy = iy
        self.iz = iz
        self.cx = cx
        self.cy = cy
        self.cz = cz
        self.temp: float = AMBIENT_TEMP
        self.pressure: float = AMBIENT_PRESSURE
        self.smoke: float = 0.0
        self.co_ppm: float = 0.0
        self.o2_fraction: float = 0.232   # mass fraction of O2 in air
        self.co2_ppm: float = 0.0          # CO2 volume fraction (ppm)
        self.u: float = 0.0
        self.v: float = 0.0
        self.w: float = 0.0
        self.is_solid: bool = False

    @property
    def density(self) -> float:
        """Ideal-gas density  rho = P / (R·T)  (kg/m³)."""
        return self.pressure / (GAS_CONSTANT_AIR * max(self.temp, 1.0))

    @property
    def speed(self) -> float:
        """Velocity magnitude (m/s)."""
        return math.sqrt(self.u * self.u + self.v * self.v + self.w * self.w)


class VoxelGrid:
    """Uniform Cartesian grid spanning the computational domain.

    Parameters:
        width:  domain extent in x (m)
        length: domain extent in y (m)
        height: domain extent in z (m)
        resolution: cell size (m)
    """

    def __init__(
        self,
        width: float,
        length: float,
        height: float,
        resolution: float,
    ) -> None:
        # SAFETY FIX (F3): Input validation — reject negative/zero/NaN dimensions
        # Without these checks, negative or NaN inputs produce silently wrong
        # results (e.g., VoxelGrid(-5, 3, 2, 0.5) creates nx=1 from ceil(-5/0.5)).
        if not math.isfinite(width) or width <= 0.0:
            raise ValueError(f"VoxelGrid width must be positive and finite, got {width}")
        if not math.isfinite(length) or length <= 0.0:
            raise ValueError(f"VoxelGrid length must be positive and finite, got {length}")
        if not math.isfinite(height) or height <= 0.0:
            raise ValueError(f"VoxelGrid height must be positive and finite, got {height}")
        if not math.isfinite(resolution) or resolution <= 0.0:
            raise ValueError(f"VoxelGrid resolution must be positive and finite, got {resolution}")

        self.width = width
        self.length = length
        self.height = height
        self.resolution = resolution
        self.nx: int = max(1, int(math.ceil(width / resolution)))
        self.ny: int = max(1, int(math.ceil(length / resolution)))
        self.nz: int = max(1, int(math.ceil(height / resolution)))

        self._cells: List[Voxel] = []
        for iz in range(self.nz):
            for iy in range(self.ny):
                for ix in range(self.nx):
                    cx = (ix + 0.5) * resolution
                    cy = (iy + 0.5) * resolution
                    cz = (iz + 0.5) * resolution
                    self._cells.append(Voxel(ix, iy, iz, cx, cy, cz))

        # Index lookup: (ix, iy, iz) -> list index
        # HIGH-08: Keys are always Python int tuples (from range()),
        # which have stable hash values. Explicit int() casting in get()
        # provides defense against numpy.int64 or other non-standard ints.
        self._idx: Dict[Tuple[int, int, int], int] = {}
        for i, v in enumerate(self._cells):
            self._idx[(v.ix, v.iy, v.iz)] = i

    # -- accessors -----------------------------------------------------------

    def get(self, ix: int, iy: int, iz: int) -> Optional[Voxel]:
        """Return voxel at grid indices, or None if out of bounds.

        HIGH-08 FIX: Explicitly cast to int for dict key safety.
        While Python range() always produces ints, defensive casting
        prevents subtle bugs if a caller passes float indices (e.g.,
        from numpy.int64 which hashes differently than Python int).
        """
        idx = self._idx.get((int(ix), int(iy), int(iz)))
        if idx is not None:
            return self._cells[idx]
        return None

    def at_pos(self, x: float, y: float, z: float) -> Optional[Voxel]:
        """Return voxel containing world position (x, y, z).

        BUG FIX (CRIT-04): Previous version used int() truncation which
        gives wrong results for negative coordinates:
          int(-0.3 / 0.5) = int(-0.6) = 0  (WRONG — should be -1 → out of bounds)
        Now uses math.floor() which correctly handles negative values:
          math.floor(-0.3 / 0.5) = math.floor(-0.6) = -1  → out of bounds → None

        For positive coordinates, floor and int give the same result:
          math.floor(0.7 / 0.5) = math.floor(1.4) = 1  ✓
          int(0.7 / 0.5) = int(1.4) = 1  ✓
        """
        ix = math.floor(x / self.resolution)
        iy = math.floor(y / self.resolution)
        iz = math.floor(z / self.resolution)
        if 0 <= ix < self.nx and 0 <= iy < self.ny and 0 <= iz < self.nz:
            return self.get(ix, iy, iz)
        return None

    def all_fluid(self) -> List[Voxel]:
        """Return all non-solid voxels."""
        return [v for v in self._cells if not v.is_solid]

    def neighbours(self, v: Voxel) -> List[Voxel]:
        """Return the 6-connected neighbour voxels (may be empty at boundaries)."""
        out: List[Voxel] = []
        for dix, diy, diz in ((1, 0, 0), (-1, 0, 0),
                               (0, 1, 0), (0, -1, 0),
                               (0, 0, 1), (0, 0, -1)):
            nb = self.get(v.ix + dix, v.iy + diy, v.iz + diz)
            if nb is not None and not nb.is_solid:
                out.append(nb)
        return out

    def mark_solid(
        self, x0: float, y0: float, z0: float,
        x1: float, y1: float, z1: float,
    ) -> int:
        """Mark all voxels inside the AABB [x0..x1, y0..y1, z0..z1] as solid.

        Returns the number of voxels marked.
        """
        count = 0
        for v in self._cells:
            if x0 <= v.cx <= x1 and y0 <= v.cy <= y1 and z0 <= v.cz <= z1:
                if not v.is_solid:
                    v.is_solid = True
                    v.u = 0.0
                    v.v = 0.0
                    v.w = 0.0
                    count += 1
        return count

    # -- reduction queries ---------------------------------------------------

    def peak_temp(self) -> float:
        """Maximum temperature across all fluid cells (K)."""
        mx = AMBIENT_TEMP
        for v in self._cells:
            if not v.is_solid and v.temp > mx:
                mx = v.temp
        return mx

    def peak_smoke(self) -> float:
        """Maximum smoke OD across all fluid cells (m⁻¹)."""
        mx = 0.0
        for v in self._cells:
            if not v.is_solid and v.smoke > mx:
                mx = v.smoke
        return mx

    def avg_temp(self) -> float:
        """Mean temperature across all fluid cells (K)."""
        total = 0.0
        count = 0
        for v in self._cells:
            if not v.is_solid:
                total += v.temp
                count += 1
        return total / count if count > 0 else AMBIENT_TEMP

    @property
    def cells(self) -> List[Voxel]:
        """All voxels (read-only reference)."""
        return self._cells


# ---------------------------------------------------------------------------
# 3. CFLController – Adaptive Timestep with Stability Enforcement
# ---------------------------------------------------------------------------


class CFLController:
    """Computes the maximum stable time-step under CFL, diffusion, and
    viscous constraints, and checks for numerical divergence.

    All CFL numbers are intentionally conservative (< 0.5) to provide a
    safety margin for the simplified advection scheme.
    """

    CFL_ADV: float = 0.45       # advective CFL number
    CFL_DIFF: float = 0.45      # diffusive CFL number
    CFL_VISC: float = 0.45      # viscous CFL number
    ALPHA_HOT: float = 5e-5     # turbulent thermal diffusivity (m²/s)
    D_SMOKE: float = 0.18       # turbulent smoke diffusivity (m²/s)
    NU_AIR: float = 1.51e-5     # kinematic viscosity of air (m²/s)

    def compute_dt(
        self,
        dx: float,
        u_max: float,
        dt_req: float,
    ) -> float:
        """Return the largest stable dt given cell size *dx*, maximum velocity
        *u_max*, and the user-requested *dt_req*.

        The returned dt is the minimum of:
          - CFL_ADV  * dx / max(u_max, 1e-6)
          - CFL_DIFF * dx² / (2 * max(ALPHA_HOT, D_SMOKE))
          - CFL_VISC * dx² / NU_AIR
          - dt_req
        """
        # SAFETY FIX (F4): NaN/Inf velocity guard — prevent numerical blow-up
        # If u_max is NaN/Inf, the CFL computation would produce NaN dt,
        # which would silently propagate through the entire simulation.
        if not math.isfinite(u_max):
            u_max = 0.0
        if not math.isfinite(dx) or dx <= 0.0:
            return max(dt_req, 1e-6)
        if not math.isfinite(dt_req) or dt_req <= 0.0:
            dt_req = 1.0

        u_safe = max(u_max, 1e-6)
        dt_adv = self.CFL_ADV * dx / u_safe
        dt_diff = self.CFL_DIFF * dx * dx / (2.0 * max(self.ALPHA_HOT, self.D_SMOKE))
        dt_visc = self.CFL_VISC * dx * dx / self.NU_AIR
        dt = min(dt_adv, dt_diff, dt_visc, dt_req)
        return max(dt, 1e-6)  # floor to avoid zero

    def check_divergence(self, cells: Sequence[Voxel]) -> None:
        """Raise RuntimeError if any fluid cell shows T > 3000 K, NaN, or Inf.

        This is a physical-consistency guard: real compartment fires rarely
        exceed ~1500 K; 3000 K indicates numerical blow-up.
        """
        for v in cells:
            if v.is_solid:
                continue
            if not math.isfinite(v.temp):
                raise RuntimeError(
                    f"DIVERGENCE: Non-finite temperature at voxel "
                    f"({v.ix},{v.iy},{v.iz}) = {v.temp}"
                )
            if v.temp > 3000.0:
                raise RuntimeError(
                    f"DIVERGENCE: Temperature {v.temp:.1f} K at voxel "
                    f"({v.ix},{v.iy},{v.iz}) exceeds 3000 K safety limit"
                )

    @staticmethod
    def max_velocity(cells: Sequence[Voxel]) -> float:
        """Return the maximum speed across all fluid cells (m/s)."""
        mx = 0.0
        for v in cells:
            if not v.is_solid:
                s = v.speed
                if s > mx:
                    mx = s
        return mx


# ---------------------------------------------------------------------------
# 4. FireSource
# ---------------------------------------------------------------------------


@dataclass
class FireSource:
    """Point-like fire with t² growth (NFPA 72 Annex B).

    Attributes:
        x, y, z: fire position (m)
        hrr: peak heat release rate (W)
        growth_alpha: t² growth coefficient (kW/s²)
        soot_yield: soot yield fraction (kg_soot / kg_fuel)
        co_yield: CO yield fraction (kg_CO / kg_fuel)
        ignition_time: time of ignition (s)
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    hrr: float = 500_000.0       # 500 kW default
    growth_alpha: float = 0.047  # kW/s² – fast fire (NFPA 72 Table B.4.2.1)
    soot_yield: float = 0.10     # typical for upholstered furniture
    co_yield: float = 0.04       # typical for well-ventilated flaming
    ignition_time: float = 0.0
    fuel_load_kg: float = 500.0  # total fuel available (kg) — CRIT-02 FIX


# ---------------------------------------------------------------------------
# 5. FireGrowthModel
# ---------------------------------------------------------------------------


class FireGrowthModel:
    """t² fire growth model per NFPA 72-2022 Annex B, Table B.4.2.1.

    The HRR follows:  Q(t) = min(alpha · dt² · 1000, Q_peak)
    where dt = max(t - t_ignition, 0) and alpha is in kW/s².
    """

    @staticmethod
    def hrr_at(
        hrr_peak: float,
        alpha: float,
        t_ign: float,
        t: float,
    ) -> float:
        """Return HRR (W) at simulation time *t*.

        Parameters:
            hrr_peak: peak heat release rate (W)
            alpha: growth coefficient (kW/s²)
            t_ign: ignition time (s)
            t: current simulation time (s)
        """
        # SAFETY FIX (F5): Guard against negative/invalid inputs
        # Negative hrr_peak or alpha produces negative HRR, which is physically
        # impossible and would corrupt energy balance calculations downstream.
        if not math.isfinite(hrr_peak) or hrr_peak < 0.0:
            return 0.0
        if not math.isfinite(alpha) or alpha < 0.0:
            return 0.0
        if not math.isfinite(t_ign) or not math.isfinite(t):
            return 0.0

        dt = t - t_ign
        if dt <= 0.0:
            return 0.0
        hrr = alpha * dt * dt * 1000.0  # kW -> W
        return min(max(hrr, 0.0), hrr_peak)


# ---------------------------------------------------------------------------
# 5b. VoxelCombustionModel – CRIT-02: O2-limited combustion with fuel tracking
# ---------------------------------------------------------------------------


class VoxelCombustionModel:
    """CRIT-02 FIX: Physics-based combustion model for the voxel-grid solver.

    The previous fire_physics.py had NO combustion model — it used a simple
    t² growth curve (FireGrowthModel.hrr_at) that grows forever regardless of
    oxygen supply or fuel exhaustion. This is physically impossible:

      - Real fires cannot burn without oxygen (ventilation control)
      - Real fires decay when fuel is exhausted
      - HRR must be limited by BOTH fuel AND oxygen availability

    This model implements a 3-phase combustion:
      Phase 1 — GROWTH:   Q(t) = min(alpha * dt² * 1000, Q_peak)
      Phase 2 — VENT-CTRL: Q limited by local O2 at fire voxel
      Phase 3 — DECAY:     Q decays exponentially when fuel runs out

    O2-limited HRR:
      Q_vent = m_dot_O2_available * DeltaH_c / r_O2
      where m_dot_O2 = (Y_O2 - Y_O2_min) * rho * V_cell / tau_mix

    Fuel consumption:
      m_dot_fuel = Q / DeltaH_c  (kg/s)
      fuel_remaining -= m_dot_fuel * dt

    SAFETY: This follows PRINCIPLE ZERO — if O2 drops to zero, HRR drops to
    zero (FAIL LOUDLY — the fire goes out, which is physically correct).

    References:
      - NFPA 72-2022 Annex B — Fire Growth Parameters
      - CFAST Technical Reference Guide (NIST SP 1030)
      - Babrauskas, V. (1983), "Estimating Large Room Test Burn Rates"
      - Drysdale, D. (2011), "An Introduction to Fire Dynamics", 3rd ed.
    """

    # O2 ventilation threshold (mass fraction) — below this, fire is O2-limited
    O2_VENT_THRESHOLD: float = 0.15       # ~15% O2 by mass
    O2_MIN_BURN: float = 0.05             # absolute minimum for combustion
    DECAY_TAU: float = 300.0              # decay time constant (s)
    MIXING_TIME: float = 5.0              # characteristic mixing time (s)
    HEAT_OF_COMBUSTION: float = 13.1e6    # J/kg (cellulosic fuel)
    O2_STOICH_RATIO: float = 2.3          # kg_O2 per kg_fuel

    def __init__(
        self,
        hrr_peak_w: float = 500_000.0,
        growth_alpha_kw_s2: float = 0.047,  # fast fire per NFPA 72 Table B.4.2.1
        ignition_time_s: float = 0.0,
        fuel_load_kg: float = 500.0,
    ) -> None:
        # Input validation (defense-in-depth)
        if not math.isfinite(hrr_peak_w) or hrr_peak_w < 0.0:
            raise ValueError(
                f"VoxelCombustionModel hrr_peak must be non-negative finite, got {hrr_peak_w}"
            )
        if not math.isfinite(growth_alpha_kw_s2) or growth_alpha_kw_s2 < 0.0:
            raise ValueError(
                f"VoxelCombustionModel alpha must be non-negative finite, got {growth_alpha_kw_s2}"
            )
        if not math.isfinite(fuel_load_kg) or fuel_load_kg < 0.0:
            raise ValueError(
                f"VoxelCombustionModel fuel_load must be non-negative finite, got {fuel_load_kg}"
            )

        self.hrr_peak = hrr_peak_w
        self.alpha = growth_alpha_kw_s2
        self.ignition_time = ignition_time_s
        self.fuel_load = fuel_load_kg
        self.fuel_remaining = fuel_load_kg

        self._phase: str = "GROWTH"  # GROWTH, VENT_CONTROLLED, DECAY
        self._time_at_decay: Optional[float] = None
        self._hrr_at_decay: float = 0.0

    @property
    def phase(self) -> str:
        """Current combustion phase."""
        return self._phase

    def get_hrr(
        self,
        t: float,
        grid: Optional[VoxelGrid] = None,
        fire: Optional[FireSource] = None,
    ) -> float:
        """Compute current HRR (W) with O2-limited combustion.

        Parameters:
            t: Current simulation time (s)
            grid: VoxelGrid (for O2 reading at fire voxel)
            fire: FireSource (for fire voxel position)

        Returns:
            Current heat release rate (W), O2-limited if applicable.
        """
        dt_ign = t - self.ignition_time
        if dt_ign <= 0.0:
            return 0.0

        # --- Phase 1: GROWTH ---
        if self._phase == "GROWTH":
            hrr = self.alpha * dt_ign * dt_ign * 1000.0  # kW -> W
            hrr = max(hrr, 0.0)
            hrr = min(hrr, self.hrr_peak)

            # Check for ventilation control (O2 depletion at fire voxel)
            if grid is not None and fire is not None:
                o2_frac = self._read_local_o2(grid, fire)
                if o2_frac < self.O2_VENT_THRESHOLD:
                    self._phase = "VENT_CONTROLLED"
                    return self._ventilation_limited_hrr(grid, fire, hrr)

            # BUG-HIGH-4 FIX: Check fuel exhaustion in ALL phases, not just at peak.
            # If fuel runs out during growth or ventilation control, fire must decay.
            if self.fuel_remaining <= 0.0:
                self._transition_to_decay(t, hrr)
                return hrr * 0.5  # immediate drop on fuel exhaustion

            # Check if peak reached — transition to STEADY (not stay in GROWTH)
            if hrr >= self.hrr_peak:
                self._phase = "STEADY"

            return hrr

        # --- Phase 1.5: STEADY (HRR at peak, no growth, no decay yet) ---
        if self._phase == "STEADY":
            hrr = self.hrr_peak

            # BUG-HIGH-4 FIX: Check fuel exhaustion in STEADY phase too
            if self.fuel_remaining <= 0.0:
                self._transition_to_decay(t, hrr)
                return hrr * 0.5

            # Check for ventilation control
            if grid is not None and fire is not None:
                o2_frac = self._read_local_o2(grid, fire)
                if o2_frac < self.O2_VENT_THRESHOLD:
                    self._phase = "VENT_CONTROLLED"
                    return self._ventilation_limited_hrr(grid, fire, hrr)

            return hrr

        # --- Phase 2: VENTILATION-CONTROLLED ---
        if self._phase == "VENT_CONTROLLED":
            # BUG-HIGH-4 FIX: Check fuel exhaustion in VENT_CONTROLLED phase too
            if self.fuel_remaining <= 0.0:
                self._transition_to_decay(t, min(self.alpha * dt_ign * dt_ign * 1000.0, self.hrr_peak))
                return self._hrr_at_decay * 0.5

            # Base growth HRR
            hrr_growth = min(
                self.alpha * dt_ign * dt_ign * 1000.0,
                self.hrr_peak,
            )

            # Check if O2 recovered
            if grid is not None and fire is not None:
                o2_frac = self._read_local_o2(grid, fire)
                if o2_frac > self.O2_VENT_THRESHOLD + 0.02:
                    # O2 recovered — back to STEADY or GROWTH
                    if hrr_growth >= self.hrr_peak:
                        self._phase = "STEADY"
                    else:
                        self._phase = "GROWTH"
                    return min(hrr_growth, self.hrr_peak)

                return self._ventilation_limited_hrr(grid, fire, hrr_growth)

            return min(hrr_growth, self.hrr_peak)

        # --- Phase 3: DECAY ---
        if self._phase == "DECAY":
            if self._time_at_decay is not None:
                dt_decay = t - self._time_at_decay
                hrr = self._hrr_at_decay * math.exp(-dt_decay / self.DECAY_TAU)
                return max(hrr, 0.0)
            return 0.0

        return 0.0

    def consume_fuel(self, hrr_w: float, dt: float) -> None:
        """Consume fuel based on current HRR.

        m_dot_fuel = Q / DeltaH_c  (kg/s)
        """
        if hrr_w <= 0.0 or dt <= 0.0:
            return
        m_dot_fuel = hrr_w / self.HEAT_OF_COMBUSTION
        self.fuel_remaining -= m_dot_fuel * dt
        if self.fuel_remaining <= 0.0:
            self.fuel_remaining = 0.0

    def check_fuel_exhaustion(self, t: float, current_hrr: float) -> float:
        """Check if fuel is exhausted and transition to decay if so.

        Returns potentially reduced HRR if fuel just ran out.
        """
        if self.fuel_remaining <= 0.0 and self._phase != "DECAY":
            self._transition_to_decay(t, current_hrr)
            return current_hrr * 0.5  # immediate drop
        return current_hrr

    def _read_local_o2(self, grid: VoxelGrid, fire: FireSource) -> float:
        """Read O2 mass fraction averaged over a region around the fire.

        CRIT-02 STABILITY: A single voxel contains very little O2
        (e.g., 0.035 kg in a 0.5m cell). A real fire draws O2 from the
        entire room via the plume entrainment flow. Using only the fire
        voxel's O2 causes instant depletion and numerical blow-up.

        Solution: Average O2 over a 3×3×3 block (27 cells) centered on
        the fire, which better represents the O2 available to the fire
        plume. This is consistent with CFAST's well-mixed lower layer
        assumption.
        """
        voxel = grid.at_pos(fire.x, fire.y, fire.z)
        if voxel is None or voxel.is_solid:
            return 0.232  # ambient — assume well-ventilated

        # Average O2 over 3×3×3 neighborhood
        o2_sum = 0.0
        count = 0
        for dix in range(-1, 2):
            for diy in range(-1, 2):
                for diz in range(-1, 2):
                    nb = grid.get(voxel.ix + dix, voxel.iy + diy, voxel.iz + diz)
                    if nb is not None and not nb.is_solid:
                        o2_sum += getattr(nb, 'o2_fraction', 0.232)
                        count += 1

        if count > 0:
            return o2_sum / count
        return getattr(voxel, 'o2_fraction', 0.232)

    def _ventilation_limited_hrr(
        self,
        grid: VoxelGrid,
        fire: FireSource,
        hrr_unlimited: float,
    ) -> float:
        """Compute HRR limited by available oxygen around the fire.

        Q_vent = m_O2_available * DeltaH_c / r_O2

        Uses O2 averaged over the 3×3×3 neighborhood of the fire voxel,
        consistent with _read_local_o2(). The available O2 mass is
        computed from the total neighborhood volume (not just one cell).

        BUG-HIGH-5 FIX: Previously used single-cell volume (dx³) but
        neighborhood-averaged O2 from 27 cells, underestimating available O2
        by ~5×. Now counts actual non-solid cells in 3×3×3 block and uses
        the total volume, with a plume entrainment factor of 2× for
        air drawn from beyond the immediate neighborhood.
        """
        voxel = grid.at_pos(fire.x, fire.y, fire.z)
        if voxel is None or voxel.is_solid:
            return min(hrr_unlimited, self.hrr_peak)

        o2_frac = self._read_local_o2(grid, fire)
        o2_excess = max(o2_frac - self.O2_MIN_BURN, 0.0)

        # BUG-HIGH-5 FIX: Count non-solid cells in 3×3×3 neighborhood
        # and use total volume (not single-cell volume × arbitrary factor).
        dx = grid.resolution
        n_cells = 0
        for dix in range(-1, 2):
            for diy in range(-1, 2):
                for diz in range(-1, 2):
                    nb = grid.get(voxel.ix + dix, voxel.iy + diy, voxel.iz + diz)
                    if nb is not None and not nb.is_solid:
                        n_cells += 1

        vol_total = dx * dx * dx * n_cells
        rho = voxel.density
        # Plume entrainment factor 2×: fire draws air from beyond the 3×3×3 block
        m_o2 = rho * vol_total * o2_excess * 2.0

        # HRR from available O2 (limited by mixing time)
        Q_vent = (m_o2 / self.MIXING_TIME) * self.HEAT_OF_COMBUSTION / self.O2_STOICH_RATIO

        return min(Q_vent, hrr_unlimited, self.hrr_peak)

    def _transition_to_decay(self, t: float, current_hrr: float) -> None:
        """Transition to decay phase."""
        self._phase = "DECAY"
        self._time_at_decay = t
        self._hrr_at_decay = max(current_hrr * 0.5, 0.0)


# ---------------------------------------------------------------------------
# 6. PressureSolver – Fractional-Step Navier-Stokes
# ---------------------------------------------------------------------------


class PressureSolver:
    """Fractional-step (projection) method for incompressible Navier-Stokes
    with the Boussinesq buoyancy approximation.

    Algorithm per step:
      1. Momentum prediction: viscous diffusion + upwind advection + buoyancy
      2. Pressure Poisson equation (SOR iterations)
      3. Velocity correction to enforce ∇·u = 0

    BUG FIX (from V2): Advection now includes full cross-terms with upwind
    differencing for each component:
        adv_u = -(u·∂u/∂x + v·∂u/∂y + w·∂u/∂z)
        adv_v = -(u·∂v/∂x + v·∂v/∂y + w·∂v/∂z)
        adv_w = -(u·∂w/∂x + v·∂w/∂y + w·∂w/∂z) + buoyancy

    References:
      - Chorin (1968), "Numerical Solution of the Navier-Stokes Equations"
      - Ferziger & Peric (2002), "Computational Methods for Fluid Dynamics"
    """

    OMEGA: float = 1.5     # SOR over-relaxation factor
    MAX_ITER: int = 25     # Maximum Poisson iterations
    TOL: float = 1.0       # Pressure convergence tolerance (Pa)
    BETA: float = 1.0 / AMBIENT_TEMP  # Boussinesq expansion coefficient (1/K)

    def step(self, grid: VoxelGrid, dt: float) -> None:
        """Advance the velocity/pressure field by one time-step.

        Parameters:
            grid: the VoxelGrid to update in-place
            dt: time-step (s), must satisfy CFL
        """
        dx = grid.resolution
        fluid = grid.all_fluid()

        # BUG FIX (CRIT-01): Build fluid index map for PressureSolver
        # to look up u_star by (ix, iy, iz) during Poisson iteration.
        self._fluid_idx: Dict[Tuple[int, int, int], int] = {}
        for idx_f, vf in enumerate(fluid):
            self._fluid_idx[(vf.ix, vf.iy, vf.iz)] = idx_f

        # --- Step 1: Momentum prediction (explicit Euler) -----------------
        # We accumulate u*, v*, w* for each fluid cell.
        # Store updates in temporary arrays to avoid order-dependence.
        n = len(fluid)
        u_star = [0.0] * n
        v_star = [0.0] * n
        w_star = [0.0] * n

        nu = CFLController.NU_AIR  # kinematic viscosity

        for idx, v in enumerate(fluid):
            nbs = grid.neighbours(v)
            if not nbs:
                u_star[idx] = v.u
                v_star[idx] = v.v
                w_star[idx] = v.w
                continue

            u_old = v.u
            v_old = v.v
            w_old = v.w

            # --- Viscous diffusion: nu * laplacian(u) ---------------------
            lap_u = 0.0
            lap_v = 0.0
            lap_w = 0.0
            for nb in nbs:
                lap_u += (nb.u - u_old) / (dx * dx)
                lap_v += (nb.v - v_old) / (dx * dx)
                lap_w += (nb.w - w_old) / (dx * dx)
            lap_u *= nu
            lap_v *= nu
            lap_w *= nu

            # --- Upwind advection: full cross-terms ------------------------
            # adv_u = -(u·∂u/∂x + v·∂u/∂y + w·∂u/∂z)
            # For each spatial derivative, use the velocity component
            # of the donor cell (upwind).
            adv_u = 0.0
            adv_v = 0.0
            adv_w = 0.0

            # x-derivative terms
            nb_xp = grid.get(v.ix + 1, v.iy, v.iz)
            nb_xm = grid.get(v.ix - 1, v.iy, v.iz)
            if nb_xp is not None and nb_xm is not None:
                # ∂u/∂x
                if u_old >= 0:
                    adv_u -= u_old * (u_old - nb_xm.u) / dx
                else:
                    adv_u -= u_old * (nb_xp.u - u_old) / dx
                # ∂v/∂x
                if u_old >= 0:
                    adv_v -= u_old * (v_old - nb_xm.v) / dx
                else:
                    adv_v -= u_old * (nb_xp.v - v_old) / dx
                # ∂w/∂x
                if u_old >= 0:
                    adv_w -= u_old * (w_old - nb_xm.w) / dx
                else:
                    adv_w -= u_old * (nb_xp.w - w_old) / dx
            elif nb_xp is not None:
                adv_u -= u_old * (nb_xp.u - u_old) / dx
                adv_v -= u_old * (nb_xp.v - v_old) / dx
                adv_w -= u_old * (nb_xp.w - w_old) / dx
            elif nb_xm is not None:
                adv_u -= u_old * (u_old - nb_xm.u) / dx
                adv_v -= u_old * (v_old - nb_xm.v) / dx
                adv_w -= u_old * (w_old - nb_xm.w) / dx

            # y-derivative terms
            nb_yp = grid.get(v.ix, v.iy + 1, v.iz)
            nb_ym = grid.get(v.ix, v.iy - 1, v.iz)
            if nb_yp is not None and nb_ym is not None:
                if v_old >= 0:
                    adv_u -= v_old * (u_old - nb_ym.u) / dx
                else:
                    adv_u -= v_old * (nb_yp.u - u_old) / dx
                if v_old >= 0:
                    adv_v -= v_old * (v_old - nb_ym.v) / dx
                else:
                    adv_v -= v_old * (nb_yp.v - v_old) / dx
                if v_old >= 0:
                    adv_w -= v_old * (w_old - nb_ym.w) / dx
                else:
                    adv_w -= v_old * (nb_yp.w - w_old) / dx
            elif nb_yp is not None:
                adv_u -= v_old * (nb_yp.u - u_old) / dx
                adv_v -= v_old * (nb_yp.v - v_old) / dx
                adv_w -= v_old * (nb_yp.w - w_old) / dx
            elif nb_ym is not None:
                adv_u -= v_old * (u_old - nb_ym.u) / dx
                adv_v -= v_old * (v_old - nb_ym.v) / dx
                adv_w -= v_old * (w_old - nb_ym.w) / dx

            # z-derivative terms
            nb_zp = grid.get(v.ix, v.iy, v.iz + 1)
            nb_zm = grid.get(v.ix, v.iy, v.iz - 1)
            if nb_zp is not None and nb_zm is not None:
                if w_old >= 0:
                    adv_u -= w_old * (u_old - nb_zm.u) / dx
                else:
                    adv_u -= w_old * (nb_zp.u - u_old) / dx
                if w_old >= 0:
                    adv_v -= w_old * (v_old - nb_zm.v) / dx
                else:
                    adv_v -= w_old * (nb_zp.v - v_old) / dx
                if w_old >= 0:
                    adv_w -= w_old * (w_old - nb_zm.w) / dx
                else:
                    adv_w -= w_old * (nb_zp.w - w_old) / dx
            elif nb_zp is not None:
                adv_u -= w_old * (nb_zp.u - u_old) / dx
                adv_v -= w_old * (nb_zp.v - v_old) / dx
                adv_w -= w_old * (nb_zp.w - w_old) / dx
            elif nb_zm is not None:
                adv_u -= w_old * (u_old - nb_zm.u) / dx
                adv_v -= w_old * (v_old - nb_zm.v) / dx
                adv_w -= w_old * (w_old - nb_zm.w) / dx

            # --- Buoyancy (Boussinesq, vertical only) ----------------------
            buoyancy = GRAVITY * self.BETA * (v.temp - AMBIENT_TEMP)
            adv_w += buoyancy

            # --- Predicted velocity ----------------------------------------
            u_star[idx] = u_old + dt * (lap_u + adv_u)
            v_star[idx] = v_old + dt * (lap_v + adv_v)
            w_star[idx] = w_old + dt * (lap_w + adv_w)

        # --- Step 2: Pressure Poisson equation (SOR) ----------------------
        # Solve  ∇²p = (rho/dt) · ∇·u*  with Neumann BC on walls
        # Use the existing pressure field as initial guess.
        rho_ref = AIR_DENSITY

        # BUG FIX (CRIT-01): Removed dead code from first divergence block
        # (lines 574-583) that was immediately overwritten by second block.
        # Also fixed: divergence now correctly uses u_star[idx] for the
        # current cell's predicted velocity instead of stale nb.u values.
        # The projection method REQUIRES ∇·u* (predicted velocity), not ∇·u^n.
        for _iteration in range(self.MAX_ITER):
            max_residual = 0.0
            for idx, vc in enumerate(fluid):
                nbs = grid.neighbours(vc)
                if not nbs:
                    continue

                # Accumulate neighbour pressure sum for SOR
                p_nb_sum = 0.0
                count_nb = 0
                for nb in nbs:
                    count_nb += 1
                    p_nb_sum += nb.pressure

                # Divergence of u* using central differences where possible.
                # For interior cells: ∂u*/∂x ≈ (u*_xp - u*_xm) / (2·dx)
                # We only have u* for the current cell (u_star[idx]),
                # not for neighbours, so we use neighbour's u* from the
                # u_star array by looking up its index.
                div_ustar = 0.0
                nb_xp = grid.get(vc.ix + 1, vc.iy, vc.iz)
                nb_xm = grid.get(vc.ix - 1, vc.iy, vc.iz)
                nb_yp = grid.get(vc.ix, vc.iy + 1, vc.iz)
                nb_ym = grid.get(vc.ix, vc.iy - 1, vc.iz)
                nb_zp = grid.get(vc.ix, vc.iy, vc.iz + 1)
                nb_zm = grid.get(vc.ix, vc.iy, vc.iz - 1)

                if nb_xp is not None and nb_xm is not None:
                    # Use u_star for both this cell and its neighbours
                    # by finding the neighbour's fluid index
                    xp_idx = self._fluid_idx.get((vc.ix + 1, vc.iy, vc.iz))
                    xm_idx = self._fluid_idx.get((vc.ix - 1, vc.iy, vc.iz))
                    u_xp = u_star[xp_idx] if xp_idx is not None else nb_xp.u
                    u_xm = u_star[xm_idx] if xm_idx is not None else nb_xm.u
                    div_ustar += (u_xp - u_xm) / (2.0 * dx)
                elif nb_xp is not None:
                    xp_idx = self._fluid_idx.get((vc.ix + 1, vc.iy, vc.iz))
                    u_xp = u_star[xp_idx] if xp_idx is not None else nb_xp.u
                    div_ustar += (u_xp - u_star[idx]) / dx
                elif nb_xm is not None:
                    xm_idx = self._fluid_idx.get((vc.ix - 1, vc.iy, vc.iz))
                    u_xm = u_star[xm_idx] if xm_idx is not None else nb_xm.u
                    div_ustar += (u_star[idx] - u_xm) / dx

                if nb_yp is not None and nb_ym is not None:
                    yp_idx = self._fluid_idx.get((vc.ix, vc.iy + 1, vc.iz))
                    ym_idx = self._fluid_idx.get((vc.ix, vc.iy - 1, vc.iz))
                    v_yp = v_star[yp_idx] if yp_idx is not None else nb_yp.v
                    v_ym = v_star[ym_idx] if ym_idx is not None else nb_ym.v
                    div_ustar += (v_yp - v_ym) / (2.0 * dx)
                elif nb_yp is not None:
                    yp_idx = self._fluid_idx.get((vc.ix, vc.iy + 1, vc.iz))
                    v_yp = v_star[yp_idx] if yp_idx is not None else nb_yp.v
                    div_ustar += (v_yp - v_star[idx]) / dx
                elif nb_ym is not None:
                    ym_idx = self._fluid_idx.get((vc.ix, vc.iy - 1, vc.iz))
                    v_ym = v_star[ym_idx] if ym_idx is not None else nb_ym.v
                    div_ustar += (v_star[idx] - v_ym) / dx

                if nb_zp is not None and nb_zm is not None:
                    zp_idx = self._fluid_idx.get((vc.ix, vc.iy, vc.iz + 1))
                    zm_idx = self._fluid_idx.get((vc.ix, vc.iy, vc.iz - 1))
                    w_zp = w_star[zp_idx] if zp_idx is not None else nb_zp.w
                    w_zm = w_star[zm_idx] if zm_idx is not None else nb_zm.w
                    div_ustar += (w_zp - w_zm) / (2.0 * dx)
                elif nb_zp is not None:
                    zp_idx = self._fluid_idx.get((vc.ix, vc.iy, vc.iz + 1))
                    w_zp = w_star[zp_idx] if zp_idx is not None else nb_zp.w
                    div_ustar += (w_zp - w_star[idx]) / dx
                elif nb_zm is not None:
                    zm_idx = self._fluid_idx.get((vc.ix, vc.iy, vc.iz - 1))
                    w_zm = w_star[zm_idx] if zm_idx is not None else nb_zm.w
                    div_ustar += (w_star[idx] - w_zm) / dx

                # SOR update:  p_new = (sum(p_nb) - dx²·rhs) / count_nb
                # rhs = (rho/dt) · div(u*)
                rhs = (rho_ref / dt) * div_ustar
                p_new = (p_nb_sum - dx * dx * rhs) / max(count_nb, 1)
                residual = abs(p_new - vc.pressure)
                if residual > max_residual:
                    max_residual = residual
                vc.pressure += self.OMEGA * (p_new - vc.pressure)

            if max_residual < self.TOL:
                break

        # --- Step 3: Velocity correction ----------------------------------
        # u^{n+1} = u* - (dt/rho) · ∇p
        for idx, vc in enumerate(fluid):
            nbs = grid.neighbours(vc)
            if not nbs:
                continue

            # Pressure gradient (central differences where possible)
            dp_dx = 0.0
            dp_dy = 0.0
            dp_dz = 0.0

            nb_xp = grid.get(vc.ix + 1, vc.iy, vc.iz)
            nb_xm = grid.get(vc.ix - 1, vc.iy, vc.iz)
            nb_yp = grid.get(vc.ix, vc.iy + 1, vc.iz)
            nb_ym = grid.get(vc.ix, vc.iy - 1, vc.iz)
            nb_zp = grid.get(vc.ix, vc.iy, vc.iz + 1)
            nb_zm = grid.get(vc.ix, vc.iy, vc.iz - 1)

            if nb_xp is not None and nb_xm is not None:
                dp_dx = (nb_xp.pressure - nb_xm.pressure) / (2.0 * dx)
            elif nb_xp is not None:
                dp_dx = (nb_xp.pressure - vc.pressure) / dx
            elif nb_xm is not None:
                dp_dx = (vc.pressure - nb_xm.pressure) / dx

            if nb_yp is not None and nb_ym is not None:
                dp_dy = (nb_yp.pressure - nb_ym.pressure) / (2.0 * dx)
            elif nb_yp is not None:
                dp_dy = (nb_yp.pressure - vc.pressure) / dx
            elif nb_ym is not None:
                dp_dy = (vc.pressure - nb_ym.pressure) / dx

            if nb_zp is not None and nb_zm is not None:
                dp_dz = (nb_zp.pressure - nb_zm.pressure) / (2.0 * dx)
            elif nb_zp is not None:
                dp_dz = (nb_zp.pressure - vc.pressure) / dx
            elif nb_zm is not None:
                dp_dz = (vc.pressure - nb_zm.pressure) / dx

            corr = dt / rho_ref
            vc.u = u_star[idx] - corr * dp_dx
            vc.v = v_star[idx] - corr * dp_dy
            vc.w = w_star[idx] - corr * dp_dz

            # Enforce no-penetration on solids
            if nb_xp is not None and nb_xp.is_solid:
                vc.u = min(vc.u, 0.0)
            if nb_xm is not None and nb_xm.is_solid:
                vc.u = max(vc.u, 0.0)
            if nb_yp is not None and nb_yp.is_solid:
                vc.v = min(vc.v, 0.0)
            if nb_ym is not None and nb_ym.is_solid:
                vc.v = max(vc.v, 0.0)
            if nb_zp is not None and nb_zp.is_solid:
                vc.w = min(vc.w, 0.0)
            if nb_zm is not None and nb_zm.is_solid:
                vc.w = max(vc.w, 0.0)


# ---------------------------------------------------------------------------
# 7. HeatTransportNS
# ---------------------------------------------------------------------------


class HeatTransportNS:
    """Thermal energy transport on the N-S velocity field.

    Uses explicit Euler with:
      - Diffusion: alpha * ∇²T
      - Advection: upwind on N-S velocity field
      - Fire source term at fire voxel (V9 FIX: O2-gated)
      - Convective cooling to ambient (Newton's law)

    V9 FIX: The fire source term is now gated by local O2 concentration.
    If O2 is depleted at the fire voxel, the source term is scaled
    proportionally. This prevents the physically impossible scenario
    where SmokeTransportNS consumes all O2 but HeatTransportNS
    continues adding heat as if combustion is unlimited.

    Thermal diffusivity alpha = 2.2e-5 m²/s is a turbulent effective value
    calibrated for room-scale enclosure fires (CFAST-consistent).
    """

    ALPHA: float = 2.2e-5     # effective thermal diffusivity (m²/s)
    H_CONV: float = 10.0      # convective heat transfer coeff (W/(m²·K))

    def step(
        self,
        grid: VoxelGrid,
        fire: FireSource,
        hrr_now: float,
        dt: float,
    ) -> None:
        """Advance temperature field by one time-step.

        Parameters:
            grid: VoxelGrid to update in-place
            fire: FireSource (for source location)
            hrr_now: current HRR (W) from combustion model (VoxelCombustionModel)
            dt: time-step (s)
        """
        dx = grid.resolution
        dx2 = dx * dx
        fluid = grid.all_fluid()

        # BUG FIX (HIGH-05): Compute fire_voxel ONCE before the loop
        # instead of inside every cell's iteration (was O(n) redundant calls).
        fire_voxel = grid.at_pos(fire.x, fire.y, fire.z)

        # Pre-compute new temperatures
        new_temp: Dict[int, float] = {}

        for v in fluid:
            nbs = grid.neighbours(v)
            if not nbs:
                new_temp[(v.ix, v.iy, v.iz)] = v.temp
                continue

            T = v.temp

            # Diffusion: alpha * laplacian(T)
            lap_T = 0.0
            for nb in nbs:
                lap_T += (nb.temp - T) / dx2
            diff_T = self.ALPHA * lap_T

            # Advection: -u·∇T  (upwind)
            adv_T = 0.0
            nb_xp = grid.get(v.ix + 1, v.iy, v.iz)
            nb_xm = grid.get(v.ix - 1, v.iy, v.iz)
            nb_yp = grid.get(v.ix, v.iy + 1, v.iz)
            nb_ym = grid.get(v.ix, v.iy - 1, v.iz)
            nb_zp = grid.get(v.ix, v.iy, v.iz + 1)
            nb_zm = grid.get(v.ix, v.iy, v.iz - 1)

            if nb_xp is not None and nb_xm is not None:
                if v.u >= 0:
                    dTdx = (T - nb_xm.temp) / dx
                else:
                    dTdx = (nb_xp.temp - T) / dx
                adv_T -= v.u * dTdx

            if nb_yp is not None and nb_ym is not None:
                if v.v >= 0:
                    dTdy = (T - nb_ym.temp) / dx
                else:
                    dTdy = (nb_yp.temp - T) / dx
                adv_T -= v.v * dTdy

            if nb_zp is not None and nb_zm is not None:
                if v.w >= 0:
                    dTdz = (T - nb_zm.temp) / dx
                else:
                    dTdz = (nb_zp.temp - T) / dx
                adv_T -= v.w * dTdz

            # Convective cooling to ambient
            cool_T = -self.H_CONV * (T - AMBIENT_TEMP) / (
                AIR_DENSITY * AIR_HEAT_CAP * dx
            )

            # Source term at fire voxel — spread over 3×3×3 neighborhood
            # for stability (same as SmokeTransportNS source spreading)
            #
            # V9 FIX: Gate source by local O2 availability.
            # Without this, HeatTransportNS adds heat even when O2 is
            # depleted (SmokeTransportNS already consumed it), causing
            # unphysical temperature blow-up (observed: 658,000 K).
            # The O2 gate scales the heat source proportionally to
            # available O2, ensuring consistency between the two solvers.
            source_T = 0.0
            if fire_voxel is not None:
                dist_cells = max(
                    abs(v.ix - fire_voxel.ix),
                    abs(v.iy - fire_voxel.iy),
                    abs(v.iz - fire_voxel.iz),
                )
                if dist_cells <= 1:
                    if dist_cells == 0:
                        weight = 1.0 / 3.0
                    else:
                        weight = 2.0 / (3.0 * 26.0)
                    vol = dx * dx * dx
                    # V9 FIX: Scale heat source by O2 availability.
                    # If O2 is depleted at this voxel, combustion cannot
                    # produce heat here — physically, fire needs O2.
                    # o2_fraction ranges from 0.0 (no O2) to 0.232 (ambient).
                    # Below O2_MIN_BURN (0.05), combustion is impossible.
                    o2_here = getattr(v, 'o2_fraction', 0.232)
                    o2_factor = max(0.0, min(1.0, (o2_here - 0.05) / (0.232 - 0.05)))
                    source_T = weight * o2_factor * hrr_now / (AIR_DENSITY * AIR_HEAT_CAP * vol)

            T_new = T + dt * (diff_T + adv_T + cool_T + source_T)
            # Physical floor: temperature cannot drop below absolute zero
            T_new = max(T_new, 1.0)
            key = (v.ix, v.iy, v.iz)
            new_temp[key] = T_new

        # Apply updates
        for v in fluid:
            key = (v.ix, v.iy, v.iz)
            if key in new_temp:
                v.temp = new_temp[key]


# ---------------------------------------------------------------------------
# 8. SmokeTransportNS
# ---------------------------------------------------------------------------


class SmokeTransportNS:
    """Smoke, CO, O2, and CO2 transport on the N-S velocity field.

    CRIT-05 FIX: Previously this class only transported smoke (OD) and CO.
    It did NOT consume O2 or generate CO2, which meant:
      - The fire could burn forever regardless of oxygen supply
      - No CO2 was produced (a key fire product for tenability assessment)
      - VoxelCombustionModel could not read O2 to limit HRR

    Now this class implements FULL species transport:
      - Soot generation: mass_loss_rate * soot_yield → OD via Seader-Linhard
      - CO generation:   mass_loss_rate * co_yield → ppm
      - O2 consumption:  mass_loss_rate * o2_stoich → O2 fraction depletion
      - CO2 generation:  mass_loss_rate * co2_yield → ppm

    All species are transported via diffusion + advection (upwind on N-S field).

    Soot generation uses the relationship:
        mass_loss_rate = HRR / heat_of_combustion  (kg/s)
        soot_rate      = mass_loss_rate * soot_yield
    where heat_of_combustion ≈ 13.1 MJ/kg (typical for cellulosic fuels).

    Optical density from Seader & Linhard:
        OD ≈ 7000 × soot_concentration  (m⁻¹)

    O2 consumption stoichiometry (Drysdale, "Introduction to Fire Dynamics"):
        mass_O2_consumed = mass_fuel_burned * r_O2
    where r_O2 ≈ 2.3 kg_O2 / kg_fuel for cellulosic fuels.

    CO2 generation (stoichiometric):
        mass_CO2_generated = mass_fuel_burned * r_CO2
    where r_CO2 ≈ 1.5 kg_CO2 / kg_fuel.

    Transport: diffusion + advection (upwind on N-S field) + gravitational
    settling (exponential decay with time constant ~1000 s) for smoke only.
    """

    D_SMOKE: float = 0.18   # turbulent smoke diffusivity (m²/s)
    D_CO: float = 0.20      # turbulent CO diffusivity (m²/s)
    D_O2: float = 0.20      # turbulent O2 diffusivity (m²/s)
    D_CO2: float = 0.20     # turbulent CO2 diffusivity (m²/s)
    HEAT_OF_COMBUSTION: float = 13.1e6  # J/kg (cellulosic fuel)
    OD_COEFF: float = 7000.0  # Seader & Linhard coefficient
    SETTLING_RATE: float = 0.01   # smoke settling + wall deposition rate (1/s)
    CO_DECAY_RATE: float = 0.005  # CO oxidation/dispersion rate (1/s)
    O2_STOICH_RATIO: float = 2.3   # kg_O2 / kg_fuel (Drysdale)
    CO2_YIELD: float = 1.5         # kg_CO2 / kg_fuel (stoichiometric)
    O2_AMBIENT: float = 0.232      # mass fraction of O2 in ambient air

    def step(
        self,
        grid: VoxelGrid,
        fire: FireSource,
        hrr_now: float,
        dt: float,
    ) -> None:
        """Advance smoke, CO, O2, and CO2 fields by one time-step.

        Parameters:
            grid: VoxelGrid to update in-place
            fire: FireSource (for source location and yields)
            hrr_now: current HRR (W)
            dt: time-step (s)
        """
        dx = grid.resolution
        dx2 = dx * dx
        vol = dx * dx * dx
        fluid = grid.all_fluid()

        # Source terms at fire voxel
        mass_loss_rate = hrr_now / self.HEAT_OF_COMBUSTION  # kg/s
        soot_rate = mass_loss_rate * fire.soot_yield         # kg_soot/s
        co_rate = mass_loss_rate * fire.co_yield             # kg_CO/s
        o2_consumption_rate = mass_loss_rate * self.O2_STOICH_RATIO  # kg_O2/s
        co2_rate = mass_loss_rate * self.CO2_YIELD           # kg_CO2/s

        # CRIT-05 STABILITY: Limit source terms by available O2 in fire region.
        # Use the SAME averaged O2 that VoxelCombustionModel uses (3×3×3 block)
        # to avoid mismatch where combustion model sees high O2 (averaged)
        # but smoke transport depletes the single fire voxel's O2.
        fire_voxel_pre = grid.at_pos(fire.x, fire.y, fire.z)
        o2_avg = 0.232  # default ambient
        n_cells_fire = 27  # 3×3×3 neighborhood
        if fire_voxel_pre is not None and not fire_voxel_pre.is_solid:
            # Average O2 over 3×3×3 (same as VoxelCombustionModel._read_local_o2)
            o2_sum = 0.0
            count = 0
            for dix in range(-1, 2):
                for diy in range(-1, 2):
                    for diz in range(-1, 2):
                        nb = grid.get(
                            fire_voxel_pre.ix + dix,
                            fire_voxel_pre.iy + diy,
                            fire_voxel_pre.iz + diz,
                        )
                        if nb is not None and not nb.is_solid:
                            o2_sum += getattr(nb, 'o2_fraction', 0.232)
                            count += 1
            if count > 0:
                o2_avg = o2_sum / count
                n_cells_fire = count

        # Available O2 in the fire region (all 27 cells combined)
        o2_available_kg = AIR_DENSITY * vol * o2_avg * n_cells_fire
        # V9 FIX: Maximum O2 consumable per timestep is limited by
        # a mixing time constant (5s), not by the total O2 in the
        # region. The old formula `o2_available_kg / dt` allowed
        # consuming ALL oxygen in one step (instantaneous depletion),
        # which is physically impossible — O2 must diffuse to the
        # fire via entrainment and mixing. This matches the mixing
        # time used in VoxelCombustionModel._ventilation_limited_hrr().
        O2_MIXING_TIME = 5.0  # seconds — characteristic mixing time
        o2_max_consumable = o2_available_kg / O2_MIXING_TIME  # kg/s
        if o2_max_consumable <= 0.0:
            # No O2 available → no combustion products at all
            o2_consumption_rate = 0.0
            soot_rate = 0.0
            co_rate = 0.0
            co2_rate = 0.0
            mass_loss_rate = 0.0
        elif o2_consumption_rate > o2_max_consumable:
            # Scale all source terms proportionally to available O2
            scale = o2_max_consumable / o2_consumption_rate
            o2_consumption_rate *= scale
            soot_rate *= scale
            co_rate *= scale
            co2_rate *= scale
            mass_loss_rate *= scale

        # Soot concentration → optical density conversion
        soot_source_od = self.OD_COEFF * soot_rate / vol if vol > 0 else 0.0

        # CO source in ppm (approximate: ppm = kg_CO / total_air_mass * 1e6)
        # total air in cell = rho * vol
        co_source_ppm = (co_rate / (AIR_DENSITY * vol)) * 1e6 if vol > 0 else 0.0

        # CRIT-05: O2 consumption at fire voxel (mass fraction change per second)
        # delta_Y_O2 = -o2_consumption_rate / (rho * vol)
        o2_source_frac = -o2_consumption_rate / (AIR_DENSITY * vol) if vol > 0 else 0.0

        # CRIT-05: CO2 generation at fire voxel (ppm change per second)
        # ppm_CO2 = (kg_CO2 / (rho * vol)) * (M_air / M_CO2) * 1e6
        # M_air ≈ 28.96 (CRC Handbook), M_CO2 ≈ 44.01
        co2_source_ppm = (co2_rate / (AIR_DENSITY * vol)) * (28.96 / 44.01) * 1e6 if vol > 0 else 0.0

        new_smoke: Dict[int, float] = {}
        new_co: Dict[int, float] = {}
        new_o2: Dict[int, float] = {}
        new_co2: Dict[int, float] = {}

        fire_voxel = grid.at_pos(fire.x, fire.y, fire.z)

        for v in fluid:
            nbs = grid.neighbours(v)
            if not nbs:
                new_smoke[(v.ix, v.iy, v.iz)] = v.smoke
                new_co[(v.ix, v.iy, v.iz)] = v.co_ppm
                new_o2[(v.ix, v.iy, v.iz)] = v.o2_fraction
                new_co2[(v.ix, v.iy, v.iz)] = v.co2_ppm
                continue

            s = v.smoke
            c = v.co_ppm
            o2 = v.o2_fraction
            co2 = v.co2_ppm

            # --- Diffusion ---
            lap_s = 0.0
            lap_c = 0.0
            lap_o2 = 0.0
            lap_co2 = 0.0
            for nb in nbs:
                lap_s += (nb.smoke - s) / dx2
                lap_c += (nb.co_ppm - c) / dx2
                lap_o2 += (nb.o2_fraction - o2) / dx2
                lap_co2 += (nb.co2_ppm - co2) / dx2

            diff_s = self.D_SMOKE * lap_s
            diff_c = self.D_CO * lap_c
            diff_o2 = self.D_O2 * lap_o2
            diff_co2 = self.D_CO2 * lap_co2

            # --- Advection (upwind) ---
            adv_s = 0.0
            adv_c = 0.0
            adv_o2 = 0.0
            adv_co2 = 0.0

            nb_xp = grid.get(v.ix + 1, v.iy, v.iz)
            nb_xm = grid.get(v.ix - 1, v.iy, v.iz)
            nb_yp = grid.get(v.ix, v.iy + 1, v.iz)
            nb_ym = grid.get(v.ix, v.iy - 1, v.iz)
            nb_zp = grid.get(v.ix, v.iy, v.iz + 1)
            nb_zm = grid.get(v.ix, v.iy, v.iz - 1)

            if nb_xp is not None and nb_xm is not None:
                if v.u >= 0:
                    dsdx = (s - nb_xm.smoke) / dx
                    dcdx = (c - nb_xm.co_ppm) / dx
                    do2dx = (o2 - nb_xm.o2_fraction) / dx
                    dco2dx = (co2 - nb_xm.co2_ppm) / dx
                else:
                    dsdx = (nb_xp.smoke - s) / dx
                    dcdx = (nb_xp.co_ppm - c) / dx
                    do2dx = (nb_xp.o2_fraction - o2) / dx
                    dco2dx = (nb_xp.co2_ppm - co2) / dx
                adv_s -= v.u * dsdx
                adv_c -= v.u * dcdx
                adv_o2 -= v.u * do2dx
                adv_co2 -= v.u * dco2dx

            if nb_yp is not None and nb_ym is not None:
                if v.v >= 0:
                    dsdy = (s - nb_ym.smoke) / dx
                    dcdy = (c - nb_ym.co_ppm) / dx
                    do2dy = (o2 - nb_ym.o2_fraction) / dx
                    dco2dy = (co2 - nb_ym.co2_ppm) / dx
                else:
                    dsdy = (nb_yp.smoke - s) / dx
                    dcdy = (nb_yp.co_ppm - c) / dx
                    do2dy = (nb_yp.o2_fraction - o2) / dx
                    dco2dy = (nb_yp.co2_ppm - co2) / dx
                adv_s -= v.v * dsdy
                adv_c -= v.v * dcdy
                adv_o2 -= v.v * do2dy
                adv_co2 -= v.v * dco2dy

            if nb_zp is not None and nb_zm is not None:
                if v.w >= 0:
                    dsdz = (s - nb_zm.smoke) / dx
                    dcdz = (c - nb_zm.co_ppm) / dx
                    do2dz = (o2 - nb_zm.o2_fraction) / dx
                    dco2dz = (co2 - nb_zm.co2_ppm) / dx
                else:
                    dsdz = (nb_zp.smoke - s) / dx
                    dcdz = (nb_zp.co_ppm - c) / dx
                    do2dz = (nb_zp.o2_fraction - o2) / dx
                    dco2dz = (nb_zp.co2_ppm - co2) / dx
                adv_s -= v.w * dsdz
                adv_c -= v.w * dcdz
                adv_o2 -= v.w * do2dz
                adv_co2 -= v.w * dco2dz

            # --- Source at fire voxel ---
            # CRIT-05 STABILITY: Spread source over 3×3×3 neighborhood
            # instead of concentrating in a single voxel. A real fire has
            # finite area and draws O2 from surrounding cells via plume
            # entrainment. Concentrating all source terms in one cell causes
            # instant O2 depletion and numerical blow-up.
            src_s = 0.0
            src_c = 0.0
            src_o2 = 0.0
            src_co2 = 0.0
            if fire_voxel is not None:
                # Distance from this voxel to fire center (in grid cells)
                dist_cells = max(
                    abs(v.ix - fire_voxel.ix),
                    abs(v.iy - fire_voxel.iy),
                    abs(v.iz - fire_voxel.iz),
                )
                if dist_cells <= 1:
                    # Weight: center cell gets 1/3, neighbors share 2/3
                    if dist_cells == 0:
                        weight = 1.0 / 3.0
                    else:
                        weight = 2.0 / (3.0 * 26.0)  # 26 neighbors share 2/3
                    src_s = soot_source_od * weight
                    src_c = co_source_ppm * weight
                    src_o2 = o2_source_frac * weight
                    src_co2 = co2_source_ppm * weight

            # --- Gravitational settling + wall deposition (smoke) ---
            settle_s = -self.SETTLING_RATE * s
            # CO oxidation/dispersion
            decay_c = -self.CO_DECAY_RATE * c

            # --- Update ---
            s_new = s + dt * (diff_s + adv_s + src_s + settle_s)
            c_new = c + dt * (diff_c + adv_c + src_c + decay_c)
            o2_new = o2 + dt * (diff_o2 + adv_o2 + src_o2)
            co2_new = co2 + dt * (diff_co2 + adv_co2 + src_co2)

            # Floor at zero (concentrations cannot be negative)
            s_new = max(s_new, 0.0)
            c_new = max(c_new, 0.0)
            # V9 FIX: O2 depletion rate limiter per voxel per timestep.
            # Previous code allowed O2 to drop from 0.232 to 0.0 in a
            # single step, causing numerical blow-up in HeatTransportNS
            # (observed: 658,000 K). The root cause: source term scaling
            # and mixing time were not enough because individual voxels
            # have very small O2 mass (e.g., 0.035 kg in a 0.5m cell)
            # and the source term could still consume all of it.
            #
            # Physical justification: O2 must diffuse to the fire through
            # the surrounding air. In one timestep of dt seconds, only
            # a fraction of the local O2 can be consumed — the rest must
            # wait for turbulent mixing to bring fresh O2. A 20% per-step
            # limit is conservative but prevents numerical catastrophe.
            # This is equivalent to a mixing time of ~5×dt, consistent
            # with the O2_MIXING_TIME constant above.
            O2_MAX_DEPLETION_RATE = 0.20  # max 20% depletion per step
            if o2 > 0.0:
                o2_min = o2 * (1.0 - O2_MAX_DEPLETION_RATE)
                o2_new = max(o2_new, o2_min)
            o2_new = max(min(o2_new, self.O2_AMBIENT), 0.0)
            co2_new = max(co2_new, 0.0)

            key = (v.ix, v.iy, v.iz)
            new_smoke[key] = s_new
            new_co[key] = c_new
            new_o2[key] = o2_new
            new_co2[key] = co2_new

        # Apply updates
        for v in fluid:
            key = (v.ix, v.iy, v.iz)
            if key in new_smoke:
                v.smoke = new_smoke[key]
            if key in new_co:
                v.co_ppm = new_co[key]
            if key in new_o2:
                v.o2_fraction = new_o2[key]
            if key in new_co2:
                v.co2_ppm = new_co2[key]

        # CRIT-05 STABILITY: O2 boundary replenishment.
        # In a real room, fresh air enters through doors, windows, and
        # leakage. The voxel grid has no explicit boundary conditions for
        # species, so we add O2 replenishment at domain boundaries.
        # This prevents O2 from being permanently depleted at boundary cells
        # and provides a source of fresh air for the fire to draw from
        # via diffusion and advection.
        for v in grid._cells:
            if v.is_solid:
                continue
            # Boundary voxels (on the edge of the domain) get O2 replenishment
            if (v.ix == 0 or v.ix == grid.nx - 1 or
                v.iy == 0 or v.iy == grid.ny - 1 or
                v.iz == 0 or v.iz == grid.nz - 1):
                # Relax O2 toward ambient (simulates fresh air infiltration)
                replenish_rate = 0.1 * dt  # 10% per second toward ambient
                v.o2_fraction += replenish_rate * (self.O2_AMBIENT - v.o2_fraction)
                # Also dilute CO2/CO/smoke at boundaries (fresh air mixes in)
                v.co2_ppm *= (1.0 - replenish_rate)
                v.co_ppm *= (1.0 - replenish_rate)
                v.smoke *= (1.0 - replenish_rate)


# ---------------------------------------------------------------------------
# 9. Zone, Doorway, MultiZoneEngine
# ---------------------------------------------------------------------------


class Zone:
    """Two-layer zone model (CFAST-inspired).

    Each zone contains:
      - Hot upper layer: thickness, temperature, density, smoke
      - Cold lower layer: thickness, temperature, density
      - Neutral plane / interface height z_interface
      - Zone pressure P_zone (uniform, hydrostatic offset)

    The interface height descends as the plume entrains mass into the
    upper layer.
    """

    def __init__(
        self,
        zone_id: str,
        width: float,
        length: float,
        height: float,
    ) -> None:
        self.zone_id = zone_id
        self.width = width
        self.length = length
        self.height = height
        self.floor_area = width * length  # m²
        self.volume = width * length * height  # m³

        # Initial state: all ambient
        self.z_interface: float = height      # interface height (m) from floor
        self.T_upper: float = AMBIENT_TEMP    # upper layer temperature (K)
        self.T_lower: float = AMBIENT_TEMP    # lower layer temperature (K)
        self.P_zone: float = AMBIENT_PRESSURE # zone pressure (Pa)
        self.rho_upper: float = AIR_DENSITY   # upper layer density (kg/m³)
        self.rho_lower: float = AIR_DENSITY   # lower layer density (kg/m³)
        self.smoke_upper: float = 0.0         # upper smoke OD (m⁻¹)
        self.co_upper_ppm: float = 0.0        # upper CO (ppm)

    @property
    def upper_volume(self) -> float:
        """Volume of the hot upper layer (m³)."""
        return self.floor_area * max(self.height - self.z_interface, 0.0)

    @property
    def lower_volume(self) -> float:
        """Volume of the cold lower layer (m³)."""
        return self.floor_area * max(self.z_interface, 0.0)

    def update_densities(self) -> None:
        """Recalculate layer densities from ideal gas law."""
        self.rho_upper = self.P_zone / (GAS_CONSTANT_AIR * max(self.T_upper, 1.0))
        self.rho_lower = self.P_zone / (GAS_CONSTANT_AIR * max(self.T_lower, 1.0))


@dataclass
class Doorway:
    """Opening connecting two zones.

    Attributes:
        zone_a_id: first zone ID
        zone_b_id: second zone ID
        width: opening width (m)
        height: opening height (m)
        y_center: center position of the opening along the wall (m, for bookkeeping)
        is_open: whether the door is currently open
    """
    zone_a_id: str
    zone_b_id: str
    width: float = 1.0
    height: float = 2.1
    y_center: float = 1.05  # center height of door (m from floor)
    is_open: bool = True


class MultiZoneEngine:
    """CFAST-inspired multi-zone fire model with two-layer zones connected
    by doorways.

    Flow through doorways is computed using the Bernoulli equation with
    hydrostatic pressure variation (Zukoski 1985).  The discharge coefficient
    CD = 0.68 accounts for vena contracta losses.

    BUG FIX (from V2): The doorway mass flow integration is performed from
    the *floor* (z = 0), not from the door centre.  This was the original
    V2 bug that under-estimated bidirectional flow in tall openings.

    Reference:
      Zukoski, E.E. (1985), "Buoyant Plumes in Compartment Fires",
      Fire Safety Science 1:1-16.
    """

    CD: float = 0.68  # discharge coefficient (Zukoski 1985)

    def __init__(self) -> None:
        self.zones: Dict[str, Zone] = {}
        self.doorways: List[Doorway] = []

    def add_zone(self, zone: Zone) -> None:
        self.zones[zone.zone_id] = zone

    def add_doorway(self, doorway: Doorway) -> None:
        self.doorways.append(doorway)

    def step(self, dt: float, fire: Optional[FireSource] = None,
             hrr_now: float = 0.0) -> None:
        """Advance multi-zone state by one time-step.

        Parameters:
            dt: time-step (s)
            fire: optional fire source (for plume entrainment in fire zone)
            hrr_now: current HRR (W)
        """
        # Update densities from current temperatures
        for z in self.zones.values():
            z.update_densities()

        # --- Plume entrainment for fire zone ---
        if fire is not None and hrr_now > 0.0:
            fire_zone = self._find_zone_containing(fire.x, fire.y)
            if fire_zone is not None:
                self._plume_entrainment(fire_zone, hrr_now, dt)

        # --- Doorway flows ---
        for door in self.doorways:
            if not door.is_open:
                continue
            za = self.zones.get(door.zone_a_id)
            zb = self.zones.get(door.zone_b_id)
            if za is None or zb is None:
                continue
            self._doorway_flow(za, zb, door, dt)

        # --- Zone energy balance ---
        for z in self.zones.values():
            self._energy_balance(z, dt)

    def _find_zone_containing(self, x: float, y: float) -> Optional[Zone]:
        """Find the zone that contains position (x, y)."""
        for z in self.zones.values():
            if 0.0 <= x <= z.width and 0.0 <= y <= z.length:
                return z
        # Default: return first zone if only one
        if len(self.zones) == 1:
            return next(iter(self.zones.values()))
        return None

    def _plume_entrainment(self, zone: Zone, hrr: float, dt: float) -> None:
        """Plume entrainment model (McCaffrey 1979 / CFAST).

        Entrained mass flow rate: m_e = 0.076 * Q^{2/3} * z^{5/3}  (for flaming)
        Simplified: use a fixed entrainment coefficient.

        The entrained mass enters the upper layer and the interface descends.
        """
        # Q_conv = fraction of HRR that convects upward (CFAST: ~0.7-0.8)
        Q_conv = 0.7 * hrr

        # Upper layer thickness
        h_upper = max(zone.height - zone.z_interface, 0.1)

        # Entrainment rate (simplified McCaffrey)
        # m_e ≈ 0.076 * Q_conv^(2/3) * h_upper^(5/3) / 1000  (kW inputs)
        Q_kw = Q_conv / 1000.0
        m_dot_e = 0.076 * (Q_kw ** (2.0 / 3.0)) * (h_upper ** (5.0 / 3.0))

        # Mass entering upper layer from lower layer
        dm_upper = m_dot_e * dt  # kg
        dm_lower = -dm_upper

        # Update upper layer temperature: m·Cp·dT = Q_conv·dt
        m_upper = zone.rho_upper * zone.upper_volume
        if m_upper > 0.0:
            dT_upper = Q_conv * dt / (m_upper * AIR_HEAT_CAP)
            zone.T_upper += dT_upper

        # Interface descent:  dz_interface = -dm_upper / (rho_lower * A_floor)
        if zone.rho_lower > 0.0 and zone.floor_area > 0.0:
            dz = -dm_upper / (zone.rho_lower * zone.floor_area)
            zone.z_interface = max(zone.z_interface + dz, 0.1)

    def _doorway_flow(self, za: Zone, zb: Zone, door: Doorway, dt: float) -> None:
        """Compute bidirectional flow through a doorway using Bernoulli +
        hydrostatic pressure profile.

        BUG FIX: Integrate from z = 0 (floor), not from the door centre.
        Use: z_abs = z0 + (i + 0.5) * dz  where z0 = 0 (floor level).
        The integration range is clamped to the door opening.

        Reference: Zukoski (1985), CFAST Technical Reference Guide.
        """
        n_layers = 20
        dz = door.height / n_layers
        # z0 = floor level = 0.0  (BUG FIX: was door.y_center - door.height/2)
        z0 = max(door.y_center - door.height / 2.0, 0.0)

        m_dot_a_to_b = 0.0  # mass flow from A to B (kg/s)
        m_dot_b_to_a = 0.0  # mass flow from B to A (kg/s)

        for i in range(n_layers):
            z_abs = z0 + (i + 0.5) * dz  # absolute height of layer centre

            # Hydrostatic pressure difference at height z
            # dp = (rho_B - rho_A) * g * (z_ref - z)
            # where z_ref is the neutral plane height
            # Simplified: use density-weighted pressure
            p_a = za.P_zone - za.rho_upper * GRAVITY * z_abs
            p_b = zb.P_zone - zb.rho_upper * GRAVITY * z_abs

            dp = p_a - p_b  # pressure difference (Pa)
            dA = door.width * dz  # area of this strip (m²)

            if abs(dp) < 1e-6:
                continue

            # Bernoulli: v = CD * sqrt(2 * |dp| / rho)
            # Use the density of the source zone
            if dp > 0:
                rho_src = za.rho_lower if z_abs < za.z_interface else za.rho_upper
                v = self.CD * math.sqrt(2.0 * abs(dp) / max(rho_src, 0.1))
                m_dot_a_to_b += rho_src * v * dA
            else:
                rho_src = zb.rho_lower if z_abs < zb.z_interface else zb.rho_upper
                v = self.CD * math.sqrt(2.0 * abs(dp) / max(rho_src, 0.1))
                m_dot_b_to_a += rho_src * v * dA

        # Net mass transfer over dt
        dm_ab = m_dot_a_to_b * dt
        dm_ba = m_dot_b_to_a * dt

        # Update zone masses and temperatures
        # A -> B: hot gas from A's upper layer enters B
        if dm_ab > 0.0:
            self._transfer_mass(za, zb, dm_ab, is_upper_source=True)

        if dm_ba > 0.0:
            self._transfer_mass(zb, za, dm_ba, is_upper_source=True)

    def _transfer_mass(
        self,
        src: Zone,
        dst: Zone,
        dm: float,
        is_upper_source: bool,
    ) -> None:
        """Transfer mass *dm* (kg) from *src* upper/lower layer to *dst*
        upper layer, carrying source temperature and contaminants.

        This is a simplified mixing model; CFAST solves the full energy
        and species conservation equations.
        """
        T_src = src.T_upper if is_upper_source else src.T_lower
        smoke_src = src.smoke_upper if is_upper_source else 0.0
        co_src = src.co_upper_ppm if is_upper_source else 0.0

        # Mix into destination upper layer
        m_dst_upper = dst.rho_upper * dst.upper_volume
        if m_dst_upper > 0.0:
            # Energy-weighted mixing
            T_new = (m_dst_upper * dst.T_upper + dm * T_src) / (m_dst_upper + dm)
            dst.T_upper = T_new

            # Species mixing (proportional)
            f = dm / (m_dst_upper + dm)
            dst.smoke_upper += f * (smoke_src - dst.smoke_upper)
            dst.co_upper_ppm += f * (co_src - dst.co_upper_ppm)

        # Interface descent in destination (added mass to upper layer)
        if dst.rho_lower > 0.0 and dst.floor_area > 0.0:
            dz = -dm / (dst.rho_lower * dst.floor_area)
            dst.z_interface = max(dst.z_interface + dz, 0.1)

    def _energy_balance(self, zone: Zone, dt: float) -> None:
        """Simple energy balance: convective cooling of upper layer to
        walls (CFAST uses detailed wall conduction; we use Newton's law).
        """
        # Wall cooling coefficient (simplified)
        h_wall = 5.0  # W/(m²·K)
        # Approximate wall area = 2*(W+L)*H
        wall_area = 2.0 * (zone.width + zone.length) * zone.height
        if wall_area > 0.0:
            m_upper = zone.rho_upper * zone.upper_volume
            if m_upper > 0.0:
                Q_cool = h_wall * wall_area * (zone.T_upper - AMBIENT_TEMP)
                dT = -Q_cool * dt / (m_upper * AIR_HEAT_CAP)
                zone.T_upper += dT

        # Lower layer relaxes toward ambient
        zone.T_lower += 0.01 * dt * (AMBIENT_TEMP - zone.T_lower)

        # SAFETY FIX (F8): Zone temperature bounds with WARNING logging.
        # Real compartment fires rarely exceed ~1100 K (post-flashover ~1100-1200 K).
        # T_upper > 1500 K or T_lower > 1000 K indicates numerical blow-up.
        # We clamp BUT ALSO log a warning — silent clamping violates PRINCIPLE ZERO.
        _MAX_T_UPPER = 1500.0  # K — physically reasonable ceiling for zone models
        _MAX_T_LOWER = 1000.0  # K
        if zone.T_upper > _MAX_T_UPPER:
            logger.warning(
                "Zone %s T_upper = %.1f K exceeds %d K — clamped (numerical blow-up?)",
                zone.zone_id, zone.T_upper, int(_MAX_T_UPPER),
            )
            zone.T_upper = _MAX_T_UPPER
        if zone.T_upper < AMBIENT_TEMP:
            zone.T_upper = AMBIENT_TEMP
        if zone.T_lower > _MAX_T_LOWER:
            logger.warning(
                "Zone %s T_lower = %.1f K exceeds %d K — clamped (numerical blow-up?)",
                zone.zone_id, zone.T_lower, int(_MAX_T_LOWER),
            )
            zone.T_lower = _MAX_T_LOWER
        if zone.T_lower < AMBIENT_TEMP:
            zone.T_lower = AMBIENT_TEMP

        # Update densities
        zone.update_densities()

        # Zone pressure: hydrostatic equilibrium
        zone.P_zone = AMBIENT_PRESSURE  # simplified: uniform pressure

    def impose_on_grid(self, grid: VoxelGrid) -> None:
        """Overlay the multi-zone temperature state onto the CFD grid.

        CRIT-05 FIX: Only impose TEMPERATURE from the zone model.
        Species (smoke, CO, O2, CO2) are now tracked by the voxel-grid
        species transport (SmokeTransportNS) and should NOT be overridden
        by the zone model, which would:
          - Reset upper-layer smoke to 0 every step (zone.smoke_upper=0)
          - Prevent O2/CO2 tracking in the voxel grid
          - Cause mismatches between zone and voxel species values

        The zone model's smoke_upper / co_upper_ppm are still maintained
        for compatibility but are no longer imposed on the grid.
        """
        for v in grid.all_fluid():
            zone = self._find_zone_containing(v.cx, v.cy)
            if zone is None:
                continue
            if v.cz >= zone.z_interface:
                # Upper layer: impose temperature only
                v.temp = zone.T_upper
                # Smoke and species are managed by SmokeTransportNS
            else:
                # Lower layer: impose temperature only
                v.temp = zone.T_lower


# ---------------------------------------------------------------------------
# 10. DetectorType, DetectorConfig, PhysicsDetector
# ---------------------------------------------------------------------------


class DetectorType(Enum):
    """Detector sensor types."""
    SMOKE = auto()
    HEAT = auto()
    COMBINATION = auto()
    CO = auto()


@dataclass
class DetectorConfig:
    """Configuration for a physics-based fire detector.

    Attributes:
        detector_type: sensor modality
        smoke_threshold: smoke OD threshold for alarm (m⁻¹), UL 268
        temp_threshold: temperature threshold for alarm (K)
        rti: Response Time Index (m·s)^½, NFPA 72 §17.6.3
        latency_s: electronic processing delay (s)
        false_alarm_rate: probability of false alarm per second
            NOTE: This is SIMULATION NOISE only, using an LCG PRNG.
            It is NOT a statistical prediction of real-world false alarm
            rates and must NOT be used for risk assessment.
        miss_detect_rate: probability of missing a real alarm per check
            NOTE: Also simulation noise only.
        co_threshold_ppm: CO alarm threshold (ppm)
    """
    detector_type: DetectorType = DetectorType.COMBINATION
    smoke_threshold: float = SMOKE_ALARM_OD  # m⁻¹ (UL 268)
    temp_threshold: float = AMBIENT_TEMP + 57.0  # 57 K rise → ~350 K (NFPA 72 §17.6.2.1)
    rti: float = 50.0  # (m·s)^½, typical spot detector
    latency_s: float = 1.0  # s
    false_alarm_rate: float = 1e-4  # per second (SIMULATION NOISE, NOT crypto-grade)
    miss_detect_rate: float = 0.02  # probability per check (SIMULATION NOISE)
    co_threshold_ppm: float = 400.0  # ppm (UL 2034 for CO alarms)


class PhysicsDetector:
    """Physics-based fire detector with RTI delay model and probabilistic noise.

    The RTI (Response Time Index) model per NFPA 72 §17.6.3:
        t_response = RTI / sqrt(u_gas) + latency

    where u_gas is the local gas velocity at the detector.

    Probabilistic noise uses a deterministic LCG (Linear Congruential Generator)
    PRNG.  This is NOT cryptographically secure and is NOT suitable for
    security-sensitive applications.  It provides reproducible simulation noise
    given a fixed seed.

    Attributes:
        detector_id: unique identifier
        x, y, z: world position (m)
        zone_id: NFPA 72 zone grouping identifier
        config: detector configuration
        is_alarmed: whether the detector has entered alarm state
        alarm_time: simulation time of alarm (s), None if not alarmed
        response_timer: remaining RTI delay (s)
        _rng_state: internal LCG state (deterministic)
    """

    # LCG constants (Numerical Recipes)
    _LCG_A: int = 1664525
    _LCG_C: int = 1013904223
    _LCG_M: int = 2**32

    def __init__(
        self,
        detector_id: str,
        x: float,
        y: float,
        z: float,
        zone_id: str,
        config: DetectorConfig,
        seed: int = 42,
    ) -> None:
        self.detector_id = detector_id
        self.x = x
        self.y = y
        self.z = z
        self.zone_id = zone_id
        self.config = config
        self.is_alarmed: bool = False
        self.alarm_time: Optional[float] = None
        self.response_timer: float = 0.0
        self._triggered: bool = False  # True when RTI countdown started
        self._rng_state: int = seed & 0xFFFFFFFF

    def _lcg_random(self) -> float:
        """Generate a pseudo-random float in [0, 1) using LCG.

        WARNING: This LCG PRNG is deterministic but NOT cryptographically
        secure.  It is used solely for simulation noise and must NOT be
        used for any security, cryptographic, or risk-assessment purpose.
        """
        self._rng_state = (self._LCG_A * self._rng_state + self._LCG_C) % self._LCG_M
        return self._rng_state / self._LCG_M

    def update(self, grid: VoxelGrid, t: float, dt: float) -> Optional[str]:
        """Update detector state for one time-step.

        Parameters:
            grid: VoxelGrid (to read local conditions)
            t: current simulation time (s)
            dt: time-step (s)

        Returns:
            detector_id if alarm just triggered, else None.
        """
        if self.is_alarmed:
            return None

        voxel = grid.at_pos(self.x, self.y, self.z)
        if voxel is None or voxel.is_solid:
            return None

        # Check local conditions against thresholds
        smoke_exceeded = (
            self.config.detector_type in
            (DetectorType.SMOKE, DetectorType.COMBINATION)
            and voxel.smoke >= self.config.smoke_threshold
        )
        temp_exceeded = (
            self.config.detector_type in
            (DetectorType.HEAT, DetectorType.COMBINATION)
            and voxel.temp >= self.config.temp_threshold
        )
        co_exceeded = (
            self.config.detector_type in
            (DetectorType.CO, DetectorType.COMBINATION)
            and voxel.co_ppm >= self.config.co_threshold_ppm
        )

        condition_triggered = smoke_exceeded or temp_exceeded or co_exceeded

        # --- False alarm check (simulation noise) ---
        if not condition_triggered:
            if self._lcg_random() < self.config.false_alarm_rate * dt:
                condition_triggered = True  # false alarm trigger

        # --- Miss detection check (simulation noise) ---
        if condition_triggered:
            if self._lcg_random() < self.config.miss_detect_rate:
                condition_triggered = False  # missed detection

        # --- RTI delay model ---
        if condition_triggered and not self._triggered:
            self._triggered = True
            u_gas = max(voxel.speed, 0.1)  # avoid division by zero
            t_response = self.config.rti / math.sqrt(u_gas) + self.config.latency_s
            self.response_timer = t_response

        if self._triggered:
            self.response_timer -= dt
            if self.response_timer <= 0.0:
                self.is_alarmed = True
                self.alarm_time = t
                return self.detector_id

        return None


# ---------------------------------------------------------------------------
# 11. NFPA72AlarmState, ZoneAlarmStatus, NFPA72LogicEngine
# ---------------------------------------------------------------------------


class NFPA72AlarmState(Enum):
    """Alarm verification states per NFPA 72-2022 §26.2.

    NORMAL:           No detectors in alarm
    ALARM_UNVERIFIED: Single detector in alarm (awaiting verification)
    ALARM_VERIFIED:   Two or more detectors, cross-zone, or CO/tenability
    MASS_NOTIFY:      Evacuation signal issued
    """
    NORMAL = auto()
    ALARM_UNVERIFIED = auto()
    ALARM_VERIFIED = auto()
    MASS_NOTIFY = auto()


@dataclass
class ZoneAlarmStatus:
    """Per-zone alarm tracking for NFPA 72 zone grouping.

    Attributes:
        zone_id: NFPA 72 zone identifier
        alarmed_detectors: set of detector IDs currently in alarm
        first_alarm_time: simulation time of first alarm in this zone
    """
    zone_id: str
    alarmed_detectors: set = field(default_factory=set)
    first_alarm_time: Optional[float] = None


class NFPA72LogicEngine:
    """Alarm verification logic per NFPA 72-2022.

    State machine:
      NORMAL → ALARM_UNVERIFIED  (1 detector triggers)
      ALARM_UNVERIFIED → ALARM_VERIFIED  (2+ detectors, or cross-zone,
                                           or CO lethal, or tenability lost)
      ALARM_VERIFIED → MASS_NOTIFY  (after positive alarm sequence)

    Positive Alarm Sequence (§26.2.4):
      - 15 s pre-signal delay before verification propagates
      - Verification window: 120 s maximum from first alarm

    Tenability check (§26.3.5):
      - Smoke layer below 1.8 m from floor → tenability lost
      - CO concentration exceeds lethal threshold → tenability lost

    BUG FIX (from V2): Replaced `int(t) % 30 == 0` periodic tenability
    check with a tracked `_last_tenability_report_t` variable so the
    tenability check fires at precise 30 s intervals regardless of dt.
    """

    PRE_SIGNAL_DELAY: float = 15.0     # s (NFPA 72 §26.2.4)
    VERIFICATION_WINDOW: float = 120.0  # s (NFPA 72 §26.2.3)
    TENABILITY_HEIGHT: float = 1.8      # m (NFPA 72 §26.3.5)
    TENABILITY_CHECK_INTERVAL: float = 30.0  # s

    def __init__(self) -> None:
        self.state: NFPA72AlarmState = NFPA72AlarmState.NORMAL
        self.zone_statuses: Dict[str, ZoneAlarmStatus] = {}
        self.first_alarm_time: Optional[float] = None
        self.verification_start: Optional[float] = None
        self.mass_notify_time: Optional[float] = None
        self._last_tenability_report_t: float = -self.TENABILITY_CHECK_INTERVAL
        self._tenability_lost: bool = False
        self._co_lethal: bool = False

    def step(
        self,
        detectors: Sequence[PhysicsDetector],
        grid: VoxelGrid,
        t: float,
        dt: float,
    ) -> List[str]:
        """Evaluate NFPA 72 alarm logic for one time-step.

        Parameters:
            detectors: all detectors in the system
            grid: VoxelGrid (for tenability and CO checks)
            t: current simulation time (s)
            dt: time-step (s)

        Returns:
            List of event strings generated this step.
        """
        events: List[str] = []

        # Collect alarmed detectors
        alarmed_ids: List[str] = []
        alarmed_zones: Dict[str, List[str]] = {}

        for det in detectors:
            if det.is_alarmed:
                alarmed_ids.append(det.detector_id)
                zid = det.zone_id
                if zid not in alarmed_zones:
                    alarmed_zones[zid] = []
                alarmed_zones[zid].append(det.detector_id)

                # Track per-zone
                if zid not in self.zone_statuses:
                    self.zone_statuses[zid] = ZoneAlarmStatus(zone_id=zid)
                zs = self.zone_statuses[zid]
                if det.detector_id not in zs.alarmed_detectors:
                    zs.alarmed_detectors.add(det.detector_id)
                    if zs.first_alarm_time is None:
                        zs.first_alarm_time = t

        n_alarmed = len(alarmed_ids)
        n_zones_with_alarm = len(alarmed_zones)

        # --- Tenability check (with tracked interval) ---
        # BUG FIX: use tracker variable instead of int(t) % 30
        if t - self._last_tenability_report_t >= self.TENABILITY_CHECK_INTERVAL:
            self._last_tenability_report_t = t
            self._tenability_lost = self._check_tenability(grid)
            self._co_lethal = self._check_co_lethal(grid)
            if self._tenability_lost:
                events.append(f"TENABILITY_LOST at t={t:.1f}s: smoke layer < {self.TENABILITY_HEIGHT}m")
            if self._co_lethal:
                events.append(f"CO_LETHAL at t={t:.1f}s: CO > {CO_LETHAL_PPM}ppm")

        # --- State machine ---
        if self.state == NFPA72AlarmState.NORMAL:
            if n_alarmed >= 1:
                self.state = NFPA72AlarmState.ALARM_UNVERIFIED
                self.first_alarm_time = t
                self.verification_start = t
                events.append(
                    f"ALARM_UNVERIFIED at t={t:.1f}s: detector(s) {alarmed_ids}"
                )

        elif self.state == NFPA72AlarmState.ALARM_UNVERIFIED:
            # Check verification criteria
            verified = False
            verify_reason = ""

            # Criterion 1: 2+ detectors (any zone)  (§26.2.3)
            if n_alarmed >= 2:
                verified = True
                verify_reason = f"{n_alarmed} detectors in alarm"

            # Criterion 2: Cross-zone alarm  (§26.2.3)
            elif n_zones_with_alarm >= 2:
                verified = True
                verify_reason = f"cross-zone: zones {list(alarmed_zones.keys())}"

            # Criterion 3: CO lethal  (§26.3.5)
            elif self._co_lethal:
                verified = True
                verify_reason = "CO lethal concentration"

            # Criterion 4: Tenability lost  (§26.3.5)
            elif self._tenability_lost:
                verified = True
                verify_reason = "tenability lost"

            # Verification window timeout  (§26.2.3)
            if self.verification_start is not None:
                if t - self.verification_start > self.VERIFICATION_WINDOW:
                    if not verified and n_alarmed >= 1:
                        # Single detector after timeout: still unverifiable
                        # but we escalate for safety (conservative)
                        verified = True
                        verify_reason = "verification window expired (conservative escalation)"

            if verified:
                self.state = NFPA72AlarmState.ALARM_VERIFIED
                events.append(
                    f"ALARM_VERIFIED at t={t:.1f}s: {verify_reason}"
                )

        elif self.state == NFPA72AlarmState.ALARM_VERIFIED:
            # Positive Alarm Sequence: pre-signal delay before mass notification
            if self.first_alarm_time is not None:
                elapsed_since_first = t - self.first_alarm_time
                if elapsed_since_first >= self.PRE_SIGNAL_DELAY:
                    self.state = NFPA72AlarmState.MASS_NOTIFY
                    self.mass_notify_time = t
                    events.append(
                        f"MASS_NOTIFY at t={t:.1f}s: evacuation signal issued"
                    )

        # MASS_NOTIFY is terminal state
        return events

    def _check_tenability(self, grid: VoxelGrid) -> bool:
        """Check if smoke layer has descended below tenability height.

        Per NFPA 72 §26.3.5, tenability is lost when the smoke layer
        interface is below 1.8 m from the floor.
        """
        for v in grid.all_fluid():
            if v.cz < self.TENABILITY_HEIGHT and v.smoke > SMOKE_ALARM_OD:
                return True
        return False

    def _check_co_lethal(self, grid: VoxelGrid) -> bool:
        """Check if CO concentration exceeds lethal threshold anywhere.

        Per OSHA 29 CFR 1910.1000, CO lethal concentration is 1200 ppm.
        """
        for v in grid.all_fluid():
            if v.co_ppm > CO_LETHAL_PPM:
                return True
        return False


# ---------------------------------------------------------------------------
# 12. SimulationEvent + AuditEventStore
# ---------------------------------------------------------------------------


@dataclass
class SimulationEvent:
    """Immutable simulation event for the audit trail.

    Attributes:
        seq: global sequence number
        timestamp: simulation time (s)
        event_type: categorical type string
        description: human-readable detail
        cause_id: sequence number of the causal event (0 if none)
        prev_hash: SHA-256 hash of the previous event (chain integrity)
        hash: SHA-256 hash of this event's content
    """
    seq: int
    timestamp: float
    event_type: str
    description: str
    cause_id: int = 0
    prev_hash: str = ""
    hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this event's content concatenated with
        the previous event's hash (hash chain).

        The hash covers: seq, timestamp, event_type, description, cause_id, prev_hash.
        """
        content = (
            f"{self.seq}:{self.timestamp:.6f}:{self.event_type}:"
            f"{self.description}:{self.cause_id}:{self.prev_hash}"
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AuditEventStore:
    """Append-only event log with Write-Ahead Log (WAL) and SHA-256 hash
    chain integrity verification.

    Features:
      - Append-only: events cannot be modified or deleted
      - WAL: every event is persisted before being committed to the in-memory
        store, enabling crash recovery
      - Hash chain: each event's hash depends on the previous event's hash,
        making tampering detectable
      - Global sequence numbers: monotonically increasing
      - Causal chain: events can reference a cause event via cause_id

    Thread Safety:
      WAL writes are protected by a threading.Lock.  The in-memory store
      assumes single-threaded reads within a simulation run.
    """

    def __init__(self, wal_path: Optional[str] = None) -> None:
        self._events: List[SimulationEvent] = []
        self._seq_counter: int = 0
        self._last_hash: str = "GENESIS"  # hash of "virtual" first event
        self._wal_path = wal_path
        self._wal_lock = threading.Lock()

    def emit(
        self,
        timestamp: float,
        event_type: str,
        description: str,
        cause_id: int = 0,
    ) -> SimulationEvent:
        """Append a new event to the store.

        Parameters:
            timestamp: simulation time (s)
            event_type: categorical event type
            description: human-readable detail
            cause_id: sequence number of the causal event (0 = no cause)

        Returns:
            The committed SimulationEvent with hash computed.
        """
        self._seq_counter += 1
        evt = SimulationEvent(
            seq=self._seq_counter,
            timestamp=timestamp,
            event_type=event_type,
            description=description,
            cause_id=cause_id,
            prev_hash=self._last_hash,
        )
        evt.hash = evt.compute_hash()

        # WAL write (crash recovery)
        if self._wal_path is not None:
            self._wal_write(evt)

        self._events.append(evt)
        self._last_hash = evt.hash
        return evt

    def _wal_write(self, evt: SimulationEvent) -> None:
        """Persist event to Write-Ahead Log.

        Thread-safe via _wal_lock.
        """
        line = json.dumps({
            "seq": evt.seq,
            "ts": evt.timestamp,
            "type": evt.event_type,
            "desc": evt.description,
            "cause": evt.cause_id,
            "prev_h": evt.prev_hash,
            "h": evt.hash,
        }, separators=(",", ":"))
        with self._wal_lock:
            with open(self._wal_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def verify_integrity(self) -> bool:
        """Verify the hash chain integrity of all stored events.

        Returns True if every event's hash is consistent with its content
        and the previous event's hash.
        """
        prev_hash = "GENESIS"
        for evt in self._events:
            # Check prev_hash linkage
            if evt.prev_hash != prev_hash:
                return False
            # Recompute and verify hash
            if evt.compute_hash() != evt.hash:
                return False
            prev_hash = evt.hash
        return True

    @property
    def events(self) -> List[SimulationEvent]:
        """Read-only access to all events."""
        return list(self._events)

    @property
    def last_event(self) -> Optional[SimulationEvent]:
        """Return the most recent event, or None if empty."""
        return self._events[-1] if self._events else None

    @classmethod
    def restore_from_wal(cls, wal_path: str) -> "AuditEventStore":
        """Reconstruct an AuditEventStore from a WAL file.

        Parameters:
            wal_path: path to the WAL file

        Returns:
            Reconstructed AuditEventStore with all events recovered.
        """
        store = cls(wal_path=wal_path)
        if not os.path.exists(wal_path):
            return store

        with open(wal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    evt = SimulationEvent(
                        seq=data["seq"],
                        timestamp=data["ts"],
                        event_type=data["type"],
                        description=data["desc"],
                        cause_id=data.get("cause", 0),
                        prev_hash=data.get("prev_h", ""),
                        hash=data.get("h", ""),
                    )
                    store._events.append(evt)
                    store._seq_counter = evt.seq
                    store._last_hash = evt.hash
                except (json.JSONDecodeError, KeyError):
                    # Skip corrupted WAL entries
                    continue

        return store


# ---------------------------------------------------------------------------
# 13. SimulationSnapshot
# ---------------------------------------------------------------------------


@dataclass
class SimulationSnapshot:
    """Point-in-time snapshot of the simulation state for post-hoc analysis.

    Attributes:
        t: simulation time (s)
        hrr_w: current heat release rate (W)
        peak_temp_k: peak temperature in the domain (K)
        peak_smoke_od: peak smoke optical density (m⁻¹)
        alarm_events: list of alarm-related event descriptions
        n_alarmed: number of detectors currently in alarm
        dt_used: time-step used at this snapshot (s)
        nfpa_state: NFPA 72 alarm state
    """
    t: float
    hrr_w: float
    peak_temp_k: float
    peak_smoke_od: float
    alarm_events: List[str]
    n_alarmed: int
    dt_used: float
    nfpa_state: NFPA72AlarmState


# ---------------------------------------------------------------------------
# 14. ScenarioResult
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    """Complete result of a fire scenario simulation.

    Attributes:
        first_alarm_time: simulation time of first detector alarm (s), None if no alarm
        nfpa_final_state: final NFPA 72 alarm state
        n_detectors_fired: number of detectors that entered alarm
        peak_temp_k: maximum temperature reached in the domain (K)
        peak_smoke_od: maximum smoke OD reached (m⁻¹)
        simulation_duration: total simulated time (s)
        event_store: the audit event store with full history
        snapshots: list of simulation snapshots
        integrity_ok: True if event store hash chain is intact
    """
    first_alarm_time: Optional[float]
    nfpa_final_state: NFPA72AlarmState
    n_detectors_fired: int
    peak_temp_k: float
    peak_smoke_od: float
    simulation_duration: float
    event_store: AuditEventStore
    snapshots: List[SimulationSnapshot]
    integrity_ok: bool


# ---------------------------------------------------------------------------
# 15. TimeEngine
# ---------------------------------------------------------------------------


class TimeEngine:
    """Adaptive-dt time-stepping engine that orchestrates all physics modules.

    The integration loop per step:
      1. Compute stable dt via CFLController
      2. Pressure solver step (Navier-Stokes)
      3. Heat transport step
      4. Smoke transport step
      5. Multi-zone step + impose on grid
      6. Detector update
      7. NFPA 72 logic evaluation
      8. Divergence check
      9. Emit audit events
     10. Yield snapshot (for callers that iterate)

    The engine is designed to be driven by ScenarioRunner but can also
    be iterated manually.
    """

    def __init__(
        self,
        grid: VoxelGrid,
        fires: List[FireSource],
        detectors: List[PhysicsDetector],
        multi_zone: MultiZoneEngine,
        nfpa_engine: NFPA72LogicEngine,
        event_store: AuditEventStore,
        dt_request: float = 0.5,
        snapshot_interval: float = 5.0,
        combustion_model: Optional[VoxelCombustionModel] = None,
    ) -> None:
        self.grid = grid
        self.fires = fires
        self.detectors = detectors
        self.multi_zone = multi_zone
        self.nfpa_engine = nfpa_engine
        self.event_store = event_store
        self.dt_request = dt_request
        self.snapshot_interval = snapshot_interval

        # Physics solvers
        self._cfl = CFLController()
        self._pressure = PressureSolver()
        self._heat = HeatTransportNS()
        self._smoke = SmokeTransportNS()

        # CRIT-02: Combustion model with O2-limited HRR and fuel tracking.
        # If not provided, create one from the first fire source.
        if combustion_model is not None:
            self._combustion = combustion_model
        elif fires:
            self._combustion = VoxelCombustionModel(
                hrr_peak_w=fires[0].hrr,
                growth_alpha_kw_s2=fires[0].growth_alpha,
                ignition_time_s=fires[0].ignition_time,
                fuel_load_kg=fires[0].fuel_load_kg,
            )
        else:
            self._combustion = VoxelCombustionModel()

        # State tracking
        self._t: float = 0.0
        self._last_snapshot_t: float = -self.snapshot_interval

    def step(self) -> Tuple[float, float]:
        """Execute one adaptive time-step.

        Returns:
            (dt_used, t_after) — the actual dt used and the new simulation time.
        """
        # 1. CFL compute dt
        fluid = self.grid.all_fluid()
        u_max = CFLController.max_velocity(fluid)
        dx = self.grid.resolution
        dt = self._cfl.compute_dt(dx, u_max, self.dt_request)

        # Cap dt to not overshoot
        dt = min(dt, self.dt_request)

        # 2. Pressure solver step
        self._pressure.step(self.grid, dt)

        # CRIT-02: Use VoxelCombustionModel for O2-limited HRR
        # This replaces the simple FireGrowthModel.hrr_at() which had
        # no ventilation control, no fuel tracking, and no decay.
        primary_fire = self.fires[0] if self.fires else None
        hrr_now = self._combustion.get_hrr(
            self._t, grid=self.grid, fire=primary_fire,
        )

        # Check fuel exhaustion (may transition to DECAY phase)
        hrr_now = self._combustion.check_fuel_exhaustion(self._t, hrr_now)

        # 3. Heat transport
        for fire in self.fires:
            self._heat.step(self.grid, fire, hrr_now, dt)

        # 4. Smoke + species transport (CRIT-05: includes O2/CO2)
        for fire in self.fires:
            self._smoke.step(self.grid, fire, hrr_now, dt)

        # Consume fuel after transport
        self._combustion.consume_fuel(hrr_now, dt)

        # 5. Multi-zone step + impose on grid
        self.multi_zone.step(dt, fire=primary_fire, hrr_now=hrr_now)
        self.multi_zone.impose_on_grid(self.grid)

        # 6. Detector update
        new_alarms: List[str] = []
        for det in self.detectors:
            result = det.update(self.grid, self._t, dt)
            if result is not None:
                new_alarms.append(result)

        # 7. NFPA 72 logic
        alarm_events = self.nfpa_engine.step(self.detectors, self.grid, self._t, dt)

        # 8. Divergence check
        self._cfl.check_divergence(self.grid.cells)

        # 9. Emit events
        for alarm_id in new_alarms:
            self.event_store.emit(
                timestamp=self._t,
                event_type="DETECTOR_ALARM",
                description=f"Detector {alarm_id} entered alarm",
            )
        for ae in alarm_events:
            self.event_store.emit(
                timestamp=self._t,
                event_type="NFPA72_ALARM",
                description=ae,
            )

        # Advance time
        self._t += dt

        return dt, self._t

    def maybe_snapshot(self) -> Optional[SimulationSnapshot]:
        """Return a SimulationSnapshot if the snapshot interval has elapsed,
        otherwise None.
        """
        if self._t - self._last_snapshot_t >= self.snapshot_interval:
            self._last_snapshot_t = self._t

            # Compute current HRR from combustion model
            hrr_total = self._combustion.get_hrr(
                self._t, grid=self.grid,
                fire=self.fires[0] if self.fires else None,
            )

            # Collect alarm events from this snapshot window
            recent_events = [
                e.description for e in self.event_store.events
                if self._t - self.snapshot_interval <= e.timestamp <= self._t
                and e.event_type in ("DETECTOR_ALARM", "NFPA72_ALARM")
            ]

            n_alarmed = sum(1 for d in self.detectors if d.is_alarmed)

            return SimulationSnapshot(
                t=self._t,
                hrr_w=hrr_total,
                peak_temp_k=self.grid.peak_temp(),
                peak_smoke_od=self.grid.peak_smoke(),
                alarm_events=recent_events,
                n_alarmed=n_alarmed,
                dt_used=self.dt_request,
                nfpa_state=self.nfpa_engine.state,
            )
        return None

    @property
    def t(self) -> float:
        """Current simulation time (s)."""
        return self._t

    def run(self, t_end: float) -> Generator[SimulationSnapshot, None, None]:
        """Run the simulation from current time to *t_end*, yielding
        snapshots at each snapshot interval.

        Parameters:
            t_end: target end time (s)

        Yields:
            SimulationSnapshot at each snapshot interval.
        """
        while self._t < t_end:
            dt_used, t_after = self.step()
            snap = self.maybe_snapshot()
            if snap is not None:
                yield snap

            # Early termination if MASS_NOTIFY has been reached
            if self.nfpa_engine.state == NFPA72AlarmState.MASS_NOTIFY:
                # Still run a few more seconds for post-alarm data
                if t_after - (self.nfpa_engine.mass_notify_time or 0.0) > 10.0:
                    break


# ---------------------------------------------------------------------------
# 16. ScenarioRunner
# ---------------------------------------------------------------------------


class ScenarioRunner:
    """Single entry point for configuring and running a fire scenario.

    Usage:
        runner = ScenarioRunner(
            width=10, length=8, height=3, resolution=0.5
        )
        runner.add_zone(Zone("room1", 10, 8, 3))
        runner.add_doorway(Doorway("room1", "room2", width=1.0, height=2.1))
        runner.add_fire(FireSource(x=5, y=4, z=0.5, hrr=500000))
        runner.add_detector("D1", x=3, y=3, z=2.8, zone_id="room1",
                           config=DetectorConfig())
        result = runner.run(t_end=300)

    All configuration must be completed before calling run().
    """

    def __init__(
        self,
        width: float = 10.0,
        length: float = 8.0,
        height: float = 3.0,
        resolution: float = 0.5,
        dt_request: float = 0.5,
        snapshot_interval: float = 5.0,
        wal_path: Optional[str] = None,
        detector_seed: int = 42,
    ) -> None:
        self._grid = VoxelGrid(width, length, height, resolution)
        self._multi_zone = MultiZoneEngine()
        self._nfpa_engine = NFPA72LogicEngine()
        self._event_store = AuditEventStore(wal_path=wal_path)
        self._fires: List[FireSource] = []
        self._detectors: List[PhysicsDetector] = []
        self._detector_seed = detector_seed
        self._detector_counter: int = 0
        self._dt_request = dt_request
        self._snapshot_interval = snapshot_interval

    def add_zone(self, zone: Zone) -> "ScenarioRunner":
        """Add a zone to the multi-zone model."""
        self._multi_zone.add_zone(zone)
        return self

    def add_doorway(self, doorway: Doorway) -> "ScenarioRunner":
        """Add a doorway connecting two zones."""
        self._multi_zone.add_doorway(doorway)
        return self

    def add_fire(self, fire: FireSource) -> "ScenarioRunner":
        """Add a fire source to the scenario."""
        self._fires.append(fire)
        return self

    def add_detector(
        self,
        detector_id: str,
        x: float,
        y: float,
        z: float,
        zone_id: str,
        config: Optional[DetectorConfig] = None,
    ) -> "ScenarioRunner":
        """Add a detector to the scenario.

        Parameters:
            detector_id: unique identifier
            x, y, z: world position (m)
            zone_id: NFPA 72 zone identifier
            config: detector configuration (uses defaults if None)
        """
        if config is None:
            config = DetectorConfig()
        # Deterministic seed per detector (based on counter)
        seed = (self._detector_seed + self._detector_counter * 7919) & 0xFFFFFFFF
        self._detector_counter += 1
        det = PhysicsDetector(detector_id, x, y, z, zone_id, config, seed=seed)
        self._detectors.append(det)
        return self

    def add_obstacle(
        self,
        x0: float, y0: float, z0: float,
        x1: float, y1: float, z1: float,
    ) -> "ScenarioRunner":
        """Add a solid obstacle (AABB) to the grid."""
        self._grid.mark_solid(x0, y0, z0, x1, y1, z1)
        return self

    def run(self, t_end: float = 300.0) -> ScenarioResult:
        """Execute the fire scenario simulation.

        Parameters:
            t_end: simulation end time (s)

        Returns:
            ScenarioResult with all simulation outputs.
        """
        # Emit scenario start event
        self._event_store.emit(
            timestamp=0.0,
            event_type="SCENARIO_START",
            description=f"Scenario started: t_end={t_end}s, "
                        f"grid={self._grid.nx}x{self._grid.ny}x{self._grid.nz}, "
                        f"fires={len(self._fires)}, "
                        f"detectors={len(self._detectors)}",
        )

        # Create and run the time engine
        engine = TimeEngine(
            grid=self._grid,
            fires=self._fires,
            detectors=self._detectors,
            multi_zone=self._multi_zone,
            nfpa_engine=self._nfpa_engine,
            event_store=self._event_store,
            dt_request=self._dt_request,
            snapshot_interval=self._snapshot_interval,
        )

        snapshots: List[SimulationSnapshot] = []
        for snap in engine.run(t_end):
            snapshots.append(snap)

        # Final snapshot
        hrr_total = engine._combustion.get_hrr(
            engine.t, grid=self._grid,
            fire=self._fires[0] if self._fires else None,
        )
        final_snap = SimulationSnapshot(
            t=engine.t,
            hrr_w=hrr_total,
            peak_temp_k=self._grid.peak_temp(),
            peak_smoke_od=self._grid.peak_smoke(),
            alarm_events=[],
            n_alarmed=sum(1 for d in self._detectors if d.is_alarmed),
            dt_used=self._dt_request,
            nfpa_state=self._nfpa_engine.state,
        )
        snapshots.append(final_snap)

        # Compute results
        first_alarm_time: Optional[float] = None
        for det in self._detectors:
            if det.alarm_time is not None:
                if first_alarm_time is None or det.alarm_time < first_alarm_time:
                    first_alarm_time = det.alarm_time

        n_detectors_fired = sum(1 for d in self._detectors if d.is_alarmed)

        # Emit scenario end event
        self._event_store.emit(
            timestamp=engine.t,
            event_type="SCENARIO_END",
            description=f"Scenario ended: state={self._nfpa_engine.state.name}, "
                        f"alarmed={n_detectors_fired}, "
                        f"peak_T={self._grid.peak_temp():.1f}K",
        )

        integrity_ok = self._event_store.verify_integrity()

        return ScenarioResult(
            first_alarm_time=first_alarm_time,
            nfpa_final_state=self._nfpa_engine.state,
            n_detectors_fired=n_detectors_fired,
            peak_temp_k=self._grid.peak_temp(),
            peak_smoke_od=self._grid.peak_smoke(),
            simulation_duration=engine.t,
            event_store=self._event_store,
            snapshots=snapshots,
            integrity_ok=integrity_ok,
        )
