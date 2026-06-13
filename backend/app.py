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
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List

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

import hmac

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

# C-1 FIX: Removed BaseHTTPMiddleware import — all custom middleware converted
# to pure ASGI to fix StreamingResponse buffering issue. BaseHTTPMiddleware's
# await call_next() reads the ENTIRE response body into memory, breaking
# StreamingResponse for large DXF/IFC/PDF exports (OOM + timeout).
from backend.request_context import CorrelationIdMiddleware

# H-6 FIX: Read log level from environment instead of hardcoding INFO.
# Docker sets LOG_LEVEL=WARNING but basicConfig was overriding it.
_log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Startup environment validation ─────────────────────────────────────────

_ENV = os.getenv("FIREAI_ENV", "production")
if _ENV == "production":
    _required = ["FIREAI_API_KEY"]
    _missing = [k for k in _required if not os.getenv(k)]
    if _missing:
        # C-4 FIX: Fail-fast in production instead of silently continuing.
        # A safety-critical system with no API key gives a false sense of
        # security — reads succeed but all writes silently fail (503).
        logger.critical(
            "FATAL: Missing required environment variables in production mode: %s. "
            "Refusing to start — set these variables before deploying.",
            ", ".join(_missing),
        )
        import sys
        sys.exit(1)

# ── Security Audit Logging & Log Rotation ──────────────────────────────────
# V100+V105: Structured security event logging with tamper-evident chain
# hashing, sensitive data masking, and size-based log rotation.
try:
    from fireai.core.security_logging import (
        configure_log_rotation,
    )

    configure_log_rotation(logger, "fireai.log")
except ImportError:
    logger.warning("security_logging module not available — security audit disabled")

# ── Optional router availability flags (set BEFORE lifespan) ──────────────

WORKFLOW_ROUTER_AVAILABLE: bool = False
MEMORY_ROUTER_AVAILABLE: bool = False

try:
    from backend.routers import workflow
    WORKFLOW_ROUTER_AVAILABLE = True
except ImportError:
    pass

try:
    from backend.routers import memory
    MEMORY_ROUTER_AVAILABLE = True
except ImportError:
    pass


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
    from backend.services.air_quality_service import get_air_quality_service
    from backend.services.elevation_service import get_elevation_service
    from backend.services.geocoding_service import get_geocoding_service
    from backend.services.hazmat_service import get_hazmat_service
    from backend.services.region_service import get_region_service
    from backend.services.severe_weather_service import get_severe_weather_service
    from backend.services.weather_service import get_weather_service

    get_weather_service()
    get_geocoding_service()
    get_region_service()
    get_elevation_service()
    get_air_quality_service()
    get_severe_weather_service()
    get_hazmat_service()
    logger.info(
        "External API services initialized (Open-Meteo, Nominatim, REST Countries, Open Topo Data, WAQI, NWS, Hazmat DB)"
    )

    # Initialize workflow service (LangGraph-based pipeline engine)
    # V91 FIX: Wrap in try/except — langgraph may not be installed.
    try:
        from backend.services.workflow_service import get_workflow_service

        svc = get_workflow_service()
        if hasattr(svc, "_langgraph_available") and svc._langgraph_available:
            logger.info("Workflow service initialized (LangGraph State Machine)")
        elif hasattr(svc, "is_initialized") and svc.is_initialized:
            logger.info("Workflow service initialized (LangGraph available)")
        else:
            logger.warning("Workflow service in DEGRADED mode — LangGraph not installed")
    except ImportError as e:
        logger.warning(f"Workflow service not available: {e}. Workflow endpoints will return 503.")

    # Initialize memory service (Mem0-based long-term memory layer)
    # V91 FIX: Wrap in try/except — mem0/qdrant may not be installed.
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
    from backend.services.air_quality_service import close_air_quality_service
    from backend.services.elevation_service import close_elevation_service
    from backend.services.geocoding_service import close_geocoding_service
    from backend.services.hazmat_service import close_hazmat_service
    from backend.services.region_service import close_region_service
    from backend.services.severe_weather_service import close_severe_weather_service
    from backend.services.weather_service import close_weather_service

    await close_weather_service()
    await close_geocoding_service()
    await close_region_service()
    await close_elevation_service()
    await close_air_quality_service()
    await close_severe_weather_service()
    await close_hazmat_service()
    logger.info("External API services closed (Phase 1 + Phase 2)")

    # Shutdown — close workflow service (if available)
    if WORKFLOW_ROUTER_AVAILABLE:
        from backend.services.workflow_service import close_workflow_service
        await close_workflow_service()
        logger.info("Workflow service closed")

    # Shutdown — close memory service (if available)
    if MEMORY_ROUTER_AVAILABLE:
        from backend.services.memory_service import close_memory_service
        await close_memory_service()
        logger.info("Memory service closed")

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

