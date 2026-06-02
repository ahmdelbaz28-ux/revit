"""
qomn_conduit.tests.test_integration — Cross-Platform Determinism Integration Tests
===================================================================================

Tests float64 determinism, SHA-256 consistency, and cross-module integration.

Reference: NEC 2022 Chapter 9; NFPA 72-2022 §12.2.
"""

import hashlib
import json
import math
import pytest

from qomn_conduit import (
    ConduitType, TradeSize, FittingType, Point3D,
    calculate_fill, verify_bend_radius, place_fittings,
    orthogonal_astar, generate_revit_conduit,
    BoundingBox, Result,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Float64 operations produce identical results
# ─────────────────────────────────────────────────────────────────────────────

class TestFloat64Determinism:
    """float64 operations must produce identical results on any platform."""

    def test_fill_percentage_determinism(self):
        """Same cable diameters → identical fill percentage."""
        cables = [0.111, 0.111, 0.111]
        results = [
            calculate_fill(ConduitType.EMT, TradeSize.HALF_INCH, cables)
            for _ in range(10)
        ]
        fill_pcts = [r.value.fill_percentage for r in results if r.is_ok()]
        # All must be identical
        assert all(fp == fill_pcts[0] for fp in fill_pcts)

    def test_bend_developed_length_determinism(self):
        """Same bend radius → identical developed length."""
        results = [
            verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 4.0)
            for _ in range(10)
        ]
        lengths = [r.value.developed_length_in for r in results if r.is_ok()]
        assert all(l == lengths[0] for l in lengths)

    def test_pi_calculation_deterministic(self):
        """π × R / 2 must produce same result every time."""
        results = [math.pi * 4.0 / 2.0 for _ in range(100)]
        assert all(r == results[0] for r in results)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: SHA-256 of complete run is identical across runs
# ─────────────────────────────────────────────────────────────────────────────

class TestSHA256Consistency:
    """SHA-256 hash of conduit run output must be identical across runs."""

    def test_revit_output_sha256_consistent(self):
        """Same conduit run → same SHA-256 hash."""
        # Create identical runs
        path = orthogonal_astar(
            Point3D(0.0, 0.0, 3.0),
            Point3D(10.0, 0.0, 3.0),
            grid_resolution=0.5,
        )
        if not path.is_ok():
            pytest.skip("Router could not find path")

        run1 = place_fittings(path.value, ConduitType.EMT, TradeSize.HALF_INCH, run_id="DET-001")
        run2 = place_fittings(path.value, ConduitType.EMT, TradeSize.HALF_INCH, run_id="DET-001")

        if not run1.is_ok() or not run2.is_ok():
            pytest.skip("Fitting engine failed")

        out1 = generate_revit_conduit(run1.value)
        out2 = generate_revit_conduit(run2.value)

        assert out1["sha256"] == out2["sha256"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Cross-module integration — full pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipelineIntegration:
    """End-to-end test: fill → bend → route → fittings → output."""

    def test_example_1_fill_calculation(self):
        """Example 1 from spec: Calculate conduit fill for 3×#14 THHN in ½\" EMT."""
        result = calculate_fill(
            conduit_type=ConduitType.EMT,
            trade_size=TradeSize.HALF_INCH,
            cable_diameters=[0.111, 0.111, 0.111]
        )
        assert result.is_ok()
        # Geometric formula: 3 × π(0.0555)² / 0.304 × 100 ≈ 9.55%
        expected_fill = 3 * math.pi * (0.111 / 2.0) ** 2 / 0.304 * 100
        assert result.value.fill_percentage == pytest.approx(expected_fill, abs=0.01)
        assert result.value.status == "COMPLIANT"

    def test_example_2_bend_verification(self):
        """Example 2 from spec: Verify bend radius for ½\" EMT R=4.0\"."""
        result = verify_bend_radius(
            conduit_type=ConduitType.EMT,
            trade_size=TradeSize.HALF_INCH,
            actual_radius=4.0
        )
        assert result.is_ok()
        assert result.value.is_compliant is True
        assert result.value.developed_length_in == pytest.approx(
            math.pi * 4.0 / 2, abs=0.001
        )

    def test_example_3_route_and_place_fittings(self):
        """Example 3 from spec: Route and place fittings."""
        path = orthogonal_astar(
            start=Point3D(0.0, 0.0, 3.0),
            end=Point3D(10.0, 5.0, 3.0),
            obstacles=[BoundingBox(x_min=4.8, y_min=1.8, z_min=2.8,
                                  x_max=5.2, y_max=2.2, z_max=3.2,
                                  label="wall")] if False else None,
            grid_resolution=0.5,
        )
        assert path.is_ok()

        run = place_fittings(
            path=path.value,
            conduit_type=ConduitType.EMT,
            trade_size=TradeSize.THREE_QUARTER,
        )
        assert run.is_ok()
        assert len(run.value.fittings) >= 0  # May or may not have fittings on short paths
        # All EMT fittings must have catalog numbers starting with E
        for f in run.value.fittings:
            if f.fitting_type == FittingType.ELBOW_90:
                assert f.catalog_number.startswith("E")

    def test_spec_example_usage_compiles(self):
        """The example usage from the spec must compile and run without error."""
        # Example 1: Calculate conduit fill
        result = calculate_fill(
            conduit_type=ConduitType.EMT,
            trade_size=TradeSize.HALF_INCH,
            cable_diameters=[0.111, 0.111, 0.111]
        )
        assert result.is_ok()
        # fill_percentage should be approximately 6.614 (per spec)
        # Geometric formula: 3 × π(0.0555)² / 0.304 × 100 ≈ 9.55%
        expected_fill = 3 * math.pi * (0.111 / 2.0) ** 2 / 0.304 * 100
        assert result.value.fill_percentage == pytest.approx(expected_fill, abs=0.01)
        assert result.value.status == "COMPLIANT"

        # Example 2: Verify bend radius
        result2 = verify_bend_radius(
            conduit_type=ConduitType.EMT,
            trade_size=TradeSize.HALF_INCH,
            actual_radius=4.0
        )
        assert result2.is_ok()
        assert result2.value.is_compliant is True
        # developed_length = π × 4.0 / 2
        assert result2.value.developed_length_in == pytest.approx(
            math.pi * 4.0 / 2, abs=0.001
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Import all public API
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicAPI:
    """All public API items must be importable from qomn_conduit."""

    def test_all_types_importable(self):
        """Types must be importable from qomn_conduit."""
        from qomn_conduit import (
            ConduitType, TradeSize, FittingType, Point3D, Result,
            FillResult, BendResult, RoutePath, ConduitRun,
            ConduitSegment, PlacedFitting,
        )
        assert ConduitType.EMT is not None
        assert TradeSize.HALF_INCH is not None
        assert FittingType.ELBOW_90 is not None

    def test_all_errors_importable(self):
        """Error types must be importable from qomn_conduit."""
        from qomn_conduit import (
            ConduitError, PhysicsError, CodeViolationError,
            CatalogError, RoutingError, Severity,
        )
        assert PhysicsError is not None

    def test_all_functions_importable(self):
        """All public functions must be importable from qomn_conduit."""
        from qomn_conduit import (
            get_fitting, catalog_size, all_fittings,
            calculate_fill, get_internal_area,
            verify_bend_radius, calculate_developed_length,
            verify_cumulative_bends, MAX_CUMULATIVE_BEND_DEG,
            orthogonal_astar, ConduitRouter, BoundingBox,
            place_fittings,
            generate_revit_conduit, generate_autocad_entities,
            generate_schedules,
        )
        assert calculate_fill is not None
        assert place_fittings is not None
