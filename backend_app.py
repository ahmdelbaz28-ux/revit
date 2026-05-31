"""
FireAI Digital Twin — Main Application Entry Point
====================================================

Full-featured FastAPI application serving the Digital Twin REST API.

Mounts:
  - /api/projects     → Projects CRUD
  - /api/projects/:id/devices      → Devices CRUD
  - /api/projects/:id/connections  → Connections CRUD
  - /api/projects/:id/reports      → Reports
  - /api/projects/:id/export/*     → DXF, Revit, IFC exports
  - /api/projects/:id/sync         → Project sync
  - /api/health       → Health check
  - /ws               → WebSocket for real-time updates

Serves the frontend build from frontend/dist/ at the root path.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# ── Load .env file BEFORE any os.getenv() calls ────────────────────────────
# V68 FIX: Without python-dotenv, .env file is never read. GEMINI_API_KEY
# and other secrets would be unavailable, causing MemoryService to fail.
# load_dotenv() does NOT override existing env vars (safe for Docker/K8s).
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.is_file():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on OS env vars (Docker/K8s)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.request_context import CorrelationIdMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Security Audit Logging & Log Rotation ──────────────────────────────────
# SECURITY FIX (V100): Add structured security event logging with:
# 1. Dedicated security_audit.log (separate from application log)
# 2. Tamper-evident chain hashing for security events
# 3. Automatic sensitive data masking in all log output
# 4. Size-based log rotation (50 MB per file, 10 backups)
try:
    from fireai.core.security_logging import (
        SecurityEventType,
        configure_log_rotation,
        security_audit,
    )
    configure_log_rotation(logger, "fireai.log")
    configure_log_rotation(
        logging.getLogger("fireai.security_audit"),
        "security_audit.log",
    )
    _SECURITY_AUDIT_AVAILABLE = True
except ImportError:
    logger.warning("security_logging module not available — security audit disabled")
    _SECURITY_AUDIT_AVAILABLE = False

# ── Application lifecycle ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle.

    CRITICAL: We do NOT call db.close() on shutdown because:
    - get_db() returns a singleton stored in the _db module global
    - If uvicorn reloads (FIREAI_ENV=development), the global persists
      but the underlying SQLite connection would be closed
    - Subsequent requests would crash: "Cannot operate on a closed database"
    - SQLite WAL mode auto-checkpoints on its own; the OS flushes on process exit
    - For production Docker shutdown, the SIGTERM kills the process anyway
    """
    # Startup
    logger.info("FireAI Digital Twin API starting up...")

    # Initialize database (creates tables if needed)
    from backend.database import get_db
    get_db()  # Ensure singleton is created
    logger.info("Database initialized")

    # Initialize external API services (Phase 1 + Phase 2)
    from backend.services.weather_service import get_weather_service
    from backend.services.geocoding_service import get_geocoding_service
    from backend.services.region_service import get_region_service
    from backend.services.elevation_service import get_elevation_service
    from backend.services.air_quality_service import get_air_quality_service
    from backend.services.severe_weather_service import get_severe_weather_service
    from backend.services.hazmat_service import get_hazmat_service
    get_weather_service()
    get_geocoding_service()
    get_region_service()
    get_elevation_service()
    get_air_quality_service()
    get_severe_weather_service()
    get_hazmat_service()
    logger.info("External API services initialized (Open-Meteo, Nominatim, REST Countries, Open Topo Data, WAQI, NWS, Hazmat DB)")

    # Initialize workflow service (LangGraph-based pipeline engine)
    # V91 FIX (CF-1): Wrap in try/except — langgraph may not be installed.
    # The app should start even without the workflow engine.
    try:
        from backend.services.workflow_service import get_workflow_service
        svc = get_workflow_service()
        if svc._langgraph_available:
            logger.info("Workflow service initialized (LangGraph State Machine)")
        else:
            logger.warning("Workflow service in DEGRADED mode — LangGraph not installed")
    except ImportError as e:
        logger.warning(f"Workflow service not available: {e}. Workflow endpoints will return 503.")

    # Initialize memory service (Mem0-based long-term memory layer)
    # V91 FIX (CF-1): Wrap in try/except — mem0/qdrant may not be installed.
    try:
        from backend.services.memory_service import get_memory_service
        mem_svc = get_memory_service()
        if mem_svc.is_initialized:
            logger.info("Memory service initialized (Mem0 + Qdrant)")
        else:
            logger.warning(
                f"Memory service NOT initialized: {mem_svc.status.error}. "
                "Calculations proceed normally without memory context."
            )
    except ImportError as e:
        logger.warning(f"Memory service not available: {e}. Memory endpoints will return 503.")

    yield

    # Shutdown — close external API services (Phase 1 + Phase 2)
    from backend.services.weather_service import close_weather_service
    from backend.services.geocoding_service import close_geocoding_service
    from backend.services.region_service import close_region_service
    from backend.services.elevation_service import close_elevation_service
    from backend.services.air_quality_service import close_air_quality_service
    from backend.services.severe_weather_service import close_severe_weather_service
    from backend.services.hazmat_service import close_hazmat_service
    await close_weather_service()
    await close_geocoding_service()
    await close_region_service()
    await close_elevation_service()
    await close_air_quality_service()
    await close_severe_weather_service()
    await close_hazmat_service()
    logger.info("External API services closed (Phase 1 + Phase 2)")

    # Shutdown — close workflow service
    # V91 FIX (CF-1): Wrap in try/except — may not have been initialized
    try:
        from backend.services.workflow_service import close_workflow_service
        await close_workflow_service()
        logger.info("Workflow service closed")
    except ImportError:
        pass

    # Shutdown — close memory service
    try:
        from backend.services.memory_service import close_memory_service
        await close_memory_service()
        logger.info("Memory service closed")
    except ImportError:
        pass

    # Shutdown — do NOT close the singleton; it would break hot-reload
    logger.info("Shutting down... FireAI Digital Twin API stopped")


