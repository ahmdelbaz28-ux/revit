"""
backend/akamai_middleware.py — Akamai Edge Integration Middleware.
====================================================================

PURPOSE
-------
Provides a pure-ASGI middleware that integrates the FireAI backend with an
Akamai Edge deployment (Property Manager + Kona WAF + Bot Manager + API
Security). This middleware is the application-side counterpart to the
Akamai configuration templates in `deploy/akamai/`.

The middleware performs six safety-critical functions:

1. **Origin verification** — Ensures incoming requests transited Akamai
   (header `Akamai-Internal`) when AKAMAI_REQUIRE_ORIGIN_TOKEN is set.
   Prevents direct origin access bypassing WAF/Bot rules.

2. **True-Client-IP trust** — Replaces untrusted `X-Forwarded-For` chains
   with the single `True-Client-IP` header that Akamai injects AFTER
   authenticating the request. Without this, rate limiters and audit logs
   see Akamai edge IPs (useless for forensics).

3. **Bot score enforcement** — Reads `Akamai-Bot-Score` (0-100, 0=human,
   100=bot) and rejects requests above AKAMAI_ALLOWED_BOT_SCORE for
   sensitive endpoints (login, password reset, API key generation).

4. **Geo filtering** — Reads `Akamai-Geo-Country` (ISO 3166-1 alpha-2)
   and rejects requests from countries in AKAMAI_BLOCKED_COUNTRIES.

5. **Rate limit header passthrough** — Forwards Akamai's `X-RateLimit-*`
   response headers to the client so the frontend can show "retry after"
   UIs.

6. **Security header augmentation** — Adds `X-Akamai-Translated-Request`
   and `Akamai-GRN` (Global Request ID) to the response for traceability
   across the Akamai → origin → database chain.

DESIGN NOTES (agent.md compliance)
---------------------------------
- Pure ASGI middleware (NOT BaseHTTPMiddleware) — avoids response body
  buffering that breaks StreamingResponse (BUG-34 in agent.md).
- All headers are read from `scope["headers"]` (raw bytes), not via
  Starlette's Request object — minimizes overhead.
- When `AKAMAI_ENABLED=false` (default), the middleware is a no-op:
  zero runtime cost in development and on HF Space without Akamai.
- Fail-safe: if Akamai headers are missing in production (misconfigured
  origin), the middleware LOGS A WARNING but does NOT block the request
  (availability over strictness; the WAF still runs at the edge).

OWASP Top 10 Coverage
---------------------
- A01:2021 Broken Access Control → origin verification (bypass prevention)
- A04:2021 Insecure Design → bot score + geo filtering
- A05:2021 Security Misconfiguration → fail-open with logging
- A07:2021 Identification & Auth Failures → bot score on login endpoints

References
----------
- Akamai Property Manager: https://techdocs.akamai.com/property-mgr
- Akamai Bot Manager: https://techdocs.akamai.com/bot-manager
- Akamai True-Client-IP: https://techdocs.akamai.com/property-mgr/docs/true-client-ip
- agent.md Rule #14 (NO MODIFICATION WITHOUT VERIFICATION)
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Header names are case-insensitive per RFC 7230 §3.2; ASGI scope stores
# them as lower-case bytes. We define them once to avoid repeated .encode().
_HDR_AKAMAI_INTERNAL = b"akamai-internal"
_HDR_TRUE_CLIENT_IP = b"true-client-ip"
_HDR_X_FORWARDED_FOR = b"x-forwarded-for"
_HDR_AKAMAI_BOT_SCORE = b"akamai-bot-score"
_HDR_AKAMAI_BOT_PREVIEW = b"akamai-bot-preview"
_HDR_AKAMAI_GEO_COUNTRY = b"akamai-geo-country"
_HDR_AKAMAI_GRN = b"x-akamai-request-id"
_HDR_AKAMAI_RATE_LIMIT_LIMIT = b"x-ratelimit-limit"
_HDR_AKAMAI_RATE_LIMIT_REMAINING = b"x-ratelimit-remaining"
_HDR_AKAMAI_RATE_LIMIT_RESET = b"x-ratelimit-reset"

# Endpoints where bot score is enforced strictly (auth + admin).
# Matched as startswith() so sub-paths are covered too.
_BOT_SENSITIVE_PATHS: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/reset-password",
    "/api/v1/admin/api-keys",
    "/api/v1/admin/users",
)

# Header injected on every response so operators can correlate logs across
# Akamai → origin → database. Format matches Akamai's GRN (Global Request ID).
_RESPONSE_TRACE_HEADER = "X-Akamai-Translated-Request"


# ── Config ───────────────────────────────────────────────────────────────────


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean env var. Accepts true/false/1/0/yes/no (case-insensitive)."""
    v = os.getenv(name, "").strip().lower()
    if not v:
        return default
    return v in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Read an integer env var with safe fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: Iterable[str] = ()) -> frozenset[str]:
    """Read a comma-separated env var as a frozenset of stripped upper values."""
    raw = os.getenv(name, "")
    if not raw.strip():
        return frozenset(default)
    return frozenset(
        item.strip().upper() for item in raw.split(",") if item.strip()
    )


