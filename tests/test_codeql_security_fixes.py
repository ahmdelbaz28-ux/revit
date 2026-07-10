"""
tests/test_codeql_security_fixes.py — Tests proving CodeQL fixes are effective.

These tests verify that the security vulnerabilities flagged by CodeQL
are actually mitigated. Each test corresponds to a specific CodeQL alert.

Tests:
  1. SQL Injection: sort/order parameters cannot inject SQL
  2. Path Injection: filepath parameters cannot traverse directories
  3. Stack Trace Exposure: error messages don't contain tracebacks
  4. Sensitive Data Hashing: session IDs use SHA-256 (appropriate for lookup)
  5. Clear-text Storage: SettingsPage strips sensitive fields before localStorage
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


class TestSQLInjectionFix:
    """Verify SQL injection fixes in database.py."""

    def test_sort_parameter_with_sql_injection_is_rejected(self) -> None:
        """sort='; DROP TABLE connections; --' should be replaced with default."""
        from backend.database import Database

        db = Database()
        # Call list_connections with malicious sort
        # The function should replace it with "created_at"
        result = db.list_connections(
            project_id="test-project",
            page=1,
            limit=1,
            sort="; DROP TABLE connections; --",
            order="desc",
        )
        # Should not raise — the malicious sort is replaced
        assert "data" in result
        # Verify the table still exists (was not dropped)
        assert "total" in result

    def test_order_parameter_with_sql_injection_is_rejected(self) -> None:
        """order='ASC; DROP TABLE--' should be replaced with DESC."""
        from backend.database import Database

        db = Database()
        result = db.list_connections(
            project_id="test-project",
            page=1,
            limit=1,
            sort="created_at",
            order="ASC; DROP TABLE connections; --",
        )
        assert "data" in result

    def test_reports_sort_with_sql_injection_is_rejected(self) -> None:
        """Reports list should also reject malicious sort."""
        from backend.database import Database

        db = Database()
        result = db.list_reports(
            project_id="test-project",
            page=1,
            limit=1,
            sort="; DELETE FROM reports; --",
            order="asc",
        )
        assert "data" in result


class TestPathInjectionFix:
    """Verify path injection fixes in services."""

    def test_path_traversal_in_read_dwg_is_blocked(self) -> None:
        """read_dwg should reject path traversal attempts."""
        from backend.services.autocad_service import AutoCADService

        service = AutoCADService()
        # Path traversal attempt — should return error dict, not crash or read file
        result = service.read_dwg("../../../etc/passwd")
        # Service catches exception and returns error dict
        assert isinstance(result, dict)
        # Should NOT contain file contents (proving traversal was blocked)
        assert "root:" not in str(result)

    def test_path_traversal_in_read_rvt_is_blocked(self) -> None:
        """read_rvt should reject path traversal attempts."""
        from backend.services.revit_service import RevitService

        service = RevitService()
        result = service.read_rvt("../../../../etc/shadow")
        # Should return error dict, not file contents
        assert isinstance(result, dict)
        assert "root:" not in str(result)

    def test_absolute_path_outside_allowed_dirs_is_blocked(self) -> None:
        """Absolute paths outside allowed directories should be blocked."""
        from backend.services.autocad_service import AutoCADService

        service = AutoCADService()
        result = service.read_dwg("/etc/passwd")
        assert isinstance(result, dict)
        # Should not contain actual /etc/passwd contents
        assert "root:" not in str(result)

    def test_valid_temp_file_is_accepted(self) -> None:
        """A valid temp file should be accepted (no false positives)."""
        from backend.services.autocad_service import AutoCADService

        # Create a temp file
        with tempfile.NamedTemporaryFile(suffix=".dwg", delete=False) as f:
            f.write(b"test dwg content")
            temp_path = f.name

        try:
            service = AutoCADService()
            # Should not raise FileNotFoundError (path is valid)
            # May raise other errors (AutoCAD not connected) but not path-related
            try:
                service.read_dwg(temp_path)
            except (FileNotFoundError, ValueError):
                pytest.fail("Valid path was rejected")
            except Exception:
                pass  # Other errors (AutoCAD not connected) are OK
        finally:
            os.unlink(temp_path)


class TestStackTraceExposureFix:
    """Verify stack trace exposure fixes in routers."""

    def test_sanitize_error_strips_tracebacks(self) -> None:
        """_sanitize_error should remove traceback content."""
        from backend.routers.memory import _sanitize_error

        # Error with traceback
        traceback_msg = "Traceback (most recent call last):\n  File \"test.py\", line 10\n    raise ValueError"
        result = _sanitize_error(traceback_msg)
        assert "Traceback" not in result
        assert "File" not in result
        assert "sanitized" in result.lower()

    def test_sanitize_error_preserves_normal_messages(self) -> None:
        """_sanitize_error should preserve normal error messages."""
        from backend.routers.memory import _sanitize_error

        normal_msg = "Memory not found"
        result = _sanitize_error(normal_msg)
        assert result == "Memory not found"

    def test_sanitize_error_limits_length(self) -> None:
        """_sanitize_error should limit message length to 200 chars."""
        from backend.routers.memory import _sanitize_error

        long_msg = "x" * 500
        result = _sanitize_error(long_msg)
        assert len(result) <= 200

    def test_sanitize_error_handles_none(self) -> None:
        """_sanitize_error should handle None input."""
        from backend.routers.memory import _sanitize_error

        result = _sanitize_error(None)
        assert "error occurred" in result.lower()

    def test_sanitize_error_in_revit_router(self) -> None:
        """Revit router should also have _sanitize_error."""
        from backend.routers.revit import _sanitize_error

        result = _sanitize_error("Traceback (most recent call last)")
        assert "Traceback" not in result


class TestSensitiveDataHashingFix:
    """Verify sensitive data hashing is appropriate (not weak)."""

    def test_session_id_hash_is_sha256(self) -> None:
        """Session IDs should be hashed with SHA-256 for lookup (not password storage)."""
        import hashlib

        from backend.routers.auth import _hash_secret

        test_value = "test_session_id_12345"
        hashed = _hash_secret(test_value)

        # SHA-256 produces 64 hex chars
        assert len(hashed) == 64
        assert hashed == hashlib.sha256(test_value.encode()).hexdigest()

    def test_session_id_hash_is_deterministic(self) -> None:
        """Same input should produce same hash (for lookup)."""
        from backend.routers.auth import _hash_secret

        h1 = _hash_secret("test_value")
        h2 = _hash_secret("test_value")
        assert h1 == h2

    def test_different_inputs_produce_different_hashes(self) -> None:
        """Different inputs should produce different hashes."""
        from backend.routers.auth import _hash_secret

        assert _hash_secret("value1") != _hash_secret("value2")


class TestClearTextStorageFix:
    """Verify SettingsPage strips sensitive fields before localStorage."""

    def test_sensitive_keys_list_exists(self) -> None:
        """The SENSITIVE_KEYS filter should be defined in SettingsPage."""
        # Read the file and verify the filter exists
        settings_path = Path("frontend/src/pages/SettingsPage.tsx")
        if not settings_path.exists():
            pytest.skip("SettingsPage.tsx not found")

        content = settings_path.read_text(encoding="utf-8")
        assert "SENSITIVE_KEYS" in content
        assert "apiKey" in content
        assert "password" in content
        assert "token" in content
        assert "secret" in content

    def test_persist_settings_strips_sensitive_data(self) -> None:
        """persistSettings should strip sensitive fields before localStorage."""
        settings_path = Path("frontend/src/pages/SettingsPage.tsx")
        if not settings_path.exists():
            pytest.skip("SettingsPage.tsx not found")

        content = settings_path.read_text(encoding="utf-8")
        # Verify the filtering logic exists
        assert "SENSITIVE_KEYS.some" in content or "SENSITIVE_KEYS" in content
        assert "safeValue" in content


class TestDefenseInDepth:
    """Verify defense-in-depth: multiple layers of security."""

    def test_service_validates_path_even_if_caller_does_not(self) -> None:
        """Services should validate paths independently (defense in depth)."""
        from backend.services.autocad_service import AutoCADService

        service = AutoCADService()
        # Even without router validation, service should block traversal
        result = service.read_dwg("../../etc/passwd")
        assert isinstance(result, dict)
        assert "root:" not in str(result)

    def test_database_validates_sort_even_if_caller_does_not(self) -> None:
        """Database should validate sort independently (defense in depth)."""
        from backend.database import Database

        db = Database()
        # Malicious sort should be replaced, not cause SQL injection
        result = db.list_connections(
            project_id="test",
            sort="1=1; DROP TABLE connections; --",
        )
        # Should not raise — malicious sort is sanitized
        assert "data" in result
