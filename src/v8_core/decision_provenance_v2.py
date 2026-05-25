"""
v8_core/decision_provenance_v2.py
=========================
PATCH 9: Timestamped Decision Signatures (Fork-Attack Prevention)
Priority: MEDIUM

This module extends DecisionProvenance with timestamped signatures
to prevent fork attacks (reusing old signature on new decision).

Integration:
1. signer = TimestampedDecisionSigner()
2. signed = signer.sign_decision(payload, private_key)
3. is_valid, error = signer.verify_decision(signed, public_key)

Integration with DecisionProvenance:
- DecisionProvenance already includes signed_at
- This module provides cryptographic signature + verification
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple


class TimestampedDecisionSigner:
    """Sign decisions with signed_at timestamp to prevent fork attacks."""
    
    def __init__(self, max_age_hours: int = 24):
        """
        Args:
            max_age_hours: Reject signatures older than this
        """
        self.max_age_hours = max_age_hours
    
    def sign_decision(
        self,
        decision_payload: dict,
        private_key,
        algorithm: str = "RSA-SHA256"
    ) -> dict:
        """
        Sign decision with timestamp embedded in payload.
        
        Fork attack prevention:
        - Signature covers: payload + signed_at timestamp
        - Verifier checks: signature(payload + ts) is valid AND ts is reasonable
        - Can't reuse old signature on new decision (different ts)
        
        Args:
            decision_payload: Decision data to sign
            private_key: RSA private key for signing
            algorithm: Signing algorithm
            
        Returns:
            {
                'payload': {...} with signed_at,
                'signature': hex RSA signature,
                'payload_hash': SHA256 of canonical JSON,
                'signed_at': ISO timestamp,
                'signing_algorithm': algorithm
            }
        """
        from src.v8_core.canonical_json import to_canonical_json
        
        now = datetime.utcnow()
        
        # Add timestamp to payload BEFORE signing
        payload_with_ts = {
            **decision_payload,
            'signed_at': now.isoformat(),
            'signing_algorithm': algorithm
        }
        
        # Convert to canonical JSON for deterministic hash
        payload_json = to_canonical_json(payload_with_ts)
        payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
        
        # Sign
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        
        try:
            signature = private_key.sign(
                payload_json.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        except AttributeError:
            # Not a cryptography key - use HMAC fallback
            import hmac
            import base64
            key_bytes = private_key if isinstance(private_key, bytes) else str(private_key).encode()
            signature = hmac.new(key_bytes, payload_json.encode(), hashlib.sha256).digest()
            signature = base64.b64encode(signature).decode()
            algorithm = "HMAC-SHA256"
        
        return {
            'payload': payload_with_ts,
            'signature': signature.hex() if isinstance(signature, bytes) else signature,
            'payload_hash': payload_hash,
            'signed_at': now.isoformat(),
            'signing_algorithm': algorithm
        }
    
    def verify_decision(
        self,
        signed_decision: dict,
        public_key,
        max_age_hours: int = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify decision signature + timestamp.
        
        Args:
            signed_decision: Signed decision dict
            public_key: RSA public key for verification
            max_age_hours: Override max age (default from __init__)
            
        Returns:
            (is_valid: bool, error_msg: str or None)
        """
        if max_age_hours is None:
            max_age_hours = self.max_age_hours
        
        payload = signed_decision.get('payload', {})
        signature_hex = signed_decision.get('signature', '')
        signed_at_str = payload.get('signed_at')
        
        # Check signed_at exists
        if not signed_at_str:
            return False, "Missing signed_at timestamp"
        
        # Check timestamp age
        try:
            signed_at = datetime.fromisoformat(signed_at_str.replace('Z', '+00:00'))
            now = datetime.utcnow()
            age_hours = (now - signed_at.replace(tzinfo=None)).total_seconds() / 3600
            
            if age_hours > max_age_hours:
                return False, f"Signature too old ({age_hours:.1f}h > {max_age_hours}h)"
        except (ValueError, TypeError) as e:
            return False, f"Invalid timestamp: {e}"
        
        # Verify signature
        from src.v8_core.canonical_json import to_canonical_json
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        
        payload_json = to_canonical_json(payload)
        
        try:
            signature = bytes.fromhex(signature_hex)
            public_key.verify(
                signature,
                payload_json.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True, None
        except Exception as e:
            # Try HMAC fallback
            if isinstance(public_key, bytes) or isinstance(public_key, str):
                import hmac
                import base64
                key_bytes = public_key if isinstance(public_key, bytes) else str(public_key).encode()
                expected = hmac.new(key_bytes, payload_json.encode(), hashlib.sha256).digest()
                if hmac.compare_digest(signature_hex, base64.b64encode(expected).decode()):
                    return True, None
            return False, f"Signature verification failed: {e}"
    
    def is_signature_expired(self, signed_decision: dict, max_age_hours: int = None) -> bool:
        """
        Check if signature has expired.
        
        Args:
            signed_decision: Signed decision
            max_age_hours: Max age override
            
        Returns:
            True if expired, False if valid
        """
        if max_age_hours is None:
            max_age_hours = self.max_age_hours
        
        payload = signed_decision.get('payload', {})
        signed_at_str = payload.get('signed_at')
        
        if not signed_at_str:
            return True  # Treat missing as expired
        
        try:
            signed_at = datetime.fromisoformat(signed_at_str.replace('Z', '+00:00'))
            now = datetime.utcnow()
            age_hours = (now - signed_at.replace(tzinfo=None)).total_seconds() / 3600
            return age_hours > max_age_hours
        except (ValueError, TypeError):
            return True
    
    def get_signature_age_hours(self, signed_decision: dict) -> float:
        """
        Get age of signature in hours.
        
        Args:
            signed_decision: Signed decision
            
        Returns:
            Age in hours (float)
        """
        payload = signed_decision.get('payload', {})
        signed_at_str = payload.get('signed_at')
        
        if not signed_at_str:
            return float('inf')
        
        try:
            signed_at = datetime.fromisoformat(signed_at_str.replace('Z', '+00:00'))
            now = datetime.utcnow()
            return (now - signed_at.replace(tzinfo=None)).total_seconds() / 3600
        except (ValueError, TypeError):
            return float('inf')


# INTEGRATION WITH DECISIONPROVENANCE:
# =================================
#
# DecisionProvenance automatically includes signed_at timestamp.
# This module adds cryptographic signature verification.
#
# Usage:
#   from src.v8_core.decision_provenance import DecisionProvenance
#   from src.v8_core.decision_provenance_v2 import TimestampedDecisionSigner
#   
#   # Create decision (includes signed_at)
#   dp = DecisionProvenance(...)
#   
#   # Sign the decision
#   signer = TimestampedDecisionSigner(max_age_hours=24)
#   signed = signer.sign_decision(dp.to_dict(), private_key)
#   
#   # Verify before trusting
#   is_valid, error = signer.verify_decision(signed, public_key)
#   if not is_valid:
#       raise SecurityError(f"Invalid decision: {error}")
#
# FORK ATTACK PREVENTION:
# ==================
# An attacker cannot:
# 1. Take old valid signature and apply to new decision (different signed_at)
# 2. Reuse signature after expiry (max_age_hours check)
# 3. Forge signature (RSA/HMAC verification)


# PYDANTIC SCHEMA FOR AUDIT TRAIL VALIDATION
# ===================================
# Pydantic provides runtime validation for audit trail integrity.
# This ensures no invalid data enters the audit chain.

try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object


if PYDANTIC_AVAILABLE:
    class DecisionProvenanceSchema(BaseModel):
        """
        Pydantic schema for DecisionProvenance audit validation.
        
        Provides runtime type checking and validation for all decision fields.
        Used to ensure audit trail integrity at entry point.
        """
        decision_id: str = Field(..., min_length=1, description="Unique decision ID")
        decision_type: str = Field(..., description="Type: override, compliance, calculation")
        symbol: str = Field(..., description="Fire protection symbol")
        value: float = Field(..., description="Calculated value")
        unit: str = Field(..., description="Unit of measurement")
        
        confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level 0-1")
        jurisdiction: str = Field(..., description="Jurisdiction code")
        edition: str = Field(..., description="Code edition")
        
        signed_at: str = Field(..., description="ISO timestamp")
        signed_by: str = Field(..., description="Signatory")
        
        # Validators - ensure data quality
        @validator('decision_type')
        def validate_type(cls, v):
            allowed = {'override', 'compliance', 'calculation', 'spacing', 'coverage'}
            if v not in allowed:
                raise ValueError(f"Invalid type: {v}")
            return v
        
        @validator('unit')
        def validate_unit(cls, v):
            allowed = {'m', 'ft', 'in', 'ratio', 'count'}
            if v not in allowed:
                raise ValueError(f"Invalid unit: {v}")
            return v
        
        class Config:
            extra = "forbid"  # No extra fields allowed
            
else:
    # Fallback for when Pydantic not installed
    DecisionProvenanceSchema = None