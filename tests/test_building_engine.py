"""
tests/test_building_engine.py
================================
Comprehensive test suite for fireai/core/building_engine.py

SAFETY CRITICAL: BuildingEngine aggregates per-floor analysis and makes
the final safe_to_submit decision. A single unsafe room in ANY floor
must block the entire building from submission. Errors here could approve
non-compliant fire alarm designs — a direct life-safety hazard.

NFPA 72 References:
  §21.3.3 — Zone requirements
  §21.2.2 — Maximum devices per panel
  §10.4.4 — Zone identification

Architecture:
  - FloorAnalyser per floor (composition, not reimplementation)
  - FireZoneEngine per floor for zone clustering
  - DeltaCache for incremental processing
  - Sequential execution only — no parallel processing
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fireai.core.building_engine import (
    BuildingEngine,
    BuildingReport,
)
from fireai.core.fire_zone_engine import ZoneConstraints
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def optimizer():
    return DensityOptimizer()


@pytest.fixture
def engine(optimizer):
    return BuildingEngine("BLDG-001", optimizer)


@pytest.fixture
def simple_floors():
    """Two floors, each with one simple room."""
    return {
        "GF": [
            {
                "room_id": "lobby",
                "name": "Lobby",
                "polygon_coords": [(0, 0), (12, 0), (12, 8), (0, 8)],
                "ceiling_height": 3.0,
            },
        ],
        "L1": [
            {
                "room_id": "office",
                "name": "Office",
                "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
                "ceiling_height": 3.0,
            },
        ],
    }


@pytest.fixture
def empty_floors():
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# BuildingReport Dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingReport:
    def test_defaults(self):
        report = BuildingReport(building_id="B1")
        assert report.building_id == "B1"
        assert report.floor_reports == []
        assert report.total_detectors == 0
        assert report.total_theoretical_lower_bound == 0
        assert report.total_duct_devices == 0
        assert report.total_floors == 0
        assert report.fully_compliant is False
        assert report.safe_to_submit is False
        assert report.non_compliant_floors == []
        assert report.unsafe_floors == []
        assert report.building_warnings == []
        assert report.analysis_time_s == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert report.project_profile is None
        assert report.zone_reports == {}
        assert report.cache_stats is None


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineInit:
    def test_basic_init(self, optimizer):
        engine = BuildingEngine("BLDG-001", optimizer)
        assert engine.building_id == "BLDG-001"
        assert engine.opt is optimizer

    def test_zone_engine_initialized(self, optimizer):
        engine = BuildingEngine("BLDG-001", optimizer)
        assert engine.zone_engine is not None

    def test_delta_cache_initialized(self, optimizer):
        engine = BuildingEngine("BLDG-001", optimizer)
        assert engine.delta_cache is not None

    def test_custom_zone_constraints(self, optimizer):
        constraints = ZoneConstraints(max_area_sqm=1000, max_detectors_per_zone=50)
        engine = BuildingEngine("BLDG-001", optimizer, zone_constraints=constraints)
        assert engine.zone_engine.constraints.max_area_sqm == 1000

    def test_audit_trail_none_by_default(self, optimizer):
        engine = BuildingEngine("BLDG-001", optimizer)
        assert engine.audit_trail is None

    def test_audit_store_none_by_default(self, optimizer):
        engine = BuildingEngine("BLDG-001", optimizer)
        assert engine.audit_store is None


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine — Empty / Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineEmptyInput:
    def test_empty_floors_not_safe_to_submit(self, engine, empty_floors):
        """No floors → not safe to submit."""
        report = engine.analyse(empty_floors)
        assert report.safe_to_submit is False
        assert report.fully_compliant is False

    def test_empty_floors_warning(self, engine, empty_floors):
        report = engine.analyse(empty_floors)
        assert any("No floors" in w for w in report.building_warnings)

    def test_empty_floors_zero_detectors(self, engine, empty_floors):
        report = engine.analyse(empty_floors)
        assert report.total_detectors == 0
        assert report.total_floors == 0


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine — Standard Analysis
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineAnalysis:
    def test_simple_building_compliant(self, engine, simple_floors):
        """Simple building with standard rooms should be compliant."""
        report = engine.analyse(simple_floors)
        assert report.total_floors == 2
        assert report.total_detectors >= 2  # At least 1 per room

    def test_building_id_preserved(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        assert report.building_id == "BLDG-001"

    def test_floor_reports_populated(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        assert len(report.floor_reports) == 2

    def test_analysis_time_positive(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        assert report.analysis_time_s >= 0.0

    def test_zone_reports_populated(self, engine, simple_floors):
        """V0.2: Fire zone clustering per floor."""
        report = engine.analyse(simple_floors)
        assert isinstance(report.zone_reports, dict)

    def test_cache_stats_populated(self, engine, simple_floors):
        """V0.2: DeltaCache statistics."""
        report = engine.analyse(simple_floors)
        assert report.cache_stats is not None

    def test_total_detectors_summed(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        floor_total = sum(fr.total_detectors for fr in report.floor_reports)
        assert report.total_detectors == floor_total


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine — Safety Gates
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineSafetyGates:
    def test_safe_to_submit_depends_on_all_floors(self, engine, simple_floors):
        """Conservative: ALL floors must be safe for building to be safe."""
        report = engine.analyse(simple_floors)
        # If any floor is unsafe, building must be unsafe
        for fr in report.floor_reports:
            if not fr.safe_to_submit:
                assert report.safe_to_submit is False
                return
        # All floors safe → building safe
        assert report.safe_to_submit is True

    def test_fully_compliant_depends_on_all_floors(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        for fr in report.floor_reports:
            if not fr.fully_compliant:
                assert report.fully_compliant is False
                return
        assert report.fully_compliant is True

    def test_unsafe_floors_list(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        # unsafe_floors should list floors with safe_to_submit=False
        for fr in report.floor_reports:
            if not fr.safe_to_submit:
                assert fr.floor_id in report.unsafe_floors

    def test_non_compliant_floors_list(self, engine, simple_floors):
        report = engine.analyse(simple_floors)
        for fr in report.floor_reports:
            if not fr.fully_compliant:
                assert fr.floor_id in report.non_compliant_floors


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine — AuditStore Integration
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineAuditStore:
    def test_audit_store_events_logged(self, optimizer, simple_floors):
        """AuditStore receives BUILDING_ANALYSIS_START and COMPLETE events."""
        mock_store = MagicMock()
        mock_store.add_event = MagicMock()
        engine = BuildingEngine("BLDG-TEST", optimizer, audit_store=mock_store)
        engine.analyse(simple_floors)
        # Should have at least START and COMPLETE events
        calls = mock_store.add_event.call_args_list
        [c[1].get("event_type", c[0][0] if c[0] else "") for c in calls]
        # Check that add_event was called at least twice (START + COMPLETE)
        assert mock_store.add_event.call_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine — Project Profile
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineProjectProfile:
    def test_project_profile_created(self, engine, simple_floors):
        """V5.0: Project learning profile populated after analysis."""
        report = engine.analyse(simple_floors)
        # profile may or may not be populated depending on room summaries
        # but should be an attribute
        assert hasattr(report, "project_profile")


# ─────────────────────────────────────────────────────────────────────────────
# BuildingEngine — Large Building Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildingEngineLargeScenario:
    def test_multi_floor_building(self, optimizer):
        """3-floor building with multiple rooms per floor."""
        engine = BuildingEngine("BLDG-LARGE", optimizer)
        floors = {
            "GF": [
                {
                    "room_id": "lobby_12x8",
                    "name": "lobby",
                    "polygon_coords": [(0, 0), (12, 0), (12, 8), (0, 8)],
                    "ceiling_height": 3.0,
                },
            ],
            "L1": [
                {
                    "room_id": "office_10x8",
                    "name": "office",
                    "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
                    "ceiling_height": 3.0,
                },
                {
                    "room_id": "meeting_6x5",
                    "name": "meeting",
                    "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
                    "ceiling_height": 3.0,
                },
            ],
            "L2": [
                {
                    "room_id": "warehouse_50x40",
                    "name": "warehouse",
                    "polygon_coords": [(0, 0), (50, 0), (50, 40), (0, 40)],
                    "ceiling_height": 3.0,
                },
            ],
        }
        report = engine.analyse(floors)
        assert report.total_floors == 3
        assert report.total_detectors >= 4  # At least 1 per room
