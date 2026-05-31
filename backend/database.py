"""
backend/database.py — Lightweight SQLite database layer for the Digital Twin API.

This is SEPARATE from core/database.py (UniversalDataModel) which handles
BIM element persistence. This module provides simple CRUD tables for:
  - projects
  - devices
  - connections
  - reports
  - sync_status

Uses WAL mode and thread-safe connection management.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Database file location — sibling to the core fireai_universal.db
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
_DB_PATH = os.environ.get(
    "DIGITAL_TWIN_DB_PATH",
    os.path.join(_DB_DIR, "digital_twin.db")
)


class Database:
    """
    Thread-safe SQLite database for the Digital Twin REST API.

    Provides CRUD operations for projects, devices, connections,
    reports, and sync status. Uses WAL mode for concurrent read
    performance and RLock for thread safety.
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self.db_path = db_path

        # CRITICAL FIX: os.path.dirname returns '' for relative paths without
        # directory component (e.g., "digital_twin.db"). os.makedirs('') raises
        # FileNotFoundError. Always use absolute path to compute directory.
        _abs_db_path = os.path.abspath(db_path)
        _db_dir = os.path.dirname(_abs_db_path)
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True)

        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        self._conn.row_factory = sqlite3.Row

        # Performance pragmas
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-8192")  # 8 MB page cache
        self._conn.execute("PRAGMA temp_store=MEMORY")

        self._init_schema()
        logger.info(f"Digital Twin database initialized at {db_path}")

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Yield a cursor inside a locked, auto-committing transaction."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _init_schema(self) -> None:
        """Create all tables if they don't exist."""
        with self._transaction() as cur:
            # ── Projects ────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK(status IN ('active', 'archived', 'draft'))
                )
            """)

            # ── Devices ─────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z REAL NOT NULL DEFAULT 0.0,
                    rotation REAL NOT NULL DEFAULT 0.0,
                    voltage REAL NOT NULL DEFAULT 0.0,
                    current REAL NOT NULL DEFAULT 0.0,
                    load REAL NOT NULL DEFAULT 0.0,
                    properties TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # ── Connections ─────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    cable_size TEXT NOT NULL DEFAULT '1.5mm²',
                    length REAL NOT NULL DEFAULT 0.0,
                    type TEXT NOT NULL DEFAULT 'power',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # ── Reports ────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    parameters TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'completed', 'failed')),
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # ── Sync Status ────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_status (
                    project_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'synced'
                        CHECK(status IN ('syncing', 'synced', 'error')),
                    last_sync TEXT NOT NULL,
                    pending_changes INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # ── Indexes for performance ─────────────────────────────────
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_devices_project ON devices(project_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_connections_project ON connections(project_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id)"
            )
            # SAFETY FIX: Missing indexes on connections.from_id and connections.to_id
            # Every device deletion triggers DELETE FROM connections WHERE from_id=? OR to_id=?
            # Without these indexes, that's a full table scan — O(n) per deletion.
            # For a project with 10,000 connections, deleting one device scans all rows.
            # Slow operations could cause timeouts that appear as failures in a safety system.
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_connections_from ON connections(from_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_connections_to ON connections(to_id)"
            )

    # ========================================================================
    # Projects CRUD
    # ========================================================================

    def create_project(self, project_data: dict) -> dict:
        """Insert a new project and return it."""
        now = datetime.now(timezone.utc).isoformat()
        project_data.setdefault("id", str(uuid.uuid4()))
        project_data["createdAt"] = now
        project_data["updatedAt"] = now
        project_data.setdefault("status", "draft")
        project_data.setdefault("description", "")
        project_data.setdefault("author", "")

        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO projects (id, name, description, author, created_at, updated_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_data["id"],
                    project_data["name"],
                    project_data["description"],
                    project_data["author"],
                    project_data["createdAt"],
                    project_data["updatedAt"],
                    project_data["status"],
                ),
            )

        return self.get_project(project_data["id"])

    def get_project(self, project_id: str) -> Optional[dict]:
        """Get a project by ID, with device and connection counts."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
            if not row:
                return None

            # Count devices and connections
            cur.execute(
                "SELECT COUNT(*) FROM devices WHERE project_id = ?",
                (project_id,),
            )
            device_count = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM connections WHERE project_id = ?",
                (project_id,),
            )
            connection_count = cur.fetchone()[0]

        return self._row_to_project(row, device_count, connection_count)

    def list_projects(
        self,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List projects with pagination."""
        # Validate sort column to prevent SQL injection
        allowed_sorts = {"created_at", "updated_at", "name", "status", "author"}
        if sort not in allowed_sorts:
            sort = "created_at"
        if order not in ("asc", "desc"):
            order = "desc"

        with self._lock:
            cur = self._conn.cursor()

            # Get total count
            cur.execute("SELECT COUNT(*) FROM projects")
            total = cur.fetchone()[0]

            # Get paginated results
            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM projects ORDER BY {sort} {order} LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cur.fetchall()

            # Get counts for each project
            projects = []
            for row in rows:
                pid = row["id"]
                cur.execute(
                    "SELECT COUNT(*) FROM devices WHERE project_id = ?",
                    (pid,),
                )
                dc = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM connections WHERE project_id = ?",
                    (pid,),
                )
                cc = cur.fetchone()[0]
                projects.append(self._row_to_project(row, dc, cc))

        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": projects,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_project(self, project_id: str, updates: dict) -> Optional[dict]:
        """Update a project. Returns updated project or None if not found."""
        existing = self.get_project(project_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = ["updated_at = ?"]
        values = [now]

        field_map = {
            "name": "name",
            "description": "description",
            "author": "author",
            "status": "status",
        }
        for api_field, db_field in field_map.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = ?")
                values.append(updates[api_field])

        values.append(project_id)

        with self._transaction() as cur:
            cur.execute(
                f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its children (CASCADE)."""
        with self._transaction() as cur:
            cur.execute("DELETE FROM sync_status WHERE project_id = ?", (project_id,))
            cur.execute("DELETE FROM reports WHERE project_id = ?", (project_id,))
            cur.execute("DELETE FROM connections WHERE project_id = ?", (project_id,))
            cur.execute("DELETE FROM devices WHERE project_id = ?", (project_id,))
            cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cur.rowcount > 0

    def get_global_counts(self) -> dict:
        """Get total counts of devices, connections, and active projects.

        Uses efficient SQL COUNT queries instead of loading all projects
        into memory. O(1) memory regardless of project count.
        """
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM devices")
            total_devices = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM connections")
            total_connections = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'")
            active_projects = cur.fetchone()[0]
        return {
            "total_devices": total_devices,
            "total_connections": total_connections,
            "active_projects": active_projects,
        }

    # ========================================================================
    # Devices CRUD
    # ========================================================================

    def create_device(self, project_id: str, device_data: dict) -> dict:
        """Insert a new device and return it."""
        now = datetime.now(timezone.utc).isoformat()
        device_data.setdefault("id", str(uuid.uuid4()))
        device_data["projectId"] = project_id
        device_data["createdAt"] = now
        device_data["updatedAt"] = now
        device_data.setdefault("z", 0.0)
        device_data.setdefault("rotation", 0.0)
        device_data.setdefault("voltage", 0.0)
        device_data.setdefault("current", 0.0)
        device_data.setdefault("load", 0.0)
        device_data.setdefault("properties", {})

        props_json = json.dumps(device_data["properties"])

        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO devices
                   (id, project_id, type, name, category, x, y, z, rotation,
                    voltage, current, load, properties, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    device_data["id"],
                    project_id,
                    device_data["type"],
                    device_data["name"],
                    device_data["category"],
                    device_data["x"],
                    device_data["y"],
                    device_data["z"],
                    device_data["rotation"],
                    device_data["voltage"],
                    device_data["current"],
                    device_data["load"],
                    props_json,
                    device_data["createdAt"],
                    device_data["updatedAt"],
                ),
            )

        return self.get_device(project_id, device_data["id"])

    def get_device(self, project_id: str, device_id: str) -> Optional[dict]:
        """Get a device by ID within a project."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM devices WHERE id = ? AND project_id = ?",
                (device_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
        return self._row_to_device(row)

    def list_devices(
        self,
        project_id: str,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List devices in a project with pagination."""
        allowed_sorts = {"created_at", "updated_at", "name", "type", "category", "voltage", "current", "load"}
        if sort not in allowed_sorts:
            sort = "created_at"
        if order not in ("asc", "desc"):
            order = "desc"

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM devices WHERE project_id = ?",
                (project_id,),
            )
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM devices WHERE project_id = ? ORDER BY {sort} {order} LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            )
            rows = cur.fetchall()

        devices = [self._row_to_device(row) for row in rows]
        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": devices,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_device(
        self, project_id: str, device_id: str, updates: dict
    ) -> Optional[dict]:
        """Update a device. Returns updated device or None if not found."""
        existing = self.get_device(project_id, device_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = ["updated_at = ?"]
        values = [now]

        simple_fields = {
            "name": "name",
            "x": "x",
            "y": "y",
            "z": "z",
            "rotation": "rotation",
            "voltage": "voltage",
            "current": "current",
            "load": "load",
        }
        for api_field, db_field in simple_fields.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = ?")
                values.append(updates[api_field])

        # Handle properties merge
        if "properties" in updates and updates["properties"] is not None:
            merged = {**existing["properties"], **updates["properties"]}
            set_clauses.append("properties = ?")
            values.append(json.dumps(merged))

        values.extend([device_id, project_id])

        with self._transaction() as cur:
            cur.execute(
                f"UPDATE devices SET {', '.join(set_clauses)} WHERE id = ? AND project_id = ?",
                values,
            )

        return self.get_device(project_id, device_id)

    def delete_device(self, project_id: str, device_id: str) -> bool:
        """Delete a device and its associated connections.

        SAFETY NOTE: Connections referencing a deleted device become orphans
        that can corrupt voltage drop calculations, UI display, and BIM exports.
        We MUST delete all connections that reference this device before deleting
        the device itself, since there is no FK cascade on from_id/to_id.
        """
        with self._transaction() as cur:
            # Delete orphaned connections first (no FK cascade on from_id/to_id)
            cur.execute(
                "DELETE FROM connections WHERE (from_id = ? OR to_id = ?) AND project_id = ?",
                (device_id, device_id, project_id),
            )
            deleted_conns = cur.rowcount
            if deleted_conns > 0:
                import logging
                logging.getLogger(__name__).info(
                    f"Deleted {deleted_conns} orphaned connection(s) for device {device_id}"
                )
            cur.execute(
                "DELETE FROM devices WHERE id = ? AND project_id = ?",
                (device_id, project_id),
            )
            return cur.rowcount > 0

    def get_all_devices_for_project(self, project_id: str) -> list[dict]:
        """Get ALL devices for a project (no pagination, used for exports)."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM devices WHERE project_id = ?",
                (project_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_device(row) for row in rows]

    # ========================================================================
    # Connections CRUD
    # ========================================================================

    def create_connection(self, project_id: str, conn_data: dict) -> dict:
        """Insert a new connection and return it.

        SAFETY NOTE: Validates that both from_id and to_id reference existing
        devices in the same project. Without this check, connections to
        non-existent devices would corrupt voltage drop calculations, UI
        display, and BIM exports.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn_data.setdefault("id", str(uuid.uuid4()))
        conn_data["projectId"] = project_id
        conn_data["createdAt"] = now
        conn_data.setdefault("cableSize", "1.5mm²")
        conn_data.setdefault("length", 0.0)
        conn_data.setdefault("type", "power")

        with self._transaction() as cur:
            # Validate that both devices exist in this project
            from_id = conn_data["fromId"]
            to_id = conn_data["toId"]
            cur.execute(
                "SELECT id FROM devices WHERE id = ? AND project_id = ?",
                (from_id, project_id),
            )
            if not cur.fetchone():
                raise ValueError(
                    f"Cannot create connection: from_id '{from_id}' does not exist "
                    f"in project '{project_id}'"
                )
            cur.execute(
                "SELECT id FROM devices WHERE id = ? AND project_id = ?",
                (to_id, project_id),
            )
            if not cur.fetchone():
                raise ValueError(
                    f"Cannot create connection: to_id '{to_id}' does not exist "
                    f"in project '{project_id}'"
                )

            cur.execute(
                """INSERT INTO connections
                   (id, project_id, from_id, to_id, cable_size, length, type, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conn_data["id"],
                    project_id,
                    conn_data["fromId"],
                    conn_data["toId"],
                    conn_data["cableSize"],
                    conn_data["length"],
                    conn_data["type"],
                    conn_data["createdAt"],
                ),
            )

        return self.get_connection(project_id, conn_data["id"])

    def get_connection(self, project_id: str, connection_id: str) -> Optional[dict]:
        """Get a connection by ID within a project."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM connections WHERE id = ? AND project_id = ?",
                (connection_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
        return self._row_to_connection(row)

    def list_connections(
        self,
        project_id: str,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List connections in a project with pagination."""
        allowed_sorts = {"created_at", "type", "length", "cable_size"}
        if sort not in allowed_sorts:
            sort = "created_at"
        if order not in ("asc", "desc"):
            order = "desc"

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM connections WHERE project_id = ?",
                (project_id,),
            )
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM connections WHERE project_id = ? ORDER BY {sort} {order} LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            )
            rows = cur.fetchall()

        connections = [self._row_to_connection(row) for row in rows]
        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": connections,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def delete_connection(self, project_id: str, connection_id: str) -> bool:
        """Delete a connection."""
        with self._transaction() as cur:
            cur.execute(
                "DELETE FROM connections WHERE id = ? AND project_id = ?",
                (connection_id, project_id),
            )
            return cur.rowcount > 0

    def get_all_connections_for_project(self, project_id: str) -> list[dict]:
        """Get ALL connections for a project (used for exports)."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM connections WHERE project_id = ?",
                (project_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_connection(row) for row in rows]

    # ========================================================================
    # Reports CRUD
    # ========================================================================

    def create_report(self, project_id: str, report_data: dict) -> dict:
        """Insert a new report and return it."""
        now = datetime.now(timezone.utc).isoformat()
        report_data.setdefault("id", str(uuid.uuid4()))
        report_data["projectId"] = project_id
        report_data["createdAt"] = now
        report_data.setdefault("name", "")
        report_data.setdefault("parameters", {})
        report_data.setdefault("status", "pending")
        report_data["completedAt"] = None

        params_json = json.dumps(report_data["parameters"])

        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO reports
                   (id, project_id, type, name, parameters, status, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report_data["id"],
                    project_id,
                    report_data["type"],
                    report_data["name"],
                    params_json,
                    report_data["status"],
                    report_data["createdAt"],
                    report_data["completedAt"],
                ),
            )

        return self.get_report(project_id, report_data["id"])

    def get_report(self, project_id: str, report_id: str) -> Optional[dict]:
        """Get a report by ID within a project."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM reports WHERE id = ? AND project_id = ?",
                (report_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
        return self._row_to_report(row)

    def list_reports(
        self,
        project_id: str,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List reports in a project with pagination."""
        allowed_sorts = {"created_at", "type", "status", "name"}
        if sort not in allowed_sorts:
            sort = "created_at"
        if order not in ("asc", "desc"):
            order = "desc"

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM reports WHERE project_id = ?",
                (project_id,),
            )
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM reports WHERE project_id = ? ORDER BY {sort} {order} LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            )
            rows = cur.fetchall()

        reports = [self._row_to_report(row) for row in rows]
        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": reports,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_report(self, project_id: str, report_id: str, updates: dict) -> Optional[dict]:
        """Update a report. Returns updated report or None if not found."""
        set_clauses = []
        values = []

        simple_fields = {
            "status": "status",
            "name": "name",
            "completedAt": "completed_at",
        }
        for api_field, db_field in simple_fields.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = ?")
                values.append(updates[api_field])

        if "parameters" in updates and updates["parameters"] is not None:
            set_clauses.append("parameters = ?")
            values.append(json.dumps(updates["parameters"]))

        if not set_clauses:
            return self.get_report(project_id, report_id)

        values.extend([report_id, project_id])
        with self._transaction() as cur:
            cur.execute(
                f"UPDATE reports SET {', '.join(set_clauses)} WHERE id = ? AND project_id = ?",
                values,
            )

        return self.get_report(project_id, report_id)

    # ========================================================================
    # Sync Status
    # ========================================================================

    def get_sync_status(self, project_id: str) -> Optional[dict]:
        """Get sync status for a project."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM sync_status WHERE project_id = ?",
                (project_id,),
            )
            row = cur.fetchone()
            if not row:
                # Return default synced status
                return {
                    "projectId": project_id,
                    "status": "synced",
                    "lastSync": datetime.now(timezone.utc).isoformat(),
                    "pendingChanges": 0,
                    "error": None,
                }
        return self._row_to_sync(row)

    def set_sync_status(self, project_id: str, status: dict) -> dict:
        """Upsert sync status for a project."""
        with self._transaction() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO sync_status
                   (project_id, status, last_sync, pending_changes, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    project_id,
                    status.get("status", "syncing"),
                    status.get("lastSync", datetime.now(timezone.utc).isoformat()),
                    status.get("pendingChanges", 0),
                    status.get("error"),
                ),
            )

        return self.get_sync_status(project_id)

    # ========================================================================
    # Row converters (DB row -> API dict)
    # ========================================================================

    @staticmethod
    def _row_to_project(
        row: sqlite3.Row,
        device_count: int = 0,
        connection_count: int = 0,
    ) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "author": row["author"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "status": row["status"],
            "deviceCount": device_count,
            "connectionCount": connection_count,
        }

    @staticmethod
    def _row_to_device(row: sqlite3.Row) -> dict:
        props = row["properties"]
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "type": row["type"],
            "name": row["name"],
            "category": row["category"],
            "x": row["x"],
            "y": row["y"],
            "z": row["z"],
            "rotation": row["rotation"],
            "voltage": row["voltage"],
            "current": row["current"],
            "load": row["load"],
            "properties": props,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _row_to_connection(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "fromId": row["from_id"],
            "toId": row["to_id"],
            "cableSize": row["cable_size"],
            "length": row["length"],
            "type": row["type"],
            "createdAt": row["created_at"],
        }

    @staticmethod
    def _row_to_report(row: sqlite3.Row) -> dict:
        params = row["parameters"]
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                params = {}
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "type": row["type"],
            "name": row["name"],
            "parameters": params,
            "status": row["status"],
            "createdAt": row["created_at"],
            "completedAt": row["completed_at"],
        }

    @staticmethod
    def _row_to_sync(row: sqlite3.Row) -> dict:
        return {
            "projectId": row["project_id"],
            "status": row["status"],
            "lastSync": row["last_sync"],
            "pendingChanges": row["pending_changes"],
            "error": row["error"],
        }

    # ========================================================================
    # Lifecycle
    # ========================================================================

    def close(self) -> None:
        """Flush WAL and close the persistent connection."""
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.close()
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ============================================================================
# Singleton instance — imported by routers
# ============================================================================

_db: Optional[Database] = None


_db_lock = threading.Lock()


def get_db() -> Database:
    """Get or create the singleton Database instance (thread-safe)."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
    return _db
