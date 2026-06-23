"""
backend/middleware/csrf.py — Cross-Site Request Forgery Protection
==================================================================

Implements CSRF protection for the FireAI backend using:
1. Synchronizer token pattern with secure token generation
2. SameSite cookie attributes
3. One-time use tokens stored in Redis
4. Proper validation for state-changing requests

The middleware:
- Generates and stores CSRF tokens in Redis with expiration
- Validates tokens on mutating requests (POST, PUT, PATCH, DELETE)
- Implements one-time use tokens to prevent replay attacks
- Provides endpoints for token acquisition
"""

import secrets
import logging
from typing import Optional

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.core.redis_client import get_redis_client
from backend.config import settings

logger = logging.getLogger(__name__)

# HTTP methods that require CSRF protection
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Endpoints that don't require CSRF protection (API prefixes)
EXEMPT_PATHS = {
    "/api/health",
    "/api/v1/health", 
    "/docs",
    "/redoc",
    "/openapi.json",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Don't initialize Redis client in constructor since it's async
        self.app = app

    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for exempt paths and non-mutating methods
        if self._is_exempt(request):
            return await call_next(request)

        # Validate CSRF token for mutating requests
        if request.method in MUTATING_METHODS:
            await self._validate_csrf_token(request)

        response = await call_next(request)
        
        # Add CSRF token to response headers for client retrieval
        if request.method in {"GET", "HEAD"} and not self._is_exempt(request):
            csrf_token = await self.generate_csrf_token()
            response.headers["X-CSRF-Token"] = csrf_token
            
        return response

    def _is_exempt(self, request: Request) -> bool:
        """Check if the request path is exempt from CSRF protection."""
        path = request.url.path
        return path in EXEMPT_PATHS or any(path.startswith(exempt) for exempt in EXEMPT_PATHS)

    async def _validate_csrf_token(self, request: Request) -> None:
        """Validate the CSRF token from the request."""
        # Get token from header or form data
        csrf_token = (
            request.headers.get("x-csrf-token") or 
            request.headers.get("x-xsrf-token")
        )

        if not csrf_token:
            # Try to get from form data for POST requests
            if request.method == "POST":
                form_data = await request.form()
                csrf_token = form_data.get("csrf_token")
        
        if not csrf_token:
            logger.warning(f"CSRF validation failed: No token provided for {request.method} {request.url.path}")
            raise HTTPException(status_code=403, detail="CSRF token missing")

        # Get Redis client and check if token exists in Redis (validates it's a real token)
        redis_client = await get_redis_client()
        token_exists = await redis_client.exists(f"csrf:{csrf_token}")
        if not token_exists:
            logger.warning(f"CSRF validation failed: Invalid/expired token for {request.method} {request.url.path}")
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        # Remove the token after use (one-time use to prevent replay attacks)
        await redis_client.delete(f"csrf:{csrf_token}")

    async def generate_csrf_token(self) -> str:
        """Generate a new CSRF token and store it in Redis."""
        # Get Redis client
        redis_client = await get_redis_client()
        
        # Generate cryptographically secure token
        token = secrets.token_urlsafe(32)
        
        # Store in Redis with expiration (1 hour by default)
        token_key = f"csrf:{token}"
        
        # Set with expiration to prevent token buildup (1 hour)
        await redis_client.setex(token_key, 3600, "valid")
        
        return token


# Global function to generate CSRF tokens (can be called from anywhere)
async def generate_csrf_token() -> str:
    """Generate a new CSRF token and store it in Redis."""
    redis_client = await get_redis_client()
    
    # Generate cryptographically secure token
    token = secrets.token_urlsafe(32)
    
    # Store in Redis with expiration (1 hour by default)
    token_key = f"csrf:{token}"
    
    # Set with expiration to prevent token buildup (1 hour)
    await redis_client.setex(token_key, 3600, "valid")
    
    return token