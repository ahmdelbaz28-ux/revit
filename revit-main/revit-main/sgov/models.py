"""
SGL Models - Core Data Contracts with Strict Schema Validation
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


class Role(str, Enum):
    """User roles in the system"""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    SYSTEM_AGENT = "system_agent"


class RiskLevel(str, Enum):
    """Risk levels for requests"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionType(str, Enum):
    """Policy decision types"""
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_LIMITS = "ALLOW_WITH_LIMITS"


class ExecutionStatus(str, Enum):
    """Execution status types"""
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ExecutionLimits:
    """Execution limits for constrained execution"""
    max_execution_time_ms: int = 0
    max_memory_mb: int = 0
    max_tokens: int = 0


@dataclass
class ExecutionRequest:
    """Execution Request - Strict Schema Validation Required"""
    request_id: str
    user_id: str
    role: Role
    payload: Dict[str, Any]
    idempotency_key: str
    risk_level: RiskLevel
    timestamp: datetime
    validated: bool = False
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate the request after initialization"""
        if not self.request_id:
            raise ValueError("request_id is required")
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required")
        if not isinstance(self.role, Role):
            raise ValueError(f"role must be one of {list(Role)}")
        if not isinstance(self.risk_level, RiskLevel):
            raise ValueError(f"risk_level must be one of {list(RiskLevel)}")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dictionary")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime object")

    @classmethod
    def create(cls, 
               user_id: str, 
               role: str, 
               payload: Dict[str, Any], 
               idempotency_key: str, 
               risk_level: str = "low",
               metadata: Optional[Dict[str, Any]] = None) -> 'ExecutionRequest':
        """Create a new execution request with validation"""
        return cls(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            role=Role(role.lower()),
            payload=payload,
            idempotency_key=idempotency_key,
            risk_level=RiskLevel(risk_level.lower()),
            timestamp=datetime.utcnow(),
            validated=False,
            metadata=metadata or {}
        )


@dataclass
class PolicyDecision:
    """Policy Decision Object - Deterministic Decision Result"""
    decision: DecisionType
    reason: str
    rules_applied: List[str] = field(default_factory=list)
    limits: Optional[ExecutionLimits] = None
    decision_timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate the policy decision after initialization"""
        if not isinstance(self.decision, DecisionType):
            raise ValueError(f"decision must be one of {list(DecisionType)}")
        if not self.reason:
            raise ValueError("reason is required")


@dataclass
class FlowStep:
    """Single step in the execution flow trace"""
    layer: str
    latency_ms: float
    status: str = "completed"
    details: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionTrace:
    """Execution Trace Object - Full Request Tracking"""
    request_id: str
    flow: List[FlowStep] = field(default_factory=list)
    final_status: ExecutionStatus = ExecutionStatus.BLOCKED
    decision_details: Optional[PolicyDecision] = None
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    error_details: Optional[str] = None

    def __post_init__(self):
        """Validate the execution trace after initialization"""
        if not self.request_id:
            raise ValueError("request_id is required")
        if not isinstance(self.final_status, ExecutionStatus):
            raise ValueError(f"final_status must be one of {list(ExecutionStatus)}")

    def add_flow_step(self, layer: str, latency_ms: float, status: str = "completed", details: Optional[Dict[str, Any]] = None):
        """Add a step to the execution flow"""
        step = FlowStep(layer=layer, latency_ms=latency_ms, status=status, details=details)
        self.flow.append(step)

    def complete_trace(self, final_status: ExecutionStatus, decision: Optional[PolicyDecision] = None):
        """Complete the trace with final status"""
        self.final_status = final_status
        self.end_time = datetime.utcnow()
        self.decision_details = decision