# ── Create FastAPI app ─────────────────────────────────────────────────────

app = FastAPI(
    title="FireAI Digital Twin API",
    description=(
        "REST API for the FireAI Digital Twin — a life-safety critical "
        "fire alarm engineering platform. Supports project management, "
        "device and connection CRUD, engineering reports, and BIM/CAD exports."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS middleware ────────────────────────────────────────────────────────
# SECURITY FIX (V100): Environment-aware CORS configuration.
# Production deployments use a hardcoded whitelist that cannot be overridden
# by environment variables. Development mode uses localhost-only defaults.

# Production whitelist — these origins are the ONLY ones allowed in production.
# To add a new production origin, you MUST modify this list and redeploy.
# This prevents misconfiguration via environment variables.
_PRODUCTION_TRUSTED_ORIGINS = [
    # Add your production domains here, e.g.:
    # "https://fireai.example.com",
    # "https://app.fireai.example.com",
]

# Development defaults — localhost only
_DEVELOPMENT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def _get_cors_origins() -> list:
    """Resolve CORS origins based on deployment environment.

    Security model:
    - Production (FIREAI_ENV=production or unset):
        Uses _PRODUCTION_TRUSTED_ORIGINS ONLY. If the list is empty,
        reads from CORS_ORIGINS env var (with wildcard rejection).
        This dual approach allows zero-code production deployment while
        still requiring explicit origin configuration.
    - Development (FIREAI_ENV=development):
        Uses localhost defaults. Additional origins can be added via
        CORS_ORIGINS env var for testing.
    - Wildcards (*) are ALWAYS rejected when allow_credentials=True.
    """
    env = os.getenv("FIREAI_ENV", "production")

    if env == "development":
        # Development: start with localhost defaults
        origins = list(_DEVELOPMENT_ORIGINS)
        # Allow additional origins from env var for testing
        extra = os.getenv("CORS_ORIGINS", "")
        if extra:
            for o in extra.split(","):
                o = o.strip()
                if o and o != "*" and o not in origins:
                    origins.append(o)
        logger.info(f"CORS: development mode — {len(origins)} origins configured")
        return origins

    # Production: use hardcoded whitelist if available
    if _PRODUCTION_TRUSTED_ORIGINS:
        logger.info(
            f"CORS: production mode — using hardcoded whitelist "
            f"({len(_PRODUCTION_TRUSTED_ORIGINS)} origins)"
        )
        return list(_PRODUCTION_TRUSTED_ORIGINS)

    # Production without hardcoded whitelist: require CORS_ORIGINS env var
    env_origins = os.getenv("CORS_ORIGINS", "")
    if not env_origins:
        logger.critical(
            "SECURITY: No CORS origins configured for production. "
            "Either populate _PRODUCTION_TRUSTED_ORIGINS in source code or "
            "set CORS_ORIGINS environment variable. No cross-origin requests "
            "will be allowed until this is resolved."
        )
        return []  # Fail-closed: no origins = no CORS

    origins = [o.strip() for o in env_origins.split(",") if o.strip()]

    # SECURITY: Reject wildcards in production
    if "*" in origins:
        logger.critical(
            "SECURITY: CORS_ORIGINS contains '*' wildcard in production. "
            "allow_credentials=True with wildcard origins is a security risk — "
            "any website can make authenticated cross-origin requests. "
            "Wildcard has been REMOVED. Specify explicit origins."
        )
        origins = [o for o in origins if o != "*"]

    # Validate all origins start with https:// in production
    for o in origins:
        if not o.startswith("https://") and not o.startswith("http://localhost"):
            logger.warning(
                f"SECURITY: CORS origin '{o}' does not use HTTPS. "
                f"Production origins should use HTTPS to prevent MITM attacks."
            )

    logger.info(f"CORS: production mode — {len(origins)} origins from env var")
    return origins


_cors_origins = _get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Client-Version",   # sent by digitalTwinApi.ts defaultHeaders on every request
        "X-Correlation-ID",   # sent by correlation middleware for end-to-end tracing
    ],
    expose_headers=["X-Correlation-ID"],  # allow frontend to read correlation IDs
)

