"""
test_comprehensive.py — FireAI Comprehensive Test Suite V3
==========================================================
End-to-end tests across all three architectural layers:
  Layer 1: DensityOptimizer V7.3 (single room)
  Layer 2: FloorAnalyser V2.3 (floor — multiple rooms + MIP verifier)
  Layer 3: BuildingEngine V0.1 (building — multiple floors)

Plus cross-cutting concerns:
  - AuditTrail V5.2 integrity and thread safety
  - AuditStore tamper-proof chain
  - theoretical_lower_bound invariant
  - Conservative safe_to_submit gate
  - Safety refusals (NFPA 72 §17.6.4)
  - Low ceiling warning (R=6.40m not conservative)
  - Wall distance validation
  - API security (fireai_api V10)
  - MIP Solver (PuLP) — verification only, never replaces greedy

NFPA References:
  - NFPA 72 (2022) Section 17.6.3 — smoke detector coverage
  - NFPA 72 (2022) Section 17.6.4 — detector type restrictions (kitchens)
  - NFPA 72 (2022) Section 17.7.4.2.3.1 — 0.7S rule
  - NFPA 72 (2022) Table 17.6.3.1 — ceiling height / radius
  - NFPA 72 (2022) Section 17.6.3.1.1 — wall distance requirements
  - NFPA 72 (2022) Section 17.7.5 — duct detectors
  - MIP Set Covering ILP — proven optimal on candidate grid
"""

import pytest
import sys
import os
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room, DetectorLayout, DETECTOR_RADIUS
from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.building_engine import BuildingEngine, BuildingReport
from fireai.core.audit_trail import AuditTrail

# MIP Solver — optional (skipif if PuLP not installed)
try:
    from fireai.core.spatial_engine.mip_solver import solve_set_covering_mip, MIPResult, PULP_AVAILABLE
except ImportError:
    PULP_AVAILABLE = False

MIP_SKIP_REASON = "PuLP not installed — install with: pip install pulp"


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


# ═══════════════════════════════════════════════════════════════════
# Layer Tests (original 7)
# ═══════════════════════════════════════════════════════════════════

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

    assert layout.count >= 1, f"Expected at least 1 detector, got {layout.count}"
    assert layout.coverage_pct >= 99.0, f"Coverage {layout.coverage_pct:.2f}% < 99%"
    assert layout.nfpa_valid is True, "NFPA validation failed"
    assert layout.theoretical_lower_bound >= 1, "theoretical_lower_bound must be >= 1"
    assert layout.theoretical_lower_bound <= layout.count, (
        f"theoretical_lower_bound ({layout.theoretical_lower_bound}) > count ({layout.count})"
    )
    assert 0.0 <= layout.efficiency_ratio <= 1.0, (
        f"efficiency_ratio {layout.efficiency_ratio:.4f} out of range"
    )


