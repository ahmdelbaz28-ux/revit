"""
QOMN-FIRE UNIFIED ERROR FRAMEWORK
Extended with parsing and file validation error types for the input pipeline.

Safety-Critical: Each error type maps to a specific physical failure mode.
Missing an error means a corrupted file passes silently = wrong building model = people die.
"""

from typing import Generic, Optional, TypeVar

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    def __init__(self, value: Optional[T] = None, error: Optional[E] = None):
        # BUG-43 FIX: Prevent constructing Result with neither value nor error.
        # A Result(value=None) without an error would be is_success=True but
        # crash on unwrap(). This is a trap in safety-critical code — a
        # "successful" result that crashes on access is worse than an error.
        if value is None and error is None:
            raise ValueError(
                "Result must hold either a value or an error, not neither. "
                "Use Result(value=x) for success or Result(error=e) for failure."
            )
        # BUG-1 FIX: Prevent constructing Result with BOTH value and error.
        if value is not None and error is not None:
            raise ValueError(
                f"Result cannot hold both value and error. "
                f"Got value={value!r} and error={error!r}. "
                f"Use Result(value=x) for success or Result(error=e) for failure."
            )
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
        if self._value is None:
            raise ValueError("Panic: Attempted to unwrap None value from success Result")
        return self._value

    def unwrap_or(self, default: T) -> T:
        """Return value if success, otherwise return default."""
        if self._error is not None:
            return default
        return self._value if self._value is not None else default

    def error(self) -> E:
        if self._error is None:
            raise ValueError("Panic: Attempted to fetch error of successful Result")
        return self._error

    # BUG-37 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        if self.is_success:
            return f"Result.ok({self._value!r})"
        return f"Result.err({self._error!r})"

class BaseEngineeringError(Exception):
    """Base class for all QOMN-FIRE engineering errors.

    BUG-3 FIX: Now inherits from Exception so errors can be caught by
    standard exception handlers and participate in Python's exception hierarchy.
    Previously, BaseEngineeringError was a plain class, so `except Exception`
    would NOT catch it — errors could escape error handling boundaries silently.
    In a safety-critical system, uncaught errors = silent failures = people die.
    """
    def __init__(self, message: str, code_ref: str, remedy: str):
        super().__init__(message)
        self.message = message
        self.code_ref = code_ref
        self.remedy = remedy

    def __repr__(self) -> str:
        return f"[{self.code_ref}] Error: {self.message} (Remedy: {self.remedy})"

    def __str__(self) -> str:
        return f"[{self.code_ref}] {self.message}"

class ConduitFillError(BaseEngineeringError): pass
class NECViolationError(BaseEngineeringError): pass
class HatchPlacementError(BaseEngineeringError): pass
class PhysicalConstraintError(BaseEngineeringError): pass
class FACPSelectionError(BaseEngineeringError): pass

# ── Input Parsing Pipeline Error Types ──
# These errors prevent corrupted BIM files from producing wrong fire protection designs.

class FileValidationError(BaseEngineeringError):
    """File does not meet structural requirements (existence, size, permissions)."""
    pass

class FormatError(BaseEngineeringError):
    """File format cannot be identified — magic bytes don't match any known specification."""
    pass

class VersionError(BaseEngineeringError):
    """File version is unsupported or incompatible with the parser."""
    pass

class CorruptionError(BaseEngineeringError):
    """File is structurally corrupted — missing mandatory sections or markers."""
    pass

class ConversionError(BaseEngineeringError):
    """DWG→DXF or RVT→IFC conversion failed — external tool error."""
    pass

class GeometryError(BaseEngineeringError):
    """Building geometry is physically impossible (zero-area rooms, unclosed boundaries)."""
    pass

class UnitError(BaseEngineeringError):
    """File uses wrong unit system (mm/inches instead of meters) — coordinates exceed limits."""
    pass
