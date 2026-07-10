"""
marine/iec60092/electrical_installations.py — Ship Electrical IEC 60092-3xx
============================================================================
Implements ship electrical system sizing for fire-protection systems per:
    - IEC 60092-301: Main power generation & distribution
    - IEC 60092-302: Low-voltage switchboards
    - IEC 60092-303: Transformers
    - IEC 60092-304: Semiconductor converters
    - IEC 60092-350: Cables
    - IEC 60092-370: Cable insulation

SOLAS II-2/5.1.3 mandates the fire-detection system be powered from both
the main and emergency switchboard, with ≥30 min battery autonomy (UPS).
"""

from __future__ import annotations

from marine.engine.ship_power import (  # noqa: F401  # M4 refactor
    design_fire_system_power,
    validate_insulation_monitoring,
)

__all__ = ["design_fire_system_power", "validate_insulation_monitoring"]
