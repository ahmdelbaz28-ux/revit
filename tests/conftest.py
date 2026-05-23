"""
tests/conftest.py — FireAI Test Configuration
=============================================
Fixes:
  - Cleans None/empty entries from sys.path that can cause
    importlib.metadata.entry_points() to crash when hypothesis
    tries to discover entry points during collection.
  - Registers custom pytest marks to suppress warnings.
"""

import sys

# ── sys.path Sanitisation ────────────────────────────────────────────────────
# Some test modules or third-party libraries append None or "" to sys.path,
# which causes importlib.metadata.FastPath.mtime() to call os.stat(None)
# and raise TypeError.  This is triggered by hypothesis's entry_points()
# discovery at import time.  Remove any such entries BEFORE any test module
# is collected.
sys.path = [p for p in sys.path if p is not None and p != ""]


def pytest_configure(config):
    """Register custom marks to suppress PytestUnknownMarkWarning."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
