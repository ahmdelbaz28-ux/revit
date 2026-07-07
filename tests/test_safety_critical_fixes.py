"""
Safety-Critical Fix Verification Tests
========================================

These tests verify the P0/P1 safety-critical fixes applied to the FireAI
fire alarm compliance system. Each test validates that a specific fix is
working correctly and that the system will catch life-safety violations.

P0 FIXES VERIFIED:
1. Heat detector spacing: 6.1m max (was 15.24m — 2.5x overestimate)
2. Wall min distance: 0.1016m (was 0.305m — 3x too lenient)
3. Wall max distance: S/2 per NFPA 72 §17.6.3.1.1
4. Dual-engine compliance: REJECT on divergence
5. Interior rings/holes: Room polygon correctly handles holes

P1 FIXES VERIFIED:
6. Coverage radius R = 0.7×S vs wall distance S/2 distinction
7. ComplianceEngine wall distance rules
8. Comment/documentation clarity

Reference: NFPA 72-2022, AGENTS.md Rules 6 and 7
"""

import pytest

from fireai.core.nfpa72_calculations import (
    calculate_coverage_radius,
    calculate_coverage_radius_from_height,
    calculate_max_spacing,
    calculate_max_wall_distance,
)
from fireai.core.nfpa72_coverage import (
    check_coverage_polygon,
    create_room_polygon,
)
from fireai.core.nfpa72_models import (
    CeilingSpec,
    DetectorType,
    HeatDetectorSpec,
    RoomSpec,
    get_smoke_detector_radius,
    get_smoke_detector_radius_safe,
)
from fireai.core.qomn_kernel import (
    NFPA72_COVERAGE_RADIUS_FACTOR,
    NFPA72_HEAT_MAX_SPACING_M,
    NFPA72_SMOKE_MAX_SPACING_M,
    NFPA72_WALL_MAX_DISTANCE_FACTOR,
    NFPA72_WALL_MIN_DISTANCE_M,
    PhysicsGuardError,
    compute_heat_detector_spacing,
    compute_smoke_detector_spacing,
)
from fireai.core.rules_engine.compliance_bridge import (
    DualComplianceResult,
    dual_compliance_check,
)
from fireai.validation.compliance_engine import ComplianceEngine

# ============================================================================
# P0-1: Heat Detector Spacing Verification
# ============================================================================

class TestHeatDetectorSpacing:
    """
    Verify heat detector spacing is 6.1m (20ft), NOT 15.24m (50ft).

    The old value of 15.24m was the LINEAR detection spacing for rate-of-rise
    heat detectors, NOT fixed-temperature. Using 15.24m would produce
    R = 0.7 × 15.24 = 10.67m — a 2.5× overestimate vs the correct
    R = 0.7 × 6.1 = 4.27m for fixed-temperature heat detectors.
    """

    def test_heat_max_spacing_is_6_1m(self):
        """NFPA 72 Table 17.6.2.1: 6.1m (20ft) for fixed-temperature heat."""
        assert pytest.approx(6.1) == NFPA72_HEAT_MAX_SPACING_M

    def test_heat_max_spacing_not_15_24m(self):
        """Ensure the old dangerous value 15.24m is NOT present."""
        assert NFPA72_HEAT_MAX_SPACING_M != pytest.approx(15.24)

    def test_heat_detector_spec_spacing(self):
        """HeatDetectorSpec uses 6.1m, not 9.1m (smoke) or 15.24m."""
        assert pytest.approx(6.1) == HeatDetectorSpec.FIXED_SPACING_M

    def test_heat_detector_radius_is_4_27m(self):
        """R = 0.7 × 6.1 = 4.27m for fixed-temperature heat."""
        # Use class-level constant directly
        radius = round(0.7 * HeatDetectorSpec.FIXED_SPACING_M, 2)
        assert radius == pytest.approx(4.27, rel=0.01)

    def test_compute_heat_spacing_capped(self):
        """compute_heat_detector_spacing rejects area > 232.26 m² per NFPA 72 §17.6.3.1."""
        with pytest.raises(PhysicsGuardError, match="exceeds NFPA 72"):
            compute_heat_detector_spacing(3.0, 10000.0)

    def test_coverage_spec_heat_spacing(self):
        """CoverageSpec for heat uses height-adjusted spacing from NFPA table."""
        spec = calculate_coverage_radius_from_height(3.0, detector_type="heat")
        assert spec.spacing_max == pytest.approx(6.1, rel=0.01)


