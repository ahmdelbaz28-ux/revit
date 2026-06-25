"""bim_input_sanitizer.py — Safety-Critical Input Sanitization for BIM Parameters
================================================================================
LIFE-SAFETY CRITICAL: Unsanitized inputs to BIM parameters can cause:
  1. Remote Code Execution (RCE) via eval()/exec() in MCP tool handlers
  2. SQL Injection via unsanitized room names written to databases
  3. Path Traversal via file paths in export/import handlers
  4. Cross-Site Scripting (XSS) in web dashboard displays
  5. Corrupted BIM model parameters that cause incorrect fire calculations

OWASP Top 10 (A03:2021-Injection): Input injection is the #3 most critical
web application security risk. In a fire protection system, injection can
lead to:
  - Altering sprinkler pipe sizes via SQL injection
  - Deleting audit trails via command injection
  - Stealing building design data via XSS

This module provides whitelist-based input sanitization for all parameters
that flow from external sources (MCP, API, user input) into BIM models
and fire protection calculations.

Design Principle: "Never trust input from outside the system boundary."
"""

from __future__ import annotations

import logging
import math
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SANITIZATION PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# BIM parameter names: alphanumeric, underscores, hyphens, dots, spaces
_BIM_PARAM_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\s]+$')

# Room names: alphanumeric, spaces, hyphens, parentheses, dots, apostrophes
_ROOM_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\s\.\'()\/\\,&:;]+$')

# Numeric parameter values: digits, decimal point, negative sign, scientific notation
_NUMERIC_PATTERN = re.compile(r'^-?\d+\.?\d*([eE][+-]?\d+)?$')

# File paths: alphanumeric, slashes, dots, hyphens, underscores
_SAFE_PATH_PATTERN = re.compile(r'^[a-zA-Z0-9_\-./\\]+$')

# Dangerous patterns that indicate injection attempts
_INJECTION_PATTERNS = [
    re.compile(r';.*\b(import|os|sys|subprocess|eval|exec|open|write)\b', re.IGNORECASE),
    re.compile(r'(__import__|getattr|setattr|delattr|globals|locals)\s*\(', re.IGNORECASE),
    re.compile(r'<\s*script', re.IGNORECASE),  # XSS
    re.compile(r'javascript:', re.IGNORECASE),  # XSS
    re.compile(r'\.\.[/\\]'),  # Path traversal
    re.compile(r'(\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bALTER\b)\s', re.IGNORECASE),  # SQL
    re.compile(r'(\'|\")\s*(OR|AND)\s+.*[=<>]', re.IGNORECASE),  # SQL injection
    re.compile(r'\b(UNION\s+SELECT|SELECT\s+.+\s+FROM)\b', re.IGNORECASE),  # SQL injection
]


# ═══════════════════════════════════════════════════════════════════════════════
# SANITIZATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def sanitize_bim_parameter(param_value: str) -> str:
    """Sanitize a string value intended for writing to a BIM parameter.

    SAFETY: BIM parameter values are written to Revit model elements.
    If these values contain injection payloads, they can:
      - Corrupt the .rvt model database
      - Execute arbitrary code if processed by eval/exec
      - Steal engineering data via XSS in web dashboards

    This function uses a whitelist approach — only ALLOWED characters
    pass through. Everything else is stripped.

    Args:
        param_value: Raw string input from external source.

    Returns:
        Sanitized string with only safe characters.

    Raises:
        ValueError: If input is not a string.
        ValueError: If injection pattern detected (potential attack).

    Example:
        >>> sanitize_bim_parameter("Office Room 101")
        'Office Room 101'
        >>> sanitize_bim_parameter("; import os; os.system('rm -rf /') #")
        ValueError: Injection pattern detected

    """
    if not isinstance(param_value, str):
        raise ValueError(
            f"Input parameter must be a string, got {type(param_value).__name__}."
        )

    # Check for injection patterns FIRST (before sanitizing)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(param_value):
            logger.critical(
                f"[SECURITY ALERT]: Injection pattern detected in BIM parameter. "
                f"Original: '{param_value}'. Pattern: {pattern.pattern}. "
                "This may be an active attack on the fire protection system."
            )
            raise ValueError(
                "Potential injection attack detected in input. "
                "The value contains a pattern consistent with code/SQL injection. "
                "For safety, this input is REJECTED. "
                "[OWASP A03:2021-Injection]"
            )

    # Whitelist: alphanumeric, spaces, safe design punctuation
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\s\.\(\)/\\,:;\'\"]', '', param_value)

    if sanitized != param_value:
        logger.warning(
            f"[SANITIZATION]: BIM parameter sanitized. "
            f"Original: '{param_value}' → Sanitized: '{sanitized}'. "
            "Non-whitelisted characters were removed."
        )

    return sanitized


