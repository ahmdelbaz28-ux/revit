"""
QOMN-FIRE DETERMINISTIC ERROR FRAMEWORK
"""

from typing import Generic, TypeVar, Optional, Union

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    def __init__(self, value: Optional[T] = None, error: Optional[E] = None):
        self._value = value
        self._error = error

    @property
    def is_success(self) -> bool:
        return self._error is None

    @property
    def is_failure(self) -> bool:
        return self._error is not None

    def unwrap(self) -> T:
        if self._error is not None:
            raise ValueError(f"Panic: Attempted to unwrap failure Result: {self._error}")
        return self._value

    def error(self) -> E:
        if self._error is None:
            raise ValueError("Panic: Attempted to fetch error of successful Result")
        return self._error

class BaseEngineeringError:
    def __init__(self, message: str, code_ref: str, remedy: str):
        self.message = message
        self.code_ref = code_ref
        self.remedy = remedy

    def __repr__(self) -> str:
        return f"[{self.code_ref}] Error: {self.message} (Remedy: {self.remedy})"

class ConduitFillError(BaseEngineeringError):
    pass

class NECViolationError(BaseEngineeringError):
    pass

class HatchPlacementError(BaseEngineeringError):
    pass

class PhysicalConstraintError(BaseEngineeringError):
    pass
