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


@pytest.fixture(autouse=True)
def _reset_audit_store():
    """Reset audit_store global state between tests.
    
    The audit_store module uses global variables (DATABASE_PATH, _db_initialized,
    _memory_conn) that persist between tests, causing test isolation failures.
    This fixture ensures clean state for every test.
    """
    import fireai.core.audit_store as _as
    _orig_db_path = _as.DATABASE_PATH
    _orig_db_init = _as._db_initialized
    _orig_mem_conn = _as._memory_conn
    yield
    # After test: reset globals if they were changed
    if _as.DATABASE_PATH != _orig_db_path:
        _as.DATABASE_PATH = _orig_db_path
    _as._db_initialized = _orig_db_init
    _as._memory_conn = _orig_mem_conn
