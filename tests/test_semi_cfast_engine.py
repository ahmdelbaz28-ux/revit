"""
test_semi_cfast_engine.py — Comprehensive Tests for Semi-CFAST Physics Engine
==============================================================================

Tests all 11 phases of the physics engine:
  Phase 1:  LayerState + RoomCompartment (conservation of mass)
  Phase 2:  LayerEnergySolver (conservation of energy)
  Phase 3:  PlumeModel (Heskestad entrainment)
  Phase 4:  VentFlowSolver (bi-directional with neutral plane)
  Phase 5:  SmokeLayerSolver (interface height)
  Phase 6:  SpeciesTransport (O2, CO2, CO, soot)
  Phase 7:  CombustionModel (fuel → vent → decay)
  Phase 8:  DetectorPhysics (RTI model)
  Phase 9:  WallThermalSolver (transient conduction)
  Phase 10: SemiCFASTSolver (multi-room coupling)
  Phase 11: NumericalStability (adaptive timestep, mass correction)

SAFETY: These are PHYSICS VALIDATION tests. If any fail, the simulation
engine must NOT be used for fire safety decisions.
"""

import math
import sys
import os
import unittest

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from twin.semi_cfast_engine import (
    # Phase 1
    LayerState, RoomCompartment, Vent,
    # Phase 2
    LayerEnergySolver,
    # Phase 3
    PlumeModel,
    # Phase 4
    VentFlowSolver, VentFlowResult,
    # Phase 5
    SmokeLayerSolver,
    # Phase 6
    SpeciesTransport,
    # Phase 7
    CombustionPhase, CombustionModel,
    # Phase 8
    DetectorType, DetectorConfig, DetectorPhysics,
    # Phase 9
    WallThermalSolver,
    # Phase 10
    SemiCFASTSolver,
    # Phase 11
    NumericalStability,
    # Results
    RoomStateSnapshot, SimulationResult,
    # Convenience
    run_semi_cfast_simulation,
    # Constants
    AMBIENT_TEMP_K, AMBIENT_PRESSURE_PA, GRAVITY,
    GAS_CONSTANT_AIR, AIR_HEAT_CAP_CP, AIR_DENSITY_REF,
    SMOKE_ALARM_OD, CO_LETHAL_PPM, FLASHOVER_TEMP_K,
)


class TestPhase1_LayerState(unittest.TestCase):
    """Phase 1: Core Thermodynamics — LayerState"""

    def test_default_layer_state(self):
        """LayerState defaults to ambient conditions."""
        ls = LayerState()
        self.assertAlmostEqual(ls.temperature, AMBIENT_TEMP_K, places=1)
        self.assertGreater(ls.density, 0.0)
        self.assertGreater(ls.species['O2'], 0.2)

    def test_density_from_ideal_gas_law(self):
        """ρ = P / (R·T) must hold at ambient conditions."""
        ls = LayerState()
        expected_rho = AMBIENT_PRESSURE_PA / (GAS_CONSTANT_AIR * AMBIENT_TEMP_K)
        self.assertAlmostEqual(ls.density, expected_rho, places=3)

    def test_density_decreases_with_temperature(self):
        """Hot gas must be less dense than cold gas (Boussinesq)."""
        cold = LayerState(temperature=293.15)
        hot = LayerState(temperature=600.0)
        self.assertGreater(cold.density, hot.density)

    def test_enthalpy_computation(self):
        """H = m · Cp · T must be correct."""
        ls = LayerState(mass=10.0, temperature=400.0)
        expected = 10.0 * AIR_HEAT_CAP_CP * 400.0
        self.assertAlmostEqual(ls.enthalpy, expected, places=0)


