"""backend.core.models — compatibility shim.

This module must *only* re-export the authoritative domain models from the
op-level ``core.models``.

The previous implementation both:
1) dynamically loaded ``core/models.py`` under a non-canonical module name, and
2) then *redefined* a second, conflicting set of dataclasses.

That double-load/redefinition breaks dataclass type resolution during pytest
collection (e.g., crashes inside dataclasses when ``__module__`` cannot be
resolved).

Fix: import ``core.models`` normally and re-export its public symbols.
"""

from __future__ import annotations

import importlib

_core_models = importlib.import_module("core.models")

# Re-export everything from the authoritative module.
globals().update(_core_models.__dict__)

# Hard guarantee for internal symbol contract used by backend/core/database.py.
# Some runtimes/linters may still fail ImportError if the symbol is present in
# __all__ but not actually bound in this module's globals at import time.
_ELEMENT_UPDATABLE_KEYS = getattr(_core_models, "_ELEMENT_UPDATABLE_KEYS", None)
if _ELEMENT_UPDATABLE_KEYS is not None:
    globals()["_ELEMENT_UPDATABLE_KEYS"] = _ELEMENT_UPDATABLE_KEYS

# Explicitly define __all__ to avoid Pylance dynamic operation warnings
# Get the original __all__ from core.models if available, otherwise generate it
original_all = getattr(_core_models, "__all__", None)
if original_all is not None:
    __all__ = list(original_all)
else:
    # Fallback: generate from public attributes (non-private)
    __all__ = [k for k in _core_models.__dict__.keys() if not k.startswith("_")]

# Ensure _ELEMENT_UPDATABLE_KEYS is included if it exists
if "_ELEMENT_UPDATABLE_KEYS" not in __all__ and _ELEMENT_UPDATABLE_KEYS is not None:
    __all__.append("_ELEMENT_UPDATABLE_KEYS")

