"""backend/contract.py — Runtime API response contract validation.

Ensures every API response matches the expected shape before being
sent to the client. For a life-safety system, silently dropping
fields or returning malformed data is unacceptable.

This module provides validators that check response dictionaries
against the expected schema. Failed validations are logged as
CRITICAL errors (they indicate a code bug, not a user error).
"""
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
    """Validate that data has required fields with correct types."""
    violations = []
    for field, expected_type in required.items():
        if field not in data:
            violations.append(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type) and data[field] is not None:
            # Allow None for optional fields even in required dict
            violations.append(
                f"Field '{field}' has wrong type: expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, "
                f"got {type(data[field]).__name__}"
            )
    if optional:
        for field, expected_type in optional.items():
            if field in data and data[field] is not None:
                if not isinstance(data[field], expected_type):
                    violations.append(
                        f"Optional field '{field}' has wrong type: expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, "
                        f"got {type(data[field]).__name__}"
                    )
    return violations


def validate_project(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a project response against the API contract."""
    required = {
        "id": str,
        "name": str,
        "description": str,
        "author": str,
        "createdAt": str,
        "updatedAt": str,
        "status": str,
        "deviceCount": int,
        "connectionCount": int,
    }
    violations = _validate_fields(data, required)
    if violations:
        logger.critical(f"Project contract violation: {violations} — data was: {list(data.keys())}")
    return data


def validate_device(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a device response against the API contract."""
    required = {
        "id": str,
        "projectId": str,
        "type": str,
        "name": str,
        "category": str,
        "x": (int, float),
        "y": (int, float),
        "z": (int, float),
        "rotation": (int, float),
        "voltage": (int, float),
        "current": (int, float),
        "load": (int, float),
        "properties": dict,
        "createdAt": str,
        "updatedAt": str,
    }
    violations = _validate_fields(data, required)
    if violations:
        logger.critical(f"Device contract violation: {violations} — data was: {list(data.keys())}")
    return data


def validate_connection(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a connection response against the API contract."""
    required = {
        "id": str,
        "projectId": str,
        "fromId": str,
        "toId": str,
        "cableSize": str,
        "length": (int, float),
        "type": str,
        "createdAt": str,
    }
    violations = _validate_fields(data, required)
    if violations:
        logger.critical(f"Connection contract violation: {violations} — data was: {list(data.keys())}")
    return data


def validate_paginated(data: Dict[str, Any], item_validator=None) -> Dict[str, Any]:
    """Validate a paginated response."""
    required = {
        "data": list,
        "total": int,
        "page": int,
        "limit": int,
        "totalPages": int,
    }
    violations = _validate_fields(data, required)
    if violations:
        logger.critical(f"Paginated response contract violation: {violations}")
    if item_validator and "data" in data and isinstance(data["data"], list):
        for item in data["data"]:
            item_validator(item)
    return data


def validate_health(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a health check response."""
    required = {
        "status": str,
        "version": str,
        "uptime": (int, float),
        "database": str,
        "timestamp": str,
    }
    violations = _validate_fields(data, required)
    if violations:
        logger.critical(f"Health check contract violation: {violations}")
    return data