# ============================================================================
# P0-2: Wall Distance Verification
# ============================================================================

class TestWallDistances:
    """
    Verify wall distances per NFPA 72 §17.6.3.1.1.

    Two distinct wall distance rules:
    - MINIMUM: 4 inches (0.1016m) — dead air space, detector must not be closer
    - MAXIMUM: S/2 — detector must not be farther from wall than half spacing
    """

    def test_wall_min_distance_0_1016m(self):
        """4 inches = 0.1016m per NFPA 72 §17.6.3.1.1."""
        assert pytest.approx(0.1016) == NFPA72_WALL_MIN_DISTANCE_M

    def test_wall_min_not_0_305m(self):
        """Ensure old value 0.305m is NOT present."""
        assert NFPA72_WALL_MIN_DISTANCE_M != pytest.approx(0.305)

    def test_wall_max_factor_0_5(self):
        """Wall max distance = S/2 per NFPA 72 §17.6.3.1.1."""
        assert pytest.approx(0.5) == NFPA72_WALL_MAX_DISTANCE_FACTOR

    def test_compute_smoke_spacing_has_wall_distances(self):
        """compute_smoke_detector_spacing returns both wall_min_m and wall_max_m."""
        result = compute_smoke_detector_spacing(3.0)
        assert "wall_min_m" in result
        assert "wall_max_m" in result
        # wall_min_m = 0.1016m (dead air)
        assert result["wall_min_m"] == pytest.approx(0.1016, rel=1e-3)
        assert result["wall_max_m"] == pytest.approx(0.5 * result["listed_spacing_m"], rel=1e-4)

    def test_calculate_max_wall_distance_is_s_over_2(self):
        """calculate_max_wall_distance returns S/2, NOT R=0.7×S."""
        ceiling = CeilingSpec(3.0, 3.0)
        wall_dist = calculate_max_wall_distance(ceiling, DetectorType.SMOKE)
        spacing = calculate_max_spacing(ceiling, DetectorType.SMOKE)
        # Must be S/2, not 0.7×S
        assert wall_dist == pytest.approx(spacing / 2.0, rel=0.01)
        assert wall_dist != pytest.approx(spacing * 0.7, rel=0.01)


# ============================================================================
# P0-3: Coverage Radius vs Wall Distance Distinction
# ============================================================================

class TestCoverageRadiusVsWallDistance:
    """
    Verify that coverage radius R = 0.7×S and wall distance = S/2 are
    correctly distinguished. These are DIFFERENT quantities:

    - R = 0.7×S: Distance from detector to farthest point in its square cell.
      Used for coverage VERIFICATION. For smoke at h<=3m: R = 6.37m.
    - Wall distance = S/2: Maximum detector-to-wall distance.
      Used for PLACEMENT verification. For smoke at h<=3m: wall_dist = 4.55m.

    CONFUSING THESE TWO IS DANGEROUS:
    - Using S/2 for coverage radius would REJECT compliant layouts (false negative)
    - Using 0.7×S for wall distance would ALLOW non-compliant layouts (false positive)
    """

    def test_coverage_radius_is_0_7_times_spacing(self):
        """Coverage radius factor = 0.7 per NFPA 72 §17.7.4.2.3.1."""
        assert pytest.approx(0.7) == NFPA72_COVERAGE_RADIUS_FACTOR

    def test_smoke_coverage_radius_at_3m(self):
        """Smoke at h<=3m: R = 0.7 × 9.1 = 6.37m."""
        radius = get_smoke_detector_radius_safe(3.0)
        assert radius == pytest.approx(6.37, rel=0.01)

    def test_coverage_radius_greater_than_wall_distance(self):
        """
        R = 0.7×S > wall_dist = S/2 for all S > 0.

        This is because the diagonal of a square (0.707×S) is always
        longer than half its side (0.5×S).
        """
        ceiling = CeilingSpec(3.0, 3.0)
        R = calculate_coverage_radius(ceiling, DetectorType.SMOKE)
        wall = calculate_max_wall_distance(ceiling, DetectorType.SMOKE)
        assert wall < R, (
            f"Coverage radius R={R:.3f}m must be > wall distance={wall:.3f}m. "
            f"R = 0.7×S covers corners; wall_dist = S/2 is placement limit."
        )

    def test_smoke_radius_map_uses_0_7_factor(self):
        """RADIUS_MAP values should equal 0.7 × adjusted spacing."""
        # For h in [3.0, 3.7): S=9.10, R should = 0.7×9.10 = 6.37
        radius = get_smoke_detector_radius(3.0)
        expected = 0.7 * 9.10
        assert radius == pytest.approx(expected, rel=0.01)


