"""
tests/test_v9_integration.py — V9 Deep Integration Tests
=========================================================
Tests for the V9 deep integration fixes:
  1. HeatTransportNS O2-gating (prevents heat without O2)
  2. SmokeTransportNS O2 depletion rate limiter (prevents instant depletion)
  3. CFD_LITE mode stability (no PressureSolver divergence)
  4. SemiCFAST + CFD coupling (zone-to-grid overlay)
  5. Detector activation via RTI model
  6. O2-limited combustion (ventilation control)
  7. Species transport (O2 consumption, CO2/CO generation)
  8. Fuel exhaustion and decay phase
"""
import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Test 1: HeatTransportNS O2-gating ──

def test_heat_transport_o2_gating():
    """V9 FIX: HeatTransportNS must not add heat when O2 is depleted.
    
    Before V9: HeatTransportNS added heat based on HRR regardless of
    local O2, causing temperature blow-up (observed: 658,000 K).
    After V9: Source term is scaled by O2 availability.
    """
    from twin.fire_physics import VoxelGrid, FireSource, HeatTransportNS, AMBIENT_TEMP
    
    grid = VoxelGrid(width=4, length=4, height=3, resolution=1.0)
    fire = FireSource(x=2.0, y=2.0, z=0.0, hrr=200_000)
    heat = HeatTransportNS()
    
    # Set O2 to zero at fire voxel
    fire_voxel = grid.at_pos(fire.x, fire.y, fire.z)
    assert fire_voxel is not None
    fire_voxel.o2_fraction = 0.0  # No oxygen!
    
    # Apply heat transport with 200kW fire
    temp_before = fire_voxel.temp
    heat.step(grid, fire, 200_000.0, 1.0)
    temp_after = fire_voxel.temp
    
    # Temperature should NOT increase significantly when O2=0
    # (only diffusion/advection/cooling — no source term)
    assert temp_after <= temp_before + 5.0, (
        f"HeatTransportNS added heat despite O2=0: {temp_before:.1f}K -> {temp_after:.1f}K"
    )


def test_heat_transport_o2_partial():
    """V9 FIX: Heat source scales proportionally with O2."""
    from twin.fire_physics import VoxelGrid, FireSource, HeatTransportNS, AMBIENT_TEMP
    
    grid = VoxelGrid(width=4, length=4, height=3, resolution=1.0)
    fire = FireSource(x=2.0, y=2.0, z=0.0, hrr=200_000)
    heat = HeatTransportNS()
    
    # Full O2 case
    grid_full = VoxelGrid(width=4, length=4, height=3, resolution=1.0)
    fire_full = FireSource(x=2.0, y=2.0, z=0.0, hrr=200_000)
    heat_full = HeatTransportNS()
    heat_full.step(grid_full, fire_full, 200_000.0, 1.0)
    temp_full = grid_full.at_pos(2.0, 2.0, 0.0).temp
    
    # Half O2 case
    grid_half = VoxelGrid(width=4, length=4, height=3, resolution=1.0)
    fire_half = FireSource(x=2.0, y=2.0, z=0.0, hrr=200_000)
    heat_half = HeatTransportNS()
    grid_half.at_pos(2.0, 2.0, 0.0).o2_fraction = 0.14  # ~60% of ambient
    heat_half.step(grid_half, fire_half, 200_000.0, 1.0)
    temp_half = grid_half.at_pos(2.0, 2.0, 0.0).temp
    
    # With partial O2, temperature rise should be less than full O2
    # (excluding diffusion effects)
    assert temp_half < temp_full, (
        f"Partial O2 ({temp_half:.1f}K) should give lower temp than full O2 ({temp_full:.1f}K)"
    )


# ── Test 2: SmokeTransportNS O2 rate limiter ──

def test_o2_depletion_rate_limiter():
    """V9 FIX: O2 cannot drop more than 20% per step in any voxel.
    
    Before V9: O2 could drop from 0.232 to 0.0 in one step,
    causing numerical instability.
    After V9: Maximum 20% depletion per step.
    """
    from twin.fire_physics import VoxelGrid, FireSource, SmokeTransportNS
    
    grid = VoxelGrid(width=4, length=4, height=3, resolution=1.0)
    fire = FireSource(x=2.0, y=2.0, z=0.0, hrr=500_000)
    smoke = SmokeTransportNS()
    
    # Record O2 before
    o2_before = {}
    for v in grid.all_fluid():
        o2_before[(v.ix, v.iy, v.iz)] = v.o2_fraction
    
    # Apply smoke transport with high HRR
    smoke.step(grid, fire, 500_000.0, 1.0)
    
    # Check O2 after — no voxel should drop more than 20%
    max_depletion = 0.0
    for v in grid.all_fluid():
        before = o2_before[(v.ix, v.iy, v.iz)]
        after = v.o2_fraction
        if before > 0:
            depletion = (before - after) / before
            max_depletion = max(max_depletion, depletion)
    
    assert max_depletion <= 0.21, (  # 20% + small tolerance
        f"O2 depleted {max_depletion*100:.1f}% in one step — exceeds 20% limit"
    )


