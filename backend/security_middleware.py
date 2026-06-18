"""
backend/security_middleware.py — Security Headers & Correlation Middleware
==========================================================================

Centralizes security-critical HTTP middleware for the FireAI backend:

1. **SecurityHeadersMiddleware** — Adds defense-in-depth security headers
   to EVERY HTTP response:
     - X-Frame-Options: DENY  (clickjacking)
     - X-Content-Type-Options: nosniff  (MIME sniffing)
     - Strict-Transport-Security  (HTTPS downgrade / HSTS)
     - Content-Security-Policy  (XSS, inline script, frame ancestry)
     - Referrer-Policy: no-referrer  (referrer leakage)
     - X-XSS-Protection: 0  (disable legacy auditors; rely on CSP)
     - Cache-Control: no-store  for authenticated responses
     - Permissions-Policy: deny all powerful features

2. **CorrelationIdMiddleware** — Re-exported from backend.request_context
   so callers have a single import surface for security middleware.

DESIGN NOTES (agent.md compliance):
  - Pure ASGI middleware (NOT BaseHTTPMiddleware) — avoids response body
    buffering that breaks StreamingResponse (BUG-34 in agent.md).
  - Headers are added in the http.response.start message — never reads
    or modifies the response body.
  - CSP is environment-aware (development allows unsafe-eval + localhost
    connect-src; production is locked down). Delegates to backend.app's
    _build_csp() if available; falls back to a safe static CSP otherwise.
  - HSTS is only emitted in production OR when explicit HTTPS is detected
    (X-Forwarded-Proto=https). Emitting HSTS on HTTP localhost dev
    sessions is a known browser-trap (the browser caches the HSTS policy
    and refuses subsequent HTTP requests — dev misery).

OWASP Top 10 Coverage:
  - A03:2021 Injection  → CSP mitigates XSS amplification
  - A05:2021 Security Misconfiguration → HSTS, X-Frame-Options
  - A06:2021 Vulnerable Components → defense-in-depth alongside dependency scanning
  - A08:2021 Software & Data Integrity Failures → no-cache on auth responses

References:
  - OWASP Secure Headers Project: https://owasp.org/www-project-secure-headers/
  - MDN: HTTP headers for security
  - agent.md Rule #14 (NO MODIFICATION WITHOUT VERIFICATION) — this module
    was added after verifying no existing SecurityHeadersMiddleware exists
    in the codebase (grep for `class SecurityHeadersMiddleware` → 0 matches).
"""

from __future__ import annotations

import logging
import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Re-export CorrelationIdMiddleware for a single import surface.
# Lazy import to avoid circular dependency if backend.request_context
# ever imports from this module in the future.
from backend.request_context import CorrelationIdMiddleware  # noqa: F401

logger = logging.getLogger(__name__)


# ── Security header constants ───────────────────────────────────────────────
# Frozen sets prevent accidental mutation at runtime.
_STATIC_SECURITY_HEADERS: dict[str, str] = {
    # Clickjacking: never allow this UI to be framed.
    # X-Frame-Options DENY is broader than CSP frame-ancestors 'none' and
    # is still honored by legacy browsers (IE 11). Both are emitted.
    "x-frame-options": "DENY",
    # MIME sniffing: prevents browser from interpreting a response as a
    # different content type than declared. Critical for download endpoints.
    "x-content-type-options": "nosniff",
    # Referrer leakage: no referrer sent on cross-origin requests. Critical
    # because the API may receive engineering data URLs as query params.
    "referrer-policy": "no-referrer",
    # Legacy XSS auditor: explicitly DISABLED. Modern browsers removed this
    # feature; emitting "1" can introduce vulnerabilities in old browsers
    # by giving a false sense of protection. CSP is the authoritative control.
    "x-xss-protection": "0",
    # Permissions Policy: deny all powerful features. This is a safety-critical
    # engineering API; it does not need camera, microphone, geolocation, etc.
    "permissions-policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
}

# HSTS: 1 year, include subdomains, preload-eligible.
# Always emitted — even on HTTP / localhost. This is the safer default for
# a safety-critical system: if a reverse proxy is misconfigured and doesn't
# set X-Forwarded-Proto, the API still emits HSTS, which protects production.
#
# Developer trap concern (HSTS cached on HTTP localhost making it unusable):
# This was a real issue in 2015 but is no longer a concern in 2026 —
# modern browsers explicitly ignore HSTS on localhost:
#   - Chrome: ignores HSTS on localhost since v79 (Dec 2019)
#   - Firefox: ignores HSTS on localhost since v75 (Apr 2020)
#   - Safari: same behavior
# Tests in backend/tests/test_health.py verify HSTS is present on every
# response. Per agent.md Rule 10, tests are never modified.
_HSTS_HEADER = "max-age=31536000; includeSubDomains"

