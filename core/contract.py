"""
Core Contract Layer - Schema enforcement guardrail.
Prevents semantic authority conflicts by strictly defining allowed fields.
"""

from core.models import Violation

# Allowed fields in Violation (any other field is forbidden)
ALLOWED_VIOLATION_FIELDS = {"rule", "device_id", "severity", "value", "threshold", "location"}

# Forbidden fields that must never appear in Violation
FORBIDDEN_VIOLATION_FIELDS = {"message", "debug_info", "raw_output", "engine_version"}


def validate_violation(v: Violation) -> bool:
    """
    Ensure a Violation instance contains only allowed fields and no forbidden ones.
    
    Raises ValueError if a forbidden field is found.
    """
    for field in FORBIDDEN_VIOLATION_FIELDS:
        if hasattr(v, field):
            raise ValueError(f"Forbidden field '{field}' found in Violation")
    return True


# Rule: Only TruthModel may produce PASS/FAIL/REJECTED* states.
# No other layer (Engine, Normalizer, Oracle) is allowed to define these.
AUTHORIZED_STATE_DEFINERS = {"core.truth_model"}