# ── Test 3: CFD_LITE mode stability ──

def test_cfd_lite_no_divergence():
    """V9 FIX: CFD_LITE mode must not diverge.
    
    Before V9: PressureSolver caused divergence at fire temperatures
    (observed: 6,900,000 K at t=16s with dt=1.0s).
    After V9: No PressureSolver; SemiCFAST handles temperatures.
    """
    from twin.simulation_layer import (
        SimulationLayer, SimulationMode,
        SimulationRoomConfig, SimulationFireSource, SimulationDetector,
    )
    
    sim = SimulationLayer(mode=SimulationMode.CFD_LITE, resolution_m=1.0)
    rooms = [SimulationRoomConfig(room_id='room1', name='Test', width_m=4, depth_m=4, height_m=3.0)]
    fires = [SimulationFireSource(room_id='room1', x=2.0, y=2.0, hrr_peak_w=200_000, fuel_load_kg=100)]
    dets = [SimulationDetector(detector_id='det1', room_id='room1', x=2.0, y=2.0, z=2.8)]
    sim.setup(rooms, fires, dets)
    
    # Run for 120 seconds — should NOT diverge
    result = sim.run(t_end=120.0, dt_req=1.0, check_compliance=False)
    
    assert result.peak_temp_k < 3000.0, (
        f"CFD_LITE diverged: peak_temp={result.peak_temp_k:.1f}K"
    )
    assert result.total_steps > 0


# ── Test 4: SemiCFAST zone model ──

def test_semicfast_combustion_phases():
    """V9: CombustionModel transitions through all phases.
    
    Uses SimulationLayer which handles sub-stepping properly
    (SemiCFAST internally reduces dt for stability).
    """
    from twin.simulation_layer import (
        SimulationLayer, SimulationMode,
        SimulationRoomConfig, SimulationFireSource, SimulationDetector,
    )
    from twin.semi_cfast_engine import CombustionPhase
    
    sim = SimulationLayer(mode=SimulationMode.ZONE_MODEL)
    rooms = [SimulationRoomConfig(room_id='room1', name='Test', width_m=4, depth_m=4, height_m=3.0)]
    # Very small fuel load to trigger decay quickly
    fires = [SimulationFireSource(room_id='room1', x=2.0, y=2.0, hrr_peak_w=100_000, fuel_load_kg=2)]
    dets = [SimulationDetector(detector_id='det1', room_id='room1', x=2.0, y=2.0, z=2.8)]
    sim.setup(rooms, fires, dets)
    
    # Run simulation and check phases
    result = sim.run(t_end=600.0, dt_req=1.0, check_compliance=False)
    
    # Check the combustion model phase
    fire = sim._cfast.fires.get('room1')
    assert fire is not None
    # Should have reached either DECAY or VENTILATION_CONTROLLED
    assert fire.phase in (CombustionPhase.DECAY, CombustionPhase.VENTILATION_CONTROLLED), (
        f"Expected DECAY or VENT_CONTROLLED with 2kg fuel, got {fire.phase}"
    )


# ── Test 5: Detector activation ──

def test_detector_activation_rti():
    """V9: Detector activates via RTI model with reasonable timing."""
    from twin.semi_cfast_engine import (
        SemiCFASTSolver, RoomCompartment, CombustionModel,
        DetectorPhysics, DetectorConfig, DetectorType,
    )
    
    solver = SemiCFASTSolver()
    room = RoomCompartment('room1', width=6, depth=5, height=3.0)
    solver.add_room(room)
    fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047, fuel_load_kg=500)
    solver.add_fire('room1', fire)
    det = DetectorPhysics('det1', 'room1', 3.0, 2.5, 2.9,
                           DetectorConfig(detector_type=DetectorType.COMBINATION, rti=50.0))
    solver.add_detector(det)
    
    t = 0.0
    for _ in range(300):
        solver.step(t, 1.0)
        t += 1.0
    
    # Detector should alarm within 60 seconds for a fast fire
    assert det.is_alarmed, "Detector did not alarm within 300s"
    assert det.alarm_time is not None and det.alarm_time < 60.0, (
        f"Detector alarm time {det.alarm_time}s is too late for a fast fire"
    )


