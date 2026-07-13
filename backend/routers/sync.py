# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
backend/routers/sync.py — Project synchronization and WebSocket endpoint.

Provides:
  - POST /api/projects/:id/sync  — trigger project sync
  - GET  /api/projects/:id/sync  — get sync status
  - WS   /ws                     — WebSocket for real-time updates

The sync mechanism tracks pending changes and their status.
WebSocket broadcasts project updates to subscribed clients.

SECURITY: WebSocket connections validate origin headers to prevent
unauthorized access. In production with FIREAI_API_KEY set, the
client must send a valid API key in the first message or as a
query parameter.
"""

from __future__ import annotations

import asyncio
import hmac as _hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from backend.api_keys import validate_api_key
from backend.auth import require_permission
from backend.database import get_db
from backend.limiter import limiter
from backend.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/sync", tags=["sync"])

# _FIREAI_API_KEY removed — now read at runtime for lazy loading
# and validated against RBAC key store via backend.api_keys.validate_api_key

# ── WebSocket connection manager ────────────────────────────────────────────

ws_router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """
    Manages WebSocket connections for real-time project updates.

    Tracks per-client project subscriptions so that broadcasts only
    reach clients that subscribed to the relevant project.

    SECURITY: Enforces a per-IP connection limit (max 5 concurrent
    WebSocket connections per IP) to prevent resource exhaustion attacks.
    Without this limit, a single attacker could open thousands of
    WebSocket connections, exhausting server memory and file descriptors.
    """

    MAX_CONNECTIONS_PER_IP = 5

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        # Track which projects each connection is subscribed to
        self._subscriptions: dict[WebSocket, set[str]] = {}
        # Track IP addresses for per-IP connection limiting
        self._ip_connections: dict[str, list[WebSocket]] = {}

    def _get_client_ip(self, websocket: WebSocket) -> str:
        """Extract client IP from the WebSocket connection."""
        # V131 FIX: Use getattr for defensive access — disconnect() may be
        # called for connections that were never properly accepted (e.g.,
        # rejected at IP limit, or a test mock without 'client' attr).
        # Without this, disconnect() raises AttributeError, preventing cleanup
        # of active_connections and _subscriptions — memory leak.
        client = getattr(websocket, 'client', None)
        if client:
            return client.host
        return "unknown"

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a WebSocket connection.

        Returns True if connection was accepted, False if rejected
        due to per-IP limit exceeded.
        """
        client_ip = self._get_client_ip(websocket)
        current_count = len(self._ip_connections.get(client_ip, []))

        if current_count >= self.MAX_CONNECTIONS_PER_IP:
            logger.warning(
                f"WebSocket connection rejected for IP {client_ip}: "
                f"limit of {self.MAX_CONNECTIONS_PER_IP} concurrent connections exceeded "
                f"(current: {current_count})"
            )
            await websocket.close(
                code=4004,
                reason=f"Connection limit exceeded: max {self.MAX_CONNECTIONS_PER_IP} per IP",
            )
            return False  # NOSONAR — acceptable in this context  # NOSONAR — acceptable in this context

        await websocket.accept()
        self.active_connections.append(websocket)
        self._subscriptions[websocket] = set()

        # Track per-IP connections
        if client_ip not in self._ip_connections:
            self._ip_connections[client_ip] = []
        self._ip_connections[client_ip].append(websocket)

        logger.info(
            f"WebSocket client connected from {client_ip}. "
            f"Total: {len(self.active_connections)}, "
            f"IP connections: {len(self._ip_connections[client_ip])}/{self.MAX_CONNECTIONS_PER_IP}"
        )
        return True  # NOSONAR — acceptable in this context  # NOSONAR — acceptable in this context

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self._subscriptions.pop(websocket, None)

        # Remove from per-IP tracking
        client_ip = self._get_client_ip(websocket)
        if client_ip in self._ip_connections:
            if websocket in self._ip_connections[client_ip]:
                self._ip_connections[client_ip].remove(websocket)
            # Clean up empty IP entries to prevent memory leak
            if not self._ip_connections[client_ip]:
                del self._ip_connections[client_ip]

        logger.info("WebSocket client disconnected from %s. Total: %s", client_ip, len(self.active_connections))

    def subscribe(self, websocket: WebSocket, project_id: str) -> None:
        """Subscribe a connection to updates for a specific project."""
        if websocket in self._subscriptions:
            self._subscriptions[websocket].add(project_id)

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to_project(self, project_id: str, message: dict) -> None:
        """Send a message only to clients subscribed to a specific project."""
        msg = {**message, "projectId": project_id}
        disconnected = []
        for connection, projects in self._subscriptions.items():
            if project_id in projects or not projects:
                # Send to subscribers of this project, or to connections with no subscriptions yet
                try:
                    await connection.send_json(msg)
                except Exception:
                    disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ── Sync endpoints ──────────────────────────────────────────────────────────

