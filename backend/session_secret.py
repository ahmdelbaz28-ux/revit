"""
backend/session_secret.py — Professional session secret management.

Provides enterprise-grade session secret handling for a safety-critical
fire alarm engineering platform:

Features:
  1. Multiple secrets: Support primary + previous secrets for zero-downtime rotation.
     When rotating, set FIREAI_SESSION_SECRET_NEW, restart, verify, then move
     NEW to primary and remove old. Old sessions continue to work during transition.
  2. Validation: Enforces minimum 256-bit entropy (43+ URL-safe base64 chars).
     Rejects weak secrets at startup with a clear error message.
  3. Docker secrets: Supports file-based secrets via FIREAI_SESSION_SECRET_FILE
     (more secure than env vars — not visible in /proc/PID/environ).
  4. Kubernetes secrets: Same file-based mechanism works with K8s secret mounts.
  5. CLI helper: `python3 -m backend.session_secret generate` produces a strong secret.
  6. No logging: The secret is NEVER logged, even in debug mode.
  7. Constant-time comparison: All secret comparisons use hmac.compare_digest.

Security Design:
  - The secret signs all session cookies via HMAC-SHA256.
  - If compromised, an attacker can forge session tokens.
  - Therefore: rotate regularly (quarterly), use file-based secrets in prod,
    and NEVER commit the secret to version control.

Usage:
  # Generate a secret:
  python3 -m backend.session_secret generate

  # Development (auto-generated, lost on restart):
  # (no env var needed — module generates a random one with a warning)

  # Production (env var):
  export FIREAI_SESSION_SECRET=$(python3 -m backend.session_secret generate)

  # Production (Docker/K8s file-based, MORE secure):
  # Mount secret file, then:
  export FIREAI_SESSION_SECRET_FILE=/run/secrets/fireai_session_secret

  # Rotation (zero-downtime):
  # 1. Set FIREAI_SESSION_SECRET_NEW to the new secret
  # 2. Restart — old sessions still work (verified with old secret)
  # 3. New sessions are signed with the new secret
  # 4. After all old sessions expire (8 hours), move NEW to primary
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import sys
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Minimum secret length: 43 URL-safe base64 chars = 256 bits of entropy.
# This matches OWASP recommendation for session signing keys.
_MIN_SECRET_LENGTH = 43

# Maximum secret length: 256 chars (generous, prevents abuse).
_MAX_SECRET_LENGTH = 256

# Secrets are URL-safe base64. Valid chars: A-Z, a-z, 0-9, -, _
_SECRET_CHARSET = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


class SecretInfo(NamedTuple):
    """Information about a loaded secret (for logging — NEVER includes the value)."""
    source: str  # "env", "file", "generated"
    length: int
    is_primary: bool


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


def validate_secret(secret: str, source: str = "unknown") -> None:
    """
    Validate that a session secret meets security requirements.

    Args:
        secret: The secret string to validate.
        source: Where the secret came from (for error messages).

    Raises:
        ValueError: If the secret is too short, too long, or contains
                    invalid characters.
    """
    if not secret:
        raise ValueError(
            f"Session secret from '{source}' is empty. "
            f"Generate one with: python3 -m backend.session_secret generate"
        )

    if len(secret) < _MIN_SECRET_LENGTH:
        raise ValueError(
            f"Session secret from '{source}' is too short: {len(secret)} chars. "
            f"Minimum is {_MIN_SECRET_LENGTH} chars (256 bits). "
            f"Generate a strong one with: python3 -m backend.session_secret generate"
        )

    if len(secret) > _MAX_SECRET_LENGTH:
        raise ValueError(
            f"Session secret from '{source}' is too long: {len(secret)} chars. "
            f"Maximum is {_MAX_SECRET_LENGTH} chars."
        )

    # Check for invalid characters (could indicate corruption or injection)
    invalid_chars = set(secret) - _SECRET_CHARSET
    # Allow = padding (base64) and + / (standard base64) for compatibility
    invalid_chars -= {"=", "+", "/"}
    if invalid_chars:
        raise ValueError(
            f"Session secret from '{source}' contains invalid characters: "
            f"{invalid_chars}. Use only URL-safe base64 chars (A-Z, a-z, 0-9, -, _)."
        )

    # Check for obvious weak patterns (BEFORE entropy check — placeholders
    # often have low entropy, but we want the more specific error message)
    if secret == "changeme" or "changeme" in secret or secret == "secret" or secret.startswith("your_"):
        raise ValueError(
            f"Session secret from '{source}' appears to be a placeholder. "
            f"Generate a real one with: python3 -m backend.session_secret generate"
        )

    # Check for low entropy (all same character, or very few unique chars)
    if len(set(secret)) < 10:
        raise ValueError(
            f"Session secret from '{source}' has very low entropy "
            f"({len(set(secret))} unique chars). "
            f"Generate a strong one with: python3 -m backend.session_secret generate"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECRET LOADING
# ═══════════════════════════════════════════════════════════════════════════════


def _read_secret_from_file(filepath: str) -> str:
    """Read a secret from a file (Docker/K8s secret mount)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            # Strip whitespace/newlines — secret files often have trailing newline
            return f.read().strip()
    except FileNotFoundError:
        raise ValueError(
            f"Session secret file not found: {filepath}. "
            f"Ensure the Docker/K8s secret is mounted correctly."
        ) from None
    except PermissionError:
        raise ValueError(
            f"Permission denied reading session secret file: {filepath}. "
            f"Ensure the application user has read access."
        ) from None
    except OSError as e:
        raise ValueError(
            f"Error reading session secret file {filepath}: {e}"
        ) from None


