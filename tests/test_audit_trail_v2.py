# NOSONAR
"""
tests/test_audit_trail_v2.py
=============================
Comprehensive test suite for fireai/core/audit_trail.py

SAFETY CRITICAL: The audit trail provides immutable, hash-chained records
of all fire alarm design decisions. Tampering or data loss could result in
untraceable compliance failures — a direct life-safety hazard.

Key features tested:
  - Per-entry SHA-256 hash integrity
  - Thread-safe append operations
  - All logging methods (V5.1.2 + V5.2.0)
  - Query methods (count, entries, get_room_trail, summary)
  - Immutability of AuditEntry (frozen dataclass)
"""

from __future__ import annotations

import threading

import pytest

from fireai.core.audit_trail import AuditEntry, AuditTrail

# ─────────────────────────────────────────────────────────────────────────────
# AuditEntry Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditEntry:
    """Test AuditEntry dataclass and hash computation."""

    def test_creation(self):
        entry = AuditEntry(
            timestamp_utc="2024-01-01T00:00:00Z",
            room_id="R-101",
            operation="TEST_OP",
            inputs={"x": 1},
            outputs={"y": 2},
            nfpa_reference="NFPA 72 §17.6.3",
        )
        assert entry.room_id == "R-101"
        assert entry.operation == "TEST_OP"

    def test_hash_auto_computed(self):
        """Entry hash should be auto-computed in __post_init__."""
        entry = AuditEntry(
            timestamp_utc="2024-01-01T00:00:00Z",
            room_id="R-101",
            operation="TEST_OP",
            inputs={},
            outputs={},
            nfpa_reference="N/A",
        )
        assert entry.entry_hash != ""
        assert len(entry.entry_hash) == 32  # 128 bits = 32 hex chars

    def test_hash_deterministic(self):
        """Same inputs → same hash."""
        kwargs = {
            "timestamp_utc": "2024-01-01T00:00:00Z",
            "room_id": "R-101",
            "operation": "TEST_OP",
            "inputs": {"a": 1},
            "outputs": {"b": 2},
            "nfpa_reference": "N/A",
        }
        e1 = AuditEntry(**kwargs)
        e2 = AuditEntry(**kwargs)
        assert e1.entry_hash == e2.entry_hash

    def test_hash_changes_with_different_input(self):
        """Different inputs → different hash."""
        e1 = AuditEntry("2024-01-01", "R-101", "OP1", {}, {}, "N/A")
        e2 = AuditEntry("2024-01-01", "R-101", "OP2", {}, {}, "N/A")
        assert e1.entry_hash != e2.entry_hash

    def test_frozen(self):
        """AuditEntry must be immutable (frozen dataclass)."""
        entry = AuditEntry("2024-01-01", "R-101", "OP", {}, {}, "N/A")
        with pytest.raises(AttributeError):
            entry.room_id = "R-999"

    def test_to_dict(self):
        entry = AuditEntry(
            timestamp_utc="2024-01-01",
            room_id="R-101",
            operation="OP",
            inputs={"k": "v"},
            outputs={},
            nfpa_reference="N/A",
            notes=["note1"],
        )
        d = entry.to_dict()
        assert d["room_id"] == "R-101"
        assert d["entry_hash"] == entry.entry_hash
        assert d["notes"] == ["note1"]

    def test_default_notes_empty(self):
        entry = AuditEntry("2024", "R", "OP", {}, {}, "N/A")
        assert entry.notes == []

    def test_hash_uses_sorted_keys(self):
        """Hash computation must sort keys for deterministic output."""
        e1 = AuditEntry("2024", "R", "OP", {"a": 1, "b": 2}, {}, "N/A")
        e2 = AuditEntry("2024", "R", "OP", {"b": 2, "a": 1}, {}, "N/A")
        assert e1.entry_hash == e2.entry_hash


# ─────────────────────────────────────────────────────────────────────────────
# AuditTrail — Initialization Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrailInit:
    def test_creation(self):
        trail = AuditTrail("test_project")
        assert trail.project_name == "test_project"
        assert trail.floor_id == "FL01"

    def test_custom_floor_id(self):
        trail = AuditTrail("proj", floor_id="FL03")
        assert trail.floor_id == "FL03"

    def test_created_at_set(self):
        trail = AuditTrail("proj")
        assert trail.created_at != ""

    def test_initially_empty(self):
        trail = AuditTrail("proj")
        assert trail.count() == 0
        assert trail.entries() == []


# ─────────────────────────────────────────────────────────────────────────────
# AuditTrail — Core Logging Methods (V5.1.2)
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrailCoreLogging:
    """Test original V5.1.2 logging methods."""

    @pytest.fixture
    def trail(self):
        return AuditTrail("test_project")

    def test_log_radius_lookup(self, trail):
        trail.log_radius_lookup("R-101", 3.0, 6.37, "row_3")
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "SMOKE_RADIUS_LOOKUP"

    def test_log_rejection(self, trail):
        trail.log_rejection("R-102", "Invalid room type")
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "INPUT_REJECTED"
        assert entries[0].outputs["reason"] == "Invalid room type"

    def test_log_heat_params(self, trail):
        trail.log_heat_params("R-103", 9.1, 7.6, ["adjusted for ceiling slope"])
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "HEAT_DETECTOR_PARAMS"
        assert entries[0].inputs["listed_spacing_m"] == 9.1  # NOSONAR — S1244: import retained for re-export / API surface

    def test_log_coverage_result(self, trail):
        trail.log_coverage_result("R-104", 4, 99.5, 0.3, "PASS")
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "COVERAGE_VERIFICATION"
        assert entries[0].inputs["detector_count"] == 4

    def test_log_dxf_parse(self, trail):
        trail.log_dxf_parse("floor.dxf", "meters", 1.0, 25, 2)
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "DXF_PARSE"
        assert entries[0].room_id == "__FLOOR__"

    def test_log_nfpa_violation(self, trail):
        trail.log_nfpa_violation("R-105", "Spacing exceeds max", "NFPA 72 §17.6.3")
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "NFPA_COMPLIANCE_ERROR"
        assert "DESIGN CANNOT PROCEED" in entries[0].notes