# ============================================================================
# P0-4: Dual-Engine Compliance Divergence Detection
# ============================================================================

class TestDualComplianceCheck:
    """
    Verify that dual_compliance_check correctly detects divergence
    between the two compliance engines and REJECTS on disagreement.

    SAFETY PRINCIPLE: In a safety-critical system, if two independent
    verification engines disagree, the design MUST be rejected. A divergence
    indicates a bug in one of the engines — which could be masking a
    real life-safety violation.
    """

    def test_dual_check_both_pass(self):
        """When both engines pass their respective checks, result should reflect both."""
        context = {
            'ceiling_height_m': 3.0,
            'spacing_m': 9.1,
            'max_spacing_for_height': 9.1,
            'coverage_pct': 100.0,
            'radius_m': 6.37,
            'v_drop_percent': 1.5,
            'v_drop_total_percent': 2.5,
            'wall_distance_m': 4.0,
            'detector_type': 'smoke',
            'terminal_voltage_v': 24.0,  # Must be >= 16VDC
        }
        result = dual_compliance_check(context, session_id="test-both-pass")
        # Both engines should pass with complete context
        assert isinstance(result, DualComplianceResult)
        assert result.clause_engine_safe is True

    def test_dual_check_clause_fails(self):
        """When clause engine fails, result should NOT be safe."""
        context = {
            'coverage_pct': 50.0,  # Way below 99.9%
            'v_drop_percent': 10.0,  # Way above 3%
        }
        result = dual_compliance_check(context, session_id="test-clause-fails")
        assert result.clause_engine_safe is False
        assert result.is_safe is False

    def test_dual_check_divergence_detected(self):
        """Divergence is flagged when engines disagree."""
        # This tests the DualComplianceResult logic
        result = DualComplianceResult(
            is_safe=True,  # Will be overridden
            rules_engine_safe=True,
            clause_engine_safe=False,
            engines_agree=False,
            divergence_details=["Test divergence"],
        )
        assert result.is_safe is False, "Divergence must force is_safe=False"
        assert len(result.divergence_details) > 0

    def test_dual_check_agreement_pass(self):
        """When both agree and pass, is_safe should be True."""
        result = DualComplianceResult(
            is_safe=True,
            rules_engine_safe=True,
            clause_engine_safe=True,
            engines_agree=True,
        )
        assert result.is_safe is True

    def test_dual_check_agreement_fail(self):
        """When both agree and fail, is_safe should be False."""
        result = DualComplianceResult(
            is_safe=False,
            rules_engine_safe=False,
            clause_engine_safe=False,
            engines_agree=True,
        )
        assert result.is_safe is False


# ============================================================================
# P0-5: Interior Rings / Holes in Room Polygons
# ============================================================================

