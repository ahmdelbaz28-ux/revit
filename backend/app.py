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
from starlette.middleware.base import BaseHTTPMiddleware

from backend.request_context import CorrelationIdMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Security Audit Logging & Log Rotation ──────────────────────────────────
# V100+V105: Structured security event logging with tamper-evident chain
# hashing, sensitive data masking, and size-based log rotation.
try:
    from fireai.core.security_logging import (
        SecurityEventType,
        configure_log_rotation,
        security_audit,
    )
    configure_log_rotation(logger, "fireai.log")
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
    # V91 FIX: Wrap in try/except — langgraph may not be installed.
    try:
        from backend.services.workflow_service import get_workflow_service
        svc = get_workflow_service()
        if hasattr(svc, '_langgraph_available') and svc._langgraph_available:
            logger.info("Workflow service initialized (LangGraph State Machine)")
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
    from backend.services.workflow_service import close_workflow_service
    await close_workflow_service()
    logger.info("Workflow service closed")

    # Shutdown — close memory service
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
    ("/api/environment/weather",     10, 60),
    ("/api/environment/geocoding",    1,  1),
    ("/api/environment/elevation",   10, 60),
    ("/api/environment/air-quality", 10, 60),
    ("/api/environment/severe",      10, 60),
    ("/api/environment/hazmat",      30, 60),
    ("/api/environment/region",      10, 60),
    ("/api/workflow",                10, 60),
    ("/api/memory",                  60, 60),
    ("/api/projects",               30, 60),
    ("/api/analyze",                 10, 60),
    ("/api/qomn",                    10, 60),
]

_DEFAULT_RATE_LIMIT = (120, 60)


class PerPathRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-path rate limiting using longest-prefix match algorithm.

    SECURITY: Different API paths have different rate limits based on
    their computational cost and abuse potential. The longest-prefix
    match algorithm ensures that more specific paths (e.g. /api/environment/geocoding)
    take precedence over less specific ones (e.g. /api/environment/weather).
    """

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

# ── Security headers middleware ────────────────────────────────────────────
# Ported from the original project's nginx.conf security headers.
# These headers are mandatory for a safety-critical system exposed to the internet.

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every HTTP response.

    Source: Original FRONTEND-FIREAI project nginx.conf, adapted for FastAPI.
    Rationale:
      - X-Frame-Options: Prevents clickjacking on safety-critical UI
      - X-Content-Type-Options: Prevents MIME-sniffing attacks
      - X-XSS-Protection: Legacy XSS protection for older browsers
      - Referrer-Policy: Limits information leakage in referrer headers
      - Permissions-Policy: Denies access to unnecessary browser APIs
      - Content-Security-Policy: Restricts resource loading to trusted sources
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Prevent clickjacking — safety-critical UI must not be framed
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Prevent MIME type sniffing — forces declared Content-Type
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Legacy XSS protection for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Limit referrer information to origin only on cross-origin requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Deny access to unnecessary browser APIs (camera, microphone, geolocation)
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Content Security Policy — restricts resource loading
        # 'unsafe-inline' and 'unsafe-eval' needed for Vite-built React app
        # 'unsafe-eval' required by some charting/3D libraries (recharts, three.js)
        # connect-src allows API and WebSocket connections
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' http://localhost:* ws://localhost:*; "
            "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
            "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com;"
        )
        response.headers["Content-Security-Policy"] = csp
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── API Key Authentication Middleware ──────────────────────────────────────
# Safety-critical system: ALL mutating endpoints (POST, PUT, DELETE, PATCH)
# require X-API-Key header matching FIREAI_API_KEY env var.
# GET requests are allowed without auth for read-only access.
# If FIREAI_API_KEY is not set, auth is disabled (development mode only).

_FIREAI_API_KEY = os.getenv("FIREAI_API_KEY")

class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Validates X-API-Key header on mutating requests.

    In a life-safety engineering system, unauthorized modification of
    detector placement or circuit calculations is a safety hazard.
    This middleware ensures only authorized clients can modify data.

    Same-origin requests (from the SPA frontend served by this app)
    are always allowed — the API key is only required for external
    API consumers (third-party scripts, CLI tools, etc.).
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth for read-only methods and WebSocket
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        # If no API key is configured, allow all (dev mode)
        if not _FIREAI_API_KEY:
            return await call_next(request)

        # SECURITY: When API key is configured, we validate ALL mutating requests.
        # Same-origin SPA requests are identified by matching the Origin header
        # to our Host header. Requests WITHOUT an Origin header are NOT trusted
        # as same-origin — external tools (curl, Postman, scripts) typically omit
        # the Origin header, so treating absent Origin as trusted creates an
        # auth bypass vulnerability (CVE-2026-001).
        #
        # Browser fetch from the SPA always includes Origin when the request
        # is cross-origin, and same-origin POST from a form includes Origin
        # in most browsers. The SPA's fetch() calls include Origin explicitly.
        origin = request.headers.get("origin", "")

        # Check if Origin matches our server (same-origin SPA)
        # BUG-39 FIX: Previous code allowed spoofed Origin headers from external
        # IPs by matching against hardcoded dev origins like "http://localhost:3000".
        # An external attacker could set Origin: http://localhost:3000 and bypass auth.
        # Fix: Only trust Origin if it matches the request's Host header exactly,
        # OR if we're explicitly in development mode (FIREAI_ENV=development).
        if origin:
            host = request.headers.get("host", "")
            # Only trust same-origin requests where Origin matches Host exactly
            if origin in (
                f"http://{host}",
                f"https://{host}",
            ):
                return await call_next(request)

            # In development mode, trust common dev origins
            # CRITICAL: This MUST NOT be active in production
            if os.getenv("FIREAI_ENV") == "development":
                if origin in (
                    "http://localhost:3000",
                    "http://localhost:5173",
                    "http://127.0.0.1:3000",
                    "http://127.0.0.1:5173",
                ):
                    return await call_next(request)

        # No matching origin — require API key
        # This covers: (1) requests without Origin header, (2) external origins
        # Use constant-time comparison to prevent timing attacks
        import hmac
        api_key = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(api_key, _FIREAI_API_KEY):
            logger.warning(
                f"Unauthorized {request.method} request to {request.url.path} "
                f"from origin={origin or 'none'} client={request.client.host if request.client else 'unknown'}"
            )
            return Response(
                content='{"success":false,"error":"Invalid or missing X-API-Key header"}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)


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
        # Try to serve a real file first
        file_path = _FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
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
