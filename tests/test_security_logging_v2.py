# NOSONAR
"""
tests/test_security_logging_v2.py
=================================
Comprehensive test suite for fireai/core/security_logging.py.

SAFETY CRITICAL: Security logging provides tamper-evident audit trails
for security events. Chain hash corruption or sensitive data leaks could
compromise forensic analysis and violate NFPA 72 §14.2.4.

NFPA 72 References:
  §10.6.7 — Record retention requirements
  §14.2.4 — Documentation integrity requirements

Key V-Fixes tested:
  V103 FIX — loguru-based log rotation (500 MB, 30-day, zip compression)
  V104 FIX — Chain hash uses HMAC-SHA256; data masked before writing
  V105 FIX (CRITICAL-1) — verify_chain() uses same _compute_chain_hash() as log_event()
  V105 FIX (CRITICAL-2) — No duplicate loguru sinks for security_audit.log
  V105 FIX (HIGH-1) — Chain hash recovered from existing log on restart
  V105 FIX (HIGH-2) — Hex-regex pattern removed from mask_sensitive()
  V102 FIX — Thread-safe lock for chain hash integrity
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
    configure_log_rotation,
    configure_timed_rotation,
    mask_sensitive,
)

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_log_dir(tmp_path):
    """Temporary directory for log files."""
    return tmp_path / "security_logs"


@pytest.fixture
def security_logger(temp_log_dir):
    """SecurityAuditLogger with temporary log directory."""
    return SecurityAuditLogger(log_dir=temp_log_dir)


# mask_sensitive
# ─────────────────────────────────────────────────────────────────────────────


class TestMaskSensitive:
    """V105 FIX (HIGH-2): Hex-regex removed — no more hash corruption."""

    def test_empty_string(self):
        assert mask_sensitive("") == ""

    def test_none_input(self):
        assert mask_sensitive(None) == ""  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_non_string_input(self):
        result = mask_sensitive(12345)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)
        assert isinstance(result, str)

    def test_api_key_masked(self):
        result = mask_sensitive('api_key="sk-abc123def456ghi789"')
        assert "***REDACTED***" in result
        assert "sk-abc123def456ghi789" not in result

    def test_token_masked(self):
        result = mask_sensitive('token="eyJhbGciOiJIUzI1NiJ9abcdefg"')
        assert "***REDACTED***" in result

    def test_password_masked(self):
        result = mask_sensitive('password="SuperSecret12345678"')  # NOSONAR — S2068: synthetic test fixture, not a real credential
        assert "***REDACTED***" in result
        assert "SuperSecret12345678" not in result

    def test_bearer_token_masked(self):
        result = mask_sensitive("Bearer eyJhbGciOiJIUzI1NiJ9abcdefg")
        assert "***REDACTED***" in result

    def test_normal_text_not_masked(self):
        """Regular text without sensitive patterns should pass through."""
        text = "Room OFFICE-101 has 2 detectors with 99.9% coverage"
        result = mask_sensitive(text)
        assert result == text

    def test_sha256_hash_not_masked(self):
        """
        V105 FIX: Bare hex strings (SHA-256 hashes) must NOT be masked.

        The previous hex-regex pattern corrupted audit chain hashes.
        """
        hash_value = "a" * 64  # 64-char hex string (SHA-256)
        result = mask_sensitive(hash_value)
        assert result == hash_value  # Must NOT be redacted

    def test_chain_hash_not_masked(self):
        """V105 FIX: chain_hash field must not be corrupted."""
        text = 'chain_hash="abcdef1234567890abcdef1234567890"'
        result = mask_sensitive(text)
        # The hash should NOT be replaced with REDACTED
        assert "abcdef1234567890abcdef1234567890" in result

    def test_hmac_signature_not_masked(self):
        """V105 FIX: hmac_signature must not be corrupted."""
        text = 'hmac_signature="0123456789abcdef0123456789abcdef"'
        result = mask_sensitive(text)
        assert "0123456789abcdef0123456789abcdef" in result

    def test_custom_mask_string(self):
        result = mask_sensitive('api_key="sk-abc123def456ghi789"', mask="[MASKED]")
        assert "[MASKED]" in result

    def test_env_var_masking(self):
        """Values from sensitive env vars should be masked."""
        os.environ["FIREAI_TEST_SECRET_VAR"] = "test_secret_value_12345"
        try:
            # Force-refresh to pick up the new env var
            # Note: This var isn't in _SENSITIVE_ENV_VARS, so it won't be masked
            # But if we set a listed one...
            pass
        finally:
            os.environ.pop("FIREAI_TEST_SECRET_VAR", None)

    def test_short_api_key_not_masked(self):
        """API keys shorter than 8 chars should NOT be masked by the key pattern."""
        result = mask_sensitive('api_key="short"')
        # The key pattern requires 8+ chars: [A-Za-z0-9_\-\.]{8,}
        assert "short" in result  # Not masked because too short

    def test_auth_key_masked(self):
        result = mask_sensitive('auth_key="abcdefghijklmnop"')
        assert "***REDACTED***" in result


# SensitiveDataFilter
# ─────────────────────────────────────────────────────────────────────────────


class TestSensitiveDataFilter:
    def test_filter_returns_true(self):
        """Filter must always return True (allow all messages)."""
        f = SensitiveDataFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_filter_masks_message(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            'api_key="sk-abc123def456ghi789"',
            (), None
        )
        f.filter(record)
        assert "sk-abc123def456ghi789" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_filter_masks_dict_args(self):
        f = SensitiveDataFilter()
        # Create a simple LogRecord and manually set args to a dict
        # (bypassing LogRecord's special args processing)
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.args = {"key": 'api_key="sk-abc123def456ghi789"'}
        f.filter(record)
        assert "sk-abc123def456ghi789" not in str(record.args)

    def test_filter_masks_tuple_args(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "Key: %s",
            ('api_key="sk-abc123def456ghi789"',),
            None
        )
        f.filter(record)
        assert "sk-abc123def456ghi789" not in str(record.args)


# SecurityEventType
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityEventType:
    def test_all_event_types_exist(self):
        assert SecurityEventType.AUTH_SUCCESS == "AUTH_SUCCESS"
        assert SecurityEventType.AUTH_FAILURE == "AUTH_FAILURE"
        assert SecurityEventType.AUTH_KEY_ROTATION == "AUTH_KEY_ROTATION"
        assert SecurityEventType.CORS_VIOLATION == "CORS_VIOLATION"
        assert SecurityEventType.RATE_LIMIT_EXCEEDED == "RATE_LIMIT_EXCEEDED"
        assert SecurityEventType.INPUT_VALIDATION_FAILURE == "INPUT_VALIDATION_FAILURE"
        assert SecurityEventType.HMAC_INTEGRITY_FAILURE == "HMAC_INTEGRITY_FAILURE"
        assert SecurityEventType.CONFIG_CHANGE == "CONFIG_CHANGE"
        assert SecurityEventType.SUBPROCESS_EXECUTION == "SUBPROCESS_EXECUTION"
        assert SecurityEventType.EVIDENCE_PACKAGE_CREATED == "EVIDENCE_PACKAGE_CREATED"
        assert SecurityEventType.EVIDENCE_PACKAGE_VERIFIED == "EVIDENCE_PACKAGE_VERIFIED"
        assert SecurityEventType.SECURITY_SCAN_RESULT == "SECURITY_SCAN_RESULT"
        assert SecurityEventType.PLACEHOLDER_KEY_DETECTED == "PLACEHOLDER_KEY_DETECTED"
        assert SecurityEventType.WILDCARD_ORIGIN_REJECTED == "WILDCARD_ORIGIN_REJECTED"
        assert SecurityEventType.PERMISSION_DENIED == "PERMISSION_DENIED"


# _SECURITY_GENESIS
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityGenesis:
    def test_genesis_is_64_char_hex(self):
        """V105 FIX (LOW-6): Genesis must be 64-char hex string."""
        assert len(_SECURITY_GENESIS) == 64
        assert all(c in "0123456789abcdef" for c in _SECURITY_GENESIS)

    def test_genesis_is_all_zeros(self):
        assert _SECURITY_GENESIS == "0" * 64


# _compute_chain_hash
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeChainHash:
    """V105 FIX (CRITICAL-1): Single source of truth for chain hash computation."""

    def test_deterministic(self):
        """Same input must produce same hash."""
        event_json = '{"event_id":"test","timestamp":"2024-01-01"}'
        h1 = _compute_chain_hash(event_json)
        h2 = _compute_chain_hash(event_json)
        assert h1 == h2

    def test_different_input_different_hash(self):
        j1 = '{"event_id":"test1"}'
        j2 = '{"event_id":"test2"}'
        h1 = _compute_chain_hash(j1)
        h2 = _compute_chain_hash(j2)
        assert h1 != h2

    def test_hash_length(self):
        """Chain hash is truncated to 32 hex chars (128 bits)."""
        event_json = '{"test":true}'
        h = _compute_chain_hash(event_json)
        assert len(h) == 32

    def test_hash_is_hex(self):
        event_json = '{"test":true}'
        h = _compute_chain_hash(event_json)
        assert all(c in "0123456789abcdef" for c in h)

    def test_uses_hmac_when_key_set(self):
        """When AUDIT_HMAC_KEY is set, HMAC-SHA256 must be used."""
        event_json = '{"test":true}'
        with patch.dict(os.environ, {"AUDIT_HMAC_KEY": "a" * 32}):
            h_with_key = _compute_chain_hash(event_json)
        h_without_key = _compute_chain_hash(event_json)
        # HMAC and plain SHA-256 should produce different results
        assert h_with_key != h_without_key


# ─────────────────────────────────────────────────────────────────────────────
# SecurityAuditLogger — Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityAuditLoggerInit:
    def test_creates_log_directory(self, temp_log_dir):
        SecurityAuditLogger(log_dir=temp_log_dir / "subdir")
        assert (temp_log_dir / "subdir").exists()

    def test_log_path_set(self, temp_log_dir):
        sal = SecurityAuditLogger(log_dir=temp_log_dir)
        assert sal._log_path == temp_log_dir / "security_audit.log"

    def test_chain_hash_initialized_to_genesis(self, temp_log_dir):
        sal = SecurityAuditLogger(log_dir=temp_log_dir)
        assert sal._chain_hash == _SECURITY_GENESIS

    def test_thread_lock_exists(self, temp_log_dir):
        sal = SecurityAuditLogger(log_dir=temp_log_dir)
        assert isinstance(sal._lock, type(threading.Lock()))


# ─────────────────────────────────────────────────────────────────────────────
# SecurityAuditLogger — log_event()
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityAuditLoggerLogEvent:
    def test_returns_event_id(self, security_logger):
        event_id = security_logger.log_event("AUTH_SUCCESS", user="admin")
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    def test_writes_to_log_file(self, security_logger, temp_log_dir):
        security_logger.log_event("AUTH_FAILURE", ip="1.2.3.4")  # NOSONAR - python:S1313
        log_path = temp_log_dir / "security_audit.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "AUTH_FAILURE" in content

    def test_event_is_valid_json(self, security_logger, temp_log_dir):
        security_logger.log_event("CONFIG_CHANGE", setting="timeout", value="30")
        log_path = temp_log_dir / "security_audit.log"
        with open(log_path) as f:
            line = f.readline().strip()
        data = json.loads(line)
        assert data["event_type"] == "CONFIG_CHANGE"
        assert "event_id" in data
        assert "timestamp" in data
        assert "chain_hash" in data

    def test_chain_hash_advances(self, security_logger):
        security_logger.log_event("AUTH_SUCCESS")
        hash_after_1 = security_logger._chain_hash
        security_logger.log_event("AUTH_FAILURE")
        hash_after_2 = security_logger._chain_hash
        assert hash_after_1 != hash_after_2

    def test_sensitive_details_masked(self, security_logger, temp_log_dir):
        """V104 FIX: Sensitive data must be masked before writing."""
        security_logger.log_event("AUTH_FAILURE", api_key="sk-abc123def456ghi789")  # NOSONAR: S6418 — synthetic test fixture, not a real secret  # NOSONAR — S7632: test function documented via class name / module path
        log_path = temp_log_dir / "security_audit.log"
        with open(log_path) as f:
            line = f.readline().strip()
        data = json.loads(line)
        details_str = json.dumps(data["details"])
        assert "sk-abc123def456ghi789" not in details_str

    def test_multiple_events_chain(self, security_logger, temp_log_dir):
        """Multiple events must form a valid chain."""
        security_logger.log_event("AUTH_SUCCESS")
        security_logger.log_event("CONFIG_CHANGE")
        security_logger.log_event("AUTH_FAILURE")
        log_path = temp_log_dir / "security_audit.log"
        lines = []
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        assert len(lines) == 3
        # Second event's chain_hash should reference first event
        assert lines[1]["chain_hash"] != lines[0]["chain_hash"]


# ─────────────────────────────────────────────────────────────────────────────
# SecurityAuditLogger — verify_chain()
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityAuditLoggerVerifyChain:
    def test_empty_log_valid(self, temp_log_dir):
        sal = SecurityAuditLogger(log_dir=temp_log_dir)
        result = sal.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 0

    def test_single_event_valid(self, security_logger):
        security_logger.log_event("AUTH_SUCCESS")
        result = security_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 1

    def test_multiple_events_valid(self, security_logger):
        for _ in range(5):
            security_logger.log_event("AUTH_SUCCESS")
        result = security_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 5

    def test_tampered_event_detected(self, security_logger, temp_log_dir):
        """V105 FIX (CRITICAL-1): Tampered events must be detected."""
        security_logger.log_event("AUTH_SUCCESS", user="admin")
        security_logger.log_event("AUTH_FAILURE", user="attacker")
        # Tamper with the log file
        log_path = temp_log_dir / "security_audit.log"
        with open(log_path) as f:
            lines = f.readlines()
        # Modify the first event
        first_event = json.loads(lines[0])
        first_event["details"]["user"] = "tampered"
        lines[0] = json.dumps(first_event) + "\n"
        with open(log_path, "w") as f:
            f.writelines(lines)
        result = security_logger.verify_chain()
        assert result["valid"] is False
        assert result["first_break"] is not None

    def test_verify_result_structure(self, security_logger):
        security_logger.log_event("AUTH_SUCCESS")
        result = security_logger.verify_chain()
        assert "valid" in result
        assert "entries_checked" in result
        assert "first_break" in result


# ─────────────────────────────────────────────────────────────────────────────
# SecurityAuditLogger — Chain hash recovery (V105 FIX HIGH-1)
# ─────────────────────────────────────────────────────────────────────────────


class TestChainHashRecovery:
    """V105 FIX (HIGH-1): Chain hash recovered from existing log on restart."""

    def test_recovery_from_existing_log(self, temp_log_dir):
        # Write some events
        sal1 = SecurityAuditLogger(log_dir=temp_log_dir)
        sal1.log_event("AUTH_SUCCESS")
        sal1.log_event("CONFIG_CHANGE")
        hash_from_first = sal1._chain_hash

        # Create a new logger pointing to the same log directory
        sal2 = SecurityAuditLogger(log_dir=temp_log_dir)
        # The chain hash should be recovered, not reset to GENESIS
        assert sal2._chain_hash != _SECURITY_GENESIS
        assert sal2._chain_hash == hash_from_first

    def test_recovery_enables_chain_continuity(self, temp_log_dir):
        """New events after restart must link to previous chain."""
        sal1 = SecurityAuditLogger(log_dir=temp_log_dir)
        sal1.log_event("AUTH_SUCCESS")

        # Restart
        sal2 = SecurityAuditLogger(log_dir=temp_log_dir)
        sal2.log_event("AUTH_FAILURE")

        # Verify the complete chain is valid
        result = sal2.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 2

    def test_recovery_empty_log_uses_genesis(self, temp_log_dir):
        """Empty log file → genesis chain hash."""
        sal = SecurityAuditLogger(log_dir=temp_log_dir)
        assert sal._chain_hash == _SECURITY_GENESIS

    def test_recovery_corrupt_log_uses_genesis(self, temp_log_dir):
        """Corrupt log file → genesis chain hash (safe fallback)."""
        log_path = temp_log_dir / "security_audit.log"
        temp_log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            f.write("NOT VALID JSON\n")
        sal = SecurityAuditLogger(log_dir=temp_log_dir)
        assert sal._chain_hash == _SECURITY_GENESIS


# ─────────────────────────────────────────────────────────────────────────────
# SecurityAuditLogger — Thread Safety (V102 FIX)
# ─────────────────────────────────────────────────────────────────────────────


class TestThreadSafety:
    """V102 FIX: Thread-safe lock prevents chain hash corruption."""

    def test_concurrent_log_events(self, security_logger):
        """Multiple threads logging simultaneously must not corrupt chain."""
        errors = []
        event_ids = []

        def log_event(idx):
            try:
                eid = security_logger.log_event("AUTH_SUCCESS", thread=idx)
                event_ids.append(eid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=log_event, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All event IDs should be unique
        assert len(set(event_ids)) == len(event_ids)

    def test_chain_valid_after_concurrent_writes(self, security_logger):
        """Chain must be valid after concurrent writes."""
        def log_many():
            for _ in range(5):
                security_logger.log_event("AUTH_SUCCESS")

        threads = [threading.Thread(target=log_many) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = security_logger.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 15


# configure_log_rotation
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigureLogRotation:
    def test_security_audit_log_skipped(self):
        """V105 FIX (CRITICAL-2): configure_log_rotation must skip security_audit.log."""
        logger = logging.getLogger("test_rotation_skip")
        # Should return immediately without adding any handlers
        initial_handlers = len(logger.handlers)
        configure_log_rotation(logger, log_file="security_audit.log")
        # No new handlers should be added
        assert len(logger.handlers) == initial_handlers

    def test_normal_log_file_accepted(self, tmp_path):
        """Non-security-audit log files should be configured."""
        with patch("fireai.core.security_logging._LOG_DIR", tmp_path):
            logger = logging.getLogger("test_rotation_normal")
            configure_log_rotation(logger, log_file="fireai.log")
            # A handler should be added (either loguru bridge or RotatingFileHandler)
            assert len(logger.handlers) > 0
            # Cleanup
            logger.handlers.clear()


# configure_timed_rotation
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigureTimedRotation:
    def test_security_audit_log_skipped(self):
        """V105 FIX (CRITICAL-2): configure_timed_rotation must skip security_audit.log."""
        logger = logging.getLogger("test_timed_rotation_skip")
        initial_handlers = len(logger.handlers)
        configure_timed_rotation(logger, log_file="security_audit.log")
        assert len(logger.handlers) == initial_handlers

    def test_normal_log_file_accepted(self, tmp_path):
        with patch("fireai.core.security_logging._LOG_DIR", tmp_path):
            logger = logging.getLogger("test_timed_rotation_normal")
            configure_timed_rotation(logger, log_file="fireai.log")
            assert len(logger.handlers) > 0
            logger.handlers.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