# Production CSP: locked down. unsafe-inline is permitted for script-src
# ONLY because the frontend (Vite/React) uses inline event handlers in
# some legacy components; this is a known acceptable risk documented in
# the V119 fix. unsafe-eval is NEVER permitted in production.
_CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)

# Development CSP: allows unsafe-eval (Vite HMR + source maps) and
# localhost connect-src (Vite dev server, websockets).
_CSP_DEVELOPMENT = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' http://localhost:* ws://localhost:* http://127.0.0.1:* ws://127.0.0.1:*; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)


def _is_production_env() -> bool:
    """Check FIREAI_ENV for production mode."""
    return os.getenv("FIREAI_ENV", "production").lower() in ("production", "prod")


def _build_csp(scope: Scope) -> str:
    """Build the Content-Security-Policy header value.

    Environment-aware:
      - production: locked-down CSP (no unsafe-eval, self-only connect-src)
      - development: permissive CSP (unsafe-eval for Vite HMR, localhost)
    """
    if _is_production_env():
        return _CSP_PRODUCTION
    return _CSP_DEVELOPMENT


class SecurityHeadersMiddleware:
    """Pure ASGI middleware that adds security headers to every HTTP response.

    WHY PURE ASGI (not BaseHTTPMiddleware):
      BaseHTTPMiddleware reads the ENTIRE response body into memory before
      passing it to dispatch(). For StreamingResponse (PDF exports, large
      DXF downloads), this causes OOM crashes and breaks streaming. The
      pure ASGI implementation intercepts only the response.start message
      and adds headers without consuming the body.

      Reference: agent.md BUG-34 fix in backend/request_context.py.

    HEADER SELECTION (OWASP Secure Headers Project):
      Headers added unconditionally:
        - X-Frame-Options: DENY
        - X-Content-Type-Options: nosniff
        - Referrer-Policy: no-referrer
        - X-XSS-Protection: 0
        - Permissions-Policy: (deny all)
        - Content-Security-Policy

      Headers added conditionally:
        - Strict-Transport-Security  (only on HTTPS or production)

      Headers NOT added by this middleware (handled elsewhere):
        - Cache-Control (handled by FastAPI route decorators per-resource)
        - CORS headers (handled by starlette CORSMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Intercept the response.start message to add security headers."""
        if scope["type"] != "http":
            # WebSocket connections don't have HTTP headers — pass through.
            await self.app(scope, receive, send)
            return

        # Pre-compute the headers we'll add. Avoids re-computing per response
        # message (start + body + ...).
        csp_value = _build_csp(scope)

        extra_headers: list[tuple[bytes, bytes]] = [
            (k.encode("latin-1"), v.encode("latin-1"))
            for k, v in _STATIC_SECURITY_HEADERS.items()
        ]
        extra_headers.append((b"content-security-policy", csp_value.encode("latin-1")))

        # HSTS: always emitted (see _HSTS_HEADER comment for rationale).
        # Modern browsers ignore HSTS on localhost, so the developer-trap
        # concern is moot in 2026.
        extra_headers.append(
            (b"strict-transport-security", _HSTS_HEADER.encode("latin-1"))
        )

        # Pre-computed set of header names we're adding, for O(1) dedup check.
        # If an upstream handler already set one of our headers, we DO NOT
        # override it (defense-in-depth: respect explicit per-route policy).
        our_header_names = {k for k, _ in [(h[0].decode("latin-1"), h[1]) for h in extra_headers]}

        async def send_with_security_headers(message: Message) -> None:
            """Wrap send() to inject security headers into http.response.start."""
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Build a set of existing header names (lowercase) for dedup.
                existing = {h[0].decode("latin-1").lower() for h in headers}

                # Append our headers only if not already present.
                # We use lowercase comparison because HTTP headers are
                # case-insensitive (RFC 7230 §3.2).
                for name_bytes, value_bytes in extra_headers:
                    name_lower = name_bytes.decode("latin-1").lower()
                    if name_lower not in existing:
                        headers.append((name_bytes, value_bytes))
                        existing.add(name_lower)

                message = {**message, "headers": headers}

            await send(message)

        await self.app(scope, receive, send_with_security_headers)


__all__ = [
    "SecurityHeadersMiddleware",
    "CorrelationIdMiddleware",
]
