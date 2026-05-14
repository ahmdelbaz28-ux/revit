"""
FireSafetyGenius v1.1 - Fire Safety Analysis System
=============================================
"""
__version__ = "1.1.0"
__author__ = "FireCalc V8 Team"  # V8: no longer "AI"

# Core exports
from . import knowledge
from . import reasoning
from . import engineering
# V8: digital_twin disabled - now in DISABLED_BY_V8 state
# from . import digital_twin
from . import pipeline
from . import cli

__all__ = ["__version__", "knowledge", "reasoning", "engineering", "pipeline", "cli"]
