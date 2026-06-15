"""
Enhanced FACP Message Schema for Distributed System
"""
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(Enum):
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
    CLIENT = "client"
    ORCHESTRATOR = "orchestrator"
    ENGINE = "engine"


class TargetType(Enum):
    ORCHESTRATOR = "orchestrator"
    ENGINE = "engine"
    CLIENT = "client"


class ExecutionState(Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    ROUTED = "ROUTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StatusType(Enum):
    SUCCESS = "success"
    ERROR = "error"


class MessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"


class FACPRequest:
    """
    Enhanced FACP Request Object - Implements FACP/1.1 specification for distributed system
    """
    def __init__(
        self,
        id: str,
        method: str,
        params: Dict[str, Any],
        source: SourceType,
        target: TargetType,
        execution_state: ExecutionState,
        timestamp: Optional[str] = None,
        security: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None
    ):
        self.protocol = "FACP/1.1"
        self.type = MessageType.REQUEST.value
        self.id = id
        self.method = method
        self.params = params
        self.source = source.value
        self.target = target.value
        self.execution_state = execution_state.value
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.security = security or {}
        self.constraints = constraints or {
            "timeout_ms": 8000,
            "max_memory_mb": 512,
            "max_recursion_depth": 5
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary format"""
        return {
            "protocol": self.protocol,
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
            "execution_state": self.execution_state,
            "method": self.method,
            "params": self.params,
            "security": self.security,
            "constraints": self.constraints
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FACPRequest':
        """Create request from dictionary"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            method=data.get("method", ""),
            params=data.get("params", {}),
            source=SourceType(data.get("source", "client")),
            target=TargetType(data.get("target", "engine")),
            execution_state=ExecutionState(data.get("execution_state", "RECEIVED")),
            timestamp=data.get("timestamp"),
            security=data.get("security", {}),
            constraints=data.get("constraints", {})
        )


class FACPResponse:
    """
    Enhanced FACP Response Object - Implements FACP/1.1 specification for distributed system
    """
    def __init__(
        self,
        id: str,
        status: StatusType,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, str]] = None,
        trace: Optional[Dict[str, Any]] = None
    ):
        self.protocol = "FACP/1.1"
        self.type = MessageType.RESPONSE.value
        self.id = id
        self.status = status.value
        self.result = result or {}
        self.error = error
        self.trace = trace or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format"""
        response = {
            "protocol": self.protocol,
            "type": self.type,
            "id": self.id,
            "status": self.status,
            "result": self.result,
            "trace": self.trace
        }
        if self.error:
            response["error"] = self.error
        return response

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FACPResponse':
        """Create response from dictionary"""
        return cls(
            id=data["id"],
            status=StatusType(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            trace=data.get("trace")
        )


class FACPMessageValidator:
    """
    Validates FACP messages according to distributed system specification
    """

    @staticmethod
    def validate_request(request: FACPRequest) -> tuple[bool, List[str]]:
        """Validate FACP request message for distributed system"""
        errors = []

        # Validate protocol version
        if request.protocol != "FACP/1.1":
            errors.append(f"Invalid protocol version: {request.protocol} (expected FACP/1.1)")

        # Validate required fields
        if not request.id:
            errors.append("Request ID is required")

        if not request.method:
            errors.append("Method is required")

        if request.source not in [st.value for st in SourceType]:
            errors.append(f"Invalid source type: {request.source}")

        if request.target not in [tt.value for tt in TargetType]:
            errors.append(f"Invalid target type: {request.target}")

        if request.execution_state not in [es.value for es in ExecutionState]:
            errors.append(f"Invalid execution state: {request.execution_state}")

        # Validate timestamp format (basic check)
        try:
            datetime.fromisoformat(request.timestamp.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"Invalid timestamp format: {request.timestamp}")

        # Validate security block
        if not isinstance(request.security, dict):
            errors.append("Security block must be a dictionary")
        else:
            auth_token = request.security.get("auth_token")
            if auth_token is not None and not isinstance(auth_token, str):
                errors.append("Auth token must be a string or null")

            permissions = request.security.get("permissions", [])
            if not isinstance(permissions, list):
                errors.append("Permissions must be a list")

            risk_level = request.security.get("risk_level")
            if risk_level and risk_level not in [rl.value for rl in RiskLevel]:
                errors.append(f"Invalid risk level: {risk_level}")

            idempotency_key = request.security.get("idempotency_key")
            if idempotency_key is not None and not isinstance(idempotency_key, str):
                errors.append("Idempotency key must be a string or null")

        # Validate constraints
        if not isinstance(request.constraints, dict):
            errors.append("Constraints must be a dictionary")
        else:
            if "timeout_ms" in request.constraints:
                if not isinstance(request.constraints["timeout_ms"], int) or request.constraints["timeout_ms"] <= 0:
                    errors.append("timeout_ms must be a positive integer")

            if "max_memory_mb" in request.constraints:
                if not isinstance(request.constraints["max_memory_mb"], (int, float)) or request.constraints["max_memory_mb"] <= 0:
                    errors.append("max_memory_mb must be a positive number")

            if "max_recursion_depth" in request.constraints:
                if not isinstance(request.constraints["max_recursion_depth"], int) or request.constraints["max_recursion_depth"] <= 0:
                    errors.append("max_recursion_depth must be a positive integer")

        return len(errors) == 0, errors

    @staticmethod
    def validate_response(response: FACPResponse) -> tuple[bool, List[str]]:
        """Validate FACP response message for distributed system"""
        errors = []

        # Validate protocol version
        if response.protocol != "FACP/1.1":
            errors.append(f"Invalid protocol version: {response.protocol} (expected FACP/1.1)")

        # Validate required fields
        if not response.id:
            errors.append("Response ID is required")

        if response.status not in [st.value for st in StatusType]:
            errors.append(f"Invalid status: {response.status}")

        # Validate trace block
        if not isinstance(response.trace, dict):
            errors.append("Trace must be a dictionary")

        return len(errors) == 0, errors

    @staticmethod
    def sanitize_payload(payload: Any, max_size: int = 1024*1024) -> tuple[Any, bool, str]:  # 1MB default
        """Sanitize and validate payload size"""
        try:
            serialized = json.dumps(payload)
            if len(serialized.encode('utf-8')) > max_size:
                return None, False, f"Payload exceeds maximum size of {max_size} bytes"
            return payload, True, ""
        except Exception as e:
            return None, False, f"Failed to serialize payload: {str(e)}"
