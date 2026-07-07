# NOSONAR
"""
backend_app.py - FireAI QOMN + Analyze API Application Entry Point
====================================================================
FastAPI application exposing:
  - QOMN-FIRE engineering kernel endpoints (under /api/qomn/...)
  - Analyze endpoints for project-level workflows (under /api/analyze/...
    and /api/projects/{project_id}/analyze/room)
  - Health endpoint (under /api/health)

DESIGN:
  - Loads the qomn_router from backend.routers.qomn
  - Loads the analyze_router and analyze_project_router from
    backend.routers.analyze (created in Phase 10)
  - Mounts all routers under /api prefix
  - Adds a RoleDevMiddleware that grants ADMIN role when
    FIREAI_ENV in {development, testing} so endpoints with
    require_permission(Permission.QOMN_EXECUTE) are callable
    in tests / dev. In production the middleware is a no-op and
    the real API-key middleware (deployed separately) sets the role.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.rbac import Role
from backend.routers.analyze import (
    project_router as analyze_project_router,
)
from backend.routers.analyze import (
    router as analyze_router,
)
from backend.routers.health import router as health_router
from backend.routers.qomn import router as qomn_router

# V129: Security middleware — same hardening as backend/app.py.
# SecurityHeadersMiddleware adds X-Frame-Options, X-Content-Type-Options,
# HSTS, CSP, Referrer-Policy, Permissions-Policy to every HTTP response.
# CorrelationIdMiddleware adds X-Correlation-ID for end-to-end audit tracing
# (NFPA 72 §14.2.4 compliance).
from backend.security_middleware import (
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
)

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Dev role middleware (V127)
# ----------------------------------------------------------------------------
class _RoleDevMiddleware(BaseHTTPMiddleware):
    """
    Grants ADMIN role in development / testing environments.

    In production this middleware is a no-op -- the real API-key
    middleware (deployed by the platform) is responsible for setting
    request.state.fireai_role based on the validated API key.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]):  # noqa: ANN401
        env = os.getenv("FIREAI_ENV", "production").lower()
        if env in ("development", "testing"):
            # Only set if not already set by an upstream middleware.
            if getattr(request.state, "fireai_role", None) is None:
                request.state.fireai_role = Role.ADMIN
        return await call_next(request)


# ----------------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------------
app = FastAPI(
    title="FireAI QOMN-FIRE API",
    description=(
        "QOMN-FIRE deterministic engineering kernel + project-level "
        "analyze endpoints. All calculations are NFPA 72-2022 / NEC 2023 "
        "compliant with cryptographic audit trail."
    ),
    version="1.0.0",
)

# CORS — environment-aware (V127 SAFETY HARDENING).
# Production: CORS_ORIGINS env var is REQUIRED (comma-separated list of
#             trusted origins). Missing env var → security hardening fail.
# Development/testing: defaults to localhost only (safe default).
#
# PER CORS SPEC (Fetch Standard §3.2):
#   - allow_origins=["*"] + allow_credentials=True is FORBIDDEN.
#   - We never set allow_credentials=True here (the API uses X-API-Key
#     header auth, not cookies, so cross-origin credentialed requests
#     are not needed).
#   - Even without credentials, a wildcard origin in production allows
#     ANY website to read API responses (data exfiltration vector).
#   - The default below is restricted to localhost dev ports; production
#     deployments MUST set CORS_ORIGINS explicitly.
_env = os.getenv("FIREAI_ENV", "development").lower()
if _env in ("production", "prod"):
    _cors_raw = os.getenv("CORS_ORIGINS", "")
    if not _cors_raw:
        # Production without explicit CORS_ORIGINS — fail safe.
        # The platform operator must declare trusted origins.
        raise RuntimeError(
            "CORS_ORIGINS environment variable is REQUIRED in production. "  # noqa: ISC001
            "Set it to a comma-separated list of trusted origins, e.g. "
            "'https://app.example.com,https://admin.example.com'. "
            "Wildcards are forbidden in production for life-safety audit reasons."
        )
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if "*" in _cors_origins:
        raise RuntimeError(
            "CORS_ORIGINS='*' is forbidden in production. List explicit origins."
        )
else:
    # Development / testing — safe defaults (localhost only).
    _cors_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:8000",
    ).split(",")

# S8414 fix: Starlette `add_middleware` PREPENDS to the stack, so the LAST
# call is the OUTERMOST middleware. CORSMiddleware MUST be outermost so it
# can short-circuit CORS preflight (OPTIONS) requests BEFORE any other
# middleware tries to authenticate / inspect them. Previous order put CORS
# innermost, which broke preflight handling under cross-origin browsers.
# V129: SecurityHeadersMiddleware — runs inside CORS so security headers
# are still applied to every non-preflight response.
app.add_middleware(SecurityHeadersMiddleware)
# V129: CorrelationIdMiddleware — adds X-Correlation-ID to every request
# for end-to-end audit tracing (NFPA 72 §14.2.4 compliance).
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(_RoleDevMiddleware)
# S8414: CORSMiddleware MUST be added LAST (= outermost) per SonarCloud
# S8414 rule. See https://rules.sonarsource.com/python/RSPEC-8414/.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "X-Correlation-ID"],
    # NEVER enable allow_credentials=True with this design — API uses
    # X-API-Key header auth (not cookies), so cross-origin credentialed
    # requests are unnecessary and would expand the attack surface.
    allow_credentials=False,
)


# ----------------------------------------------------------------------------
# Router registration (under /api prefix per Phase 10 spec)
# ----------------------------------------------------------------------------
app.include_router(health_router, prefix="/api")
app.include_router(qomn_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(analyze_project_router, prefix="/api")


# ----------------------------------------------------------------------------
# Root / fallback
# ----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    return {"name": "FireAI QOMN-FIRE API", "version": "1.0.0",
            "docs": "/docs", "health": "/api/health"}


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler.

    Never leak internal exception text to clients -- fire-safety systems
    may have sensitive paths / connection strings in error messages.
    """
    logger.error("Unhandled exception on %s %s: %s",
                 request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "success": False},
    )


if __name__ == "__main__":
    import uvicorn
    # V129: Bind to 127.0.0.1 (loopback) by default. Production deployments
    # MUST use a reverse proxy (nginx, traefik, AWS ALB) to terminate TLS and
    # forward to this loopback address. Binding to 0.0.0.0 exposes the API
    # directly to the network, bypassing the proxy's rate limiting, TLS,
    # and request filtering.
    _bind_host = os.getenv("FIREAI_BIND_HOST", "127.0.0.1")
    if _bind_host == "0.0.0.0":
        logger.warning(
            "Binding to 0.0.0.0 — API will be reachable from the network. "  # noqa: ISC001
            "Use a reverse proxy (nginx/traefik) in production. "
            "Set FIREAI_BIND_HOST=127.0.0.1 to restore loopback-only binding."
        )
    uvicorn.run(app, host=_bind_host, port=8000)
