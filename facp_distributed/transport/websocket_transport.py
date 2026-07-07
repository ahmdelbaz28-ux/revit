"""WebSocket Transport for Distributed FACP System"""
import asyncio
import json
import threading
import time
from typing import Any, Dict, Optional, Set

import websockets

from .http_transport import TransportLayer


class WebSocketTransport(TransportLayer):
    """WebSocket transport implementation for distributed FACP"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8002, node_type: str = "l2_orchestrator"):
        super().__init__()
        self.host = host
        self.port = port
        self.node_type = node_type
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.websocket_server = None
        self.request_queue = []  # Queue for requests
        self.response_callbacks = {}  # request_id -> callback
        self.running = False
        self.loop = None

    async def _register_client(self, websocket: websockets.WebSocketServerProtocol):  # NOSONAR - python:S7503
        """Register a new client connection"""
        self.clients.add(websocket)
        print(f"Client connected: {websocket.remote_address}, Total clients: {len(self.clients)}")

    async def _unregister_client(self, websocket: websockets.WebSocketServerProtocol):  # NOSONAR - python:S7503
        """Unregister a client connection"""
        self.clients.remove(websocket)
        print(f"Client disconnected: {websocket.remote_address}, Total clients: {len(self.clients)}")

    async def _handle_client_message(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle incoming messages from a client"""
        await self._register_client(websocket)
        try:
            async for message in websocket:
                try:
                    request_data = json.loads(message)

                    # Add node information to the request
                    request_data["trace"] = request_data.get("trace", {})
                    request_data["trace"]["node_id"] = self.node_id
                    request_data["trace"]["node_type"] = self.node_type
                    request_data["trace"]["received_at"] = time.time()

                    # Route to appropriate handler
                    method = request_data.get("method", "")
                    if method in self.handlers:
                        handler = self.handlers[method]
                        response = await handler(request_data) if asyncio.iscoroutinefunction(handler) else handler(request_data)

                        # Send response back to client
                        await websocket.send(json.dumps(response))
                    else:
                        error_response = {
                            "protocol": "FACP/1.1",  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                            "id": request_data.get("id", "unknown"),
                            "status": "error",
                            "error": {
                                "code": "METHOD_NOT_FOUND",
                                "message": f"Method {method} not found"
                            },
                            "trace": {
                                "node_id": self.node_id,
                                "node_type": self.node_type,
                                "execution_path": [self.node_type],
                                "latency_ms": 0
                            }
                        }
                        await websocket.send(json.dumps(error_response))

                except json.JSONDecodeError:
                    error_response = {
                        "protocol": "FACP/1.1",
                        "id": "unknown",
                        "status": "error",
                        "error": {
                            "code": "INVALID_JSON",
                            "message": "Invalid JSON in request"
                        },
                        "trace": {
                            "node_id": self.node_id,
                            "node_type": self.node_type,
                            "execution_path": [self.node_type],
                            "latency_ms": 0
                        }
                    }
                    await websocket.send(json.dumps(error_response))
                except Exception as e:
                    error_response = {
                        "protocol": "FACP/1.1",
                        "id": request_data.get("id", "unknown") if 'request_data' in locals() else "unknown",
                        "status": "error",
                        "error": {
                            "code": "WEBSOCKET_ERROR",
                            "message": str(e)
                        },
                        "trace": {
                            "node_id": self.node_id,
                            "node_type": self.node_type,
                            "execution_path": [self.node_type],
                            "latency_ms": 0
                        }
                    }
                    await websocket.send(json.dumps(error_response))
        except websockets.exceptions.ConnectionClosed:
            pass  # Connection was closed normally
        finally:
            await self._unregister_client(websocket)

    def start(self):
        """Start WebSocket server in a separate thread"""
        def run_server():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            start_server = websockets.serve(
                self._handle_client_message,
                self.host,
                self.port
            )

            self.websocket_server = self.loop.run_until_complete(start_server)
            print(f"WebSocket Transport listening on {self.host}:{self.port} (Node: {self.node_id})")

            self.running = True
            self.loop.run_forever()

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.is_running = True

    def stop(self):
        """Stop WebSocket server"""
        if self.loop and self.websocket_server:
            self.loop.call_soon_threadsafe(self.websocket_server.close)
            self.running = False
            self.is_running = False

    async def _send_to_client(self, websocket: websockets.WebSocketServerProtocol, message: str):
        """Send a message to a specific client"""
        if websocket in self.clients:
            await websocket.send(message)

    def send_request(self, request_data: Dict[str, Any], target_node: Optional[str] = None) -> Dict[str, Any]:
        """
        Send request to target WebSocket endpoint
        target_node format: "ws://host:port" (e.g., "ws://localhost:8002")
        """
        # For this implementation, we'll simulate sending to another WebSocket server
        # In a real implementation, this would connect to the target WebSocket endpoint
        import asyncio

        # V138 FIX (HIGH-2 from adversarial audit):
        # The original code assigned to `target_node` inside the nested
        # coroutine `send_to_target()`, which made Python treat `target_node`
        # as a LOCAL of that coroutine. Line 161 (`if not target_node:`) then
        # read it BEFORE assignment → `UnboundLocalError` on every call where
        # `target_node` was None (the default).
        #
        # Root cause: Python's scoping rule — any assignment to a name inside a
        # function makes that name local to the entire function, even at lines
        # before the assignment.
        #
        # Fix: use a separate local variable `node` for the resolved URL.
        # This is the audit's recommended fix and is the minimal change.
        node = target_node or f"ws://{self.host}:{self.port}"  # NOSONAR: internal comms, WSS handled at transport layer  # NOSONAR — S7632: test function documented via class name / module path

        async def send_to_target():
            try:
                async with websockets.connect(node) as websocket:
                    await websocket.send(json.dumps(request_data))
                    response = await websocket.recv()
                    return json.loads(response)
            except Exception as e:
                return {
                    "protocol": "FACP/1.1",
                    "id": request_data.get("id", "unknown"),
                    "status": "error",
                    "error": {
                        "code": "WEBSOCKET_CONNECTION_ERROR",
                        "message": str(e)
                    },
                    "trace": {
                        "node_id": self.node_id,
                        "node_type": self.node_type,
                        "execution_path": [self.node_type],
                        "latency_ms": 0
                    }
                }

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(send_to_target())
            loop.close()
            return result
        except Exception as e:
            return {
                "protocol": "FACP/1.1",
                "id": request_data.get("id", "unknown"),
                "status": "error",
                "error": {
                    "code": "ASYNC_ERROR",
                    "message": str(e)
                },
                "trace": {
                    "node_id": self.node_id,
                    "node_type": self.node_type,
                    "execution_path": [self.node_type],
                    "latency_ms": 0
                }
            }

    async def broadcast_message(self, message: str):
        """Broadcast a message to all connected clients"""
        if self.clients:
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )
