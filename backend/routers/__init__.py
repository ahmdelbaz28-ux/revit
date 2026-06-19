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
    "api_keys",
    "autocad",
    "conflicts",
    "connections",
    "connections_v2",
    "devices",
    "digital_twin",
    "dwg",
    "elements",
    "environment",
    "exports",
    "facp",
    "health",
    "memory",
    "monitor",
    "projects",
    "qomn",
    "reports",
    "revit",
    "sync",
    "workflow",
]

if TYPE_CHECKING:
    from . import (
        api_keys,
        autocad,
        conflicts,
        connections,
        connections_v2,
        devices,
        digital_twin,
        dwg,
        elements,
        environment,
        exports,
        facp,
        health,
        memory,
        monitor,
        projects,
        qomn,
        reports,
        revit,
        sync,
        workflow,
    )

# Lazily import all routers in __all__ so they are present in the module namespace
for _name in __all__:
    _mod = _lazy_import(_name)
    if _mod is not None:
        globals()[_name] = _mod
