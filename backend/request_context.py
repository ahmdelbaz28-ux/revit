"""backend/request_context.py — Request correlation and structured logging.

Adds a unique correlation ID to every request for end-to-end tracing.
In a life-safety system, being able to trace a request from frontend
to database and back is critical for debugging and audit.

BUG-34 FIX: Replaced BaseHTTPMiddleware with pure ASGI middleware.
BaseHTTPMiddleware reads the ENTIRE response body into memory before
passing it to dispatch(), defeating StreamingResponse used in exports
and reports. For large projects, this caused OOM crashes.
Pure ASGI middleware can add headers without consuming the body.
"""
import logging
import time
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware:
    """Pure ASGI middleware that adds X-Correlation-ID to every request/response.

    Unlike BaseHTTPMiddleware, this does NOT buffer the response body,
    making it safe for StreamingResponse (exports, reports, PDFs).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Get or generate correlation ID
        headers = dict(scope.get("headers", []))
        cid_key = b"x-correlation-id"
        raw_cid = headers.get(cid_key)
        if raw_cid:
            correlation_id = raw_cid.decode("utf-8", errors="replace")
            # Validate format — prevent log injection via control characters
            try:
                # Must be a valid UUID or alphanumeric string
                uuid.UUID(correlation_id)
            except ValueError:
                if not all(c.isalnum() or c in "-_." for c in correlation_id[:64]):
                    correlation_id = str(uuid.uuid4())
        else:
            correlation_id = str(uuid.uuid4())

        # Store in scope for access in route handlers
        scope.setdefault("state", {})
        scope["state"]["correlation_id"] = correlation_id

        # Log request start
        if scope["type"] == "http":
            method = scope.get("method", "?")
            path = scope.get("path", "?")
            start_time = time.time()

            # Intercept send to add correlation ID header and log timing
            async def send_with_correlation_id(message) -> None:
                if message["type"] == "http.response.start":
                    # Add correlation ID header
                    headers = list(message.get("headers", []))
                    headers.append(
                        (b"x-correlation-id", correlation_id.encode("utf-8"))
                    )
                    message["headers"] = headers

                    # Log timing and status
                    status_code = message.get("status", 0)
                    duration_ms = (time.time() - start_time) * 1000
                    logger.info(
                        f"[{correlation_id[:8]}] {method} {path} "
                        f"→ {status_code} ({duration_ms:.1f}ms)"
                    )

                await send(message)

            await self.app(scope, receive, send_with_correlation_id)
        else:
            # WebSocket — just pass through
            await self.app(scope, receive, send)
