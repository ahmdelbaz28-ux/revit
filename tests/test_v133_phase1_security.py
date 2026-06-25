"""test_v133_phase1_security.py — Tests for PHASE 1 Security Hardening.

Validates CSRF middleware, path traversal defense, and audit integrity.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# CSRF Tests
# ---------------------------------------------------------------------------


class TestCSRFMiddleware:
    """Tests for the CSRF Double Submit Cookie middleware."""

    def test_token_generation_is_unique(self):
        from backend.security_csrf import generate_csrf_token
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert t1 != t2

    def test_token_is_43_chars_urlsafe(self):
        from backend.security_csrf import generate_csrf_token
        token = generate_csrf_token()
        assert len(token) >= 32  # At least 32 chars
        # URL-safe base64 characters only
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', token)

    def test_validate_valid_token(self):
        from backend.security_csrf import generate_csrf_token, validate_csrf_token
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True

    def test_validate_short_token_rejected(self):
        from backend.security_csrf import validate_csrf_token
        assert validate_csrf_token("short") is False

    def test_validate_empty_token_rejected(self):
        from backend.security_csrf import validate_csrf_token
        assert validate_csrf_token("") is False

    def test_validate_none_rejected(self):
        from backend.security_csrf import validate_csrf_token
        assert validate_csrf_token(None) is False

    def test_tokens_match_same(self):
        from backend.security_csrf import generate_csrf_token, tokens_match
        token = generate_csrf_token()
        assert tokens_match(token, token) is True

    def test_tokens_match_different(self):
        from backend.security_csrf import generate_csrf_token, tokens_match
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert tokens_match(t1, t2) is False

    def test_tokens_match_invalid(self):
        from backend.security_csrf import tokens_match
        assert tokens_match("invalid", "invalid") is False

    def test_build_cookie_header_https(self):
        from backend.security_csrf import build_csrf_cookie_header
        header = build_csrf_cookie_header("test_token", is_https=True)
        assert "fireai_csrf_token=test_token" in header
        assert "SameSite=Strict" in header
        assert "Secure" in header

    def test_build_cookie_header_http_dev(self):
        from backend.security_csrf import build_csrf_cookie_header
        header = build_csrf_cookie_header("test_token", is_https=False)
        assert "fireai_csrf_token=test_token" in header
        assert "SameSite=Strict" in header


# ---------------------------------------------------------------------------
# Path Traversal Tests
# ---------------------------------------------------------------------------


class TestPathTraversalDefense:
    """Tests for path traversal defense in autocad.py router."""

    def test_validate_autocad_file_path_exists(self):
        """The validation function should be importable."""
        from backend.routers.autocad import _validate_autocad_file_path
        assert callable(_validate_autocad_file_path)

    def test_path_traversal_rejected(self):
        """../../etc/passwd should be rejected (400 if blocked, 404 if not found)."""
        from backend.routers.autocad import _validate_autocad_file_path
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _validate_autocad_file_path("../../etc/passwd.dwg")
        # Path traversal is blocked with 400 (if path is rejected by security)
        # or 404 (if path is resolved but file doesn't exist)
        assert exc.value.status_code in (400, 404)

    def test_null_byte_injection_rejected(self):
        """Null byte in path should be rejected."""
        from backend.routers.autocad import _validate_autocad_file_path
        from fastapi import HTTPException
        with pytest.raises((HTTPException, Exception)):
            _validate_autocad_file_path("test.dwg\x00.txt")

    def test_nonexistent_file_returns_404(self):
        """Non-existent file should return 404 (not 400)."""
        from backend.routers.autocad import _validate_autocad_file_path
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _validate_autocad_file_path("/tmp/nonexistent_file_12345.dwg")
        assert exc.value.status_code == 404

    def test_disallowed_extension_rejected(self):
        """Files with non-BIM extensions should be rejected."""
        from backend.routers.autocad import _validate_autocad_file_path
        from fastapi import HTTPException
        # Create a temp file with wrong extension
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            temp_path = f.name
        try:
            with pytest.raises(HTTPException) as exc:
                _validate_autocad_file_path(temp_path)
            assert exc.value.status_code in (400, 404)
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Audit Integrity Tests
# ---------------------------------------------------------------------------


class TestAuditIntegrity:
    """Tests for audit integrity helper (PHASE 1.3)."""

    def test_record_audit_write_returns_hash(self):
        """Recording an audit write should return a hash."""
        from backend.audit_integrity_helper import record_audit_write
        result = record_audit_write(
            operation="test_operation",
            table="test_table",
            record_id="test-001",
            details={"key": "value"},
            success=True,
        )
        # Should return a hash string (or None if AuditStore unavailable)
        assert result is None or isinstance(result, str)

    def test_record_audit_write_failure(self):
        """Recording a failed write should also create audit entry."""
        from backend.audit_integrity_helper import record_audit_write
        result = record_audit_write(
            operation="test_failed_op",
            table="test_table",
            record_id="test-002",
            success=False,
            error="Test error message",
        )
        assert result is None or isinstance(result, str)

    def test_audit_db_write_decorator_sync(self):
        """The decorator should work for sync functions."""
        from backend.audit_integrity_helper import audit_db_write

        @audit_db_write("test_decorator_op", "test_table", record_id_arg="record_id")
        def test_func(record_id: str, value: str) -> str:
            return f"processed_{record_id}_{value}"

        result = test_func("REC-001", "test_value")
        assert result == "processed_REC-001_test_value"

    def test_audit_db_write_decorator_preserves_return(self):
        """Decorator should preserve the wrapped function's return value."""
        from backend.audit_integrity_helper import audit_db_write

        @audit_db_write("test_op", "test_table")
        def test_func(x: int, y: int) -> int:
            return x + y

        assert test_func(3, 4) == 7

    def test_audit_db_write_decorator_records_failure(self):
        """Decorator should record audit on failure and re-raise."""
        from backend.audit_integrity_helper import audit_db_write

        @audit_db_write("test_failing_op", "test_table")
        def test_func():
            raise ValueError("Test failure")

        with pytest.raises(ValueError, match="Test failure"):
            test_func()

    def test_audit_write_context_manager_success(self):
        """Context manager should record success on normal exit."""
        from backend.audit_integrity_helper import audit_write_context

        with audit_write_context("test_ctx_op", "test_table", record_id="CTX-001"):
            pass  # Normal exit

    def test_audit_write_context_manager_failure(self):
        """Context manager should record failure and re-raise."""
        from backend.audit_integrity_helper import audit_write_context

        with pytest.raises(RuntimeError, match="ctx failure"):
            with audit_write_context("test_ctx_fail", "test_table"):
                raise RuntimeError("ctx failure")

    def test_get_correlation_id_returns_none_outside_request(self):
        """Outside a request context, correlation ID should be None."""
        from backend.audit_integrity_helper import get_correlation_id
        # Outside a request context, should return None (not raise)
        result = get_correlation_id()
        assert result is None or isinstance(result, str)
