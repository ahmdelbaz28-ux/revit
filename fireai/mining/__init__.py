"""
fireai/mining/ — Mining Fire Protection & Safety Module
=======================================================

V214: New module for mining fire protection engineering.
Implements standards for both coal and metal/nonmetal mining:

  - NFPA 120-2022: Standard for Fire Prevention and Control in Coal Mines
  - NFPA 122-2022: Standard for Fire Prevention and Control in Metal/
    Nonmetal Mining and Metal Mineral Processing Facilities
  - MSHA 30 CFR Part 75: Mandatory Safety Standards for Underground Coal Mines
  - IEC 60079-0/10-1: Hazardous areas (methane + dust in mines)

Subpackages:
  core/       — Calculation engines (methane, ventilation, conveyor fire)
  detectors/  — Mine-specific detector selection + placement
  output/     — MSHA reports + evacuation plans
"""

from fireai.mining.core.conveyor_fire import ConveyorFireAnalyzer
from fireai.mining.core.methane_calculator import MethaneCalculator
from fireai.mining.core.msha_compliance import MSHAComplianceChecker
from fireai.mining.core.ventilation_calculator import VentilationCalculator

__all__ = [
    "ConveyorFireAnalyzer",
    "MSHAComplianceChecker",
    "MethaneCalculator",
    "VentilationCalculator",
]

__version__ = "1.0.0"
