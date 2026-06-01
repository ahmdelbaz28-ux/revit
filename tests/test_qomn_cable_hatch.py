"""
tests/test_qomn_cable_hatch.py — QOMN Cable Routing & Hatch Placement Test Suite
=================================================================================
Verifies the QOMN Integration Engine (qomn_integration_engine.py) for:
  1. Golden path routing (NFPA 72 & NEC 2023 compliant)
  2. Smoke detector proximity conflict warnings
  3. NEC 360-degree bend limit enforcement
  4. Hatch scale validation boundaries
  5. Determinism verification under repeated execution
  6. Input validation (negative radius, zero step size, etc.)

Standards:
  NEC 2023 Article 358.26 / 344.26 — Conduit bend limits
  NFPA 72 (2022) Section 17.7.3.2.3.1 — Detector zone spacing
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("FIREAI_ENV", "testing")
os.environ.setdefault("DIGITAL_TWIN_DB_PATH", ":memory:")

from fireai.core.qomn_integration_engine import (
    Point3D, GridMap3D, CableRouter, HatchPlacementEngine,
    CableHatchIntegrator, ConduitType, NECViolationError, HatchPlacementError,
    CableRoutingError, compute_engine_signature,
)


class TestQomnCableHatchIntegration(unittest.TestCase):

    def setUp(self):
        self.grid_map = GridMap3D(step_size=0.5)

    def test_golden_path_success(self):
        """
        TEST 1: Golden Path Validation (NFPA 72 & NEC 2023 Compliant)
        Input: 10x10m Room, One Smoke Detector, One Conduit Run
        Expected: Path successfully solved, 1 coverage hatch, zero errors.
        """
        integrator = CableHatchIntegrator(self.grid_map)

        # Add a smoke detector at center coordinate
        integrator.add_smoke_detector("SMOKE_01", Point3D(5.0, 5.0, 0.0), radius=3.0)

        # Route conduit from (0, 0, 0) to (8.0, 0.0, 0.0) -> avoids obstacle at (5,5,0)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(8.0, 0.0, 0.0)

        run_data = integrator.place_cable_with_hatch(
            run_id="RUN_01",
            start=start,
            end=end,
            conduit=ConduitType.EMT,
            hatch_scale=0.5
        )

        self.assertEqual(run_data["RunId"], "RUN_01")
        self.assertEqual(run_data["TotalBendsDegrees"], 0.0)  # Straight line
        self.assertTrue(len(run_data["HatchCorridors"]) > 0)
        self.assertEqual(len(run_data["Warnings"]), 0)

    def test_conflict_scenario_warning(self):
        """
        TEST 2: Smoke Detector Proximity Conflict Warning
        Input: Conduit passes directly through the coverage cylinder.
        Expected: Warning logged inside metadata, path successfully completed.
        """
        integrator = CableHatchIntegrator(self.grid_map)

        # Smoke detector coverage zone covers y-axis area
        integrator.add_smoke_detector(
            "SMOKE_CENTER", Point3D(5.0, 1.0, 0.0), radius=4.0
        )

        # Route passes directly from x=0 to x=10 along y=0
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(10.0, 0.0, 0.0)

        run_data = integrator.place_cable_with_hatch(
            run_id="RUN_CONFL",
            start=start,
            end=end,
            conduit=ConduitType.EMT,
            hatch_scale=0.5
        )

        self.assertTrue(
            any("intersects smoke detector zone" in w for w in run_data["Warnings"])
        )

    def test_nec_violation_bend_limit(self):
        """
        TEST 3: NEC 360-degree Bend Limit Enforcement
        When a routed path exceeds 360 degrees of total bends,
        NECViolationError must be raised per NEC Article 358.26.

        We verify:
        1. calculate_total_bends_degrees() correctly computes bend angles
        2. A path exceeding 360° is detected (>360° triggers violation)
        3. A path exactly at 360° is at the NEC limit (not a violation)
        4. CableRouter.route() raises NECViolationError for over-bent paths
        """
        # Part A: Directly verify bend calculation on known over-bent paths
        # 6 turns x 90° = 540° total (exceeds NEC 360° limit)
        serpentine_path = [
            Point3D(0.0, 0.0, 0.0),   # Start
            Point3D(5.0, 0.0, 0.0),   # Go east
            Point3D(5.0, 5.0, 0.0),   # Turn 1: east→north (90°)
            Point3D(10.0, 5.0, 0.0),  # Turn 2: north→east (180°)
            Point3D(10.0, 0.0, 0.0),  # Turn 3: east→south (270°)
            Point3D(15.0, 0.0, 0.0),  # Turn 4: south→east (360°)
            Point3D(15.0, 5.0, 0.0),  # Turn 5: east→north (450°)
            Point3D(20.0, 5.0, 0.0),  # Turn 6: north→east (540° > 360!)
        ]
        total_bends = CableRouter.calculate_total_bends_degrees(serpentine_path)
        self.assertGreater(total_bends, 360.0,
                           f"Serpentine path must exceed 360°, got {total_bends}°")
        self.assertEqual(total_bends, 540.0,
                         f"6 x 90° turns = 540°, got {total_bends}°")

        # Part B: Verify 4-turn path (360° exactly) is at the NEC limit
        path_at_limit = [
            Point3D(0.0, 0.0, 0.0),
            Point3D(5.0, 0.0, 0.0),   # east
            Point3D(5.0, 5.0, 0.0),   # 90°
            Point3D(10.0, 5.0, 0.0),  # 180°
            Point3D(10.0, 0.0, 0.0),  # 270°
            Point3D(15.0, 0.0, 0.0),  # 360° (at limit)
        ]
        bends_at_limit = CableRouter.calculate_total_bends_degrees(path_at_limit)
        self.assertEqual(bends_at_limit, 360.0,
                         f"4 x 90° turns = 360°, got {bends_at_limit}°")

        # Part C: Verify CableRouter.route() raises NECViolationError
        # We create a very constrained 2D-only corridor (single z-layer)
        # with walls that force 5+ turns.
        grid = GridMap3D(step_size=1.0)

        # Block ALL z != 0 layers to force 2D-only routing
        for x in range(-3, 26):
            for y in range(-3, 16):
                grid.add_obstacle(Point3D(float(x), float(y), 1.0))
                grid.add_obstacle(Point3D(float(x), float(y), -1.0))

        # Close boundaries tightly: y=-1 and y=11 in z=0
        for x in range(-1, 24):
            grid.add_obstacle(Point3D(float(x), -1.0, 0.0))
            grid.add_obstacle(Point3D(float(x), 11.0, 0.0))

        # Also close x boundaries
        for y in range(-1, 12):
            grid.add_obstacle(Point3D(-1.0, float(y), 0.0))

        # Alternating walls with single-cell gaps:
        for y in range(10):
            grid.add_obstacle(Point3D(3.0, float(y), 0.0))
        for y in range(1, 11):
            grid.add_obstacle(Point3D(7.0, float(y), 0.0))
        for y in range(10):
            grid.add_obstacle(Point3D(11.0, float(y), 0.0))
        for y in range(1, 11):
            grid.add_obstacle(Point3D(15.0, float(y), 0.0))
        for y in range(10):
            grid.add_obstacle(Point3D(19.0, float(y), 0.0))

        integrator = CableHatchIntegrator(grid)

        with self.assertRaises(NECViolationError):
            integrator.place_cable_with_hatch(
                run_id="RUN_NEC_FAIL",
                start=Point3D(0.0, 0.0, 0.0),
                end=Point3D(22.0, 0.0, 0.0),
                conduit=ConduitType.RMC,
                hatch_scale=0.1
            )

    def test_hatch_scale_validation(self):
        """
        TEST 4: Boundary Hatch Scale Checks
        Input: Scale factors < 0.001
        Expected: Throw HatchPlacementError
        """
        integrator = CableHatchIntegrator(self.grid_map)
        with self.assertRaises(HatchPlacementError):
            integrator.place_cable_with_hatch(
                run_id="RUN_SCALE_FAIL",
                start=Point3D(0.0, 0.0, 0.0),
                end=Point3D(2.0, 0.0, 0.0),
                conduit=ConduitType.EMT,
                hatch_scale=0.0005
            )

    def test_determinism_under_stress(self):
        """
        TEST 5: Stress & Determinism Validation
        Input: Complex model containing multiple devices and conduits,
               repeated multiple times.
        Expected: Output signatures must remain identical down to the bit level.
        """
        # First execution run
        grid_1 = GridMap3D(step_size=0.1)
        integrator_1 = CableHatchIntegrator(grid_1)

        for i in range(5):
            for j in range(5):
                integrator_1.add_smoke_detector(
                    f"SM_ID_{i}_{j}",
                    Point3D(i*10.0, j*10.0, 0.0),
                    radius=4.5
                )

        for r in range(20):
            try:
                integrator_1.place_cable_with_hatch(
                    run_id=f"CABLE_RUN_{r}",
                    start=Point3D(0.0, r*2.0, 0.0),
                    end=Point3D(40.0, r*2.0, 0.0),
                    conduit=ConduitType.EMT,
                    hatch_scale=0.1
                )
            except CableRoutingError:
                pass  # Ignore paths blocked in grid

        hash_signature_1 = compute_engine_signature(integrator_1)

        # Execute multiple times to verify absolute consistency
        for cycle in range(10):
            grid_loop = GridMap3D(step_size=0.1)
            integrator_loop = CableHatchIntegrator(grid_loop)

            for i in range(5):
                for j in range(5):
                    integrator_loop.add_smoke_detector(
                        f"SM_ID_{i}_{j}",
                        Point3D(i*10.0, j*10.0, 0.0),
                        radius=4.5
                    )

            for r in range(20):
                try:
                    integrator_loop.place_cable_with_hatch(
                        run_id=f"CABLE_RUN_{r}",
                        start=Point3D(0.0, r*2.0, 0.0),
                        end=Point3D(40.0, r*2.0, 0.0),
                        conduit=ConduitType.EMT,
                        hatch_scale=0.1
                    )
                except CableRoutingError:
                    pass

            hash_loop = compute_engine_signature(integrator_loop)
            self.assertEqual(
                hash_signature_1, hash_loop,
                f"Non-deterministic execution detected on loop {cycle}"
            )

    def test_point3d_immutability_and_precision(self):
        """Point3D coordinates must be rounded to 4 decimal places and immutable."""
        pt = Point3D(1.123456789, 2.987654321, 3.555555555)
        self.assertEqual(pt.x, 1.1235)
        self.assertEqual(pt.y, 2.9877)
        self.assertEqual(pt.z, 3.5556)

        # Immutability test
        with self.assertRaises(AttributeError):
            pt.x = 5.0

    def test_point3d_to_dict(self):
        """Point3D.to_dict() must produce serialization-safe output."""
        pt = Point3D(1.0, 2.0, 3.0)
        d = pt.to_dict()
        self.assertEqual(d, {"X": 1.0, "Y": 2.0, "Z": 3.0})

    def test_negative_radius_rejected(self):
        """Negative smoke detector radius must be rejected."""
        integrator = CableHatchIntegrator(self.grid_map)
        with self.assertRaises(ValueError):
            integrator.add_smoke_detector("BAD", Point3D(0, 0, 0), radius=-1.0)

    def test_zero_step_size_rejected(self):
        """Grid step size of zero must be rejected."""
        with self.assertRaises(ValueError):
            GridMap3D(step_size=0.0)

    def test_negative_hatch_width_rejected(self):
        """Negative corridor width must be rejected."""
        with self.assertRaises(HatchPlacementError):
            HatchPlacementEngine.generate_conduit_corridors(
                [Point3D(0, 0, 0), Point3D(5, 0, 0)], width=-0.1
            )

    def test_negative_detector_boundary_radius_rejected(self):
        """Negative boundary radius must be rejected."""
        with self.assertRaises(HatchPlacementError):
            HatchPlacementEngine.generate_smoke_detector_boundary(
                Point3D(0, 0, 0), radius=-1.0
            )

    def test_blocked_start_raises_error(self):
        """Routing from a blocked start point must raise CableRoutingError."""
        grid = GridMap3D(step_size=1.0)
        grid.add_obstacle(Point3D(0.0, 0.0, 0.0))
        integrator = CableHatchIntegrator(grid)
        with self.assertRaises(CableRoutingError):
            integrator.place_cable_with_hatch(
                run_id="BLOCKED",
                start=Point3D(0.0, 0.0, 0.0),
                end=Point3D(5.0, 0.0, 0.0),
                conduit=ConduitType.EMT,
                hatch_scale=0.5
            )

    def test_export_revit_json_structure(self):
        """export_revit_json() must produce valid JSON with required fields."""
        integrator = CableHatchIntegrator(self.grid_map)
        integrator.add_smoke_detector("D1", Point3D(5.0, 5.0, 0.0))
        integrator.place_cable_with_hatch(
            run_id="R1",
            start=Point3D(0, 0, 0),
            end=Point3D(8, 0, 0),
            conduit=ConduitType.EMT,
            hatch_scale=0.5
        )

        json_str = integrator.export_revit_json()
        data = __import__("json").loads(json_str)

        self.assertIn("SchemaVersion", data)
        self.assertIn("Metadata", data)
        self.assertIn("Zones", data)
        self.assertIn("Cables", data)
        self.assertEqual(len(data["Zones"]), 1)
        self.assertEqual(len(data["Cables"]), 1)
        self.assertEqual(data["Zones"][0]["DeviceId"], "D1")
        self.assertEqual(data["Cables"][0]["RunId"], "R1")

    def test_compute_engine_signature_deterministic(self):
        """SHA-256 signature must be identical for same inputs across calls."""
        integrator = CableHatchIntegrator(GridMap3D(step_size=0.5))
        integrator.add_smoke_detector("D1", Point3D(5.0, 5.0, 0.0))
        integrator.place_cable_with_hatch(
            run_id="R1",
            start=Point3D(0, 0, 0),
            end=Point3D(8, 0, 0),
            conduit=ConduitType.EMT,
            hatch_scale=0.5
        )

        sig1 = compute_engine_signature(integrator)
        sig2 = compute_engine_signature(integrator)
        self.assertEqual(sig1, sig2)
        self.assertEqual(len(sig1), 64)  # SHA-256 hex digest length

    def test_bend_calculation_straight_line(self):
        """Straight line must have zero bends."""
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(10, 0, 0)]
        self.assertEqual(CableRouter.calculate_total_bends_degrees(path), 0.0)

    def test_bend_calculation_single_90(self):
        """Single 90-degree turn must produce 90.0 degrees."""
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(5, 5, 0)]
        self.assertEqual(CableRouter.calculate_total_bends_degrees(path), 90.0)

    def test_bend_calculation_two_90s(self):
        """Two 90-degree turns must produce 180.0 degrees."""
        path = [
            Point3D(0, 0, 0), Point3D(5, 0, 0),
            Point3D(5, 5, 0), Point3D(0, 5, 0)
        ]
        self.assertEqual(CableRouter.calculate_total_bends_degrees(path), 180.0)

    def test_conduit_type_bend_multipliers(self):
        """Conduit bend radius multipliers per NEC must be correct."""
        self.assertEqual(ConduitType.EMT.min_bend_radius_multiplier, 4.0)
        self.assertEqual(ConduitType.RMC.min_bend_radius_multiplier, 5.0)
        self.assertEqual(ConduitType.FMC.min_bend_radius_multiplier, 3.0)


if __name__ == '__main__':
    unittest.main()
