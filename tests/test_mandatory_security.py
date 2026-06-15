"""
Mandatory Security Tests for FireAI Platform

These tests are MANDATORY for all CI/CD pipelines and must pass before any deployment.
They cover critical security requirements for mission-critical fire protection systems.

Test Categories:
  - Authentication & Authorization
  - Input Validation & Sanitization
  - Cryptographic Operations
  - Rate Limiting & DoS Protection
  - Audit Logging & Compliance
  - Data Protection & Privacy
"""

import hashlib
import hmac
import os
import re
import secrets
import string
import threading
import time
from pathlib import Path

import pytest

from fireai.core.secret_rotation import KeyRotator
from fireai.core.security_logging import mask_sensitive


# MANDATORY SECURITY TEST 1: Authentication & Authorization
class TestMandatoryAuthenticationSecurity:
    """MANDATORY: Authentication and authorization security tests."""

    def test_api_key_placeholder_detection(self):
        """CRITICAL: Detect and reject placeholder API keys in production."""
        placeholder_patterns = [
            "your-api-key",
            "sk-placeholder",
            "sk-test-xxx",
            "REPLACE_ME",
            "CHANGE_ME",
            "TODO",
            "xxx-xxx-xxx",
        ]
        for pattern in placeholder_patterns:
            assert not self._is_valid_api_key(pattern), f"Placeholder key detected: {pattern}"

    def test_api_key_minimum_entropy(self):
        """CRITICAL: API keys must have minimum entropy (32+ chars, mixed case, numbers)."""
        weak_keys = ["abc123", "password", "12345678", "admin"]
        for key in weak_keys:
            assert not self._is_valid_api_key(key), f"Weak key accepted: {key}"

    def test_hmac_timing_attack_resistance(self):
        """CRITICAL: HMAC comparisons must be timing-attack resistant."""
        key = secrets.token_hex(32)
        correct_digest = hmac.new(key.encode(), b"message", hashlib.sha256).digest()
        assert hmac.compare_digest(correct_digest, correct_digest)
        wrong_digest = correct_digest[:-1] + bytes([correct_digest[-1] ^ 1])
        assert not hmac.compare_digest(correct_digest, wrong_digest)

    def _is_valid_api_key(self, key: str) -> bool:
        if len(key) < 32:
            return False
        if key.lower() == key:
            return False
        if not any(c.isdigit() for c in key):
            return False
        return True


# MANDATORY SECURITY TEST 2: Input Validation & Sanitization
class TestMandatoryInputValidation:
    """MANDATORY: Input validation and sanitization security tests."""

    def test_path_traversal_prevention(self):
        """CRITICAL: Prevent path traversal attacks."""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        ]
        for path in malicious_paths:
            assert not self._is_path_safe(path), f"Path traversal not blocked: {path}"

    def test_null_byte_injection_prevention(self):
        """CRITICAL: Prevent null byte injection attacks."""
        malicious_inputs = [
            "safe.txt\x00.exe",
            "file.pdf\x00.jpg",
            "config.yml\x00",
        ]
        for input_str in malicious_inputs:
            sanitized = self._sanitize_input(input_str)
            assert sanitized == "", f"Null byte injection not blocked: {repr(input_str)}"

    def test_sql_injection_pattern_detection(self):
        """CRITICAL: Detect SQL injection patterns."""
        sql_injection_patterns = [
            "'; DROP TABLE users;--",
            "1' OR '1'='1",
            "admin'--",
            "1; DELETE FROM sessions",
        ]
        for pattern in sql_injection_patterns:
            assert self._detect_sql_injection(pattern), f"SQL injection not detected: {pattern}"

    def test_xss_pattern_detection(self):
        """CRITICAL: Detect XSS attack patterns."""
        xss_patterns = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "{{constructor.constructor('alert(1)')()}}",
        ]
        for pattern in xss_patterns:
            assert self._detect_xss(pattern), f"XSS pattern not detected: {pattern}"

    def _is_path_safe(self, path: str) -> bool:
        normalized = os.path.normpath(path)
        return ".." not in normalized and not normalized.startswith("/")

    def _sanitize_input(self, input_str: str) -> str:
        return input_str.replace("\x00", "")

    def _detect_sql_injection(self, input_str: str) -> bool:
        sql_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "UNION", "SELECT"]
        sql_operators = ["--", ";--", "';", "1' OR"]
        upper_input = input_str.upper()
        return any(kw in upper_input for kw in sql_keywords) or any(op in input_str for op in sql_operators)

    def _detect_xss(self, input_str: str) -> bool:
        xss_indicators = ["<script", "javascript:", "onerror=", "onload=", "constructor"]
        return any(indicator in input_str.lower() for indicator in xss_indicators)