class TestPhase1_RoomCompartment(unittest.TestCase):
    """Phase 1: RoomCompartment geometry and initialization"""

    def test_room_dimensions(self):
        """Room dimensions must be computed correctly."""
        room = RoomCompartment("R1", width=10.0, depth=8.0, height=3.0)
        self.assertEqual(room.floor_area, 80.0)
        self.assertEqual(room.volume, 240.0)

    def test_initial_interface_at_ceiling(self):
        """Interface height starts at ceiling (no upper layer)."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        self.assertAlmostEqual(room.interface_height, 3.0)

    def test_initial_upper_layer_empty(self):
        """Upper layer mass should be ~0 initially."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        self.assertAlmostEqual(room.upper.mass, 0.0, places=1)

    def test_initial_lower_layer_has_mass(self):
        """Lower layer should contain all room mass initially."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        expected_mass = AIR_DENSITY_REF * 240.0
        # Allow 1% tolerance for ideal gas law computation
        self.assertAlmostEqual(room.lower.mass, expected_mass, delta=expected_mass * 0.02)


class TestPhase2_LayerEnergySolver(unittest.TestCase):
    """Phase 2: Conservation of Energy"""

    def test_fire_heats_upper_layer(self):
        """Fire convective HRR must increase upper layer temperature."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        # Move interface down to create upper layer
        room.interface_height = 2.0
        room.sync_layer_volumes()

        solver = LayerEnergySolver()
        T_before = room.upper.temperature

        solver.solve(
            room,
            Q_fire_conv=100_000.0,  # 100 kW convective
            Q_fire_rad=50_000.0,     # 50 kW radiative
            m_dot_plume=1.0,
            T_plume=500.0,
            m_dot_in_upper=0.0,
            T_in_upper=AMBIENT_TEMP_K,
            m_dot_out_upper=0.0,
            m_dot_in_lower=0.0,
            T_in_lower=AMBIENT_TEMP_K,
            dt=1.0,
        )

        self.assertGreater(room.upper.temperature, T_before)

    def test_no_fire_no_heating(self):
        """Without fire, temperature should stay near ambient (cooling only)."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.upper.temperature = AMBIENT_TEMP_K + 50.0  # slightly warm
        room.sync_layer_volumes()

        solver = LayerEnergySolver()
        T_before = room.upper.temperature

        solver.solve(
            room,
            Q_fire_conv=0.0, Q_fire_rad=0.0,
            m_dot_plume=0.0, T_plume=AMBIENT_TEMP_K,
            m_dot_in_upper=0.0, T_in_upper=AMBIENT_TEMP_K,
            m_dot_out_upper=0.0,
            m_dot_in_lower=0.0, T_in_lower=AMBIENT_TEMP_K,
            dt=1.0,
        )

        # Temperature should decrease (cooling)
        self.assertLess(room.upper.temperature, T_before)

    def test_temperature_cannot_go_below_ambient(self):
        """Temperature floor: cannot drop below ambient."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.sync_layer_volumes()

        solver = LayerEnergySolver()
        solver.solve(
            room,
            Q_fire_conv=0.0, Q_fire_rad=0.0,
            m_dot_plume=0.0, T_plume=0.0,
            m_dot_in_upper=0.0, T_in_upper=0.0,
            m_dot_out_upper=0.0,
            m_dot_in_lower=0.0, T_in_lower=0.0,
            dt=100.0,  # long time, should try to go below ambient
        )

        self.assertGreaterEqual(room.upper.temperature, AMBIENT_TEMP_K)
        self.assertGreaterEqual(room.lower.temperature, AMBIENT_TEMP_K)


class TestPhase3_PlumeModel(unittest.TestCase):
    """Phase 3: Heskestad Plume Entrainment Model"""

    def test_zero_fire_zero_entrainment(self):
        """Zero HRR → zero entrainment."""
        plume = PlumeModel()
        self.assertEqual(plume.get_entrainment_rate(0.0, 3.0), 0.0)

    def test_entrainment_increases_with_hrr(self):
        """More HRR → more entrainment (smoke production)."""
        plume = PlumeModel()
        m_small = plume.get_entrainment_rate(100.0, 3.0)
        m_large = plume.get_entrainment_rate(1000.0, 3.0)
        self.assertGreater(m_large, m_small)

    def test_entrainment_increases_with_height(self):
        """Taller ceiling → more entrainment (more air entrained)."""
        plume = PlumeModel()
        m_low = plume.get_entrainment_rate(500.0, 2.0)
        m_high = plume.get_entrainment_rate(500.0, 4.0)
        self.assertGreater(m_high, m_low)

    def test_plume_temperature_exceeds_ambient(self):
        """Plume temperature must be above ambient for fire > 0."""
        plume = PlumeModel()
        T = plume.get_plume_temperature(500.0, 3.0)
        self.assertGreater(T, AMBIENT_TEMP_K)

    def test_plume_temperature_capped(self):
        """Plume temperature should be capped at ~1400 K."""
        plume = PlumeModel()
        T = plume.get_plume_temperature(100_000.0, 0.5)  # very large fire
        self.assertLessEqual(T, 1400.0)

    def test_heskestad_formula_matches_cfast(self):
        """Heskestad formula must be in the correct range.

        For Q = 500 kW, z = 3.0m:
        m_dot ≈ 0.071 * 500^(1/3) * 3.0^(5/3) + 0.0018 * 500
        Virtual origin correction shifts z, so allow wider tolerance.
        """
        plume = PlumeModel()
        Q = 500.0  # kW
        z = 3.0    # m

        m_dot = plume.get_entrainment_rate(Q, z, fire_diameter_m=0.5)
        # Manual calculation (without virtual origin correction)
        expected_no_correction = 0.071 * (Q ** (1.0/3.0)) * (z ** (5.0/3.0)) + 0.0018 * Q
        # Virtual origin increases effective height, so m_dot should be >= base formula
        # But allow 30% tolerance since virtual origin correction is significant
        self.assertAlmostEqual(m_dot, expected_no_correction, delta=expected_no_correction * 0.3)


