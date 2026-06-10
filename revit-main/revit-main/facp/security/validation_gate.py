"""
FACP Validation Gate - Security firewall between layers
"""
from typing import Dict, Any, Tuple, List
from ..protocol.message_schema import FACPMessageValidator, FACPRequest
from .auth import AuthProvider
import time
import logging
from enum import Enum


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityMiddleware:
    """
    Security middleware that enforces validation rules
    """
    def __init__(self, auth_provider: AuthProvider):
        self.auth_provider = auth_provider
        self.validator = FACPMessageValidator()
        self.logger = logging.getLogger(__name__)
        self.payload_size_limit = 1024 * 1024  # 1MB

    def validate_request(self, request_data: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate incoming request against security rules
        :param request_data: Raw request data
        :param return: (is_valid, errors, sanitized_data)
        """
        errors = []

        # Create FACP request object from data
        try:
            request = FACPRequest.from_dict(request_data)
        except Exception as e:
            errors.append(f"Invalid request format: {str(e)}")
            return False, errors, {}

        # Validate the request format
        is_valid, format_errors = self.validator.validate_request(request)
        if not is_valid:
            errors.extend(format_errors)
            return False, errors, {}

        # Check payload size
        payload_ok, payload_error = self._check_payload_size(request.params)
        if not payload_ok:
            errors.append(payload_error)
            return False, errors, {}

        # Authenticate request
        is_auth, auth_context = self.auth_provider.authenticate_request(request.security)
        if not is_auth:
            errors.append("Authentication failed")
            return False, errors, {}

        # Apply security policies based on risk level
        risk_level = request.security.get("risk_level", "low")
        policy_check_ok, policy_errors = self._apply_security_policy(request, risk_level)
        if not policy_check_ok:
            errors.extend(policy_errors)
            return False, errors, {}

        # Return sanitized and validated request
        return True, [], {
            "request": request,
            "auth_context": auth_context,
            "risk_level": risk_level
        }

    def _check_payload_size(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if payload exceeds size limits"""
        try:
            import json
            payload_size = len(json.dumps(params).encode('utf-8'))
            if payload_size > self.payload_size_limit:
                return False, f"Payload exceeds size limit ({payload_size} > {self.payload_size_limit})"
            return True, ""
        except Exception as e:
            return False, f"Could not measure payload size: {str(e)}"

    def _apply_security_policy(self, request: FACPRequest, risk_level: str) -> Tuple[bool, List[str]]:
        """Apply security policies based on risk level"""
        errors = []

        # Different policies for different risk levels
        if risk_level == RiskLevel.HIGH.value:
            # More restrictive checks for high-risk requests
            if request.method.startswith("admin.") or request.method.startswith("system."):
                errors.append("High-risk administrative methods not allowed")
        elif risk_level == RiskLevel.CRITICAL.value:
            # Most restrictive checks for critical-risk requests
            errors.append("Critical-risk requests require special approval")

        return len(errors) == 0, errors


class ValidationGate:
    """
    The security firewall that sits between L1 and L2
    All requests must pass through this gate before reaching orchestrator
    """
    def __init__(self, auth_provider: AuthProvider):
        self.middleware = SecurityMiddleware(auth_provider)
        self.request_cache = {}  # For idempotency
        self.logger = logging.getLogger(__name__)

    def process_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Process an incoming request through the validation gate
        :param request_data: Raw request data
        :return: (should_forward, processed_data, errors)
        """
        # First, check for idempotency
        idempotency_key = request_data.get("params", {}).get("idempotency_key")
        if idempotency_key and idempotency_key in self.request_cache:
            # Return cached response for idempotent requests
            return True, self.request_cache[idempotency_key], []

        # Validate the request
        is_valid, errors, validated_data = self.middleware.validate_request(request_data)
        
        if not is_valid:
            return False, {}, errors

        # Process successful validation
        processed_request = {
            "original_request": request_data,
            "validated_request": validated_data["request"].to_dict(),
            "auth_context": validated_data["auth_context"],
            "risk_level": validated_data["risk_level"],
            "validated_at": time.time(),
            "source_ip": request_data.get("_source_ip", "unknown"),  # Would come from transport layer
        }

        # Cache idempotent requests
        if idempotency_key:
            self.request_cache[idempotency_key] = processed_request

        return True, processed_request, []

    def validate_target_access(self, auth_context: Dict[str, Any], target: str) -> bool:
        """
        Validate if authenticated user can access target layer
        :param auth_context: Authentication context
        :param target: Target layer (orchestrator/engine)
        :return: Access allowed
        """
        user_permissions = auth_context.get("permissions", [])
        
        # Engine access requires special permissions
        if target == "engine":
            return "engine_access" in user_permissions or "admin" in user_permissions
        
        # Orchestrator access requires basic permissions
        return len(user_permissions) > 0

    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""
        self.logger.info(f"SECURITY_EVENT: {event_type} - {details}")

    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics"""
        return {
            "blocked_requests": getattr(self, '_blocked_count', 0),
            "allowed_requests": getattr(self, '_allowed_count', 0),
            "active_sessions": len(self.middleware.auth_provider.token_manager.active_tokens),
            "cached_requests": len(self.request_cache)
        }