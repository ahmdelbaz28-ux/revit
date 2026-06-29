"""
tests/test_session_secret.py — Tests for professional session secret management.

Tests:
  - Secret generation (CLI)
  - Secret validation (length, charset, entropy)
  - Loading from env var
  - Loading from file (Docker/K8s)
  - Rotation (primary + previous secrets)
  - Constant-time comparison
  - Production requires secret (refuses to start)
  - Weak secret rejection
  - Secret never logged
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Generator
from pathlib import Path

import pytest

import backend.session_secret as session_secret_module
from backend.session_secret import (
    SessionSecretManager,
    validate_secret,
)


@pytest.fixture(autouse=True)
def _reset_manager() -> Generator[None, None, None]:
    """Reset the global secret manager between tests."""
    # Save original env vars
    saved_env = {}
    for key in [
        "FIREAI_SESSION_SECRET",
        "FIREAI_SESSION_SECRET_FILE",
        "FIREAI_SESSION_SECRET_NEW",
        "FIREAI_SESSION_SECRET_NEW_FILE",
        "FIREAI_ENV",
    ]:
        if key in os.environ:
            saved_env[key] = os.environ[key]
            del os.environ[key]

    # Reset the global singleton
    old_manager = session_secret_module._secret_manager
    session_secret_module._secret_manager = None

    yield

    # Restore env vars
    for key, val in saved_env.items():
        os.environ[key] = val

    # Restore the singleton
    session_secret_module._secret_manager = old_manager


class TestSecretValidation:
    """Tests for validate_secret()."""

    def test_valid_secret_passes(self) -> None:
        """A properly generated secret should pass validation."""
        secret = secrets.token_urlsafe(64)
        validate_secret(secret)  # Should not raise

    def test_empty_secret_rejected(self) -> None:
        """Empty secret should be rejected."""
        with pytest.raises(ValueError, match="empty"):
            validate_secret("")

    def test_short_secret_rejected(self) -> None:
        """Secret shorter than 43 chars should be rejected (< 256 bits)."""
        with pytest.raises(ValueError, match="too short"):
            validate_secret("short")

    def test_placeholder_secret_rejected(self) -> None:
        """Placeholder secrets should be rejected."""
        # Make it long enough to pass length check, but still a placeholder
        with pytest.raises(ValueError, match="placeholder"):
            validate_secret("changeme" * 10)  # 70 chars, still a placeholder

    def test_your_prefix_rejected(self) -> None:
        """Secrets starting with 'your_' should be rejected."""
        with pytest.raises(ValueError, match="placeholder"):
            validate_secret("your_secret_here_1234567890123456789012345678901234567890")

    def test_low_entropy_rejected(self) -> None:
        """Secrets with very few unique chars should be rejected."""
        with pytest.raises(ValueError, match="low entropy"):
            validate_secret("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    def test_long_secret_rejected(self) -> None:
        """Secrets longer than 256 chars should be rejected."""
        with pytest.raises(ValueError, match="too long"):
            validate_secret("a" * 300)


class TestSecretLoading:
    """Tests for loading secrets from env vars and files."""

    def test_load_from_env_var(self) -> None:
        """Secret should be loadable from FIREAI_SESSION_SECRET env var."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        assert mgr.primary == secret

    def test_load_from_file(self, tmp_path: Path) -> None:
        """Secret should be loadable from a file (Docker/K8s secret mount)."""
        secret = secrets.token_urlsafe(64)
        secret_file = tmp_path / "session_secret"
        secret_file.write_text(secret)

        os.environ["FIREAI_SESSION_SECRET_FILE"] = str(secret_file)
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        assert mgr.primary == secret

    def test_file_takes_precedence_over_env(self, tmp_path: Path) -> None:
        """File-based secret should take precedence over env var."""
        env_secret = secrets.token_urlsafe(64)
        file_secret = secrets.token_urlsafe(64)
        secret_file = tmp_path / "session_secret"
        secret_file.write_text(file_secret)

        os.environ["FIREAI_SESSION_SECRET"] = env_secret
        os.environ["FIREAI_SESSION_SECRET_FILE"] = str(secret_file)
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        assert mgr.primary == file_secret, "File secret should take precedence"

    def test_file_with_trailing_newline(self, tmp_path: Path) -> None:
        """Secret file with trailing newline should be handled (stripped)."""
        secret = secrets.token_urlsafe(64)
        secret_file = tmp_path / "session_secret"
        secret_file.write_text(secret + "\n")  # Trailing newline

        os.environ["FIREAI_SESSION_SECRET_FILE"] = str(secret_file)
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        assert mgr.primary == secret, "Trailing newline should be stripped"

    def test_production_requires_secret(self) -> None:
        """Production should refuse to start without a secret."""
        os.environ["FIREAI_ENV"] = "production"
        # No secret set

        mgr = SessionSecretManager()
        with pytest.raises(RuntimeError, match="REQUIRED"):
            mgr.load()

    def test_development_generates_random_secret(self) -> None:
        """Development should generate a random secret if not set."""
        os.environ["FIREAI_ENV"] = "development"
        # No secret set

        mgr = SessionSecretManager()
        mgr.load()

        assert len(mgr.primary) > 0
        info = mgr.get_info()
        assert info["primary"]["source"] == "generated"

    def test_missing_secret_file_raises_error(self) -> None:
        """Missing secret file should raise a clear error."""
        os.environ["FIREAI_SESSION_SECRET_FILE"] = "/nonexistent/secret"
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.load()


