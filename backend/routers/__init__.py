"""FireAI Backend API Routers."""

import logging as _logging
from typing import TYPE_CHECKING

_logger = _logging.getLogger(__name__)


def _lazy_import(name: str):
    """Lazily import a router module -- fails gracefully if unavailable.

    Catches ImportError (optional dependency missing), NameError (typing
    import bug — see V143 NOSONAR cleanup), SyntaxError (broken file),
    and AttributeError (failed attribute access during module init).
    A single broken router must NOT prevent the other 20 routers from
    loading and the entire backend.app from starting.

    The failure is logged at WARNING level so operators see it in CI/CD
    logs and production logs, and can fix the broken router without
    blocking the rest of the API.
    """
    import importlib as _importlib
    try:
        return _importlib.import_module(f"backend.routers.{name}")
    except (ImportError, NameError, SyntaxError, AttributeError) as exc:
        _logger.warning(
            "Router '%s' failed to load (%s: %s) — other routers continue",
            name, type(exc).__name__, exc,
        )
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