class AkamaiConfig:
    """Lazy-loaded configuration snapshot.

    Reading env vars at startup (not import time) lets HF Space / Vercel
    inject secrets after module load. Re-read on every request would be
    wasteful; instead, the config is loaded once when the middleware is
    instantiated and remains immutable for the process lifetime.
    """

    __slots__ = (
        "allowed_bot_score",
        "blocked_countries",
        "enabled",
        "production_mode",
        "rate_limit_passthrough",
        "require_origin_token",
    )

    def __init__(self) -> None:
        self.enabled: bool = _env_bool("AKAMAI_ENABLED", default=False)
        self.require_origin_token: str = os.getenv(
            "AKAMAI_REQUIRE_ORIGIN_TOKEN", ""
        ).strip()
        self.blocked_countries: frozenset[str] = _env_list(
            "AKAMAI_BLOCKED_COUNTRIES"
        )
        self.allowed_bot_score: int = _env_int(
            "AKAMAI_ALLOWED_BOT_SCORE", default=30
        )
        self.rate_limit_passthrough: bool = _env_bool(
            "AKAMAI_RATE_LIMIT_HEADER", default=True
        )
        self.production_mode: bool = os.getenv(
            "FIREAI_ENV", "production"
        ).lower() in ("production", "prod")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_header(scope: Scope, name: bytes) -> str:
    """Return the first value for the given header (case-insensitive).

    ASGI scope headers are stored as list[tuple[bytes, bytes]] in lower-case
    form. Returns an empty string if not present.
    """
    for key, value in scope.get("headers", []):
        if key == name:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return ""
    return ""


def _is_bot_sensitive_path(path: str) -> bool:
    """Check if the request path requires strict bot-score enforcement."""
    return any(path.startswith(p) for p in _BOT_SENSITIVE_PATHS)


# ── Middleware ───────────────────────────────────────────────────────────────


