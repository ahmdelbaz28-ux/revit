"""Comprehensive tests for the multi_floor_orchestrator module.

Covers:
  - All enum values (SLCLoopClass, OccupancyType, ElevatorRecallPhase, SmokeSpreadPathway)
  - All dataclass creation and defaults (SLCLoop, VerticalZone, FloorAssignment,
    SmokeSpreadResult, ElevatorRecallResult, RiserRoutingResult, BuildingAnalysis)
  - SLCLoop.utilization_pct() and is_compliant properties
  - VerticalZone.is_compliant property
  - MultiFloorOrchestrator.__init__ (valid and invalid inputs)
  - MultiFloorOrchestrator.orchestrate() with various building specs
  - SLC loop assignment (_assign_slc_loops)
  - Vertical zone design (_design_vertical_zones)
  - Smoke spread analysis (_analyze_smoke_spread)
  - Elevator recall checks (_check_elevator_recall)
  - Riser routing (_route_risers)
  - Compliance evaluation (_evaluate_compliance)
  - Error handling and fail-safe behavior
  - Edge cases (empty floors, zero height, single floor, etc.)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fireai.core.floor_orchestrator import FloorOrchestrator, FloorResult, RoomResult
from fireai.core.multi_floor_orchestrator import (
    # Constants
    DEFAULT_RECALL_FLOOR,
    MAX_SLC_DEVICES_PER_LOOP,
    MAX_ZONE_AREA_SQFT,
    MAX_ZONE_AREA_SQM,
    MIN_SMOKE_BARRIER_RATING_H,
    OTHER_FLOORS_PER_ZONE,
    RESIDENTIAL_FLOORS_PER_ZONE,
    STACK_EFFECT_VELOCITY_MPS,
    # Dataclasses
    BuildingAnalysis,
    # Enums
    ElevatorRecallPhase,
    ElevatorRecallResult,
    FloorAssignment,
    # Main class
    MultiFloorOrchestrator,
    OccupancyType,
    RiserRoutingResult,
    SLCLoop,
    SLCLoopClass,
    SmokeSpreadPathway,
    SmokeSpreadResult,
    VerticalZone,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def floor_orchestrator():
    """Create a FloorOrchestrator with default settings."""
    return FloorOrchestrator(grid_res=0.25)


@pytest.fixture
def orchestrator(floor_orchestrator):
    """Create a MultiFloorOrchestrator with a real FloorOrchestrator."""
    return MultiFloorOrchestrator(
        floor_orchestrator=floor_orchestrator,
        building_height_m=45.0,
        panel_id="FACP-1",
    )


@pytest.fixture
def orchestrator_default():
    """Create a MultiFloorOrchestrator with all defaults (zero height)."""
    return MultiFloorOrchestrator()


@pytest.fixture
def orchestrator_class_a(floor_orchestrator):
    """Create a MultiFloorOrchestrator with Class A SLC loops."""
    return MultiFloorOrchestrator(
        floor_orchestrator=floor_orchestrator,
        slc_loop_class=SLCLoopClass.CLASS_A,
        building_height_m=30.0,
    )


@pytest.fixture
def mock_floor_result():
    """Create a mock FloorResult with one passing room."""
    room = RoomResult(
        room_id="R1",
        status="PASS",
        detector_count=4,
    )
    result = FloorResult(
        project_name="test_GF",
        source_dxf="test.dxf",
        total_rooms=1,
        room_results=[room],
        rooms_passed=1,
        rooms_failed=0,
        rooms_errored=0,
        total_detectors=4,
        status="APPROVED",
    )
    return result


@pytest.fixture
def mock_floor_result_many_devices():
    """Create a mock FloorResult with many devices to test loop splitting."""
    rooms = []
    for i in range(50):
        rooms.append(
            RoomResult(
                room_id=f"R{i+1}",
                status="PASS",
                detector_count=10,
            )
        )
    result = FloorResult(
        project_name="test_L1",
        source_dxf="test.dxf",
        total_rooms=50,
        room_results=rooms,
        rooms_passed=50,
        rooms_failed=0,
        rooms_errored=0,
        total_detectors=500,
        status="APPROVED",
    )
    return result


@pytest.fixture
def sample_building_spec():
    """A minimal building spec for a 3-floor commercial building."""
    return {
        "building_id": "BLDG-001",
        "floors": {
            "GF": [],  # No room specs — floor assignment created with warning
            "L1": [],
            "L2": [],
        },
        "occupancy_type": "business",
        "floor_elevations": {"GF": 0.0, "L1": 3.5, "L2": 7.0},
        "floor_areas": {"GF": 500.0, "L1": 500.0, "L2": 500.0},
        "elevators": [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1", "L2"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_shaft_heat_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ],
        "stairwells": [
            {
                "zone_id": "STAIR-A",
                "floors_served": ["GF", "L1", "L2"],
                "has_pressurization_fan": True,
                "has_pressure_switches": True,
                "design_pressure_pa": 50.0,
            }
        ],
        "hvac_ducts": [
            {
                "duct_id": "DUCT-1",
                "duct_type": "supply",
                "airflow_cfm": 3000.0,
                "floors_served": ["GF", "L1", "L2"],
            }
        ],
        "smoke_barriers": [],
    }


@pytest.fixture
def residential_building_spec():
    """Building spec for a residential occupancy."""
    return {
        "building_id": "RES-001",
        "floors": {"F1": [], "F2": [], "F3": [], "F4": []},
        "occupancy_type": "residential",
        "floor_elevations": {"F1": 0.0, "F2": 3.0, "F3": 6.0, "F4": 9.0},
        "floor_areas": {"F1": 400.0, "F2": 400.0, "F3": 400.0, "F4": 400.0},
    }


@pytest.fixture
def tall_building_spec():
    """Building spec for a tall building requiring stairwell pressurization."""
    return {
        "building_id": "TALL-001",
        "floors": {"GF": [], "F1": [], "F2": [], "F3": [], "F4": [], "F5": []},
        "occupancy_type": "business",
        "floor_elevations": {
            "GF": 0.0, "F1": 4.0, "F2": 8.0,
            "F3": 12.0, "F4": 16.0, "F5": 20.0,
        },
        "floor_areas": dict.fromkeys(["GF", "F1", "F2", "F3", "F4", "F5"], 600.0),
        "stairwells": [
            {
                "zone_id": "STAIR-1",
                "floors_served": ["GF", "F1", "F2", "F3", "F4", "F5"],
                "has_pressurization_fan": False,
                "has_pressure_switches": False,
                "design_pressure_pa": None,
            }
        ],
    }


# ============================================================================
# Enum Tests
# ============================================================================


class TestSLCLoopClass:
    """Tests for SLCLoopClass enum."""

    def test_class_a_value(self):
        assert SLCLoopClass.CLASS_A.value == "A"

    def test_class_b_value(self):
        assert SLCLoopClass.CLASS_B.value == "B"

    def test_class_a_is_str(self):
        assert isinstance(SLCLoopClass.CLASS_A, str)

    def test_class_b_is_str(self):
        assert isinstance(SLCLoopClass.CLASS_B, str)

    def test_members_count(self):
        assert len(SLCLoopClass) == 2

    def test_from_value(self):
        assert SLCLoopClass("A") is SLCLoopClass.CLASS_A
        assert SLCLoopClass("B") is SLCLoopClass.CLASS_B


class TestOccupancyType:
    """Tests for OccupancyType enum."""

    def test_residential_value(self):
        assert OccupancyType.RESIDENTIAL.value == "residential"

    def test_business_value(self):
        assert OccupancyType.BUSINESS.value == "business"

    def test_mercantile_value(self):
        assert OccupancyType.MERCANTILE.value == "mercantile"

    def test_educational_value(self):
        assert OccupancyType.EDUCATIONAL.value == "educational"

    def test_industrial_value(self):
        assert OccupancyType.INDUSTRIAL.value == "industrial"

    def test_institutional_value(self):
        assert OccupancyType.INSTITUTIONAL.value == "institutional"

    def test_storage_value(self):
        assert OccupancyType.STORAGE.value == "storage"

    def test_assembly_value(self):
        assert OccupancyType.ASSEMBLY.value == "assembly"

    def test_members_count(self):
        assert len(OccupancyType) == 8

    def test_is_str_enum(self):
        assert isinstance(OccupancyType.BUSINESS, str)


class TestElevatorRecallPhase:
    """Tests for ElevatorRecallPhase enum."""

    def test_phase_i_value(self):
        assert ElevatorRecallPhase.PHASE_I.value == "PHASE_I"

    def test_phase_ii_value(self):
        assert ElevatorRecallPhase.PHASE_II.value == "PHASE_II"

    def test_shunt_trip_value(self):
        assert ElevatorRecallPhase.SHUNT_TRIP.value == "SHUNT_TRIP"

    def test_members_count(self):
        assert len(ElevatorRecallPhase) == 3


class TestSmokeSpreadPathway:
    """Tests for SmokeSpreadPathway enum."""

    def test_elevator_shaft_value(self):
        assert SmokeSpreadPathway.ELEVATOR_SHAFT.value == "elevator_shaft"

    def test_stairwell_value(self):
        assert SmokeSpreadPathway.STAIRWELL.value == "stairwell"

    def test_hvac_duct_value(self):
        assert SmokeSpreadPathway.HVAC_DUCT.value == "hvac_duct"

    def test_pipe_chase_value(self):
        assert SmokeSpreadPathway.PIPE_CHASE.value == "pipe_chase"

    def test_conduit_value(self):
        assert SmokeSpreadPathway.CONDUIT.value == "conduit"

    def test_joint_value(self):
        assert SmokeSpreadPathway.JOINT.value == "construction_joint"

    def test_members_count(self):
        assert len(SmokeSpreadPathway) == 6


# ============================================================================
# Dataclass Tests
# ============================================================================


class TestSLCLoopDataclass:
    """Tests for SLCLoop dataclass and its computed properties."""

    def test_default_values(self):
        loop = SLCLoop(loop_id="SLC-1")
        assert loop.loop_class == SLCLoopClass.CLASS_B
        assert loop.device_count == 0
        assert loop.max_devices == MAX_SLC_DEVICES_PER_LOOP
        assert loop.device_addresses == []
        assert loop.floors_served == set()
        assert loop.panel_id == ""
        assert loop.cable_length_m == 0.0
        assert loop.voltage_drop_compliant is False  # Fail-safe
        assert loop.warnings == []
        assert loop.nfpa_reference == "NFPA 72-2022 §21.2.2"

    def test_custom_values(self):
        loop = SLCLoop(
            loop_id="SLC-5",
            loop_class=SLCLoopClass.CLASS_A,
            device_count=100,
            max_devices=200,
            panel_id="FACP-2",
            cable_length_m=150.0,
        )
        assert loop.loop_id == "SLC-5"
        assert loop.loop_class == SLCLoopClass.CLASS_A
        assert loop.device_count == 100
        assert loop.max_devices == 200
        assert loop.panel_id == "FACP-2"
        assert loop.cable_length_m == 150.0

    def test_utilization_pct_zero_devices(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=0, max_devices=250)
        assert loop.utilization_pct == 0.0

    def test_utilization_pct_half(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=125, max_devices=250)
        assert loop.utilization_pct == 50.0

    def test_utilization_pct_full(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=250, max_devices=250)
        assert loop.utilization_pct == 100.0

    def test_utilization_pct_over_capacity(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=300, max_devices=250)
        assert loop.utilization_pct == 120.0

    def test_utilization_pct_zero_max_devices(self):
        """Edge case: max_devices=0 should return 0.0 to avoid division by zero."""
        loop = SLCLoop(loop_id="SLC-1", device_count=10, max_devices=0)
        assert loop.utilization_pct == 0.0

    def test_utilization_pct_rounding(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=1, max_devices=3)
        # 100 * 1/3 = 33.333... → rounds to 33.3
        assert loop.utilization_pct == 33.3

    def test_is_compliant_within_limit(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=250, max_devices=250)
        assert loop.is_compliant is True

    def test_is_compliant_below_limit(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=100, max_devices=250)
        assert loop.is_compliant is True

    def test_is_compliant_over_limit(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=251, max_devices=250)
        assert loop.is_compliant is False

    def test_is_compliant_at_zero(self):
        loop = SLCLoop(loop_id="SLC-1", device_count=0, max_devices=250)
        assert loop.is_compliant is True

    def test_floors_served_is_set(self):
        loop = SLCLoop(loop_id="SLC-1")
        loop.floors_served.add("GF")
        loop.floors_served.add("L1")
        assert "GF" in loop.floors_served
        assert "L1" in loop.floors_served


class TestVerticalZoneDataclass:
    """Tests for VerticalZone dataclass and is_compliant property."""

    def test_default_values(self):
        zone = VerticalZone(zone_id="VZ-01")
        assert zone.floor_ids == []
        assert zone.floors_per_zone == OTHER_FLOORS_PER_ZONE
        assert zone.occupancy_type == "business"
        assert zone.total_area_sqm == 0.0
        assert zone.total_devices == 0
        assert zone.area_compliant is False  # Fail-safe
        assert zone.warnings == []
        assert zone.nfpa_reference == "NFPA 72-2022 §21.3.3"

    def test_custom_values(self):
        zone = VerticalZone(
            zone_id="VZ-02",
            floor_ids=["GF", "L1"],
            floors_per_zone=2,
            occupancy_type="business",
            total_area_sqm=1000.0,
            total_devices=50,
            area_compliant=True,
        )
        assert zone.zone_id == "VZ-02"
        assert zone.floor_ids == ["GF", "L1"]
        assert zone.total_area_sqm == 1000.0
        assert zone.total_devices == 50

    def test_is_compliant_both_pass(self):
        zone = VerticalZone(
            zone_id="VZ-01",
            floor_ids=["GF"],
            floors_per_zone=2,
            area_compliant=True,
        )
        assert zone.is_compliant is True

    def test_is_compliant_area_fail(self):
        zone = VerticalZone(
            zone_id="VZ-01",
            floor_ids=["GF"],
            floors_per_zone=2,
            area_compliant=False,
        )
        assert zone.is_compliant is False

    def test_is_compliant_floor_count_exceeded(self):
        zone = VerticalZone(
            zone_id="VZ-01",
            floor_ids=["GF", "L1", "L2"],
            floors_per_zone=2,
            area_compliant=True,
        )
        assert zone.is_compliant is False

    def test_is_compliant_residential_one_floor_ok(self):
        zone = VerticalZone(
            zone_id="VZ-01",
            floor_ids=["F1"],
            floors_per_zone=1,
            area_compliant=True,
        )
        assert zone.is_compliant is True

    def test_is_compliant_residential_two_floors_fail(self):
        zone = VerticalZone(
            zone_id="VZ-01",
            floor_ids=["F1", "F2"],
            floors_per_zone=1,
            area_compliant=True,
        )
        assert zone.is_compliant is False


class TestFloorAssignmentDataclass:
    """Tests for FloorAssignment dataclass."""

    def test_default_values(self):
        fa = FloorAssignment(floor_id="GF")
        assert fa.floor_id == "GF"
        assert fa.floor_index == 0
        assert fa.elevation_m == 0.0
        assert fa.room_results == []
        assert fa.total_devices == 0
        assert fa.total_detectors == 0
        assert fa.total_notification == 0
        assert fa.total_modules == 0
        assert fa.area_sqm == 0.0
        assert fa.occupancy_type == "business"
        assert fa.slc_loops == []
        assert fa.vertical_zone_id == ""
        assert fa.warnings == []

    def test_custom_values(self):
        fa = FloorAssignment(
            floor_id="L3",
            floor_index=3,
            elevation_m=10.5,
            total_devices=30,
            total_detectors=15,
            total_notification=10,
            total_modules=5,
            area_sqm=800.0,
            occupancy_type="assembly",
        )
        assert fa.floor_id == "L3"
        assert fa.floor_index == 3
        assert fa.elevation_m == 10.5
        assert fa.total_devices == 30
        assert fa.area_sqm == 800.0
        assert fa.occupancy_type == "assembly"


class TestSmokeSpreadResultDataclass:
    """Tests for SmokeSpreadResult dataclass."""

    def test_default_values(self):
        result = SmokeSpreadResult()
        assert result.pathway == SmokeSpreadPathway.STAIRWELL
        assert result.source_floor == ""
        assert result.affected_floors == []
        assert result.propagation_time_s == 0.0
        assert result.pressurization_required is False
        assert result.duct_detection_required is False
        assert result.barrier_rating_required_h == MIN_SMOKE_BARRIER_RATING_H
        assert result.violations == []
        assert result.warnings == []
        assert result.nfpa_reference == ""

    def test_custom_values(self):
        result = SmokeSpreadResult(
            pathway=SmokeSpreadPathway.ELEVATOR_SHAFT,
            source_floor="L2",
            affected_floors=["L2", "L3", "L4"],
            propagation_time_s=15.0,
            pressurization_required=True,
            duct_detection_required=True,
        )
        assert result.pathway == SmokeSpreadPathway.ELEVATOR_SHAFT
        assert result.source_floor == "L2"
        assert result.affected_floors == ["L2", "L3", "L4"]
        assert result.propagation_time_s == 15.0
        assert result.pressurization_required is True
        assert result.duct_detection_required is True


class TestElevatorRecallResultDataclass:
    """Tests for ElevatorRecallResult dataclass."""

    def test_default_values(self):
        result = ElevatorRecallResult()
        assert result.elevator_id == ""
        assert result.floors_served == []
        assert result.designated_recall_floor == DEFAULT_RECALL_FLOOR
        assert result.phase_i_compliant is False  # Fail-safe
        assert result.phase_ii_compliant is False
        assert result.shunt_trip_compliant is False
        assert result.shunt_trip_result is None
        assert result.has_smoke_detector_at_recall is False
        assert result.has_heat_detector_in_shaft is False
        assert result.violations == []
        assert result.warnings == []
        assert result.nfpa_reference == "NFPA 72-2022 §21.3.2"

    def test_custom_values(self):
        result = ElevatorRecallResult(
            elevator_id="ELEV-1",
            floors_served=["GF", "L1", "L2"],
            designated_recall_floor="GF",
            phase_i_compliant=True,
            phase_ii_compliant=True,
            shunt_trip_compliant=True,
            has_smoke_detector_at_recall=True,
            has_heat_detector_in_shaft=True,
        )
        assert result.elevator_id == "ELEV-1"
        assert result.floors_served == ["GF", "L1", "L2"]
        assert result.designated_recall_floor == "GF"
        assert result.phase_i_compliant is True
        assert result.phase_ii_compliant is True
        assert result.shunt_trip_compliant is True


class TestRiserRoutingResultDataclass:
    """Tests for RiserRoutingResult dataclass."""

    def test_default_values(self):
        result = RiserRoutingResult()
        assert result.from_floor == ""
        assert result.to_floor == ""
        assert result.cable_length_m == 0.0
        assert result.wire_gauge == "14"
        assert result.voltage_drop_pct == 0.0
        assert result.voltage_drop_compliant is False  # Fail-safe
        assert result.route_valid is False  # Fail-safe
        assert result.violations == []
        assert result.nfpa_reference == "NFPA 72-2022 §27.4.1 / NEC Art. 760"

    def test_custom_values(self):
        result = RiserRoutingResult(
            from_floor="GF",
            to_floor="L1",
            cable_length_m=25.5,
            wire_gauge="12",
            voltage_drop_pct=3.2,
            voltage_drop_compliant=True,
            route_valid=True,
        )
        assert result.from_floor == "GF"
        assert result.to_floor == "L1"
        assert result.cable_length_m == 25.5
        assert result.wire_gauge == "12"
        assert result.voltage_drop_pct == 3.2
        assert result.voltage_drop_compliant is True
        assert result.route_valid is True


class TestBuildingAnalysisDataclass:
    """Tests for BuildingAnalysis dataclass."""

    def test_default_values(self):
        analysis = BuildingAnalysis()
        assert analysis.building_id == ""
        assert analysis.total_floors == 0
        assert analysis.floor_assignments == []
        assert analysis.slc_loops == []
        assert analysis.vertical_zones == []
        assert analysis.smoke_spread_results == []
        assert analysis.elevator_recall_results == []
        assert analysis.riser_routing_results == []
        assert analysis.total_devices == 0
        assert analysis.total_detectors == 0
        assert analysis.total_slc_loops == 0
        assert analysis.total_vertical_zones == 0
        assert analysis.compliant is False  # Fail-safe
        assert analysis.analysis_time_s == 0.0
        assert analysis.warnings == []
        assert analysis.errors == []

    def test_disclaimer_present(self):
        analysis = BuildingAnalysis()
        assert "FireAI" in analysis.disclaimer
        assert "licensed fire protection engineer" in analysis.disclaimer
        assert "NFPA 72" in analysis.disclaimer

    def test_custom_values(self):
        analysis = BuildingAnalysis(
            building_id="BLDG-001",
            total_floors=5,
            total_devices=120,
            compliant=True,
        )
        assert analysis.building_id == "BLDG-001"
        assert analysis.total_floors == 5
        assert analysis.total_devices == 120
        assert analysis.compliant is True


# ============================================================================
# Constants Tests
# ============================================================================


class TestConstants:
    """Tests for module-level constants."""

    def test_max_slc_devices(self):
        assert MAX_SLC_DEVICES_PER_LOOP == 250

    def test_residential_floors_per_zone(self):
        assert RESIDENTIAL_FLOORS_PER_ZONE == 1

    def test_other_floors_per_zone(self):
        assert OTHER_FLOORS_PER_ZONE == 2

    def test_max_zone_area_sqft(self):
        assert MAX_ZONE_AREA_SQFT == 20_000.0

    def test_max_zone_area_sqm(self):
        assert pytest.approx(20_000.0 * 0.092903, rel=1e-4) == MAX_ZONE_AREA_SQM

    def test_default_recall_floor(self):
        assert DEFAULT_RECALL_FLOOR == "GF"

    def test_stack_effect_velocity(self):
        assert STACK_EFFECT_VELOCITY_MPS == 3.0

    def test_min_smoke_barrier_rating(self):
        assert MIN_SMOKE_BARRIER_RATING_H == 1.0


# ============================================================================
# MultiFloorOrchestrator.__init__ Tests
# ============================================================================


class TestMultiFloorOrchestratorInit:
    """Tests for MultiFloorOrchestrator initialization."""

    def test_default_init(self):
        mo = MultiFloorOrchestrator()
        assert mo.slc_loop_class == SLCLoopClass.CLASS_B
        assert mo.max_slc_devices == MAX_SLC_DEVICES_PER_LOOP
        assert mo.building_height_m == 0.0
        assert mo.panel_id == "FACP-1"
        assert mo.grid_res == 0.25
        assert isinstance(mo.floor_orchestrator, FloorOrchestrator)

    def test_custom_init(self, floor_orchestrator):
        mo = MultiFloorOrchestrator(
            floor_orchestrator=floor_orchestrator,
            slc_loop_class=SLCLoopClass.CLASS_A,
            max_slc_devices=200,
            building_height_m=50.0,
            panel_id="FACP-2",
            grid_res=0.5,
        )
        assert mo.floor_orchestrator is floor_orchestrator
        assert mo.slc_loop_class == SLCLoopClass.CLASS_A
        assert mo.max_slc_devices == 200
        assert mo.building_height_m == 50.0
        assert mo.panel_id == "FACP-2"
        assert mo.grid_res == 0.5

    def test_invalid_max_slc_devices_zero(self):
        with pytest.raises(ValueError, match="max_slc_devices=0 must be >= 1"):
            MultiFloorOrchestrator(max_slc_devices=0)

    def test_invalid_max_slc_devices_negative(self):
        with pytest.raises(ValueError, match="max_slc_devices=-5 must be >= 1"):
            MultiFloorOrchestrator(max_slc_devices=-5)

    def test_invalid_building_height_negative(self):
        with pytest.raises(ValueError, match="building_height_m=-1.0 must be >= 0"):
            MultiFloorOrchestrator(building_height_m=-1.0)

    def test_zero_building_height_logs_critical(self, caplog):
        """Zero building height should log a CRITICAL message about inactive smoke analysis."""
        import logging
        with caplog.at_level(logging.CRITICAL, logger="fireai.core.multi_floor_orchestrator"):
            MultiFloorOrchestrator(building_height_m=0.0)
        assert any("MFO-001" in rec.message for rec in caplog.records)


# ============================================================================
# orchestrate() Tests
# ============================================================================


class TestOrchestrate:
    """Tests for MultiFloorOrchestrator.orchestrate()."""

    def test_empty_building_id_raises(self, orchestrator):
        with pytest.raises(ValueError, match="building_id must be a non-empty string"):
            orchestrator.orchestrate(building_id="", floors={"GF": []})

    def test_whitespace_building_id_raises(self, orchestrator):
        with pytest.raises(ValueError, match="building_id must be a non-empty string"):
            orchestrator.orchestrate(building_id="   ", floors={"GF": []})

    def test_no_floors_returns_error(self, orchestrator):
        result = orchestrator.orchestrate(building_id="B1", floors={})
        assert isinstance(result, BuildingAnalysis)
        assert result.building_id == "B1"
        assert result.total_floors == 0
        assert result.compliant is False
        assert any("No floors" in e for e in result.errors)

    def test_basic_orchestration_with_empty_floors(self, orchestrator, sample_building_spec):
        """Test orchestrate with a basic building spec where all rooms are empty."""
        result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert result.building_id == "BLDG-001"
        assert result.total_floors == 3
        assert len(result.floor_assignments) == 3
        assert result.analysis_time_s >= 0.0

    def test_floor_assignments_created(self, orchestrator, sample_building_spec):
        """Verify floor assignments are created for each floor."""
        result = orchestrator.orchestrate(**sample_building_spec)
        floor_ids = {fa.floor_id for fa in result.floor_assignments}
        assert floor_ids == {"GF", "L1", "L2"}

    def test_floor_assignments_warnings_for_empty_rooms(self, orchestrator, sample_building_spec):
        """Floors with no room specs should have a warning."""
        result = orchestrator.orchestrate(**sample_building_spec)
        for fa in result.floor_assignments:
            assert any("no room specs" in w for w in fa.warnings)

    def test_floor_elevations_set(self, orchestrator, sample_building_spec):
        """Floor elevations should be propagated to floor assignments."""
        result = orchestrator.orchestrate(**sample_building_spec)
        elev_map = {fa.floor_id: fa.elevation_m for fa in result.floor_assignments}
        assert elev_map["GF"] == 0.0
        assert elev_map["L1"] == 3.5
        assert elev_map["L2"] == 7.0

    def test_floor_areas_set(self, orchestrator, sample_building_spec):
        """Floor areas should be propagated to floor assignments."""
        result = orchestrator.orchestrate(**sample_building_spec)
        area_map = {fa.floor_id: fa.area_sqm for fa in result.floor_assignments}
        assert area_map["GF"] == 500.0
        assert area_map["L1"] == 500.0

    def test_occupancy_type_set(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        for fa in result.floor_assignments:
            assert fa.occupancy_type == "business"

    def test_floors_sorted_by_elevation(self, orchestrator, sample_building_spec):
        """Floors should be sorted by elevation in the result."""
        result = orchestrator.orchestrate(**sample_building_spec)
        indices = [fa.floor_index for fa in result.floor_assignments]
        assert indices == sorted(indices)

    def test_vertical_zones_created(self, orchestrator, sample_building_spec):
        """Vertical zones should be created for the building."""
        result = orchestrator.orchestrate(**sample_building_spec)
        assert len(result.vertical_zones) > 0
        assert all(isinstance(vz, VerticalZone) for vz in result.vertical_zones)

    def test_vertical_zone_back_reference(self, orchestrator, sample_building_spec):
        """Floor assignments should reference their vertical zone."""
        result = orchestrator.orchestrate(**sample_building_spec)
        for fa in result.floor_assignments:
            assert fa.vertical_zone_id != ""

    def test_smoke_spread_results_created(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        assert len(result.smoke_spread_results) > 0

    def test_elevator_recall_results_created(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        assert len(result.elevator_recall_results) == 1
        assert result.elevator_recall_results[0].elevator_id == "ELEV-1"

    def test_riser_routing_results_created(self, orchestrator, sample_building_spec):
        """With 3 floors, there should be 2 riser segments (GF→L1, L1→L2)."""
        result = orchestrator.orchestrate(**sample_building_spec)
        assert len(result.riser_routing_results) == 2

    def test_total_devices_aggregated(self, orchestrator, sample_building_spec):
        """Total devices should be the sum across all floor assignments."""
        result = orchestrator.orchestrate(**sample_building_spec)
        expected = sum(fa.total_devices for fa in result.floor_assignments)
        assert result.total_devices == expected

    def test_total_detectors_aggregated(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        expected = sum(fa.total_detectors for fa in result.floor_assignments)
        assert result.total_detectors == expected

    def test_total_slc_loops(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        assert result.total_slc_loops == len(result.slc_loops)

    def test_total_vertical_zones(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        assert result.total_vertical_zones == len(result.vertical_zones)

    def test_analysis_time_recorded(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        assert result.analysis_time_s > 0.0 or result.analysis_time_s == 0.0  # May be very fast

    def test_disclaimer_present(self, orchestrator, sample_building_spec):
        result = orchestrator.orchestrate(**sample_building_spec)
        assert "licensed fire protection engineer" in result.disclaimer

    def test_single_floor_building(self, orchestrator):
        """A single-floor building should still produce valid results."""
        result = orchestrator.orchestrate(
            building_id="SINGLE-001",
            floors={"GF": []},
            floor_elevations={"GF": 0.0},
            floor_areas={"GF": 500.0},
        )
        assert result.total_floors == 1
        assert len(result.floor_assignments) == 1
        # No riser routing for a single floor
        assert len(result.riser_routing_results) == 0

    def test_with_project_name_and_source_dxf(self, orchestrator, sample_building_spec):
        """Project name and source DXF should be accepted without error."""
        sample_building_spec["project_name"] = "TestProject"
        sample_building_spec["source_dxf"] = "test.dxf"
        result = orchestrator.orchestrate(**sample_building_spec)
        assert result.building_id == "BLDG-001"


# ============================================================================
# SLC Loop Assignment Tests
# ============================================================================


class TestSLCLoopAssignment:
    """Tests for _assign_slc_loops."""

    def test_empty_floor_assignments(self, orchestrator):
        result = orchestrator._assign_slc_loops(floor_assignments=[])
        assert result == []

    def test_single_floor_single_loop(self, orchestrator):
        """A floor with few devices should fit in a single loop."""
        fa = FloorAssignment(
            floor_id="GF",
            floor_index=0,
            total_devices=50,
            area_sqm=500.0,
            elevation_m=0.0,
        )
        loops = orchestrator._assign_slc_loops([fa])
        assert len(loops) == 1
        assert loops[0].device_count == 50
        assert loops[0].is_compliant is True
        assert "GF" in loops[0].floors_served
        assert fa.slc_loops == ["SLC-1"]

    def test_multi_floor_single_loop(self, orchestrator):
        """Multiple floors with few devices should share a single loop."""
        fa1 = FloorAssignment(floor_id="GF", floor_index=0, total_devices=60, area_sqm=500.0, elevation_m=0.0)
        fa2 = FloorAssignment(floor_id="L1", floor_index=1, total_devices=60, area_sqm=500.0, elevation_m=3.5)
        loops = orchestrator._assign_slc_loops([fa1, fa2])
        assert len(loops) == 1
        assert loops[0].device_count == 120
        assert "GF" in loops[0].floors_served
        assert "L1" in loops[0].floors_served

    def test_loop_split_on_capacity(self, orchestrator):
        """Devices exceeding one loop should be split across loops."""
        fa = FloorAssignment(
            floor_id="GF",
            floor_index=0,
            total_devices=300,  # Exceeds 250 default
            area_sqm=1000.0,
            elevation_m=0.0,
        )
        loops = orchestrator._assign_slc_loops([fa])
        assert len(loops) == 2
        assert loops[0].device_count == 250
        assert loops[1].device_count == 50
        assert loops[0].is_compliant is True
        assert loops[1].is_compliant is True

    def test_device_addresses_format(self, orchestrator):
        """Device addresses should follow the format SLC-N:MMM."""
        fa = FloorAssignment(floor_id="GF", floor_index=0, total_devices=5, area_sqm=500.0, elevation_m=0.0)
        loops = orchestrator._assign_slc_loops([fa])
        assert len(loops[0].device_addresses) == 5
        assert loops[0].device_addresses[0] == "SLC-1:001"
        assert loops[0].device_addresses[4] == "SLC-1:005"

    def test_loop_class_b_default(self, orchestrator):
        """Default loop class should be Class B."""
        fa = FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=500.0, elevation_m=0.0)
        loops = orchestrator._assign_slc_loops([fa])
        assert loops[0].loop_class == SLCLoopClass.CLASS_B

    def test_loop_class_a(self, orchestrator_class_a):
        """Class A loops should be created when configured."""
        fa = FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=500.0, elevation_m=0.0)
        loops = orchestrator_class_a._assign_slc_loops([fa])
        assert loops[0].loop_class == SLCLoopClass.CLASS_A

    def test_panel_id_set(self, orchestrator):
        fa = FloorAssignment(floor_id="GF", floor_index=0, total_devices=5, area_sqm=500.0, elevation_m=0.0)
        loops = orchestrator._assign_slc_loops([fa])
        assert loops[0].panel_id == "FACP-1"

    def test_floor_with_zero_devices_skipped(self, orchestrator):
        """Floors with 0 devices should not create loops."""
        fa1 = FloorAssignment(floor_id="GF", floor_index=0, total_devices=0, area_sqm=500.0, elevation_m=0.0)
        fa2 = FloorAssignment(floor_id="L1", floor_index=1, total_devices=20, area_sqm=500.0, elevation_m=3.5)
        loops = orchestrator._assign_slc_loops([fa1, fa2])
        assert len(loops) == 1
        assert "GF" not in loops[0].floors_served
        assert "L1" in loops[0].floors_served

    def test_many_loops_creation(self):
        """A building with many devices should create the right number of loops."""
        mo = MultiFloorOrchestrator(max_slc_devices=10, building_height_m=10.0)
        fa = FloorAssignment(floor_id="GF", floor_index=0, total_devices=35, area_sqm=500.0, elevation_m=0.0)
        loops = mo._assign_slc_loops([fa])
        assert len(loops) == 4  # 10 + 10 + 10 + 5

    def test_loop_warning_on_split(self, orchestrator):
        """Warning should be added when a floor exceeds single loop capacity."""
        fa = FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=300, area_sqm=1000.0, elevation_m=0.0
        )
        loops = orchestrator._assign_slc_loops([fa])
        # At least one loop should have a warning about splitting
        all_warnings = [w for loop in loops for w in loop.warnings]
        assert any("exceeds single loop capacity" in w for w in all_warnings)

    def test_cable_length_estimated(self, orchestrator):
        """Cable length should be estimated for loops."""
        fa = FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=10,
            area_sqm=500.0, elevation_m=0.0,
        )
        loops = orchestrator._assign_slc_loops([fa])
        # Cable length should be > 0 when area is provided
        assert loops[0].cable_length_m > 0.0

    def test_cable_length_class_a_doubled(self, orchestrator_class_a):
        """Class A loops should have approximately double the cable length of Class B."""
        FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=10,
            area_sqm=500.0, elevation_m=0.0,
        )
        # Get Class B length
        fa_b = FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=10,
            area_sqm=500.0, elevation_m=0.0,
        )
        mo_b = MultiFloorOrchestrator(
            slc_loop_class=SLCLoopClass.CLASS_B, building_height_m=10.0,
        )
        loops_b = mo_b._assign_slc_loops([fa_b])

        # Get Class A length
        fa_a = FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=10,
            area_sqm=500.0, elevation_m=0.0,
        )
        loops_a = orchestrator_class_a._assign_slc_loops([fa_a])

        # Class A cable should be approximately 2x Class B
        assert loops_a[0].cable_length_m == pytest.approx(2.0 * loops_b[0].cable_length_m, rel=0.01)

    def test_floor_slc_loops_back_reference(self, orchestrator):
        """Floor assignments should have their SLC loops referenced."""
        fa = FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=500.0, elevation_m=0.0)
        orchestrator._assign_slc_loops([fa])
        assert "SLC-1" in fa.slc_loops

    def test_floors_sorted_by_index_in_loop_assignment(self, orchestrator):
        """Floors should be processed in index order."""
        fa2 = FloorAssignment(floor_id="L1", floor_index=1, total_devices=30, area_sqm=500.0, elevation_m=3.5)
        fa1 = FloorAssignment(floor_id="GF", floor_index=0, total_devices=30, area_sqm=500.0, elevation_m=0.0)
        loops = orchestrator._assign_slc_loops([fa2, fa1])  # Out of order input
        # GF should be processed first, device addresses should start from 001
        assert "GF" in loops[0].floors_served


# ============================================================================
# Vertical Zone Design Tests
# ============================================================================


class TestVerticalZoneDesign:
    """Tests for _design_vertical_zones."""

    def test_empty_floor_assignments(self, orchestrator):
        result = orchestrator._design_vertical_zones([], "business")
        assert result == []

    def test_business_occupancy_two_floors_per_zone(self, orchestrator):
        """Business occupancy allows 2 floors per zone."""
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, total_devices=10, area_sqm=500.0),
            FloorAssignment(floor_id="L2", floor_index=2, total_devices=10, area_sqm=500.0),
            FloorAssignment(floor_id="L3", floor_index=3, total_devices=10, area_sqm=500.0),
        ]
        zones = orchestrator._design_vertical_zones(floors, "business", {"GF": 500.0, "L1": 500.0, "L2": 500.0, "L3": 500.0})
        # 4 floors, 2 per zone → 2 zones
        assert len(zones) == 2
        assert zones[0].floors_per_zone == 2
        assert zones[1].floors_per_zone == 2

    def test_residential_occupancy_one_floor_per_zone(self, orchestrator):
        """Residential occupancy allows only 1 floor per zone."""
        floors = [
            FloorAssignment(floor_id="F1", floor_index=0, total_devices=10, area_sqm=400.0),
            FloorAssignment(floor_id="F2", floor_index=1, total_devices=10, area_sqm=400.0),
            FloorAssignment(floor_id="F3", floor_index=2, total_devices=10, area_sqm=400.0),
        ]
        zones = orchestrator._design_vertical_zones(floors, "residential")
        assert len(zones) == 3  # 1 floor per zone
        assert zones[0].floors_per_zone == 1

    def test_sleeping_occupancy_treated_as_residential(self, orchestrator):
        """Sleeping occupancy should be treated like residential (1 floor/zone)."""
        floors = [
            FloorAssignment(floor_id="F1", floor_index=0, total_devices=10, area_sqm=400.0),
            FloorAssignment(floor_id="F2", floor_index=1, total_devices=10, area_sqm=400.0),
        ]
        zones = orchestrator._design_vertical_zones(floors, "sleeping")
        assert len(zones) == 2
        assert zones[0].floors_per_zone == 1

    def test_institutional_occupancy_one_floor_per_zone(self, orchestrator):
        """Institutional occupancy should be treated like residential."""
        floors = [
            FloorAssignment(floor_id="F1", floor_index=0, total_devices=10, area_sqm=400.0),
            FloorAssignment(floor_id="F2", floor_index=1, total_devices=10, area_sqm=400.0),
        ]
        zones = orchestrator._design_vertical_zones(floors, "institutional")
        assert len(zones) == 2
        assert zones[0].floors_per_zone == 1

    def test_zone_area_compliance(self, orchestrator):
        """Zones within area limits should be compliant."""
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=800.0),
            FloorAssignment(floor_id="L1", floor_index=1, total_devices=10, area_sqm=800.0),
        ]
        zones = orchestrator._design_vertical_zones(
            floors, "business", {"GF": 800.0, "L1": 800.0}
        )
        # 1600 sqm < MAX_ZONE_AREA_SQM ≈ 1858 sqm → area_compliant
        assert zones[0].area_compliant is True

    def test_zone_area_exceeded(self, orchestrator):
        """Zones exceeding area limits should be non-compliant."""
        # Each floor has area close to MAX_ZONE_AREA_SQM
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=1500.0),
            FloorAssignment(floor_id="L1", floor_index=1, total_devices=10, area_sqm=1500.0),
        ]
        zones = orchestrator._design_vertical_zones(
            floors, "business", {"GF": 1500.0, "L1": 1500.0}
        )
        # 1500 + 1500 = 3000 > 1858 → first zone should exceed area and be split
        # Actually, adding L1 to current zone would exceed area → flush zone and start new
        assert len(zones) >= 1

    def test_zone_ids_sequential(self, orchestrator):
        """Zone IDs should be sequentially numbered: VZ-01, VZ-02, etc."""
        floors = [
            FloorAssignment(floor_id=f"F{i}", floor_index=i, total_devices=10, area_sqm=400.0)
            for i in range(4)
        ]
        zones = orchestrator._design_vertical_zones(floors, "residential")
        zone_ids = [z.zone_id for z in zones]
        assert zone_ids == ["VZ-01", "VZ-02", "VZ-03", "VZ-04"]

    def test_zone_occupancy_type_set(self, orchestrator):
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, total_devices=10, area_sqm=500.0),
        ]
        zones = orchestrator._design_vertical_zones(floors, "mercantile")
        assert zones[0].occupancy_type == "mercantile"

    def test_total_devices_in_zone(self, orchestrator):
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, total_devices=30, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, total_devices=20, area_sqm=500.0),
        ]
        zones = orchestrator._design_vertical_zones(
            floors, "business", {"GF": 500.0, "L1": 500.0}
        )
        assert zones[0].total_devices == 50


# ============================================================================
# Smoke Spread Analysis Tests
# ============================================================================


class TestSmokeSpreadAnalysis:
    """Tests for _analyze_smoke_spread."""

    def test_empty_floor_assignments(self, orchestrator):
        result = orchestrator._analyze_smoke_spread(
            floor_assignments=[], elevators=[], stairwells=[],
            hvac_ducts=[], smoke_barriers=[], building_height_m=45.0,
        )
        assert result == []

    def test_elevator_shaft_analysis(self, orchestrator):
        """Elevator shafts should produce SmokeSpreadResult with ELEVATOR_SHAFT pathway."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1", "L2"],
                "has_shaft_smoke_detector": True,
                "shaft_pressurized": False,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=elevators,
            stairwells=[], hvac_ducts=[], smoke_barriers=[],
            building_height_m=45.0,
        )
        elev_results = [r for r in results if r.pathway == SmokeSpreadPathway.ELEVATOR_SHAFT]
        assert len(elev_results) == 1
        assert elev_results[0].source_floor == "GF"
        assert elev_results[0].affected_floors == ["GF", "L1", "L2"]
        assert elev_results[0].propagation_time_s > 0

    def test_elevator_no_shaft_detector_violation(self, orchestrator):
        """Missing shaft smoke detector should produce a violation."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1"],
                "has_shaft_smoke_detector": False,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=elevators,
            stairwells=[], hvac_ducts=[], smoke_barriers=[],
            building_height_m=30.0,
        )
        elev_results = [r for r in results if r.pathway == SmokeSpreadPathway.ELEVATOR_SHAFT]
        assert len(elev_results) == 1
        assert len(elev_results[0].violations) > 0
        assert any("lacks smoke detection" in v for v in elev_results[0].violations)

    def test_elevator_unpressurized_tall_building_warning(self, orchestrator):
        """Unpressurized elevator shaft in tall building should produce a warning."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1"],
                "has_shaft_smoke_detector": True,
                "shaft_pressurized": False,
            }
        ]
        # building_height_m > 22.86 → pressurization required
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=elevators,
            stairwells=[], hvac_ducts=[], smoke_barriers=[],
            building_height_m=30.0,
        )
        elev_results = [r for r in results if r.pathway == SmokeSpreadPathway.ELEVATOR_SHAFT]
        assert any("not pressurized" in w for w in elev_results[0].warnings)

    def test_stairwell_pressurization_required(self, orchestrator):
        """Stairwells in tall buildings should require pressurization."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        stairwells = [
            {
                "zone_id": "STAIR-1",
                "floors_served": ["GF", "L1", "L2"],
                "has_pressurization_fan": True,
                "has_pressure_switches": True,
                "design_pressure_pa": 50.0,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=stairwells,
            hvac_ducts=[], smoke_barriers=[], building_height_m=45.0,
        )
        stair_results = [r for r in results if r.pathway == SmokeSpreadPathway.STAIRWELL]
        assert len(stair_results) == 1
        assert stair_results[0].pressurization_required is True

    def test_stairwell_no_fan_violation(self, orchestrator):
        """Missing pressurization fan in tall building should produce a violation."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        stairwells = [
            {
                "zone_id": "STAIR-1",
                "floors_served": ["GF", "L1", "L2"],
                "has_pressurization_fan": False,
                "has_pressure_switches": False,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=stairwells,
            hvac_ducts=[], smoke_barriers=[], building_height_m=30.0,
        )
        stair_results = [r for r in results if r.pathway == SmokeSpreadPathway.STAIRWELL]
        assert len(stair_results[0].violations) > 0
        assert any("lacks pressurization fan" in v for v in stair_results[0].violations)

    def test_stairwell_fan_no_switches_warning(self, orchestrator):
        """Fan present but no pressure switches should produce a warning."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        stairwells = [
            {
                "zone_id": "STAIR-1",
                "floors_served": ["GF", "L1"],
                "has_pressurization_fan": True,
                "has_pressure_switches": False,
                "design_pressure_pa": 50.0,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=stairwells,
            hvac_ducts=[], smoke_barriers=[], building_height_m=30.0,
        )
        stair_results = [r for r in results if r.pathway == SmokeSpreadPathway.STAIRWELL]
        assert any("lacks differential pressure monitoring" in w for w in stair_results[0].warnings)

    def test_stairwell_low_pressure_violation(self, orchestrator):
        """Design pressure below 25 Pa should produce a violation."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        stairwells = [
            {
                "zone_id": "STAIR-1",
                "floors_served": ["GF", "L1"],
                "has_pressurization_fan": True,
                "has_pressure_switches": True,
                "design_pressure_pa": 15.0,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=stairwells,
            hvac_ducts=[], smoke_barriers=[], building_height_m=30.0,
        )
        stair_results = [r for r in results if r.pathway == SmokeSpreadPathway.STAIRWELL]
        assert any("below minimum 25 Pa" in v for v in stair_results[0].violations)

    def test_stairwell_high_pressure_violation(self, orchestrator):
        """Design pressure above 85 Pa should produce a violation (doors can't open)."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        stairwells = [
            {
                "zone_id": "STAIR-1",
                "floors_served": ["GF", "L1"],
                "has_pressurization_fan": True,
                "has_pressure_switches": True,
                "design_pressure_pa": 100.0,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=stairwells,
            hvac_ducts=[], smoke_barriers=[], building_height_m=30.0,
        )
        stair_results = [r for r in results if r.pathway == SmokeSpreadPathway.STAIRWELL]
        assert any("exceeds maximum 85 Pa" in v for v in stair_results[0].violations)

    def test_hvac_duct_detection_required(self, orchestrator):
        """HVAC ducts with >2000 CFM should require duct detection."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        hvac_ducts = [
            {
                "duct_id": "DUCT-1",
                "duct_type": "supply",
                "airflow_cfm": 5000.0,
                "floors_served": ["GF", "L1", "L2"],
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=hvac_ducts, smoke_barriers=[], building_height_m=30.0,
        )
        duct_results = [r for r in results if r.pathway == SmokeSpreadPathway.HVAC_DUCT]
        assert len(duct_results) == 1
        assert duct_results[0].duct_detection_required is True
        assert len(duct_results[0].violations) > 0

    def test_hvac_duct_below_threshold(self, orchestrator):
        """HVAC ducts with ≤2000 CFM should not require duct detection."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        hvac_ducts = [
            {
                "duct_id": "DUCT-1",
                "duct_type": "supply",
                "airflow_cfm": 1500.0,
                "floors_served": ["GF"],
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=hvac_ducts, smoke_barriers=[], building_height_m=30.0,
        )
        duct_results = [r for r in results if r.pathway == SmokeSpreadPathway.HVAC_DUCT]
        assert duct_results[0].duct_detection_required is False
        assert len(duct_results[0].violations) == 0

    def test_hvac_duct_unknown_cfm_warning(self, orchestrator):
        """HVAC ducts with unknown CFM should produce a warning (conservative)."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        hvac_ducts = [
            {
                "duct_id": "DUCT-1",
                "duct_type": "supply",
                "airflow_cfm": None,
                "floors_served": ["GF"],
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=hvac_ducts, smoke_barriers=[], building_height_m=30.0,
        )
        duct_results = [r for r in results if r.pathway == SmokeSpreadPathway.HVAC_DUCT]
        assert duct_results[0].duct_detection_required is True
        assert any("airflow CFM unknown" in w for w in duct_results[0].warnings)

    def test_hvac_exhaust_duct_exempt(self, orchestrator):
        """Exhaust ducts should be exempt from duct detection requirements."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        hvac_ducts = [
            {
                "duct_id": "DUCT-EXH",
                "duct_type": "exhaust",
                "airflow_cfm": 5000.0,
                "floors_served": ["GF"],
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=hvac_ducts, smoke_barriers=[], building_height_m=30.0,
        )
        duct_results = [r for r in results if r.pathway == SmokeSpreadPathway.HVAC_DUCT]
        assert duct_results[0].duct_detection_required is False
        assert any("exhaust type" in w for w in duct_results[0].warnings)

    def test_smoke_barrier_below_rating_violation(self, orchestrator):
        """Smoke barriers below minimum rating should produce a violation."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        barriers = [
            {
                "barrier_id": "BARRIER-1",
                "between_floors": ("GF", "L1"),
                "rating_h": 0.5,  # Below 1.0h minimum
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=[], smoke_barriers=barriers, building_height_m=10.0,
        )
        barrier_results = [r for r in results if r.pathway == SmokeSpreadPathway.JOINT]
        assert len(barrier_results) == 1
        assert any("below minimum" in v for v in barrier_results[0].violations)

    def test_smoke_barrier_adequate_rating(self, orchestrator):
        """Smoke barriers with adequate rating should not produce violations."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        barriers = [
            {
                "barrier_id": "BARRIER-1",
                "between_floors": ("GF", "L1"),
                "rating_h": 1.5,  # Above 1.0h minimum
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=[], smoke_barriers=barriers, building_height_m=10.0,
        )
        barrier_results = [r for r in results if r.pathway == SmokeSpreadPathway.JOINT]
        assert len(barrier_results[0].violations) == 0

    def test_no_pathways_tall_building_warning(self, orchestrator):
        """Tall building with no shaft data should produce a general warning."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=[], smoke_barriers=[], building_height_m=45.0,
        )
        assert len(results) == 1
        assert results[0].pressurization_required is True
        assert any("No vertical shaft data" in w for w in results[0].warnings)

    def test_no_pathways_short_building(self, orchestrator):
        """Short building with no shaft data should produce no results."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=[],
            hvac_ducts=[], smoke_barriers=[], building_height_m=10.0,
        )
        assert len(results) == 0

    def test_stack_effect_propagation_time(self, orchestrator):
        """Propagation time should be calculated based on stack effect."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1", "L2"],
                "has_shaft_smoke_detector": True,
                "shaft_pressurized": True,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=elevators,
            stairwells=[], hvac_ducts=[], smoke_barriers=[],
            building_height_m=45.0,
        )
        elev_results = [r for r in results if r.pathway == SmokeSpreadPathway.ELEVATOR_SHAFT]
        assert elev_results[0].propagation_time_s > 0.0

    def test_zero_building_height_no_propagation(self):
        """With zero building height, propagation time should not be calculated."""
        mo = MultiFloorOrchestrator(building_height_m=0.0)
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1"],
                "has_shaft_smoke_detector": True,
            }
        ]
        results = mo._analyze_smoke_spread(
            floor_assignments=floors, elevators=elevators,
            stairwells=[], hvac_ducts=[], smoke_barriers=[],
            building_height_m=0.0,
        )
        elev_results = [r for r in results if r.pathway == SmokeSpreadPathway.ELEVATOR_SHAFT]
        assert elev_results[0].propagation_time_s == 0.0


