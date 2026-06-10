"""
qomn_conduit.tests.test_bend — NEC 358.24/352.24/344.24 Bend Radius Tests
============================================================================

Tests bend radius verification and developed length calculation
against NEC published minimum radii and geometric formulas.

Reference: NEC 358.24 (EMT), 352.24 (PVC), 344.24 (RGD).
"""

import math
import pytest

from qomn_conduit import (
    ConduitType, TradeSize, verify_bend_radius, calculate_developed_length,
    verify_cumulative_bends, MAX_CUMULATIVE_BEND_DEG, BendResult,
)
from qomn_conduit.errors import PhysicsError, CodeViolationError


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Compliant bend radii
# ─────────────────────────────────────────────────────────────────────────────

class TestBendCompliance:
    """Bends at or above NEC minimum must be compliant."""

    def test_emt_half_inch_at_minimum(self):
        """½\" EMT, actual R=4.0\" → is_compliant=True, min=4.0\"."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 4.0)
        assert result.is_ok()
        assert result.value.is_compliant is True
        assert result.value.min_required_in == pytest.approx(4.0, abs=0.001)

    def test_emt_half_inch_above_minimum(self):
        """½\" EMT, actual R=5.0\" → is_compliant=True."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 5.0)
        assert result.is_ok()
        assert result.value.is_compliant is True

    def test_upvc_sch40_three_quarter_at_minimum(self):
        """¾\" UPVC Sch40, actual R=5.25\" → is_compliant=True."""
        result = verify_bend_radius(ConduitType.UPVC_SCH40, TradeSize.THREE_QUARTER, 5.25)
        assert result.is_ok()
        assert result.value.is_compliant is True
        assert result.value.min_required_in == pytest.approx(5.25, abs=0.01)

    def test_rgd_half_inch_at_minimum(self):
        """½\" RGD, actual R=4.5\" → is_compliant=True."""
        result = verify_bend_radius(ConduitType.RGD, TradeSize.HALF_INCH, 4.5)
        assert result.is_ok()
        assert result.value.is_compliant is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Non-compliant bend radii
# ─────────────────────────────────────────────────────────────────────────────

class TestBendViolation:
    """Bends below NEC minimum must be non-compliant (CodeViolationError)."""

    def test_emt_half_inch_below_minimum(self):
        """½\" EMT, actual R=3.5\" → is_compliant=False, min=4.0\"."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 3.5)
        assert result.is_err()
        assert isinstance(result.error, CodeViolationError)

    def test_upvc_sch40_half_inch_below_minimum(self):
        """½\" UPVC Sch40, actual R=3.0\" → violation."""
        result = verify_bend_radius(ConduitType.UPVC_SCH40, TradeSize.HALF_INCH, 3.0)
        assert result.is_err()
        assert isinstance(result.error, CodeViolationError)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Developed length calculation
# ─────────────────────────────────────────────────────────────────────────────

class TestDevelopedLength:
    """Arc length = π × R × angle / 180."""

    def test_90_degree_bend_r4_5(self):
        """R=4.5\", angle=90° → developed = π × 4.5 × 90/180 = π × 4.5 / 2 = 7.0686...\""""
        result = calculate_developed_length(4.5, 90.0)
        assert result.is_ok()
        assert result.value == pytest.approx(math.pi * 4.5 / 2, abs=0.001)

    def test_45_degree_bend_r4_5(self):
        """R=4.5\", angle=45° → developed = π × 4.5 × 45/180 = 3.534...\""""
        result = calculate_developed_length(4.5, 45.0)
        assert result.is_ok()
        assert result.value == pytest.approx(math.pi * 4.5 * 45.0 / 180.0, abs=0.001)

    def test_emt_half_inch_90_bend_developed_length(self):
        """½\" EMT R=4.0\", 90° → developed = π × 4.0 / 2 = 6.283...\""""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 4.0)
        assert result.is_ok()
        assert result.value.developed_length_in == pytest.approx(math.pi * 4.0 / 2, abs=0.001)
        assert result.value.developed_length_m == pytest.approx(math.pi * 4.0 / 2 * 0.0254, abs=0.001)


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Physics errors for invalid inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestBendPhysicsErrors:
    """Invalid inputs must return PhysicsError."""

    def test_negative_radius(self):
        """Negative radius → PhysicsError."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, -1.0)
        assert result.is_err()
        assert isinstance(result.error, PhysicsError)

    def test_zero_radius(self):
        """Zero radius → PhysicsError."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 0.0)
        assert result.is_err()
        assert isinstance(result.error, PhysicsError)

    def test_zero_angle(self):
        """Zero angle → PhysicsError."""
        result = calculate_developed_length(4.0, 0.0)
        assert result.is_err()
        assert isinstance(result.error, PhysicsError)

    def test_negative_angle(self):
        """Negative angle → PhysicsError."""
        result = calculate_developed_length(4.0, -45.0)
        assert result.is_err()
        assert isinstance(result.error, PhysicsError)

    def test_nan_radius(self):
        """NaN radius → PhysicsError."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, float('nan'))
        assert result.is_err()
        assert isinstance(result.error, PhysicsError)

    def test_angle_over_360(self):
        """Angle > 360° → PhysicsError."""
        result = verify_bend_radius(ConduitType.EMT, TradeSize.HALF_INCH, 4.0, angle_deg=361.0)
        assert result.is_err()
        assert isinstance(result.error, PhysicsError)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Cumulative bend limit (360°)
# ─────────────────────────────────────────────────────────────────────────────

class TestCumulativeBends:
    """Total bend degrees between pull points must not exceed 360°."""

    def test_four_90_bends_ok(self):
        """4 × 90° = 360° → exactly at limit → ok."""
        result = verify_cumulative_bends(ConduitType.EMT, [90.0, 90.0, 90.0, 90.0])
        assert result.is_ok()
        assert result.value == pytest.approx(360.0, abs=0.1)

    def test_five_90_bends_violation(self):
        """5 × 90° = 450° > 360° → violation."""
        result = verify_cumulative_bends(ConduitType.EMT, [90.0, 90.0, 90.0, 90.0, 90.0])
        assert result.is_err()
        assert isinstance(result.error, CodeViolationError)

    def test_three_90_bends_ok(self):
        """3 × 90° = 270° < 360° → ok."""
        result = verify_cumulative_bends(ConduitType.EMT, [90.0, 90.0, 90.0])
        assert result.is_ok()
        assert result.value == pytest.approx(270.0, abs=0.1)

    def test_max_cumulative_bend_deg_constant(self):
        """MAX_CUMULATIVE_BEND_DEG must equal 360.0."""
        assert MAX_CUMULATIVE_BEND_DEG == 360.0
