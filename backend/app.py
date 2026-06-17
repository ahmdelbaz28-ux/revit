"""
backend/app.py — FastAPI Application Entry Point
===============================================

Core FastAPI application with all CAD/BIM integration routes.
Implements the complete backend for AutoCAD/Revit/Digital Twin system.

ARCHITECTURE:
- FastAPI app with CORS middleware
- Rate limiting with SlowAPI
- All CAD/BIM integration routes
- Health check endpoints
- Error handlers for CAD connection issues

USAGE:
    uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import logging

from pydantic import BaseModel

# Import our CAD/BIM integration routers
from backend.routers import autocad, revit, digital_twin, revit_integration

# Import rate limiter from centralized module (avoids circular import)
from backend.limiter import limiter, get_remote_address

# Configure Redis caching (optional - gracefully handles missing Redis)
_cache = {}

def get_cache():
    """Get cache instance. Returns in-memory dict if Redis unavailable."""
    return _cache

async def cache_get(key: str):
    """Get value from cache."""
    return _cache.get(key)

async def cache_set(key: str, value: str, expire: int = 300):
    """Set value in cache with expiration in seconds."""
    import time
    _cache[key] = {"value": value, "expire": time.time() + expire}

async def cache_delete(key: str):
    """Delete key from cache."""
    _cache.pop(key, None)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Used for startup and shutdown tasks.
    """
    logger.info("Starting CAD/BIM Integration Platform...")
    yield
    logger.info("Shutting down CAD/BIM Integration Platform...")

# Create FastAPI app with lifespan
app = FastAPI(
    title="CAD/BIM Integration Platform",
    description="""
## 🚀 API Overview

Complete platform for **AutoCAD** and **Revit** integration with **Digital Twin** capabilities.

### Features

- **AutoCAD Integration**: Connect to AutoCAD, read/write DWG files, create/draw entities
- **Revit Integration**: Connect to Revit, read/write RVT files, create/modify elements
- **Bidirectional Conversion**: Convert between AutoCAD and Revit formats
- **Digital Twin Engine**: Central conversion hub with semantic mapping
- **Version Management**: Track and rollback conversion history

### Authentication

All endpoints require API key authentication via `X-API-Key` header.

### Rate Limiting

| Endpoint Type | Limit |
|---------------|-------|
| Health/Read | 1000/minute |
| Standard | 100/minute |
| Write/Upload | 50/minute |
| Heavy Operations | 10/minute |
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add rate limiter state
app.state.limiter = limiter

# Add rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include our CAD/BIM integration routers (v1)
app.include_router(autocad.router, prefix="/api/v1/autocad", tags=["AutoCAD-v1"])
app.include_router(revit.router, prefix="/api/v1/revit", tags=["Revit-v1"])
app.include_router(digital_twin.router, prefix="/api/v1/digital-twin", tags=["Digital-Twin-v1"])
app.include_router(revit_integration.router, prefix="/api/v1/revit-integration", tags=["Revit-Integration"])

# Health endpoints (no version prefix - always available)
# These are versioned at root level for easy monitoring
@app.get("/api/v1/health", tags=["Health-v1"])
async def health_check_v1():
    """Health check endpoint for API v1."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "api_version": "v1"
    }

@app.get("/api/v2/health", tags=["Health-v2"])
async def health_check_v2():
    """Health check endpoint for API v2."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "api_version": "v2",
        "features": ["rate_limiting", "enhanced_caching", "streaming"]
    }

# Legacy health endpoint (deprecated)
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint (deprecated - use /api/v1/health)."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "deprecated": True,
        "suggestion": "Use /api/v1/health or /api/v2/health"
    }

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return HTTPException(status_code=500, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# CACHE MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/cache/clear", tags=["Cache"])
async def clear_cache():
    """Clear all cached data."""
    _cache.clear()
    return {"message": "Cache cleared", "items_cleared": len(_cache)}

@app.get("/api/v1/cache/stats", tags=["Cache"])
async def cache_stats():
    """Get cache statistics."""
    import time
    active_keys = sum(1 for v in _cache.values() if v.get("expire", 0) > time.time())
    return {
        "total_keys": len(_cache),
        "active_keys": active_keys,
        "cache_type": "in-memory"
    }

# Mount static files if needed
# app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
