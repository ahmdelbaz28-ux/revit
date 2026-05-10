"""
Core Layer - Unified Definitions and Truth Model
====================================
The single source of truth for the entire system.

Core provides:
- core.models: Unified class definitions (Room, Device, Obstruction, Violation)
- core.truth_model: Ground truth evaluation
"""

from core.models import Room, Device, Obstruction, Violation, NFPAStandard
from core.truth_model import TruthState, evaluate_truth, is_repair_valid, quantize_point

__all__ = [
    'Room', 'Device', 'Obstruction', 'Violation', 'NFPAStandard',
    'TruthState', 'evaluate_truth', 'is_repair_valid', 'quantize_point'
]