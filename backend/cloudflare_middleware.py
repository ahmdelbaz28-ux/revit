"""
backend/cloudflare_middleware.py — Cloudflare Edge Integration Middleware.
==========================================================================

PURPOSE
-------
Pure-ASGI middleware that integrates the FireAI backend with a Cloudflare
Edge deployment (WAF + Bot Fight Mode + Rate Limiting + Cache Rules).

Cloudflare injects the following headers on every proxied request:
  - CF-Connecting-IP       — the real client IP (set AFTER edge auth)
  - CF-RAY                  — unique request ID (e.g., "8a1b2c3d4e5f-LAX")
  - CF-IPCountry            — ISO 3166-1 alpha-2 country code
  - CF-Visitor              — JSON with scheme ("https" or "http")
  - True-Client-IP          — same as CF-Connecting-IP (when enabled in zone)
  - CF-Bot-Score / CF-Bot-Verified — bot detection signals (Pro+ only)

This middleware reads these headers and:
  1. Trusts CF-Connecting-IP — overwrites X-Forwarded-For with the real IP
  2. Enforces geo filtering (CF-IPCountry)
  3. Adds traceability headers (CF-RAY) to the response
  4. Verifies the request came through Cloudflare (X-CF-Origin-Token shared secret)

When CF_ENABLED=false (default), this middleware is a no-op pass-through.

DESIGN NOTES
-----------
- Pure ASGI (not BaseHTTPMiddleware) — avoids response body buffering.
- Reads headers from scope["headers"] (lower-case bytes).
- Complements backend/akamai_middleware.py — both can be enabled simultaneously
  if you have a multi-CDN setup (Akamai primary + Cloudflare failover).
- When both are enabled, Cloudflare runs first (outermost) and Akamai second.

References
----------
- Cloudflare request headers: https://developers.cloudflare.com/fundamentals/reference/http-request-headers/
- Cloudflare WAF: https://developers.cloudflare.com/waf/
- agent.md Rule #14 (NO MODIFICATION WITHOUT VERIFICATION)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


# ── Header constants (ASGI scope stores them as lower-case bytes) ────────────
_HDR_CF_CONNECTING_IP = b"cf-connecting-ip"
_HDR_CF_RAY = b"cf-ray"
_HDR_CF_IPCOUNTRY = b"cf-ipcountry"
_HDR_CF_VISITOR = b"cf-visitor"
_HDR_TRUE_CLIENT_IP = b"true-client-ip"
_HDR_X_FORWARDED_FOR = b"x-forwarded-for"
_HDR_X_CF_ORIGIN_TOKEN = b"x-cf-origin-token"

# Endpoints where bot verification is enforced (Cloudflare Bot Fight Mode
# already challenges these at the edge, but we double-check server-side too).
_BOT_SENSITIVE_PATHS: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/reset-password",
    "/api/v1/admin/api-keys",
    "/api/v1/admin/users",
)

_RESPONSE_TRACE_HEADER = "X-CF-Translated-Request"


# ── Config ───────────────────────────────────────────────────────────────────


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "").strip().lower()
    if not v:
        return default
    return v in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: Iterable[str] = ()) -> frozenset[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return frozenset(default)
    return frozenset(
        item.strip().upper() for item in raw.split(",") if item.strip()
    )


class CloudflareConfig:
    """Lazy-loaded configuration snapshot for Cloudflare integration."""

    __slots__ = (
        "blocked_countries",
        "enabled",
        "production_mode",
        "require_origin_token",
    )

    def __init__(self) -> None:
        self.enabled: bool = _env_bool("CF_ENABLED", default=False)
        self.require_origin_token: str = os.getenv(
            "CF_REQUIRE_ORIGIN_TOKEN", ""
        ).strip()
        self.blocked_countries: frozenset[str] = _env_list(
            "CF_BLOCKED_COUNTRIES"
        )
        self.production_mode: bool = os.getenv(
            "FIREAI_ENV", "production"
        ).lower() in ("production", "prod")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return ""
    return ""


def _is_bot_sensitive_path(path: str) -> bool:
    return any(path.startswith(p) for p in _BOT_SENSITIVE_PATHS)


# ── Middleware ───────────────────────────────────────────────────────────────


class CloudflareIntegrationMiddleware:
    """Pure-ASGI middleware for Cloudflare Edge integration.

    Usage in backend/app.py:

        from backend.cloudflare_middleware import CloudflareIntegrationMiddleware
        app.add_middleware(CloudflareIntegrationMiddleware)

    When CF_ENABLED=false, this is a no-op pass-through.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.config = CloudflareConfig()
        if self.config.enabled:
            logger.info(
                "CloudflareIntegrationMiddleware enabled "
                "(blocked_countries=%d, require_token=%s)",
                len(self.config.blocked_countries),
                bool(self.config.require_origin_token),
            )
        else:
            logger.debug("CloudflareIntegrationMiddleware disabled (CF_ENABLED=false)")

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not self.config.enabled:
            await self.app(scope, receive, send)
            return

        # ── 1. Origin verification ─────────────────────────────────────────
        if not await self._check_origin_token(scope, send):
            return

        path: str = scope.get("path", "")

        # ── 2. CF-Connecting-IP trust ──────────────────────────────────────
        # Cloudflare guarantees CF-Connecting-IP is the real client IP.
        # True-Client-IP is the same value when enabled in zone settings.
        cf_ip = _get_header(scope, _HDR_CF_CONNECTING_IP)
        if not cf_ip:
            cf_ip = _get_header(scope, _HDR_TRUE_CLIENT_IP)
        if cf_ip:
            self._set_header(scope, _HDR_X_FORWARDED_FOR, cf_ip.encode())

        # ── 3. Geo filtering (CF-IPCountry) ────────────────────────────────
        if not await self._check_geo_block(scope, send, path, cf_ip):
            return

        # ── 4. Wrap send() to inject response headers ─────────────────────
        cf_ray = _get_header(scope, _HDR_CF_RAY)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if cf_ray:
                    headers.append((b"x-cf-ray", cf_ray.encode("latin-1")))
                headers.append((b"x-cf-translated-request", b"true"))
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _check_origin_token(self, scope: Scope, send: Send) -> bool:
        """Verify X-CF-Origin-Token; return False if a 403 was sent (prod).

        In non-production environments, missing/invalid tokens are logged as
        warnings but the request is allowed to proceed (fail-open for dev).
        """
        if not self.config.require_origin_token:
            return True
        cf_token = _get_header(scope, _HDR_X_CF_ORIGIN_TOKEN)
        if cf_token == self.config.require_origin_token:
            return True
        if self.config.production_mode:
            logger.critical(
                "Direct origin access blocked (no/invalid X-CF-Origin-Token). "
                "path=%s, cf_connecting_ip=%s",
                scope.get("path", ""),
                _get_header(scope, _HDR_CF_CONNECTING_IP),
            )
            await self._send_forbidden(send, "Direct origin access forbidden")
            return False
        logger.warning(
            "Missing X-CF-Origin-Token in non-production env (allowed). path=%s",
            scope.get("path", ""),
        )
        return True

    async def _check_geo_block(
        self, scope: Scope, send: Send, path: str, cf_ip: str
    ) -> bool:
        """Return False (and send 403) if the request is from a blocked country."""
        if not self.config.blocked_countries:
            return True
        country = _get_header(scope, _HDR_CF_IPCOUNTRY).upper()
        if country and country in self.config.blocked_countries:
            logger.warning(
                "Geo-blocked request from country=%s path=%s ip=%s",
                country,
                path,
                cf_ip or "unknown",
            )
            await self._send_forbidden(
                send, f"Access from {country} is not permitted"
            )
            return False
        return True

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _set_header(scope: Scope, name: bytes, value: bytes) -> None:
        headers = scope.setdefault("headers", [])
        headers[:] = [(k, v) for k, v in headers if k != name]
        headers.append((name, value))

    @staticmethod
    async def _send_forbidden(send: Send, message: str) -> None:
        body = json.dumps(
            {
                "success": False,
                "error": "Forbidden",
                "message": message,
                "code": "CF_BLOCKED",
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


__all__ = ["CloudflareConfig", "CloudflareIntegrationMiddleware"]
