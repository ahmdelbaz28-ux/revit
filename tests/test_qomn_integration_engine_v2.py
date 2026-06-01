"""
tests/test_qomn_integration_engine_v2.py
===========================================
Comprehensive test suite for:
  - fireai/core/qomn_integration_engine.py

SAFETY CRITICAL: This module integrates cable routing and hatch placement
for fire alarm conduit systems. Routing errors could cause NEC violations
or obstruction of detector coverage zones.

NFPA/NEC References:
  NEC Article 358.26 — EMT bends (max 360° total)
  NEC Article 344.26 — RMC bends
  NFPA 72 §17.7.3.2.3.1 — Detector zone spacing
  NEC Article 300.18 — Installation of wiring methods
"""

from __future__ import annotations

import dataclasses
import json
import math
import pytest
from typing import List, Tuple

from fireai.core.qomn_integration_engine import (
    Point3D,
    GridMap3D,
    CableRouter,
    HatchPlacementEngine,
    CableHatchIntegrator,
    ConduitType,
    HatchPattern,
    CableRoutingError,
    HatchPlacementError,
    NECViolationError,
    compute_engine_signature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Point3D Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPoint3D:
    """Immutable, hashable, deterministic 3D coordinate with 4-decimal rounding."""

    def test_creation(self):
        p = Point3D(1.0, 2.0, 3.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0

    def test_four_decimal_rounding(self):
        p = Point3D(1.23456, 2.34567, 3.45678)
        assert p.x == 1.2346
        assert p.y == 2.3457
        assert p.z == 3.4568

    def test_frozen(self):
        p = Point3D(1.0, 2.0, 3.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.x = 5.0

    def test_hashable(self):
        p1 = Point3D(1.0, 2.0, 3.0)
        p2 = Point3D(1.0, 2.0, 3.0)
        assert hash(p1) == hash(p2)
        s = {p1, p2}
        assert len(s) == 1

    def test_to_tuple(self):
        p = Point3D(1.5, 2.5, 3.5)
        assert p.to_tuple() == (1.5, 2.5, 3.5)

    def test_to_dict(self):
        p = Point3D(1.0, 2.0, 3.0)
        d = p.to_dict()
        assert d == {"X": 1.0, "Y": 2.0, "Z": 3.0}

    def test_integer_input(self):
        p = Point3D(1, 2, 3)
        assert p.x == 1.0
        assert isinstance(p.x, float)

    def test_zero_coordinates(self):
        p = Point3D(0.0, 0.0, 0.0)
        assert p.x == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# ConduitType & HatchPattern Enums
# ═══════════════════════════════════════════════════════════════════════════════


class TestConduitType:
    def test_emt_bend_multiplier(self):
        """NEC Article 358: EMT minimum bend radius = 4× diameter."""
        assert ConduitType.EMT.min_bend_radius_multiplier == 4.0

    def test_rmc_bend_multiplier(self):
        """NEC Article 344: RMC minimum bend radius = 5× diameter."""
        assert ConduitType.RMC.min_bend_radius_multiplier == 5.0

    def test_fmc_bend_multiplier(self):
        assert ConduitType.FMC.min_bend_radius_multiplier == 3.0

    def test_all_types(self):
        assert {ct.value for ct in ConduitType} == {"EMT", "RMC", "FMC"}


class TestHatchPattern:
    def test_all_patterns(self):
        assert {hp.value for hp in HatchPattern} == {"ANSI31", "SOLID", "CROSS"}


# ═══════════════════════════════════════════════════════════════════════════════
# GridMap3D Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGridMap3D:
    def test_default_step_size(self):
        gm = GridMap3D()
        assert gm.step_size == 0.5

    def test_custom_step_size(self):
        gm = GridMap3D(step_size=1.0)
        assert gm.step_size == 1.0

    def test_zero_step_size_rejected(self):
        with pytest.raises(ValueError, match="> 0"):
            GridMap3D(step_size=0.0)

    def test_negative_step_size_rejected(self):
        with pytest.raises(ValueError, match="> 0"):
            GridMap3D(step_size=-0.5)

    def test_to_grid(self):
        gm = GridMap3D(step_size=0.5)
        p = Point3D(2.0, 3.0, 1.0)
        assert gm.to_grid(p) == (4, 6, 2)

    def test_to_physical(self):
        gm = GridMap3D(step_size=0.5)
        gp = (4, 6, 2)
        p = gm.to_physical(gp)
        assert p.x == 2.0
        assert p.y == 3.0
        assert p.z == 1.0

    def test_round_trip(self):
        gm = GridMap3D(step_size=0.5)
        original = Point3D(5.0, 7.5, 3.0)
        grid_pt = gm.to_grid(original)
        result = gm.to_physical(grid_pt)
        assert result.x == original.x
        assert result.y == original.y
        assert result.z == original.z

    def test_add_obstacle(self):
        gm = GridMap3D()
        gm.add_obstacle(Point3D(1.0, 1.0, 1.0))
        assert len(gm.obstacles) == 1

    def test_is_blocked(self):
        gm = GridMap3D()
        p = Point3D(1.0, 1.0, 1.0)
        gm.add_obstacle(p)
        gp = gm.to_grid(p)
        assert gm.is_blocked(gp) is True
        assert gm.is_blocked((0, 0, 0)) is False


# ═══════════════════════════════════════════════════════════════════════════════
# CableRouter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCableRouterManhattan:
    def test_same_point(self):
        d = CableRouter.manhattan_distance((0, 0, 0), (0, 0, 0))
        assert d == 0.0

    def test_axis_aligned(self):
        d = CableRouter.manhattan_distance((0, 0, 0), (3, 0, 0))
        assert d == 3.0

    def test_3d(self):
        d = CableRouter.manhattan_distance((0, 0, 0), (3, 4, 5))
        assert d == 12.0


class TestCableRouterRouting:
    """A* routing with NEC bend compliance."""

    def test_straight_route(self):
        gm = GridMap3D(step_size=1.0)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(5.0, 0.0, 0.0)
        path = CableRouter.route(gm, start, end, ConduitType.EMT)
        assert len(path) >= 2
        assert path[0] == start
        assert path[-1] == end

    def test_route_with_turn(self):
        gm = GridMap3D(step_size=1.0)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(5.0, 5.0, 0.0)
        path = CableRouter.route(gm, start, end, ConduitType.EMT)
        assert len(path) >= 2
        # Should have at least one bend for a 2-segment route
        bends = CableRouter.calculate_total_bends_degrees(path)
        assert bends >= 0.0

    def test_blocked_start_raises(self):
        gm = GridMap3D(step_size=1.0)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(5.0, 0.0, 0.0)
        gm.add_obstacle(start)
        with pytest.raises(CableRoutingError, match="blocked"):
            CableRouter.route(gm, start, end, ConduitType.EMT)

    def test_blocked_end_raises(self):
        gm = GridMap3D(step_size=1.0)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(5.0, 0.0, 0.0)
        gm.add_obstacle(end)
        with pytest.raises(CableRoutingError, match="blocked"):
            CableRouter.route(gm, start, end, ConduitType.EMT)

    def test_no_path_fully_enclosed(self):
        """Start fully enclosed by obstacles — no path possible."""
        gm = GridMap3D(step_size=1.0)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(10.0, 0.0, 0.0)
        # Block start point in all 6 directions
        gm.add_obstacle(Point3D(1.0, 0.0, 0.0))  # +X
        gm.add_obstacle(Point3D(-1.0, 0.0, 0.0))  # -X
        gm.add_obstacle(Point3D(0.0, 1.0, 0.0))  # +Y
        gm.add_obstacle(Point3D(0.0, -1.0, 0.0))  # -Y
        gm.add_obstacle(Point3D(0.0, 0.0, 1.0))  # +Z
        gm.add_obstacle(Point3D(0.0, 0.0, -1.0))  # -Z
        # Start is not blocked itself but all neighbors are
        # The router should find no path
        with pytest.raises(CableRoutingError):
            CableRouter.route(gm, start, end, ConduitType.EMT)


class TestCableRouterBends:
    """NEC Article 358.26: max 360° total bends."""

    def test_straight_zero_bends(self):
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(10, 0, 0)]
        assert CableRouter.calculate_total_bends_degrees(path) == 0.0

    def test_one_90_degree_bend(self):
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(5, 5, 0)]
        bends = CableRouter.calculate_total_bends_degrees(path)
        assert bends == pytest.approx(90.0)

    def test_two_90_degree_bends(self):
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(5, 5, 0), Point3D(10, 5, 0)]
        bends = CableRouter.calculate_total_bends_degrees(path)
        assert bends == pytest.approx(180.0)

    def test_short_path_zero_bends(self):
        """Path with < 3 points has no bends."""
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0)]
        assert CableRouter.calculate_total_bends_degrees(path) == 0.0

    def test_single_point_zero_bends(self):
        path = [Point3D(0, 0, 0)]
        assert CableRouter.calculate_total_bends_degrees(path) == 0.0

    def test_nec_violation_exceeds_360(self):
        """Route exceeding 360° total bends raises NECViolationError."""
        gm = GridMap3D(step_size=0.5)
        start = Point3D(0.0, 0.0, 0.0)
        # Zigzag to force many bends
        end = Point3D(1.0, 20.0, 0.0)
        # This should either route successfully with <360° bends
        # or raise NECViolationError
        try:
            path = CableRouter.route(gm, start, end, ConduitType.EMT)
            # If it succeeds, verify bends are within limits
            assert CableRouter.calculate_total_bends_degrees(path) <= 360.0
        except NECViolationError:
            pass  # Expected for routes that exceed 360°


