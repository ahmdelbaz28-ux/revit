"""
NFPA 72 Calculations — Canonical re-export module.

This file exists for backward compatibility with code that uses bare imports
like `from nfpa72_calculations import ...`.  It re-exports everything from the
canonical implementation at `fireai.core.nfpa72_calculations`.

⚠️  DO NOT add any logic here — single source of truth is
    `fireai/core/nfpa72_calculations.py`.
"""

from fireai.core.nfpa72_calculations import *  # noqa: F401,F403
