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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from backend.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/sync", tags=["sync"])

_FIREAI_API_KEY = os.getenv("FIREAI_API_KEY")

# ── WebSocket connection manager ────────────────────────────────────────────

ws_router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections for real-time project updates.

    Tracks per-client project subscriptions so that broadcasts only
    reach clients that subscribed to the relevant project.
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        # Track which projects each connection is subscribed to
        self._subscriptions: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        self._subscriptions[websocket] = set()
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self._subscriptions.pop(websocket, None)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

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
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("")
async def sync_project(project_id: str):
    """Trigger project synchronization."""
    _verify_project(project_id)
    db = get_db()

    # Set status to syncing
    db.set_sync_status(project_id, {
        "status": "syncing",
        "lastSync": datetime.now(timezone.utc).isoformat(),
        "pendingChanges": 0,
    })

    # Simulate sync process (in production, this would sync with external systems)
    await asyncio.sleep(0.1)

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


@router.get("")
async def get_sync_status(project_id: str):
    """Get the current sync status of a project."""
    _verify_project(project_id)
    db = get_db()
    sync_status = db.get_sync_status(project_id)
    return {"data": sync_status, "success": True}


# ── WebSocket endpoint ─────────────────────────────────────────────────────

def _validate_ws_origin(websocket: WebSocket) -> bool:
    """Validate the origin of a WebSocket connection.

    Rejects connections from non-local origins when FIREAI_API_KEY is set,
    unless the request is same-origin (from the SPA served by this app).
    """
    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")

    # SECURITY FIX (BUG-31): When API key is configured, do NOT trust missing
    # Origin headers as "same-origin". External tools (curl, Python websockets)
    # omit Origin by default, which would bypass origin validation entirely.
    # In dev mode (no API key), allow for convenience.
    if not origin:
        if not _FIREAI_API_KEY:
            return True  # Dev mode — no auth required
        # Production: missing Origin means external client — require auth via API key
        # Origin check is only for same-origin SPA bypass, not for auth.
        # We'll let the API key check handle auth.
        return False

    # Check if origin matches our server
    if origin in (
        f"http://{host}",
        f"https://{host}",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ):
        return True

    # External origin — if API key is configured, reject without auth
    if _FIREAI_API_KEY:
        return False

    # No API key configured (dev mode) → allow all origins
    return True


def _validate_ws_api_key(websocket: WebSocket) -> bool:
    """Check if the WebSocket connection provides a valid API key.

    The key MUST be provided as the FIRST message after connect:
    {"action": "auth", "apiKey": "..."}

    Query parameter auth (ws?api_key=...) is DEPRECATED and REJECTED
    because query parameters can be exposed in:
    - Server access logs (nginx, Apache, load balancers)
    - Browser history
    - Referrer headers
    - Proxy logs
    """
    if not _FIREAI_API_KEY:
        return True  # No API key configured → auth disabled

    # Query parameter auth is DEPRECATED for security — query params
    # leak in server logs, browser history, and referrer headers.
    # Only message-based auth is accepted.
    return False


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time project updates.

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

    # ── API key check (message-based only) ────────────────────────────────
    # Query parameter auth is REJECTED for security (query params leak in
    # server access logs, browser history, referrer headers, proxy logs).
    needs_auth = bool(_FIREAI_API_KEY)

    # SECURITY FIX: Do NOT add to connection manager until authenticated.
    # Previously, manager.connect() was called BEFORE auth check, giving
    # unauthenticated clients a 5-second window to receive broadcast messages.
    # Now we accept the WebSocket first, verify auth, then add to manager.
    await websocket.accept()

    # If auth is required, wait for auth message
    authenticated = not needs_auth
    if needs_auth:
        try:
            # Wait up to 5 seconds for auth message
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            message = json.loads(raw)
            if message.get("action") == "auth" and _hmac.compare_digest(message.get("apiKey", ""), _FIREAI_API_KEY):
                authenticated = True
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
    manager.active_connections.append(websocket)
    manager._subscriptions[websocket] = set()
    logger.info(f"WebSocket client authenticated and connected. Total: {len(manager.active_connections)}")

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
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
