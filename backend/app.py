"""
FireAI Digital Twin - Main Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="FireAI Digital Twin",
    description="Digital Twin for BIM coordination",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import core modules
try:
    from core.database import UniversalDataModel
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
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
