"""
System Governance Layer (SGL) - Hard Enforcement Governance Module
This is the mandatory execution gate for the FireAI platform.
"""

from .governance_engine import SystemGovernanceEngine
from .models import ExecutionRequest, PolicyDecision, ExecutionTrace
from .exceptions import GovernanceException, ValidationException, PolicyException, AuditException

__version__ = "1.0.0"
__all__ = [
    "SystemGovernanceEngine",
    "ExecutionRequest",
    "PolicyDecision",
    "ExecutionTrace",
    "GovernanceException",
    "ValidationException",
    "PolicyException",
    "AuditException"
]