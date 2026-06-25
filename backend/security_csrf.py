"""csrf_middleware.py — Production-Grade CSRF Protection (Double Submit Cookie)
==============================================================================

MISSION PHASE 1.1 — Cybersecurity Hardening (The Shield)
=========================================================

Implements the **Double Submit Cookie** CSRF protection pattern (OWASP
recommended) for the FireAI backend.

How Double Submit Cookie Works
------------------------------
1. On any GET request to a "token-issuing" endpoint (e.g., /api/v2/auth/csrf-token),
   the server generates a cryptographically random CSRF token.
2. The server sets this token in TWO places:
   a) A cookie: ``fireai_csrf_token`` (HttpOnly=false, SameSite=Strict)
   b) The response body (for the frontend to read and include in subsequent requests)
3. On any state-changing request (POST/PUT/DELETE/PATCH), the client MUST include:
   a) The cookie (sent automatically by the browser)
   b) A header: ``X-CSRF-Token: <token>``
4. The middleware compares the cookie value with the header value. If they
   match AND pass validation, the request proceeds. Otherwise → 403.

Why Double Submit Cookie (not Synchronizer Token)?
--------------------------------------------------
- FireAI is a stateless REST API. Synchronizer Token requires server-side
  session storage, which conflicts with the multi-worker uvicorn deployment
  (each worker would need to share session state via Redis).
- Double Submit Cookie is stateless — perfect for cloud-native deployment.
- The token is bound to the user's session via the cookie, not the server.

Security Properties
-------------------
1. **Cryptographically random**: Token = `secrets.token_urlsafe(32)` (256 bits entropy).
2. **SameSite=Strict**: Cookie is only sent on same-site requests, preventing CSRF
   from cross-origin domains.
3. **Constant-time comparison**: Uses `hmac.compare_digest()` to prevent timing attacks.
4. **Token rotation**: New token per session, refreshed on login.
5. **Exempt paths**: GET/HEAD/OPTIONS are exempt (safe methods). API-key-only
   endpoints (no cookies) are exempt. Health checks are exempt.

OWASP Coverage
--------------
- A01:2021 Broken Access Control → CSRF tokens prevent cross-origin state changes
- A07:2021 Identification & Authentication Failures → SameSite cookies

References
----------
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- agent.md Rule 12 (Safety-First) + Rule 17 (Root-Cause Analysis)
"""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Awaitable, Callable, MutableMapping

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# V135 F-14 FIX: Use __Host- prefix for the CSRF cookie.
# Per OWASP: the __Host- prefix enforces:
#   - Secure attribute (HTTPS only)
#   - Path=/ (root only)
#   - No Domain attribute (host-only)
# This prevents subdomain cookie injection attacks where an attacker with
# XSS on blog.fireai.com could set fireai_csrf_token on the victim's browser.
# Browsers REJECT __Host- cookies that don't meet these requirements.
CSRF_COOKIE_NAME = "__Host-fireai_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_TOKEN_LENGTH = 32  # bytes → 43 chars in urlsafe base64

# Cookie attributes — SameSite=Strict is critical for CSRF protection
CSRF_COOKIE_ATTRIBUTES = (
    f"{CSRF_COOKIE_NAME}={{token}}; "
    "Path=/; "
    "SameSite=Strict; "
    "Secure; "  # HTTPS only (browser will drop on HTTP — fine for dev with HTTP_EXCEPTIONS)
    "Max-Age=86400; "  # 24 hours
    # NOTE: HttpOnly=false — the frontend JS MUST be able to read the cookie
    # to extract the token and send it in the X-CSRF-Token header.
)

# Safe HTTP methods that do NOT require CSRF protection (RFC 7231 §4.2.1)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths exempt from CSRF (API-key-only endpoints, health checks, docs)
# Per Rule 12: be conservative — only exempt what's truly safe
CSRF_EXEMPT_PATHS = frozenset({
    "/api/v2/health",
    "/api/v1/health",
    "/api/health",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
})