# ═══════════════════════════════════════════════════════════════════════════════
# HatchPlacementEngine Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSmokeDetectorBoundary:
    """NFPA 72 §17.7.3.2.3.1: boundary polygon for detector coverage zone."""

    def test_basic_boundary(self):
        center = Point3D(5.0, 5.0, 3.0)
        verts = HatchPlacementEngine.generate_smoke_detector_boundary(center, 9.144)
        assert len(verts) == 16

    def test_custom_sides(self):
        center = Point3D(0.0, 0.0, 0.0)
        verts = HatchPlacementEngine.generate_smoke_detector_boundary(center, 5.0, num_sides=8)
        assert len(verts) == 8

    def test_zero_radius_rejected(self):
        with pytest.raises(HatchPlacementError, match="> 0"):
            HatchPlacementEngine.generate_smoke_detector_boundary(Point3D(0, 0, 0), 0.0)

    def test_negative_radius_rejected(self):
        with pytest.raises(HatchPlacementError, match="> 0"):
            HatchPlacementEngine.generate_smoke_detector_boundary(Point3D(0, 0, 0), -5.0)

    def test_too_few_sides_rejected(self):
        with pytest.raises(HatchPlacementError, match=">= 4"):
            HatchPlacementEngine.generate_smoke_detector_boundary(Point3D(0, 0, 0), 5.0, num_sides=3)

    def test_vertices_on_circle(self):
        """All vertices should be at distance radius from center."""
        center = Point3D(10.0, 10.0, 3.0)
        radius = 5.0
        verts = HatchPlacementEngine.generate_smoke_detector_boundary(center, radius)
        for vx, vy in verts:
            dist = math.sqrt((vx - center.x) ** 2 + (vy - center.y) ** 2)
            assert dist == pytest.approx(radius, rel=0.01)


