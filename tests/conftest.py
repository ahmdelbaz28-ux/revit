"""
tests/conftest.py — FireAI Test Configuration
=============================================
Fixes:
  - Adds project root to sys.path for modules that use direct imports
    like `from core.models import ...` (required for pytest 9+ importlib mode).
  - Cleans None/empty entries from sys.path that can cause
    importlib.metadata.entry_points() to crash when hypothesis
    tries to discover entry points during collection.
  - Registers custom pytest marks to suppress warnings.
"""

import sys
import os
import pytest

# ── Project root in sys.path ────────────────────────────────────────────────
# pytest 9+ with importlib mode does not honor module-level sys.path.insert.
# Many test files import from `core.*` or `parsers.*` which are at project root.
# Add the project root so these imports resolve correctly.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── sys.path Sanitisation ────────────────────────────────────────────────────
# Some test modules or third-party libraries append None or "" to sys.path,
# which causes importlib.metadata.FastPath.mtime() to call os.stat(None)
# and raise TypeError.  This is triggered by hypothesis's entry_points()
# discovery at import time.  Remove any such entries BEFORE any test module
# is collected.
sys.path = [p for p in sys.path if p is not None and p != ""]

# ── Namespace collision fix ─────────────────────────────────────────────────
# The fireai package, when installed in development mode (pip install -e .)
# or when an .egg-info directory exists, causes setuptools to add
# /path/to/revit/fireai to sys.path. This makes `import core` resolve to
# fireai/core/ (which lacks models.py, conflict_resolver.py, etc.) instead
# of the top-level core/ directory.
# Fix: remove any sub-package paths that shadow top-level packages.
_paths_to_remove = []
for p in sys.path:
    # If a path is a subdirectory of the project root AND it's not the
    # project root itself, it can shadow top-level packages.
    if p.startswith(_PROJECT_ROOT + '/') and p != _PROJECT_ROOT:
        _paths_to_remove.append(p)
for p in _paths_to_remove:
    sys.path.remove(p)

# Ensure project root is at position 0
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
elif sys.path.index(_PROJECT_ROOT) > 0:
    sys.path.remove(_PROJECT_ROOT)
    sys.path.insert(0, _PROJECT_ROOT)


def pytest_configure(config):
    """Register custom marks to suppress PytestUnknownMarkWarning.
    
    Also fix namespace collision: fireai/ sub-package path shadows
    top-level core/ package, causing `from core.models import ...`
    to resolve to fireai/core/ instead of core/.
    """
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    
    # Fix namespace collision: remove sub-package paths that shadow 
    # top-level packages. This runs AFTER all plugins have initialized
    # and modified sys.path.
    _paths_to_remove = []
    for p in sys.path:
        if p.startswith(_PROJECT_ROOT + '/') and p != _PROJECT_ROOT:
            _paths_to_remove.append(p)
    for p in _paths_to_remove:
        sys.path.remove(p)
    
    # Ensure project root is at position 0
    if _PROJECT_ROOT in sys.path:
        sys.path.remove(_PROJECT_ROOT)
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture(autouse=True)
def _reset_audit_store():
    """Reset audit_store global state between tests.
    
    Also fixes the namespace collision where fireai/core/ shadows
    the top-level core/ package, causing `from core.models import ...`
    to fail with ModuleNotFoundError.
    
    This fixture ensures:
    1. sys.path has project root before fireai/ sub-package
    2. Cached 'core' module is cleared if it resolved to fireai/core/
    3. audit_store globals are reset between tests
    """
    # ── Fix namespace collision for `core` package ────────────────────────
    # Step 1: Ensure project root is BEFORE fireai/ in sys.path
    # so that `import core` resolves to top-level core/ not fireai/core/
    fireai_path = _PROJECT_ROOT + "/fireai"
    while fireai_path in sys.path:
        sys.path.remove(fireai_path)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    elif sys.path[0] != _PROJECT_ROOT:
        sys.path.remove(_PROJECT_ROOT)
        sys.path.insert(0, _PROJECT_ROOT)
    
    # Step 2: Clear cached 'core' module if it resolved to fireai/core/
    if "core" in sys.modules:
        cached_core = sys.modules["core"]
        if hasattr(cached_core, "__file__") and cached_core.__file__:
            if "/fireai/core/" in cached_core.__file__:
                to_delete = [k for k in list(sys.modules.keys()) 
                           if k == "core" or k.startswith("core.")]
                for k in to_delete:
                    del sys.modules[k]
    
    import fireai.core.audit_store as _as
    _orig_db_path = _as.DATABASE_PATH
    _orig_db_init = _as._db_initialized
    _orig_mem_conn = _as._memory_conn

    # ── Post-import cleanup ──────────────────────────────────────────────
    # Importing fireai.core.audit_store above may have re-poisoned
    # sys.path and sys.modules:
    #   1. Python re-added fireai/ to sys.path during the import
    #   2. 'core' in sys.modules now points to fireai/core/ (wrong)
    # This causes `from core.models import ...` in downstream test
    # methods to fail with ModuleNotFoundError.
    # Re-run the namespace collision fix AFTER the import.

    # Remove fireai/ from sys.path (re-added by Python's import machinery)
    _fireai_path = _PROJECT_ROOT + '/fireai'
    while _fireai_path in sys.path:
        sys.path.remove(_fireai_path)

    # Ensure project root is first
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    elif sys.path[0] != _PROJECT_ROOT:
        sys.path.remove(_PROJECT_ROOT)
        sys.path.insert(0, _PROJECT_ROOT)

    # Clear cached 'core' module if it resolved to fireai/core/
    if 'core' in sys.modules:
        _cached = sys.modules['core']
        if hasattr(_cached, '__file__') and _cached.__file__ and '/fireai/core/' in _cached.__file__:
            for _k in [k for k in list(sys.modules.keys()) if k == 'core' or k.startswith('core.')]:
                del sys.modules[_k]

    yield
    # After test: reset globals if they were changed
    if _as.DATABASE_PATH != _orig_db_path:
        _as.DATABASE_PATH = _orig_db_path
    _as._db_initialized = _orig_db_init
    _as._memory_conn = _orig_mem_conn
