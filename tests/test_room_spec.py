"""Tests for RoomSpec strict validation - edge cases that MUST be rejected"""

import pytest
import math
from fireai.core.nfpa72_models import RoomSpec


class TestRoomSpecStrictValidation:
    """RoomSpec must reject ALL invalid inputs at construction"""

    def test_valid_room_creation(self):
        """✅ Valid room should be created successfully"""
        room = RoomSpec.create_validated(
            room_id="valid-room",
            name="Valid Room",
            width_m=6.0,
            depth_m=8.0,
            height_m=3.0,
            occupancy_type="office"
        )
        assert room.room_id == "valid-room"
        assert room.width_m == 6.0
        assert room.depth_m == 8.0
        assert room.polygon is not None
        assert room.polygon.area == 48.0

    def test_negative_width_rejected(self):
        """❌ Negative width must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="neg-width",
                width_m=-5.0,
                depth_m=10.0,
                occupancy_type="office"
            )
        assert "width_m must be > 0" in str(exc.value)

    def test_negative_depth_rejected(self):
        """❌ Negative depth must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="neg-depth",
                width_m=10.0,
                depth_m=-5.0,
                occupancy_type="office"
            )
        assert "depth_m must be > 0" in str(exc.value)

    def test_zero_width_rejected(self):
        """❌ Zero width must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="zero-width",
                width_m=0.0,
                depth_m=10.0,
                occupancy_type="office"
            )
        assert "width_m must be > 0" in str(exc.value)

    def test_zero_depth_rejected(self):
        """❌ Zero depth must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="zero-depth",
                width_m=10.0,
                depth_m=0.0,
                occupancy_type="office"
            )
        assert "depth_m must be > 0" in str(exc.value)

    def test_nan_width_rejected(self):
        """❌ NaN width must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="nan-width",
                width_m=float('nan'),
                depth_m=10.0,
                occupancy_type="office"
            )
        assert "width_m must be > 0" in str(exc.value) or "finite" in str(exc.value)

    def test_nan_depth_rejected(self):
        """❌ NaN depth must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="nan-depth",
                width_m=10.0,
                depth_m=float('nan'),
                occupancy_type="office"
            )
        assert "depth_m must be > 0" in str(exc.value) or "finite" in str(exc.value)

    def test_infinite_width_rejected(self):
        """❌ Infinite width must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="inf-width",
                width_m=float('inf'),
                depth_m=10.0,
                occupancy_type="office"
            )
        assert "width_m must be > 0" in str(exc.value) or "finite" in str(exc.value)

    def test_infinite_height_rejected(self):
        """❌ Infinite height must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="inf-height",
                width_m=10.0,
                depth_m=10.0,
                height_m=float('inf'),
                occupancy_type="office"
            )
        assert "height_m must be > 0" in str(exc.value) or "finite" in str(exc.value)

    def test_empty_room_id_rejected(self):
        """❌ Empty room_id must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="",
                width_m=10.0,
                depth_m=10.0,
                occupancy_type="office"
            )
        assert "room_id" in str(exc.value)

    def test_none_occupancy_type_rejected(self):
        """❌ None occupancy_type must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="test",
                width_m=10.0,
                depth_m=10.0,
                occupancy_type=None
            )
        assert "occupancy_type" in str(exc.value)

    def test_invalid_occupancy_type_rejected(self):
        """❌ Invalid occupancy_type must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="test",
                width_m=10.0,
                depth_m=10.0,
                occupancy_type="invalid_type_xyz"
            )
        assert "occupancy_type" in str(exc.value)

    def test_empty_polygon_list_rejected(self):
        """❌ Empty polygon list must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="test",
                width_m=10.0,
                depth_m=10.0,
                polygon=[],
                occupancy_type="office"
            )
        assert "polygon" in str(exc.value).lower()

    def test_single_point_polygon_rejected(self):
        """❌ Single point polygon must be REJECTED"""
        with pytest.raises(ValueError) as exc:
            RoomSpec(
                room_id="test",
                width_m=10.0,
                depth_m=10.0,
                polygon=[(0, 0)],
                occupancy_type="office"
            )
        assert "polygon" in str(exc.value).lower()

    def test_valid_polygon_list_accepted(self):
        """✅ Valid polygon list should be accepted"""
        room = RoomSpec.create_validated(
            room_id="test",
            width_m=10.0,
            depth_m=10.0,
            polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
            occupancy_type="office"
        )
        assert room.polygon is not None
        assert room.polygon.area == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])