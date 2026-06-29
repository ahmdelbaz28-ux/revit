"""
Shim for backend.core.database – re-export top-level core.database.

The original backend.core.database implementation conflicted with the primary
``core.database`` module used throughout the codebase and tests. This shim
loads the authoritative ``core.database`` module from the project root and
exposes its public API, ensuring consistent behavior.
"""

import importlib.util
import os
import sys

# Ensure project root is on sys.path (two levels up from this file)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load the real core.database module
_core_db_path = os.path.join(_project_root, "core", "database.py")
_spec = importlib.util.spec_from_file_location("real_core_database", _core_db_path)
_real_core_database = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_real_core_database)  # type: ignore[arg-type]

# Re-export all symbols from the real core.database module
globals().update(_real_core_database.__dict__)

# Preserve reference for introspection
_real_core_database_pkg = _real_core_database
import sqlite3
import json
import threading
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import logging
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class UniversalDataModel:
    """
    Thread-safe database abstraction layer supporting elements,
    relationships, and semantic properties.
    
    This class provides a unified interface for storing and retrieving
    structured data in a SQLite database, with support for transactions
    and concurrent access.
    """
    
    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        """
        Initialize the Universal Data Model.
        
        Args:
            db_path: Path to SQLite database file, or ':memory:' for in-memory
        """
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.RLock()
        
        # Initialize database schema
        self._initialize_schema()
    
    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            self._local.conn.row_factory = sqlite3.Row
            
            # Enable foreign keys
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            
        return self._local.conn
    
    def _initialize_schema(self):
        """Initialize database tables if they don't exist."""
        conn = self._get_connection()
        
        # Elements table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                element_id TEXT UNIQUE NOT NULL,
                name TEXT,
                type TEXT,
                properties TEXT,  -- JSON string
                geometry TEXT,    -- JSON string
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Relationships table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relationship_id TEXT UNIQUE NOT NULL,
                source_element_id TEXT NOT NULL,
                target_element_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                properties TEXT,  -- JSON string
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_element_id) REFERENCES elements(element_id),
                FOREIGN KEY (target_element_id) REFERENCES elements(element_id)
            )
        """)
        
        # Semantic Properties table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                element_id TEXT NOT NULL,
                property_key TEXT NOT NULL,
                property_value TEXT,  -- JSON string
                property_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(element_id, property_key),
                FOREIGN KEY (element_id) REFERENCES elements(element_id)
            )
        """)
        
        # Create indexes for better performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_elements_type ON elements(type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_semantic_props_key ON semantic_properties(property_key)
        """)
        
        conn.commit()
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        old_isolation = conn.isolation_level
        conn.isolation_level = None  # Start transaction
        
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.isolation_level = old_isolation
    
    def add_element(self, element_id: str, name: str = None, type: str = None, 
                    properties: Dict[str, Any] = None, geometry: Dict[str, Any] = None) -> bool:
        """Add a new element to the database."""
        with self._lock:
            conn = self._get_connection()
            
            try:
                conn.execute("""
                    INSERT INTO elements (element_id, name, type, properties, geometry)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    element_id,
                    name,
                    type,
                    json.dumps(properties) if properties else None,
                    json.dumps(geometry) if geometry else None
                ))
                
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Element ID already exists
                return False
    
    def get_element(self, element_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an element by ID."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT element_id, name, type, properties, geometry, created_at, updated_at
            FROM elements WHERE element_id = ?
        """, (element_id,))
        
        row = cursor.fetchone()
        if row:
            row_dict = dict(row)
            # Parse JSON fields
            if row_dict['properties']:
                row_dict['properties'] = json.loads(row_dict['properties'])
            if row_dict['geometry']:
                row_dict['geometry'] = json.loads(row_dict['geometry'])
            return row_dict
        return None
    
    def update_element(self, element_id: str, **updates) -> bool:
        """Update an existing element."""
        with self._lock:
            conn = self._get_connection()
            
            # Build dynamic update query
            allowed_fields = {'name', 'type', 'properties', 'geometry'}
            update_fields = {k: v for k, v in updates.items() if k in allowed_fields}
            
            if not update_fields:
                return False
            
            # Convert JSON fields if necessary
            if 'properties' in update_fields and isinstance(update_fields['properties'], dict):
                update_fields['properties'] = json.dumps(update_fields['properties'])
            if 'geometry' in update_fields and isinstance(update_fields['geometry'], dict):
                update_fields['geometry'] = json.dumps(update_fields['geometry'])
            
            set_clause = ", ".join([f"{field} = ?" for field in update_fields.keys()])
            values = list(update_fields.values()) + [element_id]
            
            cursor = conn.execute(f"""
                UPDATE elements SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE element_id = ?
            """, values)
            
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_element(self, element_id: str) -> bool:
        """Delete an element and its relationships."""
        with self._lock:
            conn = self._get_connection()
            
            # Delete relationships first (due to foreign key constraints)
            conn.execute("""
                DELETE FROM relationships
                WHERE source_element_id = ? OR target_element_id = ?
            """, (element_id, element_id))
            
            # Delete semantic properties
            conn.execute("""
                DELETE FROM semantic_properties
                WHERE element_id = ?
            """, (element_id,))
            
            # Delete the element
            cursor = conn.execute("""
                DELETE FROM elements WHERE element_id = ?
            """, (element_id,))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def add_relationship(self, relationship_id: str, source_element_id: str, 
                        target_element_id: str, relationship_type: str,
                        properties: Dict[str, Any] = None) -> bool:
        """Add a relationship between two elements."""
        with self._lock:
            conn = self._get_connection()
            
            try:
                conn.execute("""
                    INSERT INTO relationships 
                    (relationship_id, source_element_id, target_element_id, relationship_type, properties)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    relationship_id,
                    source_element_id,
                    target_element_id,
                    relationship_type,
                    json.dumps(properties) if properties else None
                ))
                
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Relationship ID already exists
                return False
    
    def get_relationships(self, element_id: str, relationship_type: str = None) -> List[Dict[str, Any]]:
        """Get relationships for an element."""
        conn = self._get_connection()
        
        if relationship_type:
            cursor = conn.execute("""
                SELECT * FROM relationships
                WHERE source_element_id = ? AND relationship_type = ?
                UNION
                SELECT * FROM relationships
                WHERE target_element_id = ? AND relationship_type = ?
            """, (element_id, relationship_type, element_id, relationship_type))
        else:
            cursor = conn.execute("""
                SELECT * FROM relationships
                WHERE source_element_id = ? OR target_element_id = ?
            """, (element_id, element_id))
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            row_dict = dict(row)
            if row_dict['properties']:
                row_dict['properties'] = json.loads(row_dict['properties'])
            results.append(row_dict)
        
        return results
    
    def get_elements_by_type(self, element_type: str) -> List[Dict[str, Any]]:
        """Get all elements of a specific type."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT element_id, name, type, properties, geometry, created_at, updated_at
            FROM elements WHERE type = ?
        """, (element_type,))
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            row_dict = dict(row)
            if row_dict['properties']:
                row_dict['properties'] = json.loads(row_dict['properties'])
            if row_dict['geometry']:
                row_dict['geometry'] = json.loads(row_dict['geometry'])
            results.append(row_dict)
        
        return results
    
    def add_semantic_property(self, element_id: str, property_key: str, 
                             property_value: Any, property_type: str = None) -> bool:
        """Add a semantic property to an element."""
        with self._lock:
            conn = self._get_connection()
            
            try:
                conn.execute("""
                    INSERT INTO semantic_properties 
                    (element_id, property_key, property_value, property_type)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(element_id, property_key) DO UPDATE SET
                        property_value = excluded.property_value,
                        property_type = excluded.property_type,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    element_id,
                    property_key,
                    json.dumps(property_value) if property_value is not None else None,
                    property_type
                ))
                
                conn.commit()
                return True
            except Exception:
                return False
    
    def get_semantic_properties(self, element_id: str) -> Dict[str, Any]:
        """Get all semantic properties for an element."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT property_key, property_value, property_type
            FROM semantic_properties
            WHERE element_id = ?
        """, (element_id,))
        
        properties = {}
        for row in cursor.fetchall():
            value = row['property_value']
            if value is not None:
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep as string if not valid JSON
            properties[row['property_key']] = value
        
        return properties
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()


__all__ = ["UniversalDataModel"]

# Ensure final definitions match the top-level core.database
import importlib.util
_core_db_path = os.path.join(_project_root, "core", "database.py")
_spec = importlib.util.spec_from_file_location("real_core_database_final", _core_db_path)
_real_core_database_final = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_real_core_database_final)
globals().update(_real_core_database_final.__dict__)
