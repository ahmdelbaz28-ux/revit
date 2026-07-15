#!/usr/bin/env python3
"""
scripts/migrate_sqlite_to_postgres.py
======================================
Migrates data from local SQLite database (digital_twin.db)
to Supabase/PostgreSQL database.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from typing import List, Tuple

# Add repository root to sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.config import config
from backend.database import Database

def migrate():
    sqlite_path = config.DIGITAL_TWIN_DB_PATH
    database_url = config.DATABASE_URL
    
    if not database_url.startswith(("postgres://", "postgresql://")):
        print("Error: DATABASE_URL is not set to a PostgreSQL connection string.")
        print(f"DATABASE_URL: {database_url}")
        sys.exit(1)
        
    print("Starting migration...")
    print(f"Source SQLite: {sqlite_path}")
    print(f"Destination PG: {database_url.split('@')[-1]}")
    
    if not os.path.exists(sqlite_path):
        print(f"SQLite file not found at '{sqlite_path}'. Nothing to migrate.")
        return

    # Initialize PostgreSQL DB schema
    db_pg = Database()
    
    # Connect to source SQLite
    conn_sq = sqlite3.connect(sqlite_path)
    conn_sq.row_factory = sqlite3.Row
    cur_sq = conn_sq.cursor()
    
    tables = [
        "projects",
        "devices",
        "connections",
        "reports",
        "sync_status",
        "sync_operations",
        "audit_log"
    ]
    
    # We will copy table by table
    with db_pg._pg_cursor() as cur_pg:
        # Disable constraints checks during migration if needed
        # In PostgreSQL we can use SET CONSTRAINTS ALL DEFERRED inside a transaction,
        # but to keep it simple, we insert tables in dependency order:
        # 1. projects
        # 2. devices, connections, reports, sync_status (have project_id reference)
        # 3. audit_log, sync_operations
        
        for table in tables:
            print(f"Migrating table '{table}'...")
            
            # Fetch all rows from SQLite
            cur_sq.execute(f"SELECT * FROM {table}")
            rows = cur_sq.fetchall()
            
            if not rows:
                print(f"  Table '{table}' is empty. Skipping.")
                continue
                
            columns = rows[0].keys()
            col_list = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            
            # Delete existing records in PG to avoid duplication/primary key errors
            cur_pg.execute(f"DELETE FROM {table}")
            
            # Insert into PG
            insert_query = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
            
            values_list = []
            for row in rows:
                val = [row[col] for col in columns]
                values_list.append(val)
                
            cur_pg.executemany(insert_query, values_list)
            print(f"  Successfully migrated {len(values_list)} rows for '{table}'.")
            
    conn_sq.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