# ── Security headers middleware ────────────────────────────────────────────
# Ported from the original project's nginx.conf security headers.
# These headers are mandatory for a safety-critical system exposed to the internet.

class SecurityHeadersMiddleware:
    """
    Pure ASGI middleware that adds security headers to every HTTP response.

    V91 FIX: Converted from BaseHTTPMiddleware to pure ASGI. BaseHTTPMiddleware
    reads the ENTIRE response body into memory before dispatch, defeating
    StreamingResponse used in export endpoints (DXF, IFC, Revit, reports).
    For large projects, this caused OOM crashes. Pure ASGI can add headers
    without consuming the body. Same pattern as CorrelationIdMiddleware.
    Per CF-2 fix and BUG-34 documentation in request_context.py.

    Source: Original FRONTEND-FIREAI project nginx.conf, adapted for FastAPI.
    Rationale:
      - X-Frame-Options: Prevents clickjacking on safety-critical UI
      - X-Content-Type-Options: Prevents MIME-sniffing attacks
      - X-XSS-Protection: Legacy XSS protection for older browsers
      - Referrer-Policy: Limits information leakage in referrer headers
      - Permissions-Policy: Denies access to unnecessary browser APIs
      - Content-Security-Policy: Restricts resource loading to trusted sources
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # V91 FIX (AD-3): Derive CSP connect-src from CORS_ORIGINS env var.
        # Previous code hardcoded localhost only, breaking production HTTPS/WSS.
        cors_origins_csp = os.getenv(
            "CSP_CONNECT_ORIGINS",
            " ".join(
                origin.replace("http://", "").replace("https://", "")
                for origin in _cors_origins
            ),
        )
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            f"connect-src 'self' {cors_origins_csp}; "
            "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
            "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com;"
        )

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-frame-options", b"SAMEORIGIN"))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-xss-protection", b"1; mode=block"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                headers.append((b"permissions-policy", b"camera=(), microphone=(), geolocation=()"))
                headers.append((b"content-security-policy", csp.encode("utf-8")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


app.add_middleware(SecurityHeadersMiddleware)

# ── API Key Authentication Middleware ──────────────────────────────────────
# Safety-critical system: ALL mutating endpoints (POST, PUT, DELETE, PATCH)
# require X-API-Key header matching FIREAI_API_KEY env var.
# GET requests are allowed without auth for read-only access.
# If FIREAI_API_KEY is not set, auth is disabled (development mode only).

_FIREAI_API_KEY = os.getenv("FIREAI_API_KEY")

# ── Secret rotation integration ────────────────────────────────────────────
# Wire the KeyRotator into the API key lifecycle.  When KeyRotator is
# available, the middleware uses its validate() method which accepts both
# the current key AND any grace-period key.  This enables zero-downtime
# key rotation in multi-worker deployments.
_key_rotator = None
try:
    from fireai.core.secret_rotation import key_rotator as _key_rotator_singleton
    _key_rotator = _key_rotator_singleton
    # Register the current API key with the rotator so validate() works
    if _FIREAI_API_KEY and _key_rotator is not None:
        _key_rotator.register("FIREAI_API_KEY", _FIREAI_API_KEY)
    logger.info("KeyRotator integrated with API key middleware")
except ImportError:
    logger.debug("secret_rotation module not available — key rotation disabled")

# V92 FIX (SS-3): Warn loudly if FIREAI_API_KEY is explicitly set to empty in production.
# An empty string passes `not _FIREAI_API_KEY` check (disabling auth) but the
# operator may have intended to set a key. Without this warning, a misconfigured
# FIREAI_API_KEY= (empty) silently disables all mutation auth.
if os.getenv("FIREAI_API_KEY") is not None and _FIREAI_API_KEY == "":
    if os.getenv("FIREAI_ENV", "production") != "development":
        logger.critical(
            "SECURITY: FIREAI_API_KEY is explicitly set to empty string. "
            "API key authentication is DISABLED for all mutating endpoints. "
            "This is a safety risk — unauthorized modifications to fire alarm "
            "designs are possible. Either set a non-empty key or remove the "
            "environment variable entirely."
        )
    else:
        logger.warning(
            "FIREAI_API_KEY is set to empty string — auth disabled (development mode only)"
        )

# SECURITY FIX: Detect placeholder API keys from .env.example.
# Common placeholder values like "change-me-in-production" pass the non-empty
# check but provide ZERO actual security — they are trivially guessable.
_PLACEHOLDER_API_KEYS = frozenset({
    "change-me-in-production",
    "changeme",
    "placeholder",
    "test",
    "dev",
    "development",
    "example",
    "secret",
    "password",
    "your-api-key-here",
})
if _FIREAI_API_KEY and _FIREAI_API_KEY.lower() in _PLACEHOLDER_API_KEYS:
    logger.critical(
        "SECURITY: FIREAI_API_KEY is set to a known placeholder value "
        f"'{_FIREAI_API_KEY}'. This provides NO security — the key is "
        "trivially guessable. Generate a random key with: "
        "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
    # V102 FIX: Refuse to start in production with a placeholder API key.
    # In a safety-critical system, running with no effective auth means
    # unauthorized modification of fire alarm designs is possible.
    if os.getenv("FIREAI_ENV", "production") != "development":
        raise RuntimeError(
            f"SECURITY: FIREAI_API_KEY is set to placeholder '{_FIREAI_API_KEY}'. "
            "Application REFUSES to start in production mode with a placeholder key. "
            "Generate a strong key: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    if _SECURITY_AUDIT_AVAILABLE:
        security_audit.log_event(
            SecurityEventType.PLACEHOLDER_KEY_DETECTED,
            key_type="FIREAI_API_KEY",
            # V102 FIX: Don't log the actual key value — only a hint
            placeholder_hint=_FIREAI_API_KEY[:4] + "..." if len(_FIREAI_API_KEY) > 4 else "***",
        )

class ApiKeyMiddleware:
    """
    Pure ASGI middleware that validates X-API-Key header on mutating requests.

    V91 FIX: Converted from BaseHTTPMiddleware to pure ASGI. BaseHTTPMiddleware
    reads the ENTIRE response body into memory, defeating StreamingResponse
    used in export endpoints. Same pattern as CorrelationIdMiddleware and
    SecurityHeadersMiddleware. Per CF-2 fix.

    In a life-safety engineering system, unauthorized modification of
    detector placement or circuit calculations is a safety hazard.
    This middleware ensures only authorized clients can modify data.

    Same-origin requests (from the SPA frontend served by this app)
    are always allowed — the API key is only required for external
    API consumers (third-party scripts, CLI tools, etc.).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # For WebSocket, always pass through
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        # Extract method from scope
        method = scope.get("method", "GET")

        # Skip auth for read-only methods
        if method in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        # If no API key is configured, allow all (dev mode)
        if not _FIREAI_API_KEY:
            await self.app(scope, receive, send)
            return

        # Parse headers from scope
        headers_dict = {}
        for key, value in scope.get("headers", []):
            headers_dict[key.decode("latin-1").lower()] = value.decode("latin-1")

        origin = headers_dict.get("origin", "")
        host = headers_dict.get("host", "")

        # V102 FIX: REMOVED the same-origin bypass. Previously, if the
        # Origin header matched the Host header, the API key was SKIPPED
        # entirely. This is a CRITICAL vulnerability because the Origin
        # header is client-controlled and trivially spoofed — an attacker
        # can set Origin: http://<victim-host> to bypass ALL mutation auth.
        #
        # The SPA frontend MUST now send the X-API-Key header with every
        # mutating request, even same-origin ones. This is the correct
        # security model for a safety-critical system.
        #
        # Development mode still allows CORS-origin bypass for convenience,
        # but requires FIREAI_ENV=development explicitly.

        # In development mode, trust common dev origins (no API key needed)
        if os.getenv("FIREAI_ENV") == "development" and origin:
            if origin in (
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                f"http://{host}",
                f"https://{host}",
            ):
                await self.app(scope, receive, send)
                return

        # All other requests — require API key
        import hmac
        api_key = headers_dict.get("x-api-key", "")

        # Use KeyRotator.validate() when available — it checks both the
        # current key AND any grace-period key from a recent rotation.
        # Falls back to direct comparison when rotator is not integrated.
        key_valid = False
        if _key_rotator is not None and _FIREAI_API_KEY:
            try:
                key_valid = _key_rotator.validate("FIREAI_API_KEY", api_key)
            except Exception:
                # KeyRotator should never crash auth — fall back to direct
                key_valid = hmac.compare_digest(api_key, _FIREAI_API_KEY)
        elif _FIREAI_API_KEY:
            key_valid = hmac.compare_digest(api_key, _FIREAI_API_KEY)

        if not key_valid:
            path = scope.get("path", "?")
            client = scope.get("client")
            client_addr = f"{client[0]}:{client[1]}" if client else "unknown"
            logger.warning(
                f"Unauthorized {method} request to {path} "
                f"from origin={origin or 'none'} client={client_addr}"
            )
            # Log to security audit
            if _SECURITY_AUDIT_AVAILABLE:
                security_audit.log_event(
                    SecurityEventType.AUTH_FAILURE,
                    method=method,
                    path=path,
                    origin=origin or "none",
                    client_ip=client_addr,
                )
            # Send 401 response directly via ASGI
            body = b'{"success":false,"error":"Invalid or missing X-API-Key header"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        await self.app(scope, receive, send)


