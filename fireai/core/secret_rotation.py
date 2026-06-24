"""fireai.core.secret_rotation — Secret Rotation & Key Management
===============================================================

Provides a mechanism for rotating security-sensitive keys without
application restart. Supports:

1. **Hot Key Rotation** — Update API keys and HMAC keys at runtime
   without restarting the server. Old keys remain valid during a
   grace period to prevent service disruption.

2. **Key Validation** — Verify that keys meet minimum security
   requirements (length, entropy, not a placeholder).

3. **Rotation Audit Trail** — Every rotation is logged to the
   security audit log with old/new key fingerprints.

SECURITY DESIGN:
  - Old keys are NEVER stored in plaintext. Only SHA-256 fingerprints
    are retained for verification during the grace period.
  - The grace period is configurable (default: 5 minutes).
  - Rotation requires the current key (similar to SSH key rotation).

USAGE:
  from fireai.core.secret_rotation import KeyRotator

  rotator = KeyRotator()
  rotator.rotate("FIREAI_API_KEY", old_key, new_key)
  if rotator.validate("FIREAI_API_KEY", provided_key):
      # Key is valid (either current or within grace period)
      pass
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fireai.core.security_logging import SecurityEventType, security_audit


@dataclass
class _KeyRecord:
    """Internal record for a rotated key."""

    fingerprint: str  # SHA-256 fingerprint of the key (NOT the key itself)
    rotated_at: float  # time.monotonic() when rotation occurred
    grace_period_s: float  # How long the old key remains valid


class KeyRotator:
    """Manages hot rotation of security keys.

    Thread-safe key rotation that allows old keys to remain valid
    during a configurable grace period. This prevents service disruption
    when rotating keys in a distributed system where not all instances
    update simultaneously.
    """

    def __init__(self, default_grace_period_s: float = 300.0) -> None:
        """Initialize the key rotator.

        Args:
            default_grace_period_s: Default grace period in seconds
                (5 minutes). During this period, both old and new keys
                are accepted.

        """
        self._default_grace_period_s = default_grace_period_s
        self._current: Dict[str, str] = {}  # key_name → current_key_value
        self._previous: Dict[str, _KeyRecord] = {}  # key_name → old_key_record
        self._lock = threading.Lock()

    @staticmethod
    def _fingerprint(key: str) -> str:
        """Compute SHA-256 fingerprint of a key (first 32 hex chars = 128 bits).

        SECURITY NOTE (V102): Previous version truncated to 16 hex chars
        (64 bits), which is vulnerable to birthday collisions (2^32 effort).
        128-bit fingerprint provides 2^64 collision resistance.
        """
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]

    def register(self, key_name: str, key_value: str) -> None:
        """Register a key for rotation management.

        This is called at startup to register the initial key value.

        Args:
            key_name: The name of the key (e.g., "FIREAI_API_KEY").
            key_value: The current key value.

        """
        with self._lock:
            self._current[key_name] = key_value

    def rotate(
        self,
        key_name: str,
        old_key: str,
        new_key: str,
        grace_period_s: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Rotate a security key.

        The old key must match the current key for rotation to succeed.
        After rotation, both old and new keys are valid during the grace
        period.

        Args:
            key_name: The name of the key to rotate.
            old_key: The current key value (for verification).
            new_key: The new key value.
            grace_period_s: Override grace period for this rotation.

        Returns:
            Tuple of (success: bool, message: str).

        """
        # Validate new key strength
        if len(new_key) < 16:
            return False, f"New key is too short ({len(new_key)} chars). Minimum 16 characters."
        if new_key == old_key:
            return False, "New key is identical to old key. Rotation rejected."

        with self._lock:
            current = self._current.get(key_name)
            if current is None:
                return False, f"Key '{key_name}' is not registered for rotation."

            # V102 FIX: Use constant-time comparison to prevent timing attacks.
            # Plain `!=` leaks timing information about the current key.
            if not hmac.compare_digest(current, old_key):
                security_audit.log_event(
                    SecurityEventType.AUTH_KEY_ROTATION,
                    key_name=key_name,
                    result="FAILED",
                    reason="old_key_mismatch",
                )
                return False, "Provided old_key does not match current key."

            # Store fingerprint of old key (NOT the key itself)
            grace = grace_period_s or self._default_grace_period_s
            self._previous[key_name] = _KeyRecord(
                fingerprint=self._fingerprint(old_key),
                rotated_at=time.monotonic(),
                grace_period_s=grace,
            )

            # Set new key
            self._current[key_name] = new_key

            # Audit the rotation
            security_audit.log_event(
                SecurityEventType.AUTH_KEY_ROTATION,
                key_name=key_name,
                result="SUCCESS",
                new_fingerprint=self._fingerprint(new_key),
                old_fingerprint=self._fingerprint(old_key),
                grace_period_s=grace,
            )

            return True, f"Key '{key_name}' rotated successfully. Grace period: {grace}s"

    def validate(self, key_name: str, provided_key: str) -> bool:
        """Validate a key against current or previous (grace period) value.

        Args:
            key_name: The name of the key to validate.
            provided_key: The key value to check.

        Returns:
            True if the key is valid (current or within grace period).

        """
        with self._lock:
            current = self._current.get(key_name)

            # V102 FIX: Use constant-time comparison to prevent timing attacks.
            # Plain `==` leaks timing information byte-by-byte.
            if current is not None and hmac.compare_digest(current, provided_key):
                return True

            # Check previous key (grace period)
            prev = self._previous.get(key_name)
            if prev is not None:
                # Check if provided key matches the old key's fingerprint
                # V102 FIX: Use constant-time comparison for fingerprint too.
                if hmac.compare_digest(self._fingerprint(provided_key), prev.fingerprint):
                    # Check if within grace period
                    elapsed = time.monotonic() - prev.rotated_at
                    if elapsed < prev.grace_period_s:
                        security_audit.log_event(
                            SecurityEventType.AUTH_SUCCESS,
                            key_name=key_name,
                            note="authenticated_with_grace_period_key",
                            remaining_grace_s=round(prev.grace_period_s - elapsed, 1),
                        )
                        return True
                    security_audit.log_event(
                        SecurityEventType.AUTH_FAILURE,
                        key_name=key_name,
                        note="grace_period_expired",
                    )

            return False

    @staticmethod
    def generate_key(length: int = 32) -> str:
        """Generate a cryptographically secure random key.

        Args:
            length: Number of bytes of randomness (default 32 = 256 bits).

        Returns:
            URL-safe base64-encoded key string.

        """
        return secrets.token_urlsafe(length)

    @staticmethod
    def validate_key_strength(key: str, min_length: int = 16) -> Tuple[bool, List[str]]:
        """Validate that a key meets minimum security requirements.

        Args:
            key: The key to validate.
            min_length: Minimum acceptable length.

        Returns:
            Tuple of (is_valid: bool, issues: list of problem descriptions).

        """
        issues = []

        if len(key) < min_length:
            issues.append(f"Key is {len(key)} chars — minimum {min_length} required")

        # Check for common placeholder patterns
        lower_key = key.lower()
        _bad_patterns = [
            "password",
            "changeme",
            "placeholder",
            "secret",
            "test",
            "dev",
            "example",
            "default",
            "admin",
        ]
        for pattern in _bad_patterns:
            if pattern in lower_key:
                issues.append(f"Key contains weak pattern '{pattern}'")

        # Check entropy (rough heuristic)
        unique_chars = len(set(key))
        if unique_chars < 6:
            issues.append(f"Low entropy — only {unique_chars} unique characters")

        return len(issues) == 0, issues


# Module-level singleton
key_rotator = KeyRotator()
