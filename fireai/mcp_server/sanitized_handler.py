"""sanitized_handler.py — Input-Sanitized MCP Request Handler
===========================================================
LIFE-SAFETY CRITICAL: This module is the GATEKEEPER between external
MCP clients (AI assistants) and the FireAI system. Every request from
an external source MUST pass through this handler, which enforces:

  1. Whitelist-based input sanitization (no eval/exec/subprocess)
  2. Type validation for all engineering parameters
  3. Range validation for all numeric values (NFPA 13, NFPA 72 limits)
  4. Injection attack detection and rejection
  5. Audit trail for all requests (for liability and forensic analysis)

This module directly addresses Forensic Audit Finding 4 (Catastrophic):
RCE via Unsanitized MCP Tool Input.

OWASP Top 10 Reference:
  - A03:2021-Injection: Input injection is #3 most critical web risk
  - In fire protection: injection can alter sprinkler pipe sizes,
    delete audit trails, or steal building design data

Design Principle (from agent.md Rule 12):
  "Safety is the absolute priority. Wrong code in this system is
   catastrophic — it threatens human life."
"""

from __future__ import annotations

import logging
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Import the existing sanitization module
from fireai.core.bim_input_sanitizer import (
    sanitize_bim_parameter,
    sanitize_file_path,
    sanitize_room_name,
)
from fireai.core.hazard_override import (
    HazardOverrideVerifier,
)

