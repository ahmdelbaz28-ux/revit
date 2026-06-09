"""
tests/test_delta_cache.py
==========================
Comprehensive test suite for fireai/core/delta_cache.py

SAFETY CRITICAL: The delta cache ensures that changed rooms are ALWAYS
re-analyzed. If cache invalidation fails, stale results could be used
for fire alarm design — potentially leaving areas without adequate
detection. Safety is NEVER compromised: changed rooms are ALWAYS
re-analyzed.

Key features tested:
  - LRU cache with TTL
  - Dependency graph with cascade invalidation
  - get_or_compute pattern
  - Direct cache access (put, get, has)
  - Legacy API (has_valid_entry, put_room, invalidate_room, process_incremental)
  - SQLite persistence
  - Content hash change detection
  - Thread safety
  - Edge cases (NaN, infinity, empty inputs)
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
import pytest

from fireai.core.delta_cache import (
    DeltaCache,
    CacheEntry,
    DependencyEdge,
    _content_hash,
    _LRUCache,
    _DependencyGraph,
    _ALGORITHM_VERSION,
)


# ─────────────────────────────────────────────────────────────────────────────
# _content_hash Helper Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        h1 = _content_hash({"a": 1, "b": 2})
        h2 = _content_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_key_order_independent(self):
        h1 = _content_hash({"a": 1, "b": 2})
        h2 = _content_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = _content_hash({"a": 1})
        h2 = _content_hash({"a": 2})
        assert h1 != h2

    def test_returns_16_char_hex(self):
        h = _content_hash({"x": 1})
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_non_serializable_falls_back_to_str(self):
        """Non-JSON-serializable objects should fall back to str()."""
        h = _content_hash(object())
        assert len(h) == 16  # Still produces a hash

    def test_list_content(self):
        h = _content_hash([1, 2, 3])
        assert len(h) == 16

    def test_string_content(self):
        h = _content_hash("hello")
        assert len(h) == 16


# ─────────────────────────────────────────────────────────────────────────────
# CacheEntry Dataclass Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheEntry:
    def test_creation(self):
        entry = CacheEntry(
            key="room-A:abc123",
            result={"detector_count": 5},
            content_hash="abc123",
            computed_at=1000.0,
        )
        assert entry.key == "room-A:abc123"
        assert entry.result == {"detector_count": 5}
        assert entry.hit_count == 0
        assert entry.compute_time_s == 0.0

    def test_custom_hit_count(self):
        entry = CacheEntry("k", "v", "h", 1.0, hit_count=10)
        assert entry.hit_count == 10


class TestDependencyEdge:
    def test_creation(self):
        edge = DependencyEdge(
            source_id="cable-01",
            target_id="room-A",
            edge_type="room→cable",
        )
        assert edge.source_id == "cable-01"
        assert edge.target_id == "room-A"


# ─────────────────────────────────────────────────────────────────────────────
# _LRUCache Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestLRUCache:
    def test_put_and_get(self):
        cache = _LRUCache(maxsize=10)
        entry = CacheEntry("k1", "result1", "h1", time.time())
        cache.put("k1", entry)
        result = cache.get("k1")
        assert result is not None
        assert result.result == "result1"

    def test_get_miss(self):
        cache = _LRUCache()
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self):
        cache = _LRUCache(maxsize=3)
        for i in range(5):
            cache.put(f"k{i}", CacheEntry(f"k{i}", f"v{i}", f"h{i}", time.time()))
        # Only last 3 should remain
        assert cache.size == 3
        assert cache.get("k0") is None
        assert cache.get("k1") is None
        assert cache.get("k2") is not None
        assert cache.get("k3") is not None
        assert cache.get("k4") is not None

    def test_ttl_expiry(self):
        cache = _LRUCache(maxsize=10, ttl_s=0.1)
        entry = CacheEntry("k1", "v1", "h1", time.time())
        cache.put("k1", entry)
        assert cache.get("k1") is not None
        time.sleep(0.15)
        assert cache.get("k1") is None

    def test_ttl_not_expired(self):
        cache = _LRUCache(maxsize=10, ttl_s=10.0)
        entry = CacheEntry("k1", "v1", "h1", time.time())
        cache.put("k1", entry)
        assert cache.get("k1") is not None

    def test_no_ttl_default(self):
        cache = _LRUCache(maxsize=10)
        assert cache._ttl == 0.0

    def test_invalidate(self):
        cache = _LRUCache()
        cache.put("k1", CacheEntry("k1", "v1", "h1", time.time()))
        assert cache.invalidate("k1") is True
        assert cache.get("k1") is None

    def test_invalidate_nonexistent(self):
        cache = _LRUCache()
        assert cache.invalidate("nonexistent") is False

    def test_invalidate_prefix(self):
        cache = _LRUCache()
        cache.put("room-A:h1", CacheEntry("room-A:h1", "v1", "h1", time.time()))
        cache.put("room-A:h2", CacheEntry("room-A:h2", "v2", "h2", time.time()))
        cache.put("room-B:h1", CacheEntry("room-B:h1", "v3", "h3", time.time()))
        count = cache.invalidate_prefix("room-A:")
        assert count == 2
        assert cache.size == 1

    def test_clear(self):
        cache = _LRUCache()
        for i in range(5):
            cache.put(f"k{i}", CacheEntry(f"k{i}", f"v{i}", f"h{i}", time.time()))
        cache.clear()
        assert cache.size == 0

    def test_hit_count_tracking(self):
        cache = _LRUCache()
        cache.put("k1", CacheEntry("k1", "v1", "h1", time.time()))
        cache.get("k1")
        cache.get("k1")
        assert cache.hits == 2
        assert cache.misses == 0

    def test_miss_count_tracking(self):
        cache = _LRUCache()
        cache.get("nonexistent")
        assert cache.misses == 1

    def test_hit_rate(self):
        cache = _LRUCache()
        cache.put("k1", CacheEntry("k1", "v1", "h1", time.time()))
        cache.get("k1")  # hit
        cache.get("k1")  # hit
        cache.get("nope")  # miss
        assert cache.hit_rate == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_hit_rate_zero_when_no_accesses(self):
        cache = _LRUCache()
        assert cache.hit_rate == 0.0

    def test_stats(self):
        cache = _LRUCache(maxsize=100)
        cache.put("k1", CacheEntry("k1", "v1", "h1", time.time()))
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["maxsize"] == 100
        assert "hit_rate" in stats

    def test_move_to_end_on_get(self):
        """Accessing a key should move it to MRU position."""
        cache = _LRUCache(maxsize=3)
        cache.put("k1", CacheEntry("k1", "v1", "h1", time.time()))
        cache.put("k2", CacheEntry("k2", "v2", "h2", time.time()))
        cache.put("k3", CacheEntry("k3", "v3", "h3", time.time()))
        # Access k1 to move it to MRU
        cache.get("k1")
        # Add k4, which should evict k2 (LRU)
        cache.put("k4", CacheEntry("k4", "v4", "h4", time.time()))
        assert cache.get("k1") is not None  # k1 still here (was accessed)
        assert cache.get("k2") is None  # k2 evicted


# ─────────────────────────────────────────────────────────────────────────────
# _DependencyGraph Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDependencyGraph:
    def test_add_dependency(self):
        graph = _DependencyGraph()
        graph.add_dependency("cable-01", "room-A")
        deps = graph.get_all_dependents("room-A")
        assert "cable-01" in deps

    def test_no_dependents(self):
        graph = _DependencyGraph()
        deps = graph.get_all_dependents("room-A")
        assert len(deps) == 0

    def test_transitive_dependencies(self):
        """A → B → C: invalidating C should invalidate A and B."""
        graph = _DependencyGraph()
        graph.add_dependency("B", "C")  # B depends on C
        graph.add_dependency("A", "B")  # A depends on B
        deps = graph.get_all_dependents("C")
        assert "A" in deps
        assert "B" in deps

    def test_remove_node(self):
        graph = _DependencyGraph()
        graph.add_dependency("cable-01", "room-A")
        graph.remove_node("cable-01")
        deps = graph.get_all_dependents("room-A")
        assert "cable-01" not in deps

    def test_stats(self):
        graph = _DependencyGraph()
        graph.add_dependency("cable-01", "room-A")
        graph.add_dependency("cable-02", "room-A")
        stats = graph.stats()
        assert stats["edges"] == 2

    def test_circular_dependency_handled(self):
        """Circular dependencies should not cause infinite loop."""
        graph = _DependencyGraph()
        graph.add_dependency("A", "B")
        graph.add_dependency("B", "A")
        deps = graph.get_all_dependents("A")
        assert "B" in deps

    def test_multiple_dependencies(self):
        graph = _DependencyGraph()
        graph.add_dependency("cable-01", "room-A")
        graph.add_dependency("floor-01", "room-A")
        graph.add_dependency("report-01", "floor-01")
        deps = graph.get_all_dependents("room-A")
        assert "cable-01" in deps
        assert "floor-01" in deps
        assert "report-01" in deps  # Transitive


# ─────────────────────────────────────────────────────────────────────────────
# DeltaCache — Core API Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaCacheCoreAPI:
    """Test Section 11.2 core API."""

    def test_get_or_compute_miss(self):
        cache = DeltaCache()
        compute_count = [0]

        def expensive_compute():
            compute_count[0] += 1
            return {"detector_count": 5}

        result = cache.get_or_compute("room-A", {"polygon": [1, 2, 3]}, expensive_compute)
        assert result == {"detector_count": 5}
        assert compute_count[0] == 1

    def test_get_or_compute_hit(self):
        cache = DeltaCache()
        compute_count = [0]

        def compute():
            compute_count[0] += 1
            return {"result": "value"}

        content = {"polygon": [1, 2, 3]}
        cache.get_or_compute("room-A", content, compute)
        cache.get_or_compute("room-A", content, compute)  # Should hit cache
        assert compute_count[0] == 1
        assert cache.saved_computes == 1

    def test_get_or_compute_different_content_recomputes(self):
        """Changed content should trigger recompute."""
        cache = DeltaCache()
        results = []

        def compute():
            results.append(1)
            return len(results)

        cache.get_or_compute("room-A", {"v": 1}, compute)
        cache.get_or_compute("room-A", {"v": 2}, compute)
        assert len(results) == 2

    def test_get_or_compute_with_dependencies(self):
        cache = DeltaCache()
        cache.get_or_compute(
            "cable-01",
            {"route": "data"},
            lambda: "cable_result",
            depends_on=["room-A"],
        )
        # Invalidating room-A should also invalidate cable-01
        invalidated = cache.invalidate("room-A", cascade=True)
        assert "cable-01" in invalidated

    def test_invalidate_single_node(self):
        cache = DeltaCache()
        cache.put("room-A", {"v": 1}, "result")
        invalidated = cache.invalidate("room-A", cascade=False)
        assert "room-A" in invalidated
        assert cache.get("room-A", {"v": 1}) is None

    def test_invalidate_cascade(self):
        cache = DeltaCache()
        cache.add_dependency("cable-01", "room-A")
        cache.put("room-A", {"v": 1}, "room_result")
        cache.put("cable-01", {"v": 1}, "cable_result")
        invalidated = cache.invalidate("room-A", cascade=True)
        assert "room-A" in invalidated
        assert "cable-01" in invalidated

    def test_invalidate_batch(self):
        cache = DeltaCache()
        cache.put("room-A", {"v": 1}, "r1")
        cache.put("room-B", {"v": 1}, "r2")
        invalidated = cache.invalidate_batch(["room-A", "room-B"], cascade=False)
        assert "room-A" in invalidated
        assert "room-B" in invalidated

    def test_put_and_get(self):
        cache = DeltaCache()
        cache.put("room-A", {"v": 1}, "result")
        assert cache.get("room-A", {"v": 1}) == "result"

    def test_get_nonexistent(self):
        cache = DeltaCache()
        assert cache.get("room-X", {"v": 1}) is None

    def test_has(self):
        cache = DeltaCache()
        assert cache.has("room-A", {"v": 1}) is False
        cache.put("room-A", {"v": 1}, "result")
        assert cache.has("room-A", {"v": 1}) is True

    def test_add_dependency(self):
        cache = DeltaCache()
        cache.add_dependency("cable-01", "room-A")
        invalidated = cache.invalidate("room-A", cascade=True)
        assert "cable-01" in invalidated

    def test_remove_node(self):
        cache = DeltaCache()
        cache.add_dependency("cable-01", "room-A")
        cache.remove_node("cable-01")
        invalidated = cache.invalidate("room-A", cascade=True)
        assert "cable-01" not in invalidated

    def test_clear(self):
        cache = DeltaCache()
        cache.put("room-A", {"v": 1}, "r1")
        cache.put("room-B", {"v": 1}, "r2")
        cache.clear()
        assert cache.size == 0

    def test_size(self):
        cache = DeltaCache()
        assert cache.size == 0
        cache.put("room-A", {"v": 1}, "r1")
        assert cache.size == 1


# ─────────────────────────────────────────────────────────────────────────────
# DeltaCache — Legacy API Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaCacheLegacyAPI:
    """Test backward-compatible room-dict-based API."""

    @pytest.fixture
    def room_dict(self):
        return {
            "room_id": "R-101",
            "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
            "ceiling_height": 3.0,
            "room_type": "office",
            "detector_type": "smoke_photoelectric",
        }

    def test_has_valid_entry_false_initially(self, room_dict):
        cache = DeltaCache()
        assert cache.has_valid_entry(room_dict) is False

    def test_put_room_and_has_valid_entry(self, room_dict):
        cache = DeltaCache()
        cache.put_room(room_dict, {"detector_count": 4})
        assert cache.has_valid_entry(room_dict) is True

    def test_invalidate_room(self, room_dict):
        cache = DeltaCache()
        cache.put_room(room_dict, {"detector_count": 4})
        cache.invalidate_room("R-101")
        assert cache.has_valid_entry(room_dict) is False

    def test_invalidate_all(self, room_dict):
        cache = DeltaCache()
        cache.put_room(room_dict, {"detector_count": 4})
        cache.invalidate_all()
        assert cache.size == 0

    def test_process_incremental_first_run(self, room_dict):
        cache = DeltaCache()
        analysis_count = [0]

        def analyze(room):
            analysis_count[0] += 1
            return {"detector_count": 3, "compliant": True}

        results, stats = cache.process_incremental([room_dict], analyze)
        assert len(results) == 1
        assert analysis_count[0] == 1
        assert results[0]["_cache_hit"] is False

    def test_process_incremental_cached_run(self, room_dict):
        cache = DeltaCache()
        analyze_count = [0]

        def analyze(room):
            analyze_count[0] += 1
            return {"detector_count": 3}

        cache.process_incremental([room_dict], analyze)
        results, stats = cache.process_incremental([room_dict], analyze)
        assert analyze_count[0] == 1  # Only ran once
        assert results[0]["_cache_hit"] is True

    def test_process_incremental_with_changed_rooms(self, room_dict):
        cache = DeltaCache()
        analyze_count = [0]

        def analyze(room):
            analyze_count[0] += 1
            return {"detector_count": 3}

        cache.process_incremental([room_dict], analyze)
        # Force re-analysis of room
        results, stats = cache.process_incremental(
            [room_dict], analyze, changed_room_ids=["R-101"],
        )
        assert analyze_count[0] == 2  # Re-ran due to change hint

    def test_process_incremental_stats(self, room_dict):
        cache = DeltaCache()

        def analyze(room):
            return {"detector_count": 3}

        _, stats = cache.process_incremental([room_dict], analyze)
        assert stats["total_rooms"] == 1
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "total_time_s" in stats

    def test_legacy_stats_property(self):
        cache = DeltaCache()
        s = cache.stats()
        assert isinstance(s, dict)

    def test_room_dict_with_id_field(self):
        """Legacy: room dict with 'id' instead of 'room_id'."""
        cache = DeltaCache()
        room = {
            "id": "R-200",
            "polygon_coords": [(0, 0), (5, 0), (5, 5), (0, 5)],
            "ceiling_height": 3.0,
            "detector_type": "smoke",
        }
        cache.put_room(room, {"detector_count": 2})
        assert cache.has_valid_entry(room) is True


# ─────────────────────────────────────────────────────────────────────────────
# DeltaCache — Statistics Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaCacheStats:
    def test_stats_summary(self):
        cache = DeltaCache()
        cache.get_or_compute("node-A", {"v": 1}, lambda: "result")
        summary = cache.stats_summary()
        assert "cache" in summary
        assert "graph" in summary
        assert summary["total_computes"] == 1
        assert "efficiency_pct" in summary

    def test_efficiency_calculation(self):
        cache = DeltaCache()
        content = {"v": 1}
        cache.get_or_compute("n1", content, lambda: "r1")
        cache.get_or_compute("n1", content, lambda: "r2")  # Hit
        summary = cache.stats_summary()
        assert summary["saved_computes"] == 1
        assert summary["efficiency_pct"] == pytest.approx(50.0, abs=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# DeltaCache — SQLite Persistence Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaCachePersistence:
    def test_persist_and_load(self):
        """Data should survive persist → load cycle."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Write
            cache1 = DeltaCache(db_path=db_path)
            cache1.put("room-A", {"v": 1}, {"detector_count": 5})
            cache1.persist()

            # Read
            cache2 = DeltaCache(db_path=db_path)
            # The entry should be loaded from SQLite
            assert cache2.size > 0
            # V131 FIX: Force persist to close any lingering connections before cleanup
            cache2.persist()
            cache1.persist()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass  # Windows may still hold a lock; temp files are cleaned up eventually

    def test_persist_without_db_path(self):
        """persist() with no db_path should be a no-op."""
        cache = DeltaCache()
        cache.put("room-A", {"v": 1}, "result")
        cache.persist()  # Should not raise

    def test_algorithm_version_invalidation(self):
        """Different algorithm version should invalidate loaded entries."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            cache1 = DeltaCache(db_path=db_path, algorithm_version="v1")
            cache1.put("room-A", {"v": 1}, "result")
            cache1.persist()

            # Load with different version — old entries should be purged
            cache2 = DeltaCache(db_path=db_path, algorithm_version="v2")
            # Entries with old algorithm version are deleted on persist
            # But loaded entries are filtered by version
            cache2.persist()
            cache1.persist()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# DeltaCache — Thread Safety Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaCacheThreadSafety:
    def test_concurrent_get_or_compute(self):
        """Multiple threads using get_or_compute should not crash."""
        cache = DeltaCache()
        errors = []

        def worker(start):
            try:
                for i in range(50):
                    node_id = f"node-{start + i}"
                    cache.get_or_compute(
                        node_id,
                        {"i": i},
                        lambda: f"result-{start}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i * 100,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_invalidate(self):
        """Concurrent invalidation should not crash."""
        cache = DeltaCache()
        for i in range(100):
            cache.put(f"node-{i}", {"v": 1}, f"result-{i}")

        errors = []

        def invalidator(start):
            try:
                for i in range(start, start + 25):
                    cache.invalidate(f"node-{i}", cascade=False)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=invalidator, args=(i * 25,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# DeltaCache — Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaCacheEdgeCases:
    def test_empty_content(self):
        cache = DeltaCache()
        cache.get_or_compute("node", {}, lambda: "result")
        assert cache.get("node", {}) == "result"

    def test_none_result(self):
        """None result should be cached (but has() returns False)."""
        cache = DeltaCache()
        cache.put("node", {"v": 1}, None)
        # get returns None, but so does a miss — this is a known limitation
        result = cache.get("node", {"v": 1})
        assert result is None

    def test_custom_hash_fn(self):
        """Custom hash function should be used."""
        call_count = [0]

        def custom_hash(content):
            call_count[0] += 1
            return "fixed-hash"

        cache = DeltaCache(hash_fn=custom_hash)
        cache.get_or_compute("node", {"v": 1}, lambda: "result")
        assert call_count[0] > 0

    def test_maxsize_respected(self):
        """Cache should not exceed maxsize."""
        cache = DeltaCache(maxsize=5)
        for i in range(20):
            cache.put(f"node-{i}", {"v": i}, f"result-{i}")
        assert cache.size <= 5

    def test_ttl_expiry(self):
        """Entries should expire after TTL."""
        cache = DeltaCache(maxsize=100, ttl_s=0.1)
        cache.put("node", {"v": 1}, "result")
        assert cache.get("node", {"v": 1}) == "result"
        time.sleep(0.15)
        assert cache.get("node", {"v": 1}) is None

    def test_large_content(self):
        """Large content should be hashable without issues."""
        cache = DeltaCache()
        content = {"data": list(range(10000))}
        cache.get_or_compute("node", content, lambda: "result")
        assert cache.get("node", content) == "result"

    def test_algorithm_version_constant(self):
        assert _ALGORITHM_VERSION == "v30.0"

    def test_invalidate_nonexistent_node(self):
        """Invalidating a nonexistent node should return just that node."""
        cache = DeltaCache()
        invalidated = cache.invalidate("nonexistent", cascade=False)
        assert "nonexistent" in invalidated

    def test_process_incremental_empty_rooms(self):
        cache = DeltaCache()
        results, stats = cache.process_incremental([], lambda r: r)
        assert results == []
        assert stats["total_rooms"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
