"""
test_comprehensive.py — FireAI V8.0 Comprehensive Test Suite
=============================================================
End-to-end tests across all three architectural layers:
  Layer 1: DensityOptimizer V7.3 (single room)
  Layer 2: FloorAnalyser V2.1 (floor — multiple rooms)
  Layer 3: BuildingEngine V0.1 (building — multiple floors)

Plus cross-cutting concerns:
  - AuditTrail V5.2 integrity
  - AuditStore tamper-proof chain
  - theoretical_lower_bound invariant
  - Conservative safe_to_submit gate

NFPA References:
  - NFPA 72 (2022) Section 17.6.3 — smoke detector coverage
  - NFPA 72 (2022) Section 17.7.4.2.3.1 — 0.7S rule
  - NFPA 72 (2022) Table 17.6.3.1 — ceiling height / radius
  - NFPA 72 (2022) Section 17.7.5 — duct detectors
"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room, DetectorLayout
from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.building_engine import BuildingEngine, BuildingReport
from audit_trail import AuditTrail


# ─── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def optimizer():
    """V7.3 DensityOptimizer with default R=6.40m."""
    return DensityOptimizer()


@pytest.fixture
def audit_trail():
    """In-memory AuditTrail V5.2 for testing."""
    return AuditTrail(project_name="comprehensive_test")


@pytest.fixture
def audit_store():
    """Tamper-proof AuditStore with temporary database."""
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["AUDIT_DB_PATH"] = db_path

    import importlib
    import fireai.core.audit_store as store_mod
    importlib.reload(store_mod)

    yield store_mod

    if os.path.exists(db_path):
        os.unlink(db_path)
    os.environ.pop("AUDIT_DB_PATH", None)


# ─── Layer 1: DensityOptimizer V7.3 — single room ──────────────
# NFPA 72 §17.6.3, §17.7.4.2.3.1

def test_1_single_room_density_optimizer(optimizer):
    """
    Layer 1: DensityOptimizer places detectors for a single room.
    Verifies: coverage >= 99%, nfpa_valid, at least 1 detector.
    NFPA 72 §17.6.3 — coverage requirement.
    NFPA 72 §17.7.4.2.3.1 — 0.7S rule (R = 6.40m).
    """
    room = Room(name="test_office", width=12, length=8, ceiling_height=3.0)
    layout = optimizer.optimize(room)

    # Must place at least 1 detector
    assert layout.count >= 1, f"Expected at least 1 detector, got {layout.count}"

    # Coverage must be >= 99% (NFPA 72 §17.6.3)
    assert layout.coverage_pct >= 99.0, f"Coverage {layout.coverage_pct:.2f}% < 99%"

    # NFPA spacing must be valid
    assert layout.nfpa_valid is True, "NFPA validation failed"

    # theoretical_lower_bound must be <= detector count
    assert layout.theoretical_lower_bound >= 1, "theoretical_lower_bound must be >= 1"
    assert layout.theoretical_lower_bound <= layout.count, (
        f"theoretical_lower_bound ({layout.theoretical_lower_bound}) > count ({layout.count})"
    )

    # efficiency_ratio must be in [0, 1]
    assert 0.0 <= layout.efficiency_ratio <= 1.0, (
        f"efficiency_ratio {layout.efficiency_ratio:.4f} out of range"
    )


# ─── Layer 2: FloorAnalyser V2.1 — 10 realistic rooms ──────────
# NFPA 72 §17.6.3, Table 17.6.3.1

def test_2_floor_analyser_ten_rooms(optimizer):
    """
    Layer 2: FloorAnalyser processes 10 realistic rooms.
    All rooms must pass the triple-check gate.
    NFPA 72 §17.6.3 — triple-check: proof_valid AND nfpa_valid AND NOT fallback_used.
    """
    analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)

    rooms = [
        {"room_id": "lobby", "name": "lobby",
         "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        {"room_id": "parking", "name": "parking",
         "polygon_coords": [(0,0),(30,0),(30,20),(0,20)], "ceiling_height": 3.0},
        {"room_id": "stairwell", "name": "stairwell",
         "polygon_coords": [(0,0),(3,0),(3,3),(0,3)], "ceiling_height": 3.0},
        {"room_id": "server_room", "name": "server_room",
         "polygon_coords": [(0,0),(8,0),(8,6),(0,6)], "ceiling_height": 3.0},
        {"room_id": "corridor", "name": "corridor",
         "polygon_coords": [(0,0),(20,0),(20,2),(0,2)], "ceiling_height": 3.0},
        {"room_id": "kitchen", "name": "kitchen",
         "polygon_coords": [(0,0),(6,0),(6,5),(0,5)], "ceiling_height": 3.0},
        {"room_id": "open_office", "name": "open_office",
         "polygon_coords": [(0,0),(25,0),(25,15),(0,15)], "ceiling_height": 3.0},
        {"room_id": "warehouse", "name": "warehouse",
         "polygon_coords": [(0,0),(50,0),(50,40),(0,40)], "ceiling_height": 3.0},
        {"room_id": "meeting", "name": "meeting",
         "polygon_coords": [(0,0),(6,0),(6,5),(0,5)], "ceiling_height": 3.0},
        {"room_id": "restroom", "name": "restroom",
         "polygon_coords": [(0,0),(3,0),(3,2),(0,2)], "ceiling_height": 3.0},
    ]

    report = analyser.analyse(rooms)

    assert isinstance(report, FloorReport)
    assert len(report.room_summaries) == 10
    assert report.fully_compliant is True
    assert report.safe_to_submit is True
    assert report.total_detectors > 0
    assert report.total_theoretical_lower_bound > 0

    # Every room must have coverage >= 99%
    for s in report.room_summaries:
        assert s.coverage_pct >= 99.0, f"Room {s.name}: coverage {s.coverage_pct:.2f}% < 99%"
        assert s.theoretical_lower_bound >= 1
        assert s.theoretical_lower_bound <= s.detector_count


# ─── Layer 3: BuildingEngine V0.1 — 3-floor building ───────────

def test_3_building_engine_three_floors(optimizer, audit_trail, audit_store):
    """
    Layer 3: BuildingEngine analyses a 3-floor building.
    All floors must be compliant and safe.
    Building-level metrics must aggregate correctly.
    """
    engine = BuildingEngine(
        "BLDG-001", optimizer,
        audit_trail=audit_trail,
        audit_store=audit_store,
    )

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
            {"room_id": "warehouse", "name": "warehouse",
             "polygon_coords": [(0,0),(50,0),(50,40),(0,40)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    assert isinstance(report, BuildingReport)
    assert report.total_floors == 3
    assert report.fully_compliant is True
    assert report.safe_to_submit is True
    assert report.total_detectors > 0
    assert report.total_theoretical_lower_bound > 0
    assert len(report.unsafe_floors) == 0
    assert len(report.non_compliant_floors) == 0

    # Aggregation check
    sum_dets = sum(fr.total_detectors for fr in report.floor_reports)
    sum_lb = sum(fr.total_theoretical_lower_bound for fr in report.floor_reports)
    assert report.total_detectors == sum_dets
    assert report.total_theoretical_lower_bound == sum_lb


# ─── Cross-cutting: AuditStore tamper-proof chain ───────────────

def test_4_audit_store_chain_integrity(optimizer, audit_store):
    """
    AuditStore receives events from all layers.
    Hash chain + HMAC signatures must be intact after analysis.
    """
    engine = BuildingEngine("AUDIT-CHAIN", optimizer, audit_store=audit_store)
    floors = {
        "GF": [
            {"room_id": "room1", "name": "room1",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ],
        "L1": [
            {"room_id": "room2", "name": "room2",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
    }

    report = engine.analyse(floors)

    # Verify chain integrity
    is_valid, error = audit_store.verify_chain()
    assert is_valid, f"AuditStore chain broken: {error}"

    # Must have building-level events
    events = audit_store.get_events()
    event_types = [e["event_type"] for e in events]
    assert "BUILDING_ANALYSIS_START" in event_types
    assert "BUILDING_ANALYSIS_COMPLETE" in event_types

    # Must have room-level events from both floors
    placement_events = [e for e in events if e["event_type"] == "DETECTOR_PLACEMENT"]
    assert len(placement_events) >= 2


# ─── Cross-cutting: AuditTrail integrity ────────────────────────

def test_5_audit_trail_integrity(optimizer, audit_trail):
    """
    AuditTrail V5.2 records all placements with thread-safe append.
    Per-entry SHA-256 hash verification must pass.
    """
    analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer, audit_trail=audit_trail)

    rooms = [
        {"room_id": "R1", "name": "room1",
         "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        {"room_id": "R2", "name": "room2",
         "polygon_coords": [(0,0),(20,0),(20,15),(0,15)], "ceiling_height": 3.0},
    ]

    report = analyser.analyse(rooms)

    # AuditTrail must have entries
    assert audit_trail.count() >= 2  # At least one placement per room

    # Integrity check must pass
    assert audit_trail.verify_integrity() is True

    # Room trail must be retrievable
    r1_trail = audit_trail.get_room_trail("R1")
    assert len(r1_trail) >= 1
    r2_trail = audit_trail.get_room_trail("R2")
    assert len(r2_trail) >= 1


# ─── Invariant: theoretical_lower_bound <= detector_count ───────

def test_6_theoretical_lower_bound_invariant(optimizer):
    """
    For any room, theoretical_lower_bound must be <= detector_count.
    This is a geometric invariant: ceil(area / pi*R^2) cannot exceed
    the number of detectors that achieve >= 99% coverage.

    NFPA 72 §17.6.3 — coverage requirement guarantees this.
    """
    rooms = [
        Room(name="small", width=3, length=2, ceiling_height=3.0),
        Room(name="medium", width=10, length=8, ceiling_height=3.0),
        Room(name="large", width=30, length=20, ceiling_height=3.0),
        Room(name="warehouse", width=50, length=40, ceiling_height=3.0),
        Room(name="corridor", width=20, length=2, ceiling_height=3.0),
        Room(name="square", width=15, length=15, ceiling_height=3.0),
    ]

    for room in rooms:
        layout = optimizer.optimize(room)
        assert layout.theoretical_lower_bound <= layout.count, (
            f"Room {room.name} ({room.width}x{room.length}): "
            f"LB={layout.theoretical_lower_bound} > count={layout.count}"
        )
        assert layout.theoretical_lower_bound >= 1, (
            f"Room {room.name}: LB={layout.theoretical_lower_bound} < 1"
        )
        assert 0.0 <= layout.efficiency_ratio <= 1.0, (
            f"Room {room.name}: efficiency_ratio={layout.efficiency_ratio:.4f}"
        )


# ─── Conservative gate: safe_to_submit ──────────────────────────

def test_7_safe_to_submit_conservative_gate(optimizer):
    """
    Any UNSAFE room in any floor must cause building's safe_to_submit = False.
    This is the conservative gate: one failure blocks the entire building.
    NFPA 72 §17.6.3 — triple-check gate must pass for every room.
    """
    # First: verify that a normal building is safe
    engine = BuildingEngine("SAFE-BLDG", optimizer)
    safe_floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
    }
    safe_report = engine.analyse(safe_floors)
    assert safe_report.safe_to_submit is True

    # Second: verify that a floor with a potentially unsafe room propagates
    # We test the logic directly: if any floor has safe_to_submit=False,
    # then building's safe_to_submit must be False
    engine2 = BuildingEngine("RISKY-BLDG", optimizer)
    risky_floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
        "B1": [
            # Thin corridor — often triggers fallback_used=True
            {"room_id": "thin_corridor", "name": "thin_corridor",
             "polygon_coords": [(0,0),(1,0),(1,50),(0,50)], "ceiling_height": 3.0},
        ],
    }
    risky_report = engine2.analyse(risky_floors)

    # If any floor is unsafe, building must be unsafe
    floor_unsafe = any(not fr.safe_to_submit for fr in risky_report.floor_reports)
    if floor_unsafe:
        assert risky_report.safe_to_submit is False, (
            "Building must be unsafe when a floor has unsafe rooms"
        )
        assert len(risky_report.unsafe_floors) > 0
        assert "B1" in risky_report.unsafe_floors

    # The safe floor must still be in floor_reports
    gf_report = [fr for fr in risky_report.floor_reports if fr.floor_id == "GF"][0]
    assert gf_report.safe_to_submit is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
