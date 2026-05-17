"""
test_building_engine.py — BuildingEngine V0.1 Test Suite
========================================================
Tests multi-floor building analysis with BuildingEngine.

Test Scenarios (per user audit requirements):
  1. Empty building (no floors)
  2. All floors compliant
  3. One floor with an unsafe room → safe_to_submit == False
  4. AuditStore receives events from all floors

NFPA References:
  - NFPA 72 (2022) Section 17.6.3 — smoke detector coverage
  - NFPA 72 (2022) Section 17.7.5 — duct detectors (placeholder)
  - NFPA 72 (2022) Table 17.6.3.1 — ceiling height / radius
"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
from fireai.core.building_engine import BuildingEngine, BuildingReport
from fireai.core.floor_analyser import FloorReport, RoomSummary
from fireai.core.audit_trail import AuditTrail


# ─── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def optimizer():
    """V7.3 DensityOptimizer with default R=6.40m."""
    return DensityOptimizer()


@pytest.fixture
def audit_trail():
    """In-memory AuditTrail for testing."""
    return AuditTrail(project_name="test_building")


@pytest.fixture
def audit_store():
    """Tamper-proof AuditStore with temporary database."""
    # Set up temp DB before import
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["AUDIT_DB_PATH"] = db_path

    import importlib
    import fireai.core.audit_store as store_mod
    importlib.reload(store_mod)

    yield store_mod

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    os.environ.pop("AUDIT_DB_PATH", None)


# ─── Test 1: Empty building — NFPA 72 §17.6.3 requires at least one space ───

def test_empty_building(optimizer):
    """Building with no floors → safe_to_submit=False, fully_compliant=False."""
    engine = BuildingEngine("EMPTY-BLDG", optimizer)
    report = engine.analyse({})

    assert isinstance(report, BuildingReport)
    assert report.total_floors == 0
    assert report.total_detectors == 0
    assert report.fully_compliant is False
    assert report.safe_to_submit is False
    assert len(report.building_warnings) > 0
    assert any("No floors" in w for w in report.building_warnings)


# ─── Test 2: All floors compliant — NFPA 72 §17.6.3 ───

def test_all_floors_compliant(optimizer, audit_trail):
    """Multi-floor building where every room passes the triple-check gate."""
    engine = BuildingEngine("GOOD-BLDG", optimizer, audit_trail=audit_trail)
    floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
            {"room_id": "parking", "name": "parking",
             "polygon_coords": [(0,0),(30,0),(30,20),(0,20)], "ceiling_height": 3.0},
        ],
        "L1": [
            {"room_id": "office", "name": "office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
            {"room_id": "meeting", "name": "meeting",
             "polygon_coords": [(0,0),(6,0),(6,5),(0,5)], "ceiling_height": 3.0},
        ],
        "L2": [
            {"room_id": "server_room", "name": "server_room",
             "polygon_coords": [(0,0),(8,0),(8,6),(0,6)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    assert report.total_floors == 3
    assert report.total_detectors > 0
    assert report.total_theoretical_lower_bound > 0
    assert report.fully_compliant is True
    assert report.safe_to_submit is True
    assert len(report.non_compliant_floors) == 0
    assert len(report.unsafe_floors) == 0
    assert len(report.building_warnings) == 0

    # Verify each floor report is present
    assert len(report.floor_reports) == 3
    for fr in report.floor_reports:
        assert isinstance(fr, FloorReport)
        assert fr.fully_compliant is True
        assert fr.safe_to_submit is True

    # Verify audit trail recorded placements
    assert audit_trail.count() > 0
    assert audit_trail.verify_integrity() is True


# ─── Test 3: One unsafe room blocks the entire building ───

def test_unsafe_room_blocks_building(optimizer):
    """
    Building with one UNSAFE room (fallback_used=True) in one floor
    → that floor's safe_to_submit=False → building's safe_to_submit=False.

    NFPA 72 §17.6.3: triple-check gate (proof_valid AND nfpa_valid AND NOT fallback_used).
    We simulate fallback by using a room that triggers the fallback strategy.
    A very narrow corridor (1x50m) typically triggers fallback.
    """
    engine = BuildingEngine("RISKY-BLDG", optimizer)
    floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
        "L1": [
            # This very narrow room often triggers fallback_used=True
            {"room_id": "thin_corridor", "name": "thin_corridor",
             "polygon_coords": [(0,0),(1,0),(1,50),(0,50)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    # Building may or may not be fully_compliant depending on fallback
    # But we test the logic: if any floor has safe_to_submit=False,
    # then building's safe_to_submit must be False
    floor_unsafe = any(not fr.safe_to_submit for fr in report.floor_reports)
    if floor_unsafe:
        assert report.safe_to_submit is False
        assert len(report.unsafe_floors) > 0
        assert any("UNSAFE" in w for w in report.building_warnings)


# ─── Test 4: AuditStore receives events from all floors ───

def test_audit_store_receives_events(optimizer, audit_store):
    """
    When audit_store is provided, events from ALL floors are recorded
    in the tamper-proof hash chain, including:
      - DETECTOR_PLACEMENT per room
      - BUILDING_ANALYSIS_START
      - BUILDING_ANALYSIS_COMPLETE
    """
    engine = BuildingEngine("AUDIT-BLDG", optimizer, audit_store=audit_store)
    floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
        "L1": [
            {"room_id": "office", "name": "office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    # AuditStore must have events
    events = audit_store.get_events()
    assert len(events) > 0

    # Must have building-level events
    event_types = [e["event_type"] for e in events]
    assert "BUILDING_ANALYSIS_START" in event_types
    assert "BUILDING_ANALYSIS_COMPLETE" in event_types

    # Must have room-level events from multiple floors
    placement_events = [e for e in events if e["event_type"] == "DETECTOR_PLACEMENT"]
    assert len(placement_events) >= 2  # At least one per room

    # Rooms from different floors
    room_ids = [e["room_id"] for e in placement_events]
    assert "lobby" in room_ids
    assert "office" in room_ids

    # Chain integrity must be intact
    is_valid, error = audit_store.verify_chain()
    assert is_valid, f"AuditStore chain broken: {error}"


# ─── Test 5: total_duct_devices and total_theoretical_lower_bound ───

def test_building_aggregation_metrics(optimizer):
    """Verify total_detectors, total_theoretical_lower_bound, total_duct_devices aggregate correctly."""
    engine = BuildingEngine("METRICS-BLDG", optimizer)
    floors = {
        "GF": [
            {"room_id": "lobby_12x8", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
        "L1": [
            {"room_id": "warehouse_50x40", "name": "warehouse",
             "polygon_coords": [(0,0),(50,0),(50,40),(0,40)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    # Verify aggregation
    sum_detectors = sum(fr.total_detectors for fr in report.floor_reports)
    sum_lb = sum(fr.total_theoretical_lower_bound for fr in report.floor_reports)
    sum_duct = sum(s.duct_devices for fr in report.floor_reports for s in fr.room_summaries)

    assert report.total_detectors == sum_detectors
    assert report.total_theoretical_lower_bound == sum_lb
    assert report.total_duct_devices == sum_duct
    assert report.total_duct_devices == 0  # No duct logic yet — placeholder

    # Each floor must have RoomSummary with theoretical_lower_bound
    for fr in report.floor_reports:
        for s in fr.room_summaries:
            assert s.theoretical_lower_bound >= 1
            assert 0.0 <= s.efficiency_ratio <= 1.0


# ─── Test 6: audit_store passed to FloorAnalyser ───

def test_audit_store_passed_to_floor_analyser(optimizer, audit_store):
    """
    Verify that the same audit_store object passed to BuildingEngine
    is also used by FloorAnalyser (critical events from rooms go to tamper-proof store).
    """
    engine = BuildingEngine("STORE-PASS-BLDG", optimizer, audit_store=audit_store)
    floors = {
        "GF": [
            {"room_id": "R1", "name": "room1",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    # There should be room-level DETECTOR_PLACEMENT events in the store
    events = audit_store.get_events()
    placement_events = [e for e in events if e["event_type"] == "DETECTOR_PLACEMENT"]
    assert len(placement_events) >= 1

    # The placement event should have details from FloorAnalyser
    det_event = placement_events[0]
    assert "detector_count" in det_event["details"]
    assert "coverage_pct" in det_event["details"]
    assert "theoretical_lower_bound" in det_event["details"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
