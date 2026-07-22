"""
backend/schema_base.py — Shared Pydantic V2 base classes and utilities.

V300 ARCHITECTURE: Extracted from backend/schemas.py to eliminate duplication
between schemas.py and models.py. Both files previously defined their own
CamelModel, _to_camel, and _validate_json_size_and_depth.

This module provides:
  - CamelModel: Base model with camelCase serialization
  - _to_camel: snake_case → camelCase converter
  - _validate_json_size_and_depth: JSON DoS protection
  - Common field factory functions

Usage:
    from backend.schema_base import CamelModel, _to_camel, validate_json_size
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# CamelCase serialization
# ============================================================================

def _to_camel(field_name: str) -> str:
    """Convert snake_case to camelCase for API serialization."""
    components = field_name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class CamelModel(BaseModel):
    """Base model that serializes snake_case fields as camelCase.

    All Response schemas serialize to camelCase (e.g., element_id → elementId),
    matching the API contract. Create/Update schemas also accept camelCase
    input via populate_by_name=True.
    """

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ============================================================================
# JSON size/depth validation
# ============================================================================

def _validate_json_size_and_depth(
    value: Any,
    field_name: str,
    max_bytes: int = 10240,
    max_depth: int = 5,
) -> Any:
    """
    Validate JSON dict size and nesting depth.

    Prevents denial-of-service via deeply nested or oversized JSON payloads.
    - max_bytes: Maximum serialized JSON size in bytes (default 10KB)
    - max_depth: Maximum nesting depth (default 5)
    """
    import json as _json

    try:
        serialized = _json.dumps(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name}: must be JSON-serializable ({e}")

    if len(serialized) > max_bytes:
        raise ValueError(
            f"{field_name}: JSON size ({len(serialized)} bytes) exceeds "
            f"maximum ({max_bytes} bytes)"
        )

    def _get_depth(obj: Any, current: int = 0) -> int:
        if isinstance(obj, dict):
            if not obj:
                return current
            return max(_get_depth(v, current + 1) for v in obj.values())
        if isinstance(obj, list):
            if not obj:
                return current
            return max(_get_depth(item, current + 1) for item in obj)
        return current

    depth = _get_depth(value)
    if depth > max_depth:
        raise ValueError(
            f"{field_name}: nesting depth ({depth}) exceeds maximum ({max_depth})"
        )

    return value


# ============================================================================
# Common field factories
# ============================================================================

def common_name_field() -> Field:
    """Standard name field with null-byte sanitization."""
    return Field(min_length=1, max_length=255)


def common_description_field() -> Field:
    """Standard description field with DoS protection."""
    return Field(default="", max_length=5000)


def common_metadata_field() -> Field:
    """Standard metadata field with size/depth limits."""
    return Field(default=None, validate_default=True)
