"""
FireSafetyGenius v1.1 - Fire Safety Analysis System
=============================================
"""
__version__ = "1.1.0"
__author__ = "FireAI Team"

# Core exports
from . import knowledge
from . import reasoning
from . import engineering
from . import digital_twin
from . import pipeline
from . import cli

__all__ = ["__version__", "knowledge", "reasoning", "engineering", "digital_twin", "pipeline", "cli"]
