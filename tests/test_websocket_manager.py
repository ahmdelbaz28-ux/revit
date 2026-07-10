"""
test_websocket_manager.py — Tests for fireai/core/websocket_manager.py

Verifies WebSocket connection management, API key authentication, and
message broadcasting.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from fireai.core.websocket_manager import (
    ConnectionManager,
    _init_api_keys,
    verify_api_key_ws,
)


class TestApiKeyVerification:
    """Test verify_api_key_ws function."""

    def test_verify_valid_key(self, monkeypatch):
        """Valid API key should be accepted."""
        monkeypatch.setenv("FIREAI_API_KEY", "test-secret-key-123")
        _init_api_keys()
        result = verify_api_key_ws("test-secret-key-123")
        assert result == "test-secret-key-123"

    def test_verify_missing_key_raises_401(self):
        """Missing API key should raise HTTPException 401."""
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key_ws(None)
        assert exc_info.value.status_code == 401

    def test_verify_empty_key_raises_401(self):
        """Empty API key should raise HTTPException 401."""
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key_ws("")
        assert exc_info.value.status_code == 401

    def test_verify_wrong_key_raises_401(self, monkeypatch):
        """Wrong API key should raise HTTPException 401."""
        monkeypatch.setenv("FIREAI_API_KEY", "correct-key")
        _init_api_keys()
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key_ws("wrong-key")
        assert exc_info.value.status_code == 401


class TestConnectionManager:
    """Test ConnectionManager class methods."""

    @pytest.fixture
    def manager(self):
        """Fresh ConnectionManager for each test."""
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket for testing."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        return ws

    @pytest.fixture(autouse=True)
    def setup_api_key(self, monkeypatch):
        """Set up a known API key for all tests."""
        monkeypatch.setenv("FIREAI_API_KEY", "test-key-for-manager")
        _init_api_keys()

    def test_manager_starts_empty(self, manager):
        """New ConnectionManager should have no connections."""
        assert manager.get_active_connections() == []
        assert manager.is_connected("any-client") is False

    @pytest.mark.asyncio
    async def test_connect_valid_client(self, manager, mock_websocket):
        """Valid client with API key should connect."""
        await manager.connect(mock_websocket, "client-1", "test-key-for-manager")
        assert manager.is_connected("client-1") is True
        assert "client-1" in manager.get_active_connections()
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_invalid_api_key_raises(self, manager, mock_websocket):
        """Invalid API key should raise HTTPException."""
        with pytest.raises(HTTPException):
            await manager.connect(mock_websocket, "client-1", "wrong-key")
        assert manager.is_connected("client-1") is False

    @pytest.mark.asyncio
    async def test_disconnect(self, manager, mock_websocket):
        """Disconnect should remove client from active connections."""
        await manager.connect(mock_websocket, "client-1", "test-key-for-manager")
        assert manager.is_connected("client-1") is True
        manager.disconnect(mock_websocket)
        assert manager.is_connected("client-1") is False

    @pytest.mark.asyncio
    async def test_disconnect_unknown_websocket(self, manager, mock_websocket):
        """Disconnect with unknown websocket should not raise."""
        manager.disconnect(mock_websocket)  # should not raise

    @pytest.mark.asyncio
    async def test_send_personal_message_success(self, manager, mock_websocket):
        """send_personal_message to connected client should return True."""
        await manager.connect(mock_websocket, "client-1", "test-key-for-manager")
        result = await manager.send_personal_message("hello", "client-1")
        assert result is True
        mock_websocket.send_text.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_send_personal_message_unknown_client(self, manager):
        """send_personal_message to unknown client should return False."""
        result = await manager.send_personal_message("hello", "unknown")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_personal_message_failure_disconnects(self, manager, mock_websocket):
        """send_personal_message that fails should disconnect the client."""
        mock_websocket.send_text.side_effect = RuntimeError("connection closed")
        await manager.connect(mock_websocket, "client-1", "test-key-for-manager")
        result = await manager.send_personal_message("hello", "client-1")
        assert result is False
        assert manager.is_connected("client-1") is False

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, manager):
        """Broadcast should send to all connected clients."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await manager.connect(ws1, "client-1", "test-key-for-manager")
        await manager.connect(ws2, "client-2", "test-key-for-manager")

        count = await manager.broadcast("broadcast-message")
        assert count == 2
        ws1.send_text.assert_called_once_with("broadcast-message")
        ws2.send_text.assert_called_once_with("broadcast-message")

    @pytest.mark.asyncio
    async def test_broadcast_no_clients(self, manager):
        """Broadcast with no clients should return 0."""
        count = await manager.broadcast("message")
        assert count == 0

    @pytest.mark.asyncio
    async def test_broadcast_partial_failure(self, manager):
        """Broadcast should continue even if some clients fail."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock(side_effect=RuntimeError("fail"))

        await manager.connect(ws1, "client-1", "test-key-for-manager")
        await manager.connect(ws2, "client-2", "test-key-for-manager")

        count = await manager.broadcast("msg")
        assert count == 1  # only ws1 succeeded
        assert manager.is_connected("client-1") is True
        assert manager.is_connected("client-2") is False  # ws2 was disconnected

    @pytest.mark.asyncio
    async def test_reconnect_same_client_id(self, manager, mock_websocket):
        """Connecting with same client_id should replace old connection."""
        await manager.connect(mock_websocket, "client-1", "test-key-for-manager")
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        await manager.connect(ws2, "client-1", "test-key-for-manager")
        assert manager.is_connected("client-1") is True
        connections = manager.get_active_connections()
        assert connections == ["client-1"]