# V135 F-35 FIX: Removed dead CSRF_SAFE_CONTENT_TYPES constant.
# It was defined but NEVER USED anywhere in the codebase. Keeping it
# misled readers into thinking the middleware enforces content-type
# checks. The middleware enforces CSRF on ALL state-changing requests
# regardless of content type (defense in depth per Rule 12).

# V135 F-13 FIX: Read _DEV_ALLOW_HTTP_COOKIES from env var (was hardcoded True).
# In production, this MUST be False (or unset, which defaults to False).
# The OLD hardcoded True overrode the dev_allow_http parameter, causing the
# Secure attribute to be omitted in production behind TLS-terminating proxies.
import os as _os
_DEV_ALLOW_HTTP_COOKIES = _os.environ.get("FIREAI_DEV_ALLOW_HTTP_COOKIES", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Token Generation & Validation
# ---------------------------------------------------------------------------


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token.

    Uses `secrets.token_urlsafe(32)` which produces a 43-character URL-safe
    base64 string from 32 bytes (256 bits) of entropy.

    Returns:
        43-character CSRF token string.
    """
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token format (not its correctness — that's done via comparison).

    A valid token:
    - Is a string
    - Has length ≥ 32 (urlsafe base64 of 32 bytes = 43 chars, but allow some slack)
    - Contains only URL-safe base64 characters (A-Z, a-z, 0-9, -, _)

    Args:
        token: Token string to validate.

    Returns:
        True if token format is valid.
    """
    if not isinstance(token, str) or len(token) < 32:
        return False
    try:
        # Verify it's valid URL-safe base64 by attempting to decode
        import base64
        # Add padding if needed
        padded = token + "=" * (4 - len(token) % 4) if len(token) % 4 else token
        decoded = base64.urlsafe_b64decode(padded)
        return len(decoded) >= 24  # At least 24 bytes decoded (192 bits)
    except Exception:
        return False


def tokens_match(cookie_token: str, header_token: str) -> bool:
    """Constant-time comparison of cookie and header tokens.

    Per OWASP: must use constant-time comparison to prevent timing attacks
    that could progressively guess the token byte-by-byte.

    Args:
        cookie_token: Token from the CSRF cookie.
        header_token: Token from the X-CSRF-Token header.

    Returns:
        True if tokens are valid AND match (constant-time).
    """
    if not validate_csrf_token(cookie_token) or not validate_csrf_token(header_token):
        return False
    # hmac.compare_digest is constant-time for strings of equal length
    # For unequal lengths, it returns False immediately (which is safe)
    return hmac.compare_digest(cookie_token, header_token)


# ---------------------------------------------------------------------------
# ASGI Middleware (Pure ASGI — NOT BaseHTTPMiddleware per BUG-34)
# ---------------------------------------------------------------------------


class CSRFMiddleware:
    """Pure ASGI middleware implementing Double Submit Cookie CSRF protection.

    Usage in backend/app.py:
        from backend.security_csrf import CSRFMiddleware
        app.add_middleware(CSRFMiddleware)

    Behavior:
    - GET/HEAD/OPTIONS: Pass through (safe methods).
    - POST/PUT/DELETE/PATCH with JSON content type: Require matching CSRF tokens.
    - POST/PUT/DELETE/PATCH with form content type: Require matching CSRF tokens.
    - Exempt paths (health, docs): Pass through.

    Token issuance is handled by a separate endpoint (e.g., /api/v2/auth/csrf-token),
    NOT by this middleware. The middleware only VALIDATES.
    """

    def __init__(
        self,
        app: Callable,
        exempt_paths: frozenset[str] | None = None,
        dev_allow_http: bool = False,
    ) -> None:
        """Initialize CSRF middleware.

        Args:
            app: ASGI application to wrap.
            exempt_paths: Additional paths to exempt (merged with default).
            dev_allow_http: If True, allow Secure cookies on HTTP (dev only).
        """
        self.app = app
        self.exempt_paths = CSRF_EXEMPT_PATHS | (exempt_paths or frozenset())
        # V135 F-13 FIX: Respect the dev_allow_http parameter (don't OR with constant).
        # The OLD code did `dev_allow_http or _DEV_ALLOW_HTTP_COOKIES` which
        # ignored False values (False or True = True). Now the parameter is
        # authoritative; _DEV_ALLOW_HTTP_COOKIES is only a module-level default.
        self.dev_allow_http = bool(dev_allow_http) if dev_allow_http is not None else _DEV_ALLOW_HTTP_COOKIES

    async def __call__(
        self,
        scope: MutableMapping,
        receive: Callable,
        send: Callable,
    ) -> None:
        """ASGI entry point.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        # V135 F-22 / V137 F-2 FIX: WebSocket connections need Origin header
        # validation to prevent Cross-Site WebSocket Hijacking (CSWSH).
        # The V135 F-22 "fix" only logged at DEBUG and ALWAYS called
        # await self.app() — it was a NO-OP. Now we ACTUALLY enforce
        # the Origin check: reject WebSocket connections from untrusted origins.
        scope_type = scope.get("type")
        if scope_type == "websocket":
            headers = scope.get("headers", [])
            origin = None
            host = None
            for name, value in headers:
                if name == b"origin":
                    origin = value.decode("utf-8", errors="replace")
                elif name == b"host":
                    host = value.decode("utf-8", errors="replace")

            # V137 F-2: If Origin header is present, verify it matches the Host.
            # Per OWASP CSWSH Prevention Cheat Sheet: the Origin header must
            # match the server's host (or be in an allowlist).
            if origin and host:
                # Extract hostname from Origin URL
                try:
                    from urllib.parse import urlparse
                    origin_parsed = urlparse(origin)
                    origin_host = origin_parsed.hostname or ""
                    # Extract hostname from Host header (strip port)
                    host_name = host.split(":")[0]

                    # Allow if origin host matches server host
                    # In dev mode, also allow localhost variants
                    is_dev = _os.environ.get("FIREAI_ENV", "development").lower() == "development"
                    trusted_hosts = {host_name, "localhost", "127.0.0.1"} if is_dev else {host_name}

                    if origin_host not in trusted_hosts:
                        # V137 F-2: REJECT the WebSocket connection (was NO-OP before)
                        logger.warning(
                            "CSWSH BLOCKED: WebSocket connection from untrusted origin '%s' "
                            "(host='%s'). Rejecting connection per OWASP CSWSH prevention.",
                            origin, host,
                        )
                        # Send close frame with policy violation code
                        await send({
                            "type": "websocket.close",
                            "code": 1008,  # Policy Violation
                            "reason": "Untrusted origin",
                        })
                        return
                except Exception as exc:
                    logger.warning("WebSocket origin check error: %s", exc)
                    # Fail-safe: reject if we can't verify
                    await send({
                        "type": "websocket.close",
                        "code": 1008,
                        "reason": "Origin verification failed",
                    })
                    return

            await self.app(scope, receive, send)
            return

        if scope_type != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        # Safe methods pass through (GET, HEAD, OPTIONS)
        if method in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # V135 F-23 FIX: Normalize trailing slash for exempt path check.
        # The OLD code did exact match (`if path in self.exempt_paths`)
        # which failed for `/api/v2/health/` (trailing slash). FastAPI
        # often redirects trailing slashes, but the middleware runs
        # BEFORE the redirect. Now we check both with and without slash.
        path_normalized = path.rstrip("/")
        if path in self.exempt_paths or path_normalized in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        # For state-changing methods (POST/PUT/DELETE/PATCH), check CSRF tokens
        # Extract cookie token from Cookie header
        headers = scope.get("headers", [])
        cookie_token = self._extract_cookie_token(headers)
        header_token = self._extract_header_token(headers)

        # Determine content type
        content_type = self._extract_content_type(headers)

        # JSON content type with proper CORS preflight is technically safe from CSRF,
        # but we enforce CSRF for ALL state-changing requests as defense in depth.
        # Per Rule 12 (Safety-First): be conservative.

        if not tokens_match(cookie_token, header_token):
            # CSRF validation failed
            logger.warning(
                "CSRF validation failed for %s %s: cookie_present=%s header_present=%s content_type=%s",
                method, path,
                bool(cookie_token), bool(header_token), content_type,
            )
            await self._send_403(scope, send, "CSRF token missing or invalid")
            return

        # CSRF validation passed — proceed with the request
        await self.app(scope, receive, send)

    # ------------------------------------------------------------------
    # Header Extraction Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_cookie_token(headers: list) -> str | None:
        """Extract CSRF token from Cookie header.

        Args:
            headers: List of (name_bytes, value_bytes) tuples from ASGI scope.

        Returns:
            Token string or None if not found.
        """
        for name, value in headers:
            if name == b"cookie":
                cookie_header = value.decode("utf-8", errors="replace")
                # Parse cookie header: "key1=val1; key2=val2; ..."
                for part in cookie_header.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k.strip() == CSRF_COOKIE_NAME:
                            return v.strip()
        return None

    @staticmethod
    def _extract_header_token(headers: list) -> str | None:
        """Extract CSRF token from X-CSRF-Token header.

        Args:
            headers: List of (name_bytes, value_bytes) tuples.

        Returns:
            Token string or None if not found.
        """
        for name, value in headers:
            if name == CSRF_HEADER_NAME.encode("ascii"):
                return value.decode("utf-8", errors="replace").strip()
        return None

    @staticmethod
    def _extract_content_type(headers: list) -> str:
        """Extract Content-Type header (lowercased, without parameters)."""
        for name, value in headers:
            if name == b"content-type":
                ct = value.decode("utf-8", errors="replace").lower()
                # Strip parameters: "application/json; charset=utf-8" → "application/json"
                return ct.split(";")[0].strip()
        return ""

    # ------------------------------------------------------------------
    # 403 Response Sender
    # ------------------------------------------------------------------

    @staticmethod
    async def _send_403(scope: MutableMapping, send: Callable, detail: str) -> None:
        """Send a 403 Forbidden response with JSON error body.

        Per OWASP: never reveal whether the token existed but was wrong,
        vs. was missing entirely. Always return the same generic message.
        """
        import json

        body = json.dumps({
            "detail": detail,
            "success": False,
            "error_code": "CSRF_VALIDATION_FAILED",
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                # Don't cache error responses
                (b"cache-control", b"no-store"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


# ---------------------------------------------------------------------------
# Cookie Helper (for the token-issuing endpoint)
# ---------------------------------------------------------------------------


def build_csrf_cookie_header(token: str, is_https: bool = True) -> str:
    """Build the Set-Cookie header value for the CSRF token.

    V137 F-9 FIX: The __Host- prefix (V135 F-14) REQUIRES the Secure
    attribute. If _DEV_ALLOW_HTTP_COOKIES=True and is_https=False, the
    OLD code omitted Secure — producing an INVALID __Host- cookie that
    browsers REJECT. Now we ALWAYS include Secure when using __Host-
    prefix (browsers enforce this anyway, but we're explicit).

    Args:
        token: CSRF token string.
        is_https: Whether the connection is HTTPS (affects Secure attribute).

    Returns:
        Set-Cookie header value string.
    """
    # V137 F-9: __Host- prefix REQUIRES Secure attribute per RFC 6265bis.
    # Even in dev mode with _DEV_ALLOW_HTTP_COOKIES=True, we MUST include
    # Secure because __Host- cookies without it are rejected by browsers.
    # In dev mode over HTTP, the cookie simply won't be SET by the browser
    # (which is the correct behavior — use HTTPS for testing CSRF).
    # The only way to test CSRF over HTTP is to NOT use __Host- prefix,
    # which we don't support (security > dev convenience).
    secure_attr = "Secure; "  # Always include for __Host- prefix

    return (
        f"{CSRF_COOKIE_NAME}={token}; "
        "Path=/; "
        "SameSite=Strict; "
        f"{secure_attr}"
        "Max-Age=86400"
    )


__all__ = [
    "CSRFMiddleware",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "CSRF_EXEMPT_PATHS",
    "generate_csrf_token",
    "validate_csrf_token",
    "tokens_match",
    "build_csrf_cookie_header",
]