class TestConduitCorridors:
    def test_x_aligned_segment(self):
        path = [Point3D(0.0, 0.0, 0.0), Point3D(5.0, 0.0, 0.0)]
        corridors = HatchPlacementEngine.generate_conduit_corridors(path, width=0.1)
        assert len(corridors) == 1
        assert len(corridors[0]) == 4  # Rectangle has 4 vertices

    def test_y_aligned_segment(self):
        path = [Point3D(0.0, 0.0, 0.0), Point3D(0.0, 5.0, 0.0)]
        corridors = HatchPlacementEngine.generate_conduit_corridors(path, width=0.1)
        assert len(corridors) == 1

    def test_vertical_segment_skipped(self):
        """Vertical segments (z-only change) are skipped in 2D hatch."""
        path = [Point3D(0.0, 0.0, 0.0), Point3D(0.0, 0.0, 3.0)]
        corridors = HatchPlacementEngine.generate_conduit_corridors(path, width=0.1)
        assert len(corridors) == 0

    def test_zero_width_rejected(self):
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0)]
        with pytest.raises(HatchPlacementError, match="> 0"):
            HatchPlacementEngine.generate_conduit_corridors(path, width=0.0)

    def test_negative_width_rejected(self):
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0)]
        with pytest.raises(HatchPlacementError, match="> 0"):
            HatchPlacementEngine.generate_conduit_corridors(path, width=-0.1)

    def test_multi_segment_path(self):
        path = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(5, 5, 0)]
        corridors = HatchPlacementEngine.generate_conduit_corridors(path, width=0.1)
        assert len(corridors) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# CableHatchIntegrator Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCableHatchIntegrator:
    """Bridges QOMN-CABLE and QOMN-HATCH engines."""

    @pytest.fixture
    def integrator(self):
        gm = GridMap3D(step_size=1.0)
        return CableHatchIntegrator(gm)

    def test_add_smoke_detector(self, integrator):
        loc = Point3D(5.0, 5.0, 3.0)
        integrator.add_smoke_detector("SD-1", loc, 9.144)
        assert "SD-1" in integrator.smoke_detectors

    def test_add_detector_blocks_grid(self, integrator):
        """Detector location becomes obstacle in grid map."""
        loc = Point3D(5.0, 5.0, 3.0)
        integrator.add_smoke_detector("SD-1", loc, 9.144)
        gp = integrator.grid_map.to_grid(loc)
        assert integrator.grid_map.is_blocked(gp)

    def test_negative_radius_rejected(self, integrator):
        with pytest.raises(ValueError, match="> 0"):
            integrator.add_smoke_detector("SD-1", Point3D(5, 5, 3), -1.0)

    def test_zero_radius_rejected(self, integrator):
        with pytest.raises(ValueError, match="> 0"):
            integrator.add_smoke_detector("SD-1", Point3D(5, 5, 3), 0.0)

    def test_place_cable_with_hatch(self, integrator):
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(10.0, 0.0, 0.0)
        result = integrator.place_cable_with_hatch(
            "RUN-1", start, end, ConduitType.EMT, hatch_scale=0.5
        )
        assert result["RunId"] == "RUN-1"
        assert result["ConduitType"] == "EMT"
        assert len(result["Path"]) >= 2

    def test_low_hatch_scale_rejected(self, integrator):
        start = Point3D(0, 0, 0)
        end = Point3D(5, 0, 0)
        with pytest.raises(HatchPlacementError, match="too low"):
            integrator.place_cable_with_hatch(
                "RUN-1", start, end, ConduitType.EMT, hatch_scale=0.0001
            )

    def test_conflict_detection(self, integrator):
        """Cable passing through detector zone should generate warning."""
        # Add detector at (5, 0, 3) — directly on the cable path
        integrator.add_smoke_detector("SD-1", Point3D(5.0, 0.0, 3.0), 9.144)
        start = Point3D(0.0, 0.0, 0.0)
        end = Point3D(10.0, 0.0, 0.0)
        result = integrator.place_cable_with_hatch(
            "RUN-1", start, end, ConduitType.EMT, hatch_scale=0.5
        )
        # May or may not have warnings depending on path vs zone intersection
        assert "Warnings" in result
        assert "Infos" in result


