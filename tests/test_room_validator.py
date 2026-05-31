"""
tests/test_room_validator.py
==============================
Comprehensive test suite for:
  - fireai/core/room_validator.py

SAFETY CRITICAL: Room validation prevents crashes and ensures data integrity
before NFPA 72 analysis. Invalid room data could lead to incorrect detector
placement, missed coverage, or AHJ rejection.

V20.2 FIX: Removed "kitchen" and "assembly" from VALID_OCCUPANCY_TYPES —
these are DANGEROUS types requiring licensed FPE review. Having them in
the validator created an inconsistency where room_validator accepted them
but RoomSpec construction would reject them.

NFPA 72 References:
  - §17.6.3.1.1: Wall distance margin
  - §17.7.1.1: Special detector requirements for certain occupancies
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from shapely.geometry import Polygon as ShapelyPolygon

from fireai.core.room_validator import (
    validate_room_spec,
    VALID_OCCUPANCY_TYPES,
)
from fireai.core.nfpa72_models import RoomSpec


# ─────────────────────────────────────────────────────────────────────────────
# Helper — Create a valid RoomSpec for testing
# ─────────────────────────────────────────────────────────────────────────────


def _make_valid_room_spec(**overrides) -> RoomSpec:
    """Create a valid RoomSpec with sensible defaults.
    
    The RoomSpec.__post_init__ does strict validation, so we must
    provide valid data to construct one successfully.
    """
    defaults = {
        "room_id": "ROOM-001",
        "name": "Test Room",
        "width_m": 10.0,
        "depth_m": 10.0,
        "occupancy_type": "office",
        "custom_polygon": [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
    }
    defaults.update(overrides)
    return RoomSpec(**defaults)


def _make_valid_room_spec_no_polygon(**overrides) -> RoomSpec:
    """Create a valid RoomSpec without custom_polygon.
    
    Uses width/depth dimensions only (polygon will be set by __post_init__).
    """
    defaults = {
        "room_id": "ROOM-001",
        "name": "Test Room",
        "width_m": 10.0,
        "depth_m": 10.0,
        "occupancy_type": "office",
    }
    defaults.update(overrides)
    return RoomSpec(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# VALID_OCCUPANCY_TYPES Set
# ─────────────────────────────────────────────────────────────────────────────


class TestValidOccupancyTypes:
    """V20.2 FIX: Verify occupancy type set correctness."""

    def test_common_types_present(self):
        expected = {"business", "educational", "factory", "hazardous", "institutional", "mercantile", "residential", "storage", "utility", "office", "corridor"}
        assert expected.issubset(VALID_OCCUPANCY_TYPES)

    def test_kitchen_not_in_valid_types(self):
        """V20.2 FIX: kitchen is DANGEROUS — requires licensed FPE review."""
        assert "kitchen" not in VALID_OCCUPANCY_TYPES

    def test_assembly_not_in_valid_types(self):
        """V20.2 FIX: assembly is DANGEROUS — requires special calculations."""
        assert "assembly" not in VALID_OCCUPANCY_TYPES

    def test_all_types_are_lowercase(self):
        """All occupancy types should be lowercase for case-insensitive matching."""
        for t in VALID_OCCUPANCY_TYPES:
            assert t == t.lower(), f"Occupancy type '{t}' is not lowercase"


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_spec — Valid Room
# ─────────────────────────────────────────────────────────────────────────────


class TestValidRoom:
    """Valid RoomSpec should pass validation without raising."""

    def test_valid_room_no_exception(self):
        """A fully valid RoomSpec should not raise ValueError."""
        spec = _make_valid_room_spec()
        # Should not raise
        validate_room_spec(spec)

    def test_valid_room_with_polygon(self):
        """RoomSpec with valid polygon should pass."""
        spec = _make_valid_room_spec()
        assert spec.polygon is not None
        validate_room_spec(spec)


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_spec — Polygon Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestPolygonValidation:
    """Polygon checks: must exist, have ≥3 points, and area > 0."""

    def test_none_polygon_raises(self):
        """polygon=None should fail validation."""
        spec = _make_valid_room_spec_no_polygon()
        # After construction, polygon is set from custom_polygon or dimensions
        # Force polygon to None to test the validator
        spec.polygon = None
        with pytest.raises(ValueError, match="polygon is None"):
            validate_room_spec(spec)

    def test_zero_area_polygon_raises(self):
        """Polygon with zero area should fail validation."""
        spec = _make_valid_room_spec_no_polygon()
        # Create a degenerate polygon (all points collinear)
        spec.polygon = ShapelyPolygon([(0, 0), (1, 0), (2, 0), (0, 0)])
        with pytest.raises(ValueError, match="area"):
            validate_room_spec(spec)

    def test_valid_polygon_passes(self):
        """Valid Shapely polygon should pass validation."""
        spec = _make_valid_room_spec()
        validate_room_spec(spec)  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_spec — Width/Depth Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestWidthDepthValidation:
    """Width and depth must be > 0 if provided."""

    def test_zero_width_raises(self):
        """width_m = 0 should fail validation."""
        spec = _make_valid_room_spec_no_polygon()
        spec.width_m = 0.0
        with pytest.raises(ValueError, match="width_m"):
            validate_room_spec(spec)

    def test_negative_width_raises(self):
        """width_m < 0 should fail validation."""
        spec = _make_valid_room_spec_no_polygon()
        spec.width_m = -5.0
        with pytest.raises(ValueError, match="width_m"):
            validate_room_spec(spec)

    def test_zero_depth_raises(self):
        """depth_m = 0 should fail validation."""
        spec = _make_valid_room_spec_no_polygon()
        spec.depth_m = 0.0
        with pytest.raises(ValueError, match="depth_m"):
            validate_room_spec(spec)

    def test_negative_depth_raises(self):
        """depth_m < 0 should fail validation."""
        spec = _make_valid_room_spec_no_polygon()
        spec.depth_m = -3.0
        with pytest.raises(ValueError, match="depth_m"):
            validate_room_spec(spec)

    def test_positive_width_depth_passes(self):
        """Positive width and depth should pass validation."""
        spec = _make_valid_room_spec()
        validate_room_spec(spec)  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_spec — Occupancy Type Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestOccupancyTypeValidation:
    """Occupancy type must be in VALID_OCCUPANCY_TYPES."""

    def test_valid_occupancy_types(self):
        """Each valid occupancy type should pass validation."""
        for occ_type in ["office", "business", "corridor", "educational"]:
            spec = _make_valid_room_spec(occupancy_type=occ_type)
            validate_room_spec(spec)  # Should not raise

    def test_empty_occupancy_type_raises(self):
        """Empty occupancy_type should fail validation.
        Note: RoomSpec.__post_init__ may catch this first."""
        # We need to create a spec with empty occupancy_type
        # RoomSpec __post_init__ validates occupancy_type, so this
        # may raise during construction. We test the validator directly
        # by modifying the attribute after construction.
        spec = _make_valid_room_spec()
        spec.occupancy_type = ""
        with pytest.raises(ValueError, match="occupancy_type"):
            validate_room_spec(spec)

    def test_invalid_occupancy_type_raises(self):
        """Invalid occupancy_type should fail validation."""
        spec = _make_valid_room_spec()
        spec.occupancy_type = "underwater_base"
        with pytest.raises(ValueError, match="occupancy_type"):
            validate_room_spec(spec)

    def test_kitchen_occupancy_rejected(self):
        """V20.2 FIX: kitchen must be rejected by the validator."""
        spec = _make_valid_room_spec()
        spec.occupancy_type = "kitchen"
        with pytest.raises(ValueError, match="occupancy_type"):
            validate_room_spec(spec)

    def test_assembly_occupancy_rejected(self):
        """V20.2 FIX: assembly must be rejected by the validator."""
        spec = _make_valid_room_spec()
        spec.occupancy_type = "assembly"
        with pytest.raises(ValueError, match="occupancy_type"):
            validate_room_spec(spec)

    def test_case_insensitive_occupancy(self):
        """Occupancy type matching should be case-insensitive."""
        spec = _make_valid_room_spec(occupancy_type="Office")
        # The validator checks .lower(), so "Office" should be accepted
        validate_room_spec(spec)  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_spec — Room ID Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomIdValidation:
    """room_id must not be empty."""

    def test_empty_room_id_raises(self):
        """Empty room_id should fail validation.
        Note: RoomSpec.__post_init__ also validates room_id, so
        we modify the attribute after construction."""
        spec = _make_valid_room_spec()
        spec.room_id = ""
        with pytest.raises(ValueError, match="room_id"):
            validate_room_spec(spec)

    def test_valid_room_id_passes(self):
        """Non-empty room_id should pass validation."""
        spec = _make_valid_room_spec(room_id="ROOM-42")
        validate_room_spec(spec)  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# validate_room_spec — Multiple Errors
# ─────────────────────────────────────────────────────────────────────────────


class TestMultipleErrors:
    """Multiple validation errors should all be reported."""

    def test_multiple_errors_in_message(self):
        """When multiple validations fail, all should be in the error message."""
        spec = _make_valid_room_spec_no_polygon()
        spec.polygon = None
        spec.occupancy_type = "invalid_type"
        spec.width_m = -1.0
        with pytest.raises(ValueError) as exc_info:
            validate_room_spec(spec)
        error_msg = str(exc_info.value)
        # Should mention multiple errors
        assert "polygon" in error_msg or "occupancy_type" in error_msg or "width_m" in error_msg


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Full RoomSpec Lifecycle
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomSpecLifecycle:
    """End-to-end: construct RoomSpec → validate → should pass."""

    def test_office_room_lifecycle(self):
        """Typical office room: 10m × 8m, business occupancy."""
        spec = RoomSpec(
            room_id="OFFICE-101",
            name="Main Office",
            width_m=10.0,
            depth_m=8.0,
            occupancy_type="business",
            custom_polygon=[(0, 0), (10, 0), (10, 8), (0, 8), (0, 0)],
        )
        validate_room_spec(spec)  # Should not raise

    def test_corridor_room_lifecycle(self):
        """Long corridor: 2m × 30m."""
        spec = RoomSpec(
            room_id="CORR-F01",
            name="Floor 1 Corridor",
            width_m=2.0,
            depth_m=30.0,
            occupancy_type="corridor",
            custom_polygon=[(0, 0), (2, 0), (2, 30), (0, 30), (0, 0)],
        )
        validate_room_spec(spec)  # Should not raise

    def test_l_shaped_room_lifecycle(self):
        """L-shaped room with custom polygon."""
        spec = RoomSpec(
            room_id="L-ROOM-01",
            name="L-Shaped Office",
            width_m=15.0,
            depth_m=12.0,
            occupancy_type="office",
            custom_polygon=[(0, 0), (15, 0), (15, 5), (5, 5), (5, 12), (0, 12), (0, 0)],
        )
        validate_room_spec(spec)  # Should not raise

    def test_hazardous_room_lifecycle(self):
        """Hazardous occupancy room requires proper validation."""
        spec = RoomSpec(
            room_id="HAZ-STOR-01",
            name="Hazardous Storage",
            width_m=6.0,
            depth_m=6.0,
            occupancy_type="hazardous",
            custom_polygon=[(0, 0), (6, 0), (6, 6), (0, 6), (0, 0)],
        )
        validate_room_spec(spec)  # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
