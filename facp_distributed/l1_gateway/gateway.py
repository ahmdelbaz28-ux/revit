"""
L1 Gateway for Distributed FACP System
"""
import logging
import time
import uuid
from typing import Any, Dict, Tuple

from ..protocol.message_schema import FACPMessageValidator, FACPRequest, FACPResponse
from ..security.validation_gate import ValidationFirewall
from ..transport.http_transport import HTTPTransport


class L1Gateway:
    """
    L1 Gateway - Handles requests from external clients (IDEs, etc.) in distributed system
    This is the first layer that receives all external requests and forwards to orchestrator
    """
    def __init__(self, validation_firewall: ValidationFirewall, transport: HTTPTransport):
        self.validation_firewall = validation_firewall
        self.transport = transport
        self.logger = logging.getLogger(__name__)
        self.node_id = f"l1_gateway_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.request_counter = 0
        self.active_requests = {}  # request_id -> request_info

    def handle_client_request(self, request_data: Dict[str, Any], source_ip: str = "unknown") -> Tuple[bool, Dict[str, Any]]:
        """
        Handle an incoming request from external client
        :param request_data: Raw request data from external client
        :param source_ip: Source IP address (for logging)
        :return: (success, response_data)
        """
        # Add node and source information
        request_data["source"] = "l1"
        request_data["target"] = "orchestrator"
        request_data["routing"] = {
            "source_node": self.node_id,
            "source_ip": source_ip,
            "timestamp": time.time()
        }

        # Generate request ID if not provided
        request_id = request_data.get("id", str(uuid.uuid4()))
        request_data["id"] = request_id

        # Update execution state
        request_data["execution_state"] = "RECEIVED"

        # Log request receipt
        self.logger.info(f"L1[{self.node_id}]: Request {request_id} received from {source_ip}")

        # Validate basic schema (L1 only does minimal validation)
        validator = FACPMessageValidator()
        is_valid, basic_errors = validator.validate_request(FACPRequest.from_dict(request_data))

        if not is_valid:
            self.logger.warning(f"L1[{self.node_id}]: Request {request_id} failed basic validation: {basic_errors}")

            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "BASIC_VALIDATION_FAILED",
                    "message": "; ".join(basic_errors)
                },
                trace={
                    "execution_path": ["L1"],
                    "latency_ms": 0,
                    "node_id": self.node_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

            return False, error_response

        # Track active request
        self.active_requests[request_id] = {
            "received_at": time.time(),
            "source_ip": source_ip,
            "method": request_data.get("method", "unknown")
        }

        # Forward to validation firewall (this is the critical security boundary)
        is_valid, processed_data, validation_errors = \
            self.validation_firewall.process_request(request_data, self.node_id)

        if not is_valid:
            self.logger.warning(f"L1[{self.node_id}]: Request {request_id} failed validation firewall: {validation_errors}")

            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "VALIDATION_FIREWALL_BLOCKED",
                    "message": "; ".join(validation_errors)
                },
                trace={
                    "execution_path": ["L1", "validation_firewall"],
                    "latency_ms": (time.time() - self.active_requests[request_id]["received_at"]) * 1000,
                    "node_id": self.node_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

            # Clean up active request tracking
            del self.active_requests[request_id]

            return False, error_response

        # Request passed validation firewall, now forward to orchestrator
        self.logger.info(f"L1[{self.node_id}]: Request {request_id} passed validation, forwarding to orchestrator")

        # Update execution state
        request_data["execution_state"] = "VALIDATED"

        # Forward to orchestrator via transport
        try:
            orchestrator_response = self.transport.send_request(request_data, target_node="l2_orchestrator")

            # Update execution path in response
            if "trace" in orchestrator_response:
                orchestrator_response["trace"]["execution_path"] = ["L1", "L2_Orchestrator"] + \
                    orchestrator_response["trace"].get("execution_path", [])
                orchestrator_response["trace"]["l1_latency_ms"] = \
                    (time.time() - self.active_requests[request_id]["received_at"]) * 1000
            else:
                orchestrator_response["trace"] = {
                    "execution_path": ["L1", "L2_Orchestrator"],
                    "l1_latency_ms": (time.time() - self.active_requests[request_id]["received_at"]) * 1000,
                    "node_id": self.node_id,
                    "engine_version": "FACP/1.1"
                }

            # Clean up active request tracking
            del self.active_requests[request_id]

            return True, orchestrator_response

        except Exception as e:
            self.logger.error(f"L1[{self.node_id}]: Failed to forward request {request_id} to orchestrator: {str(e)}")

            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "FORWARDING_ERROR",
                    "message": f"Failed to forward request to orchestrator: {str(e)}"
                },
                trace={
                    "execution_path": ["L1"],
                    "latency_ms": (time.time() - self.active_requests[request_id]["received_at"]) * 1000,
                    "node_id": self.node_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

            # Clean up active request tracking
            del self.active_requests[request_id]

            return False, error_response

    def handle_client_response(self, request_id: str, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle response from downstream services and prepare for client delivery
        """
        self.logger.info(f"L1[{self.node_id}]: Preparing response for client request {request_id}")

        # Add L1-specific trace information
        if "trace" not in response_data:
            response_data["trace"] = {}

        response_data["trace"].update({
            "node_id": self.node_id,
            "engine_version": "FACP/1.1",
            "final_delivery_node": self.node_id,
            "l1_processing_time_ms": (time.time() - self.active_requests.get(request_id, {"received_at": time.time()})["received_at"]) * 1000
        })

        # Update execution path if not already present
        if "execution_path" not in response_data["trace"]:
            response_data["trace"]["execution_path"] = ["L1"]

        return response_data

    def get_gateway_status(self) -> Dict[str, Any]:
        """Get status of the L1 gateway"""
        return {
            "node_id": self.node_id,
            "request_counter": self.request_counter,
            "active_requests": len(self.active_requests),
            "uptime_seconds": time.time() - self.active_requests.get("startup_time", time.time()),
            "transport_status": getattr(self.transport, 'is_running', False),
            "validation_firewall_status": "active"  # Simplified
        }

    def cleanup_completed_requests(self):
        """Clean up completed requests from tracking"""
        current_time = time.time()
        timeout_threshold = 300  # 5 minutes timeout

        expired_requests = [
            req_id for req_id, req_info in self.active_requests.items()
            if current_time - req_info["received_at"] > timeout_threshold
        ]

        for req_id in expired_requests:
            self.logger.warning(f"L1[{self.node_id}]: Cleaning up expired request {req_id}")
            del self.active_requests[req_id]

    def validate_client_request_format(self, request_data: Dict[str, Any]) -> Tuple[bool, list]:
        """Validate client request format before forwarding to validation firewall"""
        try:
            request = FACPRequest.from_dict(request_data)
            validator = FACPMessageValidator()
            is_valid, errors = validator.validate_request(request)
            return is_valid, errors
        except Exception as e:
            return False, [f"Request format validation failed: {str(e)}"]

    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics from validation firewall"""
        return self.validation_firewall.get_security_stats()

    def get_request_metrics(self) -> Dict[str, Any]:
        """Get metrics about requests processed by this gateway"""
        return {
            "total_requests": self.request_counter,
            "active_requests": len(self.active_requests),
            "average_processing_time": 0,  # Would calculate from request logs in real implementation
            "requests_by_method": {},  # Would track in real implementation
        }

    def graceful_shutdown(self):
        """Perform graceful shutdown of the gateway"""
        self.logger.info(f"L1[{self.node_id}]: Initiating graceful shutdown")

        # Wait for active requests to complete (up to a timeout)
        import time
        timeout = 30  # 30 seconds
        start_time = time.time()

        while len(self.active_requests) > 0 and (time.time() - start_time) < timeout:
            time.sleep(0.1)  # Brief pause

        # Force cleanup if timeout reached
        if len(self.active_requests) > 0:
            self.logger.warning(f"L1[{self.node_id}]: Force cleaning up {len(self.active_requests)} remaining requests")

        self.active_requests.clear()

        # Shutdown transport
        if hasattr(self.transport, 'stop'):
            self.transport.stop()

        self.logger.info(f"L1[{self.node_id}]: Shutdown complete")
