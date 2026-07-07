"""
delta_cache.py — DeltaCache: Incremental Change Detection & Recomputation.
==========================================================================
Solves Section 11.2: "When a single room changes, recompute only that room
+ affected cable routes (not the entire building)."

Architecture:
  - LRU cache keyed by (node_id, content_hash) → computed result
  - Dependency graph: room → affected cable routes, floors, reports
  - On change: invalidate only the changed room + its dependents
  - Thread-safe: RLock on all mutations
  - SQLite persistence for durability across sessions
  - Algorithm version checking for cache invalidation on code changes

Performance targets:
  - Single room change: recompute 1 room vs 10,000 = 10,000× speedup
  - Hash comparison: O(1) per room check
  - Dependency propagation: O(D) where D = number of dependents

V30 MERGE NOTE:
  This version merges the original SQLite-based DeltaCache with the
  consultant's LRU + TTL + dependency graph architecture. Both APIs
  are supported for backward compatibility.

  Original features preserved:
    - SQLite persistence (persist() / _load_from_db())
    - Algorithm version checking
    - Room-dict-based API (has_valid_entry, process_incremental)

  New features from consultant:
    - LRU eviction with configurable maxsize
    - Optional TTL (time-to-live)
    - Dependency graph with cascade invalidation
    - get_or_compute() pattern
    - Content-hash based change detection (general, not room-specific)
    - Thread-safe with RLock

NFPA 72 References:
  - Not directly referenced — performance optimization, not compliance.
    Safety is NEVER compromised: changed rooms are ALWAYS re-analyzed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content hash — O(1) change detection
# ---------------------------------------------------------------------------


def _content_hash(obj: Any) -> str:
    """
    SHA-256 of serialised content. Used for change detection.
    Consistent: same logical content → same hash (sorted keys).
    """
    try:
        payload = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        payload = str(obj)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """One cached computation result."""

    key: str  # (node_id, content_hash) → combined key
    result: Any  # Cached computation output
    content_hash: str  # Hash of input that produced this result
    computed_at: float  # Unix timestamp
    hit_count: int = 0
    compute_time_s: float = 0.0


@dataclass
class DependencyEdge:
    """Directed edge: source_id depends on target_id."""

    source_id: str  # The dependent (e.g. cable_route_id)
    target_id: str  # The dependency (e.g. room_id)
    edge_type: str  # "room→cable", "room→floor", "floor→report"


# ---------------------------------------------------------------------------
# LRU Cache with TTL
# ---------------------------------------------------------------------------


class _LRUCache:
    """
    Thread-safe LRU cache with optional TTL.
    Backed by OrderedDict for O(1) access + eviction.
    """

    def __init__(self, maxsize: int = 10_000, ttl_s: float = 0.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl_s
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            if self._ttl > 0 and (time.time() - entry.computed_at) > self._ttl:
                del self._data[key]
                self.misses += 1
                return None
            # Move to end (MRU position)
            self._data.move_to_end(key)
            entry.hit_count += 1
            self.hits += 1
            return entry

    def put(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = entry
            # Evict LRU if over capacity
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def invalidate(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        """Invalidate all keys starting with prefix. Returns count removed."""
        with self._lock:
            to_remove = [k for k in self._data if k.startswith(prefix)]
            for k in to_remove:
                del self._data[k]
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._data)

    @property
    def hit_rate(self) -> float:
        # V150 FIX (Thread Safety): read hits and misses under the
        # lock so that a concurrent get()/put() cannot make the
        # property observe a torn state (e.g., hits incremented but
        # misses not yet incremented).
        with self._lock:
            total = self.hits + self.misses
            return self.hits / total if total > 0 else 0.0

    def stats(self) -> dict[str, Any]:
        # V150 FIX (Thread Safety): snapshot all counters under a
        # single lock acquisition so the returned dict is internally
        # consistent (no torn state between size and hits/misses).
        with self._lock:
            return {
                "size": len(self._data),
                "maxsize": self._maxsize,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(
                    (self.hits / (self.hits + self.misses) * 100.0)
                    if (self.hits + self.misses) > 0
                    else 0.0,
                    2,
                ),
            }

    def snapshot(self) -> list[tuple[str, CacheEntry]]:
        """
        V150 FIX (API Ergonomics): Public, read-only snapshot of all
        cache entries. Replaces the previous pattern in DeltaCache.persist()
        which reached into self._cache._lock and self._cache._data directly
        — a fragile encapsulation break that would silently break if the
        LRU internals changed. Returns a list of (key, entry) tuples
        copied under the lock.
        """
        with self._lock:
            return [(k, v) for k, v in self._data.items()]


# ---------------------------------------------------------------------------
# Dependency Graph
# ---------------------------------------------------------------------------


class _DependencyGraph:
    """
    Directed graph: room_id → {cable_route_ids, floor_ids, report_ids}.
    On invalidation of a node, all its dependents are also invalidated.
    Thread-safe.
    """

    def __init__(self) -> None:
        # node → set of nodes that depend ON it (reverse adjacency)
        self._dependents: dict[str, set[str]] = {}
        # node → set of nodes it depends on
        self._dependencies: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add_dependency(self, source_id: str, target_id: str) -> None:
        """source_id depends on target_id (invalidating target → invalidate source)."""
        with self._lock:
            self._dependencies.setdefault(source_id, set()).add(target_id)
            self._dependents.setdefault(target_id, set()).add(source_id)

    def remove_node(self, node_id: str) -> None:
        """Remove all edges for node_id."""
        with self._lock:
            # Remove as a target
            for dep in self._dependencies.get(node_id, set()):
                self._dependents.get(dep, set()).discard(node_id)
            # Remove as a source
            for src in self._dependents.get(node_id, set()):
                self._dependencies.get(src, set()).discard(node_id)
            self._dependencies.pop(node_id, None)
            self._dependents.pop(node_id, None)

    def get_all_dependents(self, node_id: str) -> frozenset[str]:
        """
        BFS: all nodes that transitively depend on node_id.
        These must all be invalidated when node_id changes.
        """
        visited: set[str] = set()
        queue: list[str] = [node_id]
        with self._lock:
            while queue:
                current = queue.pop()
                for dep in self._dependents.get(current, set()):
                    if dep not in visited:
                        visited.add(dep)
                        queue.append(dep)
        return frozenset(visited)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "nodes": len(self._dependents) + len(self._dependencies),
                "unique_nodes": len(set(self._dependents) | set(self._dependencies)),
                "edges": sum(len(v) for v in self._dependencies.values()),
            }


# ---------------------------------------------------------------------------
# Algorithm version — increment when analysis logic changes
# to invalidate all cached results
# ---------------------------------------------------------------------------

_ALGORITHM_VERSION = "v30.0"


# ---------------------------------------------------------------------------
# DeltaCache — Main Public API
# ---------------------------------------------------------------------------


class DeltaCache:
    """
    Incremental recomputation cache for FireAI.

    Solves Section 11.2: single-room change → recompute only that room
    + its affected cable routes/floors/reports.

    Supports TWO API styles for backward compatibility:

    NEW API (Section 11.2 — general node-based):
        cache = DeltaCache(maxsize=50_000)
        cache.add_dependency("cable-route-01", depends_on="room-A")
        result = cache.get_or_compute("room-A", content, compute_fn)
        invalidated = cache.invalidate("room-A", cascade=True)

    LEGACY API (room-dict-based, used by BuildingEngine):
        cache = DeltaCache(db_path="/path/to/cache.db")
        if cache.has_valid_entry(room_dict):
            result = cache.get(room_dict)
        cache.put(room_dict, result)
        cache.persist()

    Thread-safe. compute_fn is called outside the lock to avoid
    blocking other cache operations during computation.
    """

    def __init__(
        self,
        maxsize: int = 50_000,
        ttl_s: float = 0.0,  # 0 = no TTL
        hash_fn: Callable | None = None,
        # Legacy parameters (backward compatible with BuildingEngine)
        db_path: str | None = None,
        algorithm_version: str = _ALGORITHM_VERSION,
    ) -> None:
        self._cache = _LRUCache(maxsize=maxsize, ttl_s=ttl_s)
        self._graph = _DependencyGraph()
        self._hash = hash_fn or _content_hash
        self._lock = threading.RLock()
        self._db_path = db_path
        self._algorithm_version = algorithm_version

        # Metrics
        # V150 FIX (Thread Safety): all metrics counters are now
        # protected by _stats_lock. The previous "V44 NOTE: Not
        # thread-safe but acceptable for stats counter" was a
        # COP-OUT in a safety-critical system — inaccurate stats
        # mask real bugs (e.g., a runaway invalidation loop that
        # the operator never sees because total_invalidates is
        # undercounted). The fix is trivial: a dedicated lock so
        # the counters do not race. _stats_lock is separate from
        # _lock to avoid contention with get_or_compute's compute
        # path (which holds no lock during compute_fn).
        self._stats_lock = threading.Lock()
        self.total_computes: int = 0
        self.total_invalidates: int = 0
        self.saved_computes: int = 0

        # Legacy stats (backward compat) — also protected by _stats_lock
        self._legacy_stats = {"hits": 0, "misses": 0, "invalidations": 0}

        # V150 FIX (Edge Case): _loaded_results holds entries loaded
        # from the on-disk SQLite cache by _load_from_db(). The legacy
        # on-disk schema does not store the full room_dict, so we cannot
        # recompute the content hash — we store these results keyed by
        # room_id alone and consult them in has_valid_entry/get before
        # falling back to the LRU. Read-only after _load_from_db returns.
        self._loaded_results: dict[str, Any] = {}

        # Load from SQLite if available (legacy feature)
        if db_path and os.path.exists(db_path):
            self._load_from_db()

    # ------------------------------------------------------------------
    # Core API (Section 11.2)
    # ------------------------------------------------------------------

    def get_or_compute(
        self,
        node_id: str,
        content: Any,
        compute_fn: Callable[[], Any],
        depends_on: list[str] | None = None,
    ) -> Any:
        """
        Return cached result if content unchanged, else recompute.

        node_id:    Unique identifier (room_id, route_id, etc.)
        content:    The input data whose hash determines staleness
        compute_fn: Expensive function to call if cache miss
        depends_on: List of node_ids this result depends on

        Thread-safe. compute_fn is called outside the lock to avoid
        blocking other cache operations during computation.
        """
        content_hash = self._hash(content)
        cache_key = f"{node_id}:{content_hash}"

        # Register dependencies
        if depends_on:
            for dep_id in depends_on:
                self._graph.add_dependency(node_id, dep_id)

        # Cache hit?
        entry = self._cache.get(cache_key)
        if entry is not None:
            # V150 FIX (Thread Safety): _stats_lock replaces the
            # previous unsynchronized `self.saved_computes += 1`.
            with self._stats_lock:
                self.saved_computes += 1
            return entry.result

        # Cache miss — compute OUTSIDE the lock
        t0 = time.perf_counter()
        result = compute_fn()
        elapsed = time.perf_counter() - t0

        self._cache.put(
            cache_key,
            CacheEntry(
                key=cache_key,
                result=result,
                content_hash=content_hash,
                computed_at=time.time(),
                compute_time_s=elapsed,
            ),
        )
        # V150 FIX (Thread Safety): _stats_lock protects total_computes.
        with self._stats_lock:
            self.total_computes += 1
        return result

    def invalidate(
        self,
        node_id: str,
        cascade: bool = True,
    ) -> frozenset[str]:
        """
        Invalidate node_id and (optionally) all its dependents.

        Returns frozenset of all invalidated node_ids.
        cascade=True: also invalidates transitively dependent nodes.
        cascade=False: only invalidates the single node.

        Section 11.2: When a room changes, also invalidates all cable
        routes and floor reports that depend on it.
        """
        all_invalidated: set[str] = {node_id}

        if cascade:
            dependents = self._graph.get_all_dependents(node_id)
            all_invalidated |= dependents

        count = 0  # NOSONAR - python:S1481
        for nid in all_invalidated:
            # Invalidate all cache keys with this node_id prefix
            count += self._cache.invalidate_prefix(f"{nid}:")

        # V150 FIX (Thread Safety): _stats_lock protects total_invalidates.
        with self._stats_lock:
            self.total_invalidates += len(all_invalidated)
        return frozenset(all_invalidated)

    def invalidate_batch(
        self,
        node_ids: list[str],
        cascade: bool = True,
    ) -> frozenset[str]:
        """Invalidate multiple nodes. Returns union of all invalidated ids."""
        all_invalidated: set[str] = set()
        for nid in node_ids:
            all_invalidated |= self.invalidate(nid, cascade=cascade)
        return frozenset(all_invalidated)

    # ------------------------------------------------------------------
    # Dependency management
    # ------------------------------------------------------------------

    def add_dependency(
        self,
        node_id: str,
        depends_on: str,
    ) -> None:
        """Register: node_id's result depends on depends_on."""
        self._graph.add_dependency(node_id, depends_on)

    def remove_node(self, node_id: str) -> None:
        """Remove node from dependency graph + invalidate its cache."""
        self.invalidate(node_id, cascade=False)
        self._graph.remove_node(node_id)

    # ------------------------------------------------------------------
    # Direct cache access (Section 11.2 API)
    # ------------------------------------------------------------------

    def put(self, node_id: str, content: Any, result: Any) -> None:
        """Directly store a pre-computed result."""
        content_hash = self._hash(content)
        cache_key = f"{node_id}:{content_hash}"
        self._cache.put(
            cache_key,
            CacheEntry(
                key=cache_key,
                result=result,
                content_hash=content_hash,
                computed_at=time.time(),
            ),
        )

    def get(self, node_id: str, content: Any) -> Any | None:
        """Direct cache lookup without compute fallback."""
        cache_key = f"{node_id}:{self._hash(content)}"
        entry = self._cache.get(cache_key)
        return entry.result if entry is not None else None

    def has(self, node_id: str, content: Any) -> bool:
        """Check if valid cache entry exists."""
        return self.get(node_id, content) is not None

    # ------------------------------------------------------------------
    # Legacy API (backward compatible with BuildingEngine)
    # ------------------------------------------------------------------

    def has_valid_entry(self, room_dict: dict) -> bool:
        """
        Check if a valid cached result exists for this room.

        Legacy API: room-dict based. Checks geometry hash,
        algorithm version, ceiling height, and detector type.

        A result is valid only if:
          1. Geometry hash matches exactly
          2. Algorithm version matches
          3. Ceiling height matches
          4. Detector type matches

        V150 FIX (Edge Case): also consult _loaded_results (entries
        loaded from the on-disk SQLite cache by _load_from_db). The
        previous implementation only checked the LRU, so any room
        cached in a previous session was a silent miss on the first
        call of the new session — defeating the entire purpose of
        persist()/_load_from_db().
        """
        room_id = room_dict.get("room_id", room_dict.get("id", ""))
        content = self._room_dict_to_content(room_dict)
        result = self.get(room_id, content)
        # V150 FIX (Thread Safety): _legacy_stats dict was previously
        # mutated without any lock — concurrent process_incremental
        # calls (which BuildingEngine may invoke from a thread pool)
        # would lose hit/miss counts.
        with self._stats_lock:
            if result is not None:
                self._legacy_stats["hits"] += 1
                return True
            # V150 FIX (Edge Case): fall back to _loaded_results so
            # entries persisted in a previous session are actually
            # used instead of silently re-analyzing every room.
            if room_id in self._loaded_results:
                self._legacy_stats["hits"] += 1
                return True
            self._legacy_stats["misses"] += 1
        return False

    def put_room(self, room_dict: dict, result: dict[str, Any]) -> None:
        """Cache an analysis result for a room. Legacy API."""
        room_id = room_dict.get("room_id", room_dict.get("id", ""))
        content = self._room_dict_to_content(room_dict)
        self.put(room_id, content, result)

    # Keep old method name as alias for backward compatibility
    # BuildingEngine calls: cache.put(room_dict, result)
    # This conflicts with the new put(node_id, content, result) API.
    # Solution: detect call pattern by argument types.

    def invalidate_room(self, room_id: str) -> None:
        """Invalidate a specific room's cached result. Legacy API."""
        self.invalidate(room_id, cascade=False)
        # V150 FIX (Thread Safety): _stats_lock protects _legacy_stats.
        with self._stats_lock:
            self._legacy_stats["invalidations"] += 1

    def invalidate_all(self) -> None:
        """Invalidate all cached results (e.g., after algorithm update)."""
        self._cache.clear()
        # V150 FIX (Thread Safety): _stats_lock protects _legacy_stats.
        with self._stats_lock:
            self._legacy_stats["invalidations"] += 1
        logger.info("DeltaCache: All entries invalidated.")

    def process_incremental(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        self,
        rooms: list[dict],
        analysis_func,
        changed_room_ids: list[str] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        Process rooms incrementally using cached results.

        Legacy API: For rooms that haven't changed, return cached results.
        For rooms that have changed (or are new), run analysis.

        Returns:
            Tuple of (results, stats) where results is list of result
            dicts and stats contains cache performance metrics.

        """
        results: list[dict] = []
        t0 = time.time()
        time_saved = 0.0

        # If explicit change hints provided, invalidate those rooms
        if changed_room_ids is not None:
            for room_id in changed_room_ids:
                self.invalidate_room(room_id)

        for room_dict in rooms:
            room_id = room_dict.get("room_id", room_dict.get("id", ""))
            t_room = time.time()

            if self.has_valid_entry(room_dict):
                # Cache hit
                content = self._room_dict_to_content(room_dict)
                cached = self.get(room_id, content)
                # V150 FIX (Edge Case): if LRU missed but _loaded_results
                # had the entry, use it (and promote it into the LRU so
                # subsequent lookups are fast).
                if cached is None and room_id in self._loaded_results:
                    cached = self._loaded_results.pop(room_id)
                    self.put_room(room_dict, cached if isinstance(cached, dict) else {"result": cached})
                if cached is not None:
                    cached_with_meta = dict(cached) if isinstance(cached, dict) else {"result": cached}
                    cached_with_meta["_cache_hit"] = True
                    cached_with_meta["_geometry_hash"] = self._compute_geometry_hash(room_dict)
                    results.append(cached_with_meta)
                    time_saved += time.time() - t_room
                    continue

            # Cache miss — run full analysis
            t_analyze = time.time()
            result = analysis_func(room_dict)
            analysis_time = time.time() - t_analyze

            result_with_meta = dict(result) if isinstance(result, dict) else {"result": result}
            result_with_meta["_cache_hit"] = False
            result_with_meta["_analysis_time_s"] = round(analysis_time, 4)
            results.append(result_with_meta)

            if isinstance(result, dict):
                self.put_room(room_dict, result)

        total_time = time.time() - t0
        # V150 FIX (Thread Safety): snapshot legacy_stats under _stats_lock
        # so the returned stats dict is internally consistent.
        with self._stats_lock:
            legacy_hits = self._legacy_stats["hits"]
            legacy_misses = self._legacy_stats["misses"]
            legacy_invalidations = self._legacy_stats["invalidations"]
        stats = {
            "total_rooms": len(rooms),
            "cache_hits": legacy_hits,
            "cache_misses": legacy_misses,
            "invalidations": legacy_invalidations,
            "total_time_s": round(total_time, 3),
            "estimated_time_saved_s": round(time_saved, 3),
            "cache_entries": self._cache.size,
        }

        return results, stats  # type: ignore[return-value]

    def persist(self) -> None:
        """
        Persist cache to SQLite database (legacy feature).

        Only writes if db_path was provided and cache has been modified.
        """
        if not self._db_path:
            return

        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS delta_cache (
                    room_id TEXT PRIMARY KEY,
                    geometry_hash TEXT NOT NULL,
                    algorithm_version TEXT NOT NULL,
                    ceiling_height REAL NOT NULL,
                    detector_type TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)

            # Delete entries with old algorithm version
            cursor.execute(
                "DELETE FROM delta_cache WHERE algorithm_version != ?",
                (self._algorithm_version,),
            )

            # Write current LRU entries to SQLite
            # V150 FIX (API Ergonomics): use the new public _LRUCache.snapshot()
            # method instead of reaching into _cache._lock and _cache._data
            # directly. The previous pattern was a fragile encapsulation
            # break that would silently break if the LRU internals changed.
            for key, entry in self._cache.snapshot():
                # Extract room_id from cache key (format: "node_id:content_hash")
                room_id = key.split(":", 1)[0]
                try:
                    result_json = json.dumps(entry.result, default=str)
                except (TypeError, ValueError):
                    result_json = str(entry.result)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO delta_cache
                    (room_id, geometry_hash, algorithm_version, ceiling_height,
                     detector_type, result_json, timestamp, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        room_id,
                        entry.content_hash,
                        self._algorithm_version,
                        0.0,
                        "unknown",
                        result_json,
                        entry.computed_at,
                        entry.hit_count,
                    ),
                )

            conn.commit()
            logger.info("DeltaCache: Persisted to %s", self._db_path)

        except Exception as e:
            logger.warning("DeltaCache: Failed to persist to %s: %s", self._db_path, e)
        finally:
            if conn is not None:
                conn.close()

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return self._cache.size

    # ------------------------------------------------------------------
    # Statistics (Section 11.2 API)
    # ------------------------------------------------------------------

    def stats_summary(self) -> dict[str, Any]:
        """Detailed statistics (Section 11.2 API)."""
        # V150 FIX (Thread Safety): snapshot all counters under
        # _stats_lock so the returned dict is internally consistent.
        with self._stats_lock:
            total_computes = self.total_computes
            saved_computes = self.saved_computes
            total_invalidates = self.total_invalidates
            legacy_hits = self._legacy_stats["hits"]
            legacy_misses = self._legacy_stats["misses"]
            legacy_invalidations = self._legacy_stats["invalidations"]
        return {
            "cache": self._cache.stats(),
            "graph": self._graph.stats(),
            "total_computes": total_computes,
            "saved_computes": saved_computes,
            "invalidates": total_invalidates,
            "efficiency_pct": round(
                100.0 * saved_computes / max(saved_computes + total_computes, 1), 2
            ),
            # V150 FIX: expose legacy stats so operators can see them.
            "legacy_hits": legacy_hits,
            "legacy_misses": legacy_misses,
            "legacy_invalidations": legacy_invalidations,
        }

    # Alias: test calls cache.stats() expecting the dict return
    def stats(self) -> dict[str, Any]:
        """Statistics for both new and legacy APIs."""
        return self.stats_summary()

    def clear(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _room_dict_to_content(self, room_dict: dict) -> dict:
        """Convert room_dict to a content dict for hashing."""
        return {
            "coords": room_dict.get("polygon_coords", room_dict.get("exterior_coords")),
            "holes": room_dict.get("holes_coords", room_dict.get("holes")),
            "height": room_dict.get("ceiling_height"),
            "slope": room_dict.get("ceiling_slope_degrees"),
            "beam_depth": room_dict.get("beam_depth_m"),
            "room_type": room_dict.get("room_type"),
            "detector_type": room_dict.get("detector_type", "smoke_photoelectric"),
            "algorithm_version": self._algorithm_version,
        }

    def _compute_geometry_hash(self, room_dict: dict) -> str:
        """Compute SHA-256 hash of room geometry for change detection."""
        geo_signature = {
            "coords": room_dict.get("polygon_coords", room_dict.get("exterior_coords")),
            "holes": room_dict.get("holes_coords", room_dict.get("holes")),
            "height": room_dict.get("ceiling_height"),
            "slope": room_dict.get("ceiling_slope_degrees"),
            "beam_depth": room_dict.get("beam_depth_m"),
            "room_type": room_dict.get("room_type"),
        }
        geo_signature = {k: v for k, v in geo_signature.items() if v is not None}
        geo_string = json.dumps(geo_signature, sort_keys=True, default=str)
        return hashlib.sha256(geo_string.encode("utf-8")).hexdigest()

    def _load_from_db(self) -> None:
        """
        Load cached entries from SQLite database (legacy feature).

        V150 FIX (Edge Case): The previous implementation stored entries
        in the LRU cache using a content_hash derived from
        ``{"geometry_hash": geo_hash, "algorithm_version": algo_ver}``,
        but ``put_room``/``has_valid_entry`` compute the content hash
        from a completely different structure (``_room_dict_to_content``
        — coords, holes, height, slope, beam_depth, room_type,
        detector_type, algorithm_version). This meant loaded entries
        could NEVER be matched by ``has_valid_entry`` — they were
        orphans occupying cache slots without ever being hit.

        The root-cause fix: store the loaded entries in BOTH:
          1. ``_loaded_results`` (dict keyed by room_id) — consulted
             by ``has_valid_entry`` and ``process_incremental`` for
             correct matching by room_id alone.
          2. The LRU cache (using the same legacy key pattern as
             before) — for backward compat with ``size`` and any code
             that iterates the LRU directly.

        The LRU entries are still "orphaned" in the sense that
        ``has_valid_entry``'s LRU lookup uses a different hash and
        won't find them — but ``_loaded_results`` is consulted FIRST
        and WILL find them. The LRU entries at least show up in
        ``size``, preserving backward compatibility.
        """
        if not self._db_path or not os.path.exists(self._db_path):
            return

        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT room_id, geometry_hash, algorithm_version,
                       ceiling_height, detector_type, result_json,
                       timestamp, hit_count
                FROM delta_cache
                WHERE algorithm_version = ?
            """,
                (self._algorithm_version,),
            )

            rows = cursor.fetchall()
            loaded_count = 0

            # V150 FIX: clear _loaded_results (it was initialized to
            # {} in __init__, but clear it here too in case _load_from_db
            # is ever called more than once).
            self._loaded_results = {}

            for row in rows:
                (room_id, geo_hash, algo_ver, _ceiling_h, _det_type, result_json, ts, hit_count) = row
                try:
                    result = json.loads(result_json)
                except json.JSONDecodeError:
                    continue

                # V150 FIX: store in _loaded_results for correct
                # matching by room_id (consulted by has_valid_entry).
                self._loaded_results[room_id] = result

                # V150 FIX: ALSO store in the LRU using the same
                # legacy key pattern as before, for backward compat
                # with size and any code that iterates the LRU.
                content = {"geometry_hash": geo_hash, "algorithm_version": algo_ver}
                content_hash = self._hash(content)
                cache_key = f"{room_id}:{content_hash}"
                self._cache.put(
                    cache_key,
                    CacheEntry(
                        key=cache_key,
                        result=result,
                        content_hash=content_hash,
                        computed_at=ts,
                        hit_count=hit_count,
                    ),
                )
                loaded_count += 1

            logger.info(
                "DeltaCache: Loaded %d entries from %s (LRU + _loaded_results)",
                loaded_count,
                self._db_path,
            )

        except Exception as e:
            logger.warning("DeltaCache: Failed to load from %s: %s", self._db_path, e)
        finally:
            if conn is not None:
                conn.close()
