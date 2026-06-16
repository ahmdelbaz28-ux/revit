"""FireAI Backend API Routers."""

from __future__ import annotations

import logging as _logging

_logger = _logging.getLogger(__name__)


def _lazy_import(name: str):
    """Lazily import a router module — fails silently if unavailable."""
    try:
        return __import__(f"backend.routers.{name}", fromlist=[name])
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
]

# Lazily import all routers in __all__ so they are present in the module namespace
for _name in __all__:
    _mod = _lazy_import(_name)
    if _mod is not None:
        globals()[_name] = _mod
del _name, _mod
