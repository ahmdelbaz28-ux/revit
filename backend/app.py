"""
FireAI Digital Twin - Main Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="FireAI Digital Twin",
    description="Digital Twin for BIM coordination",
    version="1.0.0"
)

# Security Fix (VULN-004): Read allowed CORS origins from environment variable
# In production, set CORS_ORIGINS=https://your-domain.com,https://app.your-domain.com
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Import core modules
_core_loaded = False
try:
    from core.database import UniversalDataModel
    _core_loaded = True
    logger.info("Core modules loaded successfully")
except ImportError as e:
    logger.error(f"Failed to load core modules: {e}")

@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    logger.info("FireAI Digital Twin started")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("FireAI Digital Twin stopped")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "FireAI Digital Twin API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    """Health check endpoint — truthful about core module availability.
    
    CRITICAL FIX: Previously always returned "healthy" even when core
    modules failed to load. This is a false-green health endpoint that
    misleads deployment probes and operators.
    """
    if _core_loaded:
        return {"status": "healthy", "core_modules": "loaded"}
    else:
        return {"status": "degraded", "core_modules": "failed", "warning": "Core modules not loaded — service is degraded"}

if __name__ == "__main__":
    import uvicorn
    # Security Fix (VULN-004): Bind to localhost by default; use reverse proxy in production
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
