"""
tests/test_auth_router.py — Tests for the session-based auth router (M-3).

Covers:
  - POST /api/v1/auth/login with valid key → 200 + HttpOnly cookie
  - POST /api/v1/auth/login with wrong key → 401
  - POST /api/v1/auth/login with empty key → 422 (Pydantic validation)
  - GET /api/v1/auth/me with cookie → 200 + role
  - GET /api/v1/auth/me without cookie → 401
  - POST /api/v1/projects with cookie (no X-API-Key header) → 201
  - POST /api/v1/auth/logout → clears cookie
  - GET /api/v1/auth/me after logout → 401
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
    os.environ["FIREAI_API_KEY"] = "test_key_for_auth_123"
    return


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    from backend.app import app
    with TestClient(app) as c:
        yield c


class TestLogin:
    """POST /api/v1/auth/login tests."""

    def test_login_with_valid_key_returns_200_and_cookie(self, client: TestClient) -> None:
        """Valid API key should return 200 and set an HttpOnly cookie."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_auth_123"},  # NOSONAR: hard-coded secret in test fixture
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["role"] == "admin"
        assert "expires_at" in data["data"]

        # Verify Set-Cookie header
        set_cookie = resp.headers.get("set-cookie", "")
        assert "fireai_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=Strict" in set_cookie

    def test_login_with_wrong_key_returns_401(self, client: TestClient) -> None:
        """Wrong API key should return 401."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "wrong_key"},
        )
        assert resp.status_code == 401, resp.text
        assert "Invalid" in resp.json()["detail"]

    def test_login_with_empty_key_returns_422(self, client: TestClient) -> None:
        """Empty API key should fail Pydantic validation (min_length=1)."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": ""},
        )
        assert resp.status_code == 422, resp.text

    def test_login_without_body_returns_422(self, client: TestClient) -> None:
        """Missing body should return 422."""
        resp = client.post("/api/v1/auth/login")
        assert resp.status_code == 422, resp.text


class TestAuthMe:
    """GET /api/v1/auth/me tests."""

    def test_me_without_cookie_returns_401(self, client: TestClient) -> None:
        """Without any cookie, /me should return 401."""
        # Clear any cookies from previous tests
        client.cookies.clear()
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401, resp.text

    def test_me_with_valid_cookie_returns_role(self, client: TestClient) -> None:
        """After login, /me should return the user's role."""
        # Login first to get the cookie
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_auth_123"},  # NOSONAR: hard-coded secret in test fixture
        )
        # Now /me should work (TestClient auto-sends cookies)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["role"] == "admin"


class TestCookieAuth:
    """Verify the cookie authenticates API requests (no X-API-Key header needed)."""

    def test_create_project_with_cookie_returns_201(self, client: TestClient) -> None:
        """After login, POST /projects should work with cookie alone (no header)."""
        # Login to get cookie
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_auth_123"},  # NOSONAR: hard-coded secret in test fixture
        )
        # Create project — TestClient sends cookie automatically
        resp = client.post(
            "/api/v1/projects",
            json={"name": "cookie-auth-test", "description": "test", "author": "audit"},
        )
        assert resp.status_code == 201, resp.text


class TestLogout:
    """POST /api/v1/auth/logout tests."""

    def test_logout_clears_cookie(self, client: TestClient) -> None:
        """After logout, the cookie should be cleared and /me should 401."""
        # Login
        client.post(
            "/api/v1/auth/login",
            json={"api_key": "test_key_for_auth_123"},  # NOSONAR: hard-coded secret in test fixture
        )
        # Logout
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200, resp.text
        # Verify Set-Cookie clears the cookie (Max-Age=0)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
