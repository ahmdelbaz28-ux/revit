"""
delta_cache.py — Hash-Based Incremental Processing Cache
=========================================================

Enables delta processing: when an architect changes one room in Revit,
only that room is re-analyzed instead of the entire building.

Consultant #6 Criticism #3 — CONCEPT ACCEPTED, IMPLEMENTATION REJECTED:
  The consultant's SmartDeltaEngine used SHA-256 hashing of geometry
  with placeholder _load_cache/_save_cache. This is REJECTED because:

  1. Cache persistence was incomplete (empty methods).
  2. In a BIM/Revit workflow, the Revit plugin should be the primary
     change detector (it already knows what changed). The analysis
     engine should support incremental processing when told what changed.
  3. Per-room results can have indirect dependencies (zone assignments,
     panel capacity) that a naive hash check would miss.
  4. No cache invalidation strategy when NFPA rules or analysis
     algorithms change.

  ACCEPTED: The delta processing concept is valid. This implementation:
  - Uses SHA-256 fingerprinting for geometry change detection
  - Supports explicit change hints from the Revit connector
  - Tracks algorithm version for cache invalidation
  - Stores cache in SQLite for persistence and concurrent access
  - Handles zone/panel dependency invalidation

Architecture:
  - DeltaCache: Per-room result cache with SHA-256 fingerprinting
  - CacheEntry: A single cached result with metadata
  - Integration: BuildingEngine can use DeltaCache for incremental
    analysis when change hints are provided

NFPA 72 References:
  - Not directly referenced — this is a performance optimization,
    not a compliance feature. Safety is never compromised: changed
    rooms are ALWAYS re-analyzed. The cache only skips rooms that
    provably haven't changed.

IMPORTANT SAFETY PRINCIPLE:
  The cache NEVER skips re-verification of a room that might have
  changed. If in doubt, re-analyze. The cache saves time only when
  the geometry is provably identical (same SHA-256 hash).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Cache Entry
# ──────────────────────────────────────────────────────────────────

@dataclass
class CacheEntry:
    """A single cached room analysis result.

    Attributes:
        room_id: Room identifier.
        geometry_hash: SHA-256 hash of room geometry.
        algorithm_version: Version string of the analysis algorithm.
        ceiling_height: Ceiling height used for analysis.
        detector_type: Detector type used.
        result: Serialized analysis result (JSON-compatible dict).
        timestamp: Unix timestamp when cached.
        hit_count: Number of cache hits for this entry.
    """
    room_id: str
    geometry_hash: str
    algorithm_version: str
    ceiling_height: float
    detector_type: str
    result: Dict[str, Any]
    timestamp: float = 0.0
    hit_count: int = 0


# ──────────────────────────────────────────────────────────────────
# Delta Cache
# ──────────────────────────────────────────────────────────────────

# Algorithm version — increment when analysis logic changes
# to invalidate all cached results
_ALGORITHM_VERSION = "v10.1"

# TODO (Consultant #7 — Cascading Invalidation):
# When zone/panel results are cached (not just per-room results),
# add cascade invalidation: if a room's geometry changes, invalidate
# not only the room result but also the zone and panel that contain it.
# Current architecture recomputes zones from scratch each run, so
# cascade invalidation is not needed yet. When zone caching is added,
# implement:
#   def invalidate_cascade(self, room_id: str) -> Set[str]:
#       """Invalidate room + its zone + its panel. Return invalidated IDs."""
#       invalidated = {room_id}
#       for zone_id, zone_room_ids in self._zone_index.items():
#           if room_id in zone_room_ids:
#               self.invalidate_zone(zone_id)
#               invalidated.add(zone_id)
#       return invalidated


class DeltaCache:
    """Hash-based incremental processing cache for room analysis.

    Uses SHA-256 fingerprinting of room geometry to detect changes.
    When a room's geometry hasn't changed AND the algorithm version
    matches, the cached result is returned directly without re-analysis.

    Safety guarantee:
      - A room is ONLY skipped if its geometry hash matches exactly
      - If the algorithm version changes, ALL entries are invalidated
      - If ceiling_height or detector_type changes, the entry is invalidated
      - Zone/panel assignments are NOT cached (they depend on all rooms)

    Usage:
        cache = DeltaCache("/path/to/cache.db")

        # Before analysis:
        if cache.has_valid_entry(room_dict):
            result = cache.get(room_dict)
        else:
            result = analyze_room(room_dict)
            cache.put(room_dict, result)

        # After all rooms processed:
        cache.persist()

    SQLite Schema:
        CREATE TABLE IF NOT EXISTS delta_cache (
            room_id TEXT PRIMARY KEY,
            geometry_hash TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            ceiling_height REAL NOT NULL,
            detector_type TEXT NOT NULL,
            result_json TEXT NOT NULL,
            timestamp REAL NOT NULL,
            hit_count INTEGER DEFAULT 0
        );
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        algorithm_version: str = _ALGORITHM_VERSION,
    ):
        """Initialize delta cache.

        Args:
            db_path: Path to SQLite database file for persistence.
                If None, cache is in-memory only (not persisted).
            algorithm_version: Algorithm version string. When this
                changes, all cached entries are invalidated.
        """
        self.db_path = db_path
        self.algorithm_version = algorithm_version
        self._cache: Dict[str, CacheEntry] = {}
        self._dirty: bool = False  # True if cache has unsaved changes
        self._stats = {"hits": 0, "misses": 0, "invalidations": 0}

        # Load from SQLite if available
        if db_path and os.path.exists(db_path):
            self._load_from_db()

    # ── Public API ──────────────────────────────────────────────

    def has_valid_entry(self, room_dict: dict) -> bool:
        """Check if a valid cached result exists for this room.

        A result is valid only if:
          1. Geometry hash matches exactly
          2. Algorithm version matches
          3. Ceiling height matches
          4. Detector type matches

        Args:
            room_dict: Room dict with geometry info.

        Returns:
            True if a valid cached entry exists.
        """
        room_id = room_dict.get("room_id", room_dict.get("id", ""))
        geo_hash = self._compute_geometry_hash(room_dict)
        ceiling_h = float(room_dict.get("ceiling_height", 3.0) or 3.0)
        det_type = room_dict.get("detector_type", "smoke_photoelectric")

        entry = self._cache.get(room_id)
        if entry is None:
            self._stats["misses"] += 1
            return False

        # Check all validity conditions
        valid = (
            entry.geometry_hash == geo_hash
            and entry.algorithm_version == self.algorithm_version
            and abs(entry.ceiling_height - ceiling_h) < 0.001
            and entry.detector_type == det_type
        )

        if valid:
            self._stats["hits"] += 1
            entry.hit_count += 1
        else:
            self._stats["misses"] += 1

        return valid

    def get(self, room_dict: dict) -> Optional[Dict[str, Any]]:
        """Get cached result for a room.

        Args:
            room_dict: Room dict with geometry info.

        Returns:
            Cached result dict, or None if no valid entry.
        """
        room_id = room_dict.get("room_id", room_dict.get("id", ""))
        entry = self._cache.get(room_id)
        if entry and self.has_valid_entry(room_dict):
            return entry.result
        return None

    def put(self, room_dict: dict, result: Dict[str, Any]) -> None:
        """Cache an analysis result for a room.

        Args:
            room_dict: Room dict with geometry info.
            result: Analysis result to cache (must be JSON-serializable).
        """
        room_id = room_dict.get("room_id", room_dict.get("id", ""))
        geo_hash = self._compute_geometry_hash(room_dict)
        ceiling_h = float(room_dict.get("ceiling_height", 3.0) or 3.0)
        det_type = room_dict.get("detector_type", "smoke_photoelectric")

        entry = CacheEntry(
            room_id=room_id,
            geometry_hash=geo_hash,
            algorithm_version=self.algorithm_version,
            ceiling_height=ceiling_h,
            detector_type=det_type,
            result=result,
            timestamp=time.time(),
            hit_count=0,
        )
        self._cache[room_id] = entry
        self._dirty = True

    def invalidate(self, room_id: str) -> None:
        """Invalidate a specific room's cached result.

        Args:
            room_id: Room ID to invalidate.
        """
        if room_id in self._cache:
            del self._cache[room_id]
            self._dirty = True
            self._stats["invalidations"] += 1

    def invalidate_all(self) -> None:
        """Invalidate all cached results (e.g., after algorithm update)."""
        self._cache.clear()
        self._dirty = True
        self._stats["invalidations"] += 1
        logger.info("DeltaCache: All entries invalidated.")

    def process_incremental(
        self,
        rooms: List[dict],
        analysis_func,
        changed_room_ids: Optional[List[str]] = None,
    ) -> Tuple[List[dict], List[dict]]:
        """Process rooms incrementally using cached results.

        For rooms that haven't changed, return cached results.
        For rooms that have changed (or are new), run analysis.

        Args:
            rooms: List of room dicts to process.
            analysis_func: Function that takes a room dict and returns
                a result dict.
            changed_room_ids: Optional explicit list of rooms that changed.
                If provided, ONLY these rooms are re-analyzed (the rest
                use cache). If None, all rooms are checked via geometry hash.

        Returns:
            Tuple of (results, stats) where:
              - results: List of result dicts (cached + fresh)
              - stats: Dict with hit_count, miss_count, time_saved_s
        """
        results: List[dict] = []
        t0 = time.time()
        time_saved = 0.0

        # If explicit change hints provided, invalidate those rooms
        if changed_room_ids is not None:
            for room_id in changed_room_ids:
                self.invalidate(room_id)

        for room_dict in rooms:
            room_id = room_dict.get("room_id", room_dict.get("id", ""))
            t_room = time.time()

            if self.has_valid_entry(room_dict):
                # Cache hit — use stored result
                cached = self.get(room_dict)
                if cached is not None:
                    # Mark as cached for transparency
                    cached_with_meta = dict(cached)
                    cached_with_meta["_cache_hit"] = True
                    cached_with_meta["_geometry_hash"] = self._compute_geometry_hash(room_dict)
                    results.append(cached_with_meta)
                    time_saved += (time.time() - t_room)
                    continue

            # Cache miss — run full analysis
            t_analyze = time.time()
            result = analysis_func(room_dict)
            analysis_time = time.time() - t_analyze

            # Cache the new result
            result_with_meta = dict(result) if isinstance(result, dict) else {"result": result}
            result_with_meta["_cache_hit"] = False
            result_with_meta["_analysis_time_s"] = round(analysis_time, 4)
            results.append(result_with_meta)

            # Store in cache (only if result is dict-serializable)
            if isinstance(result, dict):
                self.put(room_dict, result)

        total_time = time.time() - t0
        stats = {
            "total_rooms": len(rooms),
            "cache_hits": self._stats["hits"],
            "cache_misses": self._stats["misses"],
            "invalidations": self._stats["invalidations"],
            "total_time_s": round(total_time, 3),
            "estimated_time_saved_s": round(time_saved, 3),
            "cache_entries": len(self._cache),
        }

        return results, stats

    def persist(self) -> None:
        """Persist cache to SQLite database.

        Only writes if cache has been modified since last persist.
        """
        if not self._dirty or not self.db_path:
            return

        try:
            conn = sqlite3.connect(self.db_path)
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
                (self.algorithm_version,),
            )

            # Upsert all entries
            for entry in self._cache.values():
                result_json = json.dumps(entry.result, default=str)
                cursor.execute("""
                    INSERT OR REPLACE INTO delta_cache
                    (room_id, geometry_hash, algorithm_version, ceiling_height,
                     detector_type, result_json, timestamp, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.room_id,
                    entry.geometry_hash,
                    entry.algorithm_version,
                    entry.ceiling_height,
                    entry.detector_type,
                    result_json,
                    entry.timestamp,
                    entry.hit_count,
                ))

            conn.commit()
            conn.close()
            self._dirty = False
            logger.info("DeltaCache: Persisted %d entries to %s", len(self._cache), self.db_path)

        except Exception as e:
            logger.warning("DeltaCache: Failed to persist to %s: %s", self.db_path, e)

    @property
    def stats(self) -> Dict[str, int]:
        """Cache statistics."""
        return dict(self._stats)

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self._cache)

    # ── Private ──────────────────────────────────────────────────

    def _compute_geometry_hash(self, room_dict: dict) -> str:
        """Compute SHA-256 hash of room geometry for change detection.

        Includes coordinates, ceiling height, holes, and any geometry-
        affecting parameters. Does NOT include analysis parameters
        (those are checked separately).

        Args:
            room_dict: Room dict with geometry info.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        # Extract geometry-significant fields
        geo_signature = {
            "coords": room_dict.get("polygon_coords", room_dict.get("exterior_coords")),
            "holes": room_dict.get("holes_coords", room_dict.get("holes")),
            "height": room_dict.get("ceiling_height"),
            "slope": room_dict.get("ceiling_slope_degrees"),
            "beam_depth": room_dict.get("beam_depth_m"),
            "room_type": room_dict.get("room_type"),  # affects detector type selection
        }
        # Remove None values for consistent hashing
        geo_signature = {k: v for k, v in geo_signature.items() if v is not None}

        # Sort keys for deterministic serialization
        geo_string = json.dumps(geo_signature, sort_keys=True, default=str)
        return hashlib.sha256(geo_string.encode("utf-8")).hexdigest()

    def _load_from_db(self) -> None:
        """Load cached entries from SQLite database."""
        if not self.db_path or not os.path.exists(self.db_path):
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT room_id, geometry_hash, algorithm_version,
                       ceiling_height, detector_type, result_json,
                       timestamp, hit_count
                FROM delta_cache
                WHERE algorithm_version = ?
            """, (self.algorithm_version,))

            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                (room_id, geo_hash, algo_ver, ceiling_h,
                 det_type, result_json, ts, hit_count) = row
                try:
                    result = json.loads(result_json)
                except json.JSONDecodeError:
                    continue

                entry = CacheEntry(
                    room_id=room_id,
                    geometry_hash=geo_hash,
                    algorithm_version=algo_ver,
                    ceiling_height=ceiling_h,
                    detector_type=det_type,
                    result=result,
                    timestamp=ts,
                    hit_count=hit_count,
                )
                self._cache[room_id] = entry

            logger.info("DeltaCache: Loaded %d entries from %s", len(self._cache), self.db_path)

        except Exception as e:
            logger.warning("DeltaCache: Failed to load from %s: %s", self.db_path, e)
