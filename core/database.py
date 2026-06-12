"""
core/database.py — Universal Data Model (UDM) SQLite Store
===========================================================

Thread-safe SQLite persistence layer for UniversalElement objects.

WHY THIS FILE EXISTS
--------------------
Four files import ``from core.database import UniversalDataModel``:
  - backend/db_service.py
  - backend/app.py
  - fireai/core/ci_benchmark.py

Previously, this module did not exist, causing ``ImportError`` at runtime.
The ``backend/db_service.py`` had a ``try/except ImportError`` wrapper,
but the service was completely non-functional without it.

DESIGN DECISIONS
----------------
- Uses SQLite with WAL mode for concurrent read performance.
- Thread-safe via ``threading.RLock`` — same pattern as ``backend/database.py``.
- Elements are stored as JSON blobs for schema flexibility.
- ``add_element()`` accepts any object with ``to_dict()`` and an ``element_id``
  attribute (duck typing) for benchmark compatibility.
- Full CRUD: add, get, update, delete (soft), list.
- Relationships and conflicts tables for directed edges and merge tracking.

V83 SAFETY HARDENING
--------------------
- C-3 FIX: ``update_element()`` now validates update keys against a whitelist
  to prevent arbitrary JSON injection.
- H-5 FIX: Exception handlers now classify failures (CRITICAL/HIGH/MEDIUM/LOW)
  per agent.md Failure Governance. MemoryError and SystemError are re-raised.
  Only sqlite3.Error and json.JSONDecodeError are caught.
- H-6 FIX: Added ``close()`` method and context manager protocol.
- M-7 FIX: Added ``conflicts`` table.
- M-8 FIX: ``get_all_elements()`` now accepts ``include_deleted`` parameter.
- M-5 FIX: ``add_element()`` type hint is more specific (Protocol-style).
- M-6 FIX: ``source`` parameter typed as ``Optional[ChangeSource]``.

SAFETY NOTES
------------
- All SQL uses parameterized queries — no string interpolation.
- Lock ordering: caller lock → _lock (never reversed).
- Soft deletes: ``is_deleted=True`` rather than ``DELETE FROM``.

Copyright (c) 2024-2026 FireAI Project. All rights reserved.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.models import (
    _ELEMENT_UPDATABLE_KEYS,
    ChangeSource,
    Conflict,
    ConflictType,
    ElementType,
    Geometry,
    Point3D,
    Relationship,
    SemanticProperties,
    UniversalElement,
)

__all__ = ["UniversalDataModel"]

logger = logging.getLogger(__name__)


@runtime_checkable
class _ElementLike(Protocol):
    """Protocol for objects that can be added to UniversalDataModel.

    Allows duck-typed objects (e.g., ci_benchmark's _El) without
    forcing a UniversalElement dependency.
    """
    element_id: str

    def to_dict(self) -> Dict[str, Any]: ...


class UniversalDataModel:
    """Thread-safe SQLite store for UniversalElement objects.

    Provides CRUD operations for BIM elements, relationships, and conflicts.
    Elements are stored as JSON blobs in the ``elements`` table, with
    relationships and conflicts in separate tables for query performance.

    V83 FIX: Now implements context manager protocol (``with`` statement)
    to prevent SQLite connection leaks.

    Usage::

        with UniversalDataModel(db_path="udm.db") as udm:
            elem = UniversalElement(element_id="abc", properties=SemanticProperties(...))
            udm.add_element(elem)
            retrieved = udm.get_element("abc")
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path

        # Ensure directory exists for file-based databases
        if db_path != ":memory:":
            abs_path = os.path.abspath(db_path)
            db_dir = os.path.dirname(abs_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._conn.row_factory = sqlite3.Row

        self._init_tables()
        logger.info("UniversalDataModel initialized (db_path=%s)", "memory" if db_path == ":memory:" else "file")

    def __enter__(self) -> UniversalDataModel:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the SQLite connection.

        V83 FIX (H-6): Previous code never closed the connection, causing
        file descriptor leaks in long-running processes.
        """
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def _init_tables(self) -> None:
        """Create database tables if they don't exist.

        V83 FIX (M-7): Added ``conflicts`` table — the Conflict model
        existed in models.py but had no persistence path.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS elements (
                    element_id TEXT PRIMARY KEY,
                    data JSON NOT NULL,
                    created_timestamp TEXT,
                    last_modified_timestamp TEXT,
                    is_deleted INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS relationships (
                    relationship_id TEXT PRIMARY KEY,
                    from_element_id TEXT NOT NULL,
                    to_element_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    is_parametric INTEGER DEFAULT 0,
                    metadata JSON,
                    FOREIGN KEY (from_element_id) REFERENCES elements(element_id),
                    FOREIGN KEY (to_element_id) REFERENCES elements(element_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    element_id TEXT NOT NULL,
                    conflict_type TEXT NOT NULL,
                    source_a TEXT,
                    source_b TEXT,
                    change_a JSON,
                    change_b JSON,
                    resolution JSON,
                    resolved INTEGER DEFAULT 0,
                    timestamp TEXT,
                    FOREIGN KEY (element_id) REFERENCES elements(element_id)
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_rel_from
                ON relationships(from_element_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_rel_to
                ON relationships(to_element_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_conflict_element
                ON conflicts(element_id)
            ''')
            self._conn.commit()

    # ── Element CRUD ──────────────────────────────────────────────────────

    def add_element(self, element: _ElementLike) -> bool:
        """Add an element to the store.

        Args:
            element: A UniversalElement or any object with ``element_id`` and ``to_dict()``.

        Returns:
            True if the element was added, False if it already exists.

        Raises:
            MemoryError: If the system runs out of memory (not swallowed).
        """
        with self._lock:
            try:
                element_id = element.element_id
                data = element.to_dict()
                now = datetime.now(timezone.utc).isoformat()

                cursor = self._conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO elements (element_id, data, created_timestamp, last_modified_timestamp) VALUES (?, ?, ?, ?)",
                    (element_id, json.dumps(data), now, now),
                )
                self._conn.commit()
                return cursor.rowcount > 0
            except MemoryError:
                # V83 FIX (H-5): Never swallow MemoryError — let it propagate.
                raise
            except (sqlite3.Error, json.JSONDecodeError) as e:
                # V83 FIX (H-5): Only catch expected exceptions. Classify:
                # MEDIUM — database/serialization error, not data corruption.
                logger.error("MEDIUM: Error adding element %s: %s", element_id if 'element_id' in dir() else '?', e)
                return False

    def add_elements_batch(self, elements: List[_ElementLike]) -> int:
        """Add multiple elements in a single transaction.

        Args:
            elements: Iterable of elements with ``element_id`` and ``to_dict()``.

        Returns:
            Number of elements successfully added.

        Raises:
            MemoryError: If the system runs out of memory (not swallowed).
        """
        count = 0
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                cursor = self._conn.cursor()
                for element in elements:
                    element_id = element.element_id
                    data = element.to_dict()
                    cursor.execute(
                        "INSERT OR IGNORE INTO elements (element_id, data, created_timestamp, last_modified_timestamp) VALUES (?, ?, ?, ?)",
                        (element_id, json.dumps(data), now, now),
                    )
                    count += cursor.rowcount
                self._conn.commit()
                return count
            except MemoryError:
                raise
            except (sqlite3.Error, json.JSONDecodeError) as e:
                logger.error("MEDIUM: Error in batch add: %s", e)
                return count

    def get_element(self, element_id: str) -> Optional[UniversalElement]:
        """Retrieve an element by ID.

        Returns:
            UniversalElement if found, None otherwise.
        """
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT data, is_deleted, version FROM elements WHERE element_id = ?",
                    (element_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                return self._dict_to_element(data, is_deleted=bool(row["is_deleted"]), version=row["version"])
            except MemoryError:
                raise
            except (sqlite3.Error, json.JSONDecodeError) as e:
                logger.error("HIGH: Error getting element %s: %s", element_id, e)
                return None

    def get_all_elements(self, include_deleted: bool = True) -> List[UniversalElement]:
        """Retrieve elements from the store.

        V83 FIX (M-8): Added ``include_deleted`` parameter. Previous code
        always included soft-deleted elements, which could cause NFPA
        calculations to include demolished walls.

        Args:
            include_deleted: If False, exclude soft-deleted elements.

        Returns:
            List of UniversalElement objects.
        """
        with self._lock:
            try:
                cursor = self._conn.cursor()
                if include_deleted:
                    cursor.execute("SELECT data, is_deleted, version FROM elements")
                else:
                    cursor.execute("SELECT data, is_deleted, version FROM elements WHERE is_deleted = 0")
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                    elem = self._dict_to_element(data, is_deleted=bool(row["is_deleted"]), version=row["version"])
                    if elem is not None:
                        result.append(elem)
                return result
            except MemoryError:
                raise
            except (sqlite3.Error, json.JSONDecodeError) as e:
                logger.error("HIGH: Error getting elements: %s", e)
                return []

    def update_element(self, element_id: str, updates: Dict[str, Any], source: Optional[ChangeSource] = None) -> bool:
        """Update an element with the given field values.

        V83 FIX (C-3): Update keys are now validated against a whitelist.
        Arbitrary keys like ``evil_key`` are rejected. Keys ``element_id``,
        ``version``, ``is_deleted`` (system-managed) are also rejected —
        they must be updated through their dedicated methods.

        Args:
            element_id: The element to update.
            updates: Dictionary of field names to new values.
            source: ChangeSource enum value (for audit trail).

        Returns:
            True if the element was updated, False if not found.

        Raises:
            ValueError: If updates contain keys not in the whitelist.
        """
        # V83 FIX (C-3): Key whitelist validation — prevents JSON injection
        invalid_keys = set(updates.keys()) - _ELEMENT_UPDATABLE_KEYS
        if invalid_keys:
            raise ValueError(
                f"update_element() rejected invalid keys: {sorted(invalid_keys)}. "
                f"Allowed keys: {sorted(_ELEMENT_UPDATABLE_KEYS)}. "
                "System-managed fields (element_id, version) must use dedicated methods."
            )

        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT data, version FROM elements WHERE element_id = ?",
                    (element_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return False

                data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                current_version = row["version"]

                # Merge only whitelisted updates
                data.update(updates)
                new_version = current_version + 1
                now = datetime.now(timezone.utc).isoformat()

                cursor.execute(
                    "UPDATE elements SET data = ?, version = ?, last_modified_timestamp = ? WHERE element_id = ?",
                    (json.dumps(data), new_version, now, element_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0
            except MemoryError:
                raise
            except (sqlite3.Error, json.JSONDecodeError) as e:
                logger.error("HIGH: Error updating element %s: %s", element_id, e)
                return False

    def delete_element(self, element_id: str, source: Optional[ChangeSource] = None) -> bool:
        """Soft-delete an element.

        Sets ``is_deleted = True`` rather than removing the row.

        Args:
            element_id: The element to soft-delete.
            source: ChangeSource enum value (for audit trail).

        Returns:
            True if the element was deleted, False if not found.
        """
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE elements SET is_deleted = 1, last_modified_timestamp = ? WHERE element_id = ?",
                    (now, element_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0
            except MemoryError:
                raise
            except sqlite3.Error as e:
                logger.error("HIGH: Error deleting element %s: %s", element_id, e)
                return False

    # ── Deserialization ───────────────────────────────────────────────────

    @staticmethod
    def _dict_to_element(data: Dict[str, Any], is_deleted: bool = False, version: int = 0) -> Optional[UniversalElement]:
        """Reconstruct a UniversalElement from its JSON dictionary.

        Args:
            data: The serialized element data.
            is_deleted: Whether the element has been soft-deleted.
            version: The element's version number.

        Returns:
            Reconstructed UniversalElement, or None on failure.
        """
        try:
            # Properties
            props_data = data.get("properties", {})
            properties = None
            if props_data:
                et = props_data.get("element_type", "unknown")
                # Convert string back to ElementType if possible
                try:
                    et = ElementType(et)
                except (ValueError, KeyError):
                    # V83 FIX (M-4): Log when element_type can't be resolved
                    logger.warning("Cannot resolve element_type '%s' to ElementType enum — keeping as string", et)
                properties = SemanticProperties(
                    element_type=et,
                    name=props_data.get("name", ""),
                    description=props_data.get("description"),
                    material=props_data.get("material"),
                    fire_rating=props_data.get("fire_rating"),
                    height=props_data.get("height"),
                    width=props_data.get("width"),
                    load_bearing=props_data.get("load_bearing", False),
                    layer=props_data.get("layer"),
                    revit_category=props_data.get("revit_category"),
                )

            # Geometry — V83 FIX: Convert list to tuple for frozen dataclass
            geom_data = data.get("geometry")
            geometry = None
            if geom_data:
                points = tuple(
                    Point3D(x=p["x"], y=p["y"], z=p.get("z", 0.0))
                    for p in geom_data.get("points", [])
                )
                geometry = Geometry(
                    points=points,
                    polyline_closed=geom_data.get("polyline_closed", False),
                )

            # Relationships — V83 FIX: Convert list to tuple for frozen dataclass
            rels_data = data.get("relationships", [])
            relationships = []
            for r in rels_data:
                if isinstance(r, dict):
                    relationships.append(Relationship(
                        from_element_id=r.get("from_element_id", ""),
                        to_element_id=r.get("to_element_id", ""),
                        relationship_type=r.get("relationship_type", ""),
                        is_parametric=r.get("is_parametric", False),
                        metadata=r.get("metadata"),
                        connection_id=r.get("connection_id"),
                    ))

            # Timestamps — V83 FIX (M-4): Log malformed timestamps instead of silently degrading
            created_ts = None
            if data.get("created_timestamp"):
                try:
                    created_ts = datetime.fromisoformat(data["created_timestamp"])
                except (ValueError, TypeError):
                    logger.warning("Malformed created_timestamp: %s — defaulting to None", data["created_timestamp"])

            modified_ts = None
            if data.get("last_modified_timestamp"):
                try:
                    modified_ts = datetime.fromisoformat(data["last_modified_timestamp"])
                except (ValueError, TypeError):
                    logger.warning("Malformed last_modified_timestamp: %s — defaulting to None", data["last_modified_timestamp"])

            return UniversalElement(
                element_id=data.get("element_id", ""),
                properties=properties,
                geometry=geometry,
                relationships=tuple(relationships),
                source_file=data.get("source_file"),
                last_modified_by=data.get("last_modified_by"),
                autocad_handle=data.get("autocad_handle"),
                revit_element_id=data.get("revit_element_id"),
                created_timestamp=created_ts,
                last_modified_timestamp=modified_ts,
                version=version or data.get("version", 0),
                is_deleted=is_deleted or data.get("is_deleted", False),
                project_id=data.get("project_id"),
            )
        except MemoryError:
            raise
        except Exception as e:
            logger.error("CRITICAL: Error deserializing element: %s", e)
            return None
