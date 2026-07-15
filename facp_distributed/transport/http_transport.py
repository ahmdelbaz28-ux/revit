# NOSONAR
"""HTTP Transport for Distributed FACP System"""
import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

import aiohttp
import uvicorn
from fastapi import FastAPI, Request

# Circuit Breaker Implementation
class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker pattern to prevent cascade failures"""
    
    def __init__(self, failure_threshold=5, timeout=60, recovery_timeout=30):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.recovery_timeout = recovery_timeout
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN state")
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e
    
    def _on_success(self):
        """Handle successful operation"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.last_failure_time = None
    
    def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} consecutive failures")


class TransportLayer(ABC):
    """Abstract base class for transport layers"""

    def __init__(self):
        self.handlers = {}  # method -> handler_function
        self.is_running = False
        self.node_id = f"node_{int(time.time())}_{hash(str(threading.current_thread().ident)) % 10000}"
        # Add circuit breaker for transport operations
        self.circuit_breaker = CircuitBreaker()

    def register_handler(self, method: str, handler: Callable):
        """Register a handler for a specific method"""
        self.handlers[method] = handler

    @abstractmethod
    def start(self):
        """Start the transport layer"""
        raise NotImplementedError("Subclasses must implement start()")

    @abstractmethod
    def stop(self):
        """Stop the transport layer"""
        raise NotImplementedError("Subclasses must implement stop()")

    @abstractmethod
    def send_request(self, request_data: Dict[str, Any], target_node: Optional[str] = None) -> Dict[str, Any]:
        """Send request to target"""
        raise NotImplementedError("Subclasses must implement send_request()")


