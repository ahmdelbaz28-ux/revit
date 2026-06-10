"""
SGL Enforcement Engine - Hard Gate Implementation
"""

import time
import threading
from typing import Dict, Any, Optional
from ..models import ExecutionRequest, PolicyDecision, ExecutionTrace, ExecutionStatus
from ..validation import InputValidationEngine
from ..auth import AuthorizationEngine
from ..policy import PolicyDecisionEngine
from ..audit import AuditEngine
from ..exceptions import (
    GovernanceException, ValidationException, 
    PolicyException, AuditException, EnforcementException, IdempotencyException
)


class IdempotencyManager:
    """
    Manages idempotency keys to prevent duplicate execution
    """
    
    def __init__(self):
        self.cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def check_and_record(self, idempotency_key: str, request_data: Any) -> tuple[bool, Optional[Any]]:
        """
        Check if request with this idempotency key has been processed before
        
        Args:
            idempotency_key: The idempotency key
            request_data: The request data for comparison
            
        Returns:
            Tuple of (is_new, cached_result if exists)
        """
        with self._lock:
            if idempotency_key in self.cache:
                # Return the cached result
                return False, self.cache[idempotency_key]
            else:
                # Record this as a new request
                self.cache[idempotency_key] = request_data
                return True, None


class EnforcementEngine:
    """
    Enforcement Engine - The Hard Gate Implementation
    All requests must pass through this gate to proceed to L2/L3
    """
    
    def __init__(self):
        self.validation_engine = InputValidationEngine()
        self.auth_engine = AuthorizationEngine()
        self.policy_engine = PolicyDecisionEngine()
        self.audit_engine = AuditEngine()
        self.idempotency_manager = IdempotencyManager()
        
        # Track ongoing executions to prevent race conditions
        self.ongoing_executions = set()
        self._execution_lock = threading.Lock()
    
    def enforce_governance(self, 
                          request: ExecutionRequest, 
                          action_requires_write: bool = False,
                          required_action: Optional[str] = None) -> tuple[bool, PolicyDecision, ExecutionTrace]:
        """
        Enforce governance requirements for a request
        
        Args:
            request: The execution request
            action_requires_write: Whether the action requires write permissions
            required_action: The specific action being requested
            
        Returns:
            Tuple of (is_allowed, policy_decision, execution_trace)
        """
        start_time = time.time()
        trace = self.audit_engine.initialize_trace(request)
        
        try:
            # Step 1: Validate input
            validation_start = time.time()
            is_valid, validation_msg = self.validation_engine.validate_request(request)
            validation_latency = (time.time() - validation_start) * 1000
            
            trace.add_flow_step("VALIDATION", validation_latency)
            self.audit_engine.log_validation_result(request.request_id, is_valid, validation_msg)
            
            if not is_valid:
                trace.complete_trace(ExecutionStatus.BLOCKED)
                raise ValidationException(f"Input validation failed: {validation_msg}")
            
            # Step 2: Check idempotency
            idempotency_start = time.time()
            is_new, cached_result = self.idempotency_manager.check_and_record(
                request.idempotency_key, 
                None  # We'll store the final result later
            )
            idempotency_latency = (time.time() - idempotency_start) * 1000
            
            trace.add_flow_step("IDEMPOTENCY_CHECK", idempotency_latency)
            
            if not is_new:
                # This is a duplicate request, return the cached result
                trace.complete_trace(ExecutionStatus.SUCCESS)
                decision = PolicyDecision(
                    decision="ALLOW",  # Since it was previously allowed
                    reason="Idempotency key match - returning cached result",
                    rules_applied=["IDEMPOTENCY_RULE"]
                )
                return True, decision, trace
            
            # Step 3: Authorize request
            auth_start = time.time()
            try:
                self.auth_engine.authorize_request(request, required_action)
                auth_authorized = True
                auth_msg = "Authorization passed"
            except GovernanceException as e:
                auth_authorized = False
                auth_msg = str(e)
            
            auth_latency = (time.time() - auth_start) * 1000
            
            trace.add_flow_step("AUTHORIZATION", auth_latency)
            self.audit_engine.log_authorization_result(
                request.request_id, 
                auth_authorized, 
                request.role.value, 
                required_action or ""
            )
            
            if not auth_authorized:
                trace.complete_trace(ExecutionStatus.BLOCKED)
                raise GovernanceException(f"Authorization failed: {auth_msg}")
            
            # Step 4: Policy decision
            policy_start = time.time()
            decision = self.policy_engine.evaluate_request(request, action_requires_write)
            policy_latency = (time.time() - policy_start) * 1000
            
            trace.add_flow_step("POLICY_EVALUATION", policy_latency)
            self.audit_engine.log_policy_decision(request.request_id, decision)
            
            if decision.decision == "DENY":
                trace.complete_trace(ExecutionStatus.BLOCKED, decision)
                raise PolicyException(f"Policy denied request: {decision.reason}")
            
            # Step 5: Add the decision to trace
            trace.complete_trace(ExecutionStatus.SUCCESS, decision)
            
            # Log the successful passage through SGL
            total_latency = (time.time() - start_time) * 1000
            self.audit_engine.log_layer_transition(
                request.request_id,
                "L1_TO_SGL",
                "SGL_APPROVED",
                total_latency,
                {"decision": decision.decision.value, "reason": decision.reason}
            )
            
            return True, decision, trace
            
        except ValidationException as e:
            # Log validation failure
            self.audit_engine.log_security_event(
                request.request_id,
                "VALIDATION_FAILURE",
                "HIGH",
                f"Request blocked due to validation failure: {str(e)}"
            )
            trace.complete_trace(ExecutionStatus.BLOCKED)
            raise
        
        except PolicyException as e:
            # Log policy failure
            self.audit_engine.log_security_event(
                request.request_id,
                "POLICY_VIOLATION",
                "HIGH",
                f"Request blocked due to policy violation: {str(e)}"
            )
            trace.complete_trace(ExecutionStatus.BLOCKED)
            raise
        
        except Exception as e:
            # Log unexpected failure - FAIL CLOSED
            self.audit_engine.log_security_event(
                request.request_id,
                "ENFORCEMENT_ERROR",
                "CRITICAL",
                f"Request blocked due to enforcement error: {str(e)}"
            )
            trace.complete_trace(ExecutionStatus.BLOCKED)
            raise EnforcementException(f"Enforcement error: {str(e)}") from e
    
    def is_request_allowed(self, 
                          user_id: str, 
                          role: str, 
                          payload: Dict[str, Any], 
                          idempotency_key: str, 
                          risk_level: str = "low",
                          action_requires_write: bool = False,
                          required_action: Optional[str] = None) -> tuple[bool, PolicyDecision, ExecutionTrace]:
        """
        Convenience method to check if a request is allowed
        
        Args:
            user_id: The user ID
            role: The user role
            payload: The request payload
            idempotency_key: The idempotency key
            risk_level: The risk level
            action_requires_write: Whether the action requires write permissions
            required_action: The specific action being requested
            
        Returns:
            Tuple of (is_allowed, policy_decision, execution_trace)
        """
        request = ExecutionRequest.create(
            user_id=user_id,
            role=role,
            payload=payload,
            idempotency_key=idempotency_key,
            risk_level=risk_level
        )
        
        return self.enforce_governance(request, action_requires_write, required_action)
    
    def get_execution_trace(self, request_id: str) -> Optional[ExecutionTrace]:
        """
        Get the execution trace for a request
        
        Args:
            request_id: The request ID
            
        Returns:
            Execution trace if found, None otherwise
        """
        # This would typically look up in a trace store
        # For now, we'll return None since traces are held in memory in the audit engine
        return None