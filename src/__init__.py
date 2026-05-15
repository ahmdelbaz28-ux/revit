"""
FireSafetyGenius v1.1 - Fire Safety Analysis System
=============================================

⚠️ LIFE-SAFETY CRITICAL WARNING ⚠️
=============================================

This software is a PATTERN-MATCHING tool, NOT a replacement for 
Professional Engineer (PE) judgment.

- All outputs require PE verification and signature
- Buildings outside validated scope require manual review
- This system does NOT guarantee correct fire safety decisions
- Using outputs without PE review may result in DEATH

See: docs/SCOPE_DOCUMENT.md for validated scope
See: docs/PE_LIABILITY_PROTOCOL.md for PE requirements

⚠️ USE AT YOUR OWN RISK - LIVES MAY DEPEND ON IT ⚠️

"""
__version__ = "1.1.0"
__author__ = "FireCalc V8 Team"  # V8: no longer "AI"

# Core exports
from . import knowledge
from . import reasoning
from . import engineering
# V8: digital_twin disabled - now in DISABLED_BY_V8 state
# from . import digital_twin
try:
    from . import pipeline
except ImportError:
    pipeline = None
from . import cli

__all__ = ["__version__", "knowledge", "reasoning", "engineering", "cli"]
