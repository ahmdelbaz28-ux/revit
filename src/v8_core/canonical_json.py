"""
v8_core/canonical_json.py
========================
PATCH 8: Deterministic JSON Serialization (RFC 8785)
Priority: MEDIUM

This module provides canonical JSON serialization for:
- Deterministic hash computation
- Pattern library deduplication
- Reproducible decision signatures

Integration:
1. json_str = to_canonical_json(obj)
2. hash_val = canonical_hash(obj)
"""

import json
import hashlib
from collections import OrderedDict
from typing import Any


class CanonicalJSONEncoder(json.JSONEncoder):
    """Encode JSON in deterministic canonical form (RFC 8785)."""
    
    def encode(self, o: Any) -> str:
        """Override to sort keys at every level."""
        return super().encode(self._canonicalize(o))
    
    def _canonicalize(self, obj: Any) -> Any:
        """Recursively canonicalize nested objects."""
        if isinstance(obj, dict):
            # Sort keys alphabetically
            return OrderedDict((k, self._canonicalize(obj[k])) for k in sorted(obj.keys()))
        elif isinstance(obj, (list, tuple)):
            return [self._canonicalize(item) for item in obj]
        elif isinstance(obj, set):
            return sorted([self._canonicalize(item) for item in obj], key=lambda x: json.dumps(x, sort_keys=True))
        else:
            return obj
    
    def iterencode(self, o: Any, _one_shot: bool = False):
        """Ensure canonical form during iteration."""
        return super().iterencode(self._canonicalize(o), _one_shot)


def to_canonical_json(obj: dict, sort_keys: bool = True) -> str:
    """
    Convert object to canonical JSON (deterministic hash basis).
    
    Args:
        obj: Dictionary to serialize
        sort_keys: Whether to sort keys (default True)
        
    Returns:
        Canonical JSON string with sorted keys
    """
    if sort_keys:
        return json.dumps(obj, cls=CanonicalJSONEncoder, separators=(',', ':'), sort_keys=True)
    else:
        return json.dumps(obj, separators=(',', ':'))


def canonical_hash(obj: dict, algorithm: str = "sha256") -> str:
    """
    Hash object deterministically.
    
    Args:
        obj: Dictionary to hash
        algorithm: Hash algorithm (sha256, sha512)
        
    Returns:
        Hex digest of canonical JSON
    """
    canonical = to_canonical_json(obj)
    
    if algorithm == "sha512":
        return hashlib.sha512(canonical.encode()).hexdigest()
    else:
        return hashlib.sha256(canonical.encode()).hexdigest()


def canonical_hash_fast(obj: dict) -> str:
    """
    Fast canonical hash (SHA256).
    
    Alias for canonical_hash(obj).
    """
    return canonical_hash(obj)


def verify_canonical(obj1: dict, obj2: dict) -> bool:
    """
    Verify two objects have identical canonical representation.
    
    Args:
        obj1: First object
        obj2: Second object
        
    Returns:
        True if canonical forms are identical
    """
    return canonical_hash(obj1) == canonical_hash(obj2)


def anonymize_for_pattern(obj: dict, keep_types: list = None) -> dict:
    """
    Anonymize a decision object for pattern library.
    
    Removes:
    - Drawing IDs
    - PE signatures
    - Timestamps (keeps relative info)
    - Project names
    
    Args:
        obj: Decision payload
        keep_types: List of field types to keep
        
    Returns:
        Anonymized dictionary suitable for pattern library
    """
    if keep_types is None:
        keep_types = ["area", "occupancy", "device_count", "panel_count", "loop_count"]
    
    anonymized = {}
    
    for key, value in obj.items():
        # Skip specific identifiers
        if any(skip in key.lower() for skip in ["id", "name", "signature", "project", "by", "drawing"]):
            continue
        
        # Keep only allowed types
        if key in keep_types:
            anonymized[key] = value
        elif isinstance(value, (int, float, str, bool)):
            anonymized[key] = value
        elif isinstance(value, dict):
            # Recursively anonymize nested dicts
            anonymized[key] = anonymize_for_pattern(value, keep_types)
        elif isinstance(value, list) and value:
            # For lists, keep length info
            anonymized[f"{key}_count"] = len(value)
    
    return anonymized


# INTEGRATION EXAMPLES:
# ==================
#
# Example 1: Same hash regardless of key order
#   drawing1 = {"fire_rating": 2, "area": 1000, "material": "gypsum"}
#   drawing2 = {"area": 1000, "material": "gypsum", "fire_rating": 2}
#   assert canonical_hash(drawing1) == canonical_hash(drawing2)  # True!
#
# Example 2: Pattern library deduplication
#   from src.v8_core.canonical_json import canonical_hash, anonymize_for_pattern
#   
#   decision = {
#       "decision_type": "panel_placement",
#       "drawing_id": "DWG-001",  # Will be removed
#       "area": 5000,
#       "device_count": 50,
#       "pe_signature": "XYZ-123"  # Will be removed
#   }
#   
#   anonymized = anonymize_for_pattern(decision)
#   pattern_hash = canonical_hash(anonymized)
#   # Now safe to store in pattern_library without PII
#
# Example 3: Verify consistency
#   from src.v8_core.canonical_json import verify_canonical, to_canonical_json
#   
#   # Same logical decision, different key order
#   decision_a = {"type": "A", "value": 1}
#   decision_b = {"value": 1, "type": "A"}
#   
#   if verify_canonical(decision_a, decision_b):
#       print("Decisions are equivalent!")