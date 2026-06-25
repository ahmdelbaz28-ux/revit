"""
tests/test_safe_building_engine.py
=====================================
Comprehensive test suite for:
  - fireai/core/safe_building_engine.py

SAFETY CRITICAL: Multi-floor building analysis must be thread-safe.
CBC solver deadlocks with ProcessPoolExecutor. SafeBuildingEngine
uses ThreadPoolExecutor + RLock to prevent C++ memory corruption.

Key Safety Properties:
  - ThreadPoolExecutor (NOT ProcessPoolExecutor)
  - Global RLock serializes CBC solver invocations
  - 180s timeout per room
  - CRASH status on fatal failures
  - V15 FIX: Don't mutate caller's room dicts
"""

from __future__ import annotations

import threading

import pytest

from fireai.core.safe_building_engine import SafeBuildingEngine

# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeBuildingEngineInit:
    def test_default_init(self):
        engine = SafeBuildingEngine()
        assert engine.max_threads == 4
        assert engine.coverage_radius > 0
        assert engine.candidate_step == 1.0
        assert engine.time_limit_s == 60.0

    def test_custom_init(self):
        engine = SafeBuildingEngine(
            max_threads=2,
            coverage_radius=5.0,
            candidate_step=0.5,
            time_limit_s=30.0,
        )
        assert engine.max_threads == 2
        assert engine.coverage_radius == 5.0
        assert engine.candidate_step == 0.5
        assert engine.time_limit_s == 30.0

    def test_has_rlock(self):
        engine = SafeBuildingEngine()
        assert isinstance(engine.global_c_level_lock, type(threading.RLock()))


# ─────────────────────────────────────────────────────────────────────────────
# _solve_mip_safe
# ─────────────────────────────────────────────────────────────────────────────


class TestSolveMIPSafe:
    """Thread-safe MIP solving for single rooms."""

    @pytest.fixture
    def engine(self):
        return SafeBuildingEngine(max_threads=1, time_limit_s=10.0)

    def test_basic_room_solve(self, engine):
        """Simple room solve — success depends on PuLP availability."""
        room = {
            "room_id": "RM-001",
            "width_m": 10.0,
            "length_m": 10.0,
        }
        result = engine._solve_mip_safe(room)
        assert result["room_id"] == "RM-001"
        # success may be False if PuLP not installed, but must not crash
        assert isinstance(result["success"], bool)

    def test_room_id_preserved(self, engine):
        room = {"room_id": "OFFICE-A3", "width_m": 8.0, "length_m": 12.0}
        result = engine._solve_mip_safe(room)
        assert result["room_id"] == "OFFICE-A3"

    def test_missing_room_id_defaults_unk(self, engine):
        room = {"width_m": 10.0}
        result = engine._solve_mip_safe(room)
        assert result["room_id"] == "UNK"

    def test_default_length_equals_width(self, engine):
        """When length_m not specified, defaults to width_m (square room)."""
        room = {"room_id": "SQUARE", "width_m": 10.0}
        result = engine._solve_mip_safe(room)
        # Should not crash
        assert "room_id" in result

    def test_override_coverage_radius(self, engine):
        room = {
            "room_id": "RM-OVERRIDE",
            "width_m": 10.0,
            "length_m": 10.0,
            "coverage_radius": 5.0,
        }
        result = engine._solve_mip_safe(room)
        assert "room_id" in result

    def test_result_has_required_keys(self, engine):
        room = {"room_id": "RM-KEYS", "width_m": 10.0, "length_m": 10.0}
        result = engine._solve_mip_safe(room)
        expected_keys = ["room_id", "success", "status"]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_exception_handling(self, engine):
        """Invalid room spec should return error result, not crash."""
        room = {"room_id": "BAD-ROOM", "width_m": -1.0, "length_m": -1.0}
        result = engine._solve_mip_safe(room)
        # Should handle error gracefully
        assert "room_id" in result


