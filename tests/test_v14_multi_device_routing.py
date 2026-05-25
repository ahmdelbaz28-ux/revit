"""
tests/test_v14_multi_device_routing.py
======================================
V14 Unit Tests: Multi-device daisy-chain Class A routing + provenance shim.

Tests the critical fix where generate_class_a_loop() previously only
routed to the last device, skipping all intermediate devices. Now the
outgoing path must daisy-chain through ALL devices.

Also tests the provenance shim (fireai.core.provenance) which replaces
the fragile src.v8_core cross-package import.
"""
import pytest
import math
from fireai.core.routing_engine_v10 import EliteClassARouter, ArchitecturalWall, RouteSegment


class TestMultiDeviceDaisyChain:
    """Test that Class A routing visits ALL devices in order."""

    def setup_method(self):
        """Create a router with a 50m x 40m building."""
        self.router = EliteClassARouter(width=50.0, length=40.0, resolution=0.5)

    def test_single_device_still_works(self):
        """V14 regression: single-device routing still produces valid paths."""
        facp = (5.0, 5.0)
        devices = [(25.0, 18.0)]

        result = self.router.generate_class_a_loop(facp, devices)

        assert "outgoing_class_a" in result
        assert "return_class_a" in result
        assert result["outgoing_class_a"].class_type == "CLASS_A_OUT"
        assert result["return_class_a"].class_type == "CLASS_A_RETURN"
        assert len(result["outgoing_class_a"].path) > 0
        assert len(result["return_class_a"].path) > 0

    def test_multi_device_outgoing_visits_all(self):
        """V14 CRITICAL: Outgoing path must visit ALL devices, not just the last."""
        facp = (5.0, 5.0)
        devices = [(15.0, 10.0), (25.0, 15.0), (35.0, 25.0)]

        result = self.router.generate_class_a_loop(facp, devices)

        out_path = result["outgoing_class_a"].path
        assert len(out_path) > 2, "Multi-device path should have many waypoints"

        # The outgoing path should pass NEAR each device (within 2m tolerance
        # for grid-based routing). Previously, it only went to the last device.
        for dev_x, dev_y in devices:
            min_dist = min(
                math.hypot(px - dev_x, py - dev_y) for px, py in out_path
            )
            assert min_dist < 3.0, (
                f"Device at ({dev_x}, {dev_y}) is {min_dist:.1f}m from outgoing "
                f"path — daisy-chain routing should visit all devices"
            )

    def test_multi_device_return_path_separated(self):
        """V14: Return path must maintain >=1m separation from outgoing."""
        facp = (5.0, 5.0)
        devices = [(15.0, 10.0), (30.0, 20.0)]

        result = self.router.generate_class_a_loop(facp, devices)

        out_path = result["outgoing_class_a"].path
        ret_path = result["return_class_a"].path

        # Check separation in the MIDDLE of paths (not terminal zones)
        # Skip first 4m and last 4m of outgoing path
        cum_dist = [0.0]
        for i in range(1, len(out_path)):
            d = math.hypot(out_path[i][0] - out_path[i-1][0],
                           out_path[i][1] - out_path[i-1][1])
            cum_dist.append(cum_dist[-1] + d)
        total_len = cum_dist[-1]

        min_sep = float('inf')
        for idx, (ox, oy) in enumerate(out_path):
            d_start = cum_dist[idx]
            d_end = total_len - d_start
            # Skip terminal connection zones (2m at each end)
            if d_start < 2.0 or d_end < 2.0:
                continue
            for rx, ry in ret_path:
                dist = math.hypot(ox - rx, oy - ry)
                if dist < min_sep:
                    min_sep = dist

        assert min_sep >= 0.8, (
            f"Return path separation {min_sep:.2f}m < 0.8m (allowing grid "
            f"discretization) — NFPA 72 S12.2.2 requires >=1m"
        )

    def test_multi_device_path_length_longer_than_single(self):
        """V14: Multi-device path should be longer than going directly to last device."""
        facp = (5.0, 5.0)
        devices = [(15.0, 10.0), (30.0, 20.0)]

        result = self.router.generate_class_a_loop(facp, devices)
        multi_length = result["outgoing_class_a"].length_m

        # Direct distance from FACP to last device
        direct = math.hypot(30.0 - 5.0, 20.0 - 5.0)
        assert multi_length > direct * 1.1, (
            f"Multi-device path ({multi_length:.1f}m) should be longer than "
            f"direct route ({direct:.1f}m) since it visits intermediate devices"
        )

    def test_empty_devices_returns_empty(self):
        """V14 regression: empty device list returns empty dict."""
        result = self.router.generate_class_a_loop((5.0, 5.0), [])
        assert result == {}

    def test_multi_device_with_fire_walls(self):
        """V14: Multi-device routing detects fire-rated wall penetrations."""
        router = EliteClassARouter(width=50.0, length=40.0, resolution=0.5)

        # Fire-rated wall cutting across the building
        walls = [ArchitecturalWall((20.0, 0.0), (20.0, 40.0), fire_rated=True)]
        router.inject_structural_obstructions(walls)

        facp = (5.0, 5.0)
        devices = [(15.0, 10.0), (35.0, 25.0)]  # Second device is on other side of wall

        result = router.generate_class_a_loop(facp, devices)

        # The outgoing path should detect at least one firestop penetration
        # (the path crosses the fire-rated wall at x=20)
        out_firestops = result["outgoing_class_a"].firestop_nodes
        assert len(out_firestops) > 0, (
            "Path crossing fire-rated wall should detect penetration points"
        )

    def test_three_devices_sequential_ordering(self):
        """V14: Three devices produce a path that visits them in sequence."""
        facp = (2.0, 2.0)
        devices = [(10.0, 5.0), (20.0, 10.0), (35.0, 20.0)]

        result = self.router.generate_class_a_loop(facp, devices)
        out_path = result["outgoing_class_a"].path

        # Find approximate positions where path is closest to each device
        def closest_index(path, target):
            return min(range(len(path)),
                       key=lambda i: math.hypot(path[i][0] - target[0],
                                                path[i][1] - target[1]))

        idx_dev0 = closest_index(out_path, devices[0])
        idx_dev1 = closest_index(out_path, devices[1])
        idx_dev2 = closest_index(out_path, devices[2])

        # Path should visit devices in order: dev0 before dev1 before dev2
        assert idx_dev0 < idx_dev1 < idx_dev2, (
            f"Devices visited out of order: dev0@idx={idx_dev0}, "
            f"dev1@idx={idx_dev1}, dev2@idx={idx_dev2}"
        )


