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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

from pydantic import BaseModel

# Import our CAD/BIM integration routers
from backend.routers import autocad, revit, digital_twin

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)

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

# Include our CAD/BIM integration routers
app.include_router(autocad.router, prefix="/api", tags=["autocad"])
app.include_router(revit.router, prefix="/api", tags=["revit"])
app.include_router(digital_twin.router, prefix="/api", tags=["digital-twin"])

# Basic health check endpoint
@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {"message": "CAD/BIM Integration Platform is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0"
    }

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return HTTPException(status_code=500, detail=str(exc))

# Mount static files if needed
# app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