# Import engineering validation modules
from fireai.core.hydraulic_solver import (
    MAX_C_FACTOR,
    MIN_C_FACTOR,
    MIN_PIPE_DIAMETER_INCHES,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# FORBIDDEN PATTERNS — Absolute Ban
# ═══════════════════════════════════════════════════════════════════════════════

# These code patterns are FORBIDDEN in any MCP request payload.
# If any of these patterns appear in a request, the request is REJECTED
# and logged as a potential security attack.

_FORBIDDEN_CODE_PATTERNS = [
    re.compile(r'\beval\s*\(', re.IGNORECASE),
    re.compile(r'\bexec\s*\(', re.IGNORECASE),
    re.compile(r'\bsubprocess\b', re.IGNORECASE),
    re.compile(r'\bos\.system\b', re.IGNORECASE),
    re.compile(r'\bos\.popen\b', re.IGNORECASE),
    re.compile(r'\b__import__\s*\(', re.IGNORECASE),
    re.compile(r'\bgetattr\s*\(', re.IGNORECASE),
    re.compile(r'\bsetattr\s*\(', re.IGNORECASE),
    re.compile(r'\bglobals\s*\(', re.IGNORECASE),
    re.compile(r'\blocals\s*\(', re.IGNORECASE),
    re.compile(r'\bcompile\s*\(', re.IGNORECASE),
    re.compile(r'\bopen\s*\(', re.IGNORECASE),
    re.compile(r'\bwrite\s*\(', re.IGNORECASE),
    # Additional dangerous Python builtins
    re.compile(r'\bpickle\b', re.IGNORECASE),
    re.compile(r'\bmarshal\b', re.IGNORECASE),
    re.compile(r'\bshutil\b', re.IGNORECASE),
    re.compile(r'\bctypes\b', re.IGNORECASE),
    re.compile(r'\bsocket\b', re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MCPRequest:
    """An incoming request from an MCP client (AI assistant).

    Attributes:
        request_id: Unique identifier for audit trail.
        tool_name: Name of the MCP tool being invoked.
        parameters: Dictionary of tool parameters (raw, unsanitized).
        source: Origin of the request (e.g., "claude_desktop", "api").
        timestamp: When the request was received.

    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)


@dataclass
class MCPResponse:
    """Response to an MCP request.

    Attributes:
        request_id: Matches the MCPRequest.request_id.
        success: Whether the request was processed successfully.
        result: The result data (if successful).
        error: Error message (if failed).
        violations: List of validation/sanitization violations found.
        sanitized_parameters: The parameters after sanitization (for audit).

    """

    request_id: str = ""
    success: bool = False
    result: Any = None
    error: str = ""
    violations: List[str] = field(default_factory=list)
    sanitized_parameters: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# SANITIZED MCP HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

class SanitizedMCPHandler:
    """Input-sanitized handler for MCP tool requests.

    SAFETY: This handler is the ONLY approved entry point for MCP
    requests. It enforces:
      1. Code injection detection and rejection
      2. Parameter sanitization via bim_input_sanitizer
      3. Engineering range validation (NFPA 13, NFPA 72 limits)
      4. Hazard classification override verification
      5. Unit conversion safety checks

    Design Principle: "Never trust input from outside the system boundary."

    Usage:
        handler = SanitizedMCPHandler()
        request = MCPRequest(
            tool_name="update_bim_parameter",
            parameters={"element_id": "12345", "param": "Diameter", "value": "2.067"},
            source="claude_desktop",
        )
        response = handler.handle(request)
    """

    # Allowed MCP tool names (whitelist — unknown tools are REJECTED)
    ALLOWED_TOOLS = {
        "update_bim_parameter",
        "query_hydraulic_calculation",
        "validate_sprinkler_compliance",
        "calculate_friction_loss",
        "calculate_battery_capacity",
        "query_room_hazard_class",
        "update_room_classification",
        "get_project_status",
        "export_report",
    }

    # Parameter validation rules per tool
    PARAM_RULES: Dict[str, Dict[str, Dict[str, Any]]] = {
        "update_bim_parameter": {
            "element_id": {"type": "str", "sanitize": "bim_parameter", "required": True},
            "parameter_name": {"type": "str", "sanitize": "bim_parameter", "required": True},
            # parameter_value: must be float or sanitized string;
            # 'any' type is validated by Gate 2 injection check
            "parameter_value": {"type": "any", "required": True},
        },
        "query_hydraulic_calculation": {
            "flow_rate_gpm": {"type": "float", "min": 0.0, "max": 50000.0, "required": True},
            "friction_factor_c": {"type": "float", "min": MIN_C_FACTOR, "max": MAX_C_FACTOR, "required": True},
            "internal_diameter_inches": {"type": "float", "min": MIN_PIPE_DIAMETER_INCHES, "max": 36.0, "required": True},
            "pipe_length_feet": {"type": "float", "min": 0.0, "max": 5000.0, "required": True},
        },
        # calculate_friction_loss uses same params as query_hydraulic_calculation
        "calculate_friction_loss": {
            "flow_rate_gpm": {"type": "float", "min": 0.0, "max": 50000.0, "required": True},
            "friction_factor_c": {"type": "float", "min": MIN_C_FACTOR, "max": MAX_C_FACTOR, "required": True},
            "internal_diameter_inches": {"type": "float", "min": MIN_PIPE_DIAMETER_INCHES, "max": 36.0, "required": True},
            "pipe_length_feet": {"type": "float", "min": 0.0, "max": 5000.0, "required": True},
        },
        "validate_sprinkler_compliance": {
            "head_pressure_psi": {"type": "float", "min": 0.0, "max": 500.0, "required": True},
            "density_gpm_sqft": {"type": "float", "min": 0.0, "max": 1.0, "required": True},
            "hazard_class": {"type": "str", "sanitize": "bim_parameter", "required": True},
        },
        "calculate_battery_capacity": {
            "standby_current_ma": {"type": "float", "min": 0.0, "max": 10000.0, "required": True},
            "alarm_current_ma": {"type": "float", "min": 0.0, "max": 50000.0, "required": True},
            "standby_hours": {"type": "float", "min": 24.0, "max": 72.0, "required": False},
            "alarm_minutes": {"type": "float", "min": 5.0, "max": 30.0, "required": False},
        },
        "update_room_classification": {
            "room_name": {"type": "str", "sanitize": "room_name", "required": True},
            "hazard_class": {"type": "str", "sanitize": "bim_parameter", "required": True},
            "element_id": {"type": "str", "sanitize": "bim_parameter", "required": True},
        },
    }

    def __init__(self) -> None:
        self._hazard_verifier = HazardOverrideVerifier()
        self._request_log: List[Dict[str, Any]] = []

    def handle(self, request: MCPRequest) -> MCPResponse:
        """Process an MCP request with full input sanitization.

        SAFETY: This method enforces ALL safety gates before any
        processing occurs. A request that fails ANY gate is REJECTED.

        Gates:
          1. Tool name whitelist check
          2. Code injection detection
          3. Parameter sanitization
          4. Engineering range validation
          5. Hazard override verification (if applicable)

        Args:
            request: The incoming MCP request.

        Returns:
            MCPResponse with success/failure and audit information.

        """
        violations: List[str] = []

        # Gate 1: Tool name whitelist
        if request.tool_name not in self.ALLOWED_TOOLS:
            violations.append(
                f"Unknown tool: '{request.tool_name}'. "
                f"Allowed tools: {sorted(self.ALLOWED_TOOLS)}. "
                "[OWASP A03:2021 — tool injection attempt?]"
            )
            logger.critical(
                f"[MCP SECURITY]: Unknown tool name rejected: '{request.tool_name}' "
                f"from source={request.source} request_id={request.request_id}"
            )
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Tool '{request.tool_name}' is not authorized.",
                violations=violations,
            )

        # Gate 2: Code injection detection in ALL parameter values
        for key, value in request.parameters.items():
            if isinstance(value, str):
                for pattern in _FORBIDDEN_CODE_PATTERNS:
                    if pattern.search(value):
                        violations.append(
                            f"Forbidden code pattern in parameter '{key}': "
                            f"matches {pattern.pattern}. "
                            "[OWASP A03:2021 — code injection attempt?]"
                        )
                        logger.critical(
                            f"[MCP SECURITY]: Code injection attempt in parameter '{key}'. "
                            f"Pattern: {pattern.pattern}. Value: '{value[:100]}'. "
                            f"Source: {request.source}. Request: {request.request_id}"
                        )

        if violations:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error="Potential code injection detected. Request REJECTED.",
                violations=violations,
            )

        # Gate 3: Parameter sanitization
        sanitized_params: Dict[str, Any] = {}
        rules = self.PARAM_RULES.get(request.tool_name, {})

        for param_name, rule in rules.items():
            raw_value = request.parameters.get(param_name)

            # Check required
            if rule.get("required") and raw_value is None:
                violations.append(
                    f"Required parameter '{param_name}' is missing."
                )
                continue

            if raw_value is None:
                continue

            # Sanitize strings
            if rule.get("type") == "str" and isinstance(raw_value, str):
                sanitize_method = rule.get("sanitize", "bim_parameter")
                try:
                    if sanitize_method == "bim_parameter":
                        sanitized_params[param_name] = sanitize_bim_parameter(raw_value)
                    elif sanitize_method == "room_name":
                        sanitized_params[param_name] = sanitize_room_name(raw_value)
                    elif sanitize_method == "file_path":
                        sanitized_params[param_name] = sanitize_file_path(raw_value)
                    else:
                        sanitized_params[param_name] = sanitize_bim_parameter(raw_value)
                except ValueError as e:
                    violations.append(
                        f"Sanitization rejected parameter '{param_name}': {e}"
                    )
                    continue

            # Validate numerics
            elif rule.get("type") == "float" and isinstance(raw_value, (int, float)):
                num_val = float(raw_value)
                if not math.isfinite(num_val):
                    violations.append(
                        f"Parameter '{param_name}' is not finite: {num_val}"
                    )
                    continue
                min_val = rule.get("min")
                max_val = rule.get("max")
                if min_val is not None and num_val < min_val:
                    violations.append(
                        f"Parameter '{param_name}'={num_val} is below "
                        f"minimum {min_val}. [NFPA 13 / NFPA 72 boundary]"
                    )
                    continue
                if max_val is not None and num_val > max_val:
                    violations.append(
                        f"Parameter '{param_name}'={num_val} exceeds "
                        f"maximum {max_val}. [Engineering limit]"
                    )
                    continue
                sanitized_params[param_name] = num_val

            # Pass through other types with safety checks
            else:
                # For 'any' type, still validate strings for injection
                if isinstance(raw_value, str):
                    try:
                        sanitized_params[param_name] = sanitize_bim_parameter(raw_value)
                    except ValueError as e:
                        violations.append(
                            f"Sanitization rejected parameter '{param_name}': {e}"
                        )
                        continue
                elif isinstance(raw_value, (int, float)):
                    if not math.isfinite(float(raw_value)):
                        violations.append(
                            f"Parameter '{param_name}' is not finite: {raw_value}"
                        )
                        continue
                    sanitized_params[param_name] = raw_value
                else:
                    sanitized_params[param_name] = raw_value

        if violations:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error="Parameter validation failed. Request REJECTED.",
                violations=violations,
                sanitized_parameters=sanitized_params,
            )

        # Gate 4: Hazard override verification (for classification updates)
        if request.tool_name == "update_room_classification":
            room_name = sanitized_params.get("room_name", "")
            hazard_class = sanitized_params.get("hazard_class", "")
            override_result = self._hazard_verifier.verify_and_override(
                room_name=room_name,
                ml_predicted_hazard=hazard_class,
            )
            # If override was applied, update the sanitized parameter
            if override_result.override_applied:
                sanitized_params["hazard_class"] = override_result.final_classification
                sanitized_params["_override_applied"] = True
                sanitized_params["_override_rationale"] = override_result.safety_rationale
                logger.warning(
                    f"[MCP SAFETY]: Hazard override applied for room '{room_name}'. "
                    f"AI predicted '{hazard_class}' → overridden to "
                    f"'{override_result.final_classification}'. "
                    f"Reason: {override_result.safety_rationale}"
                )

        # Log successful request
        self._request_log.append({
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "source": request.source,
            "timestamp": request.timestamp,
            "param_count": len(sanitized_params),
            "violations": len(violations),
        })

        return MCPResponse(
            request_id=request.request_id,
            success=True,
            result=sanitized_params,
            sanitized_parameters=sanitized_params,
        )

    def get_request_log(self, last_n: int = 100) -> List[Dict[str, Any]]:
        """Return the last N request log entries."""
        return list(self._request_log[-last_n:])