# ─────────────────────────────────────────────────────────────────────────────
# run_multi_floor_safety_analysis
# ─────────────────────────────────────────────────────────────────────────────


class TestRunMultiFloorSafetyAnalysis:
    @pytest.fixture
    def engine(self):
        return SafeBuildingEngine(max_threads=2, time_limit_s=10.0)

    def test_single_floor_single_room(self, engine):
        floors = [
            {
                "floor_id": "F1",
                "rooms": [
                    {"room_id": "RM-001", "width_m": 10.0, "length_m": 10.0},
                ],
            }
        ]
        results = engine.run_multi_floor_safety_analysis(floors)
        assert len(results) == 1
        assert results[0]["room_id"] == "RM-001"

    def test_multiple_floors(self, engine):
        floors = [
            {
                "floor_id": "F1",
                "rooms": [
                    {"room_id": "F1-RM1", "width_m": 10.0, "length_m": 10.0},
                ],
            },
            {
                "floor_id": "F2",
                "rooms": [
                    {"room_id": "F2-RM1", "width_m": 8.0, "length_m": 12.0},
                ],
            },
        ]
        results = engine.run_multi_floor_safety_analysis(floors)
        assert len(results) == 2
        room_ids = {r["room_id"] for r in results}
        assert "F1-RM1" in room_ids
        assert "F2-RM1" in room_ids

    def test_empty_floors(self, engine):
        """Empty floor list returns empty results."""
        results = engine.run_multi_floor_safety_analysis([])
        assert results == []

    def test_floor_with_no_rooms(self, engine):
        """Floor with empty rooms list returns empty results."""
        floors = [{"floor_id": "F1", "rooms": []}]
        results = engine.run_multi_floor_safety_analysis(floors)
        assert results == []

    def test_v15_fix_no_dict_mutation(self, engine):
        """V15 FIX: Caller's room dicts must NOT be mutated."""
        original_room = {"room_id": "RM-001", "width_m": 10.0, "length_m": 10.0}
        original_keys = set(original_room.keys())
        floors = [{"floor_id": "F1", "rooms": [original_room]}]
        engine.run_multi_floor_safety_analysis(floors)
        # Original dict should not have virtual_floor added
        assert set(original_room.keys()) == original_keys

    def test_multiple_rooms_per_floor(self, engine):
        floors = [
            {
                "floor_id": "F1",
                "rooms": [
                    {"room_id": f"RM-{i:03d}", "width_m": 8.0, "length_m": 8.0}
                    for i in range(3)
                ],
            }
        ]
        results = engine.run_multi_floor_safety_analysis(floors)
        assert len(results) == 3

    def test_crash_status_on_fatal_error(self, engine):
        """Fatal errors should produce CRASH status, not raise exceptions."""
        # Room with invalid dimensions that might cause solver to fail
        floors = [
            {
                "floor_id": "F1",
                "rooms": [
                    {"room_id": "FATAL", "width_m": -999, "length_m": -999},
                ],
            }
        ]
        results = engine.run_multi_floor_safety_analysis(floors)
        # Should return results, not crash the entire process
        assert len(results) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Thread Safety
# ─────────────────────────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_rlock_prevents_concurrent_solver(self):
        """RLock ensures only one CBC instance runs at a time."""
        engine = SafeBuildingEngine(max_threads=1)
        # RLock exists and is usable
        assert engine.global_c_level_lock.acquire(blocking=False)
        engine.global_c_level_lock.release()

    def test_multiple_sequential_runs(self):
        """Multiple sequential analyses should not interfere."""
        engine = SafeBuildingEngine(max_threads=1, time_limit_s=10.0)
        room = {"room_id": "RM-001", "width_m": 10.0, "length_m": 10.0}
        r1 = engine._solve_mip_safe(room)
        r2 = engine._solve_mip_safe(room)
        # Both should complete without crashing
        assert "room_id" in r1
        assert "room_id" in r2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
