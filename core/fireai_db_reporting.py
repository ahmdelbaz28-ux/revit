"""
FireAI Database Module
====================
SQLite database for all FireAI projects.
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional


class FireAIDatabase:
    """SQLite database for all FireAI projects."""

    DB_NAME = "fireai_projects.db"

    def __init__(self, db_path: str = None):
        self.db_path = db_path or self.DB_NAME
        self._is_memory = db_path == ":memory:"
        
        # Create connection
        if self._is_memory:
            self._conn = sqlite3.connect(":memory:")
        else:
            self._conn = sqlite3.connect(self.db_path)
        
        # Initialize tables
        self._init_db()
        
    def _init_db(self):
        """Create all tables."""
        c = self._conn.cursor()
        
        # Projects table
        c.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_hash TEXT UNIQUE,
                name TEXT,
                file_path TEXT,
                file_type TEXT,
                status TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Analysis results
        c.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_hash TEXT,
                room_count INTEGER,
                device_count INTEGER,
                violations INTEGER,
                analysis_data TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_hash) REFERENCES projects(project_hash)
            )
        """)
        
        # Audit log
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_hash TEXT,
                action TEXT,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self._conn.commit()
        
    def save_project(self, name: str, file_path: str, file_type: str) -> str:
        """Save new project and return hash."""
        project_hash = hashlib.md5(
            f"{name}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        self._conn.execute("""
            INSERT INTO projects (project_hash, name, file_path, file_type, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (project_hash, name, file_path, file_type))
        self._conn.commit()
        
        self.log_audit(project_hash, "PROJECT_CREATED", f"Project: {name}")
        return project_hash
    
    def save_analysis(
        self, 
        project_hash: str, 
        room_count: int, 
        device_count: int,
        violations: int,
        analysis_data: Dict
    ):
        """Save analysis result."""
        self._conn.execute("""
            INSERT INTO analyses 
            (project_hash, room_count, device_count, violations, analysis_data)
            VALUES (?, ?, ?, ?, ?)
        """, (
            project_hash, 
            room_count, 
            device_count, 
            violations,
            json.dumps(analysis_data)
        ))
        self._conn.commit()
        
        self.log_audit(
            project_hash, 
            "ANALYSIS_COMPLETE",
            f"Rooms: {room_count}, Devices: {device_count}"
        )
        
    def log_audit(self, project_hash: str, action: str, details: str):
        """Log audit trail."""
        self._conn.execute("""
            INSERT INTO audit_log (project_hash, action, details)
            VALUES (?, ?, ?)
        """, (project_hash, action, details))
        self._conn.commit()
        
    def get_project(self, project_hash: str) -> Optional[Dict]:
        """Get project info."""
        c = self._conn.execute(
            "SELECT * FROM projects WHERE project_hash = ?",
            (project_hash,)
        ).fetchone()
        
        if c:
            return {
                "id": c[0],
                "hash": c[1],
                "name": c[2],
                "file_path": c[3],
                "file_type": c[4],
                "status": c[5],
                "created_at": c[6]
            }
        return None
    
    def list_projects(self) -> List[Dict]:
        """List all projects."""
        rows = self._conn.execute("""
            SELECT project_hash, name, status, created_at 
            FROM projects ORDER BY created_at DESC
        """).fetchall()
        
        return [
            {"hash": r[0], "name": r[1], "status": r[2], "created": r[3]}
            for r in rows
        ]
    
    def get_audit_trail(self, project_hash: str) -> List[Dict]:
        """Get audit trail for project."""
        rows = self._conn.execute("""
            SELECT action, details, created_at 
            FROM audit_log 
            WHERE project_hash = ?
            ORDER BY created_at DESC
        """, (project_hash,)).fetchall()

        return [{"action": r[0], "details": r[1], "time": r[2]} for r in rows]


if __name__ == "__main__":
    # Test database
    print("Testing database...")
    
    # Test in-memory
    db = FireAIDatabase(":memory:")
    print("✅ In-memory created")
    
    # Save project
    project_hash = db.save_project("Test Tower", "tower.dxf", "DXF")
    print(f"✅ Project saved: {project_hash}")
    
    # Save analysis
    db.save_analysis(
        project_hash,
        room_count=5,
        device_count=10,
        violations=2,
        analysis_data={"status": "complete"}
    )
    print("✅ Analysis saved")
    
    # List projects
    projects = db.list_projects()
    print(f"✅ Projects: {len(projects)}")
    
    print("\n✅ All database tests PASSED!")