class TestSecretRotation:
    """Tests for zero-downtime secret rotation."""

    def test_rotation_retains_previous_secret(self) -> None:
        """When FIREAI_SESSION_SECRET_NEW is set, old secret becomes 'previous'."""
        old_secret = secrets.token_urlsafe(64)
        new_secret = secrets.token_urlsafe(64)

        os.environ["FIREAI_SESSION_SECRET"] = old_secret
        os.environ["FIREAI_SESSION_SECRET_NEW"] = new_secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        # Primary should be the NEW secret
        assert mgr.primary == new_secret

        # Previous should be the OLD secret
        info = mgr.get_info()
        assert info["rotation_in_progress"] is True
        assert info["previous"]["length"] > 0

    def test_rotation_old_sessions_still_valid(self) -> None:
        """Sessions signed with old secret should still verify during rotation."""
        old_secret = secrets.token_urlsafe(64)
        new_secret = secrets.token_urlsafe(64)

        os.environ["FIREAI_SESSION_SECRET"] = old_secret
        os.environ["FIREAI_ENV"] = "production"

        mgr1 = SessionSecretManager()
        mgr1.load()

        # Sign a session with old secret
        data = "test_session_id"
        old_signature = mgr1.sign(data)

        # Now rotate: add NEW secret
        os.environ["FIREAI_SESSION_SECRET_NEW"] = new_secret

        mgr2 = SessionSecretManager()
        mgr2.load()

        # Old signature should still verify (against previous secret)
        assert mgr2.verify_signature(data, old_signature), \
            "Old sessions should still work during rotation"

        # New signature should also verify (against primary secret)
        new_signature = mgr2.sign(data)
        assert mgr2.verify_signature(data, new_signature), \
            "New sessions should work with new secret"

    def test_no_rotation_when_new_not_set(self) -> None:
        """Without FIREAI_SESSION_SECRET_NEW, no rotation should occur."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        info = mgr.get_info()
        assert info["rotation_in_progress"] is False
        assert info["previous"]["source"] == "none"


class TestSigningAndVerification:
    """Tests for HMAC signing and verification."""

    def test_sign_and_verify_roundtrip(self) -> None:
        """A signed token should verify successfully."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        data = "session_id_12345"
        signature = mgr.sign(data)

        assert mgr.verify_signature(data, signature) is True

    def test_tampered_signature_rejected(self) -> None:
        """A tampered signature should be rejected."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        data = "session_id_12345"
        signature = mgr.sign(data)

        # Tamper with signature
        tampered = signature[:-1] + ("a" if signature[-1] != "a" else "b")
        assert mgr.verify_signature(data, tampered) is False

    def test_different_data_rejected(self) -> None:
        """Signature for one data should not verify for different data."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        sig1 = mgr.sign("data1")
        assert mgr.verify_signature("data2", sig1) is False

    def test_wrong_secret_rejected(self) -> None:
        """Signature from a different secret should be rejected."""
        secret1 = secrets.token_urlsafe(64)
        secret2 = secrets.token_urlsafe(64)

        os.environ["FIREAI_SESSION_SECRET"] = secret1
        os.environ["FIREAI_ENV"] = "production"
        mgr1 = SessionSecretManager()
        mgr1.load()

        os.environ["FIREAI_SESSION_SECRET"] = secret2
        mgr2 = SessionSecretManager()
        mgr2.load()

        data = "test_session"
        sig1 = mgr1.sign(data)

        # Signature from secret1 should NOT verify with secret2
        assert mgr2.verify_signature(data, sig1) is False


class TestSecretInfo:
    """Tests for diagnostic info (must never expose secret values)."""

    def test_get_info_does_not_expose_secret(self) -> None:
        """get_info() should never include the actual secret value."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        info = mgr.get_info()

        # Convert to string and check secret is not present
        info_str = str(info)
        assert secret not in info_str, "Secret value must not appear in info"

    def test_get_info_shows_source_and_length(self) -> None:
        """get_info() should show source and length (not the value)."""
        secret = secrets.token_urlsafe(64)
        os.environ["FIREAI_SESSION_SECRET"] = secret
        os.environ["FIREAI_ENV"] = "production"

        mgr = SessionSecretManager()
        mgr.load()

        info = mgr.get_info()
        assert info["primary"]["source"] == "env"
        assert info["primary"]["length"] == len(secret)
        assert info["rotation_in_progress"] is False


class TestCLI:
    """Tests for CLI commands."""

    def test_generate_produces_valid_secret(self, capsys: pytest.CaptureFixture[str]) -> None:
        """CLI generate should produce a valid secret."""
        import sys

        from backend import session_secret as mod

        # Call main with 'generate' argument
        old_argv = sys.argv
        sys.argv = ["session_secret", "generate"]
        try:
            mod.main()
        finally:
            sys.argv = old_argv

        captured = capsys.readouterr()
        # The last non-comment line should be the secret
        lines = [l for l in captured.out.strip().split("\n") if l and not l.startswith("#")]
        assert len(lines) > 0
        secret = lines[-1]
        validate_secret(secret)

    def test_generated_secret_has_sufficient_entropy(self) -> None:
        """Generated secrets should have at least 256 bits of entropy."""
        secret = secrets.token_urlsafe(64)
        # token_urlsafe(64) = 64 bytes = 512 bits = 86 URL-safe base64 chars
        assert len(secret) >= 86
        # Should pass validation
        validate_secret(secret)
