"""
v8_core/secure_tokens.py
=================
PATCH 3: Secure Cryptographic Randomness
Priority: CRITICAL

This module provides cryptographically secure token generation using Python's
secrets module (256-bit entropy) with hash-only storage.

Integration:
1. gen = SecureTokenGenerator()
2. override = gen.generate_override_token(duration_hours=4)
3. Store override['token_hash'] in DB, never the token itself
4. Verify with: gen.verify_token(user_token, stored_hash)
"""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class SecureTokenGenerator:
    """Cryptographically secure token generation with audit trail."""
    
    def __init__(self, token_log_path: str = ".tokens/generated.log"):
        """
        Args:
            token_log_path: Path to token issuance audit log
        """
        self.token_log = Path(token_log_path)
        self.token_log.parent.mkdir(parents=True, exist_ok=True)
    
    def generate_override_token(self, duration_hours: int = 4) -> dict:
        """
        Generate cryptographically secure override token.
        
        Returns:
            {
                'token': (64 hex chars, 256 bits),
                'token_hash': SHA256 hash (for storage),
                'expires_at': ISO timestamp,
                'issued_at': ISO timestamp
            }
        """
        # 32 random bytes = 256 bits of entropy
        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        now = datetime.utcnow()
        expires = now + timedelta(hours=duration_hours)
        
        payload = {
            'token': token,
            'token_hash': token_hash,
            'issued_at': now.isoformat(),
            'expires_at': expires.isoformat(),
            'duration_hours': duration_hours
        }
        
        # Log for audit (never store plaintext token)
        self._log_token_issuance(token_hash)
        
        return payload
    
    def generate_session_token(self, duration_hours: int = 8) -> dict:
        """
        Generate a session token for PE authentication.
        
        Returns:
            Same structure as override token
        """
        return self.generate_override_token(duration_hours)
    
    def generate_api_token(self, duration_days: int = 90) -> dict:
        """
        Generate a long-lived API token.
        
        Returns:
            Same structure as override token
        """
        return self.generate_override_token(duration_hours=duration_days * 24)
    
    def _log_token_issuance(self, token_hash: str):
        """Append token hash to audit log."""
        timestamp = datetime.utcnow().isoformat()
        with open(self.token_log, 'a') as f:
            f.write(f"{timestamp} ISSUED {token_hash}\n")
    
    def verify_token(self, token: str, stored_token_hash: str) -> bool:
        """
        Verify token by comparing hashes.
        
        IMPORTANT: Never compare plaintext tokens!
        
        Args:
            token: User-provided token (plaintext)
            stored_token_hash: SHA256 hash stored in DB
            
        Returns:
            True if token matches hash
        """
        computed_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(computed_hash, stored_token_hash)
    
    def is_token_expired(self, expires_at: str) -> bool:
        """
        Check if token is expired.
        
        Args:
            expires_at: ISO timestamp string
            
        Returns:
            True if token is expired
        """
        try:
            expiry = datetime.fromisoformat(expires_at)
            return datetime.utcnow() > expiry
        except (ValueError, TypeError):
            return True  # Treat invalid as expired
    
    def get_token_age_hours(self, issued_at: str) -> float:
        """
        Get token age in hours.
        
        Args:
            issued_at: ISO timestamp string
            
        Returns:
            Age in hours (float)
        """
        try:
            issued = datetime.fromisoformat(issued_at)
            age = datetime.utcnow() - issued
            return age.total_seconds() / 3600
        except (ValueError, TypeError):
            return float('inf')


class SecureOverrideConsumer:
    """Consume override token safely."""
    
    def __init__(self, db_pool, token_gen: SecureTokenGenerator):
        """
        Args:
            db_pool: Database connection pool
            token_gen: SecureTokenGenerator instance
        """
        self.db = db_pool
        self.token_gen = token_gen
    
    def consume_override(self, token: str, override_id: str) -> dict:
        """
        Consume override token:
        1. Verify hash
        2. Check expiry
        3. Check revocation status
        4. Return result
        
        Args:
            token: User-provided token (plaintext)
            override_id: Override identifier
            
        Returns:
            {
                'success': bool,
                'error': str or None,
                'expires_at': str or None
            }
        """
        # Fetch stored hash
        sql = "SELECT token_hash, expires_at, revoked_at FROM overrides WHERE override_id = ?"
        row = self.db.execute(sql, (override_id,), fetch_one=True)
        
        if not row:
            return {
                'success': False,
                'error': 'Override not found',
                'expires_at': None
            }
        
        # Handle different row types
        if hasattr(row, 'items'):
            row = dict(row)
        
        stored_hash = row.get('token_hash')
        expires_at = row.get('expires_at')
        revoked_at = row.get('revoked_at')
        
        # Check revocation
        if revoked_at:
            return {
                'success': False,
                'error': 'Override has been revoked',
                'expires_at': expires_at
            }
        
        # Check expiry
        if self.token_gen.is_token_expired(expires_at):
            return {
                'success': False,
                'error': 'Override has expired',
                'expires_at': expires_at
            }
        
        # Verify token hash
        if not self.token_gen.verify_token(token, stored_hash):
            return {
                'success': False,
                'error': 'Invalid token',
                'expires_at': expires_at
            }
        
        return {
            'success': True,
            'error': None,
            'expires_at': expires_at
        }
    
    def generate_and_store_override(self, override_id: str, duration_hours: int = 4) -> dict:
        """
        Generate a new override and store hash (not token).
        
        Args:
            override_id: Unique override identifier
            duration_hours: Token validity period
            
        Returns:
            Token payload (includes plaintext token)
        """
        token_payload = self.token_gen.generate_override_token(duration_hours)
        
        # Store ONLY the hash!
        sql = """
            INSERT INTO overrides 
            (override_id, token_hash, issued_at, expires_at)
            VALUES (?, ?, ?, ?)
        """
        
        try:
            self.db.execute(sql, (
                override_id,
                token_payload['token_hash'],
                token_payload['issued_at'],
                token_payload['expires_at']
            ))
        except Exception as e:
            print(f"[!] Failed to store override: {e}")
            return None
        
        return token_payload


# INTEGRATION GUIDE:
# ================
#
# Step 1: Initialize
#   from src.v8_core.secure_tokens import SecureTokenGenerator, SecureOverrideConsumer
#   gen = SecureTokenGenerator()
#   consumer = SecureOverrideConsumer(db_pool, gen)
#
# Step 2: Generate token
#   token = gen.generate_override_token(duration_hours=4)
#   # Store ONLY token_hash in database!
#   override_id = "OVR-001"
#   consumer.generate_and_store_override(override_id, duration_hours=4)
#
# Step 3: Verify token
#   result = consumer.consume_override(user_token, "OVR-001")
#   if result['success']:
#       allow_override()
#   else:
#       reject(result['error'])
#
# Step 4: Log all token operations
#   - Token issuance is logged automatically to .tokens/generated.log
#   - Check logs for audit trail
#
# SECURITY NOTES:
# =============
# - NEVER store plaintext tokens in database
# - ALWAYS use secrets.compare_digest for timing-safe comparison
# - Add ".tokens/" to .gitignore (contains audit log only, no secrets)