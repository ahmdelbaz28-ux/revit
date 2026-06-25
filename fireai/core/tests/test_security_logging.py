"""fireai/core/tests/test_security_logging.py — Security Logging Tests
=====================================================================
Task 2.14: Enhance security test coverage (91% → 95%)

Tests cover:
  1. mask_sensitive() — API keys, tokens, Bearer, env vars, edge cases
  2. SensitiveDataFilter — logging filter integration
  3. SecurityEventType — all event type constants
  4. SecurityAuditLogger — chain hashing, log_event, verify_chain
  5. _compute_chain_hash — HMAC vs SHA-256 modes
  6. configure_log_rotation — security_audit.log protection (V105)
  7. configure_timed_rotation — security_audit.log protection
  8. Chain hash recovery on restart (V105 HIGH-1)
  9. Thread-safety of log_event (V102 FIX)
  10. Environment variable cache refresh
"""

from __future__ import annotations

import json
import logging
import os
import threading
from unittest.mock import patch

import pytest

from fireai.core.security_logging import (
    _SECURITY_GENESIS,
    SecurityAuditLogger,
    SecurityEventType,
    SensitiveDataFilter,
    _compute_chain_hash,
    _force_refresh_env_cache,
    configure_log_rotation,
    configure_timed_rotation,
    mask_sensitive,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_log_dir(tmp_path):
    """Temporary directory for log files."""
    return tmp_path / "security_logs"


@pytest.fixture
def audit_logger(temp_log_dir):
    """Fresh SecurityAuditLogger with temp directory."""
    return SecurityAuditLogger(log_dir=temp_log_dir)


@pytest.fixture
def clean_env():
    """Ensure no audit HMAC key leaks between tests."""
    old = os.environ.pop("AUDIT_HMAC_KEY", None)
    yield
    if old is not None:
        os.environ["AUDIT_HMAC_KEY"] = old
    else:
        os.environ.pop("AUDIT_HMAC_KEY", None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. mask_sensitive()
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaskSensitive:
    """mask_sensitive() replaces secrets with ***REDACTED***."""

    def test_api_key_masked(self):
        result = mask_sensitive('api_key="sk-abc123def456ghi789"')
        assert "***REDACTED***" in result
        assert "sk-abc123def456ghi789" not in result

    def test_token_masked(self):
        result = mask_sensitive('token="abcdef12345678"')
        assert "***REDACTED***" in result

    def test_bearer_token_masked(self):
        result = mask_sensitive("Bearer eyJhbGciOiJIUzI1NiJ9payload")
        assert "***REDACTED***" in result
        assert "eyJhbGciOiJIUzI1NiJ9payload" not in result

    def test_password_masked(self):
        result = mask_sensitive('password="SuperSecret123!"')
        assert "***REDACTED***" in result

    def test_auth_key_masked(self):
        result = mask_sensitive('auth_key="my-secret-key-1234"')
        assert "***REDACTED***" in result

    def test_non_sensitive_text_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog"
        assert mask_sensitive(text) == text

    def test_empty_string_returns_empty(self):
        assert mask_sensitive("") == ""

    def test_none_returns_empty(self):
        assert mask_sensitive(None) == ""

    def test_non_string_input_converted(self):
        result = mask_sensitive(42)
        assert result == "42"

    def test_chain_hash_not_corrupted(self):
        """V105 FIX: Hex-regex no longer corrupts hash values."""
        chain_hash = "a" * 64  # 64-char hex string (SHA-256)
        result = mask_sensitive(f"chain_hash={chain_hash}")
        assert chain_hash in result

    def test_entry_hash_not_corrupted(self):
        """V105 FIX: entry_hash values must survive masking."""
        entry_hash = "b" * 64
        result = mask_sensitive(f"entry_hash={entry_hash}")
        assert entry_hash in result

    def test_hmac_signature_not_corrupted(self):
        """V105 FIX: hmac_signature must survive masking."""
        sig = "c" * 64
        result = mask_sensitive(f"hmac_signature={sig}")
        assert sig in result

    def test_custom_mask_string(self):
        result = mask_sensitive('api_key="secretvalue12"', mask="[REMOVED]")
        assert "[REMOVED]" in result

    def test_env_var_value_masked(self):
        """Values from _SENSITIVE_ENV_VARS are masked."""
        os.environ["FIREAI_API_KEY"] = "test-api-key-value-12345"
        _force_refresh_env_cache()
        try:
            result = mask_sensitive("Using FIREAI_API_KEY=test-api-key-value-12345")
            assert "test-api-key-value-12345" not in result
            assert "***REDACTED***" in result
        finally:
            del os.environ["FIREAI_API_KEY"]
            _force_refresh_env_cache()

    def test_credential_keyword_masked(self):
        result = mask_sensitive('credential="mycred12345678"')
        assert "***REDACTED***" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SensitiveDataFilter
# ═══════════════════════════════════════════════════════════════════════════════


class TestSensitiveDataFilter:
    """SensitiveDataFilter masks sensitive data in log records."""

    def test_filter_masks_string_msg(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg='api_key="sk-secret12345678"', args=None, exc_info=None,
        )
        result = f.filter(record)
        assert result is True  # Filter always returns True (allows record)
        assert "sk-secret12345678" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_filter_with_dict_args(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Key: %(key)s", args=None, exc_info=None,
        )
        # Simulate dict args (logging uses %(key)s format for dict args)
        record.args = {"key": 'token="secretvalue12"'}
        f.filter(record)
        assert "secretvalue12" not in str(record.args)

    def test_filter_with_tuple_args(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Key: %s", args=('api_key="mykey12345678"',), exc_info=None,
        )
        f.filter(record)
        assert "mykey12345678" not in str(record.args)

    def test_filter_non_string_msg_passes(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=42, args=None, exc_info=None,
        )
        result = f.filter(record)
        assert result is True

    def test_filter_none_args_passes(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="normal message", args=None, exc_info=None,
        )
        result = f.filter(record)
        assert result is True
        assert record.msg == "normal message"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SecurityEventType
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityEventType:
    """All security event types are defined as class constants."""

    def test_auth_success(self):
        assert SecurityEventType.AUTH_SUCCESS == "AUTH_SUCCESS"

    def test_auth_failure(self):
        assert SecurityEventType.AUTH_FAILURE == "AUTH_FAILURE"

    def test_auth_key_rotation(self):
        assert SecurityEventType.AUTH_KEY_ROTATION == "AUTH_KEY_ROTATION"

    def test_cors_violation(self):
        assert SecurityEventType.CORS_VIOLATION == "CORS_VIOLATION"

    def test_rate_limit_exceeded(self):
        assert SecurityEventType.RATE_LIMIT_EXCEEDED == "RATE_LIMIT_EXCEEDED"

    def test_input_validation_failure(self):
        assert SecurityEventType.INPUT_VALIDATION_FAILURE == "INPUT_VALIDATION_FAILURE"

    def test_hmac_integrity_failure(self):
        assert SecurityEventType.HMAC_INTEGRITY_FAILURE == "HMAC_INTEGRITY_FAILURE"

    def test_config_change(self):
        assert SecurityEventType.CONFIG_CHANGE == "CONFIG_CHANGE"

    def test_subprocess_execution(self):
        assert SecurityEventType.SUBPROCESS_EXECUTION == "SUBPROCESS_EXECUTION"

    def test_evidence_package_created(self):
        assert SecurityEventType.EVIDENCE_PACKAGE_CREATED == "EVIDENCE_PACKAGE_CREATED"

    def test_evidence_package_verified(self):
        assert SecurityEventType.EVIDENCE_PACKAGE_VERIFIED == "EVIDENCE_PACKAGE_VERIFIED"

    def test_security_scan_result(self):
        assert SecurityEventType.SECURITY_SCAN_RESULT == "SECURITY_SCAN_RESULT"

    def test_placeholder_key_detected(self):
        assert SecurityEventType.PLACEHOLDER_KEY_DETECTED == "PLACEHOLDER_KEY_DETECTED"

    def test_wildcard_origin_rejected(self):
        assert SecurityEventType.WILDCARD_ORIGIN_REJECTED == "WILDCARD_ORIGIN_REJECTED"

    def test_permission_denied(self):
        assert SecurityEventType.PERMISSION_DENIED == "PERMISSION_DENIED"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _compute_chain_hash
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeChainHash:
    """Chain hash computation: HMAC-SHA256 when key set, plain SHA-256 otherwise."""

    def test_without_hmac_key(self, clean_env):
        """Without AUDIT_HMAC_KEY, uses plain SHA-256."""
        os.environ.pop("AUDIT_HMAC_KEY", None)
        result = _compute_chain_hash("test event data")
        assert isinstance(result, str)
        assert len(result) == 32  # truncated to 32 hex chars
        # Deterministic
        assert _compute_chain_hash("test event data") == result

    def test_with_hmac_key(self, clean_env):
        """With AUDIT_HMAC_KEY, uses HMAC-SHA256."""
        os.environ["AUDIT_HMAC_KEY"] = "test-hmac-key"
        try:
            result = _compute_chain_hash("test event data")
            assert isinstance(result, str)
            assert len(result) == 32
            # Different from plain SHA-256
            os.environ.pop("AUDIT_HMAC_KEY")
            plain_result = _compute_chain_hash("test event data")
            assert result != plain_result
        finally:
            os.environ.pop("AUDIT_HMAC_KEY", None)

    def test_different_inputs_different_hashes(self, clean_env):
        os.environ.pop("AUDIT_HMAC_KEY", None)
        h1 = _compute_chain_hash("event A")
        h2 = _compute_chain_hash("event B")
        assert h1 != h2


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SecurityAuditLogger — log_event and verify_chain
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityAuditLoggerLogEvent:
    """SecurityAuditLogger.log_event() writes tamper-evident entries."""

    def test_log_event_returns_event_id(self, audit_logger):
        event_id = audit_logger.log_event("AUTH_SUCCESS", user="alice")
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    def test_log_event_writes_json(self, audit_logger, temp_log_dir):
        audit_logger.log_event("AUTH_FAILURE", ip="1.2.3.4")
        log_path = temp_log_dir / "security_audit.log"
        assert log_path.exists()
        content = log_path.read_text()
        event = json.loads(content.strip().split("\n")[-1])
        assert event["event_type"] == "AUTH_FAILURE"
        assert event["details"]["ip"] == "1.2.3.4"

    def test_log_event_includes_chain_hash(self, audit_logger, temp_log_dir):
        audit_logger.log_event("AUTH_SUCCESS")
        log_path = temp_log_dir / "security_audit.log"
        content = log_path.read_text()
        event = json.loads(content.strip().split("\n")[-1])
        assert "chain_hash" in event
        assert event["chain_hash"] == _SECURITY_GENESIS

    def test_log_event_chain_advances(self, audit_logger, temp_log_dir):
        audit_logger.log_event("AUTH_SUCCESS")
        audit_logger.log_event("CONFIG_CHANGE")
        log_path = temp_log_dir / "security_audit.log"
        lines = [l for l in log_path.read_text().strip().split("\n") if l]
        event1 = json.loads(lines[0])
        event2 = json.loads(lines[1])
        # Second event's chain_hash should be derived from first
        assert event2["chain_hash"] != _SECURITY_GENESIS
        assert event2["chain_hash"] != event1["chain_hash"]

    def test_log_event_masks_sensitive_details(self, audit_logger, temp_log_dir):
        audit_logger.log_event("AUTH_FAILURE", api_key="sk-secret12345678")
        log_path = temp_log_dir / "security_audit.log"
        content = log_path.read_text()
        assert "sk-secret12345678" not in content

    def test_log_event_includes_timestamp(self, audit_logger, temp_log_dir):
        audit_logger.log_event("AUTH_SUCCESS")
        log_path = temp_log_dir / "security_audit.log"
        content = log_path.read_text()
        event = json.loads(content.strip())
        assert "timestamp" in event
        assert "T" in event["timestamp"]  # ISO format


class TestSecurityAuditLoggerVerifyChain:
    """SecurityAuditLogger.verify_chain() checks tamper-evident chain."""

    def test_verify_empty_chain(self, audit_logger):
        result = audit_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 0

    def test_verify_valid_chain(self, audit_logger):
        audit_logger.log_event("AUTH_SUCCESS")
        audit_logger.log_event("CONFIG_CHANGE")
        result = audit_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 2

    def test_verify_single_event(self, audit_logger):
        audit_logger.log_event("AUTH_SUCCESS")
        result = audit_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 1

    def test_verify_detects_tampering(self, audit_logger, temp_log_dir):
        audit_logger.log_event("AUTH_SUCCESS")
        audit_logger.log_event("CONFIG_CHANGE")
        log_path = temp_log_dir / "security_audit.log"
        # Tamper with the first event — this breaks the chain because
        # the hash of the tampered event no longer matches the
        # chain_hash stored in the second event.
        original = log_path.read_text()
        tampered = original.replace("AUTH_SUCCESS", "TAMPERED_EVENT")
        log_path.write_text(tampered)
        # Create a new logger to re-verify
        new_logger = SecurityAuditLogger(log_dir=temp_log_dir)
        result = new_logger.verify_chain()
        assert result["valid"] is False

    def test_verify_missing_log_file(self, temp_log_dir):
        """verify_chain returns valid=True when log doesn't exist."""
        logger = SecurityAuditLogger(log_dir=temp_log_dir)
        result = logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Chain Hash Recovery on Restart (V105 HIGH-1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestChainHashRecovery:
    """V105 HIGH-1: Chain hash is recovered from existing log on restart."""

    def test_chain_continues_after_restart(self, temp_log_dir):
        # Write events with first logger
        logger1 = SecurityAuditLogger(log_dir=temp_log_dir)
        logger1.log_event("AUTH_SUCCESS")
        logger1.log_event("CONFIG_CHANGE")
        # Create new logger (simulating restart)
        logger2 = SecurityAuditLogger(log_dir=temp_log_dir)
        event_id = logger2.log_event("PERMISSION_DENIED")
        assert isinstance(event_id, str)
        # Verify entire chain
        result = logger2.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 3

    def test_genesis_on_empty_log(self, temp_log_dir):
        """New logger on empty log dir starts with GENESIS chain."""
        logger = SecurityAuditLogger(log_dir=temp_log_dir)
        assert logger._chain_hash == _SECURITY_GENESIS


# ═══════════════════════════════════════════════════════════════════════════════
# 7. configure_log_rotation — security_audit.log protection
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigureLogRotation:
    """V105 CRITICAL-2: configure_log_rotation skips security_audit.log."""

    def test_skips_security_audit_log(self, temp_log_dir, clean_env):
        """configure_log_rotation must NOT add sinks for security_audit.log."""
        test_logger = logging.getLogger(f"test_rotation_{id(self)}")
        original_handler_count = len(test_logger.handlers)
        with patch("fireai.core.security_logging._LOG_DIR", temp_log_dir):
            configure_log_rotation(test_logger, log_file="security_audit.log")
        # No handlers should be added
        assert len(test_logger.handlers) == original_handler_count

    def test_adds_handler_for_normal_log(self, temp_log_dir, clean_env):
        """configure_log_rotation adds handler for non-security logs."""
        test_logger = logging.getLogger(f"test_rotation_normal_{id(self)}")
        original_handler_count = len(test_logger.handlers)
        with patch("fireai.core.security_logging._LOG_DIR", temp_log_dir):
            configure_log_rotation(test_logger, log_file="fireai.log")
        assert len(test_logger.handlers) > original_handler_count
        # Clean up
        test_logger.handlers = test_logger.handlers[:original_handler_count]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. configure_timed_rotation — security_audit.log protection
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigureTimedRotation:
    """V105 CRITICAL-2: configure_timed_rotation skips security_audit.log."""

    def test_skips_security_audit_log(self, temp_log_dir, clean_env):
        test_logger = logging.getLogger(f"test_timed_rotation_{id(self)}")
        original_handler_count = len(test_logger.handlers)
        with patch("fireai.core.security_logging._LOG_DIR", temp_log_dir):
            configure_timed_rotation(test_logger, log_file="security_audit.log")
        assert len(test_logger.handlers) == original_handler_count


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Thread Safety (V102 FIX)
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    """V102 FIX: log_event is thread-safe."""

    def test_concurrent_log_events(self, audit_logger, temp_log_dir):
        """Concurrent log_event calls must not corrupt the chain."""
        errors = []

        def log_events(n):
            try:
                for i in range(n):
                    audit_logger.log_event(
                        "AUTH_FAILURE", thread=threading.current_thread().name, index=i
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=log_events, args=(5,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        # Verify chain integrity
        result = audit_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 20


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Environment Variable Cache
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvVarCache:
    """Env var cache refreshes for key rotation support."""

    def test_force_refresh(self):
        """_force_refresh_env_cache updates the cache."""
        _force_refresh_env_cache()
        # No assertion on contents — just verify no crash

    def test_cache_picks_up_new_env_var(self):
        """Setting an env var after startup gets picked up."""
        os.environ["FIREAI_API_KEY"] = "new-key-value-12345"
        _force_refresh_env_cache()
        try:
            result = mask_sensitive("Using FIREAI_API_KEY=new-key-value-12345")
            assert "new-key-value-12345" not in result
        finally:
            del os.environ["FIREAI_API_KEY"]
            _force_refresh_env_cache()
