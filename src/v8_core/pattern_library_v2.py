"""
v8_core/pattern_library_v2.py
========================
PATCH 10: Pattern Library Deduplication with UNIQUE Constraint
Priority: LOW (but critical before curators ingest)

This module provides pattern library with deduplication
using canonical_hash as UNIQUE constraint.

Integration:
1. lib = PatternLibraryDedup(db_pool)
2. lib.ingest_pattern(pattern_hash, anonymized_decision, "warehouse")
3. lib.approve_pattern(pattern_hash, "curator@firm.com")
"""

import json
from datetime import datetime
from typing import Optional


class PatternLibraryDedup:
    """Pattern library with deduplication constraint."""
    
    def __init__(self, db_pool):
        """
        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool
        self._init_schema()
    
    def _init_schema(self):
        """Create pattern table with UNIQUE canonical_hash constraint."""
        sql = """
        CREATE TABLE IF NOT EXISTS pattern_library_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_hash TEXT UNIQUE NOT NULL,
            anonymized_decision TEXT NOT NULL,
            pattern_class TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            curator_approved INTEGER DEFAULT 0,
            curator_approved_at TEXT,
            approved_by TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_pattern_class ON pattern_library_v2(pattern_class);
        CREATE INDEX IF NOT EXISTS idx_pattern_hash ON pattern_library_v2(canonical_hash);
        """
        try:
            self.db.execute(sql)
            print("[✓] Pattern library initialized with UNIQUE canonical_hash")
        except Exception as e:
            print(f"[!] Schema init: {e}")
    
    def ingest_pattern(
        self,
        canonical_hash: str,
        anonymized_decision: dict,
        pattern_class: str
    ) -> bool:
        """
        Ingest anonymized decision into pattern library.
        
        Args:
            canonical_hash: SHA256 hash of canonical decision
            anonymized_decision: Anonymized decision dict
            pattern_class: Classification (e.g., "warehouse", "office")
            
        Returns:
            True if new pattern added
            False if duplicate (hash already in library)
        """
        decision_json = json.dumps(anonymized_decision, sort_keys=True)
        
        sql = """
        INSERT INTO pattern_library_v2
        (canonical_hash, anonymized_decision, pattern_class, ingested_at)
        VALUES (?, ?, ?, datetime('now'))
        """
        
        try:
            self.db.execute(sql, (canonical_hash, decision_json, pattern_class))
            print(f"[✓] New pattern ingested: {canonical_hash[:16]}... ({pattern_class})")
            return True
        except Exception as e:
            if 'UNIQUE constraint failed' in str(e) or 'unique' in str(e).lower():
                print(f"[!] Duplicate pattern (hash: {canonical_hash[:16]}...) - skipped")
                return False
            else:
                print(f"[!] Ingest failed: {e}")
                return False
    
    def approve_pattern(
        self,
        canonical_hash: str,
        approved_by: str
    ) -> bool:
        """
        Curator approves pattern for use in fire calculations.
        
        Args:
            canonical_hash: Pattern hash to approve
            approved_by: Curator email/ID
            
        Returns:
            True if approved
        """
        sql = """
        UPDATE pattern_library_v2
        SET curator_approved = 1, 
            curator_approved_at = datetime('now'), 
            approved_by = ?
        WHERE canonical_hash = ?
        AND curator_approved = 0
        """
        
        cursor = self.db.execute(sql, (approved_by, canonical_hash))
        
        if cursor and cursor > 0:
            print(f"[✓] Pattern approved by {approved_by}: {canonical_hash[:16]}...")
            return True
        else:
            print(f"[!] Pattern not found or already approved")
            return False
    
    def unapprove_pattern(self, canonical_hash: str) -> bool:
        """
        Remove curator approval from a pattern.
        
        Args:
            canonical_hash: Pattern hash to unapprove
            
        Returns:
            True if unapproved
        """
        sql = """
        UPDATE pattern_library_v2
        SET curator_approved = 0,
            curator_approved_at = NULL,
            approved_by = NULL
        WHERE canonical_hash = ?
        """
        
        cursor = self.db.execute(sql, (canonical_hash,))
        
        if cursor and cursor > 0:
            print(f"[✓] Pattern unapproved: {canonical_hash[:16]}...")
            return True
        return False
    
    def query_patterns(
        self,
        pattern_class: str = None,
        approved_only: bool = False
    ) -> list:
        """
        Query patterns from library.
        
        Args:
            pattern_class: Filter by class (None = all)
            approved_only: Only return approved patterns
            
        Returns:
            List of pattern dicts
        """
        if pattern_class:
            sql = """
            SELECT canonical_hash, anonymized_decision, pattern_class, ingested_at
            FROM pattern_library_v2
            WHERE pattern_class = ?
            """
            params = (pattern_class,)
        else:
            sql = """
            SELECT canonical_hash, anonymized_decision, pattern_class, ingested_at
            FROM pattern_library_v2
            """
            params = ()
        
        rows = self.db.execute(sql, params)
        
        patterns = []
        for row in rows:
            if hasattr(row, 'items'):
                row = dict(row)
            
            # Skip unapproved if requested
            if approved_only and not row.get('curator_approved'):
                continue
            
            try:
                decision = json.loads(row.get('anonymized_decision', '{}'))
            except json.JSONDecodeError:
                decision = {}
            
            patterns.append({
                'hash': row.get('canonical_hash'),
                'decision': decision,
                'class': row.get('pattern_class'),
                'ingested_at': row.get('ingested_at')
            })
        
        return patterns
    
    def query_approved_patterns(self, pattern_class: str = None) -> list:
        """Query only approved patterns (convenience method)."""
        return self.query_patterns(pattern_class, approved_only=True)
    
    def get_pattern_count(self, approved_only: bool = False) -> int:
        """
        Get total pattern count.
        
        Args:
            approved_only: Count only approved patterns
            
        Returns:
            Number of patterns
        """
        sql = "SELECT COUNT(*) as count FROM pattern_library_v2"
        
        if approved_only:
            sql += " WHERE curator_approved = 1"
        
        row = self.db.execute(sql, fetch_one=True)
        
        if hasattr(row, 'items'):
            row = dict(row)
        
        return row.get('count', 0) if row else 0
    
    def delete_pattern(self, canonical_hash: str) -> bool:
        """
        Delete a pattern from library.
        
        Args:
            canonical_hash: Pattern hash to delete
            
        Returns:
            True if deleted
        """
        sql = "DELETE FROM pattern_library_v2 WHERE canonical_hash = ?"
        
        cursor = self.db.execute(sql, (canonical_hash,))
        
        if cursor and cursor > 0:
            print(f"[✓] Pattern deleted: {canonical_hash[:16]}...")
            return True
        return False
    
    def get_stats(self) -> dict:
        """
        Get pattern library statistics.
        
        Returns:
            Dict with stats
        """
        total = self.get_pattern_count(approved_only=False)
        approved = self.get_pattern_count(approved_only=True)
        
        return {
            'total_patterns': total,
            'approved_patterns': approved,
            'pending_approval': total - approved
        }


# INTEGRATION EXAMPLES:
# ==================
#
# Example 1: Ingest new pattern (after anonymizing)
#   from src.v8_core.pattern_library_v2 import PatternLibraryDedup
#   from src.v8_core.canonical_json import canonical_hash, anonymize_for_pattern
#   
#   lib = PatternLibraryDedup(db_pool)
#   
#   # Raw decision from firecalc
#   decision = {
#       "decision_type": "panel_placement",
#       "drawing_id": "DWG-001",  # Will be removed
#       "device_count": 50,
#       "area": 5000,
#       "occupancy": "warehouse"
#   }
#   
#   # Anonymize for pattern library
#   anonymized = anonymize_for_pattern(decision)
#   pattern_hash = canonical_hash(anonymized)
#   
#   # Ingest (duplicate-safe)
#   lib.ingest_pattern(pattern_hash, anonymized, "warehouse")
#
# Example 2: Curator approves pattern
#   lib.approve_pattern(pattern_hash, "curator@firm.com")
#
# Example 3: Query approved patterns for inference
#   patterns = lib.query_approved_patterns("warehouse")
#   for p in patterns:
#       use p['decision'] for similarity matching
#
# Example 4: Get stats
#   stats = lib.get_stats()
#   print(f"Total: {stats['total_patterns']}, Approved: {stats['approved_patterns']}")