"""
revit_mcp_server.py — Main Revit MCP Server Entry Point
========================================================
LIFE-SAFETY CRITICAL: This module provides the MCP server that bridges
AI assistants (Claude, GPT) with the Revit BIM model.

Safety Architecture:
  1. ALL requests pass through SanitizedMCPHandler (input sanitization)
  2. ALL Revit model writes go through ThreadSafeModelUpdateQueue
  3. NO eval(), exec(), or dynamic code execution
  4. Engineering calculations use validated, bounded inputs
  5. Full audit trail for all operations

This module addresses:
  - Finding 1: Unsafe Multithreading on Revit API (Catastrophic)
  - Finding 4: RCE via Unsanitized MCP Tool Input (Catastrophic)

Usage:
    server = RevitMCPServer()
    # Start the MCP server (listens for AI assistant connections)
    server.start()
"""

from __future__ import annotations

import logging
import queue
import uuid
from typing import Any, Dict, Optional

from fireai.mcp_server.thread_safe_queue import (
    ThreadSafeModelUpdateQueue,
    ModelUpdateAction,
    ModelUpdateType,
    ModelUpdateResult,
    ModelUpdateStatus,
)
from fireai.mcp_server.sanitized_handler import (
    SanitizedMCPHandler,
    MCPRequest,
    MCPResponse,
)

logger = logging.getLogger(__name__)


