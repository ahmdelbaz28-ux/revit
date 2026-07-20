# File-level suppression comment removed per audit guide (V143 hardening).
# Per-line justified suppressions are preserved.
"""
tests/test_etap_integration.py — ETAP Integration tests.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# Ensure ETAP_ENCRYPTION_KEY is set for tests
os.environ.setdefault("ETAP_ENCRYPTION_KEY", __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())

from backend.integrations.etap_crypto import encrypt_password, mask_password
from backend.rbac import Permission


# ─── Crypto Tests ────────────────────────────────────────────────────────────

class TestEtapCrypto:
        """Tests for ETAP password encryption utilities."""

        def test_encrypt_password_returns_string(self):
                result = encrypt_password("test_password")
                assert isinstance(result, str)
                assert result != "test_password"

        def test_decrypt_password_returns_original(self):
                original = "my_secure_password"
                encrypted = encrypt_password(original)
                decrypted = __import__("backend.integrations.etap_crypto", fromlist=["decrypt_password"]).decrypt_password(encrypted)
                assert decrypted == original

        def test_encrypt_empty_password_returns_empty(self):
                result = encrypt_password("")
                assert result == ""

        def test_decrypt_empty_password_returns_empty(self):
                result = __import__("backend.integrations.etap_crypto", fromlist=["decrypt_password"]).decrypt_password("")
                assert result == ""

        def test_mask_password_short(self):
                result = mask_password("short")
                assert result == "****"

        def test_mask_password_normal(self):
                result = mask_password("abcdefghijkl")
                assert result == "abcd...ijkl"

        def test_mask_password_empty(self):
                result = mask_password("")
                assert result == ""

        def test_different_passwords_produce_different_ciphertexts(self):
                enc1 = encrypt_password("password1")
                enc2 = encrypt_password("password1")
                assert enc1 != enc2  # Fernet uses random IV


# ─── RBAC Tests ──────────────────────────────────────────────────────────────

class TestEtapRBAC:
        """Tests for ETAP RBAC permissions."""

        def test_integration_read_permission_exists(self):
                assert Permission.INTEGRATION_READ == "integration:read"

        def test_integration_manage_permission_exists(self):
                assert Permission.INTEGRATION_MANAGE == "integration:manage"

        def test_admin_has_integration_permissions(self):
                from backend.rbac import ROLE_PERMISSIONS, Role
                admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
                assert Permission.INTEGRATION_READ in admin_perms
                assert Permission.INTEGRATION_MANAGE in admin_perms

        def test_engineer_has_integration_permissions(self):
                from backend.rbac import ROLE_PERMISSIONS, Role
                engineer_perms = ROLE_PERMISSIONS[Role.ENGINEER]
                assert Permission.INTEGRATION_READ in engineer_perms
                assert Permission.INTEGRATION_MANAGE in engineer_perms

        def test_viewer_has_integration_read_only(self):
                from backend.rbac import ROLE_PERMISSIONS, Role
                viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
                assert Permission.INTEGRATION_READ in viewer_perms
                assert Permission.INTEGRATION_MANAGE not in viewer_perms


# ─── Schemas Tests ───────────────────────────────────────────────────────────

class TestEtapSchemas:
        """Tests for ETAP Pydantic schemas."""

        def test_connection_settings_valid(self):
                from backend.integrations.etap_schemas import EtapConnectionSettings
                settings = EtapConnectionSettings(
                        host="etap.example.com",
                        port=9876,
                        username="admin",
                        password="secret",
                )
                assert settings.host == "etap.example.com"
                assert settings.port == 9876

        def test_connection_settings_empty_host_raises(self):
                from backend.integrations.etap_schemas import EtapConnectionSettings
                with pytest.raises(Exception):
                        EtapConnectionSettings(
                                host="",
                                port=9876,
                                username="admin",
                                password="secret",
                        )

        def test_export_request_defaults(self):
                from backend.integrations.etap_schemas import EtapExportRequest
                req = EtapExportRequest(project_id="proj-1")
                assert req.include_loads is True
                assert req.include_sources is True
                assert req.include_topology is False
                assert req.format == "csv"

        def test_import_request_defaults(self):
                from backend.integrations.etap_schemas import EtapImportRequest
                req = EtapImportRequest(project_id="proj-1", etap_project_id="etap-1")
                assert req.import_loads is True
                assert req.import_sources is True
                assert req.conflict_resolution == "skip"

        def test_settings_update_partial(self):
                from backend.integrations.etap_schemas import EtapSettingsUpdate
                update = EtapSettingsUpdate(host="newhost.example.com")
                assert update.host == "newhost.example.com"
                assert update.port is None


# ─── Database Tests ──────────────────────────────────────────────────────────

class TestEtapDatabase:
        """Tests for ETAP database tables."""

        def test_etap_integrations_table_exists(self):
                from backend.database import Database
                db = Database(":memory:")
                try:
                        with db._transaction() as cur:
                                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='etap_integrations'")
                                row = cur.fetchone()
                                assert row is not None
                finally:
                        db._conn.close()

        def test_etap_sync_logs_table_exists(self):
                from backend.database import Database
                db = Database(":memory:")
                try:
                        with db._transaction() as cur:
                                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='etap_sync_logs'")
                                row = cur.fetchone()
                                assert row is not None
                finally:
                        db._conn.close()

        def test_etap_integrations_index_exists(self):
                from backend.database import Database
                db = Database(":memory:")
                try:
                        with db._transaction() as cur:
                                cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_etap_integrations_project'")
                                row = cur.fetchone()
                                assert row is not None
                finally:
                        db._conn.close()