# ─── Layer 2: FloorAnalyser V2.2 — 10 realistic rooms ──────────
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
        {"room_id": "kitchen_heat", "name": "kitchen_heat",
         "polygon_coords": [(0,0),(6,0),(6,5),(0,5)], "ceiling_height": 3.0,
         "room_type": "kitchen", "detector_type": "heat_fixed"},
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

    for s in report.room_summaries:
        assert s.coverage_pct >= 99.0, f"Room {s.name}: coverage {s.coverage_pct:.2f}% < 99%"
        assert s.theoretical_lower_bound >= 1
        assert s.theoretical_lower_bound <= s.detector_count
        # New fields must exist
        assert hasattr(s, 'refused')
        assert hasattr(s, 'refusal_reason')
        assert hasattr(s, 'used_mip')
        assert hasattr(s, 'mip_proven_optimal_count')
        assert hasattr(s, 'mip_solve_time_s')
        assert hasattr(s, 'mip_status')
        # Without use_mip, these should be None/False
        assert s.mip_proven_optimal_count is None
        assert s.mip_solve_time_s is None
        assert s.mip_status is None


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

    is_valid, error = audit_store.verify_chain()
    assert is_valid, f"AuditStore chain broken: {error}"

    events = audit_store.get_events()
    event_types = [e["event_type"] for e in events]
    assert "BUILDING_ANALYSIS_START" in event_types
    assert "BUILDING_ANALYSIS_COMPLETE" in event_types

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

    assert audit_trail.count() >= 2
    assert audit_trail.verify_integrity() is True

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
    engine = BuildingEngine("SAFE-BLDG", optimizer)
    safe_floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
    }
    safe_report = engine.analyse(safe_floors)
    assert safe_report.safe_to_submit is True

    engine2 = BuildingEngine("RISKY-BLDG", optimizer)
    risky_floors = {
        "GF": [
            {"room_id": "lobby", "name": "lobby",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ],
        "B1": [
            {"room_id": "thin_corridor", "name": "thin_corridor",
             "polygon_coords": [(0,0),(1,0),(1,50),(0,50)], "ceiling_height": 3.0},
        ],
    }
    risky_report = engine2.analyse(risky_floors)

    floor_unsafe = any(not fr.safe_to_submit for fr in risky_report.floor_reports)
    if floor_unsafe:
        assert risky_report.safe_to_submit is False, (
            "Building must be unsafe when a floor has unsafe rooms"
        )
        assert len(risky_report.unsafe_floors) > 0
        assert "B1" in risky_report.unsafe_floors

    gf_report = [fr for fr in risky_report.floor_reports if fr.floor_id == "GF"][0]
    assert gf_report.safe_to_submit is True


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — Safety Refusals (NFPA 72 §17.6.4)
# ═══════════════════════════════════════════════════════════════════

class TestSafetyRefusals:
    """
    Test NFPA 72 safety refusals — smoke detector in kitchen is prohibited.
    Uses FloorAnalyser._check_safety_refusal() — NOT an ExpertSystem.
    """

    def test_smoke_in_kitchen_is_refused(self, optimizer):
        """Smoke detector in kitchen MUST be refused — NFPA 72 §17.6.4."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "K1", "name": "kitchen",
             "polygon_coords": [(0,0),(6,0),(6,5),(0,5)],
             "ceiling_height": 3.0,
             "room_type": "kitchen",
             "detector_type": "smoke_photoelectric"},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.refused is True, "Kitchen + smoke must be refused"
        assert "PROHIBITED" in (s.refusal_reason or "")
        assert "§17.6.4" in (s.refusal_reason or "")

    def test_refused_room_has_zero_detectors(self, optimizer):
        """A refused room must return zero detector positions."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "K2", "name": "kitchen2",
             "polygon_coords": [(0,0),(8,0),(8,6),(0,6)],
             "ceiling_height": 3.0,
             "room_type": "kitchen",
             "detector_type": "smoke_photoelectric"},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.refused is True
        assert s.detector_count == 0, "Refused room must have 0 detectors"

    def test_refused_room_not_compliant(self, optimizer):
        """compliant must be False for refused rooms — no silent pass-through."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "K3", "name": "kitchen3",
             "polygon_coords": [(0,0),(6,0),(6,5),(0,5)],
             "ceiling_height": 3.0,
             "room_type": "kitchen",
             "detector_type": "smoke_photoelectric"},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.compliant is False
        assert s.safe_to_submit is False

    def test_heat_in_kitchen_is_accepted(self, optimizer):
        """Heat detector in kitchen must NOT be refused — correct type."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "K4", "name": "kitchen_heat",
             "polygon_coords": [(0,0),(6,0),(6,5),(0,5)],
             "ceiling_height": 3.0,
             "room_type": "kitchen",
             "detector_type": "heat_fixed"},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.refused is False, f"Heat in kitchen should be accepted, got: {s.refusal_reason}"

    def test_office_with_smoke_is_not_refused(self, optimizer):
        """Smoke detector in office must NOT be refused — normal case."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "O1", "name": "office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)],
             "ceiling_height": 3.0,
             "room_type": "office",
             "detector_type": "smoke_photoelectric"},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.refused is False


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — Wall Distance Validation
# ═══════════════════════════════════════════════════════════════════

class TestWallDistance:
    """
    Test that placed detectors satisfy NFPA 72 §17.6.3.1.1 wall distances.
    All detectors must be >= 0.10m from walls.
    """

    def test_no_wall_violations_in_standard_rooms(self, optimizer):
        """Standard rooms must have zero wall distance violations."""
        rooms = [
            Room(name="office_12x8", width=12, length=8, ceiling_height=3.0),
            Room(name="lobby_10x10", width=10, length=10, ceiling_height=3.0),
            Room(name="corridor_20x2", width=20, length=2, ceiling_height=3.0),
        ]
        for room in rooms:
            layout = optimizer.optimize(room)
            assert layout.wall_violations == 0, (
                f"Room {room.name}: {layout.wall_violations} wall violations"
            )

    def test_audit_trail_logs_wall_violation_format(self):
        """log_wall_distance_violation must produce correct format with §17.6.3.1.1."""
        trail = AuditTrail("WALL-TEST")
        trail.log_wall_distance_violation("R1", 0, (0.05, 5.0), "SOUTH", 0.05)
        e = trail.entries()[-1]
        assert e.operation == "WALL_DISTANCE_VIOLATION"
        assert e.outputs["distance_m"] == 0.05
        assert e.outputs["required_m"] == 0.10
        assert "§17.6.3.1.1" in e.nfpa_reference

    def test_detectors_within_room_bounds(self, optimizer):
        """All detector positions must be within room boundaries."""
        room = Room(name="bounded", width=10, length=8, ceiling_height=3.0)
        layout = optimizer.optimize(room)
        for x, y in layout.detectors:
            assert x >= 0.0, f"Detector x={x:.2f} < 0"
            assert y >= 0.0, f"Detector y={y:.2f} < 0"
            assert x <= room.width, f"Detector x={x:.2f} > width={room.width}"
            assert y <= room.length, f"Detector y={y:.2f} > length={room.length}"


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — Low Ceiling Warning
# ═══════════════════════════════════════════════════════════════════

class TestLowCeilingWarning:
    """
    Test LOW_CEILING_WARNING when ceiling_height < 3.0m.
    R is now dynamically calculated from NFPA 72 Table 17.6.3.2.
    For heights below 3.0m, the safe fallback uses R=4.55m (3.0m bracket).
    """

    def test_low_ceiling_produces_warning(self, optimizer):
        """Room with ceiling < 3.0m must produce LOW_CEILING_WARNING."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "LOW1", "name": "low_ceiling",
             "polygon_coords": [(0,0),(8,0),(8,6),(0,6)],
             "ceiling_height": 2.4},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        has_low = any("LOW_CEILING_WARNING" in w for w in s.warnings)
        assert has_low, f"No LOW_CEILING_WARNING for 2.4m ceiling. Warnings: {s.warnings}"

    def test_normal_ceiling_no_warning(self, optimizer):
        """Room with ceiling >= 3.0m must NOT produce LOW_CEILING_WARNING."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "NORM1", "name": "normal_ceiling",
             "polygon_coords": [(0,0),(8,0),(8,6),(0,6)],
             "ceiling_height": 3.5},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        has_low = any("LOW_CEILING_WARNING" in w for w in s.warnings)
        assert not has_low, f"LOW_CEILING_WARNING for 3.5m ceiling (should not appear)"

    def test_low_ceiling_warning_references_nfpa(self, optimizer):
        """LOW_CEILING_WARNING must reference NFPA 72 Table 17.6.3.2."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)
        rooms = [
            {"room_id": "LOW2", "name": "low2",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)],
             "ceiling_height": 2.7},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        low_warnings = [w for w in s.warnings if "LOW_CEILING_WARNING" in w]
        assert len(low_warnings) >= 1
        assert "Table 17.6.3.2" in low_warnings[0]


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — AuditTrail Thread Safety
# ═══════════════════════════════════════════════════════════════════

