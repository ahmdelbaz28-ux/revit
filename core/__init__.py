"""
Core Layer - Unified Definitions and Truth Model
====================================
The single source of truth for the entire system.

Core provides:
- core.models: Unified class definitions (Room, Device, Obstruction, Violation)
- core.truth_model: Constraint utilities (decision logic moved to ComplianceOracle)
"""

from core.models import Room, Device, Obstruction, Violation, NFPAStandard
from core.truth_model import (
    TruthState,  # DEPRECATED - kept for backward compatibility
    is_repair_valid, 
    quantize_point,
    _is_geometry_valid,
    _is_ambiguous
)

__all__ = [
    'Room', 'Device', 'Obstruction', 'Violation', 'NFPAStandard',
    'TruthState', 'is_repair_valid', 'quantize_point',
    '_is_geometry_valid', '_is_ambiguous'
]