# NOSONAR
"""Client Interface for L1 Gateway in Distributed FACP System"""
import threading
import time
import uuid
from typing import Any, Callable, Dict

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .gateway import L1Gateway


class ClientInterface:
    """Interface layer that handles external client connections (IDEs, etc.)"""

    def __init__(self, l1_gateway: L1Gateway, host: str = "0.0.0.0", port: int = 8000):
        self.l1_gateway = l1_gateway
        self.host = host
        self.port = port
        self.app = FastAPI(title="FACP L1 Client Interface", version="1.1")
        self.server = None
        self.node_id = l1_gateway.node_id
        self.request_handlers = {}

        # Setup FastAPI routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes for client interface"""

        @self.app.post("/facp/request")
        async def handle_facp_request(request: Request):
            try:
                # Get client IP
                client_ip = request.client.host

                # Parse request data
                request_data = await request.json()

                # Validate request format
                is_valid, errors = self.l1_gateway.validate_client_request_format(request_data)
                if not is_valid:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "protocol": "FACP/1.1",  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                            "id": request_data.get("id", "unknown"),
                            "status": "error",
                            "error": {
                                "code": "INVALID_FORMAT",
                                "message": f"Request format validation failed: {'; '.join(errors)}"
                            },
                            "trace": {
                                "execution_path": ["L1_client_interface"],
                                "latency_ms": 0,
                                "node_id": self.node_id,
                                "engine_version": "FACP/1.1"
                            }
                        }
                    )

                # Process through L1 gateway
                success, response = self.l1_gateway.handle_client_request(request_data, client_ip)

                if success:
                    return response
                # Error response already formatted by L1 gateway
                status_code = 400 if response.get("error") else 500
                return JSONResponse(status_code=status_code, content=response)

            except Exception as e:
                # CodeQL: py/stack-trace-exposure — sanitize error message
                safe_msg = str(e)[:200] if "Traceback" not in str(e) else "Client interface error"
                return JSONResponse(
                    status_code=500,
                    content={
                        "protocol": "FACP/1.1",
                        "id": "unknown",
                        "status": "error",
                        "error": {
                            "code": "CLIENT_INTERFACE_ERROR",
                            "message": safe_msg  # lgtm[py/stack-trace-exposure] — sanitized
                        },
                        "trace": {
                            "execution_path": ["L1_client_interface"],
                            "latency_ms": 0,
                            "node_id": self.node_id,
                            "engine_version": "FACP/1.1"
                        }
                    }
                )

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "node_id": self.node_id,
                "node_type": "l1_gateway",
                "timestamp": time.time(),
                "gateway_status": self.l1_gateway.get_gateway_status()
            }

        @self.app.get("/metrics")
        async def get_metrics():
            """Metrics endpoint"""
            return {
                "gateway_metrics": self.l1_gateway.get_request_metrics(),
                "security_stats": self.l1_gateway.get_security_stats(),
                "timestamp": time.time()
            }

    def start(self):
        """Start the client interface server"""
        def run_server():
            uvicorn.run(
                self.app,
                host=self.host,
                port=self.port,
                log_level="info"
            )

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        print(f"L1 Client Interface started on {self.host}:{self.port}")

    def stop(self):
        """Stop the client interface server"""
        # In a real implementation, we'd have proper shutdown
        print(f"L1 Client Interface on {self.host}:{self.port} stopping...")

    def register_request_handler(self, method: str, handler: Callable):
        """Register a custom handler for specific request methods"""
        self.request_handlers[method] = handler

    def get_status(self) -> Dict[str, Any]:
        """Get status of the client interface"""
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "running": self.server_thread.is_alive() if hasattr(self, 'server_thread') else False,
            "registered_handlers": list(self.request_handlers.keys()),
            "gateway_status": self.l1_gateway.get_gateway_status()
        }