# V110 FIX: Added _get_cors_origins with wildcard rejection and
# PerPathRateLimitMiddleware with longest-prefix match for security compliance.


def _get_cors_origins() -> list:
    """Resolve CORS origins based on deployment environment.

    SECURITY: Wildcard ('*') origins are ALWAYS rejected, even in development.
    In production, CORS_ORIGINS must be explicitly configured or the system
    fails closed (empty list). In development, localhost defaults are provided.
    """
    env = os.getenv("FIREAI_ENV", "production")

    if env == "development":
        origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
        extra = os.getenv("CORS_ORIGINS", "")
        if extra:
            for o in extra.split(","):
                o = o.strip()
                if o and o != "*" and o not in origins:
                    origins.append(o)
        return origins

    # Production: require explicit CORS_ORIGINS env var
    env_origins = os.getenv("CORS_ORIGINS", "")
    if not env_origins:
        return []  # Fail-closed: no origins allowed in production without config

    origins = [o.strip() for o in env_origins.split(",") if o.strip()]

    # SECURITY: Reject wildcards in production — "*" must never appear in origins
    if "*" in origins:
        origins = [o for o in origins if o != "*"]

    return origins


_cors_origins = _get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ── Per-path rate limit middleware ──────────────────────────────────────────
# V110 FIX: Added PerPathRateLimitMiddleware with longest-prefix match algorithm.

_PER_PATH_LIMITS = [
    # V113: workflow/start gets a TIGHTER limit than general workflow endpoints.
    # Starting a workflow allocates a LangGraph state machine, async tasks,
    # checkpoint storage, and potentially 60+ second environmental API calls.
    # Without this tighter limit, an attacker could start thousands of concurrent
    # workflows, exhausting server memory (OOM) and API rate limits.
    # Per agent.md Priority 1 (Safety): DoS on a fire protection system means
    # engineers can't access life-safety tools during an emergency.
    ("/api/workflow/start", 3, 60),  # 3 starts per minute — strict
    # H-5 FIX: Report generation is computationally expensive (database queries,
    # PDF/DXF rendering). Without a tighter limit, an attacker can trigger
    # hundreds of concurrent report generations, exhausting CPU and memory.
    # This prefix is longer than "/api/projects" so it takes precedence for
    # all project-specific sub-paths (reports, exports, devices, connections).
    ("/api/projects/", 15, 60),  # 15/min per IP for project operations
    ("/api/environment/weather", 10, 60),
    ("/api/environment/geocoding", 1, 1),
    ("/api/environment/elevation", 10, 60),
    ("/api/environment/air-quality", 10, 60),
    ("/api/environment/severe", 10, 60),
    ("/api/environment/hazmat", 30, 60),
    ("/api/environment/region", 10, 60),
    ("/api/workflow", 10, 60),  # General workflow queries
    ("/api/memory", 60, 60),
    ("/api/projects", 30, 60),  # Project listing only (shorter prefix)
    ("/api/analyze", 10, 60),
    ("/api/qomn", 10, 60),
    ("/api/parse-dwg", 5, 60),  # DWG parsing is CPU+subprocess intensive
    ("/api/facp", 15, 60),  # FACP selection/compliance (less compute-intensive than QOMN)
]

_DEFAULT_RATE_LIMIT = (120, 60)