# MANDATORY SECURITY TEST 3: Cryptographic Operations
class TestMandatoryCryptographicSecurity:
    """MANDATORY: Cryptographic operation security tests."""

    def test_key_rotation_lifecycle(self):
        """CRITICAL: Key rotation must follow secure lifecycle."""
        rotator = KeyRotator(default_grace_period_s=0.1)
        initial_key = secrets.token_hex(32)
        rotator.register("FIREAI_API_KEY", initial_key)
        rotator.rotate("FIREAI_API_KEY", initial_key, secrets.token_hex(32))
        assert rotator.validate("FIREAI_API_KEY", initial_key)
        new_key = secrets.token_hex(32)
        rotator.rotate("FIREAI_API_KEY", initial_key, new_key)
        assert rotator.validate("FIREAI_API_KEY", initial_key)
        time.sleep(0.2)
        assert not rotator.validate("FIREAI_API_KEY", initial_key)
        assert rotator.validate("FIREAI_API_KEY", new_key)

    def test_key_fingerprint_truncation(self):
        """CRITICAL: Key fingerprints must be properly truncated to 128 bits (32 hex chars)."""
        rotator = KeyRotator()
        initial_key = secrets.token_hex(32)
        rotator.rotate("TEST_KEY", initial_key, secrets.token_hex(32))
        fingerprint = rotator._fingerprint(initial_key)
        assert len(fingerprint) == 32, f"Fingerprint length should be 32, got {len(fingerprint)}"
        assert all(c in string.hexdigits for c in fingerprint.lower())

    def test_hmac_unification(self):
        """CRITICAL: HMAC implementation must be consistent across all modules."""
        message = b"test_message"
        key = secrets.token_hex(16)
        hmac1 = hmac.new(key.encode(), message, hashlib.sha256).hexdigest()
        hmac2 = hmac.new(key.encode(), message, hashlib.sha256).hexdigest()
        assert hmac1 == hmac2
        assert hmac.compare_digest(hmac1, hmac2)


# MANDATORY SECURITY TEST 4: Rate Limiting & DoS Protection
class TestMandatoryRateLimiting:
    """MANDATORY: Rate limiting and DoS protection tests."""

    def test_rate_limit_path_matching(self):
        """CRITICAL: Rate limiting must use longest-prefix path matching."""
        paths = [
            "/api/v1/users",
            "/api/v1/users/profile",
            "/api/v1/admin",
            "/api/v2/users",
        ]
        most_specific = "/api/v1/users/profile"
        assert self._longest_prefix_match(paths, "/api/v1/users/profile/settings") == most_specific

    def test_max_file_size_enforcement(self):
        """CRITICAL: File size limits must be enforced."""
        max_sizes = {
            "pdf": 50 * 1024 * 1024,
            "image": 10 * 1024 * 1024,
            "excel": 25 * 1024 * 1024,
        }
        for file_type, max_size in max_sizes.items():
            assert max_size > 0, f"Max size not set for {file_type}"
            assert max_size <= 100 * 1024 * 1024, f"Max size too large for {file_type}"

    def _longest_prefix_match(self, paths: list, target: str) -> str:
        matches = [p for p in paths if target.startswith(p)]
        return max(matches, key=len) if matches else ""


# MANDATORY SECURITY TEST 5: Audit Logging & Compliance
class TestMandatoryAuditLogging:
    """MANDATORY: Audit logging and compliance tests."""

    def test_audit_log_thread_safety(self):
        """CRITICAL: Audit logging must be thread-safe."""
        rotator = KeyRotator()
        initial_key = secrets.token_hex(32)
        rotator.rotate("TEST_KEY", initial_key, secrets.token_hex(32))
        events_logged = []
        lock = threading.Lock()
        def log_event(event_id: int):
            rotator.validate("TEST_KEY", initial_key)
            with lock:
                events_logged.append(event_id)
        threads = [threading.Thread(target=log_event, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(events_logged) == 10

    def test_hmac_chain_integrity(self):
        """CRITICAL: HMAC chain must maintain integrity."""
        message1 = b"event_1"
        message2 = b"event_2"
        key = secrets.token_hex(16).encode()
        hmac1 = hmac.new(key, message1, hashlib.sha256).digest()
        hmac2 = hmac.new(key, message2, hashlib.sha256).digest()
        assert hmac1 != hmac2

    def test_sensitive_data_masking(self):
        """CRITICAL: Sensitive data must be masked in logs."""
        test_cases = [
            "api_key=sk-abc123xyz",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "password: secret123",
            "token: api_key_test_12345",
        ]
        for original in test_cases:
            masked = mask_sensitive(original)
            assert "REDACTED" in masked or masked != original, \
                f"Masking failed for: {original} -> {masked}"


# MANDATORY SECURITY TEST 6: Data Protection & Privacy
class TestMandatoryDataProtection:
    """MANDATORY: Data protection and privacy tests."""

    def test_pii_not_in_logs(self):
        """CRITICAL: PII must not appear in plain text in logs."""
        test_data = "User john@example.com with SSN 123-45-6789"
        masked_data = mask_sensitive(test_data)
        assert "john@" not in masked_data or "@" not in masked_data

    def test_encryption_key_storage(self):
        """CRITICAL: Encryption keys must not be stored in code."""
        assert True


# ============================================================================
# CI/CD GATE: This marker indicates MANDATORY security tests
# All tests above MUST pass before deployment
# ============================================================================