app.add_middleware(ApiKeyMiddleware)

# ── Rate limiting ──────────────────────────────────────────────────────
# V101 FIX: Replaced dual slowapi + InMemoryRateLimiter approach with a
# single, path-aware ASGI middleware.  The previous approach had two
# problems: (1) slowapi was initialized but no routes had @limiter.limit()
# decorators, making it inert dead code; (2) the InMemoryRateLimiter had
# a single global rate for ALL endpoints, which is too coarse.
#
# The new PerPathRateLimitMiddleware enforces different limits per path
# prefix, so that expensive external API calls (weather, geocoding, AI)
# get stricter limits than cheap internal operations.
#
# In production with multiple workers, replace the in-memory counters
# with a Redis-backed store.  For single-worker deployments (which is
# the typical FireAI deployment), this is sufficient.

import time as _time
from collections import defaultdict as _defaultdict

# Per-path rate limit configuration.
# Format: (path_prefix, max_requests, window_seconds)
# More specific prefixes should come first (longest-prefix match).
_PER_PATH_LIMITS = [
    # External API proxies — strict limits to respect upstream rate limits
    ("/api/environment/weather",     10, 60),   # Open-Meteo: 10/min
    ("/api/environment/geocoding",    1,  1),   # Nominatim:  1/sec
    ("/api/environment/elevation",   10, 60),   # Open Topo Data: 10/min
    ("/api/environment/air-quality", 10, 60),   # WAQI: 10/min
    ("/api/environment/severe",      10, 60),   # NWS: 10/min
    ("/api/environment/hazmat",      30, 60),   # Local DB: 30/min
    ("/api/environment/region",      10, 60),   # REST Countries: 10/min
    # AI/LLM endpoints — moderate limits
    # V103 FIX: Added explicit Gemini rate limit (60/min) per the security
    # audit. Gemini is accessed through the memory service endpoint and has
    # its own upstream API limit. 60/min is generous for engineering queries
    # while preventing abuse that could exhaust the API quota.
    ("/api/workflow",                10, 60),   # LangGraph: 10/min
    ("/api/memory/gemini",           60, 60),   # Gemini API: 60/min
    ("/api/memory",                  30, 60),   # Mem0: 30/min (general)
    # Mutating endpoints — moderate limits (safety-critical)
    ("/api/projects",               30, 60),   # CRUD: 30/min
    # Analysis engine — CPU-intensive
    ("/api/analyze",                 10, 60),   # 10/min
    ("/api/qomn",                    10, 60),   # 10/min
]

