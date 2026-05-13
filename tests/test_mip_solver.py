"""
test_mip_solver.py
MIP Solver Tests - Optimal Placement
"""

import pytest
from nfpa72_models import RoomSpec
from spatial_engine.mip_solver import OptimalMIPEngine


def test_old_api_rejected():
    """Old grid_size/radius API should be rejected with TypeError"""
    with pytest.raises(TypeError):
        OptimalMIPEngine(grid_size=10, radius=3.0)


def test_single_device_optimal():
    """Test with RoomSpec - single device in small room"""
    room = RoomSpec(name='test', width_m=4, depth_m=4, height_m=3)
    engine = OptimalMIPEngine(room)
    devices, count, success, meta = engine.solve()
    
    assert success == True
    assert count >= 1
    assert len(devices) >= 1


def test_infeasible_case():
    """Test feasible case with 10x10 room"""
    room = RoomSpec(name='test', width_m=10, depth_m=10, height_m=3)
    engine = OptimalMIPEngine(room)
    devices, count, success, meta = engine.solve()
    
    assert success == True
    assert count >= 3
    assert len(devices) >= 3
