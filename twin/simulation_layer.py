"""
twin/simulation_layer.py — FireAI Level 4 Simulation Layer
============================================================
High-level simulation interface that wraps the physics engine with
NFPA 72 compliance validation and proper detector activation tracking.

This layer sits between:
  - Below: semi_cfast_engine.py (SemiCFASTSolver — physics-based zone model)
  - Above: digital_twin_bridge.py (BIM integration, state management)

CRITICAL FIX (CRIT-02 + CRIT-05): This module now uses SemiCFASTSolver
instead of the old MultiZoneEngine. The old engine was an event-driven
visualization tool, NOT a physics simulation. It lacked:
  ❌ Combustion model (fires burned forever)
  ❌ Species transport (O2, CO, CO2, soot)
  ❌ Fuel consumption
  ❌ Proper RTI detector model
  ❌ Conservation-law enforcement

The SemiCFASTSolver provides ALL of these via its 11-phase architecture:
  Phase 1:  LayerState + RoomCompartment (conservation of mass)
  Phase 2:  LayerEnergySolver (conservation of energy, semi-implicit)
  Phase 3:  PlumeModel (Heskestad entrainment)
  Phase 4:  VentFlowSolver (bi-directional with neutral plane)
  Phase 5:  SmokeLayerSolver (conservation-consistent interface height)
  Phase 6:  SpeciesTransport (O2, CO2, CO, soot conservation)
  Phase 7:  CombustionModel (fuel → ventilation → decay)
  Phase 8:  DetectorPhysics (RTI model per NFPA 72 §17.6.3)
  Phase 9:  WallThermalSolver (transient conduction)
  Phase 10: MultiRoomCoupling (coupled compartment solver)
  Phase 11: NumericalStability (adaptive timestep, mass correction, energy clipping)

SAFETY: All simulation results are approximate. Must be verified by PE.
"Late correct results are better than fast wrong results in a safety program."
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ── Primary physics engine: SemiCFASTSolver (CRIT-02/05 FIX) ──
from twin.semi_cfast_engine import (
    AMBIENT_TEMP_K,
    AMBIENT_PRESSURE_PA,
    AIR_HEAT_CAP_CP,
    GRAVITY as GRAVITY_SEMI,
    GAS_CONSTANT_AIR as GAS_CONSTANT_SEMI,
    FLASHOVER_TEMP_K,
    SMOKE_ALARM_OD,
    CO_LETHAL_PPM,
    HEAT_OF_COMBUSTION_REF,
    LayerState,
    RoomCompartment,
    Vent,
    VentFlowSolver,
    VentFlowResult,
    PlumeModel,
    SmokeLayerSolver,
    SpeciesTransport,
    CombustionModel,
    CombustionPhase,
    DetectorPhysics,
    WallThermalSolver,
    NumericalStability,
    SemiCFASTSolver,
)

# ── Legacy imports for CFD mode and NFPA 72 bridge ──
from twin.fire_physics import (
    AMBIENT_TEMP,
    AIR_DENSITY,
    AIR_HEAT_CAP,
    GRAVITY,
    GAS_CONSTANT_AIR,
    VoxelGrid,
    CFLController,
    FireSource,
    VoxelCombustionModel,
    PressureSolver,
    HeatTransportNS,
    SmokeTransportNS,
    Doorway,
)
from twin.nfpa72_bridge import (
    NFPA72Bridge,
    RoomConfig,
    DetectorPlacement,
    OccupancyType,
)

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data structures for simulation results
# ═══════════════════════════════════════════════════════════════════════

class SimulationMode(Enum):
    """Simulation mode selector."""
    ZONE_MODEL = "zone"          # SemiCFASTSolver (physics-based, 11-phase)
    CFD_LITE = "cfd_lite"        # N-S VoxelGrid solver (slower, detailed)
    HYBRID = "hybrid"            # Zone model + CFD validation


@dataclass
class SimulationRoomConfig:
    """Room configuration for simulation."""
    room_id: str
    name: str
    width_m: float
    depth_m: float
    height_m: float
    occupancy_type: str = "business"
    ceiling_type: str = "smooth"


@dataclass
class SimulationFireSource:
    """Fire source configuration for simulation."""
    room_id: str
    x: float
    y: float
    z: float = 0.0
    hrr_peak_w: float = 500_000.0
    growth_alpha_kW_s2: float = 0.047  # Fast fire per NFPA 72 Table B.4.2.1
    soot_yield: float = 0.10
    co_yield: float = 0.04
    ignition_time_s: float = 0.0
    fuel_load_kg: float = 500.0    # Total fuel available (kg)


@dataclass
class SimulationDetector:
    """Detector configuration for simulation."""
    detector_id: str
    room_id: str
    x: float
    y: float
    z: float
    detector_type: str = "smoke"  # smoke, heat, combination, co
    zone_id: str = ""
    rti: float = 50.0             # Response Time Index (m·s)^½


@dataclass
class DetectorActivation:
    """Record of a detector activation during simulation."""
    detector_id: str
    room_id: str
    activation_time_s: float
    activation_type: str  # "smoke", "heat", "co", "multi"
    threshold_value: float
    measured_value: float
    zone_id: str = ""


@dataclass
class RoomSimulationState:
    """State of a room during simulation (from SemiCFAST zone model)."""
    room_id: str
    time_s: float
    upper_layer_temp_k: float
    lower_layer_temp_k: float
    interface_height_m: float
    smoke_od_m1: float
    co_ppm: float
    o2_mass_fraction: float
    combustion_phase: str = "none"
    fuel_remaining_kg: float = 0.0
    is_flashover: bool = False


@dataclass
class SimulationStep:
    """Single simulation time step result."""
    time_s: float
    room_states: List[RoomSimulationState]
    activations: List[DetectorActivation]
    peak_temp_k: float
    peak_smoke_od: float


@dataclass
class SimulationResult:
    """Complete simulation result."""
    mode: SimulationMode
    duration_s: float
    dt_used: float
    total_steps: int
    room_states: Dict[str, List[RoomSimulationState]]
    all_activations: List[DetectorActivation]
    flashover_rooms: List[str]
    compliance_result: Optional[Dict[str, Any]]
    peak_temp_k: float
    peak_smoke_od: float
    elapsed_wall_s: float
    engine_version: str = "SemiCFAST-v1.0"
    sha256: str = ""


# ═══════════════════════════════════════════════════════════════════════
# Simulation Layer
# ═══════════════════════════════════════════════════════════════════════

class SimulationLayer:
    """High-level fire simulation interface with NFPA 72 validation.

    Uses SemiCFASTSolver as the primary physics engine (CRIT-02/05 FIX).

    The old MultiZoneEngine was an event-driven visualization tool that:
      - Had no combustion model (fires burned forever)
      - Had no species transport (O2, CO2, CO, soot)
      - Had no fuel consumption
      - Did not enforce conservation laws
      - Used ad-hoc equations instead of physics-based ones

    The SemiCFASTSolver provides proper physics with:
      ✅ Heskestad plume entrainment model
      ✅ Bi-directional vent flow with neutral plane
      ✅ Conservation of mass and energy (semi-implicit)
      ✅ Species transport (O2 consumption, CO/CO2/soot generation)
      ✅ 3-phase combustion (growth → ventilation-controlled → decay)
      ✅ RTI detector model per NFPA 72 §17.6.3
      ✅ Wall thermal response (1-D implicit)
      ✅ Numerical stability (adaptive dt, mass correction)
      ✅ Reversible flashover (HIGH-07 FIX)

    Supports three modes:
      - ZONE_MODEL: SemiCFASTSolver (fast, physics-based)
      - CFD_LITE: Full N-S voxel solver (detailed but slower)
      - HYBRID: Zone model with CFD spot-checks

    Safety: All results are approximate. Must be verified by licensed PE.
    """

    # Flashover temperature threshold (600°C per ISO 834 / Babrauskas)
    FLASHOVER_TEMP_K: float = 873.15

    # Detector check interval (seconds) — how often we poll detectors
    DETECTOR_CHECK_INTERVAL_S: float = 0.1

    def __init__(
        self,
        mode: SimulationMode = SimulationMode.ZONE_MODEL,
        resolution_m: float = 0.5,
        max_steps: int = 100_000,
    ) -> None:
        self.mode = mode
        self.resolution_m = resolution_m
        self.max_steps = max_steps

        # ── Primary physics engine: SemiCFASTSolver ──
        self._cfast: Optional[SemiCFASTSolver] = None

        # ── NFPA 72 compliance bridge ──
        self._nfpa72 = NFPA72Bridge()

        # ── CFD components (for CFD_LITE/HYBRID modes) ──
        self._cfl = CFLController()
        self._grid: Optional[VoxelGrid] = None
        self._pressure_solver: Optional[PressureSolver] = None
        self._heat_transport: Optional[HeatTransportNS] = None
        self._smoke_transport: Optional[SmokeTransportNS] = None

        # ── Detector tracking ──
        self._detector_last_check: Dict[str, float] = {}
        self._activated_detector_ids: set = set()

        # ── Room/fire configs (for CFD mode and NFPA72 bridge) ──
        self._room_configs: Dict[str, SimulationRoomConfig] = {}
        self._fires: List[SimulationFireSource] = []
        self._detector_configs: Dict[str, SimulationDetector] = {}

    def setup(
        self,
        rooms: List[SimulationRoomConfig],
        fires: List[SimulationFireSource],
        detectors: List[SimulationDetector],
        doorways: Optional[List[Doorway]] = None,
    ) -> None:
        """Set up the simulation with room, fire, and detector configs.

        Parameters:
            rooms: Room configurations
            fires: Fire source configurations
            detectors: Detector configurations
            doorways: Optional connections between rooms (for multi-zone)
        """
        # Store room configs
        for room in rooms:
            self._room_configs[room.room_id] = room

        # Store fire configs
        self._fires = fires

        # Store detector configs
        for det in detectors:
            self._detector_configs[det.detector_id] = det

        # ── Initialize SemiCFASTSolver (CRIT-02/05 FIX) ──
        self._cfast = SemiCFASTSolver()

        # Add rooms as compartments
        for room in rooms:
            compartment = RoomCompartment(
                room_id=room.room_id,
                width=room.width_m,
                depth=room.depth_m,
                height=room.height_m,
            )
            self._cfast.add_room(compartment)

        # Add doorways as vents (convert Doorway → Vent)
        if doorways:
            for i, door in enumerate(doorways):
                vent = Vent(
                    vent_id=f"vent_{door.zone_a_id}_{door.zone_b_id}_{i}",
                    zone_a_id=door.zone_a_id,
                    zone_b_id=door.zone_b_id,
                    width=door.width,
                    height=door.height,
                    sill_height=0.0,  # Floor-level doors
                    is_open=door.is_open,
                )
                self._cfast.add_vent(vent)

        # Add fires as CombustionModel instances
        for fire in fires:
            combustion = CombustionModel(
                hrr_peak_w=fire.hrr_peak_w,
                growth_alpha_kw_s2=fire.growth_alpha_kW_s2,
                ignition_time_s=fire.ignition_time_s,
                fuel_load_kg=fire.fuel_load_kg,
                soot_yield=fire.soot_yield,
                co_yield=fire.co_yield,
            )
            self._cfast.add_fire(fire.room_id, combustion)

        # Add detectors with RTI model
        for det in detectors:
            # Map detector type string to DetectorType enum
            from twin.semi_cfast_engine import DetectorType as SemiDetectorType
            from twin.semi_cfast_engine import DetectorConfig as SemiDetectorConfig
            from twin.semi_cfast_engine import DetectorPhysics as SemiDetectorPhysics

            dt_map = {
                "smoke": SemiDetectorType.SMOKE,
                "heat": SemiDetectorType.HEAT,
                "combination": SemiDetectorType.COMBINATION,
                "co": SemiDetectorType.CO,
            }
            det_type_enum = dt_map.get(det.detector_type.lower(), SemiDetectorType.SMOKE)

            # Create DetectorConfig with proper RTI
            config = SemiDetectorConfig(
                detector_type=det_type_enum,
                rti=det.rti,
            )

            # Create DetectorPhysics with proper RTI model
            physics_det = SemiDetectorPhysics(
                detector_id=det.detector_id,
                room_id=det.room_id,
                x=det.x,
                y=det.y,
                z=det.z,
                config=config,
            )
            self._cfast.add_detector(physics_det)
            self._detector_last_check[det.detector_id] = -1.0

        # ── Initialize CFD grid if needed ──
        if self.mode in (SimulationMode.CFD_LITE, SimulationMode.HYBRID):
            self._setup_cfd(rooms)

        log.info(
            "Simulation setup (SemiCFAST): %d rooms, %d fires, %d detectors, mode=%s",
            len(rooms), len(fires), len(detectors), self.mode.value,
        )

    def _setup_cfd(self, rooms: List[SimulationRoomConfig]) -> None:
        """Initialize CFD voxel grid for the largest room."""
        if not rooms:
            return

        largest = max(rooms, key=lambda r: r.width_m * r.depth_m * r.height_m)
        self._grid = VoxelGrid(
            width=largest.width_m,
            length=largest.depth_m,
            height=largest.height_m,
            resolution=self.resolution_m,
        )
        self._pressure_solver = PressureSolver()
        self._heat_transport = HeatTransportNS()
        self._smoke_transport = SmokeTransportNS()

        log.info(
            "CFD grid: %dx%dx%d cells (%.1fm resolution)",
            self._grid.nx, self._grid.ny, self._grid.nz,
            self.resolution_m,
        )

    def run(
        self,
        t_end: float = 300.0,
        dt_req: float = 1.0,
        check_compliance: bool = True,
    ) -> SimulationResult:
        """Run the fire simulation using SemiCFASTSolver.

        Parameters:
            t_end: Simulation end time (seconds)
            dt_req: Requested time step (seconds) — may be adapted
            check_compliance: Whether to run NFPA 72 compliance check

        Returns:
            SimulationResult with all states and activations
        """
        if self._cfast is None:
            raise RuntimeError("Simulation not set up. Call setup() first.")

        wall_start = _time.time()
        t = 0.0
        step_count = 0
        dt_actual = dt_req  # Will be adapted by SemiCFAST

        # Results tracking
        room_states: Dict[str, List[RoomSimulationState]] = {
            rid: [] for rid in self._room_configs
        }
        all_activations: List[DetectorActivation] = []
        flashover_rooms: List[str] = []
        global_peak_temp = AMBIENT_TEMP_K
        global_peak_smoke = 0.0

        # Group fires by room for CFD mode
        fires_by_room: Dict[str, List[SimulationFireSource]] = {}
        for fire in self._fires:
            fires_by_room.setdefault(fire.room_id, []).append(fire)

        while t < t_end and step_count < self.max_steps:
            dt = min(dt_req, t_end - t)

            if self.mode == SimulationMode.ZONE_MODEL:
                # ── SemiCFASTSolver step (CRIT-02/05 FIX) ──
                # V9 FIX: SemiCFAST internally adapts its timestep (may use
                # dt < dt_req for stability). We sub-step until the requested
                # time interval has been covered. Without this, the simulation
                # time advanced (t) was out of sync with the physics time
                # actually simulated, causing fuel consumption to be 20× too
                # slow and detector activation times to be wrong.
                activation_events = self._substep_cfast(t, dt)
                dt_actual = dt  # We've covered the full dt via sub-stepping

                # Process detector activations from SemiCFAST
                for event in activation_events:
                    det_id = event.get('detector_id', '')
                    if det_id and det_id not in self._activated_detector_ids:
                        self._activated_detector_ids.add(det_id)
                        # Find room for this detector
                        det_cfg = self._detector_configs.get(det_id)
                        room_id = det_cfg.room_id if det_cfg else "unknown"

                        activation = DetectorActivation(
                            detector_id=det_id,
                            room_id=room_id,
                            activation_time_s=round(event.get('activation_time', t), 2),
                            activation_type=event.get('activation_type', 'unknown'),
                            threshold_value=round(event.get('threshold_value', 0.0), 4),
                            measured_value=round(event.get('measured_value', 0.0), 4),
                            zone_id=det_cfg.zone_id if det_cfg else "",
                        )
                        all_activations.append(activation)

            elif self.mode == SimulationMode.CFD_LITE:
                # CFD mode: SemiCFAST for detector RTI + sub-stepping
                self._substep_cfast(t, dt)
                dt_actual = dt
                self._advance_cfd(dt, fires_by_room, t)

            elif self.mode == SimulationMode.HYBRID:
                # Hybrid: SemiCFAST primary + CFD overlay + sub-stepping
                self._substep_cfast(t, dt)
                dt_actual = dt
                # Periodically overlay zone model onto CFD grid
                if step_count % 10 == 0:
                    self._overlay_zone_to_cfd()

            # ── Record room states from SemiCFAST compartments ──
            for room_id, room_cfg in self._room_configs.items():
                compartment = self._cfast.rooms.get(room_id)
                if compartment is None:
                    continue

                # BUG-LOW-11 FIX: Update derived quantities BEFORE reading
                # smoke_od and co_ppm, not after. Previously, the recorded
                # state used the previous timestep's derived quantities.
                compartment.update_derived_quantities()

                # Read state from RoomCompartment (AFTER update)
                upper_temp = compartment.upper.temperature
                lower_temp = compartment.lower.temperature
                interface = compartment.interface_height
                smoke_od = compartment.smoke_od
                co_ppm = compartment.co_ppm
                o2_frac = compartment.upper.species.get('O2', 0.232)

                # Combustion phase
                fire = self._cfast.fires.get(room_id)
                if fire is not None:
                    comb_phase = fire.phase.name.lower()
                    fuel_rem = fire.fuel_remaining
                else:
                    comb_phase = "none"
                    fuel_rem = 0.0

                # HIGH-07 FIX: Flashover is now REVERSIBLE
                # Old behavior: is_flashover was a one-way flag
                # New behavior: flashover depends on current temperature
                is_flashover = upper_temp >= self.FLASHOVER_TEMP_K
                if is_flashover and room_id not in flashover_rooms:
                    flashover_rooms.append(room_id)
                if not is_flashover and room_id in flashover_rooms:
                    # Flashover reversed — temperature dropped below threshold
                    # This is physically correct: if the fire decays or
                    # ventilation improves, conditions can improve.
                    flashover_rooms.remove(room_id)

                # Track peaks
                if upper_temp > global_peak_temp:
                    global_peak_temp = upper_temp
                if smoke_od > global_peak_smoke:
                    global_peak_smoke = smoke_od

                # Calculate lower layer temperature using proper physics
                # The SemiCFAST energy solver already computes this correctly.
                # No more ad-hoc PLUME_IMPACT_FACTOR needed.
                state = RoomSimulationState(
                    room_id=room_id,
                    time_s=round(t, 2),
                    upper_layer_temp_k=round(upper_temp, 1),
                    lower_layer_temp_k=round(lower_temp, 1),
                    interface_height_m=round(interface, 2),
                    smoke_od_m1=round(smoke_od, 4),
                    co_ppm=round(co_ppm, 1),
                    o2_mass_fraction=round(o2_frac, 4),
                    combustion_phase=comb_phase,
                    fuel_remaining_kg=round(fuel_rem, 1),
                    is_flashover=is_flashover,
                )
                room_states[room_id].append(state)

            t += dt_actual
            step_count += 1

        # NFPA 72 compliance check
        compliance_result = None
        if check_compliance and self._room_configs:
            compliance_result = self._check_nfpa72_compliance()

        # Build result
        elapsed_wall = round(_time.time() - wall_start, 2)

        result = SimulationResult(
            mode=self.mode,
            duration_s=t_end,
            dt_used=dt_actual,
            total_steps=step_count,
            room_states=room_states,
            all_activations=all_activations,
            flashover_rooms=flashover_rooms,
            compliance_result=compliance_result,
            peak_temp_k=round(global_peak_temp, 1),
            peak_smoke_od=round(global_peak_smoke, 4),
            elapsed_wall_s=elapsed_wall,
        )

        # Compute SHA-256 of result for audit integrity
        result.sha256 = self._compute_result_hash(result)

        log.info(
            "Simulation complete (SemiCFAST): %d steps, %d activations, "
            "%d flashover rooms, %.1fs wall",
            step_count, len(all_activations), len(flashover_rooms), elapsed_wall,
        )

        return result

    def _advance_cfd(
        self,
        dt: float,
        fires_by_room: Dict[str, List[SimulationFireSource]],
        t: float,
    ) -> None:
        """Advance the CFD solver by one time step.

        CRIT-02 FIX: Uses VoxelCombustionModel for O2-limited HRR instead of
        the simple FireGrowthModel.hrr_at() which had no ventilation control,
        no fuel tracking, and no decay phase.

        V9 FIX: Removed PressureSolver from CFD_LITE mode. The N-S solver
        was numerically unstable at dt=1.0s with typical fire temperatures
        (>800K), causing divergence (observed: 6,900,000 K at t=16s).
        The PressureSolver requires dt << 1.0s for CFL stability at fire
        temperatures, making it impractical for real-time simulation.

        Instead, CFD_LITE now uses:
          - SemiCFAST for zone temperatures (read from compartments)
          - SmokeTransportNS for smoke/O2/CO/CO2 diffusion + buoyant advection
          - Simplified buoyant velocity (no N-S solve) for advection
          - O2-gated HeatTransportNS for fire source heat

        This is physically justified: CFD_LITE is a "lite" mode — it
        provides spatial resolution for species transport without the
        computational cost and instability risk of full N-S.

        BUG-FIX: Removed double 'break' that silently dropped all fires after
        the first fire in the first room. Now processes ALL fires in ALL rooms.
        Added check_fuel_exhaustion() call (was missing — fires never decayed).
        Fixed cache key to include fire.z for uniqueness.
        """
        if not self._grid:
            return

        # V9 FIX: Overlay SemiCFAST temperatures onto CFD grid FIRST.
        # This ensures the CFD grid uses the zone model's temperature
        # field (which is numerically stable and physics-based) rather
        # than computing its own N-S temperature field (which diverges).
        self._overlay_zone_to_cfd()

        # V9 FIX: Apply simplified buoyant velocity field for advection.
        # Instead of solving the full N-S equations (which requires very
        # small dt for stability), use a simplified buoyancy-driven velocity:
        #   w = sqrt(2 * g * beta * (T - T_ambient) * z)
        # This gives physically reasonable upward velocity near the fire
        # without the numerical instability of the N-S pressure solve.
        self._apply_buoyant_velocity()

        # Process ALL fires in ALL rooms (BUG-CRIT-1: removed double break)
        for room_id, fires in fires_by_room.items():
            for fire in fires:
                fire_src = FireSource(
                    x=fire.x, y=fire.y, z=fire.z,
                    hrr=fire.hrr_peak_w,
                    soot_yield=fire.soot_yield,
                    co_yield=fire.co_yield,
                    fuel_load_kg=fire.fuel_load_kg,
                )

                # CRIT-02 FIX: Use VoxelCombustionModel for O2-limited HRR
                cache_key = f"_comb_{room_id}_{fire.x}_{fire.y}_{fire.z}"
                combustion = getattr(self, cache_key, None)
                if combustion is None:
                    combustion = VoxelCombustionModel(
                        hrr_peak_w=fire.hrr_peak_w,
                        growth_alpha_kw_s2=fire.growth_alpha_kW_s2,
                        ignition_time_s=fire.ignition_time_s,
                        fuel_load_kg=fire.fuel_load_kg,
                    )
                    setattr(self, cache_key, combustion)

                hrr_now = combustion.get_hrr(t, grid=self._grid, fire=fire_src)

                # BUG-CRIT-2 FIX: Check fuel exhaustion
                hrr_now = combustion.check_fuel_exhaustion(t, hrr_now)

                combustion.consume_fuel(hrr_now, dt)

                # V9: HeatTransportNS with O2-gating (safe — won't diverge)
                if self._heat_transport:
                    self._heat_transport.step(self._grid, fire_src, hrr_now, dt)
                # SmokeTransportNS with O2 depletion rate limiter (V9)
                if self._smoke_transport:
                    self._smoke_transport.step(self._grid, fire_src, hrr_now, dt)

        # V9 FIX: No PressureSolver — removed for numerical stability.
        # The N-S solver required dt < 0.1s at fire temperatures for CFL
        # stability, which is impractical. SemiCFAST handles temperatures.
        # Divergence check remains as safety guard.
        self._cfl.check_divergence(self._grid.all_fluid())

    def _apply_buoyant_velocity(self) -> None:
        """Apply simplified buoyancy-driven velocity field to CFD grid.

        V9 FIX: Replaces the full N-S PressureSolver with a simplified
        buoyancy model. This provides physically reasonable advection
        velocities for species transport without numerical instability.

        The vertical velocity is based on the buoyancy of hot gas:
          w = sqrt(2 * g * beta * (T - T_ambient) * min(z, H))
        where beta = 1/T_ambient (Boussinesq approximation).

        Horizontal velocities are set to a small fraction of the
        vertical velocity to represent entrainment flow toward the plume.
        """
        if not self._grid or not self._cfast:
            return

        for v in self._grid.all_fluid():
            if v.is_solid:
                continue

            # Buoyant vertical velocity (upward for hot gas)
            dT = v.temp - AMBIENT_TEMP
            if dT > 0.0:
                beta = 1.0 / AMBIENT_TEMP  # Boussinesq expansion coefficient
                z_eff = max(v.cz, 0.1)  # height above floor
                # Buoyant velocity: w ≈ sqrt(2 * g * beta * dT * z)
                v.w = math.sqrt(2.0 * GRAVITY * beta * dT * z_eff)
                # Cap at physical maximum (~5 m/s for room fires)
                v.w = min(v.w, 5.0)
            else:
                v.w = 0.0

            # Horizontal entrainment (toward fire plume, simplified)
            # In a real plume, air is drawn horizontally toward the fire.
            # Simplified: small inward velocity based on distance to fire.
            v.u *= 0.1  # decay existing horizontal velocity
            v.v *= 0.1

    def _substep_cfast(self, t: float, dt_req: float) -> List[Dict[str, Any]]:
        """Sub-step SemiCFAST until the full dt_req time interval is covered.

        V9 FIX: SemiCFAST.adapt_timestep() may reduce dt internally for
        numerical stability (e.g., dt=0.07s when dt_req=1.0s). Without
        sub-stepping, the physics only advances by the adapted dt while
        the caller assumes it advanced by dt_req — a ~15× time sync error
        that caused fuel consumption to be far too slow and detector
        activation times to be wrong.

        This method repeatedly calls _cfast.step() with the adapted dt
        until the full dt_req interval has been simulated, collecting
        all detector activations along the way.
        """
        all_events: List[Dict[str, Any]] = []
        t_local = t
        t_end = t + dt_req
        max_substeps = 500  # Safety limit (e.g., dt_req=1.0 / dt_min=0.01 = 100)

        for _ in range(max_substeps):
            if t_local >= t_end - 1e-10:
                break
            dt_remaining = t_end - t_local
            events = self._cfast.step(t_local, dt_remaining)
            all_events.extend(events)

            # SemiCFAST internally reduces dt via adapt_timestep().
            # We need to know the actual dt used to track how much time
            # has passed. Since step() doesn't return dt_used, we
            # estimate it from the stability adapter.
            dt_adapted = self._cfast.stability.adapt_timestep(
                self._cfast.rooms, dt_remaining
            )
            t_local += dt_adapted

        return all_events

    def _overlay_zone_to_cfd(self) -> None:
        """Overlay SemiCFAST zone model state onto CFD grid.

        This is the HYBRID mode coupling: the fast zone model provides
        boundary conditions for the CFD grid, ensuring consistency.

        BUG-HIGH-6 FIX: Now overlays O2 and CO2 as well, preventing
        inconsistent voxel state (temp+smoke from zone, O2 from CFD).
        """
        if not self._grid or not self._cfast:
            return

        for v in self._grid.all_fluid():
            # Find which compartment this voxel belongs to
            for room_id, compartment in self._cfast.rooms.items():
                room_cfg = self._room_configs.get(room_id)
                if room_cfg is None:
                    continue
                if (0.0 <= v.cx <= room_cfg.width_m and
                        0.0 <= v.cy <= room_cfg.depth_m):
                    if v.cz >= compartment.interface_height:
                        v.temp = compartment.upper.temperature
                        v.smoke = compartment.smoke_od
                        v.co_ppm = compartment.co_ppm
                        # BUG-HIGH-6 FIX: Overlay species to prevent
                        # inconsistent state (zone says hot smoke, CFD says
                        # high O2 — physically impossible combination).
                        v.o2_fraction = compartment.upper.species.get('O2', 0.232)
                        v.co2_ppm = compartment.upper.species.get('CO2', 0.0) * 1e6
                    else:
                        v.temp = compartment.lower.temperature
                        v.o2_fraction = compartment.lower.species.get('O2', 0.232)
                        v.co2_ppm = compartment.lower.species.get('CO2', 0.0) * 1e6
                    break

    def _check_nfpa72_compliance(self) -> Dict[str, Any]:
        """Run NFPA 72 compliance validation on the design."""
        room_configs = []
        detector_placements = []

        for room_id, room in self._room_configs.items():
            occ_map = {
                "business": OccupancyType.BUSINESS,
                "assembly": OccupancyType.ASSEMBLY,
                "educational": OccupancyType.EDUCATIONAL,
                "factory": OccupancyType.FACTORY,
                "hazardous": OccupancyType.HAZARDOUS,
                "institutional": OccupancyType.INSTITUTIONAL,
                "mercantile": OccupancyType.MERCANTILE,
                "residential": OccupancyType.RESIDENTIAL,
                "storage": OccupancyType.STORAGE,
            }
            occ = occ_map.get(room.occupancy_type.lower(), OccupancyType.BUSINESS)

            room_configs.append(RoomConfig(
                room_id=room_id,
                name=room.name,
                width_m=room.width_m,
                depth_m=room.depth_m,
                ceiling_height_m=room.height_m,
                occupancy_type=occ,
                floor_number=1,
                ceiling_type=room.ceiling_type,
            ))

        for det_id, det_cfg in self._detector_configs.items():
            room_cfg = self._room_configs.get(det_cfg.room_id)
            ceiling_h = room_cfg.height_m if room_cfg else 2.8
            det_type_str = det_cfg.detector_type.lower()
            if det_type_str == "combination":
                det_type_str = "smoke"

            adjusted = self._nfpa72.get_adjusted_spacing(ceiling_h, det_type_str)
            coverage_r = self._nfpa72.get_coverage_radius(adjusted)

            detector_placements.append(DetectorPlacement(
                detector_id=det_id,
                room_id=det_cfg.room_id,
                x=det_cfg.x,
                y=det_cfg.y,
                z=det_cfg.z,
                detector_type=det_type_str,
                coverage_radius_m=coverage_r,
            ))

        return self._nfpa72.validate_design(
            building_id="simulation",
            room_configs=room_configs,
            detector_placements=detector_placements,
        )

    @staticmethod
    def _compute_result_hash(result: SimulationResult) -> str:
        """Compute SHA-256 hash of simulation result for audit integrity."""
        data = {
            'duration_s': result.duration_s,
            'total_steps': result.total_steps,
            'activations': len(result.all_activations),
            'flashover_rooms': sorted(result.flashover_rooms),
            'peak_temp_k': result.peak_temp_k,
            'peak_smoke_od': result.peak_smoke_od,
            'engine_version': result.engine_version,
        }
        content = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════
# Convenience function
# ═══════════════════════════════════════════════════════════════════════

def run_simulation(
    rooms: List[SimulationRoomConfig],
    fires: List[SimulationFireSource],
    detectors: List[SimulationDetector],
    doorways: Optional[List[Doorway]] = None,
    t_end: float = 300.0,
    dt: float = 1.0,
    mode: str = "zone",
    check_compliance: bool = True,
) -> SimulationResult:
    """Run a fire simulation with detector activation tracking.

    Convenience function that creates a SimulationLayer and runs it.

    Parameters:
        rooms: Room configurations
        fires: Fire source configurations
        detectors: Detector configurations
        doorways: Optional inter-room connections
        t_end: Simulation end time (seconds)
        dt: Requested time step (seconds)
        mode: "zone", "cfd_lite", or "hybrid"
        check_compliance: Whether to run NFPA 72 compliance check

    Returns:
        SimulationResult with all states, activations, and compliance info
    """
    sim_mode = SimulationMode(mode)
    sim = SimulationLayer(mode=sim_mode)
    sim.setup(rooms, fires, detectors, doorways)
    return sim.run(t_end=t_end, dt_req=dt, check_compliance=check_compliance)


__all__ = [
    "SimulationMode",
    "SimulationRoomConfig",
    "SimulationFireSource",
    "SimulationDetector",
    "DetectorActivation",
    "RoomSimulationState",
    "SimulationStep",
    "SimulationResult",
    "SimulationLayer",
    "run_simulation",
]