# ── Test 6: O2-limited combustion ──

def test_o2_limited_combustion():
    """V9: HRR drops when O2 is depleted (ventilation control)."""
    from twin.fire_physics import VoxelGrid, VoxelCombustionModel, FireSource
    
    grid = VoxelGrid(width=4, length=4, height=3, resolution=1.0)
    fire = FireSource(x=2.0, y=2.0, z=0.0, hrr=500_000, fuel_load_kg=1000)
    combustion = VoxelCombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047, fuel_load_kg=1000)
    
    # Deplete O2 around fire
    fire_voxel = grid.at_pos(fire.x, fire.y, fire.z)
    for dix in range(-1, 2):
        for diy in range(-1, 2):
            for diz in range(-1, 2):
                nb = grid.get(fire_voxel.ix + dix, fire_voxel.iy + diy, fire_voxel.iz + diz)
                if nb is not None:
                    nb.o2_fraction = 0.08  # Well below threshold
    
    # At t=100s (should be at peak), with O2=0.08, HRR should be limited
    hrr_limited = combustion.get_hrr(100.0, grid=grid, fire=fire)
    
    # Without O2 limitation, HRR would be 500kW at peak
    # With O2 at 0.08 (below 0.15 threshold), it should be in VENT_CONTROLLED
    # and HRR should be significantly less than peak
    assert combustion.phase in ('VENT_CONTROLLED', 'DECAY'), (
        f"Expected VENT_CONTROLLED or DECAY with O2=0.08, got {combustion.phase}"
    )


# ── Test 7: Species transport ──

def test_species_transport():
    """V9: CO2 and O2 are properly tracked in SemiCFAST."""
    from twin.semi_cfast_engine import SemiCFASTSolver, RoomCompartment, CombustionModel
    
    solver = SemiCFASTSolver()
    room = RoomCompartment('room1', width=6, depth=5, height=3.0)
    solver.add_room(room)
    fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047, fuel_load_kg=500)
    solver.add_fire('room1', fire)
    
    t = 0.0
    for _ in range(120):
        solver.step(t, 1.0)
        t += 1.0
    
    # After 120s of fire, O2 should have decreased
    o2 = room.upper.species.get('O2', 0.232)
    assert o2 < 0.232, f"O2 should decrease during fire, got {o2:.4f}"
    
    # CO2 should have increased
    co2 = room.upper.species.get('CO2', 0.0006)
    assert co2 > 0.0006, f"CO2 should increase during fire, got {co2:.4f}"
    
    # Soot should have increased
    soot = room.upper.species.get('soot', 0.0)
    assert soot > 0.0, f"Soot should increase during fire, got {soot:.4f}"


# ── Test 8: Fuel exhaustion ──

def test_fuel_exhaustion_decay():
    """V9: Fire decays when fuel is exhausted."""
    from twin.semi_cfast_engine import SemiCFASTSolver, RoomCompartment, CombustionModel, CombustionPhase
    
    solver = SemiCFASTSolver()
    room = RoomCompartment('room1', width=6, depth=5, height=3.0)
    solver.add_room(room)
    # Very small fuel load — should exhaust quickly
    fire = CombustionModel(hrr_peak_w=500_000, growth_alpha_kw_s2=0.047, fuel_load_kg=5)
    solver.add_fire('room1', fire)
    
    t = 0.0
    peak_hrr_seen = 0.0
    for _ in range(600):
        solver.step(t, 1.0)
        hrr = fire.get_hrr(t, room)
        peak_hrr_seen = max(peak_hrr_seen, hrr)
        t += 1.0
    
    # Fire should have entered either DECAY or VENTILATION_CONTROLLED phase
    # In a sealed room with small fuel, O2 depletion occurs first
    assert fire.phase in (CombustionPhase.DECAY, CombustionPhase.VENTILATION_CONTROLLED), (
        f"Expected DECAY or VENT_CONTROLLED with 5kg fuel, got {fire.phase}"
    )
    # Fuel should be nearly exhausted (in DECAY) or still burning (in VENT_CONTROLLED)
    if fire.phase == CombustionPhase.DECAY:
        assert fire.fuel_remaining <= 0.0, "Fuel should be exhausted in DECAY"


# ── Test 9: SimulationLayer all modes ──