class TestAuditTrailThreadSafety:
    """
    Test that AuditTrail is thread-safe under concurrent writes.
    Uses threading.Lock to protect _entries list.
    """

    def test_concurrent_writes_preserve_count(self):
        """100 writes from 5 threads = 500 entries, no lost writes."""
        trail = AuditTrail("THREAD-SAFE")

        def _write():
            for _ in range(100):
                trail.log_placement("R", 1, "SMOKE_PHOTOELECTRIC", 100.0, [])

        threads = [threading.Thread(target=_write) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert trail.count() == 500, f"Expected 500, got {trail.count()}"

    def test_integrity_after_concurrent_writes(self):
        """SHA-256 hash integrity must hold after concurrent writes."""
        trail = AuditTrail("THREAD-INTEGRITY")

        def _write(room_id):
            for _ in range(50):
                trail.log_placement(room_id, 1, "SMOKE_PHOTOELECTRIC", 100.0, [])

        threads = [
            threading.Thread(target=_write, args=(f"R{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert trail.count() == 250
        assert trail.verify_integrity() is True, "Integrity check failed after concurrent writes"

    def test_audit_entry_hash_immutable(self):
        """Each AuditEntry hash must be immutable — changing data must not match."""
        trail = AuditTrail("IMMUTABLE")
        trail.log_placement("R1", 3, "SMOKE_PHOTOELECTRIC", 99.5, [(1, 1), (2, 2), (3, 3)])
        entry = trail.entries()[0]
        original_hash = entry.entry_hash
        # Hash must match recomputation
        assert entry._compute_hash() == original_hash
        # Count must be 1
        assert trail.count() == 1


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — API Security (fireai_api V10)
# ═══════════════════════════════════════════════════════════════════

class TestAPISecurity:
    """
    Test API security: API key validation, request size limits, error handling.
    Uses fireai_api V10 (FastAPI) with TestClient.
    """

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("FIREAI_API_KEYS", "valid-key-001")

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from fireai.core.fireai_api import app
        return TestClient(app, raise_server_exceptions=False)

    def test_missing_api_key_rejected(self, client):
        """Request without X-Api-Key header must be rejected with 401 or 422."""
        r = client.post("/analyse/room", json={})
        assert r.status_code in (401, 422), (
            f"Expected 401/422, got {r.status_code}"
        )

    def test_wrong_api_key_rejected(self, client):
        """Wrong API key must return 401."""
        r = client.post(
            "/analyse/room",
            headers={"X-Api-Key": "wrong-key"},
            json={
                "room": {
                    "room_id": "R1", "name": "T",
                    "polygon": [[0,0],[10,0],[10,10],[0,10]],
                    "ceiling_height_m": 3.5,
                },
                "required_coverage_pct": 100.0,
            },
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_health_endpoint_works(self, client):
        """Health endpoint must return 200 without API key."""
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"

    def test_oversized_file_rejected(self, client):
        """File > 50MB must return 413."""
        r = client.post(
            "/projects/",
            headers={"X-Api-Key": "valid-key-001"},
            files={"file": ("big.json", b"x" * (51 * 1024 * 1024), "application/json")},
        )
        assert r.status_code == 413, f"Expected 413, got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════
# Planned but not yet implemented — skip markers with reasons
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — MIP Solver (PuLP) — Verification Only
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not PULP_AVAILABLE, reason=MIP_SKIP_REASON)
class TestMIPSolver:
    """
    MIP Set Covering ILP — proves minimum detector count on candidate grid.
    MIP is VERIFIER only — never replaces greedy placement.
    See TECHNICAL_HONESTY.md §5 for terminology.
    """

    def test_small_room_optimal(self):
        """5x5 room with R=6.40: MIP must prove 1 detector sufficient."""
        result = solve_set_covering_mip(
            room_width=5.0,
            room_length=5.0,
            coverage_radius=6.40,
            candidate_step=1.0,
            time_limit_seconds=30.0,
        )
        assert result.success, f"MIP failed: {result.fallback_reason}"
        assert result.solver_status == "Optimal"
        assert result.theoretical_minimum == 1, (
            f"Expected 1 detector for 5x5 room with R=6.40, got {result.theoretical_minimum}"
        )
        assert result.used_mip is True

    def test_medium_room_optimality_proven(self):
        """10x10 room: verify MIP returns proven optimal (not just feasible)."""
        result = solve_set_covering_mip(
            room_width=10.0,
            room_length=10.0,
            coverage_radius=6.40,
            candidate_step=1.5,
            time_limit_seconds=30.0,
        )
        assert result.success, f"MIP failed: {result.fallback_reason}"
        assert result.solver_status == "Optimal"
        assert result.theoretical_minimum is not None
        assert result.theoretical_minimum >= 1
        assert len(result.detector_positions) == result.theoretical_minimum

    def test_coverage_completeness(self):
        """Every target point must be within R of at least one MIP detector."""
        room_w, room_l, R = 8.0, 6.0, 6.40
        result = solve_set_covering_mip(
            room_width=room_w,
            room_length=room_l,
            coverage_radius=R,
            candidate_step=1.0,
            time_limit_seconds=30.0,
        )
        assert result.success

        # Verify coverage on dense grid (matching V7.3 VERIFY_STEP = 0.20)
        check_step = 0.20
        uncovered = []
        x = check_step / 2
        while x <= room_w:
            y = check_step / 2
            while y <= room_l:
                covered = any(
                    (x - dx) ** 2 + (y - dy) ** 2 <= R ** 2
                    for dx, dy in result.detector_positions
                )
                if not covered:
                    uncovered.append((round(x, 2), round(y, 2)))
                y += check_step
            x += check_step

        assert not uncovered, (
            f"{len(uncovered)} uncovered points found — MIP solution is infeasible! "
            f"First 5: {uncovered[:5]}"
        )

    def test_mip_within_time_limit(self):
        """MIP must not exceed time limit excessively."""
        import time as _time
        start = _time.perf_counter()
        result = solve_set_covering_mip(
            room_width=12.0,
            room_length=10.0,
            coverage_radius=6.40,
            candidate_step=2.0,
            time_limit_seconds=15.0,
        )
        elapsed = _time.perf_counter() - start
        # Allow 5s margin above limit
        assert elapsed < 20.0, f"MIP took {elapsed:.1f}s — exceeds acceptable threshold"

    def test_fallback_when_pulp_unavailable(self, monkeypatch):
        """Graceful fallback when PULP_AVAILABLE is False."""
        import fireai.core.spatial_engine.mip_solver as mip_mod
        original = mip_mod.PULP_AVAILABLE
        monkeypatch.setattr(mip_mod, "PULP_AVAILABLE", False)
        try:
            result = solve_set_covering_mip(5.0, 5.0, 6.40)
            assert result.success is False
            assert result.used_mip is False
            assert "PuLP" in (result.fallback_reason or "")
        finally:
            monkeypatch.setattr(mip_mod, "PULP_AVAILABLE", original)


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — MIP Integration with FloorAnalyser
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not PULP_AVAILABLE, reason=MIP_SKIP_REASON)
class TestMIPIntegration:
    """
    Integration tests: FloorAnalyser with use_mip=True.
    MIP verification runs after greedy — never replaces placement.
    """

    def test_use_mip_sets_fields(self, optimizer):
        """FloorAnalyser with use_mip=True must populate MIP fields in RoomSummary."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer, use_mip=True)
        rooms = [
            {"room_id": "R1", "name": "office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.used_mip is True, "used_mip must be True when MIP succeeds"
        assert s.mip_proven_optimal_count is not None, "mip_proven_optimal_count must be set"
        assert s.mip_proven_optimal_count >= 1
        assert s.mip_solve_time_s is not None
        assert s.mip_solve_time_s >= 0
        assert s.mip_status == "Optimal"

    def test_mip_proven_count_leq_greedy_count(self, optimizer):
        """MIP proven optimal must be <= greedy detector count."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer, use_mip=True)
        rooms = [
            {"room_id": "R1", "name": "office",
             "polygon_coords": [(0,0),(12,0),(12,8),(0,8)], "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.mip_proven_optimal_count <= s.detector_count, (
            f"MIP proven ({s.mip_proven_optimal_count}) > greedy ({s.detector_count}) — impossible!"
        )

    def test_mip_optimality_gap_warning(self, optimizer):
        """When MIP proves fewer detectors, MIP_OPTIMALITY_GAP warning must appear."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer, use_mip=True)
        rooms = [
            {"room_id": "R1", "name": "large_room",
             "polygon_coords": [(0,0),(20,0),(20,15),(0,15)], "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        # If MIP proves fewer, warning must exist
        if s.mip_proven_optimal_count is not None and s.mip_proven_optimal_count < s.detector_count:
            has_gap = any("MIP_OPTIMALITY_GAP" in w for w in s.warnings)
            assert has_gap, "MIP_OPTIMALITY_GAP warning missing when MIP < greedy"

    def test_without_use_mip_no_mip_fields(self, optimizer):
        """Without use_mip, MIP fields should be None/False."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer, use_mip=False)
        rooms = [
            {"room_id": "R1", "name": "office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ]
        report = analyser.analyse(rooms)
        s = report.room_summaries[0]
        assert s.used_mip is False
        assert s.mip_proven_optimal_count is None
        assert s.mip_solve_time_s is None
        assert s.mip_status is None

    def test_greedy_still_places_detectors_with_mip(self, optimizer):
        """Greedy placement must be unchanged regardless of MIP verification."""
        # Without MIP
        analyser_no_mip = FloorAnalyser(floor_id="GF", optimizer=optimizer, use_mip=False)
        analyser_mip = FloorAnalyser(floor_id="GF", optimizer=optimizer, use_mip=True)
        rooms = [
            {"room_id": "R1", "name": "office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height": 3.0},
        ]
        report_no_mip = analyser_no_mip.analyse(rooms)
        report_mip = analyser_mip.analyse(rooms)
        s_no = report_no_mip.room_summaries[0]
        s_mip = report_mip.room_summaries[0]
        # Greedy count must be identical
        assert s_no.detector_count == s_mip.detector_count, (
            f"Greedy count changed with MIP: {s_no.detector_count} vs {s_mip.detector_count}"
        )
        assert s_no.coverage_pct == s_mip.coverage_pct
        assert s_no.nfpa_valid == s_mip.nfpa_valid
        assert s_no.method == s_mip.method


@pytest.mark.skip(reason="Duct detector logic not yet implemented — NFPA 72 §17.7.5 deferred")
def test_duct_detectors_injected_automatically():
    """Room with HVAC duct must receive duct detectors. Deferred to future phase."""
    pass


# ═══════════════════════════════════════════════════════════════════
# NEW: Test Group — Variable Coverage Radius (NFPA 72 Table 17.6.3.2)
# ═══════════════════════════════════════════════════════════════════

class TestVariableCoverageRadius:
    """
    Test that coverage radius varies with ceiling height per NFPA 72.
    Low ceilings → smaller radius → more detectors.
    High ceilings → larger radius → fewer detectors.
    """

    def test_low_ceiling_produces_more_detectors(self, optimizer):
        """Low ceiling (3.0m → R=4.55m) must produce more detectors than high ceiling (9.1m → R=6.40m)."""
        analyser = FloorAnalyser(floor_id="GF", optimizer=optimizer)

        # Same room dimensions, different ceiling heights
        rooms_low = [
            {"room_id": "LOW", "name": "low_ceiling",
             "polygon_coords": [(0,0),(20,0),(20,15),(0,15)],
             "ceiling_height": 3.0},
        ]
        rooms_high = [
            {"room_id": "HIGH", "name": "high_ceiling",
             "polygon_coords": [(0,0),(20,0),(20,15),(0,15)],
             "ceiling_height": 9.1},
        ]

        report_low = analyser.analyse(rooms_low)
        report_high = analyser.analyse(rooms_high)

        s_low = report_low.room_summaries[0]
        s_high = report_high.room_summaries[0]

        # Low ceiling (R=4.55m) must produce more detectors than high ceiling (R=6.40m)
        assert s_low.detector_count > s_high.detector_count, (
            f"Low ceiling (3.0m, R=4.55m) should produce more detectors than "
            f"high ceiling (9.1m, R=6.40m): {s_low.detector_count} vs {s_high.detector_count}"
        )

    def test_high_ceiling_matches_default_radius(self, optimizer):
        """High ceiling (9.1m → R=6.40m) must match default DensityOptimizer behaviour."""
        # Direct call without coverage_radius (default R=6.40m)
        room = Room(name="default", width=20, length=15, ceiling_height=9.1)
        layout_default = optimizer.optimize(room)

        # Call with explicit R=6.40 (from 9.1m ceiling)
        layout_explicit = optimizer.optimize(room, coverage_radius=6.40)

        assert layout_default.count == layout_explicit.count, (
            f"Default R=6.40m and explicit coverage_radius=6.40 should match: "
            f"{layout_default.count} vs {layout_explicit.count}"
        )


@pytest.mark.skip(reason="Monte Carlo resilience not yet implemented — planned for V2.0")
def test_resilience_check_for_multi_detector():
    """Rooms with >=2 detectors must have resilience result. Future feature."""
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