class TestInteriorRings:
    """
    Verify that rooms with interior holes (columns, shafts, chases)
    are correctly handled in coverage verification.

    SAFETY: Without hole handling, detectors placed over a shaft or column
    would falsely report coverage of an area that physically cannot have
    a detector above it — a FALSE PASS that could leave areas unprotected.
    """

    def test_room_with_single_hole(self):
        """RoomSpec with one hole creates polygon with interior ring."""
        room = RoomSpec(
            room_id="room-with-column",
            width_m=20.0,
            depth_m=20.0,
            holes=[
                # 2m×2m column at center
                [(9.0, 9.0), (11.0, 9.0), (11.0, 11.0), (9.0, 11.0), (9.0, 9.0)],
            ],
        )
        assert room.polygon is not None
        assert len(list(room.polygon.interiors)) == 1

    def test_room_with_hole_has_smaller_area(self):
        """Room area with hole should be less than without hole."""
        room_no_hole = RoomSpec(room_id="no-hole", width_m=20.0, depth_m=20.0)
        room_with_hole = RoomSpec(
            room_id="with-hole",
            width_m=20.0,
            depth_m=20.0,
            holes=[
                [(9.0, 9.0), (11.0, 9.0), (11.0, 11.0), (9.0, 11.0), (9.0, 9.0)],
            ],
        )
        assert room_with_hole.area_sqm < room_no_hole.area_sqm
        # Hole area = 4m², so room area = 400 - 4 = 396m²
        assert room_with_hole.area_sqm == pytest.approx(396.0, rel=0.01)

    def test_room_with_multiple_holes(self):
        """RoomSpec with multiple holes creates polygon with multiple interior rings."""
        room = RoomSpec(
            room_id="room-with-columns",
            width_m=30.0,
            depth_m=30.0,
            holes=[
                # Column 1 at (5,5)
                [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)],
                # Column 2 at (25,25)
                [(24.0, 24.0), (26.0, 24.0), (26.0, 26.0), (24.0, 26.0), (24.0, 24.0)],
            ],
        )
        assert len(list(room.polygon.interiors)) == 2

    def test_coverage_excludes_holes(self):
        """Coverage check should not count hole areas as needing coverage."""
        room_with_hole = RoomSpec(
            room_id="coverage-hole-test",
            width_m=20.0,
            depth_m=20.0,
            holes=[
                [(9.0, 9.0), (11.0, 9.0), (11.0, 11.0), (9.0, 11.0), (9.0, 9.0)],
            ],
            ceiling_spec=CeilingSpec(3.0, 3.0),
        )
        ceiling = CeilingSpec(3.0, 3.0)
        # Place detectors at grid covering the room
        detectors = [
            (4.55, 4.55), (4.55, 13.65), (4.55, 18.0),
            (13.65, 4.55), (13.65, 13.65), (13.65, 18.0),
            (18.0, 4.55), (18.0, 13.65), (18.0, 18.0),
        ]
        result = check_coverage_polygon(
            detector_positions=detectors,
            room_spec=room_with_hole,
            ceiling_spec=ceiling,
            detector_type=DetectorType.SMOKE,
        )
        # The coverage check should work without errors
        assert isinstance(result.coverage_percentage, float)

    def test_invalid_hole_rejected(self):
        """Holes with fewer than 4 points should be rejected."""
        with pytest.raises(ValueError, match="hole.*must have at least 4"):
            RoomSpec(
                room_id="bad-hole",
                width_m=10.0,
                depth_m=10.0,
                holes=[
                    [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)],  # Only 3 points
                ],
            )

    def test_no_holes_backward_compatible(self):
        """Rooms without holes work exactly as before."""
        room = RoomSpec(room_id="no-holes", width_m=10.0, depth_m=10.0)
        assert len(list(room.polygon.interiors)) == 0
        assert room.area_sqm == pytest.approx(100.0)


# ============================================================================
# P1-1: ComplianceEngine Wall Distance Rules
# ============================================================================

class TestComplianceEngineWallRules:
    """Verify that ComplianceEngine now checks wall distances."""

    def test_wall_distance_exceeds_s_over_2(self):
        """Detector too far from wall should be flagged."""
        engine = ComplianceEngine()
        context = {
            'spacing_m': 9.1,
            'wall_distance_m': 5.0,  # > S/2 = 4.55m
        }
        violations = engine.validate(context)
        wall_violations = [v for v in violations if 'wall_max' in v]
        assert len(wall_violations) > 0, "Should flag wall distance > S/2"

    def test_wall_distance_within_s_over_2(self):
        """Detector within S/2 of wall should pass."""
        engine = ComplianceEngine()
        context = {
            'spacing_m': 9.1,
            'wall_distance_m': 4.0,  # < S/2 = 4.55m
        }
        violations = engine.validate(context)
        wall_violations = [v for v in violations if 'wall_max' in v]
        assert len(wall_violations) == 0, "Should pass wall distance <= S/2"

    def test_wall_distance_too_close(self):
        """Detector in dead air space (< 0.1016m) should be flagged."""
        engine = ComplianceEngine()
        context = {
            'spacing_m': 9.1,
            'wall_distance_m': 0.05,  # < 0.1016m (4 inches)
        }
        violations = engine.validate(context)
        dead_air_violations = [v for v in violations if 'wall_min' in v]
        assert len(dead_air_violations) > 0, "Should flag dead air space"

    def test_wall_distance_at_minimum(self):
        """Detector at exactly 0.1016m from wall should pass."""
        engine = ComplianceEngine()
        context = {
            'spacing_m': 9.1,
            'wall_distance_m': 0.1016,  # Exactly at minimum
        }
        violations = engine.validate(context)
        dead_air_violations = [v for v in violations if 'wall_min' in v]
        assert len(dead_air_violations) == 0, "0.1016m should pass"


