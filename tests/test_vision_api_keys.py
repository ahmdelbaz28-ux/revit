"""
tests/test_vision_api_keys.py — V151 Vision API Keys test suite.

Covers:
  1. AES-256-GCM encryption/decryption roundtrip (backend/vision_key_store.py)
  2. Masking never exposes plaintext (Rule 1: ABSOLUTE TRUTH)
  3. Tamper detection (auth tag verification)
  4. DB schema migration (vision_api_keys table creation)
  5. CRUD via the /api/v1/settings/keys/openai router
  6. RBAC enforcement (admin only; viewer/engineer rejected)
  7. Plaintext NEVER returned in any response
  8. CUA loop fallback chain (DB → env → OpenCV)
  9. CUA loop NEVER raises (Rule 1 + safety contract)
 10. Empty/invalid input handling

Rule 10 (TEST-AND-FIX LOOP): if any test fails, the production code is
wrong, NOT the test. The test asserts the V151 spec exactly.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_master_key(monkeypatch, tmp_path):
    """
    Isolate the master encryption key per-test:
    - Use a deterministic env var so each test gets a fresh, known key.
    - Reset the cached _MASTER_KEY so _load_master_key re-reads env.
    """
    # Generate a fresh 32-byte hex key per test
    import secrets as _secrets

    fresh_key = _secrets.token_bytes(32).hex()
    monkeypatch.setenv("FIREAI_VISION_KEY_ENCRYPTION_KEY", fresh_key)
    # Clear cached master key
    import backend.vision_key_store as vks

    monkeypatch.setattr(vks, "_MASTER_KEY", None)
    yield
    monkeypatch.setattr(vks, "_MASTER_KEY", None)


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """Use a temp SQLite DB file for each test that needs DB access.

    Patches the Database singleton AND the default __init__ argument so that
    get_db() returns a Database bound to our temp file.
    """
    db_path = str(tmp_path / "test_vision.db")
    # Force Database singleton to be re-created
    import backend.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    # Patch the module-level _DB_PATH (used as default arg in Database.__init__)
    monkeypatch.setattr(dbmod, "_DB_PATH", db_path)
    # Also override the env var so any code that reads it directly sees the temp path
    monkeypatch.setenv("DIGITAL_TWIN_DB_PATH", db_path)
    # Also reset vision_key_store master key file default
    monkeypatch.setenv(
        "FIREAI_VISION_KEY_FILE", str(tmp_path / "vision_master.key")
    )
    # Pre-warm the singleton with our temp path
    dbmod.Database(db_path)
    monkeypatch.setattr(dbmod, "_db", dbmod.Database(db_path))
    yield db_path
    monkeypatch.setattr(dbmod, "_db", None)


# ── 1. Encryption / Decryption ──────────────────────────────────────────────


class TestEncryption:
    """Test AES-256-GCM encrypt/decrypt primitives."""

    def test_roundtrip(self):
        from backend.vision_key_store import encrypt_key, decrypt_key

        plaintext = "sk-proj-abcdef1234567890ABCD"
        encrypted = encrypt_key(plaintext)
        assert encrypted != plaintext
        assert encrypted.startswith("v1$")
        parts = encrypted.split("$", 2)
        assert len(parts) == 3
        assert parts[0] == "v1"
        # Verify decryption returns the original
        assert decrypt_key(encrypted) == plaintext

    def test_each_encryption_has_unique_nonce(self):
        """Same plaintext must produce different ciphertexts (random nonce)."""
        from backend.vision_key_store import encrypt_key

        e1 = encrypt_key("sk-test-1234567890")
        e2 = encrypt_key("sk-test-1234567890")
        assert e1 != e2, "Nonce must be random — same plaintext must yield different ciphertexts"

    def test_plaintext_not_in_ciphertext(self):
        """The ciphertext must never contain the plaintext as a substring."""
        from backend.vision_key_store import encrypt_key

        plaintext = "sk-proj-VERY_UNIQUE_PLAINTEXT_MARKER_12345"
        encrypted = encrypt_key(plaintext)
        assert plaintext not in encrypted
        # Also check the base64-decoded ciphertext doesn't contain plaintext bytes
        import base64

        parts = encrypted.split("$", 2)
        ct_bytes = base64.b64decode(parts[2])
        assert plaintext.encode() not in ct_bytes

    def test_empty_plaintext_rejected(self):
        from backend.vision_key_store import encrypt_key

        with pytest.raises(ValueError):
            encrypt_key("")

    def test_tamper_detection(self):
        """Modifying the ciphertext must cause decryption to fail (auth tag)."""
        from backend.vision_key_store import encrypt_key, decrypt_key
        import base64

        plaintext = "sk-proj-tamper-test-1234567890"
        encrypted = encrypt_key(plaintext)
        parts = encrypted.split("$", 2)
        # Flip a bit in the ciphertext
        ct = bytearray(base64.b64decode(parts[2]))
        ct[0] ^= 0xFF
        tampered = f"v1${parts[1]}${base64.b64encode(bytes(ct)).decode()}"
        with pytest.raises(ValueError, match="decryption failed"):
            decrypt_key(tampered)

    def test_tamper_detection_nonce(self):
        """Modifying the nonce must cause decryption to fail."""
        from backend.vision_key_store import encrypt_key, decrypt_key
        import base64

        plaintext = "sk-proj-nonce-tamper-test-1234567890"
        encrypted = encrypt_key(plaintext)
        parts = encrypted.split("$", 2)
        nonce = bytearray(base64.b64decode(parts[1]))
        nonce[0] ^= 0xFF
        tampered = f"v1${base64.b64encode(bytes(nonce)).decode()}${parts[2]}"
        with pytest.raises(ValueError):
            decrypt_key(tampered)

    def test_wrong_master_key_fails(self, monkeypatch):
        """Decrypting with a different master key must fail (auth tag)."""
        from backend.vision_key_store import encrypt_key, decrypt_key

        plaintext = "sk-proj-master-key-test-1234567890"
        encrypted = encrypt_key(plaintext)
        # Reset cache and use a different key
        import backend.vision_key_store as vks

        monkeypatch.setattr(vks, "_MASTER_KEY", None)
        monkeypatch.setenv(
            "FIREAI_VISION_KEY_ENCRYPTION_KEY",
            "b" * 64,  # different hex key
        )
        with pytest.raises(ValueError, match="decryption failed"):
            decrypt_key(encrypted)

    def test_malformed_format_rejected(self):
        from backend.vision_key_store import decrypt_key

        for bad in ["garbage", "", "v1$", "v1$abc", "v2$abc$def", "v1$abc$def$extra"]:
            with pytest.raises(ValueError):
                decrypt_key(bad)

    def test_invalid_base64_rejected(self):
        from backend.vision_key_store import decrypt_key

        # Valid format but invalid base64
        with pytest.raises(ValueError):
            decrypt_key("v1$!!!$@@@")


# ── 2. Masking ───────────────────────────────────────────────────────────────


class TestMasking:
    """Test that mask_key never exposes more than 2 prefix + 4 suffix chars."""

    def test_standard_mask(self):
        from backend.vision_key_store import mask_key

        masked = mask_key("sk-proj-abcdef1234567890ABCD")
        assert masked == "fe_sk***...***ABCD", f"Got: {masked}"

    def test_short_key(self):
        from backend.vision_key_store import mask_key

        # Keys <= 6 chars: suffix is hidden to avoid exposing the whole key
        masked = mask_key("abc")
        assert masked == "fe_ab***...***", f"Got: {masked}"
        # Verify no suffix leak
        assert "abc" not in masked

    def test_empty_key(self):
        from backend.vision_key_store import mask_key

        assert mask_key("") == "fe_***...***"

    def test_plaintext_never_in_mask(self):
        """The masked form must NEVER contain the plaintext as a substring."""
        from backend.vision_key_store import mask_key

        plaintext = "sk-proj-SECRET_LONG_KEY_1234567890abcdef"
        masked = mask_key(plaintext)
        assert plaintext not in masked
        # Verify only prefix (2 chars) + suffix (4 chars) are exposed
        assert plaintext[:2] in masked
        assert plaintext[-4:] in masked
        # The middle must be hidden
        middle = plaintext[2:-4]
        assert middle not in masked

    def test_whitespace_stripped(self):
        from backend.vision_key_store import mask_key

        masked = mask_key("  sk-proj-test1234XYZ  \n")
        # No whitespace or newlines in the masked output
        assert "\n" not in masked
        assert "  " not in masked


# ── 3. DB Schema ─────────────────────────────────────────────────────────────


class TestDBSchema:
    """Test that the vision_api_keys table is created correctly."""

    def test_table_created_sqlite(self, temp_db):
        from backend.database import get_db

        db = get_db()
        with db._transaction() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='vision_api_keys'"
            )
            row = cur.fetchone()
            assert row is not None, "vision_api_keys table must be created"
            assert row[0] == "vision_api_keys"

    def test_table_columns(self, temp_db):
        from backend.database import get_db

        db = get_db()
        with db._transaction() as cur:
            cur.execute("PRAGMA table_info(vision_api_keys)")
            cols = {r[1]: r for r in cur.fetchall()}
        expected = {
            "id", "provider", "encrypted_key", "masked_key", "base_url",
            "model_name", "is_active", "created_at", "updated_at", "last_used_at",
        }
        assert expected.issubset(cols.keys()), f"Missing columns: {expected - set(cols.keys())}"

    def test_indexes_created(self, temp_db):
        from backend.database import get_db

        db = get_db()
        with db._transaction() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='vision_api_keys'"
            )
            idx_names = {r[0] for r in cur.fetchall()}
        assert "idx_vision_keys_provider" in idx_names
        assert "idx_vision_keys_active" in idx_names


# ── 4. CUA Loop Fallback ────────────────────────────────────────────────────


class TestCuaLoopFallback:
    """Test the CUA loop's DB → env → OpenCV fallback chain."""

    def test_opencv_fallback_when_no_key(self, temp_db, monkeypatch):
        """No DB key + no env key → OpenCV fallback."""
        # Ensure no env key
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Make a small test image
        import cv2
        import numpy as np

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:] = (50, 50, 50)
        cv2.rectangle(img, (10, 10), (50, 50), (255, 255, 255), 2)
        ok, buf = cv2.imencode(".png", img)
        assert ok
        image_bytes = buf.tobytes()

        from fireai.vision.cua_loop import analyze_screenshot

        result = analyze_screenshot(image_bytes, prompt="test")
        assert result.ok, f"OpenCV fallback must succeed — got error: {result.error}"
        assert result.provider == "opencv"
        assert result.description  # non-empty
        assert "100x100" in result.description

    def test_empty_image_returns_none_provider(self, temp_db, monkeypatch):
        """Empty image bytes → 'none' provider with error (no raise)."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from fireai.vision.cua_loop import analyze_screenshot

        result = analyze_screenshot(b"", prompt="test")
        assert result.provider == "none"
        assert not result.ok
        assert result.error  # has error message

    def test_invalid_image_falls_through(self, temp_db, monkeypatch):
        """Invalid image bytes (not a real image) → OpenCV fails → 'none' provider."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from fireai.vision.cua_loop import analyze_screenshot

        # garbage bytes that OpenCV cannot decode
        result = analyze_screenshot(b"not an image", prompt="test")
        # OpenCV should fail to decode → fall through to 'none'
        # OR succeed with no elements if OpenCV is lenient
        assert result.provider in ("opencv", "none")
        if result.provider == "opencv":
            assert not result.ok
        # NEVER raises

    def test_db_key_preferred_over_env(self, temp_db, monkeypatch):
        """
        When both a DB key and an env key exist, the DB key is tried first.

        We can't actually call OpenAI in tests, so we verify priority by
        checking that the DB loader returns a key when one is stored.
        """
        # Store a key in DB
        from backend.vision_key_store import encrypt_key, mask_key, utc_now_iso
        from backend.database import get_db
        import uuid

        db = get_db()
        now = utc_now_iso()
        key_id = str(uuid.uuid4())
        plaintext = "sk-proj-DB_KEY_PRIORITY_TEST_12345"
        masked = mask_key(plaintext)
        encrypted = encrypt_key(plaintext)
        with db._transaction() as cur:
            cur.execute(
                """INSERT INTO vision_api_keys
                   (id, provider, encrypted_key, masked_key, base_url, model_name,
                    is_active, created_at, updated_at, last_used_at, description)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, '')""",
                (key_id, "openai", encrypted, masked, "https://api.openai.com/v1", "gpt-4o", now, now),
            )

        # Also set an env key (would be tried second if DB key fails)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-ENV_FALLBACK_KEY_12345")

        # Load DB key — must succeed and return the DB-stored values
        from fireai.vision.cua_loop import _load_active_db_key

        loaded = _load_active_db_key()
        assert loaded is not None
        assert loaded["api_key"] == plaintext
        assert loaded["masked_key"] == masked
        assert loaded["base_url"] == "https://api.openai.com/v1"
        assert loaded["model_name"] == "gpt-4o"

    def test_corrupted_db_key_falls_through(self, temp_db, monkeypatch):
        """If the DB key's ciphertext is corrupted, the loader returns None
        (and the CUA loop falls through to env / OpenCV)."""
        from backend.database import get_db
        import uuid

        db = get_db()
        from backend.vision_key_store import mask_key, utc_now_iso

        now = utc_now_iso()
        key_id = str(uuid.uuid4())
        # Insert a key with garbage ciphertext (can't decrypt)
        with db._transaction() as cur:
            cur.execute(
                """INSERT INTO vision_api_keys
                   (id, provider, encrypted_key, masked_key, base_url, model_name,
                    is_active, created_at, updated_at, last_used_at, description)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, '')""",
                (
                    key_id,
                    "openai",
                    "v1$GARBAGE$GARBAGE",  # malformed ciphertext
                    mask_key("sk-proj-fake-1234567890"),
                    "https://api.openai.com/v1",
                    "gpt-4o",
                    now,
                    now,
                ),
            )

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from fireai.vision.cua_loop import _load_active_db_key

        loaded = _load_active_db_key()
        assert loaded is None, "Corrupted DB key must return None, not raise"

    def test_cua_loop_never_raises(self, temp_db, monkeypatch):
        """The CUA loop must NEVER raise — always return a result."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from fireai.vision.cua_loop import analyze_screenshot

        # Various edge-case inputs
        inputs = [b"", b"x", b"\x00" * 100, b"not an image at all"]
        for inp in inputs:
            result = analyze_screenshot(inp)
            assert hasattr(result, "provider")
            assert hasattr(result, "ok")
            assert hasattr(result, "error")
            # Must return a result, not raise


# ── 5. Router (RBAC + CRUD) ────────────────────────────────────────────────


class TestSettingsRouter:
    """Test the /api/v1/settings/keys/openai router."""

    @pytest.fixture
    def admin_client(self, temp_db, monkeypatch):
        """
        TestClient authenticated as ADMIN via the FIREAI_API_KEY env var
        bypass (security_middleware.py:430-435). The middleware compares the
        X-API-Key header to FIREAI_API_KEY and grants ADMIN role on match.
        """
        from fastapi.testclient import TestClient
        from backend.app import app

        # The env var is set globally by backend/tests/conftest.py to
        # "test-api-key-for-testing-only". Set it here too in case that
        # conftest wasn't imported (e.g. when running this file standalone).
        monkeypatch.setenv("FIREAI_API_KEY", "test-api-key-for-testing-only")

        with TestClient(
            app,
            raise_server_exceptions=False,
            headers={"X-API-Key": "test-api-key-for-testing-only"},
        ) as client:
            yield client

    @pytest.fixture
    def viewer_client(self, temp_db, monkeypatch):
        """
        TestClient authenticated as VIEWER via a registered RBAC key.
        The middleware validates the key against api_keys.json and grants
        the VIEWER role. The router's require_permission(SYSTEM_CONFIG)
        check should then reject with 403.
        """
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend.api_keys import add_api_key
        from backend.rbac import Role
        import backend.api_keys as api_keys_mod

        # Use a fresh keys file in temp_db's directory
        keys_file = os.path.join(os.path.dirname(temp_db), "test_api_keys_viewer.json")
        monkeypatch.setattr(api_keys_mod, "KEYS_FILE", keys_file)
        monkeypatch.setattr(api_keys_mod, "_SERVER_SECRET", b"")
        # Clear the env var bypass so the viewer key MUST be validated via RBAC
        monkeypatch.delenv("FIREAI_API_KEY", raising=False)
        # Register a viewer key
        viewer_key = "test-viewer-key-vision-tests"
        add_api_key(viewer_key, Role.VIEWER, "Vision tests viewer key")

        with TestClient(
            app,
            raise_server_exceptions=False,
            headers={"X-API-Key": viewer_key},
        ) as client:
            yield client

    def test_post_key_returns_masked_only(self, admin_client):
        """POST must return ONLY the masked key — never plaintext."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={
                "api_key": "sk-proj-SECRET_PLAINTEXT_1234567890",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o",
                "description": "test",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "masked_key" in body
        assert body["masked_key"].startswith("fe_")
        assert "sk-proj-SECRET_PLAINTEXT_1234567890" not in resp.text
        assert "sk-proj-SECRET_PLAINTEXT_1234567890" not in str(body)
        # Verify only first 2 + last 4 chars are exposed
        assert "sk" in body["masked_key"]
        assert "7890" in body["masked_key"]
        assert "SECRET_PLAINTEXT" not in body["masked_key"]

    def test_post_then_get_returns_masked(self, admin_client):
        """POST a key, then GET — must never return plaintext."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={
                "api_key": "sk-proj-GET_TEST_1234567890abcd",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o",
            },
        )
        assert resp.status_code == 201
        # GET list
        resp = admin_client.get("/api/v1/settings/keys/openai")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        # Verify plaintext NEVER appears in the GET response
        assert "sk-proj-GET_TEST_1234567890abcd" not in resp.text
        # Verify masked form is present
        masked = body[0]["masked_key"]
        assert masked.startswith("fe_")
        assert "sk" in masked  # first 2 chars
        assert "abcd" in masked  # last 4 chars

    def test_post_deactivates_previous_active(self, admin_client):
        """Adding a new key should deactivate the previous active key."""
        # Add first key
        r1 = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-proj-FIRST_KEY_1234567890ab", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        assert r1.status_code == 201
        # Add second key
        r2 = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-proj-SECOND_KEY_1234567890cd", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        assert r2.status_code == 201
        # GET active keys — should only return the second
        resp = admin_client.get("/api/v1/settings/keys/openai")
        assert resp.status_code == 200
        body = resp.json()
        active = [k for k in body if k["is_active"]]
        assert len(active) == 1, f"Expected 1 active key, got {len(active)}"
        # mask_key returns last 4 chars only (spec: fe_***...***f4c1)
        assert active[0]["masked_key"].endswith("90cd")  # second key's last 4 chars

    def test_delete_key(self, admin_client):
        """DELETE removes the key."""
        # Add
        r = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-proj-DELETE_ME_1234567890ef", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        assert r.status_code == 201
        key_id = r.json()["id"]
        # Delete
        d = admin_client.delete(f"/api/v1/settings/keys/openai/{key_id}")
        assert d.status_code == 204
        # GET — should be gone
        g = admin_client.get("/api/v1/settings/keys/openai")
        body = g.json()
        assert all(k["id"] != key_id for k in body)

    def test_delete_nonexistent_is_idempotent(self, admin_client):
        """DELETE on a non-existent id returns 204 (no info leak)."""
        d = admin_client.delete("/api/v1/settings/keys/openai/nonexistent-id-12345")
        assert d.status_code == 204

    def test_get_nonexistent_returns_404(self, admin_client):
        """GET on a non-existent id returns 404."""
        g = admin_client.get("/api/v1/settings/keys/openai/nonexistent-id-12345")
        assert g.status_code == 404

    def test_viewer_role_rejected(self, viewer_client):
        """VIEWER role must NOT be able to POST (403)."""
        resp = viewer_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "sk-proj-VIEWER_REJECT_1234567890", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        assert resp.status_code == 403, f"VIEWER must be rejected, got {resp.status_code}"

    def test_short_api_key_rejected(self, admin_client):
        """API key shorter than 8 chars must be rejected by pydantic validation."""
        resp = admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": "short", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        assert resp.status_code == 422  # pydantic validation error

    def test_plaintext_not_in_logs(self, admin_client, caplog):
        """The plaintext key must NEVER appear in logs."""
        import logging

        caplog.set_level(logging.INFO)
        plaintext = "sk-proj-LOG_LEAK_TEST_1234567890xyz"
        admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": plaintext, "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        # Verify plaintext is NOT in any log record
        for record in caplog.records:
            assert plaintext not in record.getMessage(), (
                f"Plaintext key leaked in log: {record.getMessage()!r}"
            )
            assert plaintext not in str(record.__dict__), "Plaintext leaked in record dict"

    def test_db_persists_encrypted_form(self, admin_client, temp_db):
        """Verify the DB stores the encrypted form, not plaintext."""
        plaintext = "sk-proj-DB_PERSIST_TEST_1234567890gh"
        admin_client.post(
            "/api/v1/settings/keys/openai",
            json={"api_key": plaintext, "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
        )
        # Read the DB directly
        from backend.database import get_db

        db = get_db()
        with db._transaction() as cur:
            cur.execute("SELECT encrypted_key FROM vision_api_keys WHERE provider='openai'")
            rows = cur.fetchall()
        assert len(rows) >= 1
        for row in rows:
            enc = row["encrypted_key"]
            assert enc.startswith("v1$"), f"DB must store encrypted form, got: {enc!r}"
            assert plaintext not in enc, "Plaintext must NOT be in the stored encrypted_key"