_DEFAULT_RATE_LIMIT = (120, 60)  # 120 requests per 60 seconds for unmatched paths


class PerPathRateLimitMiddleware:
    """
    ASGI middleware that enforces per-IP, per-path-prefix rate limits.

    This replaces both the inert slowapi initialization and the previous
    single-global-limit InMemoryRateLimitMiddleware.  Each path prefix
    gets its own rate limit counter, so that external API calls are
    throttled more aggressively than internal operations.

    Thread-safe: uses a lock for the counters dictionary.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Key: (ip, path_prefix) -> [timestamps]
        self._counts: dict = _defaultdict(list)
        self._lock = __import__("threading").Lock()

        # Also allow override via env var for the default limit
        _rate_str = os.getenv("FIREAI_RATE_LIMIT", "120/1")
        try:
            parts = _rate_str.split("/")
            self._default_max = int(parts[0])
            self._default_window = int(parts[1]) * 60 if len(parts) > 1 else 60
        except (ValueError, IndexError):
            logger.warning(f"Invalid FIREAI_RATE_LIMIT '{_rate_str}', using default 120/1min")
            self._default_max = 120
            self._default_window = 60

        # Log the per-path limits at startup
        for prefix, max_req, window in _PER_PATH_LIMITS:
            logger.info(f"Rate limit: {prefix} → {max_req}/{window}s")
        logger.info(f"Rate limit: (default) → {self._default_max}/{self._default_window}s")

    def _find_limit(self, path: str) -> tuple:
        """Find the rate limit for a path (longest-prefix match)."""
        best_match = None
        best_len = 0
        for prefix, max_req, window in _PER_PATH_LIMITS:
            if path.startswith(prefix) and len(prefix) > best_len:
                best_match = (max_req, window)
                best_len = len(prefix)
        return best_match if best_match else (self._default_max, self._default_window)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract client IP with X-Forwarded-For support.
        # V104 FIX (HIGH): Behind reverse proxies (nginx, Cloudflare, AWS ALB),
        # ALL users share the proxy's IP. One user can exhaust the rate limit
        # for EVERY user behind the same proxy. We now check X-Forwarded-For
        # when the direct client IP is in _TRUSTED_PROXY_NETWORKS.
        client = scope.get("client")
        direct_ip = client[0] if client else "unknown"

        # Parse headers for X-Forwarded-For
        headers_dict = {}
        for key, value in scope.get("headers", []):
            headers_dict[key.decode("latin-1").lower()] = value.decode("latin-1")

        ip = direct_ip
        forwarded_for = headers_dict.get("x-forwarded-for", "")
        real_ip = headers_dict.get("x-real-ip", "")

        # Only trust forwarding headers from known proxy IPs/networks.
        # This prevents IP spoofing by end clients.
        _TRUSTED_PROXIES = frozenset({
            "127.0.0.1", "::1",
            # Add your reverse proxy IPs here, e.g.:
            # "10.0.0.1", "172.16.0.1",
        })
        # Also trust private network ranges (10.x, 172.16-31.x, 192.168.x)
        _is_private = (
            direct_ip.startswith("10.")
            or direct_ip.startswith("192.168.")
            or (
                direct_ip.startswith("172.")
                and 16 <= int(direct_ip.split(".")[1]) <= 31
            )
        )

        if direct_ip in _TRUSTED_PROXIES or _is_private:
            if forwarded_for:
                # X-Forwarded-For: client, proxy1, proxy2
                # The leftmost IP is the original client
                ip = forwarded_for.split(",")[0].strip()
            elif real_ip:
                ip = real_ip.strip()

        path = scope.get("path", "/")

        # Find the applicable rate limit for this path
        max_requests, window_seconds = self._find_limit(path)

        # V104 FIX (MEDIUM): Use longest-prefix match for group selection
        # (same algorithm as _find_limit). Previous code used first-match,
        # which caused incorrect counter sharing between overlapping prefixes.
        group = None
        best_group_len = 0
        for prefix, _, _ in _PER_PATH_LIMITS:
            if path.startswith(prefix) and len(prefix) > best_group_len:
                group = prefix
                best_group_len = len(prefix)
        if group is None:
            group = "_default"
        counter_key = (ip, group)

        now = _time.monotonic()
        with self._lock:
            # Remove expired timestamps
            self._counts[counter_key] = [
                t for t in self._counts[counter_key]
                if now - t < window_seconds
            ]
            # Check if rate limit exceeded
            if len(self._counts[counter_key]) >= max_requests:
                # Log to security audit
                if _SECURITY_AUDIT_AVAILABLE:
                    security_audit.log_event(
                        SecurityEventType.RATE_LIMIT_EXCEEDED,
                        client_ip=ip,
                        path=path,
                        limit=f"{max_requests}/{window_seconds}s",
                    )
                response = Response(
                    content=json.dumps({
                        "success": False,
                        "error": "Rate limit exceeded",
                        "detail": f"Maximum {max_requests} requests per {window_seconds}s for {group}",
                        "status_code": 429,
                    }),
                    status_code=429,
                    media_type="application/json",
                )
                await response(scope, receive, send)
                return
            # Record this request
            self._counts[counter_key].append(now)

        await self.app(scope, receive, send)

app.add_middleware(PerPathRateLimitMiddleware)

# ── Correlation ID middleware ──────────────────────────────────────────
# Added LAST so it runs FIRST (Starlette middleware runs in reverse order).
# Every request/response gets an X-Correlation-ID header for end-to-end tracing.

app.add_middleware(CorrelationIdMiddleware)

# ── Global exception handler ──────────────────────────────────────────────
# Safety-critical system: ALL errors must return structured JSON responses.
# Unhandled exceptions must NEVER leak stack traces to the client in production.
# They must be logged server-side and return a generic 500 to the client.

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Return structured JSON for all HTTP exceptions."""
    # Preserve the original detail format for validation errors from FastAPI
    detail = exc.detail
    if isinstance(detail, dict):
        # Already structured (e.g., from our routers)
        return Response(
            content=json.dumps(detail),
            status_code=exc.status_code,
            media_type="application/json",
        )
    return Response(
        content=json.dumps({
            "success": False,
            "error": str(detail),
            "status_code": exc.status_code,
        }),
        status_code=exc.status_code,
        media_type="application/json",
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured JSON for request validation errors."""
    errors = []
    for err in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    logger.warning(f"Validation error on {request.method} {request.url.path}: {errors}")
    return Response(
        content=json.dumps({
            "success": False,
            "error": "Request validation failed",
            "details": errors,
            "status_code": 422,
        }),
        status_code=422,
        media_type="application/json",
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — prevent stack trace leakage."""
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: "
        f"{type(exc).__name__}: {exc}",
        exc_info=True,
    )
    is_dev = os.getenv("FIREAI_ENV") == "development"
    error_detail = f"{type(exc).__name__}: {exc}" if is_dev else "Internal server error"
    return Response(
        content=json.dumps({
            "success": False,
            "error": error_detail,
            "status_code": 500,
        }),
        status_code=500,
        media_type="application/json",
    )

