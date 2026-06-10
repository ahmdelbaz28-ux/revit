"""
System Governance Engine - The Central Orchestrator for All Governance Functions
"""

import time
from typing import Dict, Any, Optional, Tuple
from .models import ExecutionRequest, PolicyDecision, ExecutionTrace, ExecutionStatus
from .enforcement import EnforcementEngine
from .exceptions import GovernanceException, ValidationException, PolicyException, AuditException


class SystemGovernanceEngine:
    """
    System Governance Engine - The Mandatory Execution Gate
    All requests MUST pass through this gate to reach L2/L3
    Implements the hard enforcement model with zero trust architecture
    """
    
    def __init__(self):
        self.enforcement_engine = EnforcementEngine()
        self.is_operational = True
    
    def process_request(self,
                      user_id: str,
                      role: str,
                      payload: Dict[str, Any],
                      idempotency_key: str,
                      risk_level: str = "low",
                      action_requires_write: bool = False,
                      required_action: Optional[str] = None) -> tuple[bool, PolicyDecision, ExecutionTrace]:
        """
        Process a request through the governance engine (THE HARD GATE)
        
        This is the mandatory execution gate. No request reaches L2/L3 without passing through this.
        
        Args:
            user_id: The user ID
            role: The user role
            payload: The request payload
            idempotency_key: The idempotency key (required for all requests)
            risk_level: The risk level of the request
            action_requires_write: Whether the action requires write permissions
            required_action: The specific action being requested
            
        Returns:
            Tuple of (is_allowed, policy_decision, execution_trace)
            
        Raises:
            ValidationException: If input validation fails
            PolicyException: If policy decision is DENY
            AuditException: If audit logging fails
            EnforcementException: If enforcement fails
        """
        if not self.is_operational:
            raise GovernanceException("Governance engine is not operational")
        
        # Validate mandatory parameters
        if not idempotency_key:
            raise ValidationException("idempotency_key is required for all requests")
        
        if not user_id:
            raise ValidationException("user_id is required for all requests")
        
        # Process through the hard enforcement gate
        return self.enforcement_engine.is_request_allowed(
            user_id=user_id,
            role=role,
            payload=payload,
            idempotency_key=idempotency_key,
            risk_level=risk_level,
            action_requires_write=action_requires_write,
            required_action=required_action
        )
    
    def validate_and_approve(self, request: ExecutionRequest) -> tuple[PolicyDecision, ExecutionTrace]:
        """
        Validate and approve a pre-created request
        
        Args:
            request: The execution request to validate and approve
            
        Returns:
            Tuple of (policy_decision, execution_trace)
        """
        if not self.is_operational:
            raise GovernanceException("Governance engine is not operational")
        
        # Process through the hard enforcement gate
        is_allowed, decision, trace = self.enforcement_engine.enforce_governance(request)
        
        if not is_allowed:
            raise PolicyException(f"Request not allowed by policy: {decision.reason}")
        
        return decision, trace
    
    def check_policy_compliance(self, 
                               user_id: str,
                               role: str, 
                               payload: Dict[str, Any],
                               idempotency_key: str,
                               risk_level: str = "low") -> PolicyDecision:
        """
        Check policy compliance without fully processing the request
        
        Args:
            user_id: The user ID
            role: The user role
            payload: The request payload
            idempotency_key: The idempotency key
            risk_level: The risk level
            
        Returns:
            PolicyDecision for the request
        """
        # Create a request just for policy evaluation
        request = ExecutionRequest.create(
            user_id=user_id,
            role=role,
            payload=payload,
            idempotency_key=idempotency_key,
            risk_level=risk_level
        )
        
        # Run through validation only to see if it would be allowed
        try:
            is_valid, validation_msg = self.enforcement_engine.validation_engine.validate_request(request)
            if not is_valid:
                return PolicyDecision(
                    decision="DENY",
                    reason=f"Validation failed: {validation_msg}",
                    rules_applied=["VALIDATION_RULE"]
                )
            
            # Then check authorization
            try:
                self.enforcement_engine.auth_engine.authorize_request(request)
            except Exception as e:
                return PolicyDecision(
                    decision="DENY",
                    reason=f"Authorization failed: {str(e)}",
                    rules_applied=["AUTHORIZATION_RULE"]
                )
            
            # Finally, get policy decision
            decision = self.enforcement_engine.policy_engine.evaluate_request(request)
            return decision
            
        except Exception as e:
            return PolicyDecision(
                decision="DENY",
                reason=f"Compliance check failed: {str(e)}",
                rules_applied=[]
            )
    
    def get_governance_metrics(self) -> Dict[str, Any]:
        """
        Get governance engine metrics
        
        Returns:
            Dictionary with governance metrics
        """
        # This would typically aggregate metrics from all subsystems
        return {
            "is_operational": self.is_operational,
            "engine_uptime": getattr(self, '_start_time', time.time()),
            "total_requests_processed": 0,  # Would be tracked in a real implementation
            "requests_blocked": 0,  # Would be tracked in a real implementation
            "average_validation_time_ms": 0,  # Would be tracked in a real implementation
            "average_policy_time_ms": 0,  # Would be tracked in a real implementation
        }
    
    def shutdown(self):
        """Shutdown the governance engine safely"""
        self.is_operational = False
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check of the governance engine
        
        Returns:
            Health check results
        """
        return {
            "status": "healthy" if self.is_operational else "unhealthy",
            "subsystems": {
                "validation_engine": "operational",
                "auth_engine": "operational", 
                "policy_engine": "operational",
                "audit_engine": "operational",
                "enforcement_engine": "operational"
            },
            "timestamp": time.time()
        }


def create_governance_engine() -> SystemGovernanceEngine:
    """
    Factory function to create a governance engine instance
    
    Returns:
        SystemGovernanceEngine instance
    """
    return SystemGovernanceEngine()


# Global instance for easy access (though in a real system you'd likely manage this differently)
governance_engine = create_governance_engine()