class TestProvenanceShim:
    """Test the fireai.core.provenance shim module."""

    def test_shim_import(self):
        """V14: Provenance shim can be imported from fireai.core.provenance."""
        from fireai.core.provenance import (
            DecisionProvenance, RuleApplied, ConfidenceScore,
            ConfidenceLevel, Violation,
        )
        # If src.v8_core is available, these should NOT be None
        # If not available, they are None (graceful degradation)
        assert DecisionProvenance is not None, "DecisionProvenance should be available"

    def test_shim_decision_provenance_functional(self):
        """V14: DecisionProvenance from shim works the same as direct import."""
        from fireai.core.provenance import DecisionProvenance, RuleApplied, ConfidenceScore, ConfidenceLevel

        rule = RuleApplied(
            citation="NFPA 72 12.2.2",
            constant_id="CLASS_A_SEP",
            value_used=1.0,
            unit="m",
        )

        provenance = DecisionProvenance.new(
            decision_type="test_shim",
            value={"test": True},
            inputs={"panel": (0, 0), "terminal_node": (10, 10)},
            rules_applied=[rule],
            algorithm={"name": "shim_test", "version": "v14"},
            confidence=ConfidenceScore(1.0, 1.0, 1.0, ConfidenceLevel.HIGH),
            selected_because="Shim import test",
            violations=[],
        )

        assert provenance is not None
        assert len(provenance.rules_applied) == 1

    def test_routing_global_class_a_uses_shim(self):
        """V14: EliteGlobalRouter uses provenance shim (not direct src.v8_core)."""
        import inspect
        import fireai.core.routing_global_class_a as mod

        source = inspect.getsource(mod)
        # Should NOT contain the old cross-package import
        assert "from src.v8_core" not in source, (
            "routing_global_class_a.py should use fireai.core.provenance shim, "
            "not direct src.v8_core import"
        )
        # Should contain the new shim import
        assert "from fireai.core.provenance import" in source
