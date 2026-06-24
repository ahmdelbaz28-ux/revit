"""fireai/v17_core — V17 Critical Life-Safety Triad
==================================================
The three modules that prevent AHJ rejection and ensure real-world
life safety. These are the V17 "Critical Trilogy":

  1. AcousticSPLCalculator — NFPA 72 §18.4 audible notification compliance
  2. StrictBatterySizer    — NFPA 72 §10.6.7 battery aging & temperature derating
  3. TenabilityEvaluator  — NFPA 101 §9.3 ASET vs RSET dynamic tenability

Each module wraps the physics-correct implementations in fireai.core
and adds DecisionProvenance audit trails for AHJ submittal.

Key corrections from consultant's original code:
  - Acoustic: 2D → 3D distance, wrong formula 20*log10(d) → 20*log10(d/d_ref),
    behind_closed_door on speaker → proper Barrier system
  - Battery: Simple 25% factor → IEEE 485 temperature table + IEEE 1188 aging
    + Peukert discharge rate correction
  - ASET/RSET: Fixed 1.0 m/s speed → occupancy-based (NFPA 101/SFPE),
    60s fixed delay → occupancy-based premovement delays,
    2.0 safety factor → risk-category-based safety factors
"""

from fireai.v17_core.acoustic_calculator import AcousticSPLCalculator
from fireai.v17_core.battery_calculator import StrictBatterySizer
from fireai.v17_core.dynamic_tenability_evaluator import TenabilityEvaluator

__all__ = [
    "AcousticSPLCalculator",
    "StrictBatterySizer",
    "TenabilityEvaluator",
]