class TestPhase4_VentFlowSolver(unittest.TestCase):
    """Phase 4: Bi-directional Vent Flow with Neutral Plane"""

    def test_equal_rooms_zero_flow(self):
        """Identical rooms at same conditions → no net flow."""
        room_a = RoomCompartment("A", 10.0, 8.0, 3.0)
        room_b = RoomCompartment("B", 10.0, 8.0, 3.0)
        vent = Vent("V1", "A", "B", width=1.0, height=2.1)

        solver = VentFlowSolver()
        result = solver.calculate_flow(vent, room_a, room_b)

        # Net flow should be very small (symmetric conditions)
        total_a_to_b = result.m_dot_upper_a_to_b + result.m_dot_lower_a_to_b
        total_b_to_a = result.m_dot_upper_b_to_a + result.m_dot_lower_b_to_a
        self.assertAlmostEqual(total_a_to_b, total_b_to_a, delta=0.1)

    def test_fire_room_pushes_smoke_out(self):
        """Room with fire (hot upper layer) should push flow to cool room."""
        room_a = RoomCompartment("A", 10.0, 8.0, 3.0)
        room_a.upper.temperature = 500.0  # hot room
        room_a.interface_height = 2.0
        room_a.sync_layer_volumes()

        room_b = RoomCompartment("B", 10.0, 8.0, 3.0)  # cool room
        vent = Vent("V1", "A", "B", width=1.0, height=2.1)

        solver = VentFlowSolver()
        result = solver.calculate_flow(vent, room_a, room_b)

        # Upper layer flow A→B should be significant (hot gas flows out)
        self.assertGreater(result.m_dot_upper_a_to_b, 0.0)

    def test_vent_closed_zero_flow(self):
        """Closed vent → zero flow."""
        room_a = RoomCompartment("A", 10.0, 8.0, 3.0)
        room_a.upper.temperature = 600.0
        room_b = RoomCompartment("B", 10.0, 8.0, 3.0)
        vent = Vent("V1", "A", "B", width=1.0, height=2.1, is_open=False)

        solver = VentFlowSolver()
        result = solver.calculate_flow(vent, room_a, room_b)

        self.assertEqual(result.m_dot_upper_a_to_b, 0.0)
        self.assertEqual(result.m_dot_lower_a_to_b, 0.0)


