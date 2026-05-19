"""
v8_core/override_revocation.py
======================
PATCH 7: Override Token Revocation Before Expiry
Priority: MEDIUM

This module provides override token revocation capabilities,
allowing PEs to revoke an override before expiry if errors are detected.

Integration:
1. rev_manager = OverrideRevocationManager(db_pool)
2. rev_manager.revoke_override("OVR-001", reason="design flaw detected")
3. if rev_manager.is_override_valid("OVR-001"):
"""

import sqlite3
from datetime import datetime as dt
from typing import Optional


class OverrideRevocationManager:
    """Manage override revocation + expiry for PE error recovery."""
    
    def __init__(self, db_pool):
        """
        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool
        self._init_schema()
    
    def _init_schema(self):
        """Create revocation table if not present."""
        sql = """
        CREATE TABLE IF NOT EXISTS overrides_revocation (
            override_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            revoked_reason TEXT,
            revoked_by TEXT
        )
        """
        try:
            self.db.execute(sql)
        except Exception as e:
            # Table might already exist
            pass
    
    def issue_override(self, override_id: str, token_hash: str, expires_at: str):
        """
        Issue an override token.
        
        Args:
            override_id: Unique override identifier
            token_hash: SHA256 hash of token (not plaintext)
            expires_at: ISO timestamp when override expires
        """
        sql = """
        INSERT INTO overrides_revocation 
        (override_id, token_hash, issued_at, expires_at)
        VALUES (?, ?, datetime('now'), ?)
        """
        try:
            self.db.execute(sql, (override_id, token_hash, expires_at))
            print(f"[✓] Override issued: {override_id}")
        except sqlite3.IntegrityError:
            print(f"[!] Override already exists: {override_id}")
    
    def revoke_override(
        self,
        override_id: str,
        reason: str = "",
        revoked_by: str = ""
    ) -> bool:
        """
        Revoke an override before expiry.
        
        Args:
            override_id: Override to revoke
            reason: Reason for revocation
            revoked_by: Who is revoking
            
        Returns:
            True if revoked successfully
        """
        sql = """
        UPDATE overrides_revocation
        SET revoked_at = datetime('now'), revoked_reason = ?, revoked_by = ?
        WHERE override_id = ?
        AND revoked_at IS NULL
        """
        cursor = self.db.execute(sql, (reason, revoked_by, override_id))
        
        if cursor and cursor > 0:
            print(f"[✓] Override revoked: {override_id}")
            return True
        else:
            print(f"[!] Override not found or already revoked: {override_id}")
            return False
    
    def is_override_valid(self, override_id: str) -> bool:
        """
        Check if override is still valid (not revoked + not expired).
        
        Args:
            override_id: Override ID to check
            
        Returns:
            True if valid, False otherwise
        """
        sql = """
        SELECT expires_at, revoked_at FROM overrides_revocation
        WHERE override_id = ?
        """
        row = self.db.execute(sql, (override_id,), fetch_one=True)
        
        if not row:
            return False
        
        # Handle dict vs Row
        if hasattr(row, 'items'):
            row = dict(row)
        
        revoked_at = row.get('revoked_at')
        expires_at = row.get('expires_at')
        
        # Check revocation
        if revoked_at:
            print(f"[!] Override {override_id} is revoked")
            return False
        
        # Check expiry
        if expires_at:
            try:
                expiry = dt.fromisoformat(expires_at.replace('Z', '+00:00'))
                if dt.utcnow() > expiry.replace(tzinfo=None):
                    print(f"[!] Override {override_id} is expired")
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def get_override_status(self, override_id: str) -> Optional[dict]:
        """
        Get full status of an override.
        
        Args:
            override_id: Override ID
            
        Returns:
            Dict with status info, or None if not found
        """
        sql = "SELECT * FROM overrides_revocation WHERE override_id = ?"
        row = self.db.execute(sql, (override_id,), fetch_one=True)
        
        if not row:
            return None
        
        if hasattr(row, 'items'):
            row = dict(row)
        
        return {
            'override_id': row.get('override_id'),
            'issued_at': row.get('issued_at'),
            'expires_at': row.get('expires_at'),
            'revoked': row.get('revoked_at') is not None,
            'revoked_at': row.get('revoked_at'),
            'revoked_reason': row.get('revoked_reason'),
            'revoked_by': row.get('revoked_by')
        }
    
    def list_active_overrides(self) -> list:
        """
        List all active (non-revoked, non-expired) overrides.
        
        Returns:
            List of override IDs
        """
        sql = """
        SELECT override_id, expires_at FROM overrides_revocation
        WHERE revoked_at IS NULL
        ORDER BY issued_at DESC
        """
        rows = self.db.execute(sql)
        
        active = []
        now = dt.utcnow()
        
        for row in rows:
            if hasattr(row, 'items'):
                row = dict(row)
            
            expires_at = row.get('expires_at')
            if expires_at:
                try:
                    expiry = dt.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if now > expiry.replace(tzinfo=None):
                        continue  # Expired
                except (ValueError, TypeError):
                    continue
            
            active.append(row.get('override_id'))
        
        return active
    
    def list_revoked_overrides(self) -> list:
        """
        List all revoked overrides.
        
        Returns:
            List of override IDs with revocation details
        """
        sql = """
        SELECT override_id, revoked_at, revoked_reason, revoked_by
        FROM overrides_revocation
        WHERE revoked_at IS NOT NULL
        ORDER BY revoked_at DESC
        """
        rows = self.db.execute(sql)
        
        revoked = []
        for row in rows:
            if hasattr(row, 'items'):
                row = dict(row)
            revoked.append({
                'id': row.get('override_id'),
                'at': row.get('revoked_at'),
                'reason': row.get('revoked_reason'),
                'by': row.get('revoked_by')
            })
        
        return revoked


# INTEGRATION EXAMPLES:
# ==================
#
# Example 1: Initialize and issue override
#   from src.v8_core.override_revocation import OverrideRevocationManager
#   
#   rev_mgr = OverrideRevocationManager(db_pool)
#   
#   # Issue new override (after generating token)
#   token_hash = "abc123..."  # SHA256 hash
#   rev_mgr.issue_override("OVR-001", token_hash, "2026-05-14T18:00:00")
#
# Example 2: PE discovers error - revoke
#   rev_mgr.revoke_override(
#       "OVR-001",
#       reason="PE detected fire pump undersizing",
#       revoked_by="pe@firm.com"
#   )
#
# Example 3: Check before consuming
#   if rev_mgr.is_override_valid("OVR-001"):
#       allow_override()
#   else:
#       reject("Override invalid or revoked")
#
# Example 4: List all active overrides
#   active = rev_mgr.list_active_overrides()
#   print(f"Active overrides: {active}")