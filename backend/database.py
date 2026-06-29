"""
backend/database.py — Lightweight database layer for the Digital Twin API.

Supports two backends:
  - SQLite (default) — for single-instance development/deployment
  - PostgreSQL — for production, multi-replica, and horizontally-scaled deployments

This is SEPARATE from core/database.py (UniversalDataModel) which handles
BIM element persistence. This module provides simple CRUD tables for:
  - projects
  - devices
  - connections
  - reports
  - sync_status
  - sync_operations

SQLite uses WAL mode and thread-safe connection management.
PostgreSQL uses psycopg2 with connection pooling.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Database file location — sibling to the core fireai_universal.db
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
_DB_PATH = os.environ.get("DIGITAL_TWIN_DB_PATH", os.path.join(_DB_DIR, "digital_twin.db"))

# PostgreSQL support: if DATABASE_URL starts with postgres:// or postgresql://,
# use psycopg2 + connection pooling instead of SQLite.
_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = _DATABASE_URL.startswith(("postgres://", "postgresql://"))


class Database:
    """
    Thread-safe database for the Digital Twin REST API.

    Supports two backends:
      - SQLite (default) — for single-instance development/deployment
      - PostgreSQL — for production, multi-replica, and horizontally-scaled deployments

    The backend is selected via the DATABASE_URL environment variable:
      - If DATABASE_URL starts with "postgres://" or "postgresql://", PostgreSQL is used.
      - Otherwise, SQLite is used with the DIGITAL_TWIN_DB_PATH or default path.

    PostgreSQL mode uses connection pooling (psycopg2.pool) for concurrent access
    and is compatible with multi-instance deployments (K8s, Docker Compose).
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._is_postgres = _USE_POSTGRES

        if self._is_postgres:
            self._init_postgres()
        else:
            self._init_sqlite(db_path)

    def _ph(self) -> str:
        """Return the parameter placeholder for the current backend: ? (SQLite) or %s (PostgreSQL)."""
        return "%s" if self._is_postgres else "?"

    def _init_sqlite(self, db_path: str) -> None:
        """Initialize SQLite connection with performance pragmas."""
        # V127 SAFETY FIX: guard makedirs for :memory: and empty paths.
        # os.path.dirname(os.path.abspath(':memory:')) returns the CWD, which
        # would trigger an unnecessary makedirs on the project root. Skip
        # directory creation entirely for in-memory databases.
        _db_dir = (
            os.path.dirname(os.path.abspath(db_path))
            if db_path not in (":memory:", "")
            else None
        )
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True)

        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row

        # Performance pragmas
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-8192")  # 8 MB page cache
        self._conn.execute("PRAGMA temp_store=MEMORY")

        self._init_schema()
        logger.info("Digital Twin database initialized (SQLite) at %s", db_path)

    def _init_postgres(self) -> None:
        """Initialize PostgreSQL connection pool."""
        try:
            import psycopg2  # noqa: F401  (imported to surface ImportError early)
            from psycopg2 import pool as pg_pool
        except ImportError:
            raise ImportError(
                "PostgreSQL mode requires psycopg2. Install it with: "
                "pip install psycopg2-binary  OR  pip install psycopg2"
            )

        self._pg_pool = pg_pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=_DATABASE_URL,
        )
        self._conn = None  # Not used in Postgres mode
        logger.info(
            f"Digital Twin database initialized (PostgreSQL) — "
            f"pool: 2–20 connections, URL: {_DATABASE_URL.split('@')[-1]}"
        )
        self._init_schema_pg()

    @contextmanager
    def _pg_cursor(self):
        """Get a cursor from the PostgreSQL connection pool."""
        from psycopg2.extras import RealDictCursor
        conn = self._pg_pool.getconn()
        try:
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
        finally:
            self._pg_pool.putconn(conn)

    @contextmanager
    def _transaction(self):
        """
        Yield a cursor inside a locked, auto-committing transaction.

        Returns a SQLite cursor or PostgreSQL cursor depending on the backend.
        """
        if self._is_postgres:
            with self._pg_cursor() as cur:
                yield cur
        else:
            with self._lock:
                cur = self._conn.cursor()
                try:
                    yield cur
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise

    def _init_schema_pg(self) -> None:
        """
        Create all tables in PostgreSQL — schema MUST match _init_schema() (SQLite) exactly.

        CRITICAL: The PostgreSQL schema must be identical to the SQLite schema in column
        names, types, constraints, and indexes. Any drift will cause runtime errors when
        the same CRUD queries (which use {self._ph()}) execute against PostgreSQL.
        The SQLite schema is the source of truth — PG uses DOUBLE PRECISION instead of
        REAL and SERIALLY for auto-increment, but column names and constraints must match.
        """
        with self._pg_cursor() as cur:
            # ── Projects ────────────────────────────────────────────
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

            # ── Devices ─────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    x DOUBLE PRECISION NOT NULL,
                    y DOUBLE PRECISION NOT NULL,
                    z DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    rotation DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    voltage DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    current DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    load DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    properties TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # ── Connections (MUST match SQLite schema exactly) ──────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    cable_size TEXT NOT NULL DEFAULT '1.5mm²',
                    length DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    type TEXT NOT NULL DEFAULT 'power',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # ── Reports (MUST match SQLite schema exactly) ──────────
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

            # ── Sync Status (MUST match SQLite schema exactly) ──────
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

            # ── Sync Operations (MUST match SQLite schema exactly) ──
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_operations (
                    id SERIAL PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    target_db TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    last_sync_at TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0
                )
            """)

            # ── Indexes (MUST match SQLite indexes exactly) ─────────
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_project ON devices(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_project ON connections(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_from ON connections(from_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_to ON connections(to_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_entity ON sync_operations(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_status ON sync_operations(status)")

        logger.info("PostgreSQL schema initialized successfully (matching SQLite schema)")

    def _init_schema(self) -> None:
        """Create all tables if they don't exist (SQLite)."""
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

            # ── Sync Operations (granular per-entity sync tracking) ────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    target_db TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    last_sync_at TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0
                )
            """)

            # ── Indexes for performance ─────────────────────────────────
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_project ON devices(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_project ON connections(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id)")
            # SAFETY FIX: Missing indexes on connections.from_id and connections.to_id
            # Every device deletion triggers DELETE FROM connections WHERE from_id=? OR to_id=?
            # Without these indexes, that's a full table scan — O(n) per deletion.
            # For a project with 10,000 connections, deleting one device scans all rows.
            # Slow operations could cause timeouts that appear as failures in a safety system.
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_from ON connections(from_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_to ON connections(to_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_entity ON sync_operations(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_status ON sync_operations(status)")

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
                f"""INSERT INTO projects (id, name, description, author, created_at, updated_at, status)
                   VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()})""",
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

    def get_project(self, project_id: str) -> dict | None:
        """Get a project by ID, with device and connection counts — single query."""
        with self._transaction() as cur:
            cur.execute(
                f"""
                SELECT
                    p.*,
                    COALESCE(d.device_count, 0) AS device_count,
                    COALESCE(c.connection_count, 0) AS connection_count
                FROM projects p
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS device_count
                    FROM devices
                    GROUP BY project_id
                ) d ON p.id = d.project_id
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS connection_count
                    FROM connections
                    GROUP BY project_id
                ) c ON p.id = c.project_id
                WHERE p.id = {self._ph()}
                """,
                (project_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

        return self._row_to_project(row, row["device_count"], row["connection_count"])

    def list_projects(
        self,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List projects with pagination — uses JOIN to avoid N+1 counts."""
        # Whitelist sort columns and order direction to prevent SQL injection
        _ALLOWED_PROJECT_SORTS = {"id", "name", "created_at", "updated_at", "status", "author"}
        if sort not in _ALLOWED_PROJECT_SORTS:
            sort = "created_at"
        order = "DESC" if order.upper() not in ("ASC", "DESC") else order.upper()

        with self._transaction() as cur:
            # Get total count
            cur.execute("SELECT COUNT(*) FROM projects")
            total = cur.fetchone()[0]

            # Get paginated results with device/connection counts in ONE query (no N+1)
            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                    p.*,
                    COALESCE(d.device_count, 0) AS device_count,
                    COALESCE(c.connection_count, 0) AS connection_count
                FROM projects p
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS device_count
                    FROM devices
                    GROUP BY project_id
                ) d ON p.id = d.project_id
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS connection_count
                    FROM connections
                    GROUP BY project_id
                ) c ON p.id = c.project_id
                ORDER BY p.{sort} {order}
                LIMIT {self._ph()} OFFSET {self._ph()}
                """,
                (limit, offset),
            )
            rows = cur.fetchall()

            projects = [
                self._row_to_project(row, row["device_count"], row["connection_count"])
                for row in rows
            ]

        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": projects,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_project(self, project_id: str, updates: dict) -> dict | None:
        """Update a project. Returns updated project or None if not found."""
        existing = self.get_project(project_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"updated_at = {self._ph()}"]
        values = [now]

        field_map = {
            "name": "name",
            "description": "description",
            "author": "author",
            "status": "status",
        }
        for api_field, db_field in field_map.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = {self._ph()}")
                values.append(updates[api_field])

        values.append(project_id)

        with self._transaction() as cur:
            cur.execute(
                f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = {self._ph()}",
                values,
            )

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its children (CASCADE)."""
        with self._transaction() as cur:
            cur.execute(f"DELETE FROM sync_status WHERE project_id = {self._ph()}", (project_id,))
            cur.execute(f"DELETE FROM reports WHERE project_id = {self._ph()}", (project_id,))
            cur.execute(f"DELETE FROM connections WHERE project_id = {self._ph()}", (project_id,))
            cur.execute(f"DELETE FROM devices WHERE project_id = {self._ph()}", (project_id,))
            cur.execute(f"DELETE FROM projects WHERE id = {self._ph()}", (project_id,))
            return cur.rowcount > 0

    def get_global_counts(self) -> dict:
        """
        Get total counts of devices, connections, and active projects.

        Uses efficient SQL COUNT queries instead of loading all projects
        into memory. O(1) memory regardless of project count.
        """
        with self._transaction() as cur:
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
                f"""INSERT INTO devices
                   (id, project_id, type, name, category, x, y, z, rotation,
                    voltage, current, load, properties, created_at, updated_at)
                   VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()})""",
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

    def get_device(self, project_id: str, device_id: str) -> dict | None:
        """Get a device by ID within a project."""
        with self._transaction() as cur:
            cur.execute(
                f"SELECT * FROM devices WHERE id = {self._ph()} AND project_id = {self._ph()}",
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
        # Whitelist sort columns and order direction to prevent SQL injection
        _ALLOWED_DEVICE_SORTS = {
            "id",
            "created_at",
            "updated_at",
            "name",
            "type",
            "category",
            "voltage",
            "current",
            "load",
        }
        if sort not in _ALLOWED_DEVICE_SORTS:
            sort = "created_at"
        order = "DESC" if order.upper() not in ("ASC", "DESC") else order.upper()

        with self._transaction() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM devices WHERE project_id = {self._ph()}",
                (project_id,),
            )
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM devices WHERE project_id = {self._ph()} ORDER BY {sort} {order} LIMIT {self._ph()} OFFSET {self._ph()}",
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

    def update_device(self, project_id: str, device_id: str, updates: dict) -> dict | None:
        """Update a device. Returns updated device or None if not found."""
        existing = self.get_device(project_id, device_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"updated_at = {self._ph()}"]
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
                set_clauses.append(f"{db_field} = {self._ph()}")
                values.append(updates[api_field])

        # Handle properties merge
        if "properties" in updates and updates["properties"] is not None:
            merged = {**existing["properties"], **updates["properties"]}
            set_clauses.append(f"properties = {self._ph()}")
            values.append(json.dumps(merged))

        values.extend([device_id, project_id])

        with self._transaction() as cur:
            cur.execute(
                f"UPDATE devices SET {', '.join(set_clauses)} WHERE id = {self._ph()} AND project_id = {self._ph()}",
                values,
            )

        return self.get_device(project_id, device_id)

    def delete_device(self, project_id: str, device_id: str) -> bool:
        """
        Delete a device and its associated connections.

        SAFETY NOTE: Connections referencing a deleted device become orphans
        that can corrupt voltage drop calculations, UI display, and BIM exports.
        We MUST delete all connections that reference this device before deleting
        the device itself, since there is no FK cascade on from_id/to_id.
        """
        with self._transaction() as cur:
            # Delete orphaned connections first (no FK cascade on from_id/to_id)
            cur.execute(
                f"DELETE FROM connections WHERE (from_id = {self._ph()} OR to_id = {self._ph()}) AND project_id = {self._ph()}",
                (device_id, device_id, project_id),
            )
            deleted_conns = cur.rowcount
            if deleted_conns > 0:
                logger.info(
                    f"Deleted {deleted_conns} orphaned connection(s) for device {device_id}"
                )
            cur.execute(
                f"DELETE FROM devices WHERE id = {self._ph()} AND project_id = {self._ph()}",
                (device_id, project_id),
            )
            return cur.rowcount > 0

    def get_all_devices_for_project(self, project_id: str) -> list[dict]:
        """Get ALL devices for a project (no pagination, used for exports)."""
        with self._transaction() as cur:
            cur.execute(
                f"SELECT * FROM devices WHERE project_id = {self._ph()}",
                (project_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_device(row) for row in rows]

    # ========================================================================
    # Connections CRUD
    # ========================================================================

    def create_connection(self, project_id: str, conn_data: dict) -> dict:
        """
        Insert a new connection and return it.

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
                f"SELECT id FROM devices WHERE id = {self._ph()} AND project_id = {self._ph()}",
                (from_id, project_id),
            )
            if not cur.fetchone():
                raise ValueError(
                    f"Cannot create connection: from_id '{from_id}' does not exist in project '{project_id}'"
                )
            cur.execute(
                f"SELECT id FROM devices WHERE id = {self._ph()} AND project_id = {self._ph()}",
                (to_id, project_id),
            )
            if not cur.fetchone():
                raise ValueError(f"Cannot create connection: to_id '{to_id}' does not exist in project '{project_id}'")

            cur.execute(
                f"""INSERT INTO connections
                   (id, project_id, from_id, to_id, cable_size, length, type, created_at)
                   VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()})""",
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

    def get_connection(self, project_id: str, connection_id: str) -> dict | None:
        """Get a connection by ID within a project."""
        with self._transaction() as cur:
            cur.execute(
                f"SELECT * FROM connections WHERE id = {self._ph()} AND project_id = {self._ph()}",
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
        # Whitelist sort columns and order direction to prevent SQL injection.
        # CodeQL: py/sql-injection — sort and order are SAFE because they are
        # validated against a strict whitelist BEFORE being used in the query.
        # If an attacker passes sort="; DROP TABLE connections; --", it will
        # not match the whitelist and will be replaced with "created_at".
        _ALLOWED_CONNECTION_SORTS = frozenset({"id", "created_at", "type", "length", "cable_size"})
        if sort not in _ALLOWED_CONNECTION_SORTS:
            sort = "created_at"
        # order is restricted to exactly ASC or DESC (no other values allowed)
        order = "ASC" if order.upper() == "ASC" else "DESC"

        with self._transaction() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM connections WHERE project_id = {self._ph()}",
                (project_id,),
            )
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            # sort and order are SAFE here (whitelisted above) — lgtm[py/sql-injection]
            cur.execute(
                f"SELECT * FROM connections WHERE project_id = {self._ph()} ORDER BY {sort} {order} LIMIT {self._ph()} OFFSET {self._ph()}",
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
                f"DELETE FROM connections WHERE id = {self._ph()} AND project_id = {self._ph()}",
                (connection_id, project_id),
            )
            return cur.rowcount > 0

    def update_connection(self, project_id: str, connection_id: str, updates: dict) -> dict | None:
        """
        Update specific fields of a connection.

        Args:
            project_id: Project the connection belongs to.
            connection_id: Connection to update.
            updates: Dict of fields to update (e.g., {"cableSize": "2.5mm²"}).

        Returns:
            Updated connection dict, or None if not found.

        """
        # First verify the connection exists
        connection = self.get_connection(project_id, connection_id)
        if not connection:
            return None

        # Map API camelCase fields to database snake_case columns
        _FIELD_MAP = {
            "cableSize": "cable_size",
            "length": "length",
            "type": "type",
            "fromId": "from_id",
            "toId": "to_id",
        }
        set_parts = []
        values = []
        for field, value in updates.items():
            if field in _FIELD_MAP:
                set_parts.append(f"{_FIELD_MAP[field]} = {self._ph()}")
                values.append(value)

        if not set_parts:
            return connection

        values.append(connection_id)
        values.append(project_id)

        with self._transaction() as cur:
            cur.execute(
                f"UPDATE connections SET {', '.join(set_parts)} WHERE id = {self._ph()} AND project_id = {self._ph()}",
                values,
            )
            if cur.rowcount == 0:
                return None

        return self.get_connection(project_id, connection_id)

    def get_all_connections_for_project(self, project_id: str) -> list[dict]:
        """Get ALL connections for a project (used for exports)."""
        with self._transaction() as cur:
            cur.execute(
                f"SELECT * FROM connections WHERE project_id = {self._ph()}",
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
                f"""INSERT INTO reports
                   (id, project_id, type, name, parameters, status, created_at, completed_at)
                   VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()})""",
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

    def get_report(self, project_id: str, report_id: str) -> dict | None:
        """Get a report by ID within a project."""
        with self._transaction() as cur:
            cur.execute(
                f"SELECT * FROM reports WHERE id = {self._ph()} AND project_id = {self._ph()}",
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
        # Whitelist sort columns and order direction to prevent SQL injection.
        # CodeQL: py/sql-injection — sort and order are SAFE (whitelisted).
        _ALLOWED_REPORT_SORTS = frozenset({"id", "created_at", "type", "status", "name"})
        if sort not in _ALLOWED_REPORT_SORTS:
            sort = "created_at"
        order = "ASC" if order.upper() == "ASC" else "DESC"

        with self._transaction() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM reports WHERE project_id = {self._ph()}",
                (project_id,),
            )
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            # sort and order are SAFE here (whitelisted above) — lgtm[py/sql-injection]
            cur.execute(
                f"SELECT * FROM reports WHERE project_id = {self._ph()} ORDER BY {sort} {order} LIMIT {self._ph()} OFFSET {self._ph()}",
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

    def update_report(self, project_id: str, report_id: str, updates: dict) -> dict | None:
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
                set_clauses.append(f"{db_field} = {self._ph()}")
                values.append(updates[api_field])

        if "parameters" in updates and updates["parameters"] is not None:
            set_clauses.append(f"parameters = {self._ph()}")
            values.append(json.dumps(updates["parameters"]))

        if not set_clauses:
            return self.get_report(project_id, report_id)

        values.extend([report_id, project_id])
        with self._transaction() as cur:
            cur.execute(
                f"UPDATE reports SET {', '.join(set_clauses)} WHERE id = {self._ph()} AND project_id = {self._ph()}",
                values,
            )

        return self.get_report(project_id, report_id)

    # ========================================================================
    # Sync Status
    # ========================================================================

    def get_sync_status(self, project_id: str) -> dict | None:
        """Get sync status for a project."""
        with self._transaction() as cur:
            cur.execute(
                f"SELECT * FROM sync_status WHERE project_id = {self._ph()}",
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
            if self._is_postgres:
                cur.execute(
                    f"""
                    INSERT INTO sync_status (project_id, status, last_sync, pending_changes, error)
                    VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()})
                    ON CONFLICT (project_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_sync = EXCLUDED.last_sync,
                        pending_changes = EXCLUDED.pending_changes,
                        error = EXCLUDED.error
                    """,
                    (
                        project_id,
                        status.get("status", "syncing"),
                        status.get("lastSync", datetime.now(timezone.utc).isoformat()),
                        status.get("pendingChanges", 0),
                        status.get("error"),
                    ),
                )
            else:
                cur.execute(
                    f"""INSERT OR REPLACE INTO sync_status
                       (project_id, status, last_sync, pending_changes, error)
                       VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()})""",
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
    # Sync Operations (granular per-entity sync tracking)
    # ========================================================================

    def record_sync(
        self,
        entity_type: str,
        entity_id: str,
        target_db: str,
        status: str,
        error: str | None = None,
    ) -> int:
        """
        Record a sync operation status.

        Inserts a new row or updates an existing pending row for the same
        entity_type + entity_id + target_db combination.

        Args:
            entity_type: Type of entity (e.g. "project", "device", "connection").
            entity_id: ID of the entity being synced.
            target_db: Target database name (e.g. "udm_elements").
            status: Sync status — "pending", "syncing", "synced", or "error".
            error: Optional error message if status is "error".

        Returns:
            The row ID of the inserted/updated sync operation.

        """
        now = datetime.now(timezone.utc).isoformat()

        with self._transaction() as cur:
            # Check for an existing pending/syncing record for this entity
            cur.execute(
                f"""SELECT id, status, retry_count FROM sync_operations
                   WHERE entity_type = {self._ph()} AND entity_id = {self._ph()} AND target_db = {self._ph()}
                   ORDER BY id DESC LIMIT 1""",
                (entity_type, entity_id, target_db),
            )
            existing = cur.fetchone()

            if existing and existing["status"] in ("pending", "syncing", "error"):
                # Update existing record
                row_id = existing["id"]
                retry_count = existing["retry_count"]
                if status == "error":
                    retry_count += 1
                cur.execute(
                    f"""UPDATE sync_operations
                       SET status = {self._ph()}, last_sync_at = {self._ph()}, error_message = {self._ph()}, retry_count = {self._ph()}
                       WHERE id = {self._ph()}""",
                    (status, now, error, retry_count, row_id),
                )
            else:
                # Insert new record
                cur.execute(
                    f"""INSERT INTO sync_operations
                       (entity_type, entity_id, target_db, status, last_sync_at,
                        error_message, retry_count)
                       VALUES ({self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, {self._ph()}, 0)""",
                    (entity_type, entity_id, target_db, status, now, error),
                )
                row_id = cur.lastrowid

        return row_id

    def get_pending_syncs(self, max_retries: int = 3) -> list:
        """
        Get sync operations that need to be retried.

        Returns all operations with status "pending" or "error" where
        retry_count has not exceeded max_retries.
        """
        with self._transaction() as cur:
            cur.execute(
                f"""SELECT * FROM sync_operations
                   WHERE status IN ('pending', 'error')
                     AND retry_count < {self._ph()}
                   ORDER BY id ASC""",
                (max_retries,),
            )
            rows = cur.fetchall()

        return [
            {
                "id": row["id"],
                "entityType": row["entity_type"],
                "entityId": row["entity_id"],
                "targetDb": row["target_db"],
                "status": row["status"],
                "lastSyncAt": row["last_sync_at"],
                "errorMessage": row["error_message"],
                "retryCount": row["retry_count"],
            }
            for row in rows
        ]

    # ========================================================================
    # Row converters (DB row -> API dict)
    # ========================================================================

    @staticmethod
    def _row_to_project(
        row: Any,
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
    def _row_to_device(row: Any) -> dict:
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
    def _row_to_connection(row: Any) -> dict:
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
    def _row_to_report(row: Any) -> dict:
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
    def _row_to_sync(row: Any) -> dict:
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
        """Close the database connection or pool."""
        if self._is_postgres:
            if hasattr(self, '_pg_pool') and self._pg_pool:
                self._pg_pool.closeall()
                logger.info("PostgreSQL connection pool closed")
        else:
            with suppress(Exception):
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception as e:
            logger.debug("Database.__del__ close failed: %s", e)


# ============================================================================
# Singleton instance — imported by routers
# ============================================================================

_db: Database | None = None


_db_lock = threading.Lock()


def get_db() -> Database:
    """Get or create the singleton Database instance (thread-safe)."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
    return _db
