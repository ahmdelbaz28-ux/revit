"""API Key management with role-based access control.

Each API key is associated with a role (admin, engineer, viewer).
Keys are stored as SHA-256 hashes (never plaintext).
On first startup, creates an admin key from FIREAI_API_KEY env var.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Optional

from backend.rbac import APIKeyInfo, Role

logger = logging.getLogger(__name__)

KEYS_FILE = os.getenv("FIREAI_API_KEYS_FILE", "db/api_keys.json")

# Thread-safety lock for TOCTOU prevention on load-modify-save cycles
_keys_lock = threading.Lock()


def _hash_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def _load_keys() -> dict:
    """Load API keys from the JSON file."""
    path = Path(KEYS_FILE)
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load API keys file: %s", e)
        return {}


def _save_keys(keys: dict) -> None:
    """Save API keys to the JSON file."""
    path = Path(KEYS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(keys, f, indent=2)


def _ensure_default_admin_key() -> None:
    """Ensure at least one admin key exists (from env var on first run)."""
    with _keys_lock:
        keys = _load_keys()
        if not keys:
            env_key = os.getenv("FIREAI_API_KEY")
            if env_key:
                key_hash = _hash_key(env_key)
                keys[key_hash] = {
                    "role": Role.ADMIN.value,
                    "description": "Default admin key (from FIREAI_API_KEY)",
                }
                _save_keys(keys)
                logger.info("Created default admin API key from FIREAI_API_KEY env var")


def add_api_key(key: str, role: Role, description: str = "") -> str:
    """Add a new API key. Returns the key hash."""
    with _keys_lock:
        keys = _load_keys()
        key_hash = _hash_key(key)
        keys[key_hash] = {
            "role": role.value,
            "description": description,
        }
        _save_keys(keys)
    logger.info("Added API key with role=%s, desc=%s", role.value, description)
    return key_hash


def validate_api_key(key: str) -> Optional[APIKeyInfo]:
    """Validate an API key and return its info including role.

    Returns None if the key is invalid or empty.
    """
    if not key:
        return None
    with _keys_lock:
        keys = _load_keys()
        key_hash = _hash_key(key)
        info = keys.get(key_hash)
    if not info:
        return None
    return APIKeyInfo(
        key_hash=key_hash,
        role=Role(info["role"]),
        description=info.get("description", ""),
    )


def validate_api_key_by_hash(key_hash: str) -> Optional[APIKeyInfo]:
    """Validate an API key by its hash (for internal lookups).

    Returns None if the hash is not found.
    """
    if not key_hash:
        return None
    with _keys_lock:
        keys = _load_keys()
        info = keys.get(key_hash)
    if not info:
        return None
    return APIKeyInfo(
        key_hash=key_hash,
        role=Role(info["role"]),
        description=info.get("description", ""),
    )


def generate_api_key(role: Role, description: str = "") -> str:
    """Generate a new random API key with the given role.

    Returns the plaintext key (show once!).
    """
    key = f"fireai_{secrets.token_urlsafe(32)}"
    add_api_key(key, role, description)
    return key


def list_api_keys() -> list:
    """List all API keys (without the actual key values)."""
    with _keys_lock:
        keys = _load_keys()
    return [
        {
            "key_hash": kh,
            "role": info["role"],
            "description": info.get("description", ""),
        }
        for kh, info in keys.items()
    ]


def delete_api_key(key_hash: str) -> bool:
    """Delete an API key by its hash."""
    with _keys_lock:
        keys = _load_keys()
        if key_hash in keys:
            del keys[key_hash]
            _save_keys(keys)
            logger.info("Deleted API key %s...", key_hash[:8])
            return True
    return False


def update_api_key_role(key_hash: str, role: Role) -> bool:
    """Update the role of an existing API key."""
    with _keys_lock:
        keys = _load_keys()
        if key_hash in keys:
            keys[key_hash]["role"] = role.value
            _save_keys(keys)
            logger.info("Updated API key %s... role to %s", key_hash[:8], role.value)
            return True
    return False


# Initialize on import
_ensure_default_admin_key()
