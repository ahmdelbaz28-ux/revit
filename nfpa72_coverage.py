"""
NFPA 72 Coverage — Canonical re-export module.

This file exists for backward compatibility with code that uses bare imports
like `from nfpa72_coverage import ...`.  It re-exports everything from the
canonical implementation at `fireai.core.nfpa72_coverage`.

⚠️  DO NOT add any logic here — single source of truth is
    `fireai/core/nfpa72_coverage.py`.
"""

from fireai.core.nfpa72_coverage import *  # noqa: F401,F403
