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
- Relationships table for directed edges between elements.

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
from typing import Any, Dict, List, Optional

from core.models import (
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

logger = logging.getLogger(__name__)


class UniversalDataModel:
    """Thread-safe SQLite store for UniversalElement objects.

    Provides CRUD operations for BIM elements, relationships, and conflicts.
    Elements are stored as JSON blobs in the ``elements`` table, with
    relationships and conflicts in separate tables for query performance.

    Usage::

        udm = UniversalDataModel(db_path="udm.db")
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
        logger.info(f"UniversalDataModel initialized: db_path={db_path}")

    def _init_tables(self) -> None:
        """Create database tables if they don't exist."""
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
                CREATE INDEX IF NOT EXISTS idx_rel_from
                ON relationships(from_element_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_rel_to
                ON relationships(to_element_id)
            ''')
            self._conn.commit()

    # ── Element CRUD ──────────────────────────────────────────────────────

    def add_element(self, element: Any) -> bool:
        """Add an element to the store.

        Args:
            element: A UniversalElement or any object with ``element_id`` and ``to_dict()``.

        Returns:
            True if the element was added, False if it already exists.
        """
        with self._lock:
            try:
                element_id = element.element_id
                data = element.to_dict() if hasattr(element, 'to_dict') else {"element_id": element_id}
                now = datetime.now(timezone.utc).isoformat()

                cursor = self._conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO elements (element_id, data, created_timestamp, last_modified_timestamp) VALUES (?, ?, ?, ?)",
                    (element_id, json.dumps(data), now, now),
                )
                self._conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error adding element: {e}")
                return False

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
            except Exception as e:
                logger.error(f"Error getting element {element_id}: {e}")
                return None

    def get_all_elements(self) -> List[UniversalElement]:
        """Retrieve all elements (including soft-deleted).

        Returns:
            List of all UniversalElement objects in the store.
        """
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("SELECT data, is_deleted, version FROM elements")
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                    elem = self._dict_to_element(data, is_deleted=bool(row["is_deleted"]), version=row["version"])
                    if elem is not None:
                        result.append(elem)
                return result
            except Exception as e:
                logger.error(f"Error getting all elements: {e}")
                return []

    def update_element(self, element_id: str, updates: Dict[str, Any], source: Any = None) -> bool:
        """Update an element with the given field values.

        Args:
            element_id: The element to update.
            updates: Dictionary of field names to new values.
            source: ChangeSource enum value (for audit trail).

        Returns:
            True if the element was updated, False if not found.
        """
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

                # Merge updates
                data.update(updates)
                new_version = current_version + 1
                now = datetime.now(timezone.utc).isoformat()

                cursor.execute(
                    "UPDATE elements SET data = ?, version = ?, last_modified_timestamp = ? WHERE element_id = ?",
                    (json.dumps(data), new_version, now, element_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error updating element {element_id}: {e}")
                return False

    def delete_element(self, element_id: str, source: Any = None) -> bool:
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
            except Exception as e:
                logger.error(f"Error deleting element {element_id}: {e}")
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
                    pass
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

            # Geometry
            geom_data = data.get("geometry")
            geometry = None
            if geom_data:
                points = [Point3D(x=p["x"], y=p["y"], z=p.get("z", 0.0)) for p in geom_data.get("points", [])]
                geometry = Geometry(
                    points=points,
                    polyline_closed=geom_data.get("polyline_closed", False),
                )

            # Relationships
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
                    ))

            # Timestamps
            created_ts = None
            if data.get("created_timestamp"):
                try:
                    created_ts = datetime.fromisoformat(data["created_timestamp"])
                except (ValueError, TypeError):
                    pass

            modified_ts = None
            if data.get("last_modified_timestamp"):
                try:
                    modified_ts = datetime.fromisoformat(data["last_modified_timestamp"])
                except (ValueError, TypeError):
                    pass

            return UniversalElement(
                element_id=data.get("element_id", ""),
                properties=properties,
                geometry=geometry,
                relationships=relationships,
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
        except Exception as e:
            logger.error(f"Error deserializing element: {e}")
            return None
