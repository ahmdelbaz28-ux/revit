#!/usr/bin/env python3
"""WebSocket connection manager for FastAPI with API key verification.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Dict, List, Optional

from fastapi import HTTPException, WebSocket
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

_EFFECTIVE_API_KEYS: set[str] = set()


def _init_api_keys() -> None:
    global _EFFECTIVE_API_KEYS
    keys_str = os.environ.get("FIREAI_API_KEYS", "")
    if keys_str:
        _EFFECTIVE_API_KEYS = {k.strip() for k in keys_str.split(",") if k.strip()}
    else:
        single_key = os.environ.get("FIREAI_API_KEY")
        if single_key:
            _EFFECTIVE_API_KEYS = {single_key}
        else:
            generated = secrets.token_urlsafe(32)
            logger.warning(
                "FIREAI_API_KEYS not set — auto-generated for dev: %s",
                generated[:8] + "...",
            )
            _EFFECTIVE_API_KEYS = {generated}


_init_api_keys()


def verify_api_key_ws(api_key: Optional[str] = None) -> str:
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required. Pass X-API-Key header.")
    if not any(secrets.compare_digest(api_key, valid_key) for valid_key in _EFFECTIVE_API_KEYS):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return api_key


class ConnectionManager:
    def __init__(self):
        self._active_connections: Dict[str, WebSocket] = {}
        self._connection_keys: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, client_id: str, api_key: Optional[str] = None) -> None:
        verify_api_key_ws(api_key)
        await websocket.accept()
        self._active_connections[client_id] = websocket
        self._connection_keys[websocket] = client_id
        logger.info("WebSocket client %s connected", client_id)

    def disconnect(self, websocket: WebSocket) -> None:
        client_id = self._connection_keys.pop(websocket, None)
        if client_id and client_id in self._active_connections:
            del self._active_connections[client_id]
        logger.info("WebSocket client disconnected")

    async def send_personal_message(self, message: str, client_id: str) -> bool:
        websocket = self._active_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_text(message)
                return True
            except Exception as e:
                logger.error("Failed to send message to %s: %s", client_id, e)
                self.disconnect(websocket)
        return False

    async def broadcast(self, message: str) -> int:
        sent_count = 0
        for client_id, websocket in list(self._active_connections.items()):
            try:
                await websocket.send_text(message)
                sent_count += 1
            except Exception as e:
                logger.error("Failed to broadcast to %s: %s", client_id, e)
                self.disconnect(websocket)
        return sent_count

    def get_active_connections(self) -> List[str]:
        return list(self._active_connections.keys())

    def is_connected(self, client_id: str) -> bool:
        return client_id in self._active_connections


manager = ConnectionManager()