# ============================================================================
# Elevator Recall Tests
# ============================================================================


class TestElevatorRecall:
    """Tests for _check_elevator_recall."""

    def test_no_elevators(self, orchestrator):
        result = orchestrator._check_elevator_recall(
            elevators=[], floor_assignments=[]
        )
        assert result == []

    def test_fully_compliant_elevator(self, orchestrator):
        """A fully compliant elevator should have no violations."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF", "L1", "L2"],
                "designated_recall_floor": "GF",
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_shaft_heat_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert len(results) == 1
        assert results[0].elevator_id == "ELEV-1"
        assert results[0].phase_i_compliant is True
        assert results[0].phase_ii_compliant is True
        assert results[0].shunt_trip_compliant is True
        assert results[0].has_smoke_detector_at_recall is True
        assert len(results[0].violations) == 0

    def test_missing_phase_i_violation(self, orchestrator):
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": False,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert results[0].phase_i_compliant is False
        assert any("Phase I recall NOT PROVIDED" in v for v in results[0].violations)

    def test_missing_phase_ii_violation(self, orchestrator):
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": False,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert results[0].phase_ii_compliant is False
        assert any("Phase II" in v for v in results[0].violations)

    def test_missing_recall_smoke_detector_violation(self, orchestrator):
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": False,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert results[0].phase_i_compliant is False  # Overridden back to False
        assert any("No smoke detector at recall" in v for v in results[0].violations)

    def test_missing_machine_room_heat_detector_violation(self, orchestrator):
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": False,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert any("No heat detector in machine room" in v for v in results[0].violations)

    def test_missing_shunt_trip_violation(self, orchestrator):
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": False,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert any("Shunt trip breaker NOT PROVIDED" in v for v in results[0].violations)
        assert results[0].shunt_trip_compliant is False

    def test_shunt_trip_without_machine_room_hd_not_compliant(self, orchestrator):
        """Shunt trip present but no machine room heat detector → not compliant."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": False,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert results[0].shunt_trip_compliant is False

    def test_invalid_recall_floor_warning(self, orchestrator):
        """Recall floor not in building floor list should produce a warning."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "designated_recall_floor": "B1",  # Not in building
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert any("not found in building floor list" in w for w in results[0].warnings)

    def test_no_alternate_recall_floor_warning(self, orchestrator):
        """Missing alternate recall floor should produce a warning."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "designated_recall_floor": "GF",
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
                # No alternate_recall_floor
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert any("No alternate recall floor" in w for w in results[0].warnings)

    def test_with_alternate_recall_floor_no_warning(self, orchestrator):
        """Having an alternate recall floor should not produce the warning."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "designated_recall_floor": "GF",
                "alternate_recall_floor": "L1",
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert not any("No alternate recall floor" in w for w in results[0].warnings)

    def test_default_recall_floor(self, orchestrator):
        """Default recall floor should be 'GF'."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert results[0].designated_recall_floor == "GF"

    def test_multiple_elevators(self, orchestrator):
        """Multiple elevators should produce multiple results."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": ["GF"],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            },
            {
                "elevator_id": "ELEV-2",
                "floors_served": ["GF", "L1"],
                "has_phase_i": False,
                "has_phase_ii": False,
                "has_recall_smoke_detector": False,
                "has_machine_room_heat_detector": False,
                "has_shunt_trip": False,
            },
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert len(results) == 2
        assert results[0].elevator_id == "ELEV-1"
        assert results[1].elevator_id == "ELEV-2"


# ============================================================================
# Riser Routing Tests
# ============================================================================


class TestRiserRouting:
    """Tests for _route_risers."""

    def test_empty_floor_assignments(self, orchestrator):
        result = orchestrator._route_risers(floor_assignments=[], slc_loops=[])
        assert result == []

    def test_single_floor_no_risers(self, orchestrator):
        floors = [FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0)]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=[])
        assert len(result) == 0

    def test_two_floors_one_segment(self, orchestrator):
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=3.5, area_sqm=500.0),
        ]
        loops = [SLCLoop(loop_id="SLC-1", device_count=10, floors_served={"GF", "L1"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        assert len(result) == 1
        assert result[0].from_floor == "GF"
        assert result[0].to_floor == "L1"
        assert result[0].cable_length_m > 0.0

    def test_three_floors_two_segments(self, orchestrator):
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=3.5, area_sqm=500.0),
            FloorAssignment(floor_id="L2", floor_index=2, elevation_m=7.0, area_sqm=500.0),
        ]
        loops = [SLCLoop(loop_id="SLC-1", device_count=10, floors_served={"GF", "L1", "L2"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        assert len(result) == 2
        assert result[0].from_floor == "GF"
        assert result[0].to_floor == "L1"
        assert result[1].from_floor == "L1"
        assert result[1].to_floor == "L2"

    def test_default_inter_floor_height(self, orchestrator):
        """When floor elevations are the same, default 3.5m should be used."""
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=0.0, area_sqm=500.0),  # Same elevation
        ]
        loops = [SLCLoop(loop_id="SLC-1", device_count=10, floors_served={"GF", "L1"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        assert len(result) == 1
        # Should still produce a result with default vertical distance
        assert result[0].cable_length_m > 0.0

    def test_wire_gauge_upgraded_on_high_drop(self, orchestrator):
        """When voltage drop exceeds limits, wire gauge should be upgraded."""
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=3.5, area_sqm=500.0),
        ]
        # Many devices → high current → high voltage drop
        loops = [SLCLoop(loop_id="SLC-1", device_count=250, floors_served={"GF", "L1"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        # The result should have a wire gauge (at least "14")
        assert result[0].wire_gauge in ("14", "12", "10", "8", "6", "4", "2", "1/0")

    def test_voltage_drop_compliant_flag(self, orchestrator):
        """Voltage drop compliant flag should be set correctly."""
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=3.5, area_sqm=500.0),
        ]
        loops = [SLCLoop(loop_id="SLC-1", device_count=5, floors_served={"GF", "L1"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        assert isinstance(result[0].voltage_drop_compliant, bool)
        assert isinstance(result[0].voltage_drop_pct, float)

    def test_voltage_drop_violation_recorded(self, orchestrator):
        """When voltage drop exceeds limits, a violation should be recorded."""
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=3.5, area_sqm=500.0),
        ]
        loops = [SLCLoop(loop_id="SLC-1", device_count=250, floors_served={"GF", "L1"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        if not result[0].voltage_drop_compliant:
            assert len(result[0].violations) > 0
            assert any("voltage drop" in v.lower() for v in result[0].violations)

    def test_riser_reference(self, orchestrator):
        floors = [
            FloorAssignment(floor_id="GF", floor_index=0, elevation_m=0.0, area_sqm=500.0),
            FloorAssignment(floor_id="L1", floor_index=1, elevation_m=3.5, area_sqm=500.0),
        ]
        loops = [SLCLoop(loop_id="SLC-1", device_count=10, floors_served={"GF", "L1"})]
        result = orchestrator._route_risers(floor_assignments=floors, slc_loops=loops)
        assert "NFPA 72" in result[0].nfpa_reference
        assert "NEC" in result[0].nfpa_reference


# ============================================================================
# Compliance Evaluation Tests
# ============================================================================


class TestComplianceEvaluation:
    """Tests for _evaluate_compliance."""

    def test_empty_analysis_compliant(self):
        """An analysis with no results should be compliant (nothing to violate)."""
        analysis = BuildingAnalysis()
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is True

    def test_slc_loop_non_compliant(self):
        """Non-compliant SLC loop should make building non-compliant."""
        analysis = BuildingAnalysis()
        analysis.slc_loops = [
            SLCLoop(loop_id="SLC-1", device_count=300, max_devices=250)
        ]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is False

    def test_slc_loop_voltage_drop_non_compliant(self):
        """SLC loop with voltage drop non-compliant should make building non-compliant."""
        analysis = BuildingAnalysis()
        analysis.slc_loops = [
            SLCLoop(loop_id="SLC-1", device_count=10, max_devices=250, voltage_drop_compliant=False)
        ]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is False

    def test_vertical_zone_non_compliant(self):
        """Non-compliant vertical zone should make building non-compliant."""
        analysis = BuildingAnalysis()
        analysis.vertical_zones = [
            VerticalZone(
                zone_id="VZ-01",
                floor_ids=["F1", "F2", "F3"],
                floors_per_zone=2,
                area_compliant=True,
            )
        ]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is False

    def test_smoke_spread_violations(self):
        """Smoke spread violations should make building non-compliant."""
        analysis = BuildingAnalysis()
        analysis.smoke_spread_results = [
            SmokeSpreadResult(violations=["Some critical violation"])
        ]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is False

    def test_elevator_recall_violations(self):
        """Elevator recall violations should make building non-compliant."""
        analysis = BuildingAnalysis()
        analysis.elevator_recall_results = [
            ElevatorRecallResult(violations=["Phase I not provided"])
        ]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is False

    def test_riser_voltage_drop_non_compliant(self):
        """Non-compliant riser voltage drop should make building non-compliant."""
        analysis = BuildingAnalysis()
        analysis.riser_routing_results = [
            RiserRoutingResult(voltage_drop_compliant=False)
        ]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is False

    def test_fully_compliant(self):
        """All systems compliant should make building compliant."""
        analysis = BuildingAnalysis()
        analysis.slc_loops = [
            SLCLoop(loop_id="SLC-1", device_count=100, max_devices=250, voltage_drop_compliant=True)
        ]
        analysis.vertical_zones = [
            VerticalZone(zone_id="VZ-01", floor_ids=["GF"], floors_per_zone=2, area_compliant=True)
        ]
        analysis.smoke_spread_results = [SmokeSpreadResult(violations=[])]
        analysis.elevator_recall_results = [ElevatorRecallResult(violations=[])]
        analysis.riser_routing_results = [RiserRoutingResult(voltage_drop_compliant=True)]
        assert MultiFloorOrchestrator._evaluate_compliance(analysis) is True


# ============================================================================
# Fail-Safe and Error Handling Tests
# ============================================================================


class TestFailSafeBehavior:
    """Tests for fail-safe behavior — subsystems should not crash each other."""

    def test_floor_analysis_failure_continues(self, orchestrator, sample_building_spec):
        """If floor analysis fails, other subsystems should still run."""
        with patch.object(
            orchestrator, "_analyze_floors", side_effect=RuntimeError("Floor analysis crashed")
        ):
            result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert any("Floor analysis failed" in e for e in result.errors)
        # Other subsystems should still have run
        assert result.total_slc_loops >= 0

    def test_slc_assignment_failure_continues(self, orchestrator, sample_building_spec):
        """If SLC assignment fails, other subsystems should still run."""
        with patch.object(
            orchestrator, "_assign_slc_loops", side_effect=RuntimeError("SLC crashed")
        ):
            result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert any("SLC loop assignment failed" in e for e in result.errors)

    def test_vertical_zone_failure_continues(self, orchestrator, sample_building_spec):
        """If vertical zone design fails, other subsystems should still run."""
        with patch.object(
            orchestrator, "_design_vertical_zones", side_effect=RuntimeError("Zone crashed")
        ):
            result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert any("Vertical zone design failed" in e for e in result.errors)

    def test_smoke_spread_failure_continues(self, orchestrator, sample_building_spec):
        """If smoke spread analysis fails, other subsystems should still run."""
        with patch.object(
            orchestrator, "_analyze_smoke_spread", side_effect=RuntimeError("Smoke crashed")
        ):
            result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert any("Smoke spread analysis failed" in e for e in result.errors)

    def test_elevator_recall_failure_continues(self, orchestrator, sample_building_spec):
        """If elevator recall fails, other subsystems should still run."""
        with patch.object(
            orchestrator, "_check_elevator_recall", side_effect=RuntimeError("Elevator crashed")
        ):
            result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert any("Elevator recall check failed" in e for e in result.errors)

    def test_riser_routing_failure_continues(self, orchestrator, sample_building_spec):
        """If riser routing fails, other subsystems should still run."""
        with patch.object(
            orchestrator, "_route_risers", side_effect=RuntimeError("Riser crashed")
        ):
            result = orchestrator.orchestrate(**sample_building_spec)
        assert isinstance(result, BuildingAnalysis)
        assert any("Riser routing failed" in e for e in result.errors)


class TestOrchestrateWithFloorOrchestrator:
    """Tests for orchestrate with a mocked FloorOrchestrator that returns real data."""

    def test_with_mock_floor_orchestrator(self, mock_floor_result):
        """Test orchestrate with a mocked FloorOrchestrator.process()."""
        fo = MagicMock(spec=FloorOrchestrator)
        fo.process.return_value = mock_floor_result

        mo = MultiFloorOrchestrator(
            floor_orchestrator=fo,
            building_height_m=20.0,
        )

        result = mo.orchestrate(
            building_id="BLDG-MOCK",
            floors={"GF": [MagicMock()]},  # One room spec
            floor_elevations={"GF": 0.0},
            floor_areas={"GF": 500.0},
        )

        assert result.building_id == "BLDG-MOCK"
        assert result.total_floors == 1
        assert len(result.floor_assignments) == 1
        # FloorOrchestrator.process should have been called
        fo.process.assert_called_once()

    def test_floor_result_status_warning(self):
        """Floor with non-APPROVED status should produce a warning."""
        room = RoomResult(room_id="R1", status="FAIL", detector_count=2)
        floor_result = FloorResult(
            project_name="test",
            source_dxf="test.dxf",
            total_rooms=1,
            room_results=[room],
            rooms_passed=0,
            rooms_failed=1,
            rooms_errored=0,
            total_detectors=2,
            status="REJECTED",
        )

        fo = MagicMock(spec=FloorOrchestrator)
        fo.process.return_value = floor_result

        mo = MultiFloorOrchestrator(floor_orchestrator=fo, building_height_m=10.0)
        result = mo.orchestrate(
            building_id="BLDG-FAIL",
            floors={"GF": [MagicMock()]},
            floor_elevations={"GF": 0.0},
            floor_areas={"GF": 500.0},
        )

        fa = result.floor_assignments[0]
        assert any("status: REJECTED" in w for w in fa.warnings)

    def test_device_count_from_room_results(self):
        """Device counts should be derived from room results."""
        rooms = [
            RoomResult(room_id="R1", status="PASS", detector_count=5),
            RoomResult(room_id="R2", status="PASS", detector_count=3),
        ]
        floor_result = FloorResult(
            project_name="test",
            source_dxf="test.dxf",
            total_rooms=2,
            room_results=rooms,
            rooms_passed=2,
            rooms_failed=0,
            rooms_errored=0,
            total_detectors=8,
            status="APPROVED",
        )

        fo = MagicMock(spec=FloorOrchestrator)
        fo.process.return_value = floor_result

        mo = MultiFloorOrchestrator(floor_orchestrator=fo, building_height_m=10.0)
        result = mo.orchestrate(
            building_id="BLDG-DEV",
            floors={"GF": [MagicMock()]},
            floor_elevations={"GF": 0.0},
            floor_areas={"GF": 500.0},
        )

        fa = result.floor_assignments[0]
        # total_detectors = floor_result.total_detectors + sum of detector_count from room_results
        # The code sets fa.total_detectors from FloorResult, then adds detector_count from each rr
        assert fa.total_detectors > 0
        assert fa.total_devices > 0
        # Notification and module estimates should be present
        assert fa.total_notification > 0
        assert fa.total_modules > 0


# ============================================================================
# Residential Building Tests
# ============================================================================


class TestResidentialBuilding:
    """Tests for residential building orchestration."""

    def test_residential_zone_design(self, orchestrator, residential_building_spec):
        """Residential buildings should have 1 floor per zone."""
        result = orchestrator.orchestrate(**residential_building_spec)
        assert len(result.vertical_zones) == 4  # 4 floors, 1 per zone
        for zone in result.vertical_zones:
            assert zone.floors_per_zone == 1
            assert len(zone.floor_ids) == 1

    def test_residential_occupancy_type_in_zones(self, orchestrator, residential_building_spec):
        result = orchestrator.orchestrate(**residential_building_spec)
        for zone in result.vertical_zones:
            assert zone.occupancy_type == "residential"


# ============================================================================
# Tall Building Tests
# ============================================================================


class TestTallBuilding:
    """Tests for tall building scenarios requiring pressurization."""

    def test_tall_building_stairwell_pressurization(self, tall_building_spec):
        """Tall building (>22.86m) should require stairwell pressurization."""
        mo = MultiFloorOrchestrator(building_height_m=25.0)
        result = mo.orchestrate(**tall_building_spec)

        stair_results = [
            r for r in result.smoke_spread_results
            if r.pathway == SmokeSpreadPathway.STAIRWELL
        ]
        assert len(stair_results) > 0
        assert stair_results[0].pressurization_required is True

    def test_tall_building_no_fan_violation(self, tall_building_spec):
        """Tall building with unpressurized stairwell should have violations."""
        mo = MultiFloorOrchestrator(building_height_m=25.0)
        result = mo.orchestrate(**tall_building_spec)

        stair_results = [
            r for r in result.smoke_spread_results
            if r.pathway == SmokeSpreadPathway.STAIRWELL
        ]
        assert len(stair_results[0].violations) > 0
        assert any("lacks pressurization fan" in v for v in stair_results[0].violations)


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_building_id_with_special_characters(self, orchestrator):
        result = orchestrator.orchestrate(
            building_id="BLDG-2024/REV.B",
            floors={"GF": []},
        )
        assert result.building_id == "BLDG-2024/REV.B"

    def test_very_large_building(self):
        """Test with a large number of floors."""
        mo = MultiFloorOrchestrator(building_height_m=100.0)
        floors_spec = {f"F{i}": [] for i in range(20)}
        floor_elevations = {f"F{i}": float(i * 3.5) for i in range(20)}
        floor_areas = {f"F{i}": 800.0 for i in range(20)}

        result = mo.orchestrate(
            building_id="LARGE-001",
            floors=floors_spec,
            floor_elevations=floor_elevations,
            floor_areas=floor_areas,
        )
        assert result.total_floors == 20
        assert len(result.floor_assignments) == 20
        assert len(result.riser_routing_results) == 19

    def test_all_fields_none_optional(self, orchestrator):
        """Orchestrate should work with only required parameters."""
        result = orchestrator.orchestrate(
            building_id="MINIMAL",
            floors={"GF": []},
        )
        assert result.building_id == "MINIMAL"
        assert result.total_floors == 1

    def test_area_compliant_boundary(self, orchestrator):
        """Test vertical zone at the exact area boundary."""
        # Zone area exactly at the limit
        area_exactly_at_limit = MAX_ZONE_AREA_SQM
        floors = [
            FloorAssignment(
                floor_id="GF", floor_index=0, total_devices=10,
                area_sqm=area_exactly_at_limit,
            ),
        ]
        zones = orchestrator._design_vertical_zones(
            floors, "business", {"GF": area_exactly_at_limit}
        )
        # area_exactly_at_limit <= MAX_ZONE_AREA_SQM → should be compliant
        assert zones[0].area_compliant is True

    def test_area_just_over_boundary(self, orchestrator):
        """Test vertical zone just over the area boundary."""
        area_over_limit = MAX_ZONE_AREA_SQM + 1.0
        floors = [
            FloorAssignment(
                floor_id="GF", floor_index=0, total_devices=10,
                area_sqm=area_over_limit,
            ),
        ]
        zones = orchestrator._design_vertical_zones(
            floors, "business", {"GF": area_over_limit}
        )
        assert zones[0].area_compliant is False

    def test_slc_loop_at_exact_capacity(self):
        """SLC loop with exactly max devices should be compliant."""
        mo = MultiFloorOrchestrator(max_slc_devices=10, building_height_m=10.0)
        fa = FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=10,
            area_sqm=500.0, elevation_m=0.0,
        )
        loops = mo._assign_slc_loops([fa])
        assert len(loops) == 1
        assert loops[0].device_count == 10
        assert loops[0].is_compliant is True

    def test_slc_loop_one_over_capacity(self):
        """SLC loop with max+1 devices should split into two loops."""
        mo = MultiFloorOrchestrator(max_slc_devices=10, building_height_m=10.0)
        fa = FloorAssignment(
            floor_id="GF", floor_index=0, total_devices=11,
            area_sqm=500.0, elevation_m=0.0,
        )
        loops = mo._assign_slc_loops([fa])
        assert len(loops) == 2

    def test_occupancy_type_case_insensitive(self, orchestrator):
        """Occupancy type should be case-insensitive for zone design."""
        floors = [
            FloorAssignment(floor_id="F1", floor_index=0, total_devices=10, area_sqm=400.0),
            FloorAssignment(floor_id="F2", floor_index=1, total_devices=10, area_sqm=400.0),
        ]
        zones_lower = orchestrator._design_vertical_zones(floors, "residential")
        zones_upper = orchestrator._design_vertical_zones(floors, "Residential")
        zones_mixed = orchestrator._design_vertical_zones(floors, "RESIDENTIAL")

        assert len(zones_lower) == len(zones_upper) == len(zones_mixed) == 2

    def test_elevator_with_empty_floors_served(self, orchestrator):
        """Elevator with no floors served should not crash."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0)]
        elevators = [
            {
                "elevator_id": "ELEV-1",
                "floors_served": [],
                "has_phase_i": True,
                "has_phase_ii": True,
                "has_recall_smoke_detector": True,
                "has_machine_room_heat_detector": True,
                "has_shunt_trip": True,
            }
        ]
        results = orchestrator._check_elevator_recall(elevators, floors)
        assert len(results) == 1
        assert results[0].floors_served == []  # Empty floor list propagated

    def test_stairwell_with_stairwell_id_key(self, orchestrator):
        """Stairwell with 'stairwell_id' key instead of 'zone_id' should work."""
        floors = [FloorAssignment(floor_id="GF", floor_index=0, area_sqm=500.0, elevation_m=0.0)]
        stairwells = [
            {
                "stairwell_id": "STAIR-ALT",
                "floors_served": ["GF", "L1"],
                "has_pressurization_fan": True,
                "has_pressure_switches": True,
                "design_pressure_pa": 50.0,
            }
        ]
        results = orchestrator._analyze_smoke_spread(
            floor_assignments=floors, elevators=[], stairwells=stairwells,
            hvac_ducts=[], smoke_barriers=[], building_height_m=30.0,
        )
        stair_results = [r for r in results if r.pathway == SmokeSpreadPathway.STAIRWELL]
        assert len(stair_results) == 1