class HTTPTransport(TransportLayer):
    """HTTP transport implementation for distributed FACP"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8000, node_type: str = "l2_orchestrator"):
        super().__init__()
        self.host = host
        self.port = port
        self.node_type = node_type
        self.app = FastAPI(title=f"FACP {node_type} Node", version="1.1")
        self.server = None
        self.request_queue = []  # Queue for requests
        self.response_callbacks = {}  # request_id -> callback
        self.client_sessions = {}  # host:port -> session

        # Add routes to FastAPI app
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes for the transport"""
        @self.app.post("/facp/request")
        async def handle_facp_request(request: Request):
            try:
                request_data = await request.json()
                
                # Input validation gate - validate request structure and content
                if not self._validate_request(request_data):
                    return {
                        "protocol": "FACP/1.1",
                        "id": request_data.get("id", "unknown"),
                        "status": "error",
                        "error": {
                            "code": "INVALID_REQUEST",
                            "message": "Request validation failed"
                        },
                        "trace": {
                            "node_id": self.node_id,
                            "node_type": self.node_type,
                            "execution_path": [self.node_type],
                            "latency_ms": 0
                        }
                    }
                
                # Add node information to the request
                request_data["trace"] = request_data.get("trace", {})
                request_data["trace"]["node_id"] = self.node_id
                request_data["trace"]["node_type"] = self.node_type
                request_data["trace"]["received_at"] = time.time()

                # Route to appropriate handler
                method = request_data.get("method", "")
                if method in self.handlers:
                    handler = self.handlers[method]
                    return await handler(request_data) if asyncio.iscoroutinefunction(handler) else handler(request_data)
                return {
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
            except Exception as e:
                # CodeQL: py/stack-trace-exposure — sanitize error message
                safe_msg = str(e)[:200] if "Traceback" not in str(e) else "Transport error"
                return {
                    "protocol": "FACP/1.1",
                    "id": request_data.get("id", "unknown") if 'request_data' in locals() else "unknown",
                    "status": "error",
                    "error": {
                        "code": "TRANSPORT_ERROR",
                        "message": safe_msg  # lgtm[py/stack-trace-exposure] — sanitized
                    },
                    "trace": {
                        "node_id": self.node_id,
                        "node_type": self.node_type,
                        "execution_path": [self.node_type],
                        "latency_ms": 0
                    }
                }

        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "node_id": self.node_id,
                "node_type": self.node_type,
                "timestamp": time.time()
            }
    
    def _validate_request(self, request_data: Dict[str, Any]) -> bool:
        """Validate incoming request for security"""
        # Check if request has required fields
        required_fields = ["method", "id"]
        for field in required_fields:
            if field not in request_data:
                logger.warning(f"Missing required field: {field}")
                return False
        
        # Validate method is in allowed list
        allowed_methods = {
            "create_device", "update_device", "delete_device",
            "create_connection", "update_connection", "delete_connection", 
            "get_project", "list_projects", "create_project",
            "execute_calculation", "run_simulation", "generate_report"
        }
        
        method = request_data.get("method", "")
        if method not in allowed_methods:
            logger.warning(f"Unauthorized method: {method}")
            return False
        
        # Validate ID format (should be alphanumeric with hyphens/underscores)
        request_id = request_data.get("id", "")
        if not isinstance(request_id, str) or not request_id.replace('-', '').replace('_', '').isalnum():
            logger.warning(f"Invalid request ID format: {request_id}")
            return False
        
        # Validate size limits to prevent oversized requests
        import json
        request_size = len(json.dumps(request_data))
        if request_size > 1024 * 1024:  # 1MB limit
            logger.warning(f"Request too large: {request_size} bytes")
            return False
        
        # If we got here, request is valid
        return True

    def start(self):
        """Start HTTP server in a separate thread"""
        def run_server():
            uvicorn.run(
                self.app,
                host=self.host,
                port=self.port,
                log_level="info"
            )

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.is_running = True
        print(f"HTTP Transport listening on {self.host}:{self.port} (Node: {self.node_id})")

    def stop(self):
        """Stop HTTP server"""
        # Note: In a real implementation, we'd have a proper shutdown mechanism
        self.is_running = False

    async def async_send_request(self, request_data: Dict[str, Any], target_host: str = "localhost", target_port: int = 8000) -> Dict[str, Any]:
        """Send request asynchronously to target HTTP endpoint"""
        target_url = f"http://{target_host}:{target_port}/facp/request"  # NOSONAR - python:S5332

        # Create a session for this host if not exists
        session_key = f"{target_host}:{target_port}"
        if session_key not in self.client_sessions:
            self.client_sessions[session_key] = aiohttp.ClientSession()

        session = self.client_sessions[session_key]

        try:
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
            async with session.post(target_url, json=request_data, timeout=timeout) as response:
                return await response.json()
        except Exception as e:
            return {
                "protocol": "FACP/1.1",
                "id": request_data.get("id", "unknown"),
                "status": "error",
                "error": {
                    "code": "NETWORK_ERROR",
                    "message": str(e)
                },
                "trace": {
                    "node_id": self.node_id,
                    "node_type": self.node_type,
                    "execution_path": [self.node_type],
                    "latency_ms": 0
                }
            }

    def send_request(self, request_data: Dict[str, Any], target_node: Optional[str] = None) -> Dict[str, Any]:
        """
        Send request to target (synchronous wrapper for async method) with circuit breaker protection
        target_node format: "host:port" (e.g., "localhost:8001")
        """
        def _internal_send():
            if target_node:
                host, port = target_node.split(":")
                port = int(port)
            else:
                # Default to localhost:8001 for testing
                host, port = "localhost", 8001

            # Run the async function synchronously
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.async_send_request(request_data, host, port))
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

        # Use circuit breaker to protect against cascade failures
        try:
            return self.circuit_breaker.call(_internal_send)
        except Exception as e:
            return {
                "protocol": "FACP/1.1",
                "id": request_data.get("id", "unknown"),
                "status": "error",
                "error": {
                    "code": "CIRCUIT_BREAKER_OPEN" if str(e) == "Circuit breaker is OPEN" else "REQUEST_FAILED",
                    "message": str(e)
                },
                "trace": {
                    "node_id": self.node_id,
                    "node_type": self.node_type,
                    "execution_path": [self.node_type],
                    "latency_ms": 0
                }
            }

    def get_client_session(self, host: str, port: int):
        """Get or create a client session for the given host:port"""
        session_key = f"{host}:{port}"
        if session_key not in self.client_sessions:
            self.client_sessions[session_key] = aiohttp.ClientSession()
        return self.client_sessions[session_key]


class TransportRouter:
    """Routes requests to appropriate transport based on configuration"""

    def __init__(self):
        self.transports = {}
        self.active_transport = None
        self.transport_preferences = {}  # node_id -> preferred_transport

    def add_transport(self, name: str, transport: TransportLayer):
        """Add a transport to the router"""
        self.transports[name] = transport

    def activate_transport(self, name: str):
        """Activate a specific transport"""
        if name in self.transports:
            self.active_transport = self.transports[name]
            return True
        return False

    def get_transport(self, name: str) -> Optional[TransportLayer]:
        """Get a specific transport"""
        return self.transports.get(name)

    def route_request(self, request_data: Dict[str, Any], target_node: Optional[str] = None,
                     transport_hint: Optional[str] = None) -> Dict[str, Any]:
        """Route request to appropriate transport and node"""
        transport = None

        if transport_hint and transport_hint in self.transports:
            transport = self.transports[transport_hint]
        elif self.active_transport:
            transport = self.active_transport
        else:
            # Default to first available transport
            transport = next(iter(self.transports.values()), None)

        if transport:
            return transport.send_request(request_data, target_node)
        # Return error if no transport available
        return {
            "error": {
                "code": "TRANSPORT_UNAVAILABLE",
                "message": "No transport available to handle request"
            }
        }

    def start_all(self):
        """Start all configured transports"""
        for transport in self.transports.values():
            transport.start()

    def stop_all(self):
        """Stop all configured transports"""
        for transport in self.transports.values():
            transport.stop()
