"""
FACP L1 Interface Handler - External request handler (untrusted)
"""
from typing import Dict, Any, Optional, Tuple
from ..protocol.message_schema import FACPRequest, FACPResponse, FACPMessageValidator
from ..security.validation_gate import ValidationGate
from ..runtime.state_machine import ExecutionStateMachine, ExecutionState
from ..runtime.idempotency_manager import IdempotencyMiddleware
import time
import uuid
import logging


class L1InterfaceHandler:
    """
    L1 Interface Handler - Handles external requests from untrusted sources
    This is the first layer that receives all external requests
    """
    def __init__(self, validation_gate: ValidationGate, execution_sm: ExecutionStateMachine):
        self.validation_gate = validation_gate
        self.execution_sm = execution_sm
        self.idempotency_middleware = IdempotencyMiddleware(validation_gate.middleware.idempotency_manager)
        self.logger = logging.getLogger(__name__)

    def handle_request(self, request_data: Dict[str, Any], source_ip: str = "unknown") -> Tuple[bool, Dict[str, Any]]:
        """
        Handle an incoming request from external source
        :param request_data: Raw request data from external source
        :param source_ip: Source IP address (for logging)
        :return: (success, response_data)
        """
        # Add source IP to request for logging
        request_data["_source_ip"] = source_ip
        
        # Generate request ID if not provided
        request_id = request_data.get("id", str(uuid.uuid4()))
        
        # Create execution state for this request
        self.execution_sm.create_request_state(request_id, request_data)
        
        # Log request receipt
        self.logger.info(f"L1: Request {request_id} received from {source_ip}")
        self.execution_sm.transition_to(request_id, ExecutionState.RECEIVED, 
                                       f"Request received from {source_ip}", 
                                       {"source_ip": source_ip})
        
        # Check for idempotency first
        should_process, cached_result, idempotency_status = \
            self.idempotency_middleware.process_request(request_data)
        
        if not should_process and cached_result:
            self.logger.info(f"L1: Idempotent request {request_id}, returning cached result")
            self.execution_sm.transition_to(request_id, ExecutionState.COMPLETED,
                                          "Idempotent request served from cache",
                                          {"cached": True})
            return True, cached_result
        
        # Pass through validation gate (this is the critical security firewall)
        is_valid, processed_data, validation_errors = \
            self.validation_gate.process_request(request_data)
        
        if not is_valid:
            self.logger.warning(f"L1: Request {request_id} failed validation: {validation_errors}")
            self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                          "Request failed validation gate",
                                          {"validation_errors": validation_errors})
            
            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "VALIDATION_FAILED",
                    "message": "; ".join(validation_errors)
                },
                trace={
                    "engine_version": "FACP/1.0",
                    "execution_path": ["L1"],
                    "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                }
            ).to_dict()
            
            return False, error_response
        
        # Request passed validation, transition to validated state
        self.execution_sm.transition_to(request_id, ExecutionState.VALIDATED,
                                      "Request passed validation gate",
                                      {"auth_context": processed_data["auth_context"]})
        
        # Verify target access
        auth_context = processed_data["auth_context"]
        target = request_data.get("target", "engine")
        
        if not self.validation_gate.validate_target_access(auth_context, target):
            self.logger.warning(f"L1: Request {request_id} denied access to target {target}")
            self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                          "Access denied to target layer",
                                          {"target": target})
            
            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "ACCESS_DENIED",
                    "message": f"Insufficient permissions to access {target}"
                },
                trace={
                    "engine_version": "FACP/1.0",
                    "execution_path": ["L1", "validation"],
                    "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                }
            ).to_dict()
            
            return False, error_response
        
        # Request is validated and authorized, ready to forward to L2
        self.logger.info(f"L1: Request {request_id} validated and authorized, forwarding to L2")
        self.execution_sm.transition_to(request_id, ExecutionState.ROUTED,
                                      "Request validated and routed to L2",
                                      {"target": target})
        
        # Return processed data for forwarding to L2
        return True, {
            "request_id": request_id,
            "processed_request": processed_data,
            "auth_context": auth_context,
            "should_forward": True
        }

    def handle_response(self, request_id: str, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle response from lower layers and prepare for external delivery
        """
        # Log response processing
        self.logger.info(f"L1: Preparing response for request {request_id}")
        
        # Transition to completed state
        self.execution_sm.transition_to(request_id, ExecutionState.COMPLETED,
                                      "Response prepared for external delivery",
                                      {"response_size": len(str(response_data))})
        
        # Add execution trace to response if not already present
        if "trace" not in response_data:
            trace = self.execution_sm.get_execution_trace(request_id)
            response_data["trace"] = {
                "engine_version": "FACP/1.0",
                "execution_path": trace.get("states_visited", []),
                "latency_ms": trace.get("total_duration", 0) * 1000
            }
        
        # Apply idempotency if applicable
        original_request = self.execution_sm.requests[request_id].get("initial_data", {})
        self.idempotency_middleware.record_successful_result(original_request, response_data)
        
        return response_data

    def handle_error_response(self, request_id: str, error: Dict[str, str], 
                            error_stage: str) -> Dict[str, Any]:
        """
        Handle error and prepare error response for external delivery
        """
        self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                      f"Error at {error_stage}",
                                      {"error": error, "stage": error_stage})
        
        error_response = FACPResponse(
            id=request_id,
            status="error",
            error=error,
            trace={
                "engine_version": "FACP/1.0",
                "execution_path": ["L1", error_stage],
                "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
            }
        ).to_dict()
        
        return error_response

    def get_request_status(self, request_id: str) -> Dict[str, Any]:
        """Get status of a request"""
        current_state = self.execution_sm.get_current_state(request_id)
        state_history = self.execution_sm.get_state_history(request_id)
        
        return {
            "request_id": request_id,
            "current_state": current_state.value if current_state else None,
            "state_history": state_history,
            "is_terminal": self.execution_sm.is_terminal_state(request_id) if current_state else False
        }

    def cleanup_completed_request(self, request_id: str):
        """Clean up resources for completed request"""
        self.execution_sm.cleanup_request(request_id)
        # Note: Idempotency records are kept for their TTL period

    def validate_request_format(self, request_data: Dict[str, Any]) -> Tuple[bool, list]:
        """Validate request format before passing to validation gate"""
        try:
            request = FACPRequest.from_dict(request_data)
            validator = FACPMessageValidator()
            is_valid, errors = validator.validate_request(request)
            return is_valid, errors
        except Exception as e:
            return False, [f"Request format validation failed: {str(e)}"]

    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics from validation gate"""
        return self.validation_gate.get_security_stats()