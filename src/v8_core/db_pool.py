"""
v8_core/db_pool.py
===============
PATCH 1: DB Connection Pooling with Thread-Safe Lock
Priority: HIGH (concurrent access critical)

This module provides thread-safe SQLite connection pooling
to prevent deadlocks under concurrent PE access.

Integration:
1. pool = DatabasePool("/path/to/fire.db")
2. result = pool.execute("SELECT ...")
"""

import os
import sqlite3
import threading
from queue import Queue
from contextlib import contextmanager
from typing import Any, Optional


class DatabasePool:
    """Thread-safe SQLite connection pool with RLock-based serialization."""
    
    def __init__(self, db_path: str, pool_size: int = 5):
        """
        Args:
            db_path: Path to SQLite database
            pool_size: Maximum number of connections in pool
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Queue = Queue(maxsize=pool_size)
        self._lock = threading.RLock()
        self._initialized = False
        
        # Initialize pool on first use
        self._init_pool()
    
    def _init_pool(self):
        """Initialize connection pool."""
        if self._initialized:
            return
            
        # Create database file if needed
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # Pre-populate pool with connections
        for _ in range(self.pool_size):
            try:
                conn = self._new_connection()
                self._pool.put(conn)
            except Exception as e:
                print(f"[!] Failed to create connection: {e}")
        
        self._initialized = True
        print(f"[✓] Database pool initialized: {self.db_path} ({self.pool_size} connections)")
    
    def _new_connection(self) -> sqlite3.Connection:
        """
        Create a new database connection with optimized settings.
        """
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row
        
        # Performance optimizations
        conn.execute("PRAGMA journal_mode=WAL")      # Write-Ahead Logging
        conn.execute("PRAGMA synchronous=FULL")   # Durability
        conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")   # Temp tables in memory
        conn.execute("PRAGMA foreign_keys=ON")   # Foreign key enforcement
        
        return conn
    
    @contextmanager
    def get_connection(self):
        """
        Acquire and release connection atomically.
        
        Usage:
            with pool.get_connection() as conn:
                conn.execute("SELECT ...")
        """
        if not self._initialized:
            self._init_pool()
            
        conn = self._pool.get()
        try:
            with self._lock:  # Serialize all DB access
                yield conn
        finally:
            self._pool.put(conn)
    
    def execute(self, sql: str, params: tuple = (), fetch_one: bool = False) -> Any:
        """
        Execute SQL with automatic lock + pool management.
        
        Args:
            sql: SQL query (can contain ? parameter placeholders)
            params: Query parameters tuple
            fetch_one: If True, return single row; if False return all
            
        Returns:
            - Single row (dict) if fetch_one=True
            - List of rows if fetch_one=False (SELECT queries)
            - Row count for INSERT/UPDATE/DELETE
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                    
                # For SELECT queries, fetch all
                if sql.strip().upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]
                    
                # For INSERT/UPDATE/DELETE, commit
                conn.commit()
                return cursor.rowcount
                
            except sqlite3.Error as e:
                conn.rollback()
                raise
    
    def execute_many(self, sql: str, params_list: list) -> int:
        """
        Execute SQL with multiple parameter sets.
        
        Args:
            sql: SQL query
            params_list: List of parameter tuples
            
        Returns:
            Number of rows affected
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(sql, params_list)
                conn.commit()
                return cursor.rowcount
            except sqlite3.Error as e:
                conn.rollback()
                raise
    
    def execute_script(self, sql: str) -> None:
        """
        Execute a SQL script (multiple statements).
        
        Args:
            sql: SQL script with multiple statements
        """
        with self.get_connection() as conn:
            try:
                conn.executescript(sql)
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                raise
    
    @contextmanager
    def transaction(self):
        """
        Manual transaction control.
        
        Usage:
            with pool.transaction() as conn:
                conn.execute(...)
                conn.commit()
        """
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def close(self):
        """Close all connections in pool."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Exception:
                pass
        self._initialized = False
        print("[✓] Database pool closed")


def create_pool(db_path: str, pool_size: int = 5) -> DatabasePool:
    """
    Create and initialize a database connection pool.
    
    Args:
        db_path: Path to SQLite database
        pool_size: Maximum connections
        
    Returns:
        DatabasePool instance
    """
    return DatabasePool(db_path, pool_size)


# INTEGRATION GUIDE:
# ================
#
# Step 1: Initialize pool
#   from src.v8_core.db_pool import create_pool
#   pool = create_pool(".fireai/fire.db", pool_size=5)
#
# Step 2: Execute queries
#   # Single row
#   row = pool.execute("SELECT * FROM constants WHERE id = ?", ("NFPA72.MAX_DEVICES",), fetch_one=True)
#
#   # Multiple rows
#   rows = pool.execute("SELECT * FROM constants WHERE code_family = ?", ("NFPA72",))
#
#   # INSERT/UPDATE/DELETE
#   count = pool.execute("INSERT INTO audit_log (...) VALUES (...)", (...))
#
# Step 3: Use transactions when needed
#   with pool.transaction() as conn:
#       conn.execute("INSERT INTO ...")
#       conn.execute("INSERT INTO ...")
#       conn.commit()
#
# SECURITY NOTES:
# ============
# - WAL mode improves concurrent read performance
# - RLock serializes all writes to prevent corruption
# - Connection timeout prevents indefinite blocking