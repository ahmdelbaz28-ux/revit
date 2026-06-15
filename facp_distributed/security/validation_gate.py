"""
Validation Firewall for Distributed FACP System
"""
import hashlib
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Tuple

from ..protocol.message_schema import FACPMessageValidator, FACPRequest
from .auth import AuthProvider


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityMiddleware:
    """
    Security middleware that enforces validation rules in distributed environment
    """
    def __init__(self, auth_provider: AuthProvider):
        self.auth_provider = auth_provider
        self.validator = FACPMessageValidator()
        self.logger = logging.getLogger(__name__)
        self.payload_size_limit = 1024 * 1024  # 1MB
        self.rate_limits = {}  # user_id -> [(timestamp, count)]

    def validate_request(self, request_data: Dict[str, Any], source_node: str = None) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate incoming request against security rules in distributed context
        :param request_data: Raw request data
        :param source_node: Node that originated the request
        :return: (is_valid, errors, sanitized_data)
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

        # Check rate limits
        rate_limit_ok, rate_limit_error = self._check_rate_limits(request.security.get("auth_token"), source_node)
        if not rate_limit_ok:
            errors.append(rate_limit_error)
            return False, errors, {}

        # Authenticate request
        is_auth, auth_context = self.auth_provider.authenticate_request(request.security, source_node)
        if not is_auth:
            errors.append("Authentication failed")
            return False, errors, {}

        # Apply security policies based on risk level
        risk_level = request.security.get("risk_level", "low")
        policy_check_ok, policy_errors = self._apply_security_policy(request, risk_level, source_node)
        if not policy_check_ok:
            errors.extend(policy_errors)
            return False, errors, {}

        # Return sanitized and validated request
        return True, [], {
            "request": request,
            "auth_context": auth_context,
            "risk_level": risk_level,
            "source_node": source_node
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

    def _check_rate_limits(self, token: str, source_node: str) -> Tuple[bool, str]:
        """Check if request rate is within limits"""
        # Create user identifier based on token or source node
        user_id = hashlib.sha256((token or source_node or "unknown").encode()).hexdigest()

        current_time = time.time()
        window_size = 60  # 60 seconds window

        # Clean old entries
        if user_id in self.rate_limits:
            self.rate_limits[user_id] = [
                (ts, count) for ts, count in self.rate_limits[user_id]
                if current_time - ts <= window_size
            ]
        else:
            self.rate_limits[user_id] = []

        # Count current requests
        current_requests = sum(count for ts, count in self.rate_limits[user_id])

        # Apply different limits based on risk level and source
        max_requests = 1000 if source_node and "l2" in source_node else 100  # More permissive for orchestrator nodes

        if current_requests >= max_requests:
            return False, f"Rate limit exceeded: {max_requests} requests per {window_size}s"

        # Add current request
        self.rate_limits[user_id].append((current_time, 1))

        return True, ""

    def _apply_security_policy(self, request: FACPRequest, risk_level: str, source_node: str) -> Tuple[bool, List[str]]:
        """Apply security policies based on risk level and source node"""
        errors = []

        # Different policies for different risk levels
        if risk_level == RiskLevel.HIGH.value:
            # More restrictive checks for high-risk requests
            if request.method.startswith("admin.") or request.method.startswith("system."):
                if not source_node or not any(n in source_node for n in ["l2", "orchestrator"]):
                    errors.append("High-risk administrative methods only allowed from orchestrator nodes")
        elif risk_level == RiskLevel.CRITICAL.value:
            # Most restrictive checks for critical-risk requests
            errors.append("Critical-risk requests require special approval")

        # Check for requests from unauthorized source nodes
        if source_node and "l3" in source_node and request.target != "client":
            # L3 nodes should typically only respond to requests, not initiate them to clients
            errors.append("L3 engine nodes should not initiate requests to clients")

        return len(errors) == 0, errors


class ValidationFirewall:
    """
    The security firewall that sits between L1 and L2 in distributed system
    All requests must pass through this gate before reaching orchestrator
    """
    def __init__(self, auth_provider: AuthProvider):
        self.middleware = SecurityMiddleware(auth_provider)
        self.request_cache = {}  # For idempotency across distributed system
        self.logger = logging.getLogger(__name__)
        self.distributed_idempotency_store = {}  # Shared idempotency store
        self.idempotency_ttl = 3600  # 1 hour TTL

    def process_request(self, request_data: Dict[str, Any], source_node: str = None) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Process an incoming request through the validation firewall
        :param request_data: Raw request data
        :param source_node: Node that originated the request
        :return: (should_forward, processed_data, errors)
        """
        # First, check for idempotency in distributed store
        idempotency_key = request_data.get("params", {}).get("idempotency_key")
        if idempotency_key and idempotency_key in self.distributed_idempotency_store:
            # Return cached response for idempotent requests
            cached_response = self.distributed_idempotency_store[idempotency_key]

            # Check TTL
            if time.time() - cached_response.get("created_at", 0) < self.idempotency_ttl:
                return True, cached_response["response"], []

        # Validate the request
        is_valid, errors, validated_data = self.middleware.validate_request(request_data, source_node)

        if not is_valid:
            return False, {}, errors

        # Process successful validation
        processed_request = {
            "original_request": request_data,
            "validated_request": validated_data["request"].to_dict(),
            "auth_context": validated_data["auth_context"],
            "risk_level": validated_data["risk_level"],
            "source_node": validated_data["source_node"],
            "validated_at": time.time(),
            "processing_node": getattr(self, 'node_id', 'validation_firewall'),
        }

        # Store in distributed idempotency cache if key exists
        if idempotency_key:
            self.distributed_idempotency_store[idempotency_key] = {
                "response": processed_request,
                "created_at": time.time(),
                "source_node": source_node
            }

        return True, processed_request, []

    def validate_target_access(self, auth_context: Dict[str, Any], target: str, source_node: str) -> bool:
        """
        Validate if authenticated user can access target in distributed context
        :param auth_context: Authentication context
        :param target: Target (orchestrator/engine/client)
        :param source_node: Source node type
        :return: Access allowed
        """
        user_permissions = auth_context.get("permissions", [])
        user_roles = auth_context.get("roles", [])

        # Engine access requires specific permissions
        if target == "engine":
            return ("engine_access" in user_permissions or
                   "admin" in user_permissions or
                   ("operator" in user_roles and source_node and "l2" in source_node))

        # Client access might be limited based on user role
        elif target == "client":
            return len(user_permissions) > 0  # Basic authenticated access

        # Orchestrator access requires basic permissions
        else:
            return len(user_permissions) > 0

    def log_security_event(self, event_type: str, details: Dict[str, Any], source_node: str = None):
        """Log security-related events in distributed context"""
        details["source_node"] = source_node
        details["timestamp"] = time.time()
        self.logger.info(f"DIST_SECURITY_EVENT: {event_type} - {details}")

    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics for distributed system"""
        return {
            "blocked_requests": getattr(self, '_blocked_count', 0),
            "allowed_requests": getattr(self, '_allowed_count', 0),
            "active_sessions": len(self.middleware.auth_provider.token_manager.active_tokens),
            "cached_requests": len(self.distributed_idempotency_store),
            "rate_limited_sources": len(self.middleware.rate_limits),
            "unique_nodes_processed": len({
                data.get("source_node") for data in self.distributed_idempotency_store.values()
            })
        }

    def sync_idempotency_store(self, cluster_nodes: list, sync_callback):
        """
        Sync idempotency store with other nodes in cluster
        """
        sync_data = {
            "idempotency_store": self.distributed_idempotency_store,
            "node_id": getattr(self, 'node_id', 'validation_firewall'),
            "timestamp": time.time()
        }

        # In a real implementation, this would sync with other cluster nodes
        for node in cluster_nodes:
            sync_callback(node, sync_data)

    def cleanup_expired_entries(self):
        """
        Clean up expired entries from stores
        """
        current_time = time.time()

        # Clean up expired idempotency entries
        expired_keys = [
            key for key, value in self.distributed_idempotency_store.items()
            if current_time - value.get("created_at", 0) >= self.idempotency_ttl
        ]

        for key in expired_keys:
            del self.distributed_idempotency_store[key]

        # Clean up old rate limit entries (done in _check_rate_limits method)
        # This is just a periodic cleanup trigger