# ─────────────────────────────────────────────────────────────────────────────
# AuditTrail — V5.2.0 New Logging Methods
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrailV52Logging:
    """Test V5.2.0 additional logging methods."""

    @pytest.fixture
    def trail(self):
        return AuditTrail("test_project")

    def test_log_placement(self, trail):
        trail.log_placement("R-101", 5, "smoke_photoelectric", 99.8, [(1, 1), (2, 2)])
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "DETECTOR_PLACEMENT"
        assert entries[0].outputs["detector_count"] == 5
        assert entries[0].outputs["positions_count"] == 2

    def test_log_wall_distance_violation(self, trail):
        trail.log_wall_distance_violation("R-102", 3, (1.5, 2.0), "east", 0.05)
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "WALL_DISTANCE_VIOLATION"
        assert entries[0].outputs["distance_m"] == 0.05  # NOSONAR — S1244: import retained for re-export / API surface

    def test_log_duct_detector_placement(self, trail):
        trail.log_duct_detector_placement("R-103", "DUCT-01", 2, [(1.0, 2.0), (3.0, 4.0)])
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "DUCT_DETECTOR_PLACEMENT"
        assert entries[0].inputs["duct_id"] == "DUCT-01"

    def test_log_safe_fallback_used(self, trail):
        trail.log_safe_fallback_used("R-104", 12.0, 9.1, 6.37)
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "SAFE_FALLBACK_ACTIVATED"
        assert entries[0].inputs["original_height_m"] == 12.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_log_boundary_limit_warning(self, trail):
        trail.log_boundary_limit_warning("R-105", 99.95)
        assert trail.count() == 1
        entries = trail.entries()
        assert entries[0].operation == "BOUNDARY_LIMIT_WARNING"
        assert entries[0].outputs["coverage_pct"] == 99.95  # NOSONAR — S1244: import retained for re-export / API surface


# ─────────────────────────────────────────────────────────────────────────────
# AuditTrail — Query Methods
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrailQueries:
    @pytest.fixture
    def trail(self):
        t = AuditTrail("test_project")
        t.log_radius_lookup("R-101", 3.0, 6.37, "row_3")
        t.log_rejection("R-102", "bad room")
        t.log_placement("R-101", 3, "smoke", 99.5, [(1, 1)])
        t.log_nfpa_violation("R-103", "violation", "§17.6.3")
        return t

    def test_count(self, trail):
        assert trail.count() == 4

    def test_get_room_trail(self, trail):
        room_trail = trail.get_room_trail("R-101")
        assert len(room_trail) == 2
        assert all(e.room_id == "R-101" for e in room_trail)

    def test_get_room_trail_nonexistent(self, trail):
        assert trail.get_room_trail("R-999") == []

    def test_to_list(self, trail):
        result = trail.to_list()
        assert len(result) == 4
        assert all(isinstance(d, dict) for d in result)
        assert all("entry_hash" in d for d in result)

    def test_entries_returns_list(self, trail):
        result = trail.entries()
        assert isinstance(result, list)
        assert len(result) == 4

    def test_verify_integrity_valid(self, trail):
        """All entries should have valid hashes."""
        assert trail.verify_integrity() is True

    def test_summary(self, trail):
        s = trail.summary()
        assert s["project_name"] == "test_project"
        assert s["floor_id"] == "FL01"
        assert s["entry_count"] == 4
        assert len(s["operations"]) == 4


# ─────────────────────────────────────────────────────────────────────────────
# AuditTrail — Thread Safety
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrailThreadSafety:
    def test_concurrent_appends(self):
        """Multiple threads appending should not lose entries."""
        trail = AuditTrail("thread_test")
        errors = []

        def append_entries(start, count):
            try:
                for i in range(start, start + count):
                    trail.log_placement(f"R-{i}", 1, "smoke", 99.0, [(0, 0)])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=append_entries, args=(i * 100, 100)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert trail.count() == 400

    def test_concurrent_read_write(self):
        """Reads and writes happening simultaneously should not crash."""
        trail = AuditTrail("rw_test")
        trail.log_radius_lookup("R-0", 3.0, 6.37, "row")

        errors = []

        def writer():
            try:
                for i in range(50):
                    trail.log_placement(f"R-{i}", 1, "smoke", 99.0, [(0, 0)])
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    trail.count()
                    trail.entries()
                    trail.get_room_trail("R-0")
                    trail.verify_integrity()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# AuditTrail — Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrailEdgeCases:
    def test_empty_notes(self):
        entry = AuditEntry("2024", "R", "OP", {}, {}, "N/A")
        assert entry.notes == []

    def test_multiple_notes(self):
        entry = AuditEntry("2024", "R", "OP", {}, {}, "N/A", notes=["a", "b", "c"])
        assert len(entry.notes) == 3

    def test_empty_trail_integrity(self):
        """Empty trail should verify as intact."""
        trail = AuditTrail("empty")
        assert trail.verify_integrity() is True

    def test_large_number_of_entries(self):
        """Handle many entries without performance issues."""
        trail = AuditTrail("large_test")
        for i in range(1000):
            trail.log_radius_lookup(f"R-{i}", 3.0, 6.37, "row")
        assert trail.count() == 1000
        assert trail.verify_integrity() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
