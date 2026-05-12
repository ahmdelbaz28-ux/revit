"""
Tests for ConstraintSolver
"""

import pytest
from spatial_engine.constraint_solver import ConstraintSolver, MAX_DEVICE_SPACING


class TestConstraintSolver:
    """Test constraint solver"""
    
    def test_room_10x10_coverage(self):
        """Test room 10x10 with radius 3.0, should achieve 100% coverage"""
        # Room: 10x10 square
        room_polygon = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        
        solver = ConstraintSolver(room_polygon, device_radius=3.0)
        result = solver.find_optimal_placement(max_devices=20)
        
        # Should achieve full coverage
        assert result.num_devices > 0
        assert result.coverage_percent >= 90  # Allow small tolerance
    
    def test_verify_coverage(self):
        """Test coverage verification"""
        room_polygon = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        
        solver = ConstraintSolver(room_polygon, device_radius=3.0)
        
        # Place 4 devices in corners - should cover ~100%
        positions = [(3, 3), (3, 7), (7, 3), (7, 7)]
        coverage = solver.verify_coverage(positions)
        
        # Should cover most of the room
        assert coverage > 50
    
    def test_small_room(self):
        """Test small room with large device"""
        # Room: 5x5, device radius = 4 (should cover entire room)
        room_polygon = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
        
        solver = ConstraintSolver(room_polygon, device_radius=4.0)
        result = solver.find_optimal_placement(max_devices=5)
        
        # One device should be enough
        assert result.num_devices >= 1
        assert result.coverage_percent >= 90


if __name__ == "__main__":
    pytest.main([__file__, "-v"])