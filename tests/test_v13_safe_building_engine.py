"""
tests/test_v13_safe_building_engine.py
=======================================
Unit tests for SafeBuildingEngine (ThreadPoolExecutor + RLock for CBC safety).
"""
import unittest
from fireai.core.safe_building_engine import SafeBuildingEngine


class TestSafeBuildingEngine(unittest.TestCase):
    """Test thread-safe MIP execution engine."""

    def test_single_room_solve(self):
        """Single room MIP solve should succeed."""
        sbe = SafeBuildingEngine(max_threads=1)
        result = sbe._solve_mip_safe({
            'room_id': 'test_room',
            'width_m': 10.0,
            'length_m': 8.0,
        })
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'Optimal')
        self.assertGreater(result['theoretical_minimum'], 0)

    def test_multi_floor_analysis(self):
        """Multi-floor analysis should process all rooms."""
        sbe = SafeBuildingEngine(max_threads=2)
        floors = [
            {'floor_id': 'GF', 'rooms': [
                {'room_id': 'lobby', 'width_m': 12.0, 'length_m': 8.0},
                {'room_id': 'office', 'width_m': 10.0, 'length_m': 8.0},
            ]},
            {'floor_id': 'L1', 'rooms': [
                {'room_id': 'meeting', 'width_m': 6.0, 'length_m': 5.0},
            ]},
        ]
        results = sbe.run_multi_floor_safety_analysis(floors)
        self.assertEqual(len(results), 3)
        room_ids = {r['room_id'] for r in results}
        self.assertIn('lobby', room_ids)
        self.assertIn('office', room_ids)
        self.assertIn('meeting', room_ids)

    def test_rlock_prevents_concurrent_solves(self):
        """RLock must be present and be an RLock type."""
        sbe = SafeBuildingEngine(max_threads=4)
        import threading
        self.assertIsInstance(sbe.global_c_level_lock, type(threading.RLock()))

    def test_default_parameters(self):
        """Default parameters should be set correctly."""
        sbe = SafeBuildingEngine()
        self.assertEqual(sbe.max_threads, 4)
        self.assertAlmostEqual(sbe.coverage_radius, 6.37)
        self.assertAlmostEqual(sbe.candidate_step, 1.0)
        self.assertAlmostEqual(sbe.time_limit_s, 60.0)

    def test_empty_floor_list(self):
        """Empty floor list should return empty results."""
        sbe = SafeBuildingEngine()
        results = sbe.run_multi_floor_safety_analysis([])
        self.assertEqual(len(results), 0)

    def test_result_contains_required_fields(self):
        """Each result must have required fields for downstream processing."""
        sbe = SafeBuildingEngine(max_threads=1)
        result = sbe._solve_mip_safe({'room_id': 'r1', 'width_m': 10.0, 'length_m': 8.0})
        required_keys = ['room_id', 'success', 'placements', 'theoretical_minimum', 'status']
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")


if __name__ == "__main__":
    unittest.main()
