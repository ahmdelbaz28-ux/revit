# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR â€” S3776: ...') are preserved.
"""
backend/database.py â€” Lightweight database layer for the Digital Twin API.

Supports two backends:
  - SQLite (default) â€” for single-instance development/deployment
  - PostgreSQL â€” for production, multi-replica, and horizontally-scaled deployments

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
import uuid  # noqa: F401 â€” kept for backward compat with modules importing from database
from contextlib import contextmanager, suppress
from datetime import datetime, timezone  # noqa: F401 â€” kept for backward compat
from typing import Any

# Import configuration
from backend.config import config
from backend.db.repositories.connection import ConnectionRepository
from backend.db.repositories.device import DeviceRepository
from backend.db.repositories.project import ProjectRepository
from backend.db.repositories.report import ReportRepository
from backend.db.repositories.sync import SyncRepository

logger = logging.getLogger(__name__)

# Database file location â€” sibling to the core fireai_universal.db
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
_DB_PATH = config.DIGITAL_TWIN_DB_PATH

# PostgreSQL support: if DATABASE_URL starts with postgres://, postgresql://,
# or postgresql+asyncpg://, use psycopg2 + connection pooling instead of SQLite.
# NOTE: These are read at module import-time for backward compat, but the
# Database class also re-reads them at config time to support late-binding
# (e.g. Hugging Face Spaces that inject secrets after module import).
_DATABASE_URL = config.DATABASE_URL
_USE_POSTGRES = _DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://"))


class Database:
    """
    Thread-safe database for the Digital Twin REST API.

    Supports two backends:
      - SQLite (default) â€” for single-instance development/deployment
      - PostgreSQL â€” for production, multi-replica, and horizontally-scaled deployments

    The backend is selected via the DATABASE_URL environment variable:
      - If DATABASE_URL starts with "postgres://", "postgresql://", or "postgresql+asyncpg://",
        PostgreSQL is used.
      - Otherwise, SQLite is used with the DIGITAL_TWIN_DB_PATH or default path.

    PostgreSQL mode uses connection pooling (psycopg2.pool) for concurrent access
    and is compatible with multi-instance deployments (K8s, Docker Compose).
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        # Re-read DATABASE_URL at instantiation time (not just at module import)
        # so that environment variables injected after module load (e.g. HF Secrets)
        # are correctly picked up when the singleton is first created.
        database_url = config.DATABASE_URL
        self._is_postgres = database_url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://"))
        if self._is_postgres:
            # Store the actual URL on the instance for _init_postgres to use
            self._database_url = database_url
            self._init_postgres()
        else:
            self._init_sqlite(db_path)

        # Initialize Repositories (pattern deepening refactor)
        self.projects = ProjectRepository(self)
        self.devices = DeviceRepository(self)
        self.connections = ConnectionRepository(self)
        self.reports = ReportRepository(self)
        self.sync = SyncRepository(self)

    def _ph(self) -> str:
        """Return the parameter placeholder for the current backend: ? (SQLite) or %s (PostgreSQL)."""
        return "%s" if self._is_postgres else "?"

    def _init_sqlite(self, db_path: str) -> None:
        """Initialize SQLite connection with performance pragmas."""
        # os.path.dirname(os.path.abspath(':memory:')) returns the CWD, which
        # would trigger an unnecessary makedirs on the project root. Skip
        # directory creation entirely for in-memory databases.
        _db_dir = (
            os.path.dirname(os.path.abspath(db_path))
            if db_path not in (":memory:", "")
            else None
        )
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True, mode=0o700)

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
        """Initialize PostgreSQL connection pool.

        Fallback chain (added 2026-07-09):
          1. Try DATABASE_URL (primary â€” usually Supabase in standard config).
          2. If the connection fails (e.g. HF Spaces free tier cannot reach
             Supabase's IPv6-only endpoint), fall back to NEON_DATABASE_URL
             (IPv4-direct, always reachable from any container runtime).
          3. If both fail, raise the original DATABASE_URL error so the
             application surfaces the primary misconfiguration, not a
             secondary one.

        This makes BOTH databases work together: Supabase stays as the
        standard primary; Neon is the automatic IPv4 fallback.
        """
        try:
            import psycopg2  # noqa: F401  (imported to surface ImportError early)
            from psycopg2 import pool as pg_pool
        except ImportError:
            raise ImportError(
                "PostgreSQL mode requires psycopg2. Install it with: "
                "pip install psycopg2-binary  OR  pip install psycopg2"
            )

        db_url = getattr(self, '_database_url', _DATABASE_URL)
        neon_url = os.environ.get("NEON_DATABASE_URL", "")

        # Try the primary DATABASE_URL first
        try:
            self._pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                dsn=db_url,
            )
            # Smoke-test the connection â€” pool creation is lazy on some drivers
            test_conn = self._pg_pool.getconn()
            try:
                cur = test_conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
            finally:
                self._pg_pool.putconn(test_conn)
            self._conn = None
            logger.info(
                "Digital Twin database initialized (PostgreSQL) â€” "
                "pool: 2â€“20 connections, URL: %s",
                db_url.split("@")[-1],
            )
        except Exception as primary_exc:
            if not neon_url or neon_url == db_url:
                # No fallback available â€” raise the original error
                raise
            logger.warning(
                "Primary DATABASE_URL failed (%s); falling back to NEON_DATABASE_URL (%s)",
                type(primary_exc).__name__,
                neon_url.split("@")[-1],
            )
            # Close the partially-initialized pool if it was created
            try:
                self._pg_pool.closeall()
            except Exception:
                                logger.debug("Suppressed Exception in database.py", exc_info=True)
            self._database_url = neon_url
            self._pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                dsn=neon_url,
            )
            self._conn = None
            logger.info(
                "Digital Twin database initialized (PostgreSQL via NEON_DATABASE_URL fallback) â€” "
                "pool: 2â€“20 connections, URL: %s",
                neon_url.split("@")[-1],
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

    def _scalar(self, cur, key: str = "count"):
        """Read a scalar value from a cursor â€” works for BOTH SQLite tuples
        (`row[0]`) and PostgreSQL RealDictCursor rows (`row['count']`).

        Added 2026-07-09: the legacy code path assumed tuple cursors
        (`cur.fetchone()[0]`) which is correct for SQLite but raises
        `KeyError: 0` against the RealDictCursor used in PostgreSQL mode.
        This helper transparently handles both cursor types so the same
        SQL (`SELECT COUNT(*) FROM ...`) works on either backend.
        """
        row = cur.fetchone()
        if row is None:
            return 0
        if isinstance(row, dict):
            # RealDictCursor / RealDictRow â€” keys are column names
            return row.get(key, row.get(next(iter(row.keys())), 0))
        # SQLite Row or plain tuple â€” index by position
        return row[0]

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
        Create all tables in PostgreSQL â€” schema MUST match _init_schema() (SQLite) exactly.

        CRITICAL: The PostgreSQL schema must be identical to the SQLite schema in column
        names, types, constraints, and indexes. Any drift will cause runtime errors when
        the same CRUD queries (which use {self._ph()}) execute against PostgreSQL.
        The SQLite schema is the source of truth â€” PG uses DOUBLE PRECISION instead of
        REAL and SERIALLY for auto-increment, but column names and constraints must match.
        """
        with self._pg_cursor() as cur:
            # â”€â”€ Projects â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Devices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Connections (MUST match SQLite schema exactly) â”€â”€â”€â”€â”€â”€
            cur.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    cable_size TEXT NOT NULL DEFAULT '1.5mmآ²',
                    length DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    type TEXT NOT NULL DEFAULT 'power',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # â”€â”€ Reports (MUST match SQLite schema exactly) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Sync Status (MUST match SQLite schema exactly) â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Sync Operations (MUST match SQLite schema exactly) â”€â”€
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

            # â”€â”€ Indexes (MUST match SQLite indexes exactly) â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_project ON devices(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_project ON connections(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_from ON connections(from_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_to ON connections(to_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_entity ON sync_operations(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_status ON sync_operations(status)")

            # â”€â”€ Audit Log Table for NFPA 72 Compliance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,  -- CREATE, UPDATE, DELETE, VIEW
                    entity_type TEXT NOT NULL,  -- projects, devices, etc.
                    entity_id TEXT NOT NULL,
                    old_values TEXT,  -- JSON string of old values
                    new_values TEXT,  -- JSON string of new values
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)

            # â”€â”€ Additional indexes for audit log performance â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action)")

            # H-05: updated_at auto-trigger (Postgres)
            # BEFORE UPDATE: if app forgets updated_at, trigger catches it.
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cur.execute("""
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_projects_updated_at'
                  AND tgrelid = 'projects'::regclass
            """)
            if not cur.fetchone():
                cur.execute("""
                    CREATE TRIGGER trg_projects_updated_at
                    BEFORE UPDATE ON projects
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column()
                """)
            cur.execute("""
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_devices_updated_at'
                  AND tgrelid = 'devices'::regclass
            """)
            if not cur.fetchone():
                cur.execute("""
                    CREATE TRIGGER trg_devices_updated_at
                    BEFORE UPDATE ON devices
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column()
                """)

            # â”€â”€ ETAP Integration Tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("""
                CREATE TABLE IF NOT EXISTS etap_integrations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    last_sync TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_etap_integrations_project ON etap_integrations(project_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS etap_sync_logs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_synced INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_etap_sync_logs_project ON etap_sync_logs(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_etap_sync_logs_created ON etap_sync_logs(created_at)")

        logger.info("PostgreSQL schema initialized successfully (matching SQLite schema)")

    def _init_schema(self) -> None:
        """Create all tables if they don't exist (SQLite)."""
        with self._transaction() as cur:
            # â”€â”€ Projects â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Devices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Connections â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    cable_size TEXT NOT NULL DEFAULT '1.5mmآ²',
                    length REAL NOT NULL DEFAULT 0.0,
                    type TEXT NOT NULL DEFAULT 'power',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # â”€â”€ Reports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Sync Status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            # â”€â”€ Sync Operations (granular per-entity sync tracking) â”€â”€â”€â”€
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

            # â”€â”€ Indexes for performance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_project ON devices(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_project ON connections(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id)")
            # SAFETY FIX: Missing indexes on connections.from_id and connections.to_id
            # Every device deletion triggers DELETE FROM connections WHERE from_id=? OR to_id=?
            # Without these indexes, that's a full table scan â€” O(n) per deletion.
            # For a project with 10,000 connections, deleting one device scans all rows.
            # Slow operations could cause timeouts that appear as failures in a safety system.
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_from ON connections(from_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_to ON connections(to_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_entity ON sync_operations(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_ops_status ON sync_operations(status)")

            # â”€â”€ Audit Log Table for NFPA 72 Compliance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,  -- CREATE, UPDATE, DELETE, VIEW
                    entity_type TEXT NOT NULL,  -- projects, devices, etc.
                    entity_id TEXT NOT NULL,
                    old_values TEXT,  -- JSON string of old values
                    new_values TEXT,  -- JSON string of new values
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)

            # â”€â”€ Additional indexes for audit log performance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action)")

            # H-05: updated_at auto-trigger (SQLite)
            # AFTER UPDATE with UPDATE OF column list prevents recursion.
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_projects_updated_at
                AFTER UPDATE OF name, description, author, status ON projects
                BEGIN
                    UPDATE projects SET updated_at = datetime("now")
                    WHERE id = NEW.id;
                END
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_devices_updated_at
                AFTER UPDATE OF type, name, category, x, y, z, rotation, voltage, current, load, properties ON devices
                BEGIN
                    UPDATE devices SET updated_at = datetime("now")
                    WHERE id = NEW.id;
                END
            """)

            # â”€â”€ ETAP Integration Tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            cur.execute("""
                CREATE TABLE IF NOT EXISTS etap_integrations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 0,
                    last_sync TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_etap_integrations_project ON etap_integrations(project_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS etap_sync_logs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_synced INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_etap_sync_logs_project ON etap_sync_logs(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_etap_sync_logs_created ON etap_sync_logs(created_at)")

    # ========================================================================
    # Projects CRUD
    # ========================================================================

    # ========================================================================
    # Database Repositories Delegations (100% Backward Compatible)
    # ========================================================================

    # Projects Delegation
    def create_project(self, project_data: dict) -> dict:
        return self.projects.create_project(project_data)

    def get_project(self, project_id: str) -> dict | None:
        return self.projects.get_project(project_id)

    def list_projects(self, page: int = 1, limit: int = 20, sort: str = "created_at", order: str = "desc") -> dict:
        return self.projects.list_projects(page, limit, sort, order)

    def update_project(self, project_id: str, updates: dict) -> dict | None:
        return self.projects.update_project(project_id, updates)

    def delete_project(self, project_id: str) -> bool:
        return self.projects.delete_project(project_id)

    def get_global_counts(self) -> dict:
        return self.projects.get_global_counts()

    # Devices Delegation
    def create_device(self, project_id: str, device_data: dict) -> dict:
        return self.devices.create_device(project_id, device_data)

    def get_device(self, project_id: str, device_id: str) -> dict | None:
        return self.devices.get_device(project_id, device_id)

    def list_devices(self, project_id: str, page: int = 1, limit: int = 20, sort: str = "created_at", order: str = "desc") -> dict:
        return self.devices.list_devices(project_id, page, limit, sort, order)

    def update_device(self, project_id: str, device_id: str, updates: dict) -> dict | None:
        return self.devices.update_device(project_id, device_id, updates)

    def delete_device(self, project_id: str, device_id: str) -> bool:
        return self.devices.delete_device(project_id, device_id)

    def get_all_devices_for_project(self, project_id: str) -> list[dict]:
        return self.devices.get_all_devices_for_project(project_id)

    # Connections Delegation
    def create_connection(self, project_id: str, conn_data: dict) -> dict:
        return self.connections.create_connection(project_id, conn_data)

    def get_connection(self, project_id: str, connection_id: str) -> dict | None:
        return self.connections.get_connection(project_id, connection_id)

    def list_connections(self, project_id: str, page: int = 1, limit: int = 20, sort: str = "created_at", order: str = "desc") -> dict:
        return self.connections.list_connections(project_id, page, limit, sort, order)

    def delete_connection(self, project_id: str, connection_id: str) -> bool:
        return self.connections.delete_connection(project_id, connection_id)

    def update_connection(self, project_id: str, connection_id: str, updates: dict) -> dict | None:
        return self.connections.update_connection(project_id, connection_id, updates)

    def get_all_connections_for_project(self, project_id: str) -> list[dict]:
        return self.connections.get_all_connections_for_project(project_id)

    # Reports Delegation
    def create_report(self, project_id: str, report_data: dict) -> dict:
        return self.reports.create_report(project_id, report_data)

    def get_report(self, project_id: str, report_id: str) -> dict | None:
        return self.reports.get_report(project_id, report_id)

    def list_reports(self, project_id: str, page: int = 1, limit: int = 20, sort: str = "created_at", order: str = "desc") -> dict:
        return self.reports.list_reports(project_id, page, limit, sort, order)

    def update_report(self, project_id: str, report_id: str, updates: dict) -> dict | None:
        return self.reports.update_report(project_id, report_id, updates)

    # Sync Delegation
    def get_sync_status(self, project_id: str) -> dict | None:
        return self.sync.get_sync_status(project_id)

    def set_sync_status(self, project_id: str, status: dict) -> dict:
        return self.sync.set_sync_status(project_id, status)

    def record_sync(self, entity_type: str, entity_id: str, target_db: str, status: str, error: str | None = None) -> int:
        return self.sync.record_sync(entity_type, entity_id, target_db, status, error)

    def get_pending_syncs(self, max_retries: int = 3) -> list:
        return self.sync.get_pending_syncs(max_retries)


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
# Singleton instance â€” imported by routers
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
