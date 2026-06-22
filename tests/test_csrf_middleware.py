"""
tests/test_csrf_middleware.py
==============================
Tests for the CSRF middleware (V133 — 2026-06-22).

Covers:
  - Token generation (43 chars, URL-safe)
  - Token validation (valid, invalid, expired, empty)
  - Safe method exemption (GET/HEAD/OPTIONS)
  - State-changing method enforcement (POST/PUT/PATCH/DELETE)
  - One-time use (token consumed after first use)
  - Token issuance endpoint (GET /api/csrf-token)
  - Token TTL expiry
  - Garbage collection of expired tokens
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.security_middleware import CSRFMiddleware


@pytest.fixture
def middleware():
    """Fresh CSRFMiddleware instance for each test."""
    return CSRFMiddleware(app=MagicMock())


class TestTokenGeneration:
    def test_token_is_string(self, middleware):
        token = middleware._issue_token()
        assert isinstance(token, str)

    def test_token_is_url_safe(self, middleware):
        """Token should only contain URL-safe characters."""
        token = middleware._issue_token()
        # secrets.token_urlsafe produces: A-Z, a-z, 0-9, -, _
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in token)

    def test_token_has_sufficient_entropy(self, middleware):
        """Token should be at least 32 chars (256 bits via token_urlsafe(32))."""
        token = middleware._issue_token()
        assert len(token) >= 32

    def test_each_token_is_unique(self, middleware):
        """Two consecutive calls should produce different tokens."""
        t1 = middleware._issue_token()
        t2 = middleware._issue_token()
        assert t1 != t2


class TestTokenValidation:
    def test_valid_token_accepted(self, middleware):
        token = middleware._issue_token()
        assert middleware._is_valid_token(token) is True

    def test_invalid_token_rejected(self, middleware):
        assert middleware._is_valid_token("nonexistent-token") is False

    def test_empty_token_rejected(self, middleware):
        assert middleware._is_valid_token("") is False

    def test_none_token_rejected(self, middleware):
        assert middleware._is_valid_token(None) is False

    def test_expired_token_rejected(self, middleware):
        """Token past its TTL should be rejected and cleaned up."""
        token = middleware._issue_token()
        # Manually expire it
        middleware._token_store[token] = time.time() - 1
        assert middleware._is_valid_token(token) is False
        # Expired token should be removed from store
        assert token not in middleware._token_store


class TestSafeMethodExemption:
    """GET, HEAD, OPTIONS should pass through without CSRF check."""

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    @pytest.mark.asyncio
    async def test_safe_methods_pass_through(self, middleware, method):
        """Safe methods should call the wrapped app without CSRF check."""
        middleware.app = AsyncMock()
        scope = {"type": "http", "method": method, "path": "/api/health", "headers": []}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        middleware.app.assert_called_once_with(scope, receive, send)
        # send should NOT have been called (no CSRF rejection)
        send.assert_not_called()


class TestStateChangingMethodEnforcement:
    """POST, PUT, PATCH, DELETE should require a valid CSRF token."""

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    @pytest.mark.asyncio
    async def test_state_changing_without_token_returns_403(self, middleware, method):
        """State-changing requests without a CSRF token should get 403."""
        middleware.app = AsyncMock()
        scope = {
            "type": "http",
            "method": method,
            "path": "/api/v1/projects",
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should NOT be called (request rejected)
        middleware.app.assert_not_called()
        # send should be called with 403 status
        assert send.call_count >= 2
        start_call = send.call_args_list[0]
        # send is called with a positional dict argument, not a kwarg
        start_msg = start_call.args[0] if start_call.args else start_call.kwargs.get("message", {})
        assert start_msg["status"] == 403

    @pytest.mark.asyncio
    async def test_state_changing_with_valid_token_passes(self, middleware):
        """State-changing requests with a valid CSRF token should pass through."""
        middleware.app = AsyncMock()
        token = middleware._issue_token()
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/projects",
            "headers": [(b"x-csrf-token", token.encode("latin-1"))],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        middleware.app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_state_changing_with_invalid_token_returns_403(self, middleware):
        """State-changing requests with an invalid CSRF token should get 403."""
        middleware.app = AsyncMock()
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/projects",
            "headers": [(b"x-csrf-token", b"invalid-token")],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        middleware.app.assert_not_called()
        start_call = send.call_args_list[0]
        start_msg = start_call.args[0] if start_call.args else start_call.kwargs.get("message", {})
        assert start_msg["status"] == 403


class TestOneTimeUse:
    @pytest.mark.asyncio
    async def test_token_consumed_after_use(self, middleware):
        """A valid token should be consumed (deleted) after first use."""
        middleware.app = AsyncMock()
        token = middleware._issue_token()
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/projects",
            "headers": [(b"x-csrf-token", token.encode("latin-1"))],
        }
        receive = AsyncMock()
        send = AsyncMock()

        # First use — should succeed
        await middleware(scope, receive, send)
        middleware.app.assert_called_once()

        # Token should now be consumed
        assert token not in middleware._token_store
        assert middleware._is_valid_token(token) is False


class TestTokenIssuanceEndpoint:
    @pytest.mark.asyncio
    async def test_get_csrf_token_endpoint(self, middleware):
        """GET /api/csrf-token should return a new token."""
        middleware.app = AsyncMock()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/csrf-token",
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should NOT be called (middleware handles this endpoint directly)
        middleware.app.assert_not_called()
        # Response should be 200
        start_call = send.call_args_list[0]
        start_msg = start_call.args[0] if start_call.args else start_call.kwargs.get("message", {})
        assert start_msg["status"] == 200
        # Response body should contain a csrf_token
        body_call = send.call_args_list[1]
        body_msg = body_call.args[0] if body_call.args else body_call.kwargs.get("message", {})
        body = body_msg["body"].decode("utf-8")
        assert "csrf_token" in body


class TestGarbageCollection:
    def test_expired_tokens_cleaned_up(self, middleware):
        """When store exceeds 1000 entries, expired tokens are removed."""
        # Add 1001 tokens, all expired
        past = time.time() - 1
        for i in range(1001):
            middleware._token_store[f"expired-{i}"] = past

        # Issue a new token — triggers garbage collection
        new_token = middleware._issue_token()

        # Store should be much smaller now (only valid tokens remain)
        assert len(middleware._token_store) < 100
        assert new_token in middleware._token_store


class TestNonHttpScope:
    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self, middleware):
        """Non-HTTP scopes (e.g., websocket) should pass through without CSRF check."""
        middleware.app = AsyncMock()
        scope = {"type": "websocket", "path": "/ws"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        middleware.app.assert_called_once_with(scope, receive, send)
