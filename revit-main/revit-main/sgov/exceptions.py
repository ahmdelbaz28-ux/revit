"""
SGL Exceptions - Governance Layer Exception Classes
"""


class GovernanceException(Exception):
    """Base exception for governance layer"""
    def __init__(self, message: str, code: str = "GOVERNANCE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ValidationException(GovernanceException):
    """Exception raised for validation errors"""
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code)


class PolicyException(GovernanceException):
    """Exception raised for policy errors"""
    def __init__(self, message: str, code: str = "POLICY_ERROR"):
        super().__init__(message, code)


class AuditException(GovernanceException):
    """Exception raised for audit errors"""
    def __init__(self, message: str, code: str = "AUDIT_ERROR"):
        super().__init__(message, code)


class EnforcementException(GovernanceException):
    """Exception raised for enforcement errors"""
    def __init__(self, message: str, code: str = "ENFORCEMENT_ERROR"):
        super().__init__(message, code)


class IdempotencyException(GovernanceException):
    """Exception raised for idempotency violations"""
    def __init__(self, message: str, code: str = "IDEMPOTENCY_ERROR"):
        super().__init__(message, code)