class PerPathRateLimitMiddleware:
    """
    Pure ASGI per-path rate limiting — does NOT buffer response body.

    C-1 FIX: Converted from BaseHTTPMiddleware to pure ASGI middleware.
    BaseHTTPMiddleware buffers the ENTIRE response body in memory via
    await call_next(), breaking StreamingResponse for large file exports
    (DXF, IFC, PDF). Pure ASGI middleware passes the response stream
    through without buffering.

    H-1 FIX: Added cleanup of empty IP entries and periodic full cleanup
    to prevent unbounded memory growth from unique client IPs.

    SECURITY: Different API paths have different rate limits based on
    their computational cost and abuse potential. The longest-prefix
    match algorithm ensures that more specific paths (e.g. /api/environment/geocoding)
    take precedence over less specific ones (e.g. /api/environment/weather).
    """

    def __init__(self, app, **kwargs):
        self.app = app
        self._clients: Dict[str, List[float]] = {}  # client_ip → [timestamps]
        import threading
        self._lock = threading.Lock()

    def _find_limit(self, path: str) -> tuple:
        """Find the rate limit for a path using longest-prefix match.

        Algorithm: iterate over all configured prefixes and find the
        longest one that matches the start of the request path.
        """
        best_match = None
        best_len = 0
        for prefix, max_req, window in _PER_PATH_LIMITS:
            if path.startswith(prefix) and len(prefix) > best_len:
                best_match = (max_req, window)
                best_len = len(prefix)
        return best_match if best_match else _DEFAULT_RATE_LIMIT

    def _is_rate_limited(self, client_ip: str, path: str) -> bool:
        """Check if a client has exceeded the rate limit for a path."""
        max_req, window_s = self._find_limit(path)
        now = time.time()
        with self._lock:
            if client_ip not in self._clients:
                self._clients[client_ip] = []
            # Remove expired timestamps
            self._clients[client_ip] = [ts for ts in self._clients[client_ip] if now - ts < window_s]
            # H-1 FIX: Remove empty IP entries to prevent unbounded memory growth.
            # Previously, IPs with all-expired timestamps remained in the dict forever.
            # A million unique IPs = a million permanent entries = memory leak.
            if not self._clients[client_ip]:
                del self._clients[client_ip]
                return False
            if len(self._clients[client_ip]) >= max_req:
                return True
            self._clients[client_ip].append(now)
            # H-1 FIX: Periodic full cleanup when dict grows beyond 10k entries.
            # This handles edge cases where individual entry cleanup isn't enough
            # (e.g., many IPs with partial timestamp lists).
            if len(self._clients) > 10000:
                self._cleanup_expired(now)
            return False

    def _cleanup_expired(self, now: float) -> None:
        """H-1 FIX: Remove all expired client entries to prevent memory leak."""
        expired_ips = []
        for ip, timestamps in list(self._clients.items()):
            # Keep only non-expired timestamps (1h max window covers all limits)
            fresh = [ts for ts in timestamps if now - ts < 3600]
            if not fresh:
                expired_ips.append(ip)
            else:
                self._clients[ip] = fresh
        for ip in expired_ips:
            del self._clients[ip]

    async def __call__(self, scope, receive, send):
        """Enforce per-path rate limits on every HTTP request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client_ip = scope.get("client", (None, None))[0] or "unknown"
        path = scope.get("path", "")

        if self._is_rate_limited(client_ip, path):
            body = json.dumps(
                {"detail": "Rate limit exceeded. Please try again later."}
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        await self.app(scope, receive, send)


# ── Security headers middleware ────────────────────────────────────────────
# Ported from the original project's nginx.conf security headers.
# These headers are mandatory for a safety-critical system exposed to the internet.


def _build_csp() -> str:
    """Build Content-Security-Policy header from environment configuration.

    C-2 FIX: connect-src is no longer hardcoded to localhost.
    In production, CSP_CONNECT_SRC env var must be set for external
    connections (APIs, WebSockets). Without it, only 'self' is allowed.
    In development, localhost defaults are provided.

    M-1 FIX (original): 'unsafe-eval' is only included when CSP_UNSAFE_EVAL=true.
    Original default was "true" (always include) for backward compatibility
    with three.js / recharts which historically required runtime code generation.

    V119 FIX (Finding #4): The CSP_UNSAFE_EVAL default is now ENVIRONMENT-AWARE
    rather than blanket-"true". Rationale per agent.md Priority #1 (Safety) +
    Anti-Deception Directive:
      - Production environments default to "false" (secure-by-default).
        Operators who genuinely need it (legacy frontend builds, three.js
        without WASM, etc.) must explicitly opt-in via CSP_UNSAFE_EVAL=true
        and accept the documented XSS amplification risk.
      - Development environments default to "true" preserving DX (hot-reload,
        Vite/HMR which uses eval in dev builds), without operator action.

    Modern recharts (>=2.x) and three.js (>=0.150) work WITHOUT 'unsafe-eval'
    in production builds. Verified for this codebase:
      - frontend/package.json declares recharts ^2.15.4 and three ^0.160.0
        — both versions support no-unsafe-eval production builds.
      - No `new Function(...)` or `eval(...)` calls exist in frontend/src/.

    When unsafe-eval IS enabled in production, this function logs at ERROR
    level (escalated from WARNING) so the misconfiguration cannot be hidden
    in log noise — surfacing the engineering risk per Anti-Deception
    Directive ("hidden failure modes must be surfaced").
    """
    env = os.getenv("FIREAI_ENV", "production")

    # V119 FIX: Environment-aware default. Production = secure-by-default
    # (no unsafe-eval); development = developer-convenience (eval allowed
    # for Vite/HMR). Operators may override either default explicitly.
    _csp_unsafe_eval_env = os.getenv("CSP_UNSAFE_EVAL")
    if _csp_unsafe_eval_env is None:
        # No explicit setting — pick safe default per environment
        allow_unsafe_eval = (env == "development")
    else:
        allow_unsafe_eval = _csp_unsafe_eval_env.lower() in ("true", "1", "yes")

    if allow_unsafe_eval:
        script_src = "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        if env != "development":
            # V119: Escalated from WARNING → ERROR. A misconfigured production
            # CSP weakens XSS protection on a safety-critical UI; this must
            # be visible in any reasonable log aggregation/alerting setup.
            logger.error(
                "SECURITY: CSP includes 'unsafe-eval' in production "
                "(CSP_UNSAFE_EVAL=%s). This weakens XSS protection on a "
                "safety-critical fire alarm UI. Recommended: unset "
                "CSP_UNSAFE_EVAL (secure default applies) or set to 'false', "
                "and migrate to nonce-based CSP for any frontend code that "
                "genuinely requires runtime code generation.",
                _csp_unsafe_eval_env,
            )
    else:
        script_src = "script-src 'self' 'unsafe-inline'; "

    # C-2 FIX: connect-src is configurable, not hardcoded to localhost
    connect_src_extra = ""
    if env == "development":
        connect_src_extra = " http://localhost:* ws://localhost:*"
    else:
        # Production: read allowed connection sources from env var
        extra = os.getenv("CSP_CONNECT_SRC", "")
        if extra:
            connect_src_extra = f" {extra}"
        # If CSP_CONNECT_SRC is not set, only 'self' is allowed

    csp = (
        "default-src 'self'; "
        + script_src +
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        f"connect-src 'self'{connect_src_extra}; "
        "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
        "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com;"
    )
    return csp


class SecurityHeadersMiddleware:
    """
    Pure ASGI middleware — adds security headers to every HTTP response.

    C-1 FIX: Converted from BaseHTTPMiddleware to pure ASGI middleware.
    BaseHTTPMiddleware's await call_next() reads the ENTIRE response body
    into memory before dispatch() runs, breaking StreamingResponse for
    large DXF/IFC/PDF exports. Pure ASGI middleware intercepts the response
    stream without buffering, allowing large file downloads to work.

    Source: Original FRONTEND-FIREAI project nginx.conf, adapted for FastAPI.
    Rationale:
      - X-Frame-Options: Prevents clickjacking on safety-critical UI
      - X-Content-Type-Options: Prevents MIME-sniffing attacks
      - X-XSS-Protection: Legacy XSS protection for older browsers
      - Referrer-Policy: Limits information leakage in referrer headers
      - Permissions-Policy: Denies access to unnecessary browser APIs
      - Content-Security-Policy: Restricts resource loading to trusted sources
    """

    def __init__(self, app, **kwargs):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # C-2 + M-1 FIX: Build CSP dynamically from environment configuration
        csp = _build_csp()

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Prevent clickjacking — safety-critical UI must not be framed
                headers.append([b"x-frame-options", b"SAMEORIGIN"])
                # Prevent MIME type sniffing — forces declared Content-Type
                headers.append([b"x-content-type-options", b"nosniff"])
                # Legacy XSS protection for older browsers
                headers.append([b"x-xss-protection", b"1; mode=block"])
                # Limit referrer information to origin only on cross-origin requests
                headers.append([b"referrer-policy", b"strict-origin-when-cross-origin"])
                # Deny access to unnecessary browser APIs (camera, microphone, geolocation)
                headers.append([b"permissions-policy", b"camera=(), microphone=(), geolocation=()"])
                # Content Security Policy — restricts resource loading
                headers.append([b"content-security-policy", csp.encode("utf-8")])
                # V129 FIX: HSTS header — enforce HTTPS in all environments.
                # Even in development, including HSTS prevents accidental HTTP
                # usage. Max-age=31536000 = 1 year. includeSubDomains prevents
                # HTTP on any subdomain. The browser will internally redirect
                # HTTP to HTTPS after seeing this header once.
                headers.append([b"strict-transport-security", b"max-age=31536000; includeSubDomains"])
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


app.add_middleware(SecurityHeadersMiddleware)

# ── API Key Authentication Middleware ──────────────────────────────────────
# Safety-critical system: ALL mutating endpoints (POST, PUT, DELETE, PATCH)
# require X-API-Key header matching FIREAI_API_KEY env var.
# GET requests are allowed without auth for read-only access.
# If FIREAI_API_KEY is not set, auth is disabled (development mode only).

_FIREAI_API_KEY = os.getenv("FIREAI_API_KEY")


class ApiKeyMiddleware:
    """
    Pure ASGI middleware — validates X-API-Key header on mutating requests.

    C-1 FIX: Converted from BaseHTTPMiddleware to pure ASGI middleware.
    BaseHTTPMiddleware's await call_next() reads the ENTIRE response body
    into memory, breaking StreamingResponse for large file exports.
    Pure ASGI middleware passes the response stream through without buffering.

    In a life-safety engineering system, unauthorized modification of
    detector placement or circuit calculations is a safety hazard.
    This middleware ensures only authorized clients can modify data.

    Same-origin requests (from the SPA frontend served by this app)
    are always allowed — the API key is only required for external
    API consumers (third-party scripts, CLI tools, etc.).
    """

    def __init__(self, app, **kwargs):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        client_ip = scope.get("client", (None, None))[0] or "unknown"

        # Skip auth for read-only methods and OPTIONS
        if method in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        # V65 FIX: If FIREAI_API_KEY is not set in production, FAIL TO START.
        # The old code silently allowed all requests when the key was unset,
        # which means a deployed system with a missing env variable has zero
        # access control — anyone can modify fire alarm engineering data.
        if not _FIREAI_API_KEY:
            if os.getenv("FIREAI_ENV") != "development":
                logger.critical(
                    "FIREAI_API_KEY not set in production! Refusing to process "
                    "unauthenticated mutating requests. Set FIREAI_API_KEY environment "
                    "variable or set FIREAI_ENV=development for local development."
                )
                body = b"Server misconfigured: FIREAI_API_KEY required in production"
                await send({
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        [b"content-type", b"text/plain"],
                        [b"content-length", str(len(body)).encode()],
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
            # Development mode: allow without auth
            logger.warning("FIREAI_API_KEY not set — auth disabled (development only)")
            await self.app(scope, receive, send)
            return

        # Get headers from ASGI scope (headers are [name_bytes, value_bytes] pairs)
        headers_dict = {}
        for h_name, h_value in scope.get("headers", []):
            headers_dict[
                h_name.decode("utf-8", errors="replace").lower()
            ] = h_value.decode("utf-8", errors="replace")

        origin = headers_dict.get("origin", "")

        # V65 FIX: Remove Origin-header-based auth bypass entirely.
        # The old code compared client-controlled Origin against client-controlled Host,
        # allowing ANY attacker to bypass auth by setting both headers. In a
        # life-safety system, this is catastrophic — an unauthorized person could
        # modify fire alarm projects, corrupting engineering data.
        # The API key is now required for ALL mutating requests regardless of origin.
        # Same-origin SPA requests must include the X-API-Key header.
        #
        # In development mode, allow common dev origins WITHOUT API key
        # (CRITICAL: This MUST NOT be active in production)
        if os.getenv("FIREAI_ENV") == "development":
            if origin in (
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ):
                await self.app(scope, receive, send)
                return

        # No matching origin — require API key
        # This covers: (1) requests without Origin header, (2) external origins
        # Use constant-time comparison to prevent timing attacks
        api_key = headers_dict.get("x-api-key", "")
        if not hmac.compare_digest(api_key, _FIREAI_API_KEY):
            logger.warning(
                f"Unauthorized {method} request to {path} "
                f"from origin={origin or 'none'} client={client_ip}"
            )
            body = json.dumps(
                {"success": False, "error": "Invalid or missing X-API-Key header"}
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


app.add_middleware(ApiKeyMiddleware)

# V111 FIX: Wire PerPathRateLimitMiddleware into the middleware stack.
# V101 defined it but never added it — security middleware that exists in code
# but doesn't run is a life-safety hazard (false sense of security).
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
        content=json.dumps(
            {
                "success": False,
                "error": str(detail),
                "status_code": exc.status_code,
            }
        ),
        status_code=exc.status_code,
        media_type="application/json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured JSON for request validation errors."""
    errors = []
    for err in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    logger.warning(f"Validation error on {request.method} {request.url.path}: {errors}")
    return Response(
        content=json.dumps(
            {
                "success": False,
                "error": "Request validation failed",
                "details": errors,
                "status_code": 422,
            }
        ),
        status_code=422,
        media_type="application/json",
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — prevent stack trace leakage."""
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {type(exc).__name__}: {exc}",
        exc_info=True,
    )
    is_dev = os.getenv("FIREAI_ENV") == "development"
    error_detail = f"{type(exc).__name__}: {exc}" if is_dev else "Internal server error"
    from backend.response import error as api_error_response
    resp = api_error_response(error_detail)
    resp["status_code"] = 500
    return Response(
        content=json.dumps(resp),
        status_code=500,
        media_type="application/json",
    )


# ── Import and mount routers ───────────────────────────────────────────────

from backend.routers import (
    conflicts,
    connections,
    connections_v2,
    devices,
    dwg,
    elements,
    environment,
    exports,
    facp,
    health,
    monitor,
    projects,
    qomn,
    reports,
    sync,
)

# Optional routers: already imported before lifespan() above

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

# Workflow engine at /api/workflow (optional — requires langgraph)
if WORKFLOW_ROUTER_AVAILABLE:
    app.include_router(workflow.router, prefix="/api")

# Memory layer at /api/memory (optional — requires mem0 + qdrant-client)
if MEMORY_ROUTER_AVAILABLE:
    app.include_router(memory.router, prefix="/api")

# FACP selection & compliance at /api/facp (NFPA 72 SS10.6.10, UL 864)
app.include_router(facp.router, prefix="/api")

# QOMN engineering kernel at /api/qomn (NFPA 72, NEC 2023)
app.include_router(qomn.router, prefix="/api")

# DWG/DXF parsing at /api/parse-dwg
app.include_router(dwg.router, prefix="/api")

# Monitor dashboard at /api/monitor
app.include_router(monitor.router)

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
        """
        # Don't intercept API or WebSocket routes — return proper 404
        if full_path.startswith("api/") or full_path == "ws":
            raise HTTPException(status_code=404, detail="Not found")
        # V65 FIX: Path traversal protection — validate that the resolved path
        # stays within the frontend directory. The old code directly used user-
        # controlled `full_path` with pathlib, which preserves `..` segments.
        # An attacker sending GET /../../../etc/passwd could read arbitrary files,
        # including .env files with FIREAI_API_KEY and database credentials.
        file_path = (_FRONTEND_DIST / full_path).resolve()
        if not file_path.is_relative_to(_FRONTEND_DIST.resolve()):
            raise HTTPException(status_code=403, detail="Forbidden")
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Fallback to index.html for SPA routing
        index_path = (_FRONTEND_DIST / "index.html").resolve()
        if index_path.is_file():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Not found")

    logger.info(f"Frontend build served from {_FRONTEND_DIST}")
else:
    logger.info(f"Frontend build not found at {_FRONTEND_DIST}. Run 'npm run build' in frontend/ to serve the SPA.")


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

    host = os.getenv("HOST", "0.0.0.0")  # noqa: S104 — binding to 0.0.0.0 is standard for Docker/container deployment
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        reload=os.getenv("FIREAI_ENV") == "development",
        log_level="info",
    )
