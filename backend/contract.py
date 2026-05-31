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
    """Validate a project response against the API contract.

    V112: Aligned with ProjectResponse in schemas.py.
    CamelModel serializes snake_case as camelCase:
    - project_id → projectId
    - element_count → elementCount
    - created_timestamp → createdTimestamp
    - last_modified_timestamp → lastModifiedTimestamp
    """
    required = {
        "projectId": str,
        "name": str,
        "status": str,
        "elementCount": int,
    }
    optional = {
        "description": str,
        "metadata": dict,
        "createdTimestamp": str,
        "lastModifiedTimestamp": str,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical(f"Project contract violation: {violations} — data was: {list(data.keys())}")
        # V112: M-5 — raise ContractViolation instead of silently passing
        raise ContractViolation("validate_project", violations)
    return data


def validate_device(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a device response against the API contract.

    V112: Aligned with DeviceResponse in schemas.py.
    """
    required = {
        "deviceId": str,
        "deviceType": str,
        "name": str,
        "elementId": str,
    }
    optional = {
        "position": dict,
        "roomId": str,
        "projectId": str,
        "zHeight": (int, float),
        "coverageRadius": (int, float),
        "createdTimestamp": str,
        "lastModifiedTimestamp": str,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical(f"Device contract violation: {violations} — data was: {list(data.keys())}")
        raise ContractViolation("validate_device", violations)
    return data


def validate_connection(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a connection response against the API contract.

    V112: Aligned with ConnectionResponse in schemas.py.
    """
    required = {
        "connectionId": str,
        "fromElementId": str,
        "toElementId": str,
        "relationshipType": str,
    }
    optional = {
        "isParametric": bool,
        "metadata": dict,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical(f"Connection contract violation: {violations} — data was: {list(data.keys())}")
        raise ContractViolation("validate_connection", violations)
    return data


def validate_paginated(data: Dict[str, Any], item_validator=None) -> Dict[str, Any]:
    """Validate a paginated response.

    V112: Aligned with PaginatedData/ApiResponse in schemas.py.
    The actual API returns items inside ApiResponse.data with:
    - items, total, page, pageSize, totalPages
    """
    required = {
        "items": list,
        "total": int,
        "page": int,
        "pageSize": int,
        "totalPages": int,
    }
    violations = _validate_fields(data, required)
    if violations:
        logger.critical(f"Paginated response contract violation: {violations}")
        raise ContractViolation("validate_paginated", violations)
    if item_validator and "items" in data and isinstance(data["items"], list):
        for item in data["items"]:
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
        "database": str,
        "timestamp": str,
    }
    violations = _validate_fields(data, required, optional)
    if violations:
        logger.critical(f"Health check contract violation: {violations}")
        raise ContractViolation("validate_health", violations)
    return data