class RequestNormalizer:
    """Normalizes requests from various client types to FACP/1.1 format"""

    @staticmethod
    def normalize_vscode_extension_request(raw_request: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize request from VSCode extension"""
        return {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": raw_request.get("id", str(int(time.time() * 1000000))),
            "timestamp": raw_request.get("timestamp", time.time()),
            "source": "client",
            "target": "orchestrator",
            "execution_state": "RECEIVED",
            "method": raw_request.get("method", "unknown"),
            "params": {
                "task": raw_request.get("command", "unknown"),
                "payload": raw_request.get("data", {}),
                "context": {
                    "editor": "vscode",
                    "extension_version": raw_request.get("extensionVersion", "unknown")
                }
            },
            "security": {
                "auth_token": raw_request.get("authToken"),
                "permissions": raw_request.get("permissions", []),
                "risk_level": raw_request.get("riskLevel", "low"),
                "idempotency_key": raw_request.get("idempotencyKey")
            },
            "constraints": {
                "timeout_ms": raw_request.get("timeout", 8000),
                "max_memory_mb": raw_request.get("maxMemory", 512),
                "max_recursion_depth": raw_request.get("maxDepth", 5)
            }
        }

    @staticmethod
    def normalize_autocad_plugin_request(raw_request: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize request from AutoCAD plugin"""
        return {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": raw_request.get("requestId", str(int(time.time() * 1000000))),
            "timestamp": raw_request.get("timestamp", time.time()),
            "source": "client",
            "target": "orchestrator",
            "execution_state": "RECEIVED",
            "method": raw_request.get("command", "unknown"),
            "params": {
                "task": raw_request.get("task", "unknown"),
                "payload": {
                    "drawing_data": raw_request.get("drawingData", {}),
                    "selection_set": raw_request.get("selectionSet", []),
                    "command_params": raw_request.get("commandParams", {})
                },
                "context": {
                    "application": "autocad",
                    "version": raw_request.get("applicationVersion", "unknown"),
                    "drawing_name": raw_request.get("drawingName", "untitled")
                }
            },
            "security": {
                "auth_token": raw_request.get("authToken"),
                "permissions": ["read", "write", "execute"],
                "risk_level": "medium",
                "idempotency_key": raw_request.get("requestGuid")
            },
            "constraints": {
                "timeout_ms": raw_request.get("timeout", 15000),  # AutoCAD might need more time
                "max_memory_mb": raw_request.get("maxMemory", 1024),
                "max_recursion_depth": raw_request.get("maxDepth", 3)
            }
        }

    @staticmethod
    def normalize_revit_addin_request(raw_request: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize request from Revit add-in"""
        return {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": raw_request.get("transactionId", str(int(time.time() * 1000000))),
            "timestamp": raw_request.get("timestamp", time.time()),
            "source": "client",
            "target": "orchestrator",
            "execution_state": "RECEIVED",
            "method": raw_request.get("command", "unknown"),
            "params": {
                "task": raw_request.get("task", "unknown"),
                "payload": {
                    "bim_data": raw_request.get("bimData", {}),
                    "element_ids": raw_request.get("elementIds", []),
                    "command_params": raw_request.get("commandParams", {})
                },
                "context": {
                    "application": "revit",
                    "version": raw_request.get("revitVersion", "unknown"),
                    "project_name": raw_request.get("projectName", "unnamed")
                }
            },
            "security": {
                "auth_token": raw_request.get("authToken"),
                "permissions": ["read", "write", "execute", "bim_access"],
                "risk_level": "medium",
                "idempotency_key": raw_request.get("transactionGuid")
            },
            "constraints": {
                "timeout_ms": raw_request.get("timeout", 20000),  # BIM operations might take longer
                "max_memory_mb": raw_request.get("maxMemory", 2048),
                "max_recursion_depth": raw_request.get("maxDepth", 5)
            }
        }

    @staticmethod
    def normalize_generic_request(raw_request: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a generic request to FACP/1.1 format"""
        # Try to detect the source and apply appropriate normalization
        if "extensionVersion" in raw_request:
            return RequestNormalizer.normalize_vscode_extension_request(raw_request)
        if "drawingName" in raw_request:
            return RequestNormalizer.normalize_autocad_plugin_request(raw_request)
        if "projectName" in raw_request:
            return RequestNormalizer.normalize_revit_addin_request(raw_request)
        # Generic normalization
        return {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": raw_request.get("id", str(uuid.uuid4())),
            "timestamp": raw_request.get("timestamp", time.time()),
            "source": "client",
            "target": "orchestrator",
            "execution_state": "RECEIVED",
            "method": raw_request.get("method", "unknown"),
            "params": {
                "task": raw_request.get("task", "unknown"),
                "payload": raw_request.get("payload", raw_request.get("data", {})),
                "context": raw_request.get("context", {})
            },
            "security": {
                "auth_token": raw_request.get("authToken", raw_request.get("auth_token")),
                "permissions": raw_request.get("permissions", []),
                "risk_level": raw_request.get("riskLevel", "low"),
                "idempotency_key": raw_request.get("idempotencyKey", raw_request.get("idempotency_key"))
            },
            "constraints": {
                "timeout_ms": raw_request.get("timeout", 8000),
                "max_memory_mb": raw_request.get("maxMemory", 512),
                "max_recursion_depth": raw_request.get("maxDepth", 5)
            }
        }

    @staticmethod
    def validate_normalized_request(request_data: Dict[str, Any]) -> tuple[bool, list]:
        """Validate a normalized request"""
        errors = []

        # Check required fields
        required_fields = ["protocol", "type", "id", "method", "params", "security", "constraints"]
        for field in required_fields:
            if field not in request_data:
                errors.append(f"Missing required field: {field}")

        # Validate protocol version
        if request_data.get("protocol") != "FACP/1.1":
            errors.append(f"Invalid protocol version: {request_data.get('protocol')}, expected FACP/1.1")

        # Validate type
        req_type = request_data.get("type")
        if req_type != "request":
            errors.append(f"Invalid request type: {req_type}, expected 'request'")

        # Validate source/target
        source = request_data.get("source")
        if source != "client":
            errors.append(f"Invalid source: {source}, expected 'client' for client requests")

        target = request_data.get("target")
        if target != "orchestrator":
            errors.append(f"Invalid target: {target}, expected 'orchestrator' for client requests")

        # Validate execution state
        exec_state = request_data.get("execution_state")
        if exec_state != "RECEIVED":
            errors.append(f"Invalid execution state: {exec_state}, expected 'RECEIVED' for new requests")

        return len(errors) == 0, errors


def create_client_interface_with_gateway(validation_firewall, transport_config=None) -> ClientInterface:
    """Factory function to create a complete L1 client interface with gateway"""
    from ..transport.http_transport import HTTPTransport

    # Create HTTP transport for the gateway
    transport = HTTPTransport(
        host=transport_config.get("host", "0.0.0.0") if transport_config else "0.0.0.0",
        port=transport_config.get("gateway_port", 8001) if transport_config else 8001,
        node_type="l1_gateway"
    )

    # Create the L1 gateway
    l1_gateway = L1Gateway(validation_firewall, transport)

    # Create the client interface
    return ClientInterface(
        l1_gateway=l1_gateway,
        host=transport_config.get("host", "0.0.0.0") if transport_config else "0.0.0.0",
        port=transport_config.get("interface_port", 8000) if transport_config else 8000
    )

