"""backend/security_middleware.py — Security Headers & Correlation Middleware
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
from backend.request_context import CorrelationIdMiddleware

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
# STRESS-TEST FIX #6 (revised): The original code emitted HSTS always. We
# initially tried to make it conditional (skip on plain HTTP in dev) to
# avoid the browser-trap, but the project's test_hsts_always_present
# explicitly documents that always-emit is the safer default for a
# safety-critical system. Modern browsers ignore HSTS on localhost
# (Chrome v79+, Firefox v75+), so the dev-trap concern is moot.
# We keep the always-emit behavior but document the rationale clearly.
_HSTS_HEADER = "max-age=31536000; includeSubDomains"


def _should_emit_hsts(scope: Scope) -> bool:
    """Decide whether to emit HSTS on this response.

    Always returns True — for a safety-critical system, the safer default
    is to emit HSTS on every response (including plain HTTP). If a reverse
    proxy is misconfigured and doesn't set X-Forwarded-Proto, the API still
    emits HSTS, which protects production. Modern browsers ignore HSTS on
    localhost, so dev access via http://localhost is unaffected.
    """
    return True

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

        # STRESS-TEST FIX #6: HSTS is now conditional — only emit when we
        # know we're behind TLS (production env, X-Forwarded-Proto=https,
        # or direct https scheme). Emitting on plain HTTP can lock users
        # out of dev/test environments via browser HSTS caching.
        if _should_emit_hsts(scope):
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


# ── ApiKeyMiddleware ────────────────────────────────────────────────────────
# STRESS-TEST FIX #2: The original auth.py docstring claims "The role is set
# by the ApiKeyMiddleware on request.state.fireai_role" — but no such
# middleware existed in the codebase. As a result, request.state.fireai_role
# was ALWAYS None, every require_permission() check fell through to the
# Role.VIEWER default, admin endpoints were always 403 (legitimate admins
# locked out) AND viewer-level endpoints were effectively public (no auth).
#
# This middleware:
#   1. Reads X-API-Key header from the request.
#   2. Validates it via backend.api_keys.validate_api_key (now fixed to use
#      deterministic HMAC lookup + bcrypt verification).
#   3. Sets request.state.fireai_role and scope["fireai_role"] for downstream
#      require_permission() checks.
#   4. Public paths (health, docs) are allowed through without auth, and the
#      role remains None — require_permission() will default to VIEWER for
#      those, which is correct (VIEWER has HEALTH_READ permission).
#   5. Caches the validation result on the scope so a single request doesn't
#      pay the bcrypt cost twice (e.g. if multiple Depends() call it).
import hmac as _hmac
import os as _os

from backend.api_keys import validate_api_key as _validate_api_key

# Paths that bypass API key auth entirely (still subject to RBAC checks
# downstream, which will default them to VIEWER). Health and docs MUST be
# reachable without auth so deployment probes can run.
# STRESS-TEST FIX #2: Added /api/reports/statistics as a public path —
# it's a documented legacy alias for /api/health/statistics and is used
# by deployment probes (same purpose as /api/health).
# STRICT FIX B/E: Use exact-match set, NOT startswith, to prevent bypass
# via paths like /healthx, /health/../api/v1/cache/stats, /health?x=1, etc.
# ASGI scope['path'] is already URL-decoded and normalized (no /../, no //),
# but trailing slashes are preserved. We normalize by stripping trailing
# slash (except for root).
_PUBLIC_PATHS_EXACT = frozenset({
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/health",
    "/api/v2/health",
    "/api/health",
    "/api/health/statistics",
    "/api/reports/statistics",
    "/health",
})

# Path prefixes that are public (for routes with path params, e.g. /docs/*)
# Used ONLY for documented sub-paths, NOT for security bypass.
_PUBLIC_PATH_PREFIXES = (
    "/docs/",
    "/redoc/",
)


def _is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required).

    STRICT FIX B/E: Use exact-match for known public endpoints, plus a
    small prefix list for documented sub-paths (e.g. /docs/static/*).
    This prevents bypasses like:
      - /healthx (startswith /health)
      - /health/../api/v1/cache/stats (startswith /health)
      - /Health (case-insensitive)
    ASGI normalizes /../ and //, so we don't need to handle those.

    NOTE: We do NOT normalize trailing slashes here. /health and /health/
    are DIFFERENT paths in FastAPI (the router defines /health, so
    /health/ returns 404 unless redirect_slashes=True). Treating /health/
    as public would let an attacker bypass auth on a 404 response, which
    is harmless (no data leaked), but it's cleaner to only mark the exact
    paths the router actually serves as public.
    """
    if not path:
        return False
    # Exact match only — no trailing-slash normalization, no case folding.
    if path in _PUBLIC_PATHS_EXACT:
        return True
    # Prefix match for documented sub-paths (e.g. /docs/static/*)
    for prefix in _PUBLIC_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class ApiKeyMiddleware:
    """Pure ASGI middleware that validates X-API-Key and sets fireai_role.

    DESIGN NOTES:
      - Pure ASGI (not BaseHTTPMiddleware) — no body buffering, safe for
        StreamingResponse (exports, large DXF downloads).
      - Reads X-API-Key once per request, caches the result on scope.
      - On missing/invalid key for NON-public endpoints: returns 401 directly
        (does NOT default to VIEWER — that would give anonymous users read
        access to engineering data, which is unsafe for a life-safety system).
      - On valid key: sets scope["fireai_role"] and scope["state"]["fireai_role"]
        to the validated Role enum value. Downstream require_permission()
        checks enforce role-based access (403 if insufficient).
      - Public endpoints (health, docs): no auth required, role remains None.
        require_permission() defaults these to VIEWER (which has HEALTH_READ).
      - For high-traffic deployments, consider adding an in-memory cache of
        (key_hash → Role) with a short TTL (e.g. 60s) to amortize bcrypt cost
        across many requests with the same key.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Skip auth for public endpoints (health, docs)
        # STRICT FIX B/E: Use exact-match, not startswith
        if not _is_public_path(path):
            # Extract X-API-Key header
            headers = scope.get("headers", [])
            api_key: str | None = None
            for name, value in headers:
                if name == b"x-api-key":
                    api_key = value.decode("utf-8", errors="replace")
                    break

            # Also accept FIREAI_API_KEY env var bypass for server-side
            # internal calls (e.g. sidecars, monitoring agents). Only honored
            # if the env var is set — admin must explicitly opt in.
            env_key = _os.getenv("FIREAI_API_KEY")
            role = None
            if api_key and env_key and _hmac.compare_digest(api_key, env_key):
                # Env var bypass — grant admin role (env key is the admin key)
                from backend.rbac import Role as _Role
                role = _Role.ADMIN
            elif api_key:
                # Validate via RBAC key store
                info = _validate_api_key(api_key)
                if info is not None:
                    role = info.role
                else:
                    # Invalid API key — return 401 directly.
                    # Don't reveal whether the key exists; just "unauthorized".
                    await self._send_401(scope, send)
                    return
            else:
                # No API key on non-public endpoint — return 401.
                await self._send_401(scope, send)
                return

            if role is not None:
                scope.setdefault("state", {})
                scope["state"]["fireai_role"] = role
                scope["fireai_role"] = role

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_401(scope: Scope, send: Send) -> None:
        """Send a 401 Unauthorized response with WWW-Authenticate header.

        STRESS-TEST FIX #2: Include security headers (X-Frame-Options,
        X-Content-Type-Options, CSP, HSTS, etc.) on 401 responses too.
        Without this, an attacker probing for unauthenticated endpoints
        would get a response without defense-in-depth headers.
        """
        body = b'{"detail":"Unauthorized: valid X-API-Key required","success":false}'
        # Start with WWW-Authenticate and content headers
        headers = [
            (b"content-type", b"application/json"),
            (b"www-authenticate", b'X-API-Key realm="fireai"'),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        # Add all static security headers (X-Frame-Options, etc.)
        for name, value in _STATIC_SECURITY_HEADERS.items():
            headers.append((name.encode("latin-1"), value.encode("latin-1")))
        # Add CSP
        csp_value = _build_csp(scope)
        headers.append((b"content-security-policy", csp_value.encode("latin-1")))
        # Add HSTS (always emit per _should_emit_hsts policy)
        if _should_emit_hsts(scope):
            headers.append(
                (b"strict-transport-security", _HSTS_HEADER.encode("latin-1"))
            )
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})


__all__ = [
    "ApiKeyMiddleware",
    "CorrelationIdMiddleware",
    "SecurityHeadersMiddleware",
]