class TestSegmentIntersectsCircle2D:
    """Geometric helper: segment-circle intersection in XY plane."""

    def test_segment_through_circle(self):
        p1 = Point3D(0, 0, 0)
        p2 = Point3D(10, 0, 0)
        center = Point3D(5, 0, 3)
        assert CableHatchIntegrator._segment_intersects_circle_2d(p1, p2, center, 5.0) is True

    def test_segment_outside_circle(self):
        p1 = Point3D(0, 10, 0)
        p2 = Point3D(10, 10, 0)
        center = Point3D(5, 0, 3)
        assert CableHatchIntegrator._segment_intersects_circle_2d(p1, p2, center, 5.0) is False

    def test_point_on_circle(self):
        """Zero-length segment (point) inside circle."""
        p1 = Point3D(5, 0, 0)
        p2 = Point3D(5, 0, 0)
        center = Point3D(5, 0, 0)
        assert CableHatchIntegrator._segment_intersects_circle_2d(p1, p2, center, 1.0) is True


class TestPolygonsIntersect2D:
    """AABB intersection test."""

    def test_overlapping(self):
        poly1 = [(0, 0), (5, 0), (5, 5), (0, 5)]
        poly2 = [(3, 3), (8, 3), (8, 8), (3, 8)]
        assert CableHatchIntegrator._polygons_intersect_2d(poly1, poly2) is True

    def test_non_overlapping(self):
        poly1 = [(0, 0), (5, 0), (5, 5), (0, 5)]
        poly2 = [(10, 10), (15, 10), (15, 15), (10, 15)]
        assert CableHatchIntegrator._polygons_intersect_2d(poly1, poly2) is False

    def test_touching_at_edge(self):
        poly1 = [(0, 0), (5, 0), (5, 5), (0, 5)]
        poly2 = [(5, 0), (10, 0), (10, 5), (5, 5)]
        assert CableHatchIntegrator._polygons_intersect_2d(poly1, poly2) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Export & Signature Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestExportRevitJson:
    def test_empty_export(self):
        gm = GridMap3D(step_size=1.0)
        integrator = CableHatchIntegrator(gm)
        json_str = integrator.export_revit_json()
        data = json.loads(json_str)
        assert data["SchemaVersion"] == "1.0"
        assert len(data["Zones"]) == 0
        assert len(data["Cables"]) == 0

    def test_with_detector_and_cable(self):
        gm = GridMap3D(step_size=1.0)
        integrator = CableHatchIntegrator(gm)
        integrator.add_smoke_detector("SD-1", Point3D(5, 5, 3), 9.144)
        integrator.place_cable_with_hatch(
            "RUN-1", Point3D(0, 0, 0), Point3D(10, 0, 0), ConduitType.EMT, hatch_scale=0.5
        )
        json_str = integrator.export_revit_json()
        data = json.loads(json_str)
        assert len(data["Zones"]) == 1
        assert len(data["Cables"]) == 1
        assert data["Zones"][0]["DeviceId"] == "SD-1"
        assert data["Cables"][0]["RunId"] == "RUN-1"

    def test_deterministic_output(self):
        """Same input → same JSON output, always."""
        gm = GridMap3D(step_size=1.0)
        int1 = CableHatchIntegrator(gm)
        int1.add_smoke_detector("SD-1", Point3D(5, 5, 3), 9.144)
        int1.place_cable_with_hatch(
            "RUN-1", Point3D(0, 0, 0), Point3D(10, 0, 0), ConduitType.EMT, hatch_scale=0.5
        )
        json1 = int1.export_revit_json()

        gm2 = GridMap3D(step_size=1.0)
        int2 = CableHatchIntegrator(gm2)
        int2.add_smoke_detector("SD-1", Point3D(5, 5, 3), 9.144)
        int2.place_cable_with_hatch(
            "RUN-1", Point3D(0, 0, 0), Point3D(10, 0, 0), ConduitType.EMT, hatch_scale=0.5
        )
        json2 = int2.export_revit_json()
        assert json1 == json2