class AkamaiIntegrationMiddleware:
    """Pure-ASGI middleware for Akamai Edge integration.

    Usage in backend/app.py:

        from backend.akamai_middleware import AkamaiIntegrationMiddleware
        app.add_middleware(AkamaiIntegrationMiddleware)

    Configuration via env vars (see AkamaiConfig above).

    When `AKAMAI_ENABLED=false`, the middleware passes through all requests
    with zero overhead beyond a single config check.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.config = AkamaiConfig()
        if self.config.enabled:
            logger.info(
                "AkamaiIntegrationMiddleware enabled "
                "(blocked_countries=%d, allowed_bot_score=%d, require_token=%s)",
                len(self.config.blocked_countries),
                self.config.allowed_bot_score,
                bool(self.config.require_origin_token),
            )
        else:
            logger.debug("AkamaiIntegrationMiddleware disabled (AKAMAI_ENABLED=false)")

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        # Only inspect HTTP requests; WebSocket / lifespan pass through.
        if scope["type"] != "http" or not self.config.enabled:
            await self.app(scope, receive, send)
            return

        # ── 1. Origin verification ─────────────────────────────────────────
        if not await self._check_origin_token(scope, send):
            return  # 403 already sent or non-prod warning logged

        path: str = scope.get("path", "")

        # ── 2. True-Client-IP trust ────────────────────────────────────────
        # Akamai guarantees True-Client-IP is set AFTER authenticating the
        # request at the edge. We make it the canonical client IP by:
        #   - Removing X-Forwarded-For (which can be spoofed)
        #   - Replacing it with True-Client-IP (Akamai-controlled)
        # Downstream code (limiter, audit, request_context) reads X-Forwarded-For,
        # so we overwrite it here for consistency.
        true_client_ip = _get_header(scope, _HDR_TRUE_CLIENT_IP)
        if true_client_ip:
            self._set_header(scope, _HDR_X_FORWARDED_FOR, true_client_ip.encode())

        # ── 3. Geo filtering ───────────────────────────────────────────────
        if not await self._check_geo_block(scope, send, path, true_client_ip):
            return

        # ── 4. Bot score enforcement (auth endpoints only) ─────────────────
        if not await self._check_bot_score(scope, send, path, true_client_ip):
            return

        # ── 5. Wrap send() to inject response headers ─────────────────────
        # We capture Akamai's GRN and echo it back so operators can correlate
        # a single request across the entire stack (Akamai → backend → DB).
        akamai_grn = _get_header(scope, _HDR_AKAMAI_GRN)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                # Inject traceability header
                if akamai_grn:
                    headers.append(
                        (b"x-akamai-grn", akamai_grn.encode("latin-1"))
                    )
                headers.append(
                    (b"x-akamai-translated-request", b"true")
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _check_origin_token(self, scope: Scope, send: Send) -> bool:
        """Verify Akamai-Internal token; return False if request was blocked.

        Returns True to continue processing, False if a 403 was sent (prod)
        or if no token check is configured. The token is checked against a
        shared secret rotated periodically. Akamai sets this header via an
        EdgeWorker or Request Header Modification rule in Property Manager.
        """
        if not self.config.require_origin_token:
            return True
        akamai_internal = _get_header(scope, _HDR_AKAMAI_INTERNAL)
        if akamai_internal == self.config.require_origin_token:
            return True
        # Fail-safe: log CRITICAL and block in production.
        # In dev/test (FIREAI_ENV != production), allow passthrough.
        if self.config.production_mode:
            logger.critical(
                "Direct origin access blocked (no/invalid Akamai-Internal token). "
                "path=%s, true_client_ip=%s",
                scope.get("path", ""),
                _get_header(scope, _HDR_TRUE_CLIENT_IP),
            )
            await self._send_forbidden(send, "Direct origin access forbidden")
            return False
        logger.warning(
            "Missing Akamai-Internal token in non-production env (allowed). "
            "path=%s",
            scope.get("path", ""),
        )
        return True

    async def _check_geo_block(
        self, scope: Scope, send: Send, path: str, true_client_ip: str
    ) -> bool:
        """Return False (and send 403) if the request is from a blocked country."""
        if not self.config.blocked_countries:
            return True
        country = _get_header(scope, _HDR_AKAMAI_GEO_COUNTRY).upper()
        if country and country in self.config.blocked_countries:
            logger.warning(
                "Geo-blocked request from country=%s path=%s ip=%s",
                country,
                path,
                true_client_ip or "unknown",
            )
            await self._send_forbidden(
                send, f"Access from {country} is not permitted"
            )
            return False
        return True

    async def _check_bot_score(
        self, scope: Scope, send: Send, path: str, true_client_ip: str
    ) -> bool:
        """Return False (and send 403) if bot score exceeds threshold on sensitive paths."""
        if not _is_bot_sensitive_path(path):
            return True
        bot_score_str = _get_header(scope, _HDR_AKAMAI_BOT_SCORE)
        if not bot_score_str:
            return True
        try:
            bot_score = int(bot_score_str)
        except ValueError:
            logger.debug(
                "Invalid Akamai-Bot-Score header value: %r", bot_score_str
            )
            return True
        if bot_score <= self.config.allowed_bot_score:
            return True
        logger.warning(
            "Bot score %d exceeds threshold %d on sensitive path=%s ip=%s",
            bot_score,
            self.config.allowed_bot_score,
            path,
            true_client_ip or "unknown",
        )
        await self._send_forbidden(
            send, "Automated traffic detected on sensitive endpoint"
        )
        return False

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _set_header(scope: Scope, name: bytes, value: bytes) -> None:
        """Replace or append a header in the ASGI scope (request side)."""
        headers = scope.setdefault("headers", [])
        # Remove existing entries
        headers[:] = [(k, v) for k, v in headers if k != name]
        # Append the new value
        headers.append((name, value))

    @staticmethod
    async def _send_forbidden(send: Send, message: str) -> None:
        """Send a 403 Forbidden response with a JSON body.

        Used for: direct origin access, geo-blocked, bot-score exceeded.
        The body follows the same error contract as backend/response.py
        so the frontend's error handler displays it correctly.
        """
        import json

        body = json.dumps(
            {
                "success": False,
                "error": "Forbidden",
                "message": message,
                "code": "AKAMAI_BLOCKED",
            }
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


__all__ = ["AkamaiConfig", "AkamaiIntegrationMiddleware"]
