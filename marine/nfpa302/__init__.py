"""marine/nfpa302 — NFPA 302 Fire Protection for Craft and Small Vessels."""
from marine.nfpa302.small_craft import (
    is_in_scope,
    required_portable_extinguishers,
    validate_galley_fixed_system,
)

__all__ = [
    "is_in_scope", "required_portable_extinguishers",
    "validate_galley_fixed_system",
]