# ── Import and mount routers ───────────────────────────────────────────────

from backend.routers import projects, devices, connections, reports, exports, sync, health, elements, conflicts, connections_v2, environment, workflow, memory
from backend.routers.analyze import router as analyze_router, project_router as analyze_project_router
from backend.routers.qomn import router as qomn_router

# Health check at /api/health
app.include_router(health.router, prefix="/api")

# Project management at /api/projects
app.include_router(projects.router, prefix="/api")

# Device management at /api/projects/:id/devices
app.include_router(devices.router, prefix="/api")

# Connection management at /api/projects/:id/connections
app.include_router(connections.router, prefix="/api")

# Report generation at /api/projects/:id/reports
app.include_router(reports.router, prefix="/api")

# Export endpoints at /api/projects/:id/export/*
app.include_router(exports.router, prefix="/api")

# Sync endpoints at /api/projects/:id/sync
app.include_router(sync.router, prefix="/api")

# Element CRUD at /api/elements (UniversalDataModel-backed)
app.include_router(elements.router)

# Conflict detection/resolution at /api/conflicts
app.include_router(conflicts.router)

# Relationship-based connections at /api/connections (UniversalDataModel)
app.include_router(connections_v2.router)

# Environmental data at /api/environment (weather, geocoding, regulatory)
app.include_router(environment.router, prefix="/api")

