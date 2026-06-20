"""FireAI Backend API Routers."""

from __future__ import annotations

import logging as _logging
from typing import TYPE_CHECKING

_logger = _logging.getLogger(__name__)


def _lazy_import(name: str):
    """Lazily import a router module -- fails silently if unavailable."""
    import importlib as _importlib
    try:
        return _importlib.import_module(f"backend.routers.{name}")
    except ImportError:
        _logger.debug("Router '%s' not available (optional dependency missing)", name)
        return None


__all__ = [
    "health",
    "projects",
    "devices",
    "connections",
    "connections_v2",
    "elements",
    "conflicts",
    "reports",
    "exports",
    "sync",
    "monitor",
    "memory",
    "workflow",
    "environment",
    "dwg",
    "qomn",
    "facp",
    "api_keys",
    "autocad",
    "revit",
    "digital_twin",
    "ml",
]

if TYPE_CHECKING:
    from . import health
    from . import projects
    from . import devices
    from . import connections
    from . import connections_v2
    from . import elements
    from . import conflicts
    from . import reports
    from . import exports
    from . import sync
    from . import monitor
    from . import memory
    from . import workflow
    from . import environment
    from . import dwg
    from . import qomn
    from . import facp
    from . import api_keys
    from . import autocad
    from . import revit
    from . import digital_twin
    from . import ml

# Lazily import all routers in __all__ so they are present in the module namespace
for _name in __all__:
    _mod = _lazy_import(_name)
    if _mod is not None:
        globals()[_name] = _mod
