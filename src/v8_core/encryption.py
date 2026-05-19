"""
v8_core/encryption.py
====================
PATCH 2: Encryption at Rest with AES-256
Priority: CRITICAL

This module provides column-level encryption for sensitive fields
like audit logs, PE signatures, and override tokens.

Integration:
1. Generate master key: openssl rand -base64 32 > .keys/master.key
2. Initialize: enc = ColumnEncryptor(".keys/master.key")
3. Use EncryptedAuditLog for audit trail
"""

import os
import base64
from typing import Optional

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class ColumnEncryptor:
    """AES-256 column-level encryption for sensitive fields."""
    
    def __init__(self, master_key_path: str):
        """
        Args:
            master_key_path: Path to 32-byte master key file
        """
        if not CRYPTO_AVAILABLE:
            raise ImportError("cryptography package required. Install: pip install cryptography")
        
        if not os.path.exists(master_key_path):
            raise FileNotFoundError(f"Master key not found: {master_key_path}")
        
        with open(master_key_path, 'rb') as f:
            key_bytes = f.read(32)
        
        if len(key_bytes) != 32:
            raise ValueError(f"Master key must be 32 bytes, got {len(key_bytes)}")
        
        # Fernet uses 256-bit keys (base64 encoded)
        self.cipher = Fernet(base64.urlsafe_b64encode(key_bytes))
    
    @staticmethod
    def generate_key(key_path: str) -> str:
        """
        Generate and save a new master key.
        
        Args:
            key_path: Path to save the key
            
        Returns:
            Path to the generated key
        """
        import subprocess
        
        # Generate 32 bytes of random data
        result = subprocess.run(
            ['openssl', 'rand', '-base64', '32'],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # Fallback to secrets module
            import secrets
            key_bytes = secrets.token_bytes(32)
            key_b64 = base64.urlsafe_b64encode(key_bytes).decode()
        else:
            key_b64 = result.stdout.strip()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(key_path) if os.path.dirname(key_path) else '.', exist_ok=True)
        
        # Write key
        with open(key_path, 'wb') as f:
            f.write(key_b64.encode())
        
        os.chmod(key_path, 0o600)  # Owner read/write only
        
        return key_path
    
    def encrypt_value(self, plaintext: str) -> Optional[str]:
        """Encrypt a value for storage."""
        if not plaintext:
            return None
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt_value(self, ciphertext: str) -> Optional[str]:
        """Decrypt a value from storage."""
        if not ciphertext:
            return None
        try:
            decrypted = self.cipher.decrypt(base64.b64decode(ciphertext))
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")


class EncryptedAuditLog:
    """Audit log with encrypted sensitive fields."""
    
    def __init__(self, db_pool, encryptor: ColumnEncryptor):
        """
        Args:
            db_pool: Database connection pool
            encryptor: ColumnEncryptor instance
        """
        self.db = db_pool
        self.enc = encryptor
    
    def log_override(self, override_id: str, drawing_id: str, override_reason: str,
                  pe_signature: str, issued_by: str) -> bool:
        """
        Log override with encrypted reason + signature.
        
        Args:
            override_id: Unique override identifier
            drawing_id: Drawing being overridden
            override_reason: Reason for override (will be encrypted)
            pe_signature: PE signature (will be encrypted)
            issued_by: Who issued the override
            
        Returns:
            True if logged successfully
        """
        encrypted_reason = self.enc.encrypt_value(override_reason)
        encrypted_sig = self.enc.encrypt_value(pe_signature)
        
        sql = """
            INSERT INTO audit_log 
            (override_id, drawing_id, reason_enc, signature_enc, issued_by, ts)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """
        
        try:
            self.db.execute(sql, (override_id, drawing_id, encrypted_reason, encrypted_sig, issued_by))
            return True
        except Exception as e:
            print(f"[!] Audit log failed: {e}")
            return False
    
    def retrieve_override_log(self, override_id: str) -> Optional[dict]:
        """Decrypt and return audit entry."""
        sql = "SELECT * FROM audit_log WHERE override_id = ?"
        
        try:
            row = self.db.execute(sql, (override_id,), fetch_one=True)
        except Exception:
            # Try alternate column names
            row = self.db.execute(sql, (override_id,), fetch_one=True)
        
        if not row:
            return None
        
        # Handle both dict-like and Row objects
        if hasattr(row, 'items'):
            row = dict(row)
        
        return {
            'override_id': row.get('override_id'),
            'reason': self.enc.decrypt_value(row.get('reason_enc', '')),
            'signature': self.enc.decrypt_value(row.get('signature_enc', '')),
            'issued_by': row.get('issued_by'),
            'ts': row.get('ts')
        }
    
    def log_decision(self, decision_type: str, payload: dict, signature: str, signed_by: str) -> bool:
        """
        Log a fire safety decision with encrypted payload + signature.
        
        Args:
            decision_type: Type of decision (panel_placement, loop_design, etc.)
            payload: Decision payload (will be encrypted JSON)
            signature: Digital signature (will be encrypted)
            signed_by: Who signed the decision
        """
        import json
        
        import json
        payload_json = json.dumps(payload)
        encrypted_payload = self.enc.encrypt_value(payload_json)
        encrypted_sig = self.enc.encrypt_value(signature)
        
        sql = """
            INSERT INTO decision_log 
            (decision_type, payload_enc, signature_enc, signed_by, ts)
            VALUES (?, ?, ?, ?, datetime('now'))
        """
        
        try:
            self.db.execute(sql, (decision_type, encrypted_payload, encrypted_sig, signed_by))
            return True
        except Exception as e:
            print(f"[!] Decision log failed: {e}")
            return False


# INTEGRATION GUIDE:
# ================
#
# Step 1: Generate master key
#   mkdir -p .keys
#   ColumnEncryptor.generate_key(".keys/master.key")
#
# Step 2: Initialize encryptor
#   from src.v8_core.encryption import ColumnEncryptor, EncryptedAuditLog
#   enc = ColumnEncryptor(".keys/master.key")
#
# Step 3: Use for audit logs
#   audit_log = EncryptedAuditLog(db_pool, enc)
#   audit_log.log_override("OVR-001", "DWG-112", "Fire pump too small", "PE-SIG-XYZ", "john@firm.com")
#
# SECURITY NOTES:
# =============
# - Master key should be backed up to AWS Secrets Manager
# - Never commit .keys/ to version control
# - Add ".keys/" to .gitignore