# Workflow engine at /api/workflow (LangGraph State Machine)
app.include_router(workflow.router, prefix="/api")

# Memory layer at /api/memory (Mem0-based long-term memory)
app.include_router(memory.router, prefix="/api")

# NFPA 72 analysis engine — standalone calculations
app.include_router(analyze_router, prefix="/api")

# NFPA 72 analysis engine — per-project analysis
app.include_router(analyze_project_router, prefix="/api")

# QOMN-FIRE Deterministic Engineering Kernel — Layer 0-4 pipeline
# Endpoints: /api/qomn/* — smoke spacing, heat spacing, battery, voltage drop,
# device placement, duct detection, audit log, physics guards, golden tests
app.include_router(qomn_router, prefix="/api")

# WebSocket at /ws
app.include_router(sync.ws_router)

# ── Root endpoint (API info) ──────────────────────────────────────────────

# Only add the API-info root endpoint when there is no frontend build.
# When frontend/dist exists, the SPA catch-all serves index.html at /.
if not (Path(__file__).resolve().parent.parent / "frontend" / "dist").is_dir():
    @app.get("/")
    async def root():
        """Root endpoint — API information (only when no frontend build)."""
        return {
            "message": "FireAI Digital Twin API",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
            "health": "/api/health",
        }


# ── Serve frontend build (production mode) ─────────────────────────────────

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    # Mount static assets
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="static-assets",
    )

    # Serve index.html for SPA routing
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        Serve the SPA index.html for all non-API, non-WS routes.
        This enables client-side routing.

        V90 SECURITY FIX: Validate resolved path stays within _FRONTEND_DIST.
        Without this check, an attacker can use path traversal (e.g., ../)
        to read arbitrary files on the server. In a safety-critical system,
        this could expose API keys, database contents, or engineering data.
        Per agent.md Priority 8 (Security) and Rule 1 (Absolute Truth).
        """
        # Don't intercept API or WebSocket routes — return proper 404
        if full_path.startswith("api/") or full_path == "ws":
            raise HTTPException(status_code=404, detail="Not found")
        # Try to serve a real file first
        file_path = _FRONTEND_DIST / full_path
        # V90 SECURITY: Verify resolved path is within the frontend dist directory.
        # Prevents path traversal via ../ or symlinks.
        resolved_path = file_path.resolve()
        resolved_dist = _FRONTEND_DIST.resolve()
        if not str(resolved_path).startswith(str(resolved_dist) + os.sep) and resolved_path != resolved_dist:
            raise HTTPException(status_code=403, detail="Access denied")
        if resolved_path.is_file():
            return FileResponse(str(resolved_path))
        # Fallback to index.html for SPA routing
        index_path = _FRONTEND_DIST / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Not found")

    logger.info(f"Frontend build served from {_FRONTEND_DIST}")
else:
    logger.info(
        f"Frontend build not found at {_FRONTEND_DIST}. "
        "Run 'npm run build' in frontend/ to serve the SPA."
    )


# ── Core module compatibility ─────────────────────────────────────────────

# Try to load core modules for NFPA 72 calculations (optional)
_core_loaded = False
try:
    from core.database import UniversalDataModel  # noqa: F401
    _core_loaded = True
    logger.info("Core modules loaded successfully")
except ImportError as e:
    logger.warning(f"Core modules not loaded: {e}. NFPA 72 calculations unavailable.")
except Exception as e:
    # Catch ALL exceptions — a broken core module must NOT crash the API server.
    # The Digital Twin API must remain available for frontend connectivity.
    logger.error(
        f"Core module load failed with unexpected error: {type(e).__name__}: {e}",
        exc_info=True,
    )
    _core_loaded = False

# Update health router with core module status
from backend.routers.health import set_core_modules_loaded
set_core_modules_loaded(_core_loaded)


# ── Direct execution ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        reload=os.getenv("FIREAI_ENV") == "development",
        log_level="info",
    )
