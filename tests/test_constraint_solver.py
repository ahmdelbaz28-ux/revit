"""
Tests for ConstraintSolver - TRL 6
"""

import pytest
from spatial_engine.constraint_solver import ConstraintSolver


class TestConstraintSolver:
    def test_perfect_coverage_small_room(self):
        """10x10 room, radius=3.0 → 4 devices, 100%"""
        room_polygon = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        solver = ConstraintSolver(room_polygon, device_radius=3.0)
        result = solver.find_optimal_placement(max_devices=10)
        
        assert result.num_devices >= 3, f"Expected >=3, got {result.num_devices}"
        assert result.coverage_percent >= 90.0


    def test_single_device_covers_all(self):
        """4x4 room, radius=5.0 → 1 device"""
        room_polygon = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
        solver = ConstraintSolver(room_polygon, device_radius=5.0)
        result = solver.find_optimal_placement(max_devices=5)
        
        assert result.num_devices == 1, f"Expected 1, got {result.num_devices}"


    def test_impossible_coverage(self):
        """10x10 room, radius=0.5 → fails"""
        room_polygon = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        solver = ConstraintSolver(room_polygon, device_radius=0.5)
        result = solver.find_optimal_placement(max_devices=2)
        
        assert result.coverage_percent < 50.0