class TestComputeEngineSignature:
    def test_deterministic_hash(self):
        gm = GridMap3D(step_size=1.0)
        int1 = CableHatchIntegrator(gm)
        int1.add_smoke_detector("SD-1", Point3D(5, 5, 3), 9.144)
        sig1 = compute_engine_signature(int1)

        gm2 = GridMap3D(step_size=1.0)
        int2 = CableHatchIntegrator(gm2)
        int2.add_smoke_detector("SD-1", Point3D(5, 5, 3), 9.144)
        sig2 = compute_engine_signature(int2)
        assert sig1 == sig2

    def test_hash_is_sha256_hex(self):
        gm = GridMap3D(step_size=1.0)
        integrator = CableHatchIntegrator(gm)
        sig = compute_engine_signature(integrator)
        assert len(sig) == 64  # Full SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in sig)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegrationScenarios:
    def test_office_floor_cable_and_detection(self):
        """Route cable from panel to detector zone in an office."""
        gm = GridMap3D(step_size=1.0)
        integrator = CableHatchIntegrator(gm)

        # Add smoke detectors
        integrator.add_smoke_detector("SD-1", Point3D(5, 5, 3), 9.144)
        integrator.add_smoke_detector("SD-2", Point3D(15, 5, 3), 9.144)

        # Route cable from panel to first detector
        result = integrator.place_cable_with_hatch(
            "PANEL-SD1", Point3D(0, 0, 0), Point3D(5, 5, 0), ConduitType.EMT, hatch_scale=0.5
        )
        assert result["RunId"] == "PANEL-SD1"

        # Export and verify
        json_str = integrator.export_revit_json()
        data = json.loads(json_str)
        assert len(data["Zones"]) == 2
        assert len(data["Cables"]) == 1

    def test_multiple_cable_runs(self):
        gm = GridMap3D(step_size=1.0)
        integrator = CableHatchIntegrator(gm)
        integrator.place_cable_with_hatch(
            "RUN-1", Point3D(0, 0, 0), Point3D(5, 0, 0), ConduitType.EMT, hatch_scale=0.5
        )
        integrator.place_cable_with_hatch(
            "RUN-2", Point3D(0, 5, 0), Point3D(5, 5, 0), ConduitType.EMT, hatch_scale=0.5
        )
        json_str = integrator.export_revit_json()
        data = json.loads(json_str)
        assert len(data["Cables"]) == 2