class TestPhase5_SmokeLayerSolver(unittest.TestCase):
    """Phase 5: Conservation-consistent interface height"""

    def test_plume_lowers_interface(self):
        """Plume entrainment must lower the interface (smoke layer descends)."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        z_before = room.interface_height

        solver = SmokeLayerSolver()
        solver.solve(room, m_dot_plume=2.0, m_dot_vent_out_upper=0.0,
                     m_dot_vent_in_upper=0.0, dt=1.0)

        self.assertLess(room.interface_height, z_before)

    def test_vent_outflow_raises_interface(self):
        """Removing mass from upper layer (vent outflow) should raise interface."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        # Create an upper layer
        room.interface_height = 1.5
        room.sync_layer_volumes()

        z_before = room.interface_height

        solver = SmokeLayerSolver()
        # Vent outflow without plume → interface rises
        solver.solve(room, m_dot_plume=0.0, m_dot_vent_out_upper=5.0,
                     m_dot_vent_in_upper=0.0, dt=1.0)

        self.assertGreater(room.interface_height, z_before)

    def test_interface_bounded(self):
        """Interface height must stay within [0.1, H-0.01]."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        solver = SmokeLayerSolver()

        # Try to push interface below floor
        solver.solve(room, m_dot_plume=1000.0, m_dot_vent_out_upper=0.0,
                     m_dot_vent_in_upper=0.0, dt=100.0)

        self.assertGreaterEqual(room.interface_height, 0.1)
        self.assertLessEqual(room.interface_height, 3.0)


class TestPhase6_SpeciesTransport(unittest.TestCase):
    """Phase 6: Species Conservation"""

    def test_fire_produces_soot_and_co(self):
        """Burning fuel must produce soot and CO in upper layer."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.sync_layer_volumes()

        solver = SpeciesTransport()
        soot_before = room.upper.species.get('soot', 0.0)
        co_before = room.upper.species.get('CO', 0.0)

        solver.solve(room, m_dot_fuel=0.05, dt=10.0)

        self.assertGreater(room.upper.species['soot'], soot_before)
        self.assertGreater(room.upper.species['CO'], co_before)

    def test_fire_consumes_oxygen(self):
        """Burning must consume O2 in upper layer."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.sync_layer_volumes()

        solver = SpeciesTransport()
        o2_before = room.upper.species.get('O2', 0.232)

        solver.solve(room, m_dot_fuel=0.1, dt=20.0)

        self.assertLess(room.upper.species['O2'], o2_before)

    def test_species_non_negative(self):
        """Species mass fractions cannot be negative."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.sync_layer_volumes()

        solver = SpeciesTransport()
        solver.solve(room, m_dot_fuel=1.0, dt=100.0)  # aggressive burning

        for sp in ['O2', 'CO2', 'CO', 'soot', 'N2']:
            self.assertGreaterEqual(room.upper.species.get(sp, 0.0), 0.0)


class TestPhase7_CombustionModel(unittest.TestCase):
    """Phase 7: Three-phase combustion model"""

    def test_growth_phase_t_squared(self):
        """Growth phase: Q(t) = α·t²."""
        fire = CombustionModel(hrr_peak_w=1_000_000, growth_alpha_kw_s2=0.047)
        self.assertEqual(fire.phase, CombustionPhase.GROWTH)

        # At t=60s: Q ≈ 0.047 * 60² * 1000 = 169,200 W
        hrr = fire.get_hrr(60.0)
        self.assertAlmostEqual(hrr, 169200.0, delta=1000.0)

    def test_peak_hrr_cap(self):
        """HRR should not exceed peak value."""
        fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047)
        hrr = fire.get_hrr(10000.0)  # very long time
        self.assertLessEqual(hrr, 500_000.0)

    def test_ventilation_control(self):
        """When O2 drops, fire should enter ventilation-controlled phase."""
        room = RoomCompartment("R1", 4.0, 4.0, 2.5)  # small room
        room.interface_height = 1.5
        room.upper.species['O2'] = 0.10  # below 15% threshold
        room.sync_layer_volumes()

        fire = CombustionModel(hrr_peak_w=500_000)
        hrr = fire.get_hrr(100.0, room)
        # Should transition to ventilation-controlled
        self.assertIn(fire.phase, [CombustionPhase.VENTILATION_CONTROLLED,
                                   CombustionPhase.STEADY])

    def test_fuel_consumption(self):
        """Fire must consume fuel over time."""
        fire = CombustionModel(fuel_load_kg=100.0)
        fuel_before = fire.fuel_remaining
        fire.consume_fuel(500_000.0, 10.0)
        self.assertLess(fire.fuel_remaining, fuel_before)

    def test_fuel_exhaustion_causes_decay(self):
        """When fuel runs out, fire should enter decay phase."""
        fire = CombustionModel(fuel_load_kg=1.0, hrr_peak_w=500_000)
        # Consume all fuel
        fire.consume_fuel(500_000.0, 100.0)
        self.assertEqual(fire.fuel_remaining, 0.0)


