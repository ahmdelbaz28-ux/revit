"""
core — Compatibility shim for the Universal Data Model (UDM) layer.

This package exists SOLELY to satisfy import references throughout the
codebase that use ``from core.models import ...`` and
``from core.database import ...``.

The canonical definitions live in:
  - backend/schemas.py  — Pydantic API schemas (ElementType, ChangeSource, ConflictType, …)
  - core/models.py      — Dataclass domain models (Point3D, Geometry, UniversalElement, …)
  - core/database.py    — UniversalDataModel SQLite store

SAFETY NOTE: Do NOT add business logic here. This is a re-export hub only.
Any new domain types must be defined in core/models.py and re-exported here.
"""

from core.database import (  # noqa: F401
    UniversalDataModel,
)
from core.models import (  # noqa: F401
    ChangeSource,
    Conflict,
    ConflictType,
    ElementType,
    Geometry,
    Point3D,
    Relationship,
    SemanticProperties,
    UniversalElement,
)
