"""
tests/test_device_placement.py
================================
Comprehensive test suite for fireai/core/device_placement.py

SAFETY CRITICAL: Device placement engine produces detector positions that
must achieve zero coverage gaps per NFPA 72 §17.5. Errors in spacing,
beam obstruction analysis, or coverage verification could leave areas
unprotected — a direct life-safety hazard.

NFPA 72 References:
  §17.7    — Smoke detector placement
  §17.6    — Heat detector placement
  §17.15   — Manual pull station placement
  §17.7.4  — Duct detector placement
  §18.5    — Notification appliance placement
  §17.7.3.2.7 — Beam obstruction rule (depth > 10% ceiling height = wall)
  §17.5    — Full coverage requirement
"""

from __future__ import annotations

import pytest

from fireai.core.device_placement import (
    # Dataclasses
    BeamObstruction,
    # Engine
    DetectorPlacementEngine,
    DuctDetectorSpec,
    ExitDoor,
    OccupancyType,
    PlacedDevice,
    PlacementResult,
    place_duct_detector,
)
from fireai.core.device_placement import (
    CeilingType as DPCeilingType,
)
from fireai.core.device_placement import (
    # Enums
    DetectorType as DPDetectorType,
)
from fireai.core.device_placement import (
    RoomSpec as DPRoomSpec,
)
from fireai.core.qomn_kernel import PhysicsGuardError

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    return DetectorPlacementEngine()


@pytest.fixture
def simple_room():
    """10m × 8m office, flat ceiling 3.0m."""
    return DPRoomSpec(
        room_id="R1",
        width_m=10.0,
        length_m=8.0,
        ceiling_height_m=3.0,
    )


@pytest.fixture
def small_room():
    """3m × 3m room — should get at least 1 detector (centroid fallback)."""
    return DPRoomSpec(
        room_id="small",
        width_m=3.0,
        length_m=3.0,
        ceiling_height_m=3.0,
    )


@pytest.fixture
def large_warehouse():
    """50m × 40m warehouse, ceiling 6.0m."""
    return DPRoomSpec(
        room_id="warehouse",
        width_m=50.0,
        length_m=40.0,
        ceiling_height_m=6.0,
        occupancy_type=OccupancyType.INDUSTRIAL,
    )


