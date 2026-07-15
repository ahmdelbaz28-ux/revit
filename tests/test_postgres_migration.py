import os
import tempfile
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from scripts.migrate_sqlite_to_postgres import migrate
from backend.config import config

def test_migrate_logic():
    """Verify the database migration script reads from SQLite and writes to PostgreSQL correctly."""
    # 1. Create a temporary SQLite database with test tables and test data
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_digital_twin.db")
    
    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    
    # Create matching projects schema
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
        )
    """)
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
            updated_at TEXT NOT NULL
        )
    """)
    # Dummy tables to satisfy migration list
    for table in ["connections", "reports", "sync_status", "sync_operations", "audit_log"]:
        cur.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY)")
        
    # Insert a test project and device
    cur.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("proj-1", "Test Project", "Desc", "Author", "2026-07-15", "2026-07-15", "draft")
    )
    cur.execute(
        "INSERT INTO devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("dev-1", "proj-1", "smoke", "Smoke Detector", "detector", 10.0, 20.0, 3.0, 0.0, 24.0, 0.1, 2.4, "{}", "2026-07-15", "2026-07-15")
    )
    conn.commit()
    conn.close()
    
    # Mock Database and check its execution
    mock_db = MagicMock()
    mock_cur_pg = MagicMock()
    mock_db._pg_cursor.return_value.__enter__.return_value = mock_cur_pg
    
    with patch("scripts.migrate_sqlite_to_postgres.config") as mock_config, \
         patch("scripts.migrate_sqlite_to_postgres.Database", return_value=mock_db):
        
        mock_config.DIGITAL_TWIN_DB_PATH = temp_db_path
        mock_config.DATABASE_URL = "postgresql://user:pass@localhost:5432/dbname"
        
        # Execute migration
        migrate()
        
        # Verify that INSERT was called on the mock cursor for projects and devices
        executed_statements = [call[0][0] for call in mock_cur_pg.execute.call_args_list]
        executed_many = [call[0][0] for call in mock_cur_pg.executemany.call_args_list]
        
        # Should delete existing data first
        assert any("DELETE FROM projects" in stmt for stmt in executed_statements)
        assert any("DELETE FROM devices" in stmt for stmt in executed_statements)
        
        # Should insert projects and devices
        assert any("INSERT INTO projects" in stmt for stmt in executed_many)
        assert any("INSERT INTO devices" in stmt for stmt in executed_many)
        
    # Clean up
    os.remove(temp_db_path)
    os.rmdir(temp_dir)
