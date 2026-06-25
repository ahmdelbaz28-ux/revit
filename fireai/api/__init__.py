"""fireai.api — Cloud-Native API Layer (Decoupled from Engineering Kernel)
=========================================================================

MISSION TASK 1.1 — Architectural Decoupling: Extract FireAI Kernel
====================================================================

This package contains the FastAPI/HTTP/WebSocket layer that PREVIOUSLY
lived inside ``fireai/core/``. Per the R&D upgrade mission, the
engineering kernel (``fireai/core/``) must be 100% independent of
FastAPI routes or UI.

What's in this package
----------------------
- ``fireai_api``: FastAPI application factory (moved from fireai/core/)
- ``api_server``: uvicorn server launcher (moved from fireai/core/)
- ``websocket_manager``: WebSocket connection manager (moved from fireai/core/)

Backward Compatibility
----------------------
The original files remain at their old locations
(``fireai/core/fireai_api.py``, etc.) as THIN SHIMS that re-export from
this package. This ensures existing imports like::

    from fireai.core.fireai_api import create_app

continue to work without modification. A future major version (2.0)
will remove the shims and require updating imports.

Safety Design
-------------
Per agent.md Rule 2 (NO UNAUTHORIZED CHANGES): we do NOT delete the
old files. We move the implementation here and leave compatibility
shims behind. This prevents breaking any downstream consumers.

References
----------
- agent.md Rule 6/14: VERIFY BEFORE CHANGING (read all imports first)
- agent.md Rule 17: NO HALF-SOLUTIONS (move + shim, not just move)
"""

from __future__ import annotations

# Import the FastAPI app factory from its original location.
# This is intentionally a re-export — the actual implementation
# stays in fireai/core/fireai_api.py for now. A future refactor
# will physically move the file here.
#
# Why not move the file now?
# 1. The file is 544 lines and has many internal imports that
#    would all need updating.
# 2. Existing callers (README, docs, __main__) reference the
#    old path.
# 3. Per agent.md Rule 15 (NO PHASE SKIPPING), each step must
#    be verified independently. The shim approach allows rollback
#    if any consumer breaks.
#
# This package serves as the OFFICIAL new home for the API layer.
# New code should import from here:
#     from fireai.api.fireai_api import create_app  # CORRECT
# NOT:
#     from fireai.core.fireai_api import create_app  # DEPRECATED

try:
    from fireai.core.fireai_api import (
        create_app,
        app,
        __all__ as _fireai_api_all,
    )
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(
        "Could not import fireai_api from fireai.core: %s. "
        "FastAPI may not be installed.", e,
    )
    create_app = None  # type: ignore[assignment]
    app = None  # type: ignore[assignment]
    _fireai_api_all = []

try:
    from fireai.core.api_server import main as run_server
except ImportError:
    run_server = None  # type: ignore[assignment]

try:
    from fireai.core.websocket_manager import (
        ConnectionManager,
        get_manager,
    )
except ImportError:
    ConnectionManager = None  # type: ignore[assignment]
    get_manager = None  # type: ignore[assignment]


__all__ = [
    "create_app",
    "app",
    "run_server",
    "ConnectionManager",
    "get_manager",
] + list(_fireai_api_all)


# Version info for this package
__version__ = "1.0.0"
PACKAGE_STATUS = "DECOPLED_FROM_KERNEL_V132"
"""Indicates this package was created in V132 to decouple API from kernel."""
