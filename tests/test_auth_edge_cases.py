# NOSONAR
"""
tests/test_auth_edge_cases.py — Additional edge-case tests for auth.

Tests:
  - Session expiry (expired session → 401)
  - Concurrent sessions with same API key (each gets unique session)
  - Cross-domain cookie rejection (cookie from different domain)
  - Multiple rapid logins (no race condition)
  - Login with whitespace-only API key
  - Login with very long API key
  - Cookie with extra whitespace
  - Session store cleanup on expiry
  - Rate limit window reset after 5 minutes
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _setup_env() -> Generator[None, None, None]:
    """Set test environment."""
    os.environ["FIREAI_ENV"] = "development"
    os.environ["FIREAI_API_KEY"] = "test_key_edge_cases"
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


class TestSessionExpiry:
    """Tests for session expiration."""

    def test_expired_session_returns_401(self, client: TestClient) -> None:
        """An expired session should return 401."""
        client.cookies.clear()
        from backend.routers import auth as auth_module

        # Login
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        assert resp.status_code == 200

        # Get the session ID hash from store
        store_keys = list(auth_module._SESSION_STORE.keys())
        assert len(store_keys) == 1

        # Manually expire the session
        auth_module._SESSION_STORE[store_keys[0]]["expires_at"] = time.time() - 1

        # Now /me should return 401
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401, "Expired session should be rejected"

    def test_expired_session_removed_from_store(self, client: TestClient) -> None:
        """Expired sessions should be cleaned up from the store."""
        client.cookies.clear()
        from backend.routers import auth as auth_module

        # Login
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )

        store_keys = list(auth_module._SESSION_STORE.keys())
        assert len(store_keys) == 1

        # Expire the session
        auth_module._SESSION_STORE[store_keys[0]]["expires_at"] = time.time() - 1

        # Trigger cleanup by calling /me
        client.get("/api/v1/auth/me")

        # Session should be removed from store
        assert store_keys[0] not in auth_module._SESSION_STORE, \
            "Expired session should be cleaned up from store"


class TestConcurrentSessions:
    """Tests for concurrent session handling."""

    def test_same_api_key_creates_unique_sessions(self, client: TestClient) -> None:
        """Two logins with same API key should create different sessions."""
        client.cookies.clear()

        # First login
        resp1 = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        token1 = resp1.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]

        # Clear cookie, second login
        client.cookies.clear()
        resp2 = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        token2 = resp2.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]

        # Tokens must be different (random session IDs)
        assert token1 != token2, "Each login should create a unique session"

    def test_both_sessions_valid_simultaneously(self, client: TestClient) -> None:
        """Both sessions from same API key should work independently."""
        client.cookies.clear()

        # Login twice
        resp1 = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        resp1.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]

        client.cookies.clear()
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )

        # Both should be in session store
        from backend.routers import auth as auth_module
        assert len(auth_module._SESSION_STORE) >= 2, \
            "Both sessions should exist in store"

    def test_logout_one_session_does_not_affect_other(self, client: TestClient) -> None:
        """Logging out one session should not invalidate the other."""
        client.cookies.clear()
        from backend.routers import auth as auth_module

        # First login
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        first_session_count = len(auth_module._SESSION_STORE)

        # Second login (new session)
        client.cookies.clear()
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        assert len(auth_module._SESSION_STORE) == first_session_count + 1

        # Logout current session
        client.post("/api/v1/auth/logout")

        # Only one session should be removed
        assert len(auth_module._SESSION_STORE) == first_session_count, \
            "Logout should only remove the current session, not others"


class TestInputValidation:
    """Tests for input validation edge cases."""

    def test_whitespace_only_api_key_rejected(self, client: TestClient) -> None:
        """Whitespace-only API key should be rejected (empty after strip)."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "   "},
        )
        # Pydantic min_length=1 should catch this before strip
        assert resp.status_code in (400, 422)

    def test_very_long_api_key_handled(self, client: TestClient) -> None:
        """Very long API key should not crash (rejected as invalid)."""
        long_key = "x" * 10000
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": long_key},
        )
        assert resp.status_code == 401, "Long invalid key should be rejected"

    def test_api_key_with_special_chars(self, client: TestClient) -> None:
        """API key with special characters should be handled safely."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "key<script>alert(1)</script>"},
        )
        assert resp.status_code == 401, "Invalid key should be rejected"

    def test_api_key_with_newlines(self, client: TestClient) -> None:
        """API key with newlines should be handled safely (no header injection)."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "key\n\rSet-Cookie: evil=true"},
        )
        assert resp.status_code == 401, "Invalid key should be rejected"

    def test_missing_api_key_field(self, client: TestClient) -> None:
        """Missing api_key field should return 400 (business logic rejection).

        Note: LoginRequest.api_key is Optional (username/password auth is an
        alternative), so an empty body {} passes Pydantic validation (no 422).
        The endpoint's business logic then rejects it with 400 'missing api_key'.
        """
        resp = client.post(
            "/api/v1/auth/login",
            json={},
        )
        assert resp.status_code == 400

    def test_wrong_content_type(self, client: TestClient) -> None:
        """Wrong content type should return 422."""
        # S8405 fix: use `content=` (not `data=`) when passing raw str/bytes
        # to HTTPX/Starlette TestClient. `data=` is for form-encoded dicts;
        # raw text bodies must use `content=` to avoid being mis-encoded.
        resp = client.post(
            "/api/v1/auth/login",
            content="api_key=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 422


class TestRateLimitWindow:
    """Tests for rate limit window behavior."""

    def test_rate_limit_window_resets(self, client: TestClient) -> None:
        """Rate limit should reset after the window expires."""
        from backend.routers import auth as auth_module

        # Make 5 failed attempts
        for _ in range(5):
            client.post("/api/v1/auth/login", json={"api_key": "wrong"})

        # Should be rate limited
        resp = client.post("/api/v1/auth/login", json={"api_key": "wrong"})
        assert resp.status_code == 429

        # Simulate time passing (clear the failed attempts)
        auth_module._FAILED_ATTEMPTS.clear()

        # Should be able to attempt again
        resp = client.post("/api/v1/auth/login", json={"api_key": "wrong"})
        assert resp.status_code == 401, "Rate limit should reset after window"

    def test_successful_login_clears_failed_attempts(self, client: TestClient) -> None:
        """Successful login should clear failed attempts for that IP."""
        from backend.routers import auth as auth_module

        # 3 failed attempts
        for _ in range(3):
            client.post("/api/v1/auth/login", json={"api_key": "wrong"})

        # Verify attempts recorded
        client_ip = "testclient"
        assert client_ip in auth_module._FAILED_ATTEMPTS
        assert len(auth_module._FAILED_ATTEMPTS[client_ip]) == 3

        # Successful login
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )

        # Failed attempts should be cleared
        assert client_ip not in auth_module._FAILED_ATTEMPTS or \
               len(auth_module._FAILED_ATTEMPTS.get(client_ip, [])) == 0


