"""
fireai/core/tests/test_device_placement.py — Tests for Device Placement Engine.

NFPA 72-2022 §17.7: Smoke detector placement
NFPA 72-2022 §17.6: Heat detector placement
NFPA 72-2022 §17.7.3.2.1: 3D placement requirements
UL 268: Smoke detector spacing for high ceilings
"""

import math
import pytest

from fireai.core.device_placement import (
    BeamObstruction,
    CeilingType,
    DetectorPlacementEngine,
    DetectorType,
    ExitDoor,
    OccupancyType,
    PlacedDevice,
    PlacedPullStation,
    PlacedNotificationAppliance,
    PlacementResult,
    RoomSpec,
    calculate_3d_detector_placement,
    DuctDetectorSpec,
    place_duct_detector,
)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> DetectorPlacementEngine:
    """Create a DetectorPlacementEngine instance."""
    return DetectorPlacementEngine()


@pytest.fixture
def simple_room() -> RoomSpec:
    """Create a simple rectangular room for testing."""
    return RoomSpec(
        room_id="test-room-001",
        width_m=10.0,
        length_m=12.0,
        ceiling_height_m=3.0,
        detector_type=DetectorType.SMOKE,
    )


@pytest.fixture
def heat_room() -> RoomSpec:
    """Create a room for heat detector testing."""
    return RoomSpec(
        room_id="heat-room-001",
        width_m=8.0,
        length_m=8.0,
        ceiling_height_m=3.0,
        detector_type=DetectorType.HEAT,
    )


# ── RoomSpec Validation Tests ─────────────────────────────────────────────


class TestRoomSpecValidation:
    """Test RoomSpec validation (physics guards)."""

    def test_valid_room(self, simple_room: RoomSpec):
        """Valid room should pass validation without error."""
        simple_room.validate()  # Should not raise

    def test_zero_width_rejected(self):
        """Zero width must raise PhysicsGuardError."""
        with pytest.raises(Exception):
            RoomSpec(
                room_id="bad",
                width_m=0,
                length_m=10,
                ceiling_height_m=3.0,
            ).validate()

    def test_negative_length_rejected(self):
        """Negative length must raise PhysicsGuardError."""
        with pytest.raises(Exception):
            RoomSpec(
                room_id="bad",
                width_m=10,
                length_m=-5,
                ceiling_height_m=3.0,
            ).validate()

    def test_nan_dimensions_rejected(self):
        """NaN dimensions must raise PhysicsGuardError."""
        with pytest.raises(Exception):
            RoomSpec(
                room_id="bad",
                width_m=float("nan"),
                length_m=10,
                ceiling_height_m=3.0,
            ).validate()

    def test_slope_exceeds_45_degrees(self):
        """Slope > 45 degrees must raise PhysicsGuardError."""
        with pytest.raises(Exception):
            RoomSpec(
                room_id="bad",
                width_m=10,
                length_m=10,
                ceiling_height_m=3.0,
                slope_degrees=60,
            ).validate()


# ── Smoke Detector Placement Tests ────────────────────────────────────────


class TestSmokeDetectorPlacement:
    """NFPA 72 §17.7: Smoke detector placement."""

    def test_basic_placement(self, engine: DetectorPlacementEngine, simple_room: RoomSpec):
        """Basic smoke detector placement should produce valid result."""
        result = engine.place_detectors(simple_room)
        assert isinstance(result, PlacementResult)
        assert result.room_id == "test-room-001"
        assert len(result.detectors) > 0
        assert result.coverage_pct > 0

    def test_all_detectors_have_z_coordinate(self, engine: DetectorPlacementEngine, simple_room: RoomSpec):
        """All placed detectors should have a valid z coordinate."""
        result = engine.place_detectors(simple_room)
        for d in result.detectors:
            assert d.z_m > 0
            assert d.z_m <= simple_room.ceiling_height_m

    def test_small_room_gets_at_least_one(self, engine: DetectorPlacementEngine):
        """Even very small rooms should get at least one detector."""
        small_room = RoomSpec(
            room_id="tiny",
            width_m=2.0,
            length_m=2.0,
            ceiling_height_m=3.0,
            detector_type=DetectorType.SMOKE,
        )
        result = engine.place_detectors(small_room)
        assert len(result.detectors) >= 1


# ── Heat Detector Placement Tests ────────────────────────────────────────


class TestHeatDetectorPlacement:
    """NFPA 72 §17.6: Heat detector placement."""

    def test_heat_placement(self, engine: DetectorPlacementEngine, heat_room: RoomSpec):
        """Heat detector placement should produce valid result."""
        result = engine.place_detectors(heat_room)
        assert len(result.detectors) > 0
        assert all(d.device_type == DetectorType.HEAT for d in result.detectors)


