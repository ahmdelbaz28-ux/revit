"""
test_api_keys.py — Direct unit tests for backend/api_keys.py.

Covers key hashing, validation, add/list/delete/update operations,
timing-safe dummy verify, and the O(1) lookup index.
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_keys_file(tmp_path, monkeypatch):
    """Redirect the keys file to a temp directory for each test."""
    keys_file = str(tmp_path / "api_keys.json")
    monkeypatch.setenv("FIREAI_API_KEYS_FILE", keys_file)
    monkeypatch.setenv("FIREAI_API_KEYS_SECRET_FILE", str(tmp_path / "api_keys.secret"))
    # Clear any cached server secret and validation cache
    import backend.api_keys as ak

    ak._SERVER_SECRET = b""
    ak._VALIDATED_KEY_CACHE.clear()
    yield keys_file
    ak._VALIDATED_KEY_CACHE.clear()


class TestKeyHashing:
    """Core hashing and verification functions."""

    def test_hash_key_returns_string(self):
        from backend.api_keys import _hash_key

        h = _hash_key("my-secret-key")
        assert isinstance(h, str)
        assert len(h) > 0

    def test_hash_key_is_non_deterministic(self):
        from backend.api_keys import _hash_key

        h1 = _hash_key("my-secret-key")
        h2 = _hash_key("my-secret-key")
        assert h1 != h2

    def test_verify_key_success(self):
        from backend.api_keys import _hash_key, _verify_key

        h = _hash_key("my-secret-key")
        assert _verify_key("my-secret-key", h) is True

    def test_verify_key_wrong_key_fails(self):
        from backend.api_keys import _hash_key, _verify_key

        h = _hash_key("my-secret-key")
        assert _verify_key("wrong-key", h) is False

    def test_verify_key_empty_hash_fails(self):
        from backend.api_keys import _verify_key

        assert _verify_key("key", "") is False

    def test_lookup_key_is_deterministic(self):
        from backend.api_keys import _lookup_key

        lk1 = _lookup_key("my-secret-key")
        lk2 = _lookup_key("my-secret-key")
        assert lk1 == lk2
        assert lk1.startswith("hk$")


class TestCRUDOperations:
    """API key lifecycle operations."""

    def test_add_and_validate_key(self):
        from backend.api_keys import add_api_key, validate_api_key
        from backend.rbac import Role

        plaintext = "test-api-key-12345"
        add_api_key(plaintext, Role.ADMIN, "test key")
        info = validate_api_key(plaintext)
        assert info is not None
        assert info.role == Role.ADMIN

    def test_validate_invalid_key_returns_none(self):
        from backend.api_keys import add_api_key, validate_api_key
        from backend.rbac import Role

        add_api_key("valid-key", Role.ADMIN)
        assert validate_api_key("invalid-key") is None

    def test_generate_api_key(self):
        from backend.api_keys import generate_api_key, validate_api_key
        from backend.rbac import Role

        key = generate_api_key(Role.ENGINEER, "generated")
        assert key.startswith("fireai_")
        assert len(key) > 10
        info = validate_api_key(key)
        assert info is not None
        assert info.role == Role.ENGINEER

    def test_list_api_keys(self):
        from backend.api_keys import add_api_key, list_api_keys
        from backend.rbac import Role

        add_api_key("key-admin", Role.ADMIN, "admin key")
        add_api_key("key-viewer", Role.VIEWER, "viewer key")
        keys = list_api_keys()
        assert len(keys) == 2
        roles = {k["role"] for k in keys}
        assert roles == {"admin", "viewer"}

    def test_delete_api_key(self):
        from backend.api_keys import add_api_key, delete_api_key, validate_api_key
        from backend.rbac import Role

        plaintext = "key-to-delete"
        add_api_key(plaintext, Role.VIEWER)
        info = validate_api_key(plaintext)
        assert info is not None
        deleted = delete_api_key(info.key_hash)
        assert deleted is True
        assert validate_api_key(plaintext) is None

    def test_update_api_key_role(self):
        from backend.api_keys import add_api_key, update_api_key_role, validate_api_key
        from backend.rbac import Role

        plaintext = "key-to-update"
        add_api_key(plaintext, Role.VIEWER)
        info = validate_api_key(plaintext)
        assert info.role == Role.VIEWER
        updated = update_api_key_role(info.key_hash, Role.ADMIN)
        assert updated is True
        new_info = validate_api_key(plaintext)
        assert new_info.role == Role.ADMIN

    def test_validate_too_long_key_returns_none(self):
        from backend.api_keys import validate_api_key

        long_key = "a" * 2000
        assert validate_api_key(long_key) is None

    def test_validate_empty_key_returns_none(self):
        from backend.api_keys import validate_api_key

        assert validate_api_key("") is None
        assert validate_api_key(None) is None  # type: ignore[arg-type]
