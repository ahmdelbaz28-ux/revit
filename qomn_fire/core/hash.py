"""
QOMN-FIRE CRYPTOGRAPHIC AND DETERMINISTIC DATA COMPACTION
"""

import hashlib

def get_bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def get_string_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
