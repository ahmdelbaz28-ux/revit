"""
tests/test_v13_class_a_routing.py
=================================
Unit tests for Class A loop routing with >=1m separation per NFPA 72 S12.2.2.
Tests EliteClassARouter (canonical) and EliteGlobalRouter (wrapper).
"""
import math
import unittest
from fireai.core.routing_engine_v10 import EliteClassARouter, ArchitecturalWall, RouteSegment


class TestEliteClassARouter(unittest.TestCase):
    """Test the canonical Class A + Firestopping routing engine."""

    def setUp(self):
        self.router = EliteClassARouter(width=30.0, length=20.0, resolution=0.5)
        self.fire_wall = ArchitecturalWall((15.0, 0.0), (15.0, 20.0), fire_rated=True)
        self.normal_wall = ArchitecturalWall((0.0, 10.0), (15.0, 10.0), fire_rated=False)

    def test_class_a_loop_generates_both_paths(self):
        """Outgoing and return paths must both be generated."""
        result = self.router.generate_class_a_loop((2.0, 2.0), [(25.0, 18.0)])
        self.assertIn("outgoing_class_a", result)
        self.assertIn("return_class_a", result)
        out_seg = result["outgoing_class_a"]
        ret_seg = result["return_class_a"]
        self.assertIsInstance(out_seg, RouteSegment)
        self.assertIsInstance(ret_seg, RouteSegment)
        self.assertGreater(len(out_seg.path), 0)
        self.assertGreater(len(ret_seg.path), 0)

    def test_class_a_segment_types(self):
        """Outgoing = CLASS_A_OUT, Return = CLASS_A_RETURN."""
        result = self.router.generate_class_a_loop((2.0, 2.0), [(25.0, 18.0)])
        self.assertEqual(result["outgoing_class_a"].class_type, "CLASS_A_OUT")
        self.assertEqual(result["return_class_a"].class_type, "CLASS_A_RETURN")

    def test_class_a_middle_separation(self):
        """Middle-section separation must be >=1.0m per NFPA 72 S12.2.2."""
        result = self.router.generate_class_a_loop((2.0, 2.0), [(25.0, 18.0)])
        out_seg = result["outgoing_class_a"]
        ret_seg = result["return_class_a"]
        # Skip terminal connection zones (first/last 5 waypoints)
        out_mid = out_seg.path[5:-5]
        ret_mid = ret_seg.path[5:-5]
        if out_mid and ret_mid:
            min_sep = min(
                math.hypot(ox - rx, oy - ry)
                for ox, oy in out_mid
                for rx, ry in ret_mid
            )
            self.assertGreaterEqual(min_sep, 1.0,
                f"Middle separation {min_sep:.2f}m < 1.0m NFPA 72 S12.2.2")

    def test_class_a_with_fire_walls_detects_firestops(self):
        """Fire-rated wall penetrations must be detected."""
        self.router.inject_structural_obstructions([self.fire_wall])
        result = self.router.generate_class_a_loop((2.0, 2.0), [(25.0, 18.0)])
        out_firestops = result["outgoing_class_a"].firestop_nodes
        ret_firestops = result["return_class_a"].firestop_nodes
        # At least the outgoing path should cross the fire wall at x=15
        total_firestops = len(out_firestops) + len(ret_firestops)
        self.assertGreater(total_firestops, 0,
            "Expected fire-rated wall penetration detection")

    def test_class_a_empty_devices_returns_empty(self):
        """No devices = empty result."""
        result = self.router.generate_class_a_loop((2.0, 2.0), [])
        self.assertEqual(result, {})

    def test_class_a_path_length_positive(self):
        """Both paths must have positive length."""
        result = self.router.generate_class_a_loop((2.0, 2.0), [(25.0, 18.0)])
        self.assertGreater(result["outgoing_class_a"].length_m, 0)
        self.assertGreater(result["return_class_a"].length_m, 0)

    def test_terminal_connection_zone_exemption(self):
        """First/last waypoints of outgoing and return share same terminals.
        This is physically correct — both conductors connect to same devices."""
        result = self.router.generate_class_a_loop((2.0, 2.0), [(25.0, 18.0)])
        out_seg = result["outgoing_class_a"]
        ret_seg = result["return_class_a"]
        # Return path starts at terminal, ends at panel (reversed)
        self.assertAlmostEqual(ret_seg.path[0][0], 25.0, delta=1.0)
        self.assertAlmostEqual(ret_seg.path[0][1], 18.0, delta=1.0)


class TestEliteGlobalRouterWrapper(unittest.TestCase):
    """Test the wrapper that delegates to EliteClassARouter."""

    def test_wrapper_returns_decision_provenance(self):
        """Wrapper must return DecisionProvenance with audit trail."""
        from fireai.core.routing_global_class_a import EliteGlobalRouter
        gr = EliteGlobalRouter(global_bounds=(0, 0, 30, 20), resolution=0.5)
        dp = gr.route_class_a_loop(panel=(2.0, 2.0), terminal_device=(25.0, 18.0))
        self.assertEqual(dp.decision_type, "class_a_route_creation")
        self.assertEqual(len(dp.rules_applied), 1)
        self.assertEqual(dp.confidence.overall.value, "HIGH")
        self.assertIsNotNone(dp.value)
        self.assertIn("out_path", dp.value)
        self.assertIn("return_path", dp.value)


if __name__ == "__main__":
    unittest.main()