# ── Pull Station Placement Tests ──────────────────────────────────────────


class TestPullStationPlacement:
    """NFPA 72 §17.15: Manual pull station placement."""

    def test_pull_station_near_exit(self, engine: DetectorPlacementEngine):
        """Pull stations should be placed near exit doors."""
        room = RoomSpec(
            room_id="room-with-exit",
            width_m=10.0,
            length_m=10.0,
            ceiling_height_m=3.0,
            detector_type=DetectorType.SMOKE,
            exit_doors=[ExitDoor(x_m=5.0, y_m=0.0)],
        )
        result = engine.place_detectors(room)
        assert len(result.pull_stations) >= 1


# ── 3D Detector Placement Tests ───────────────────────────────────────────


class Test3DDetectorPlacement:
    """NFPA 72 Section 17.7.3.2.1 & UL 268: 3D placement tests.

    These tests verify the calculate_3d_detector_placement function
    which computes detector positions in 3D space (x, y, z) for
    spaces with varying ceiling heights.
    """

    def test_standard_ceiling(self):
        """Test placement with standard 3m ceiling."""
        floor_plan = {"width": 15.0, "length": 15.0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=3.0)
        assert len(result["detectors"]) > 0
        # All detectors should be at ceiling_height - 0.5m
        for d in result["detectors"]:
            assert d[2] == round(3.0 - 0.5, 4)  # z = 2.5m

    def test_high_ceiling_warning(self):
        """Test warning for ceiling > 9.14m (30ft) per NFPA 72."""
        floor_plan = {"width": 15.0, "length": 15.0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=10.0)
        assert result["compliant"] is False
        assert len(result["warnings"]) > 0
        assert any("9.1m" in w or "30ft" in w for w in result["warnings"])

    def test_heat_detector_spacing(self):
        """Test heat detector spacing (6.10m per NFPA 72 §17.6)."""
        floor_plan = {"width": 18.0, "length": 18.0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=3.0, detector_type="heat")
        assert len(result["detectors"]) >= 4  # 18m / 6.1m spacing needs multiple detectors

    def test_smoke_detector_spacing(self):
        """Test smoke detector spacing (9.10m per NFPA 72 §17.7)."""
        floor_plan = {"width": 30.0, "length": 30.0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=3.0, detector_type="smoke")
        assert len(result["detectors"]) >= 4  # 30m / 9.1m spacing needs multiple detectors

    def test_invalid_detector_type(self):
        """Test invalid detector type returns warning."""
        floor_plan = {"width": 15.0, "length": 15.0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=3.0, detector_type="invalid")
        assert result["compliant"] is False
        assert len(result["warnings"]) > 0

    def test_zero_dimensions(self):
        """Test zero floor plan dimensions."""
        floor_plan = {"width": 0, "length": 0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=3.0)
        assert result["compliant"] is False
        assert len(result["detectors"]) == 0

    def test_all_detectors_have_3d_coordinates(self):
        """All detectors should have valid x, y, z coordinates."""
        floor_plan = {"width": 20.0, "length": 20.0}
        result = calculate_3d_detector_placement(floor_plan, ceiling_height=4.0)
        for d in result["detectors"]:
            assert len(d) == 3  # (x, y, z)
            assert d[0] > 0  # x > 0
            assert d[1] > 0  # y > 0
            assert d[2] > 0  # z > 0


# ── Duct Detector Placement Tests ─────────────────────────────────────────


class TestDuctDetectorPlacement:
    """NFPA 72 §17.7.4: Duct detector placement."""

    def test_small_duct_one_detector(self):
        """Small duct (≤ 0.305m width) needs one detector."""
        spec = DuctDetectorSpec(duct_id="D1", width_m=0.25, height_m=0.20, velocity_m_s=5.0)
        result = place_duct_detector(spec)
        assert result["n_detectors"] == 1

    def test_medium_duct_two_detectors(self):
        """Medium duct (> 0.305m, ≤ 0.914m width) needs two detectors."""
        spec = DuctDetectorSpec(duct_id="D2", width_m=0.50, height_m=0.30, velocity_m_s=5.0)
        result = place_duct_detector(spec)
        assert result["n_detectors"] == 2

    def test_zero_velocity_rejected(self):
        """Zero velocity must raise PhysicsGuardError."""
        spec = DuctDetectorSpec(duct_id="D3", width_m=0.25, height_m=0.20, velocity_m_s=0)
        with pytest.raises(Exception):
            place_duct_detector(spec)
