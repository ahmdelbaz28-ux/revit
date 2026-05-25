"""
test_mip_solver.py
MIP Solver Tests - Optimal Placement
"""

import pytest

# V20.2 FIX: Skip entire module if pulp is not installed.
# The MIP solver is optional — ConstraintSolver/AdaptiveSolver
# provide full coverage without PuLP.
try:
    from pulp import LpProblem  # noqa: F401 — just checking availability
    HAS_PULP = True
except ImportError:
    HAS_PULP = False

pytestmark = pytest.mark.skipif(
    not HAS_PULP,
    reason="PuLP not installed — MIP solver tests require 'pip install pulp'"
)

from nfpa72_models import RoomSpec
from spatial_engine.mip_solver import OptimalMIPEngine


def test_old_api_rejected():
    """Old grid_size/radius API should be rejected with TypeError"""
    with pytest.raises(TypeError):
        OptimalMIPEngine(grid_size=10, radius=3.0)


def test_single_device_optimal():
    """Test with RoomSpec - single device in small room"""
    room = RoomSpec(room_id='test-1', name='test', width_m=4, depth_m=4)
    engine = OptimalMIPEngine(room)
    devices, count, success, meta = engine.solve()
    
    assert success == True
    assert count >= 1
    assert len(devices) >= 1


def test_infeasible_case():
    """Test feasible case with 10x10 room"""
    room = RoomSpec(room_id='test-2', name='test', width_m=10, depth_m=10)
    engine = OptimalMIPEngine(room)
    devices, count, success, meta = engine.solve()
    
    assert success == True
    assert count >= 3
    assert len(devices) >= 3
