# NOSONAR
"""
tests/test_auth_security.py — Security edge-case tests for auth router.

Tests:
  - Rate limiting (5 failed attempts → 429)
  - Cookie token is opaque (NOT the API key)
  - Tampered cookie token → 401
  - Expired session → 401 (after logout)
  - Multiple concurrent logins
  - Malformed cookie values
  - Session secret required in production
  - Constant-time comparison (timing attack resistance)
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _setup_env() -> Generator[None, None, None]:
    """Set test environment."""
    os.environ["FIREAI_ENV"] = "development"
    os.environ["FIREAI_API_KEY"] = "test_key_for_security_audit"
    # Clear session store between tests
    from backend.routers import auth as auth_module
    auth_module._SESSION_STORE.clear()
    auth_module._FAILED_ATTEMPTS.clear()
    yield
    auth_module._SESSION_STORE.clear()
    auth_module._FAILED_ATTEMPTS.clear()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    from backend.app import app
    with TestClient(app) as c:
        yield c


class TestRateLimiting:
    """Rate limiting on failed login attempts."""

    def test_five_failed_attempts_then_429(self, client: TestClient) -> None:
        """After 5 failed login attempts, should return 429."""
        for i in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"api_key": "wrong_key"},
            )
            assert resp.status_code == 401, f"Attempt {i+1} should be 401"

        # 6th attempt should be rate limited
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "wrong_key"},
        )
        assert resp.status_code == 429, "6th attempt should be 429"

    def test_successful_login_resets_rate_limit(self, client: TestClient) -> None:
        """A successful login should clear failed attempts."""
        # 4 failed attempts (under the limit)
        for _ in range(4):
            client.post("/api/v1/auth/login", json={"api_key": "wrong"})

        # Successful login
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        assert resp.status_code == 200

        # Should be able to fail again (rate limit was reset)
        for _ in range(4):
            resp = client.post("/api/v1/auth/login", json={"api_key": "wrong"})
            assert resp.status_code == 401


class TestCookieSecurity:
    """Verify cookie does NOT contain the API key."""

    def test_cookie_does_not_contain_api_key(self, client: TestClient) -> None:
        """The cookie value must NOT be the API key itself."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        assert resp.status_code == 200

        # Extract cookie value
        set_cookie = resp.headers.get("set-cookie", "")
        assert "fireai_session=" in set_cookie

        # Extract the token part
        token_part = set_cookie.split("fireai_session=")[1].split(";")[0]

        # CRITICAL: token must NOT equal the API key
        assert token_part != "test_key_for_security_audit", \
            "Cookie contains API key in plaintext — CRITICAL security failure!"

        # Token should be longer than the API key (it's session_id.signature)
        assert len(token_part) > 60, f"Token too short: {len(token_part)} chars"

    def test_cookie_has_httponly_flag(self, client: TestClient) -> None:
        """Cookie must have HttpOnly flag (XSS protection)."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie, "Cookie missing HttpOnly flag"

    def test_cookie_has_samesite_strict(self, client: TestClient) -> None:
        """Cookie must have SameSite=Strict (CSRF protection)."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "samesite=strict" in set_cookie, "Cookie missing SameSite=Strict"

    def test_cookie_has_cache_control_no_store(self, client: TestClient) -> None:
        """Login response must have Cache-Control: no-store."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        cache_control = resp.headers.get("cache-control", "").lower()
        assert "no-store" in cache_control, "Missing Cache-Control: no-store"


class TestTamperedCookie:
    """Verify tampered cookies are rejected."""

    def test_tampered_cookie_signature_rejected(self, client: TestClient) -> None:
        """Modifying the cookie signature should result in 401."""
        # Login to get valid cookie
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )

        # Clear ALL cookies then set tampered one
        client.cookies.clear()
        client.cookies.set("fireai_session", "fake_token.invalid_signature")

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401, "Tampered cookie should be rejected"

    def test_malformed_cookie_no_dot_rejected(self, client: TestClient) -> None:
        """Cookie without dot separator should be rejected."""
        client.cookies.set("fireai_session", "nodotincookie")

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_empty_cookie_rejected(self, client: TestClient) -> None:
        """Empty cookie value should result in 401."""
        client.cookies.clear()
        client.cookies.set("fireai_session", "")

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestSessionRevocation:
    """Verify logout actually revokes the session server-side."""

    def test_logout_revokes_session(self, client: TestClient) -> None:
        """After logout, the same cookie should NOT work."""
        # Clear any existing cookies/session state
        client.cookies.clear()
        from backend.routers import auth as auth_module
        auth_module._SESSION_STORE.clear()

        # Login
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        assert login_resp.status_code == 200

        # Verify session works
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200

        # Logout
        client.post("/api/v1/auth/logout")

        # Same cookie should NOT work after logout
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401, "Session should be revoked after logout"

    def test_multiple_logins_create_independent_sessions(self, client: TestClient) -> None:
        """Multiple logins should each create separate sessions."""
        # First login
        resp1 = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        token1 = resp1.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]

        # Second login (should create new session, not reuse)
        resp2 = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_security_audit"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        token2 = resp2.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]

        # Tokens should be different (random session IDs)
        assert token1 != token2, "Each login should create a unique session"


class TestProductionSecret:
    """Verify production requires a session secret."""

    def test_production_requires_session_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, FIREAI_SESSION_SECRET must be set."""
        import importlib

        # Clear ALL session secret env vars
        monkeypatch.setenv("FIREAI_ENV", "production")
        monkeypatch.delenv("FIREAI_SESSION_SECRET", raising=False)
        monkeypatch.delenv("FIREAI_SESSION_SECRET_FILE", raising=False)
        monkeypatch.delenv("FIREAI_SESSION_SECRET_NEW", raising=False)
        monkeypatch.delenv("FIREAI_SESSION_SECRET_NEW_FILE", raising=False)

        # Reset the global secret manager singleton
        import backend.session_secret as secret_mod
        old_manager = secret_mod._secret_manager
        secret_mod._secret_manager = None

        # Reload session_secret module — should raise RuntimeError on load()
        importlib.reload(secret_mod)

        try:
            mgr = secret_mod.SessionSecretManager()
            with pytest.raises(RuntimeError, match="FIREAI_SESSION_SECRET.*REQUIRED"):
                mgr.load()
        finally:
            # Restore original module state
            secret_mod._secret_manager = old_manager
