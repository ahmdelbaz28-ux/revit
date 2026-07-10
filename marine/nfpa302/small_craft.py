"""
marine/nfpa302/small_craft.py — NFPA 302 Fire Protection for Small Craft.
NFPA 302-2020 applies to craft <24m (65 ft) load line, including yachts,
workboats, and small commercial vessels. Replaces SOLAS for these craft.
"""
from __future__ import annotations

from marine.core.constants import (
    NFPA302_GALLEY_FIXED_AGENT,
    NFPA302_GALLEY_FIXED_SYSTEM_REQUIRED,
    NFPA302_PORTABLE_EXTINGUISHERS,
)
from marine.core.types import ComplianceResult, ShipProject


def required_portable_extinguishers(length_ft: float) -> ComplianceResult:
    """Return required portable extinguishers per NFPA 302 §6.2."""
    result = ComplianceResult(compliant=True, standard_reference="NFPA 302 §6.2")
    for (lo, hi), (rating, ext_type) in NFPA302_PORTABLE_EXTINGUISHERS.items():
        if lo <= length_ft < hi:
            result.details["min_rating"] = rating
            result.details["type"] = ext_type
            return result
    result.add_warning(f"Vessel length {length_ft} ft outside NFPA 302 scope.")
    return result

def validate_galley_fixed_system(has_fixed: bool) -> ComplianceResult:
    """NFPA 302 §7.4: galley requires fixed extinguishing system."""
    result = ComplianceResult(compliant=True, standard_reference="NFPA 302 §7.4")
    if NFPA302_GALLEY_FIXED_SYSTEM_REQUIRED and not has_fixed:
        result.add_finding(
            f"Galley requires fixed {NFPA302_GALLEY_FIXED_AGENT} system "
            f"per NFPA 302 §7.4."
        )
    return result

def is_in_scope(ship: ShipProject) -> bool:
    """Check if NFPA 302 applies (craft <24m LOA)."""
    return ship.is_small_craft

__all__ = [
    "is_in_scope",
    "required_portable_extinguishers",
    "validate_galley_fixed_system",
]
