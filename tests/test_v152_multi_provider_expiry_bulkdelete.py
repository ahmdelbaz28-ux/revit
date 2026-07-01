"""
tests/test_v152_multi_provider_expiry_bulkdelete.py — V152 feature tests.

Covers:
  1. Multi-provider support (POST/GET/DELETE for anthropic, gemini, azure, openrouter, opencode)
  2. Key expiry (expires_at column + is_expired field + expired key test rejection)
  3. Bulk delete (delete all keys for a provider + delete specific ids)
  4. Provider validation (unsupported provider → 400)
  5. /providers/list endpoint
  6. Backward compat: /openai/* still works alongside /{provider}/*

Rule 10: tests are NEVER modified — only production code. If a test fails,
the production code is wrong.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _isolated_master_key(monkeypatch):
    import secrets as _secrets
    fresh_key = _secrets.token_bytes(32).hex()
    monkeypatch.setenv("FIREAI_VISION_KEY_ENCRYPTION_KEY", fresh_key)
    import backend.vision_key_store as vks
    monkeypatch.setattr(vks, "_MASTER_KEY", None)
    yield
    monkeypatch.setattr(vks, "_MASTER_KEY", None)


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_v152.db")
    import backend.database as dbmod
    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setattr(dbmod, "_DB_PATH", db_path)
    monkeypatch.setenv("DIGITAL_TWIN_DB_PATH", db_path)
    monkeypatch.setenv("FIREAI_VISION_KEY_FILE", str(tmp_path / "vision_master.key"))
    dbmod.Database(db_path)
    monkeypatch.setattr(dbmod, "_db", dbmod.Database(db_path))
    yield db_path
    monkeypatch.setattr(dbmod, "_db", None)


@pytest.fixture
def admin_client(temp_db, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import app
    monkeypatch.setenv("FIREAI_API_KEY", "test-api-key-for-testing-only")
    # Disable CSRF in tests (no browser to set the cookie)
    monkeypatch.setenv("FIREAI_CSRF_DISABLED", "1")
    # Disable rate limiting: slowapi Limiter has an `enabled` attribute.
    # Setting it to False makes all @limiter.limit decorators skip enforcement.
    import backend.limiter as limiter_mod
    monkeypatch.setattr(limiter_mod.limiter, "enabled", False)
    with TestClient(
        app,
        raise_server_exceptions=False,
        headers={"X-API-Key": "test-api-key-for-testing-only"},
    ) as client:
        yield client


# ── 1. Multi-provider support ──────────────────────────────────────────────


class TestMultiProvider:
    """Test that POST/GET/DELETE work for all supported providers."""

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "azure", "openrouter", "opencode"])
    def test_post_key_for_each_provider(self, admin_client, provider):
        """POST a key for each supported provider — must succeed."""
        base_urls = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "azure": "https://myresource.openai.azure.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "opencode": "https://api.opencode.ai/v1",
        }
        resp = admin_client.post(
            f"/api/v1/settings/keys/{provider}",
            json={
                "api_key": f"sk-{provider}-test-key-1234567890abcd",
                "base_url": base_urls[provider],
                "model_name": "test-model",
            },
        )
        assert resp.status_code == 201, f"{provider}: {resp.text}"
        body = resp.json()
        assert body["provider"] == provider
        assert body["masked_key"].startswith("fe_")
        # Plaintext never in response
        assert f"sk-{provider}-test-key-1234567890abcd" not in resp.text

    def test_get_keys_for_specific_provider(self, admin_client):
        """GET keys for anthropic must NOT return openai keys."""
        # Add an openai key
        admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-openai-isolation-test-1234567890", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        # Add an anthropic key
        admin_client.post(
            "/api/v1/settings/keys/anthropic",
            json={"api_key": "sk-ant-isolation-test-1234567890abcd", "base_url": "https://api.anthropic.com/v1", "model_name": "claude-3-5-sonnet-20241022"},
        )
        # GET anthropic keys — must only return the anthropic key
        resp = admin_client.get("/api/v1/settings/keys/anthropic")
        assert resp.status_code == 200
        body = resp.json()
        assert all(k["provider"] == "anthropic" for k in body), "Provider isolation failed"
        assert len(body) >= 1

    def test_unsupported_provider_rejected(self, admin_client):
        """POST to an unsupported provider must return 400."""
        resp = admin_client.post(
            "/api/v1/settings/keys/unsupported_provider",
            json={"api_key": "sk-unsupported-test-1234567890", "base_url": "https://example.com", "model_name": "test"},
        )
        assert resp.status_code == 400

    def test_provider_defaults_applied(self, admin_client):
        """If base_url/model_name are empty, provider defaults are used."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-defaults-test-1234567890abcd", "base_url": "", "model_name": ""},
        )
        assert resp.status_code == 201
        body = resp.json()
        # OpenAI defaults must be applied
        assert body["base_url"] == "https://api.openai.com/v1"
        assert body["model_name"] == "gpt-4o"

    def test_backward_compat_openai_path_still_works(self, admin_client):
        """The /openai path (V151) must still work alongside /{provider} (V152)."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-backward-compat-test-1234567890", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        assert resp.status_code == 201
        # GET via /openai
        resp = admin_client.get("/api/v1/settings/keys/openai")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ── 2. Key expiry ───────────────────────────────────────────────────────────


class TestKeyExpiry:
    """Test the expires_at + is_expired fields."""

    def test_post_key_with_expiry(self, admin_client):
        """POST a key with expires_at — must persist and return is_expired=false."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={
                "api_key": "sk-expiry-test-1234567890abcd",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o",
                "expires_at": "2099-12-31T23:59:59+00:00",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["expires_at"] is not None
        assert body["is_expired"] is False

    def test_expired_key_shown_as_expired(self, admin_client):
        """A key with expires_at in the past must have is_expired=true."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={
                "api_key": "sk-past-expiry-test-1234567890",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o",
                "expires_at": "2020-01-01T00:00:00+00:00",  # past
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_expired"] is True

    def test_no_expiry_means_not_expired(self, admin_client):
        """A key without expires_at must have is_expired=false."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={
                "api_key": "sk-no-expiry-test-1234567890ab",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["expires_at"] is None
        assert body["is_expired"] is False

    def test_expired_key_test_returns_error(self, admin_client):
        """Testing an expired key must return ok=false with 'expired' error."""
        # Add an expired key
        r = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={
                "api_key": "sk-test-expired-key-1234567890",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o",
                "expires_at": "2020-01-01T00:00:00+00:00",  # past
            },
        )
        assert r.status_code == 201
        key_id = r.json()["id"]
        # Test it — must return expired error, NOT make a network call
        resp = admin_client.post(f"/api/v1/settings/keys/openai/{key_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "expired" in (body["error"] or "").lower()


# ── 3. Bulk delete ──────────────────────────────────────────────────────────


class TestBulkDelete:
    """Test the bulk-delete endpoint."""

    def test_bulk_delete_all_for_provider(self, admin_client):
        """bulk-delete with no ids deletes ALL keys for the provider."""
        # Add 3 keys (only the last will be active, but all 3 exist)
        for i in range(3):
            admin_client.post(
                "/api/v1/settings/keys/openai",
                json={"api_key": f"sk-bulk-delete-test-{i}-1234567890", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
            )
        # Verify keys exist (including inactive)
        resp = admin_client.get("/api/v1/settings/keys/openai?include_inactive=true")
        assert len(resp.json()) >= 3
        # Bulk-delete all
        resp = admin_client.post(
            "/api/v1/settings/keys/openai/bulk-delete",
            json={"ids": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] >= 3
        # Verify all gone
        resp = admin_client.get("/api/v1/settings/keys/openai?include_inactive=true")
        assert len(resp.json()) == 0

    def test_bulk_delete_specific_ids(self, admin_client):
        """bulk-delete with ids deletes only those keys."""
        # Add 2 keys
        r1 = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-bulk-specific-1-1234567890ab", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        r2 = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-bulk-specific-2-1234567890cd", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        id1 = r1.json()["id"]
        # Delete only id1
        resp = admin_client.post(
            "/api/v1/settings/keys/openai/bulk-delete",
            json={"ids": [id1]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] == 1
        # id1 is gone, id2's key (the active one) still exists
        resp = admin_client.get("/api/v1/settings/keys/openai")
        assert all(k["id"] != id1 for k in resp.json())

    def test_bulk_delete_provider_isolation(self, admin_client):
        """bulk-delete for openai must NOT touch anthropic keys."""
        # Add openai + anthropic keys
        admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-iso-openai-1234567890abcd", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        admin_client.post(
            "/api/v1/settings/keys/anthropic",
            json={"api_key": "sk-iso-anthropic-1234567890abcd", "base_url": "https://api.anthropic.com/v1", "model_name": "claude-3-5-sonnet-20241022"},
        )
        # Bulk-delete openai only
        admin_client.post(
            "/api/v1/settings/keys/openai/bulk-delete",
            json={"ids": None},
        )
        # Anthropic key must still exist
        resp = admin_client.get("/api/v1/settings/keys/anthropic")
        assert len(resp.json()) >= 1, "Anthropic key was wrongly deleted by openai bulk-delete"


# ── 4. Providers list endpoint ─────────────────────────────────────────────


class TestProvidersList:
    """Test the /providers/list endpoint."""

    def test_list_providers(self, admin_client):
        """GET /providers/list must return all supported providers."""
        resp = admin_client.get("/api/v1/settings/keys/providers/list")
        assert resp.status_code == 200
        body = resp.json()
        assert "providers" in body
        providers = body["providers"]
        expected = {"openai", "anthropic", "gemini", "azure", "openrouter", "opencode"}
        assert set(providers.keys()) == expected
        # Each provider must have default_base_url + default_model + test_path
        for prov_name, prov_config in providers.items():
            assert "default_base_url" in prov_config
            assert "default_model" in prov_config
            assert "test_path" in prov_config