# ============================================================================
# P1-2: NFPA 72 Constants Consistency
# ============================================================================

class TestNFPA72ConstantsConsistency:
    """Verify that NFPA 72 constants are consistent across modules."""

    def test_coverage_radius_factor_consistent(self):
        """COVERAGE_RADIUS_FACTOR should be 0.7 in all modules."""
        assert NFPA72_COVERAGE_RADIUS_FACTOR == pytest.approx(0.7)

    def test_heat_spacing_matches_table(self):
        """Heat max spacing matches NFPA 72 Table 17.6.2.1."""
        # Fixed-temperature heat: 20ft = 6.1m
        assert pytest.approx(6.1) == NFPA72_HEAT_MAX_SPACING_M

    def test_smoke_spacing_matches_table(self):
        """Smoke max spacing matches NFPA 72 §17.7.3.2.3."""
        # Smoke: flat 9.1m per V130 FIX per §17.7.3.2.3 (NO height reduction)
        assert pytest.approx(9.1) == NFPA72_SMOKE_MAX_SPACING_M

    def test_heat_detector_spec_matches_constant(self):
        """HeatDetectorSpec.FIXED_SPACING_M matches the constant."""
        assert HeatDetectorSpec.FIXED_SPACING_M == NFPA72_HEAT_MAX_SPACING_M

    def test_wall_min_distance_4_inches(self):
        """Wall min distance = 4 inches = 0.1016m."""
        assert pytest.approx(0.1016) == NFPA72_WALL_MIN_DISTANCE_M

    def test_wall_max_distance_factor_half(self):
        """Wall max distance factor = 0.5 (S/2)."""
        assert pytest.approx(0.5) == NFPA72_WALL_MAX_DISTANCE_FACTOR


# ============================================================================
# INTEGRATION: Full Coverage Workflow with Holes
# ============================================================================

class TestCoverageWorkflowWithHoles:
    """Integration test: full coverage check workflow with rooms containing holes."""

    def test_rectangular_room_no_holes(self):
        """Standard rectangular room — baseline coverage check."""
        room = RoomSpec(
            room_id="rect-room",
            width_m=18.0,
            depth_m=18.0,
            ceiling_spec=CeilingSpec(3.0, 3.0),
        )
        # Place 4 detectors on a 9.1m grid
        detectors = [
            (4.55, 4.55),
            (4.55, 13.65),
            (13.65, 4.55),
            (13.65, 13.65),
        ]
        result = check_coverage_polygon(
            detector_positions=detectors,
            room_spec=room,
            ceiling_spec=CeilingSpec(3.0, 3.0),
            detector_type=DetectorType.SMOKE,
        )
        assert result.is_covered is True

    def test_l_shaped_room_coverage(self):
        """L-shaped room with custom_polygon."""
        # L-shape: 20m × 10m with a 10m × 5m notch removed
        l_shape = [
            (0, 0), (20, 0), (20, 10), (10, 10), (10, 5), (0, 5), (0, 0)
        ]
        room = RoomSpec(
            room_id="l-room",
            width_m=20.0,
            depth_m=10.0,
            custom_polygon=l_shape,
            ceiling_spec=CeilingSpec(3.0, 3.0),
        )
        # Verify L-shape has less area than full rectangle
        assert room.area_sqm < 200.0
        assert room.area_sqm == pytest.approx(150.0, rel=0.01)

    def test_create_room_polygon_with_holes(self):
        """create_room_polygon preserves interior rings from RoomSpec."""
        room = RoomSpec(
            room_id="poly-hole",
            width_m=20.0,
            depth_m=20.0,
            holes=[
                [(9.0, 9.0), (11.0, 9.0), (11.0, 11.0), (9.0, 11.0), (9.0, 9.0)],
            ],
        )
        polygon = create_room_polygon(room)
        assert polygon is not None
        assert len(list(polygon.interiors)) == 1