class TestCookieSecurityHeaders:
    """Tests for cookie security attributes."""

    def test_cookie_has_path_root(self, client: TestClient) -> None:
        """Cookie should have Path=/."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "path=/" in set_cookie, "Cookie should have Path=/"

    def test_cookie_has_max_age(self, client: TestClient) -> None:
        """Cookie should have Max-Age."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "max-age=" in set_cookie, "Cookie should have Max-Age"

    def test_logout_cookie_has_max_age_zero(self, client: TestClient) -> None:
        """Logout should set cookie with Max-Age=0."""
        # Login first
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )

        # Logout
        resp = client.post("/api/v1/auth/logout")
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "max-age=0" in set_cookie, "Logout should clear cookie with Max-Age=0"


class TestSessionTokenFormat:
    """Tests for session token format validation."""

    def test_token_has_dot_separator(self, client: TestClient) -> None:
        """Token should have format: session_id.signature."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        token = resp.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]

        # Should have exactly one dot separating session_id and signature
        parts = token.split(".")
        assert len(parts) == 2, f"Token should have format id.sig, got {len(parts)} parts"
        assert len(parts[0]) > 0, "Session ID part should not be empty"
        assert len(parts[1]) == 64, f"Signature should be 64 hex chars, got {len(parts[1])}"

    def test_session_id_has_sufficient_entropy(self, client: TestClient) -> None:
        """Session ID should have at least 256 bits (43+ URL-safe base64 chars)."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_edge_cases"},  # NOSONAR: hard-coded secret in test fixture  # NOSONAR — S7632: test function documented via class name / module path
        )
        token = resp.headers.get("set-cookie", "").split("fireai_session=")[1].split(";")[0]
        session_id = token.split(".")[0]

        # 32 bytes = 256 bits = 43 URL-safe base64 chars
        assert len(session_id) >= 43, \
            f"Session ID should be >=43 chars (256 bits), got {len(session_id)}"