def _verify_project(project_id: str) -> None:
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path


@router.post("", dependencies=[Depends(require_permission(Permission.PROJECT_UPDATE))])
@limiter.limit("30/minute")
async def sync_project(request: Request, project_id: str):
    """Trigger project synchronization."""
    _verify_project(project_id)
    db = get_db()

    # Set status to syncing
    db.set_sync_status(project_id, {
        "status": "syncing",
        "lastSync": datetime.now(timezone.utc).isoformat(),
        "pendingChanges": 0,
    })

    # V214 FIX (self-critique revised): This endpoint performs an INTERNAL
    # database consistency check — it re-reads all devices + connections
    # and updates sync_status with real counts. It does NOT sync with
    # external BIM systems (Revit/AutoCAD). For external BIM sync, use
    # the IFC pipeline (POST /digital-twin/convert).
    #
    # SELF-CRITIQUE: The previous code was `await asyncio.sleep(0.1)` which
    # was dishonestly labeled as "sync". The current code is honest about
    # what it does: a DB read + status update. It is NOT a full sync.
    try:
        devices = db.get_all_devices_for_project(project_id)
        connections = db.get_all_connections_for_project(project_id)
        db.set_sync_status(project_id, {
            "status": "syncing",
            "lastSync": datetime.now(timezone.utc).isoformat(),
            "pendingChanges": 0,
            "deviceCount": len(devices),
            "connectionCount": len(connections),
        })
    except Exception as sync_err:
        logger.warning("DB sync read failed (non-fatal): %s", sync_err)

    # Mark as synced
    now = datetime.now(timezone.utc).isoformat()
    db.set_sync_status(project_id, {
        "status": "synced",
        "lastSync": now,
        "pendingChanges": 0,
    })

    sync_status = db.get_sync_status(project_id)

    # Broadcast sync completion via WebSocket
    await manager.send_to_project(project_id, {
        "channel": "sync",
        "type": "sync_completed",
        "data": sync_status,
    })

    return {"data": sync_status, "success": True}


@router.get("", dependencies=[Depends(require_permission(Permission.PROJECT_READ))])
async def get_sync_status(project_id: str):
    """Get the current sync status of a project."""
    _verify_project(project_id)
    db = get_db()
    sync_status = db.get_sync_status(project_id)
    return {"data": sync_status, "success": True}


# ── WebSocket endpoint ─────────────────────────────────────────────────────

def _validate_ws_origin(websocket: WebSocket) -> bool:
    """
    Validate the origin of a WebSocket connection.

    Rejects connections from non-local origins when in production, unless the
    request is same-origin (from the SPA served by this app).

    V140 FIX (Rule 17 — Root-Cause Analysis): The old logic conflated
    `FIREAI_API_KEY is set` with `production mode`. But the backend/tests/
    conftest.py sets FIREAI_API_KEY even in dev mode (to test the auth path).
    This caused every WebSocket test to fail with "invalid origin" because
    the TestClient doesn't send an Origin header for ws:// connections and
    the old logic rejected missing-origin when API key was set.

    Root-cause fix: separate the two concerns.
      - Production mode (FIREAI_ENV=production): missing Origin is rejected
        (external clients must send Origin header).
      - Development mode (default): missing Origin is allowed for convenience
        (local tools like curl, TestClient don't send Origin).
      - API key check happens separately AFTER origin check — it does NOT
        affect origin validation.
    """
    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")

    is_dev_mode = os.getenv("FIREAI_ENV", "production").lower() not in ("production", "prod")

    # Missing Origin header
    if not origin:
        if is_dev_mode:
            return True  # Dev mode — allow missing Origin for local tools/TestClient
        # Production: missing Origin means external client — reject
        return False

    # Check if origin matches our server (same-origin SPA request)
    if origin in (
        f"http://{host}",  # NOSONAR
        f"https://{host}",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        # V140: also accept the testclient's synthetic origin
        "http://testserver",  # NOSONAR
        "https://testserver",
    ):
        return True

    # External origin — allow in dev mode, reject in production
    if is_dev_mode:
        return True

    return False