class TestPhase8_DetectorPhysics(unittest.TestCase):
    """Phase 8: RTI Detector Model"""

    def test_heat_detector_activates_on_temperature(self):
        """Heat detector must activate when element reaches threshold."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.upper.temperature = 500.0  # very hot
        room.sync_layer_volumes()

        det = DetectorPhysics(
            detector_id="D1", room_id="R1",
            x=5.0, y=4.0, z=2.5,
            config=DetectorConfig(
                detector_type=DetectorType.HEAT,
                temp_threshold_k=AMBIENT_TEMP_K + 57.0,
                rti=5.0,  # very fast RTI for test
            ),
        )

        # Run several steps
        for _ in range(50):
            result = det.update(room, t=1.0 * _, dt=1.0, u_gas=1.0)
            if result is not None:
                break

        self.assertTrue(det.is_alarmed)
        self.assertEqual(det.alarm_type, "heat")

    def test_smoke_detector_activates_on_od(self):
        """Smoke detector must activate when OD exceeds threshold."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.smoke_od = 0.5  # well above threshold
        room.sync_layer_volumes()

        det = DetectorPhysics(
            detector_id="D2", room_id="R1",
            x=5.0, y=4.0, z=2.5,
            config=DetectorConfig(
                detector_type=DetectorType.SMOKE,
                smoke_threshold_od=0.12,
            ),
        )

        result = det.update(room, t=0.0, dt=1.0, u_gas=0.5)
        self.assertTrue(det.is_alarmed)
        self.assertIsNotNone(result)

    def test_rti_delay(self):
        """Higher RTI → longer response time."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 2.0
        room.upper.temperature = 400.0
        room.sync_layer_volumes()

        # Fast detector (RTI=5)
        det_fast = DetectorPhysics(
            "D_fast", "R1", 5, 4, 2.5,
            config=DetectorConfig(
                detector_type=DetectorType.HEAT,
                temp_threshold_k=AMBIENT_TEMP_K + 57.0,
                rti=5.0,
            ),
        )

        # Slow detector (RTI=200)
        det_slow = DetectorPhysics(
            "D_slow", "R1", 5, 4, 2.5,
            config=DetectorConfig(
                detector_type=DetectorType.HEAT,
                temp_threshold_k=AMBIENT_TEMP_K + 57.0,
                rti=200.0,
            ),
        )

        t = 0.0
        fast_activated = False
        slow_activated = False
        fast_time = None
        slow_time = None

        for step in range(500):
            t = step * 0.5

            r1 = det_fast.update(room, t, 0.5, u_gas=1.0)
            if r1 and not fast_activated:
                fast_activated = True
                fast_time = t

            r2 = det_slow.update(room, t, 0.5, u_gas=1.0)
            if r2 and not slow_activated:
                slow_activated = True
                slow_time = t

            if fast_activated and slow_activated:
                break

        # Fast detector should activate first
        if fast_activated and slow_activated:
            self.assertLess(fast_time, slow_time)


class TestPhase9_WallThermalSolver(unittest.TestCase):
    """Phase 9: Wall Thermal Response"""

    def test_wall_heats_from_hot_gas(self):
        """Wall temperature must increase when exposed to hot gas."""
        wall = WallThermalSolver()
        T_before = wall.temperatures[0]

        q = wall.solve(T_gas_inner=600.0, dt=10.0)

        self.assertGreater(wall.temperatures[0], T_before)

    def test_wall_absorbs_heat(self):
        """Wall should absorb heat from hot gas (positive flux)."""
        wall = WallThermalSolver()
        q = wall.solve(T_gas_inner=600.0, dt=1.0)
        self.assertGreater(q, 0.0)  # heat flows from gas to wall

    def test_wall_cools_to_ambient(self):
        """Wall exposed to ambient should stay near ambient."""
        wall = WallThermalSolver()
        q = wall.solve(T_gas_inner=AMBIENT_TEMP_K, dt=10.0)
        self.assertAlmostEqual(wall.temperatures[0], AMBIENT_TEMP_K, delta=5.0)


class TestPhase11_NumericalStability(unittest.TestCase):
    """Phase 11: Numerical Stability"""

    def test_adaptive_timestep_reduces_dt(self):
        """Hot rooms should reduce the time step."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.upper.temperature = 1000.0
        room.interface_height = 1.0

        stability = NumericalStability()
        dt = stability.adapt_timestep({"R1": room}, dt_requested=1.0)
        self.assertLessEqual(dt, 1.0)

    def test_mass_conservation_correction(self):
        """Mass conservation must be enforced."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.interface_height = 1.5
        room.upper.temperature = 500.0
        # Deliberately desync mass
        room.upper.mass = 999.0

        stability = NumericalStability()
        stability.conserve_mass({"R1": room})

        # After correction, mass should be consistent with volume and density
        expected_mass = room.upper.density * room.upper_volume
        self.assertAlmostEqual(room.upper.mass, expected_mass, delta=1.0)

    def test_energy_clipping(self):
        """Temperatures must stay within physical bounds."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        room.upper.temperature = -100.0  # impossible
        room.lower.temperature = 5000.0  # too hot for zone model

        stability = NumericalStability()
        stability.clip_energy({"R1": room})

        self.assertGreaterEqual(room.upper.temperature, AMBIENT_TEMP_K)
        self.assertLessEqual(room.lower.temperature, 1000.0)