def sanitize_room_name(room_name: str) -> str:
    """Sanitize a room name from BIM model or external input.

    SAFETY: Room names are used for:
      - Hazard classification (keyword matching)
      - Database storage (SQL injection risk)
      - Report generation (XSS risk in web dashboards)
      - Audit trails (log injection risk)

    Args:
        room_name: Raw room name string.

    Returns:
        Sanitized room name with only safe characters.

    Raises:
        ValueError: If injection pattern detected.

    """
    if not isinstance(room_name, str):
        raise ValueError(
            f"Room name must be a string, got {type(room_name).__name__}."
        )

    # Check for injection patterns
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(room_name):
            logger.critical(
                f"[SECURITY ALERT]: Injection pattern in room name: '{room_name}'. "
                "This may be an attempt to inject malicious code via BIM data."
            )
            raise ValueError(
                "Potential injection in room name. Input REJECTED for safety."
            )

    # Whitelist room name characters
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\s\.\'()\/\\,&:;]', '', room_name)

    if sanitized != room_name:
        logger.warning(
            f"[SANITIZATION]: Room name sanitized. "
            f"'{room_name}' → '{sanitized}'"
        )

    return sanitized.strip()


def sanitize_file_path(file_path: str) -> str:
    """Sanitize a file path to prevent path traversal attacks.

    SAFETY: Path traversal (../../etc/passwd) can expose sensitive
    system files or write fire protection data to unauthorized locations.

    Args:
        file_path: Raw file path string.

    Returns:
        Sanitized file path.

    Raises:
        ValueError: If path traversal detected.
        ValueError: If path contains non-whitelisted characters.

    """
    if not isinstance(file_path, str):
        raise ValueError(
            f"File path must be a string, got {type(file_path).__name__}."
        )

    # Check for path traversal
    if '..' in file_path:
        logger.critical(
            f"[SECURITY ALERT]: Path traversal detected: '{file_path}'. "
            "This may be an attempt to access files outside the project directory."
        )
        raise ValueError(
            "Path traversal pattern detected. File paths must not contain '..'. "
            "This is a safety-critical system — unauthorized file access is FORBIDDEN."
        )

    # Whitelist path characters
    sanitized = re.sub(r'[^a-zA-Z0-9_\-./\\]', '', file_path)

    if sanitized != file_path:
        logger.warning(
            f"[SANITIZATION]: File path sanitized. "
            f"'{file_path}' → '{sanitized}'"
        )

    return sanitized


def validate_numeric_parameter(
    value: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    param_name: str = "parameter",
) -> float:
    """Validate and convert a string to a numeric parameter value.

    SAFETY: Numeric parameters (pipe diameter, pressure, flow rate)
    MUST be validated before use in engineering calculations.
    Invalid values cause incorrect fire protection designs.

    Args:
        value: String representation of the numeric value.
        min_value: Minimum allowed value (inclusive).
        max_value: Maximum allowed value (inclusive).
        param_name: Parameter name for error messages.

    Returns:
        Validated float value.

    Raises:
        ValueError: If value is not a valid number.
        ValueError: If value is outside allowed range.

    Example:
        >>> validate_numeric_parameter("7.0", min_value=0.0, param_name="pressure")
        7.0
        >>> validate_numeric_parameter("-5.0", min_value=0.0, param_name="pressure")
        ValueError: pressure=-5.0 is below minimum 0.0

    """
    if not isinstance(value, str):
        raise ValueError(
            f"{param_name} must be a string for validation, got {type(value).__name__}."
        )

    # Strip whitespace
    value = value.strip()

    # Check numeric pattern
    if not _NUMERIC_PATTERN.match(value):
        raise ValueError(
            f"{param_name}='{value}' is not a valid numeric value. "
            "Engineering parameters must be numbers."
        )

    try:
        num_value = float(value)
    except (ValueError, OverflowError) as e:
        raise ValueError(
            f"{param_name}='{value}' cannot be converted to a number: {e}"
        )

    if not math.isfinite(num_value):
        raise ValueError(
            f"{param_name}={value} is not finite (NaN or Inf). "
            "Engineering parameters must be finite numbers."
        )

    if min_value is not None and num_value < min_value:
        raise ValueError(
            f"{param_name}={num_value} is below minimum {min_value}. "
            "This value is physically invalid for a fire protection parameter."
        )

    if max_value is not None and num_value > max_value:
        raise ValueError(
            f"{param_name}={num_value} exceeds maximum {max_value}. "
            "This value is physically invalid for a fire protection parameter."
        )

    return num_value


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "sanitize_bim_parameter",
    "sanitize_file_path",
    "sanitize_room_name",
    "validate_numeric_parameter",
]
