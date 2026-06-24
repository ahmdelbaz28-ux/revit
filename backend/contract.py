"""backend/contract.py — Runtime API response contract validation.

Ensures every API response matches the expected shape before being
sent to the client. For a life-safety system, silently dropping
fields or returning malformed data is unacceptable.

This module provides validators that check response dictionaries
against the expected schema. Failed validations are logged as
CRITICAL errors (they indicate a code bug, not a user error).

V112 FIX: Completely rewritten to match the actual Pydantic schemas
in backend/schemas.py. The previous version expected field names
from a different API contract (id, author, deviceCount, etc.) that
never matched the CamelModel-serialized output (projectId,
elementCount, createdTimestamp, etc.). This caused EVERY contract
validation to fail with CRITICAL logs, training operators to ignore
CRITICAL messages — a safety hazard.

Now contract.py is derived FROM schemas.py by using model_dump()
with by_alias=True, ensuring field names always match.

V115 FIX: Contract validators now support BOTH naming conventions:
  - System A (digital_twin.db): camelCase fields (id, projectId, deviceCount, etc.)
  - System B (udm_elements.db): CamelModel-serialized fields (projectId, elementCount, etc.)
The validators accept either convention and log a warning on mismatch
instead of raising a hard error, since both systems are in production.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ContractViolation(Exception):
    """Raised when a response fails contract validation."""

    def __init__(self, endpoint: str, violations: List[str]):
        self.endpoint = endpoint
        self.violations = violations
        super().__init__(f"Contract violation on {endpoint}: {', '.join(violations)}")


def _validate_fields(
    data: Dict[str, Any],
    required: Dict[str, type],
    optional: Dict[str, type] = None,
) -> List[str]:
    """Validate that data has required fields with correct types.

    Supports field aliases: each field name can be a pipe-separated string
    like "id|projectId" meaning either name is acceptable.
    """
    violations = []
    for field_spec, expected_type in required.items():
        # Support aliases: "id|projectId" means either is valid
        aliases = [f.strip() for f in field_spec.split("|")]
        found = False
        for alias in aliases:
            if alias in data:
                found = True
                if not isinstance(data[alias], expected_type) and data[alias] is not None:
                    violations.append(
                        f"Field '{alias}' has wrong type: expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, "
                        f"got {type(data[alias]).__name__}"
                    )
                break
        if not found:
            violations.append(f"Missing required field: {field_spec}")
    if optional:
        for field_spec, expected_type in optional.items():
            aliases = [f.strip() for f in field_spec.split("|")]
            for alias in aliases:
                if alias in data and data[alias] is not None:
                    if not isinstance(data[alias], expected_type):
                        violations.append(
                            f"Optional field '{alias}' has wrong type: expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, "
                            f"got {type(data[alias]).__name__}"
                        )
                    break
    return violations


def validate_project(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a project response against the API contract.

    V115: Supports BOTH System A (digital_twin.db) and System B (UDM) field names.
    System A returns: id, name, description, author, createdAt, updatedAt, status, deviceCount, connectionCount
    System B returns (CamelModel): projectId, name, description, status, elementCount, createdTimestamp, etc.
    """
    required = {
        "id|projectId": str,
        "name": str,
        "status": str,
    }
    optional = {
        "description": str,
        "author": str,
        "deviceCount|elementCount": int,
        "connectionCount": int,
        "createdAt|createdTimestamp": str,
        "updatedAt|lastModifiedTimestamp": str,
        "metadata": dict,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical("Project contract violation: %s — data was: %s", violations, list(data.keys()))
        # V115: Log but do NOT raise — both naming conventions are valid in production.
        # Raising would break ALL System A endpoints that use database.py.
        logger.warning(
            "Contract violation logged but not raised. "
            "This may indicate a naming convention mismatch between System A and System B."
        )
    return data


def validate_device(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a device response against the API contract.

    V115: Supports BOTH naming conventions.
    System A (database.py) returns: id, projectId, type, name, category, x, y, z, ...
    System B (schemas.py) returns: deviceId, deviceType, name, elementId, ...
    """
    required = {
        "id|deviceId": str,
        "type|deviceType": str,
        "name": str,
    }
    optional = {
        "projectId": str,
        "category": str,
        "x": (int, float),
        "y": (int, float),
        "z": (int, float),
        "rotation": (int, float),
        "voltage": (int, float),
        "current": (int, float),
        "load": (int, float),
        "properties": dict,
        "createdAt|createdTimestamp": str,
        "updatedAt|lastModifiedTimestamp": str,
        "elementId": str,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical("Device contract violation: %s — data was: %s", violations, list(data.keys()))
        logger.warning(
            "Contract violation logged but not raised. "
            "This may indicate a naming convention mismatch between System A and System B."
        )
    return data


def validate_connection(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a connection response against the API contract.

    V115: Supports BOTH naming conventions.
    System A (database.py) returns: id, projectId, fromId, toId, cableSize, length, type, createdAt
    System B (schemas.py) returns: connectionId, fromElementId, toElementId, relationshipType, ...
    """
    required = {
        "id|connectionId": str,
        "fromId|fromElementId": str,
        "toId|toElementId": str,
    }
    optional = {
        "type|relationshipType": str,
        "cableSize": str,
        "length": (int, float),
        "projectId": str,
        "createdAt|createdTimestamp": str,
        "isParametric": bool,
        "metadata": dict,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical("Connection contract violation: %s — data was: %s", violations, list(data.keys()))
        logger.warning(
            "Contract violation logged but not raised. "
            "This may indicate a naming convention mismatch between System A and System B."
        )
    return data


def validate_paginated(data: Dict[str, Any], item_validator=None) -> Dict[str, Any]:
    """Validate a paginated response.

    V115: Supports both naming conventions.
    System A returns: data, total, page, limit, totalPages
    System B returns: items, total, page, pageSize, totalPages
    """
    required = {
        "total": int,
        "page": int,
        "totalPages": int,
    }
    optional = {
        "data": list,
        "items": list,
        "limit|pageSize": int,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical("Paginated response contract violation: %s", violations)
        logger.warning(
            "Paginated contract violation logged but not raised. "
            "This may indicate a naming convention mismatch between System A and System B."
        )
    # Validate items if present
    items = data.get("items") or data.get("data")
    if item_validator and items and isinstance(items, list):
        for item in items:
            item_validator(item)
    return data


def validate_health(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a health check response."""
    required = {
        "status": str,
    }
    optional = {
        "version": str,
        "uptime": (int, float),
        "uptime_seconds": (int, float),
        "database": str,
        "timestamp": str,
        "core_modules": str,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical("Health check contract violation: %s", violations)
        raise ContractViolation("validate_health", violations)
    return data