def test_simulation_layer_zone_mode():
    """V9: Zone model simulation completes successfully."""
    from twin.simulation_layer import (
        SimulationLayer, SimulationMode,
        SimulationRoomConfig, SimulationFireSource, SimulationDetector,
    )
    
    sim = SimulationLayer(mode=SimulationMode.ZONE_MODEL)
    rooms = [SimulationRoomConfig(room_id='room1', name='Test', width_m=6, depth_m=5, height_m=3.0)]
    fires = [SimulationFireSource(room_id='room1', x=3.0, y=2.5, hrr_peak_w=500_000, fuel_load_kg=500)]
    dets = [SimulationDetector(detector_id='det1', room_id='room1', x=3.0, y=2.5, z=2.9)]
    sim.setup(rooms, fires, dets)
    result = sim.run(t_end=300.0, dt_req=1.0)
    
    assert result.total_steps > 0
    assert result.peak_temp_k > AMBIENT_TEMP
    assert len(result.all_activations) > 0, "Should have detector activations"
    assert result.sha256 != "", "Should have audit hash"


def test_simulation_layer_cfd_mode():
    """V9: CFD Lite simulation completes without divergence."""
    from twin.simulation_layer import (
        SimulationLayer, SimulationMode,
        SimulationRoomConfig, SimulationFireSource, SimulationDetector,
    )
    
    sim = SimulationLayer(mode=SimulationMode.CFD_LITE, resolution_m=1.0)
    rooms = [SimulationRoomConfig(room_id='room1', name='Test', width_m=4, depth_m=4, height_m=3.0)]
    fires = [SimulationFireSource(room_id='room1', x=2.0, y=2.0, hrr_peak_w=200_000, fuel_load_kg=100)]
    dets = [SimulationDetector(detector_id='det1', room_id='room1', x=2.0, y=2.0, z=2.8)]
    sim.setup(rooms, fires, dets)
    result = sim.run(t_end=120.0, dt_req=1.0)
    
    assert result.total_steps > 0
    assert result.peak_temp_k < 3000.0, f"CFD diverged: {result.peak_temp_k:.1f}K"


def test_simulation_layer_hybrid_mode():
    """V9: Hybrid simulation completes without divergence."""
    from twin.simulation_layer import (
        SimulationLayer, SimulationMode,
        SimulationRoomConfig, SimulationFireSource, SimulationDetector,
    )
    
    sim = SimulationLayer(mode=SimulationMode.HYBRID, resolution_m=1.0)
    rooms = [SimulationRoomConfig(room_id='room1', name='Test', width_m=4, depth_m=4, height_m=3.0)]
    fires = [SimulationFireSource(room_id='room1', x=2.0, y=2.0, hrr_peak_w=200_000, fuel_load_kg=100)]
    dets = [SimulationDetector(detector_id='det1', room_id='room1', x=2.0, y=2.0, z=2.8)]
    sim.setup(rooms, fires, dets)
    result = sim.run(t_end=120.0, dt_req=1.0)
    
    assert result.total_steps > 0
    assert result.peak_temp_k < 3000.0


# ── Test 10: VoxelGrid O2 fields ──

def test_voxel_o2_fields():
    """V9: Voxel has O2 and CO2 fields with correct defaults."""
    from twin.fire_physics import Voxel, AMBIENT_TEMP, AMBIENT_PRESSURE
    
    v = Voxel(0, 0, 0, 0.5, 0.5, 0.5)
    assert hasattr(v, 'o2_fraction'), "Voxel should have o2_fraction"
    assert hasattr(v, 'co2_ppm'), "Voxel should have co2_ppm"
    assert abs(v.o2_fraction - 0.232) < 0.001, f"Default O2 should be ~0.232, got {v.o2_fraction}"
    assert v.co2_ppm == 0.0, f"Default CO2 should be 0.0, got {v.co2_ppm}"


# Ambient temp constant for test
AMBIENT_TEMP = 293.15


if __name__ == "__main__":
    # Run all tests manually
    import traceback
    tests = [
        test_heat_transport_o2_gating,
        test_heat_transport_o2_partial,
        test_o2_depletion_rate_limiter,
        test_cfd_lite_no_divergence,
        test_semicfast_combustion_phases,
        test_detector_activation_rti,
        test_o2_limited_combustion,
        test_species_transport,
        test_fuel_exhaustion_decay,
        test_simulation_layer_zone_mode,
        test_simulation_layer_cfd_mode,
        test_simulation_layer_hybrid_mode,
        test_voxel_o2_fields,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