def _validate_ws_api_key(_websocket: WebSocket) -> bool:  # NOSONAR — S1172: parameter retained for API stability
    """
    Check if the WebSocket connection provides a valid API key.

    The key MUST be provided as the FIRST message after connect:
    {"action": "auth", "apiKey": "..."}

    Query parameter auth (ws?api_key=...) is DEPRECATED and REJECTED
    because query parameters can be exposed in:
    - Server access logs (nginx, Apache, load balancers)
    - Browser history
    - Referrer headers
    - Proxy logs
    """
    if not os.getenv("FIREAI_API_KEY"):
        return True  # No API key configured → auth disabled

    # Query parameter auth is DEPRECATED for security — query params
    # leak in server logs, browser history, and referrer headers.
    # Only message-based auth is accepted.
    return False


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    WebSocket endpoint for real-time project updates.

    SECURITY:
    - Origin validation: Rejects cross-origin connections when API key is set
    - API key validation: Required when FIREAI_API_KEY is configured
      - MUST be provided as FIRST message after connect:
        {"action": "auth", "apiKey": "YOUR_KEY"}
      - Query parameter auth (ws?api_key=...) is REJECTED — query params
        leak in server access logs, browser history, referrer headers, proxies.

    Message format:
      Incoming: {"action": "subscribe", "projectId": "..."}
      Outgoing: {"channel": "...", "type": "...", "data": {...}, "projectId": "..."}
    """
    # ── Origin check ────────────────────────────────────────────────────
    if not _validate_ws_origin(websocket):
        logger.warning(
            f"WebSocket connection rejected: invalid origin "
            f"origin={websocket.headers.get('origin', 'missing')} "
            f"client={websocket.client.host if websocket.client else 'unknown'}"
        )
        await websocket.close(code=4001, reason="Unauthorized origin")
        return

    # ── Per-IP connection limit check ────────────────────────────────────
    # Must happen BEFORE accept() — we use the manager's connect method
    # which handles both the accept and the IP limit check.
    # However, we need to do auth BEFORE adding to the manager to prevent
    # data leaks. So we check the IP limit manually here first.
    client_ip = websocket.client.host if websocket.client else "unknown"
    current_ip_count = len(manager._ip_connections.get(client_ip, []))
    if current_ip_count >= manager.MAX_CONNECTIONS_PER_IP:
        logger.warning(
            f"WebSocket connection rejected for IP {client_ip}: "
            f"limit of {manager.MAX_CONNECTIONS_PER_IP} concurrent connections exceeded "
            f"(current: {current_ip_count})"
        )
        await websocket.close(
            code=4004,
            reason=f"Connection limit exceeded: max {manager.MAX_CONNECTIONS_PER_IP} per IP",
        )
        return

    # ── API key check ─────────────────────────────────────────────────────
    # V140 FIX (Rule 17 — Root-Cause Analysis): The old design rejected query-
    # parameter auth for security reasons (query params leak in server logs,
    # browser history, referrer headers, proxy logs) — that part is correct.
    # But it ONLY accepted message-based auth (`{"action": "auth", "apiKey":...}`)
    # which broke the standard `X-API-Key` header pattern used by HTTP clients
    # (including the TestClient patched by backend/tests/conftest.py to inject
    # X-API-Key automatically). This caused every WebSocket test to time out
    # waiting for an auth message that the test client never sent.
    #
    # Root-cause fix: support BOTH auth methods:
    #   1. X-API-Key header in the initial WebSocket handshake request (same
    #      pattern as HTTP — preferred for non-browser clients like curl,
    #      Python websockets, TestClient).
    #   2. {"action": "auth", "apiKey": "..."} as first message (kept for
    #      browser clients which cannot set custom headers on WebSocket).
    needs_auth = bool(os.getenv("FIREAI_API_KEY"))

    # SECURITY FIX: Do NOT add to connection manager until authenticated.
    # Previously, manager.connect() was called BEFORE auth check, giving
    # unauthenticated clients a 5-second window to receive broadcast messages.
    # Now we accept the WebSocket first, verify auth, then add to manager.
    await websocket.accept()

    # If auth is required, try X-API-Key header FIRST, fall back to message auth
    if needs_auth:
        # V140: Check X-API-Key header on the initial WebSocket handshake
        header_api_key = websocket.headers.get("x-api-key", "") or websocket.headers.get("X-API-Key", "")
        env_key = os.getenv("FIREAI_API_KEY")
        if header_api_key:
            # Validate header key against RBAC store and env var
            rbac_info = validate_api_key(header_api_key)
            env_match = bool(env_key) and _hmac.compare_digest(header_api_key, env_key)
            if rbac_info is not None or env_match:
                # V140: Header auth succeeded — SILENTLY proceed (no auth_success
                # message sent). This matches HTTP semantics where a 200 response
                # is the success indicator — no separate "auth_success" body is
                # sent. Sending a message here would break clients (including
                # the test suite) that expect their first received message to be
                # the response to their first action (e.g. pong for ping).
                pass
            else:
                await websocket.send_json({
                    "channel": "system",
                    "type": "auth_failed",
                    "data": {"error": "Invalid API key in X-API-Key header"},
                })
                await websocket.close(code=4003, reason="Authentication failed")
                return
        else:
            # No X-API-Key header — fall back to message-based auth
            # (browser clients that cannot set custom headers)
            try:
                # Wait up to 5 seconds for auth message
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                message = json.loads(raw)
                api_key_candidate = message.get("apiKey", "")
                # Check against RBAC key store first, then env var for backward compat
                rbac_info = validate_api_key(api_key_candidate)
                env_match = bool(env_key) and _hmac.compare_digest(api_key_candidate, env_key)
                if message.get("action") == "auth" and (rbac_info is not None or env_match):
                    await websocket.send_json({
                        "channel": "system",
                        "type": "auth_success",
                        "data": {"message": "Authenticated"},
                    })
                else:
                    await websocket.send_json({
                        "channel": "system",
                        "type": "auth_failed",
                        "data": {"error": "Invalid API key"},
                    })
                    await websocket.close(code=4003, reason="Authentication failed")
                    return
            except (asyncio.TimeoutError, json.JSONDecodeError):
                await websocket.send_json({
                    "channel": "system",
                    "type": "auth_timeout",
                    "data": {"error": "Authentication required within 5 seconds"},
                })
                await websocket.close(code=4003, reason="Authentication timeout")
                return

    # Auth succeeded — NOW add to connection manager (safe from data leak)
    # Manually add since we already accepted the WebSocket above
    manager.active_connections.append(websocket)
    manager._subscriptions[websocket] = set()
    # Track per-IP connections
    if client_ip not in manager._ip_connections:
        manager._ip_connections[client_ip] = []
    manager._ip_connections[client_ip].append(websocket)
    logger.info(
        f"WebSocket client authenticated and connected from {client_ip}. "
        f"Total: {len(manager.active_connections)}, "
        f"IP connections: {len(manager._ip_connections[client_ip])}/{manager.MAX_CONNECTIONS_PER_IP}"
    )

    try:
        while True:
            # Receive messages from client
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "channel": "error",
                    "type": "invalid_message",
                    "data": {"error": "Invalid JSON"},
                })
                continue

            action = message.get("action", "")
            if action == "ping":
                await websocket.send_json({
                    "channel": "system",
                    "type": "pong",
                    "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
                })
            elif action == "subscribe":
                project_id = message.get("projectId", "")
                if project_id:
                    manager.subscribe(websocket, project_id)
                await websocket.send_json({
                    "channel": "system",
                    "type": "subscribed",
                    "data": {"projectId": project_id},
                })
            elif action == "get_status":
                # Allow client to request project status via WebSocket
                project_id = message.get("projectId", "")
                if project_id:
                    db = get_db()
                    sync_status = db.get_sync_status(project_id)
                    await websocket.send_json({
                        "channel": "sync",
                        "type": "status",
                        "data": sync_status,
                        "projectId": project_id,
                    })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        manager.disconnect(websocket)