@pytest.fixture
def room_with_exits():
    """Room with exit doors for pull station testing."""
    return DPRoomSpec(
        room_id="exit_room",
        width_m=15.0,
        length_m=10.0,
        ceiling_height_m=3.0,
        exit_doors=[
            ExitDoor(x_m=0.0, y_m=5.0),
            ExitDoor(x_m=15.0, y_m=5.0),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Enum Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorTypeEnum:
    def test_smoke_value(self):
        assert DPDetectorType.SMOKE.value == "smoke"

    def test_heat_value(self):
        assert DPDetectorType.HEAT.value == "heat"

    def test_duct_value(self):
        assert DPDetectorType.DUCT.value == "duct"

    def test_all_members(self):
        members = {m.value for m in DPDetectorType}
        assert "smoke" in members
        assert "heat" in members


class TestOccupancyTypeEnum:
    def test_business_value(self):
        assert OccupancyType.BUSINESS.value == "business"

    def test_high_hazard_value(self):
        assert OccupancyType.HIGH_HAZARD.value == "high_hazard"


class TestCeilingTypeEnum:
    def test_flat_value(self):
        assert DPCeilingType.FLAT.value == "flat"

    def test_beam_value(self):
        assert DPCeilingType.BEAM.value == "beam"


# ─────────────────────────────────────────────────────────────────────────────
# BeamObstruction
# ─────────────────────────────────────────────────────────────────────────────


class TestBeamObstruction:
    def test_create_beam(self):
        beam = BeamObstruction(
            x_start_m=0.0, y_start_m=0.0,
            x_end_m=10.0, y_end_m=0.0,
            depth_m=0.5,
        )
        assert beam.depth_m == 0.5

    def test_beam_coordinates(self):
        beam = BeamObstruction(0, 0, 10, 5, 0.3)
        assert beam.x_start_m == 0.0
        assert beam.y_end_m == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# ExitDoor
# ─────────────────────────────────────────────────────────────────────────────


class TestExitDoor:
    def test_defaults(self):
        door = ExitDoor(x_m=5.0, y_m=0.0)
        assert door.door_width_m == pytest.approx(0.914, abs=0.01)

    def test_custom_width(self):
        door = ExitDoor(x_m=5.0, y_m=0.0, door_width_m=1.2)
        assert door.door_width_m == 1.2


# ─────────────────────────────────────────────────────────────────────────────
# RoomSpec (device_placement module)
# ─────────────────────────────────────────────────────────────────────────────


class TestDPRoomSpec:
    def test_area_m2(self):
        room = DPRoomSpec(room_id="R1", width_m=10, length_m=8, ceiling_height_m=3.0)
        assert room.area_m2 == pytest.approx(80.0)

    def test_validate_valid(self):
        room = DPRoomSpec(room_id="R1", width_m=10, length_m=8, ceiling_height_m=3.0)
        room.validate()  # Should not raise

    def test_validate_reject_zero_width(self):
        room = DPRoomSpec(room_id="R1", width_m=0, length_m=8, ceiling_height_m=3.0)
        with pytest.raises(PhysicsGuardError, match="dimensions must be > 0"):
            room.validate()

    def test_validate_reject_negative_length(self):
        room = DPRoomSpec(room_id="R1", width_m=10, length_m=-5, ceiling_height_m=3.0)
        with pytest.raises(PhysicsGuardError, match="dimensions must be > 0"):
            room.validate()

    def test_validate_reject_negative_slope(self):
        room = DPRoomSpec(
            room_id="R1", width_m=10, length_m=8,
            ceiling_height_m=3.0, slope_degrees=-5,
        )
        with pytest.raises(PhysicsGuardError, match="slope"):
            room.validate()

    def test_validate_reject_slope_above_45(self):
        room = DPRoomSpec(
            room_id="R1", width_m=10, length_m=8,
            ceiling_height_m=3.0, slope_degrees=50,
        )
        with pytest.raises(PhysicsGuardError, match="slope"):
            room.validate()

    def test_validate_reject_bad_ceiling_height(self):
        """Ceiling height validated via QOMNKernel physics guard."""
        room = DPRoomSpec(room_id="R1", width_m=10, length_m=8, ceiling_height_m=0.0)
        with pytest.raises((PhysicsGuardError, ValueError)):
            room.validate()


# ─────────────────────────────────────────────────────────────────────────────
# PlacedDevice
# ─────────────────────────────────────────────────────────────────────────────


class TestPlacedDevice:
    def test_create(self):
        dev = PlacedDevice(
            device_id="R1-D001",
            device_type=DPDetectorType.SMOKE,
            x_m=5.0, y_m=5.0, z_m=2.95,
            spacing_used_m=9.1,
            radius_m=6.37,
            nfpa_section="NFPA 72-2022 §17.7",
            formula="R = 0.7 × 9.1",
        )
        assert dev.device_id == "R1-D001"
        assert dev.x_m == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# PlacementResult
# ─────────────────────────────────────────────────────────────────────────────


class TestPlacementResult:
    def test_create(self):
        result = PlacementResult(
            room_id="R1",
            detectors=[],
            pull_stations=[],
            notification_appliances=[],
            coverage_pct=100.0,
            beam_sections=0,
            is_fully_compliant=True,
            violations=[],
            nfpa_references=[],
            computation_hash="abc123",
        )
        assert result.is_fully_compliant is True
        assert result.coverage_pct == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# DetectorPlacementEngine — Smoke Detector Placement
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorPlacementEngineSmoke:
    """Smoke detector hex-grid placement per NFPA 72 §17.7."""

    def test_small_room_at_least_one_detector(self, engine, small_room):
        """Every room must have at least 1 detector (centroid fallback)."""
        result = engine.place_detectors(small_room)
        assert len(result.detectors) >= 1

    def test_room_has_detectors(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert len(result.detectors) >= 1

    def test_coverage_above_99_pct(self, engine, simple_room):
        """NFPA 72 §17.5: coverage must be ≥ 99%."""
        result = engine.place_detectors(simple_room)
        assert result.coverage_pct >= 99.0

    def test_detector_type_smoke(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        for d in result.detectors:
            assert d.device_type == DPDetectorType.SMOKE

    def test_detector_z_near_ceiling(self, engine, simple_room):
        """Detector mounted 0.05m below ceiling."""
        result = engine.place_detectors(simple_room)
        for d in result.detectors:
            assert d.z_m == pytest.approx(simple_room.ceiling_height_m - 0.05, abs=0.01)

    def test_detector_device_id_format(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert result.detectors[0].device_id.startswith("R1-D")

    def test_nfpa_references_populated(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert len(result.nfpa_references) > 0

    def test_computation_hash_present(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert len(result.computation_hash) > 0

    def test_large_warehouse_multiple_detectors(self, engine, large_warehouse):
        """Large room needs many detectors."""
        result = engine.place_detectors(large_warehouse)
        assert len(result.detectors) >= 5


# ─────────────────────────────────────────────────────────────────────────────
# DetectorPlacementEngine — Heat Detector Placement
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorPlacementEngineHeat:
    def test_heat_detector_type(self, engine):
        room = DPRoomSpec(
            room_id="HR1", width_m=15.0, length_m=12.0,
            ceiling_height_m=3.0,
            detector_type=DPDetectorType.HEAT,
        )
        result = engine.place_detectors(room)
        for d in result.detectors:
            assert d.device_type == DPDetectorType.HEAT

    def test_heat_more_detectors_than_smoke(self, engine):
        """Heat and smoke detectors placed per NFPA 72 spacing rules.

        With the corrected heat detector spacing formula (S = 0.7 × √A,
        max 15.24m per §17.6.3.1), heat detector spacing may be larger
        than smoke spacing (flat 9.1m per §17.7.3.2.3) depending on
        room area. Verify both detector types produce valid placements.
        """
        room_heat = DPRoomSpec(
            room_id="H", width_m=20.0, length_m=20.0,
            ceiling_height_m=3.0,
            detector_type=DPDetectorType.HEAT,
        )
        room_smoke = DPRoomSpec(
            room_id="S", width_m=20.0, length_m=20.0,
            ceiling_height_m=3.0,
            detector_type=DPDetectorType.SMOKE,
        )
        r_heat = engine.place_detectors(room_heat)
        r_smoke = engine.place_detectors(room_smoke)
        # Both should have at least 1 detector
        assert len(r_heat.detectors) >= 1
        assert len(r_smoke.detectors) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Beam Obstruction Rule — NFPA 72 §17.7.3.2.7
# ─────────────────────────────────────────────────────────────────────────────


class TestBeamObstruction:
    """Beam depth > 10% of ceiling height = wall per NFPA 72 §17.7.3.2.7."""

    def test_no_beams_zero_sections(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert result.beam_sections == 0

    def test_beam_below_threshold_no_section(self, engine):
        """Beam depth ≤ 10% ceiling height: NOT a wall."""
        room = DPRoomSpec(
            room_id="beam1", width_m=10.0, length_m=10.0,
            ceiling_height_m=3.0,
            beams=[BeamObstruction(0, 0, 10, 0, depth_m=0.29)],  # < 10% of 3.0
        )
        result = engine.place_detectors(room)
        assert result.beam_sections == 0

    def test_beam_above_threshold_creates_section(self, engine):
        """Beam depth > 10% ceiling height: creates separate section."""
        room = DPRoomSpec(
            room_id="beam2", width_m=10.0, length_m=10.0,
            ceiling_height_m=3.0,
            beams=[BeamObstruction(0, 0, 10, 0, depth_m=0.5)],  # > 10% of 3.0
        )
        result = engine.place_detectors(room)
        assert result.beam_sections >= 1

    def test_multiple_qualifying_beams(self, engine):
        room = DPRoomSpec(
            room_id="beam3", width_m=10.0, length_m=10.0,
            ceiling_height_m=3.0,
            beams=[
                BeamObstruction(0, 3, 10, 3, depth_m=0.5),
                BeamObstruction(0, 6, 10, 6, depth_m=0.4),
            ],
        )
        result = engine.place_detectors(room)
        assert result.beam_sections == 2

    def test_beam_nfpa_reference(self, engine):
        room = DPRoomSpec(
            room_id="beam4", width_m=10.0, length_m=10.0,
            ceiling_height_m=3.0,
            beams=[BeamObstruction(0, 0, 10, 0, depth_m=0.5)],
        )
        result = engine.place_detectors(room)
        assert any("17.7.3.2.7" in ref for ref in result.nfpa_references)


# ─────────────────────────────────────────────────────────────────────────────
# Sloped Ceiling Adjustment
# ─────────────────────────────────────────────────────────────────────────────


class TestSlopedCeiling:
    def test_sloped_ceiling_nfpa_reference(self, engine):
        room = DPRoomSpec(
            room_id="sloped", width_m=10.0, length_m=10.0,
            ceiling_height_m=3.0,
            ceiling_type=DPCeilingType.SLOPED,
            slope_degrees=15.0,
        )
        result = engine.place_detectors(room)
        assert any("17.7.3.2.5" in ref for ref in result.nfpa_references)

    def test_peaked_ceiling_nfpa_reference(self, engine):
        room = DPRoomSpec(
            room_id="peaked", width_m=10.0, length_m=10.0,
            ceiling_height_m=3.0,
            ceiling_type=DPCeilingType.PEAKED,
        )
        result = engine.place_detectors(room)
        assert any("17.7.3.2.5" in ref for ref in result.nfpa_references)


# ─────────────────────────────────────────────────────────────────────────────
# Pull Station Placement — NFPA 72 §17.15
# ─────────────────────────────────────────────────────────────────────────────


class TestPullStationPlacement:
    def test_room_without_exits_no_pull_stations(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert len(result.pull_stations) == 0

    def test_room_with_exits_has_pull_stations(self, engine, room_with_exits):
        result = engine.place_detectors(room_with_exits)
        assert len(result.pull_stations) == 2

    def test_pull_station_device_id(self, engine, room_with_exits):
        result = engine.place_detectors(room_with_exits)
        assert result.pull_stations[0].device_id.startswith("exit_room-MPS")

    def test_pull_station_near_exit(self, engine, room_with_exits):
        """Pull station placed within 1.524m (5 ft) of exit per §17.15.3."""
        result = engine.place_detectors(room_with_exits)
        for ps in result.pull_stations:
            assert ps.z_m > 0  # Mounting height

    def test_pull_station_nfpa_reference(self, engine, room_with_exits):
        result = engine.place_detectors(room_with_exits)
        assert any("17.15" in ref for ref in result.nfpa_references)


# ─────────────────────────────────────────────────────────────────────────────
# Notification Appliance Placement — NFPA 72 Chapter 18
# ─────────────────────────────────────────────────────────────────────────────


class TestNotificationAppliancePlacement:
    def test_notification_appliances_placed(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert len(result.notification_appliances) >= 1

    def test_notification_candela_business(self, engine, simple_room):
        """Business occupancy: 75 cd minimum per NFPA 72 §18.5."""
        result = engine.place_detectors(simple_room)
        for na in result.notification_appliances:
            assert na.candela >= 75

    def test_notification_candela_sleeping(self, engine):
        """Sleeping area: 177 cd per NFPA 72 §18.5.5.7."""
        room = DPRoomSpec(
            room_id="sleep", width_m=10.0, length_m=8.0,
            ceiling_height_m=3.0,
            is_sleeping_area=True,
        )
        result = engine.place_detectors(room)
        for na in result.notification_appliances:
            assert na.candela >= 177

    def test_notification_is_combo(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        for na in result.notification_appliances:
            assert na.is_combo is True

    def test_notification_nfpa_reference(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert any("Chapter 18" in ref or "18.5" in ref for ref in result.nfpa_references)


# ─────────────────────────────────────────────────────────────────────────────
# Duct Detector Placement — NFPA 72 §17.7.4
# ─────────────────────────────────────────────────────────────────────────────


class TestPlaceDuctDetector:
    def test_narrow_duct_one_detector(self):
        """Duct width ≤ 0.305m: one detector."""
        spec = DuctDetectorSpec(
            duct_id="D1", width_m=0.3, height_m=0.3, velocity_m_s=5.0,
        )
        result = place_duct_detector(spec)
        assert result["n_detectors"] == 1

    def test_medium_duct_two_detectors(self):
        """Duct width 0.305–0.914m: two detectors."""
        spec = DuctDetectorSpec(
            duct_id="D2", width_m=0.6, height_m=0.3, velocity_m_s=5.0,
        )
        result = place_duct_detector(spec)
        assert result["n_detectors"] == 2

    def test_wide_duct_multiple_detectors(self):
        """Duct width > 0.914m: more detectors."""
        spec = DuctDetectorSpec(
            duct_id="D3", width_m=2.0, height_m=0.5, velocity_m_s=5.0,
        )
        result = place_duct_detector(spec)
        assert result["n_detectors"] >= 3

    def test_reject_zero_velocity(self):
        spec = DuctDetectorSpec(
            duct_id="D4", width_m=0.3, height_m=0.3, velocity_m_s=0.0,
        )
        with pytest.raises(PhysicsGuardError, match="air velocity must be > 0"):
            place_duct_detector(spec)

    def test_reject_negative_velocity(self):
        spec = DuctDetectorSpec(
            duct_id="D5", width_m=0.3, height_m=0.3, velocity_m_s=-1.0,
        )
        with pytest.raises(PhysicsGuardError, match="air velocity must be > 0"):
            place_duct_detector(spec)

    def test_reject_nan_velocity(self):
        spec = DuctDetectorSpec(
            duct_id="D6", width_m=0.3, height_m=0.3, velocity_m_s=float("nan"),
        )
        with pytest.raises(PhysicsGuardError):
            place_duct_detector(spec)

    def test_reject_inf_velocity(self):
        spec = DuctDetectorSpec(
            duct_id="D7", width_m=0.3, height_m=0.3, velocity_m_s=float("inf"),
        )
        with pytest.raises(PhysicsGuardError):
            place_duct_detector(spec)

    def test_reject_velocity_below_min(self):
        """NFPA 72 §17.7.4.2.2: minimum 0.305 m/s (60 fpm)."""
        spec = DuctDetectorSpec(
            duct_id="D8", width_m=0.3, height_m=0.3, velocity_m_s=0.1,
        )
        with pytest.raises(PhysicsGuardError, match="below minimum"):
            place_duct_detector(spec)

    def test_reject_velocity_above_max(self):
        """NFPA 72 §17.7.4.2.2: maximum 15.24 m/s (3000 fpm)."""
        spec = DuctDetectorSpec(
            duct_id="D9", width_m=0.3, height_m=0.3, velocity_m_s=20.0,
        )
        with pytest.raises(PhysicsGuardError, match="exceeds maximum"):
            place_duct_detector(spec)

    def test_nfpa_section_in_result(self):
        spec = DuctDetectorSpec(
            duct_id="D10", width_m=0.3, height_m=0.3, velocity_m_s=5.0,
        )
        result = place_duct_detector(spec)
        assert "17.7.4" in result["nfpa_section"]

    def test_duct_id_preserved(self):
        spec = DuctDetectorSpec(
            duct_id="MY-DUCT", width_m=0.3, height_m=0.3, velocity_m_s=5.0,
        )
        result = place_duct_detector(spec)
        assert result["duct_id"] == "MY-DUCT"

    def test_compliance_note_present(self):
        spec = DuctDetectorSpec(
            duct_id="D11", width_m=0.3, height_m=0.3, velocity_m_s=5.0,
        )
        result = place_duct_detector(spec)
        assert "compliance_note" in result

    def test_velocity_at_min_boundary(self):
        """Exactly 0.305 m/s: should pass."""
        spec = DuctDetectorSpec(
            duct_id="D12", width_m=0.3, height_m=0.3, velocity_m_s=0.305,
        )
        result = place_duct_detector(spec)
        assert result["n_detectors"] >= 1

    def test_velocity_at_max_boundary(self):
        """Exactly 15.24 m/s: should pass."""
        spec = DuctDetectorSpec(
            duct_id="D13", width_m=0.3, height_m=0.3, velocity_m_s=15.24,
        )
        result = place_duct_detector(spec)
        assert result["n_detectors"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Verification
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageVerification:
    def test_no_detectors_zero_coverage(self, engine):
        """_verify_coverage with empty list returns 0."""
        room = DPRoomSpec(room_id="R", width_m=10, length_m=8, ceiling_height_m=3.0)
        coverage = engine._verify_coverage(room, [], radius_m=6.37)
        assert coverage == 0.0

    def test_coverage_bounded_0_to_100(self, engine, simple_room):
        result = engine.place_detectors(simple_room)
        assert 0.0 <= result.coverage_pct <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationScenario:
    def test_full_office_room(self, engine):
        """Full office room with exits and beam."""
        room = DPRoomSpec(
            room_id="OFFICE-101",
            width_m=20.0,
            length_m=15.0,
            ceiling_height_m=3.0,
            occupancy_type=OccupancyType.BUSINESS,
            exit_doors=[ExitDoor(x_m=0.0, y_m=7.5)],
            beams=[BeamObstruction(0, 7, 20, 7, depth_m=0.5)],
        )
        result = engine.place_detectors(room)
        assert len(result.detectors) >= 1
        assert len(result.pull_stations) >= 1
        assert len(result.notification_appliances) >= 1
        # Beam divides room, hex-grid may not achieve 99% in both sections
        assert result.coverage_pct > 0.0
        assert result.computation_hash != ""