class RevitMCPServer:
    """MCP Server for Revit BIM integration with full safety controls.

    SAFETY: This server enforces the following non-negotiable rules:
      1. ALL inputs are sanitized before processing
      2. ALL Revit model writes are queued (never direct)
      3. NO dynamic code execution (eval/exec forbidden)
      4. ALL engineering calculations are validated
      5. ALL operations are logged for audit trail

    This class is the SINGLE ENTRY POINT for all MCP communication
    with the Revit BIM model.
    """

    def __init__(self) -> None:
        self._handler = SanitizedMCPHandler()
        self._update_queue = ThreadSafeModelUpdateQueue()
        self._running = False

    @property
    def update_queue(self) -> ThreadSafeModelUpdateQueue:
        """Access the thread-safe model update queue."""
        return self._update_queue

    def process_request(self, request: MCPRequest) -> MCPResponse:
        """Process an incoming MCP request.

        SAFETY GATE SEQUENCE:
          1. Sanitize all inputs (SanitizedMCPHandler)
          2. For model writes: enqueue in ThreadSafeModelUpdateQueue
          3. For queries: delegate to appropriate engine
          4. Return response with audit information

        Args:
            request: The incoming MCP request.

        Returns:
            MCPResponse with result or error.
        """
        # Step 1: Sanitize and validate inputs
        response = self._handler.handle(request)

        if not response.success:
            return response

        # Step 2: Route to appropriate handler
        sanitized_params = response.sanitized_parameters

        if request.tool_name == "update_bim_parameter":
            return self._handle_update_bim_parameter(request, sanitized_params)
        elif request.tool_name in ("query_hydraulic_calculation", "calculate_friction_loss"):
            return self._handle_hydraulic_calculation(request, sanitized_params)
        elif request.tool_name == "validate_sprinkler_compliance":
            return self._handle_sprinkler_compliance(request, sanitized_params)
        elif request.tool_name == "calculate_battery_capacity":
            return self._handle_battery_capacity(request, sanitized_params)
        elif request.tool_name == "query_room_hazard_class":
            return self._handle_hazard_class_query(request, sanitized_params)
        elif request.tool_name == "update_room_classification":
            return self._handle_room_classification(request, sanitized_params)
        else:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Tool '{request.tool_name}' handler not implemented yet.",
            )

    def _handle_update_bim_parameter(
        self, request: MCPRequest, params: Dict[str, Any]
    ) -> MCPResponse:
        """Handle a BIM parameter update by queuing it for safe Revit execution.

        SAFETY: This NEVER directly modifies the Revit model.
        Instead, it creates a ModelUpdateAction and enqueues it
        in the ThreadSafeModelUpdateQueue for execution on the
        Revit UI thread.
        """
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id=params.get("element_id", ""),
            parameter_name=params.get("parameter_name", ""),
            parameter_value=params.get("parameter_value"),
            source=request.source,
            nfpa_reference="MCP Update via SanitizedHandler",
        )

        try:
            action_id = self._update_queue.enqueue(action)
        except (ValueError, queue.Full) as e:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Failed to enqueue model update: {e}",
            )

        return MCPResponse(
            request_id=request.request_id,
            success=True,
            result={
                "action_id": action_id,
                "status": "queued",
                "message": (
                    "Model update queued for safe execution on Revit UI thread. "
                    "The update will be processed by the IExternalEventHandler. "
                    "Use action_id to check status."
                ),
            },
            sanitized_parameters=params,
        )

    def _handle_hydraulic_calculation(
        self, request: MCPRequest, params: Dict[str, Any]
    ) -> MCPResponse:
        """Handle a hydraulic calculation query (read-only)."""
        try:
            from fireai.core.hydraulic_solver import calculate_friction_loss
            result = calculate_friction_loss(
                flow_rate_gpm=params["flow_rate_gpm"],
                friction_factor_c=params["friction_factor_c"],
                internal_diameter_inches=params["internal_diameter_inches"],
                pipe_length_feet=params["pipe_length_feet"],
            )
            return MCPResponse(
                request_id=request.request_id,
                success=True,
                result={
                    "friction_loss_psi": round(result, 4),
                    "nfpa_reference": "NFPA 13-2022 Chapter 23",
                },
                sanitized_parameters=params,
            )
        except Exception as e:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Hydraulic calculation failed: {e}",
                sanitized_parameters=params,
            )

    def _handle_sprinkler_compliance(
        self, request: MCPRequest, params: Dict[str, Any]
    ) -> MCPResponse:
        """Handle a sprinkler compliance validation query (read-only)."""
        try:
            from fireai.core.hydraulic_solver import validate_sprinkler_compliance
            result = validate_sprinkler_compliance(
                head_pressure_psi=params["head_pressure_psi"],
                density_gpm_sqft=params["density_gpm_sqft"],
                hazard_class=params["hazard_class"],
            )
            return MCPResponse(
                request_id=request.request_id,
                success=True,
                result={
                    "is_compliant": result.is_compliant,
                    "violations": result.violations,
                    "nfpa_reference": result.nfpa_reference,
                },
                sanitized_parameters=params,
            )
        except Exception as e:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Compliance validation failed: {e}",
                sanitized_parameters=params,
            )

    def _handle_battery_capacity(
        self, request: MCPRequest, params: Dict[str, Any]
    ) -> MCPResponse:
        """Handle a battery capacity calculation query (read-only)."""
        try:
            from fireai.core.battery_aging_derating import size_battery
            standby_hours = params.get("standby_hours", 24.0)
            alarm_minutes = params.get("alarm_minutes", 5.0)
            result = size_battery(
                standby_load_amps=params["standby_current_ma"] / 1000.0,
                alarm_load_amps=params["alarm_current_ma"] / 1000.0,
                standby_hours=standby_hours,
                alarm_hours=alarm_minutes / 60.0,
            )
            return MCPResponse(
                request_id=request.request_id,
                success=True,
                result={
                    "required_ah": result.required_ah,
                    "total_load_ah": result.total_load_ah,
                    "temperature_derating": result.temperature_derating,
                    "aging_derating": result.aging_derating,
                    "discharge_rate_correction": result.discharge_rate_correction,
                    "violations": result.violations,
                    "nfpa_reference": result.nfpa_reference,
                    "minimum_safety_factor_note": (
                        "The combined derating (aging EOL 0.80 + temperature + "
                        "Peukert) provides a minimum safety margin >= 1.20x "
                        "as required by NFPA 72 §10.6.7.2.1"
                    ),
                },
                sanitized_parameters=params,
            )
        except Exception as e:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Battery calculation failed: {e}",
                sanitized_parameters=params,
            )

    def _handle_hazard_class_query(
        self, request: MCPRequest, params: Dict[str, Any]
    ) -> MCPResponse:
        """Handle a hazard class query (read-only)."""
        from fireai.core.hazard_override import MANDATORY_HAZARD_OVERRIDES
        # Reuse the handler's existing verifier instance
        verifier = self._handler._hazard_verifier
        # Return the mandatory override table for reference
        return MCPResponse(
            request_id=request.request_id,
            success=True,
            result={
                "mandatory_overrides": {
                    k: v for k, v in MANDATORY_HAZARD_OVERRIDES.items()
                },
                "available_classifications": [
                    "light_hazard",
                    "ordinary_hazard_1",
                    "ordinary_hazard_2",
                    "extra_hazard_1",
                    "extra_hazard_2",
                ],
            },
        )

    def _handle_room_classification(
        self, request: MCPRequest, params: Dict[str, Any]
    ) -> MCPResponse:
        """Handle a room classification update.

        SAFETY: The hazard override verifier is applied during
        sanitization (Gate 4 in SanitizedMCPHandler). If the AI
        predicted a lower classification than mandatory, it has
        already been overridden.
        """
        # The sanitized_params already contains the override result
        override_applied = params.get("_override_applied", False)
        override_rationale = params.get("_override_rationale", "")

        # Queue the classification update for safe Revit execution
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_HAZARD_CLASS,
            element_id=params.get("element_id", ""),
            parameter_name="Hazard Classification",
            parameter_value=params.get("hazard_class"),
            source=request.source,
            nfpa_reference="NFPA 13-2022 Chapter 11 / SBC 801 Ch.9",
        )

        try:
            action_id = self._update_queue.enqueue(action)
        except (ValueError, queue.Full) as e:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Failed to enqueue classification update: {e}",
            )

        result_data: Dict[str, Any] = {
            "action_id": action_id,
            "status": "queued",
            "hazard_class": params.get("hazard_class"),
            "override_applied": override_applied,
        }
        if override_applied:
            result_data["override_rationale"] = override_rationale

        return MCPResponse(
            request_id=request.request_id,
            success=True,
            result=result_data,
            sanitized_parameters=params,
        )

    def start(self) -> None:
        """Start the MCP server."""
        self._running = True
        logger.info(
            "[MCP SERVER]: RevitMCPServer started. "
            "All model updates will be queued for thread-safe execution."
        )

    def stop(self) -> None:
        """Stop the MCP server."""
        self._running = False
        logger.info("[MCP SERVER]: RevitMCPServer stopped.")
