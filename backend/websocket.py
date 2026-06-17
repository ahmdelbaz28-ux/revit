"""backend/websocket.py — WebSocket Manager.
=======================================

Real-time WebSocket communication for the CAD/BIM Integration Platform.
Provides progress tracking, notifications, and real-time updates.

Features:
- Connection management with room support
- Broadcasting to multiple clients
- Progress updates for long operations
- Event subscriptions
- Authentication via token
- Automatic reconnection handling

Usage:
    from backend.websocket import ws_manager, ConnectionManager

    # Send progress update
    await ws_manager.send_progress(task_id, 50, "Processing...")

    # Broadcast to room
    await ws_manager.broadcast_to_room("project-123", {"type": "update", "data": ...})

    # Notify specific user
    await ws_manager.notify_user(user_id, {"type": "notification", "message": "Done!"})
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class MessageType(str, Enum):
    """WebSocket message types."""

    PROGRESS = "progress"
    NOTIFICATION = "notification"
    UPDATE = "update"
    ERROR = "error"
    COMPLETE = "complete"
    HEARTBEAT = "heartbeat"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


@dataclass
class WSMessage:
    """WebSocket message structure."""

    type: MessageType
    data: Any
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    room: str | None = None
    user_id: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "type": self.type.value if isinstance(self.type, MessageType) else self.type,
            "data": self.data,
            "timestamp": self.timestamp,
            "room": self.room,
            "user_id": self.user_id
        })

    @classmethod
    def from_json(cls, data: str) -> WSMessage | None:
        """Deserialize from JSON string."""
        try:
            parsed = json.loads(data)
            return cls(
                type=MessageType(parsed.get("type", "update")),
                data=parsed.get("data"),
                timestamp=parsed.get("timestamp", datetime.now(timezone.utc).timestamp()),
                room=parsed.get("room"),
                user_id=parsed.get("user_id")
            )
        except (json.JSONDecodeError, KeyError):
            return None


@dataclass
class Room:
    """WebSocket room for broadcasting."""

    name: str
    connections: set[str] = field(default_factory=set)  # connection_ids
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


class ConnectionManager:
    """Manages WebSocket connections with room support.

    Features:
    - Connection pool with unique IDs
    - Room-based broadcasting
    - User-specific messaging
    - Event subscriptions
    - Heartbeat/keep-alive
    """

    def __init__(self) -> None:
        # connection_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        # connection_id -> metadata
        self._metadata: dict[str, dict] = {}
        # room_name -> Room
        self._rooms: dict[str, Room] = {}
        # user_id -> set of connection_ids
        self._user_connections: dict[str, set[str]] = {}
        # task_id -> list of connection_ids (for progress updates)
        self._task_subscribers: dict[str, set[str]] = {}
        # Heartbeat task
        self._heartbeat_task: asyncio.Task | None = None
        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info("WebSocket ConnectionManager initialized")

    async def start(self) -> None:
        """Start background tasks."""
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("WebSocket heartbeat task started")

    async def stop(self) -> None:
        """Stop all connections and background tasks."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        async with self._lock:
            for ws in self._connections.values():
                with contextlib.suppress(Exception):
                    await ws.close()

        self._connections.clear()
        self._metadata.clear()
        self._rooms.clear()
        self._user_connections.clear()
        self._task_subscribers.clear()

        logger.info("WebSocket ConnectionManager stopped")

    async def connect(self, websocket: WebSocket, user_id: str | None = None,
                      room: str | None = None) -> str:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
            user_id: Optional user identifier
            room: Optional room to join immediately

        Returns:
            connection_id: Unique identifier for this connection

        """
        await websocket.accept()

        async with self._lock:
            # Generate unique connection ID
            import secrets
            connection_id = f"conn_{secrets.token_hex(8)}"

            # Store connection
            self._connections[connection_id] = websocket
            self._metadata[connection_id] = {
                "user_id": user_id,
                "connected_at": datetime.now(timezone.utc).timestamp(),
                "rooms": set(),
                "subscriptions": set()
            }

            # Track user connections
            if user_id:
                if user_id not in self._user_connections:
                    self._user_connections[user_id] = set()
                self._user_connections[user_id].add(connection_id)

            # Join room if specified
            if room:
                await self.join_room(connection_id, room)

            logger.info(f"WebSocket connected: {connection_id}, user: {user_id}, room: {room}")

            return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Remove a connection."""
        async with self._lock:
            if connection_id not in self._connections:
                return

            # Get metadata
            meta = self._metadata.pop(connection_id, {})

            # Remove from all rooms
            for room_name in meta.get("rooms", set()):
                if room_name in self._rooms:
                    self._rooms[room_name].connections.discard(connection_id)

            # Remove from task subscribers
            for task_id in meta.get("subscriptions", set()):
                if task_id in self._task_subscribers:
                    self._task_subscribers[task_id].discard(connection_id)

            # Remove user connection
            user_id = meta.get("user_id")
            if user_id and user_id in self._user_connections:
                self._user_connections[user_id].discard(connection_id)
                if not self._user_connections[user_id]:
                    del self._user_connections[user_id]

            # Close websocket
            ws = self._connections.pop(connection_id, None)
            if ws:
                with contextlib.suppress(Exception):
                    await ws.close()

            logger.info(f"WebSocket disconnected: {connection_id}")

    async def join_room(self, connection_id: str, room_name: str) -> None:
        """Join a room."""
        async with self._lock:
            if connection_id not in self._connections:
                return

            if room_name not in self._rooms:
                self._rooms[room_name] = Room(name=room_name)

            self._rooms[room_name].connections.add(connection_id)
            self._metadata[connection_id]["rooms"].add(room_name)

            logger.debug(f"Connection {connection_id} joined room {room_name}")

    async def leave_room(self, connection_id: str, room_name: str) -> None:
        """Leave a room."""
        async with self._lock:
            if room_name in self._rooms:
                self._rooms[room_name].connections.discard(connection_id)
                if not self._rooms[room_name].connections:
                    del self._rooms[room_name]

            if connection_id in self._metadata:
                self._metadata[connection_id]["rooms"].discard(room_name)

    async def subscribe_to_task(self, connection_id: str, task_id: str) -> None:
        """Subscribe to progress updates for a specific task."""
        async with self._lock:
            if task_id not in self._task_subscribers:
                self._task_subscribers[task_id] = set()
            self._task_subscribers[task_id].add(connection_id)
            self._metadata[connection_id]["subscriptions"].add(task_id)

    async def send_to_connection(self, connection_id: str, message: WSMessage) -> bool:
        """Send message to a specific connection."""
        if connection_id not in self._connections:
            return False

        try:
            ws = self._connections[connection_id]
            await ws.send_text(message.to_json())
            return True
        except Exception as e:
            logger.warning(f"Failed to send to {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False

    async def send_to_user(self, user_id: str, message: WSMessage) -> int:
        """Send message to all connections of a user. Returns count of successful sends."""
        if user_id not in self._user_connections:
            return 0

        count = 0
        for connection_id in list(self._user_connections[user_id]):
            if await self.send_to_connection(connection_id, message):
                count += 1

        return count

    async def broadcast_to_room(self, room_name: str, message: WSMessage | dict,
                                exclude: list[str] | None = None) -> int:
        """Broadcast message to all connections in a room.

        Args:
            room_name: Room to broadcast to
            message: Message to send
            exclude: Optional list of connection_ids to exclude

        Returns:
            Number of successful sends

        """
        if isinstance(message, dict):
            message = WSMessage(type=MessageType.UPDATE, data=message)
        message.room = room_name

        if room_name not in self._rooms:
            return 0

        exclude = set(exclude or [])
        count = 0

        for connection_id in list(self._rooms[room_name].connections - exclude):
            if await self.send_to_connection(connection_id, message):
                count += 1

        return count

    async def broadcast_all(self, message: WSMessage | dict) -> int:
        """Broadcast to all connected clients."""
        if isinstance(message, dict):
            message = WSMessage(type=MessageType.UPDATE, data=message)

        count = 0
        for connection_id in list(self._connections.keys()):
            if await self.send_to_connection(connection_id, message):
                count += 1

        return count

    # ─── Convenience Methods ────────────────────────────────────────────────

    async def send_progress(self, task_id: str, progress: int, status: str,
                           data: dict | None = None) -> None:
        """Send progress update to task subscribers."""
        message = WSMessage(
            type=MessageType.PROGRESS,
            data={
                "task_id": task_id,
                "progress": progress,
                "status": status,
                "data": data or {}
            }
        )

        if task_id in self._task_subscribers:
            for connection_id in list(self._task_subscribers[task_id]):
                await self.send_to_connection(connection_id, message)

    async def notify(self, room: str, message: str, level: str = "info") -> None:
        """Send notification to a room."""
        ws_msg = WSMessage(
            type=MessageType.NOTIFICATION,
            data={"message": message, "level": level}
        )
        await self.broadcast_to_room(room, ws_msg)

    async def notify_user(self, user_id: str, notification: dict) -> None:
        """Send notification to a specific user."""
        message = WSMessage(type=MessageType.NOTIFICATION, data=notification)
        await self.send_to_user(user_id, message)

    async def notify_error(self, room: str, error: str, task_id: str | None = None) -> None:
        """Send error notification to a room."""
        data = {"error": error}
        if task_id:
            data["task_id"] = task_id
        message = WSMessage(type=MessageType.ERROR, data=data)
        await self.broadcast_to_room(room, message)

    async def complete_task(self, task_id: str, result: dict) -> None:
        """Send task completion to subscribers."""
        message = WSMessage(
            type=MessageType.COMPLETE,
            data={"task_id": task_id, "result": result}
        )

        if task_id in self._task_subscribers:
            for connection_id in list(self._task_subscribers[task_id]):
                await self.send_to_connection(connection_id, message)

    # ─── Background Tasks ────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to all connections."""
        while True:
            try:
                await asyncio.sleep(30)  # Heartbeat every 30 seconds

                message = WSMessage(
                    type=MessageType.HEARTBEAT,
                    data={"timestamp": datetime.now(timezone.utc).timestamp()}
                )

                for connection_id in list(self._connections.keys()):
                    try:
                        ws = self._connections[connection_id]
                        await ws.send_text(message.to_json())
                    except Exception:
                        await self.disconnect(connection_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")

    # ─── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self._connections),
            "total_rooms": len(self._rooms),
            "total_users": len(self._user_connections),
            "task_subscribers": sum(len(s) for s in self._task_subscribers.values()),
            "rooms": [
                {"name": r.name, "connections": len(r.connections)}
                for r in self._rooms.values()
            ]
        }


# Global connection manager
ws_manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.websocket("/client")
async def websocket_client(websocket: WebSocket, token: str | None = None,
                           room: str | None = None) -> None:
    """Main WebSocket endpoint for clients.

    Query Parameters:
    - token: JWT token for authentication (optional)
    - room: Room to join on connect (optional)

    Message Types (client -> server):
    - subscribe: {"type": "subscribe", "room": "room-name"}
    - unsubscribe: {"type": "unsubscribe", "room": "room-name"}
    - subscribe_task: {"type": "subscribe_task", "task_id": "task-123"}

    Message Types (server -> client):
    - progress: {"type": "progress", "data": {"task_id": "...", "progress": 50, ...}}
    - notification: {"type": "notification", "data": {"message": "...", "level": "info"}}
    - heartbeat: {"type": "heartbeat", "data": {"timestamp": ...}}
    """
    # Extract user_id from token if provided
    user_id = None
    if token:
        from backend.routers.auth import verify_token
        payload = verify_token(token)
        if payload:
            user_id = payload.get("sub")

    # Connect
    connection_id = await ws_manager.connect(websocket, user_id=user_id, room=room)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "connection_id": connection_id,
                "user_id": user_id,
                "room": room
            }
        })

        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
                message = WSMessage.from_json(data)

                if not message:
                    continue

                # Handle message types
                if message.type == MessageType.SUBSCRIBE:
                    room_name = message.data.get("room") if isinstance(message.data, dict) else message.data
                    if room_name:
                        await ws_manager.join_room(connection_id, room_name)
                        await websocket.send_json({
                            "type": "subscribed",
                            "data": {"room": room_name}
                        })

                elif message.type == MessageType.UNSUBSCRIBE:
                    room_name = message.data.get("room") if isinstance(message.data, dict) else message.data
                    if room_name:
                        await ws_manager.leave_room(connection_id, room_name)
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "data": {"room": room_name}
                        })

                elif message.type == MessageType.SUBSCRIBE:
                    if isinstance(message.data, dict) and "task_id" in message.data:
                        task_id = message.data["task_id"]
                        await ws_manager.subscribe_to_task(connection_id, task_id)
                        await websocket.send_json({
                            "type": "task_subscribed",
                            "data": {"task_id": task_id}
                        })

                elif message.type == MessageType.HEARTBEAT:
                    # Respond to heartbeat
                    await websocket.send_json({
                        "type": "heartbeat",
                        "data": {"timestamp": datetime.now(timezone.utc).timestamp()}
                    })

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket message error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "data": {"error": str(e)}
                })

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(connection_id)


@router.get("/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics."""
    return ws_manager.get_stats()