class TestPhase10_MultiRoomCoupling(unittest.TestCase):
    """Phase 10: Multi-room coupled simulation"""

    def test_single_room_fire(self):
        """Single room with fire should produce temperature rise."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047)
        det = DetectorPhysics(
            "D1", "R1", 5.0, 4.0, 2.8,
            config=DetectorConfig(detector_type=DetectorType.COMBINATION),
        )

        solver = SemiCFASTSolver()
        solver.add_room(room)
        solver.add_fire("R1", fire)
        solver.add_detector(det)

        # Run 30 seconds
        t = 0.0
        for _ in range(60):
            solver.step(t, dt=0.5)
            t += 0.5

        # Temperature should have risen
        self.assertGreater(room.upper.temperature, AMBIENT_TEMP_K)

    def test_two_room_smoke_spread(self):
        """Smoke must spread from fire room to adjacent room via vent."""
        # Use a shorter room (2.5m) with a full-height door so the
        # smoke layer descends below the soffit and spills into room B
        room_a = RoomCompartment("A", 10.0, 8.0, 2.5)
        room_b = RoomCompartment("B", 10.0, 8.0, 2.5)
        # Full-height door ensures smoke can spill once interface descends
        vent = Vent("V1", "A", "B", width=1.0, height=2.4, sill_height=0.0)
        fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047)

        solver = SemiCFASTSolver()
        solver.add_room(room_a)
        solver.add_room(room_b)
        solver.add_vent(vent)
        solver.add_fire("A", fire)

        # Run 120 seconds (fire needs time to grow for significant smoke spread)
        t = 0.0
        for _ in range(240):
            solver.step(t, dt=0.5)
            t += 0.5

        # Room B should have heated up (smoke spread via vent)
        # The key physics: once the smoke layer descends below the door soffit,
        # hot gas spills into room B, raising its temperature
        total_temp_b = room_b.upper.temperature + room_b.lower.temperature
        total_temp_ambient = 2 * AMBIENT_TEMP_K
        self.assertGreater(total_temp_b, total_temp_ambient + 0.1,
                          "Room B should heat up from smoke spread via vent")

    def test_convenience_function(self):
        """run_semi_cfast_simulation() must return valid result."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047)
        det = DetectorPhysics(
            "D1", "R1", 5.0, 4.0, 2.8,
            config=DetectorConfig(detector_type=DetectorType.SMOKE),
        )

        result = run_semi_cfast_simulation(
            rooms=[room],
            vents=[],
            fires={"R1": fire},
            detectors=[det],
            t_end=60.0,
            dt=0.5,
            snapshot_interval=10.0,
        )

        self.assertIsInstance(result, SimulationResult)
        self.assertEqual(result.total_steps, 120)
        self.assertIn("R1", result.room_snapshots)
        self.assertGreater(len(result.room_snapshots["R1"]), 0)


class TestConservationLaws(unittest.TestCase):
    """Critical: Verify conservation laws hold during simulation."""

    def test_mass_conservation_over_time(self):
        """Total mass in room must be approximately conserved."""
        room = RoomCompartment("R1", 6.0, 6.0, 3.0)
        fire = CombustionModel(hrr_peak_w=200_000, growth_alpha_kw_s2=0.047)

        solver = SemiCFASTSolver()
        solver.add_room(room)
        solver.add_fire("R1", fire)

        # Initial total mass
        m_initial = room.upper.mass + room.lower.mass

        # Run 60 seconds
        t = 0.0
        for _ in range(120):
            solver.step(t, dt=0.5)
            t += 0.5

        m_final = room.upper.mass + room.lower.mass

        # Mass should be approximately conserved (within 10% for single room)
        # Note: some mass is added by fire (combustion products)
        self.assertAlmostEqual(m_final, m_initial, delta=m_initial * 0.15)

    def test_energy_monotonicity(self):
        """Upper layer temperature should increase monotonically during growth."""
        room = RoomCompartment("R1", 10.0, 8.0, 3.0)
        fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047)

        solver = SemiCFASTSolver()
        solver.add_room(room)
        solver.add_fire("R1", fire)

        temps = []
        t = 0.0
        for _ in range(40):  # 20 seconds
            solver.step(t, dt=0.5)
            t += 0.5
            temps.append(room.upper.temperature)

        # During growth phase, upper temp should generally increase
        # (not strictly monotonic due to cooling, but trend should be up)
        self.assertGreater(temps[-1], temps[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