def _load_single_secret(env_var: str, file_env_var: str, source_label: str) -> str | None:
    """
    Load a single secret from env var or file.

    Priority:
      1. File-based (FILE env var) — more secure
      2. Env var — convenient but visible in /proc

    Returns None if neither is set.
    """
    # Check file-based secret first (more secure)
    file_path = os.getenv(file_env_var, "")
    if file_path:
        secret = _read_secret_from_file(file_path)
        validate_secret(secret, f"{source_label} (file: {file_path})")
        return secret

    # Fall back to env var
    secret = os.getenv(env_var, "")
    if secret:
        validate_secret(secret, f"{source_label} (env: {env_var})")
        return secret

    return None


class SessionSecretManager:
    """
    Manages session secrets with support for rotation.

    Holds a primary secret (used for signing new sessions) and optionally
    a previous secret (used only for verification during rotation).

    All secret comparisons use constant-time comparison (hmac.compare_digest).
    """

    def __init__(self) -> None:
        self._primary: str = ""
        self._previous: str = ""
        self._primary_info: SecretInfo | None = None
        self._previous_info: SecretInfo | None = None

    def load(self) -> None:
        """
        Load secrets from environment variables.

        In production, FIREAI_SESSION_SECRET (or _FILE) is REQUIRED.
        In development, if not set, generates a random one (with warning).

        For rotation: set FIREAI_SESSION_SECRET_NEW to the new secret.
        The old FIREAI_SESSION_SECRET becomes the "previous" secret.
        """
        is_production = os.getenv("FIREAI_ENV", "development").lower() in ("production", "prod")

        # Load primary secret
        primary = _load_single_secret(
            "FIREAI_SESSION_SECRET",
            "FIREAI_SESSION_SECRET_FILE",
            "primary secret",
        )

        if primary is None:
            if is_production:
                raise RuntimeError(
                    "FIREAI_SESSION_SECRET is REQUIRED in production.\n"
                    "Generate one with:\n"
                    "  python3 -m backend.session_secret generate\n\n"
                    "Then set it as an environment variable:\n"
                    "  export FIREAI_SESSION_SECRET='<generated_secret>'\n\n"
                    "Or for Docker/K8s (more secure), use file-based:\n"
                    "  export FIREAI_SESSION_SECRET_FILE=/run/secrets/fireai_session_secret\n\n"
                    "The secret signs all session cookies. Without it, users cannot log in."
                )
            # Development: generate a random secret (sessions lost on restart)
            primary = secrets.token_urlsafe(64)
            self._primary_info = SecretInfo(
                source="generated",
                length=len(primary),
                is_primary=True,
            )
            logger.warning(
                "FIREAI_SESSION_SECRET not set — using random dev secret. "
                "Sessions will be lost on restart. "
                "Set FIREAI_SESSION_SECRET for persistence. "
                "Generate one with: python3 -m backend.session_secret generate"
            )
        else:
            source = "file" if os.getenv("FIREAI_SESSION_SECRET_FILE") else "env"
            self._primary_info = SecretInfo(
                source=source,
                length=len(primary),
                is_primary=True,
            )
            logger.info(
                "Primary session secret loaded (source=%s, length=%d)",
                self._primary_info.source,
                self._primary_info.length,
            )

        self._primary = primary

        # Load previous secret (for rotation) — optional
        previous = _load_single_secret(
            "FIREAI_SESSION_SECRET_NEW",  # NEW becomes previous after rotation
            "FIREAI_SESSION_SECRET_NEW_FILE",
            "rotation secret",
        )

        if previous is not None:
            # During rotation: FIREAI_SESSION_SECRET is old, _NEW is the new one.
            # New sessions are signed with _NEW, old sessions verified with old.
            # After all old sessions expire, move _NEW to primary and remove old.
            self._previous = self._primary  # old primary becomes previous
            self._primary = previous  # NEW becomes primary
            self._previous_info = self._primary_info
            self._primary_info = SecretInfo(
                source="file" if os.getenv("FIREAI_SESSION_SECRET_NEW_FILE") else "env",
                length=len(previous),
                is_primary=True,
            )
            logger.info(
                "Session rotation in progress. Primary secret updated, "
                "previous secret retained for verifying existing sessions. "
                "After all sessions expire (8h), remove FIREAI_SESSION_SECRET_NEW "
                "and set FIREAI_SESSION_SECRET to the new value."
            )

    @property
    def primary(self) -> str:
        """The primary secret (used for signing new sessions)."""
        if not self._primary:
            self.load()
        return self._primary

    def sign(self, data: str) -> str:
        """Sign data with the primary secret using HMAC-SHA256."""
        import hashlib
        return hmac.new(
            self.primary.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(self, data: str, signature: str) -> bool:
        """
        Verify a signature against the primary AND previous secrets.

        During rotation, old sessions were signed with the previous secret.
        This method accepts signatures from either secret.

        Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
        """
        import hashlib

        # Check against primary secret
        expected_primary = hmac.new(
            self.primary.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(signature, expected_primary):
            return True

        # Check against previous secret (during rotation)
        if self._previous:
            expected_previous = hmac.new(
                self._previous.encode("utf-8"),
                data.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(signature, expected_previous):
                return True

        return False

    def get_info(self) -> dict:
        """
        Get information about loaded secrets (for diagnostics).

        NEVER returns the actual secret values — only metadata.
        """
        return {
            "primary": {
                "source": self._primary_info.source if self._primary_info else "not_loaded",
                "length": self._primary_info.length if self._primary_info else 0,
            },
            "previous": {
                "source": self._previous_info.source if self._previous_info else "none",
                "length": self._previous_info.length if self._previous_info else 0,
            },
            "rotation_in_progress": bool(self._previous),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

# Global singleton — loaded once at startup, reused for all requests.
_secret_manager: SessionSecretManager | None = None


def get_secret_manager() -> SessionSecretManager:
    """Get the global SessionSecretManager singleton."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SessionSecretManager()
        _secret_manager.load()
    return _secret_manager


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI entry point for secret generation."""
    if len(sys.argv) > 1 and sys.argv[1] == "generate":
        secret = secrets.token_urlsafe(64)
        # CodeQL: py/clear-text-logging-sensitive-data — FALSE POSITIVE.
        # This is a CLI tool whose purpose is to OUTPUT the secret to stdout
        # so the user can copy it. This is NOT logging (no logger, no file).
        # The user MUST see the secret to set FIREAI_SESSION_SECRET.
        # Suppressed with explicit justification per CodeQL docs.
        print("# FireAI Session Secret — generated with cryptographic randomness")  # noqa: S105, T201 - CLI output, not logging
        print("# Store this securely. DO NOT commit to version control.")  # noqa: T201
        print("#")  # noqa: T201
        print("# Usage (env var):")  # noqa: T201
        print("#   export FIREAI_SESSION_SECRET='<copy-secret-below>'")  # noqa: T201
        print("#")  # noqa: T201
        print("# Usage (Docker/K8s file-based, more secure):")  # noqa: T201
        print("#   echo -n '<copy-secret-below>' > /run/secrets/fireai_session_secret")  # noqa: T201
        print("#   export FIREAI_SESSION_SECRET_FILE=/run/secrets/fireai_session_secret")  # noqa: T201
        print("#")  # noqa: T201
        print("# The secret below has 512 bits of entropy (86 URL-safe base64 chars):")  # noqa: T201
        print(secret)  # noqa: S105, T201 - intentional CLI output for user to copy
    elif len(sys.argv) > 1 and sys.argv[1] == "info":
        mgr = get_secret_manager()
        info = mgr.get_info()
        print("Session Secret Manager Status:")
        print(f"  Primary:  source={info['primary']['source']}, length={info['primary']['length']}")
        print(f"  Previous: source={info['previous']['source']}, length={info['previous']['length']}")
        print(f"  Rotation in progress: {info['rotation_in_progress']}")
    else:
        print("Usage:")
        print("  python3 -m backend.session_secret generate  # Generate a strong secret")
        print("  python3 -m backend.session_secret info      # Show loaded secret info")
        sys.exit(1)


if __name__ == "__main__":
    main()
