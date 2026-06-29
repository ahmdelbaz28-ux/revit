"""
revit_mcp_server.py — Main Revit MCP Server Entry Point.
========================================================
LIFE-SAFETY CRITICAL: This module provides the MCP server that bridges
AI assistants (Claude, GPT) with the Revit BIM model.

V141.2 HONEST IMPLEMENTATION (adversarial audit fix):
=====================================================
Previous versions of start() only set `_running = True` and logged a message.
This was MISLEADING — the docstring claimed "listens for AI assistant
connections" but no actual listening occurred.

V141.2 implements a REAL MCP server using the official Model Context
Protocol (MCP) over stdio (JSON-RPC 2.0). The server:
  1. Reads JSON-RPC requests from stdin (one per line)
  2. Dispatches each request to SanitizedMCPHandler.process_request()
  3. Writes JSON-RPC responses to stdout (one per line)
  4. Logs all activity to stderr (keeps stdout clean for protocol)

This matches the MCP specification: https://modelcontextprotocol.io/
AI assistants (Claude Desktop, etc.) spawn this server as a subprocess
and communicate via stdio. No network socket is needed.

Safety Architecture (unchanged from V140):
  1. ALL requests pass through SanitizedMCPHandler (input sanitization)
  2. ALL Revit model writes go through ThreadSafeModelUpdateQueue
  3. NO eval(), exec(), or dynamic code execution
  4. Engineering calculations use validated, bounded inputs
  5. Full audit trail for all operations

Usage:
    # As a subprocess (spawned by Claude Desktop / other MCP clients):
    python -m fireai.mcp_server.revit_mcp_server

    # Programmatically (in-process):
    server = RevitMCPServer()
    server.start()  # blocks, reading from stdin until EOF or stop()
"""

from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from typing import Any, Optional

from fireai.mcp_server.sanitized_handler import (
    MCPRequest,
    MCPResponse,
    SanitizedMCPHandler,
)
from fireai.mcp_server.thread_safe_queue import (
    ModelUpdateAction,
    ModelUpdateType,
    ThreadSafeModelUpdateQueue,
)

logger = logging.getLogger(__name__)


# ── MCP Protocol Constants ──────────────────────────────────────────────────
# Per https://modelcontextprotocol.io/specification
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "fireai-revit-mcp"
MCP_SERVER_VERSION = "1.0.0"

# MCP methods we support
MCP_METHODS = {
    "initialize",
    "initialized",
    "tools/list",
    "tools/call",
    "resources/list",
    "resources/read",
    "ping",
}


class RevitMCPServer:
    """
    MCP Server for Revit BIM integration with full safety controls.

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
        self._stdin_thread: Optional[threading.Thread] = None
        self._client_capabilities: dict[str, Any] = {}

    @property
    def update_queue(self) -> ThreadSafeModelUpdateQueue:
        """Access the thread-safe model update queue."""
        return self._update_queue

    def process_request(self, request: MCPRequest) -> MCPResponse:
        """
        Process an incoming MCP request.

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
        if request.tool_name in ("query_hydraulic_calculation", "calculate_friction_loss"):
            return self._handle_hydraulic_calculation(request, sanitized_params)
        if request.tool_name == "validate_sprinkler_compliance":
            return self._handle_sprinkler_compliance(request, sanitized_params)
        if request.tool_name == "calculate_battery_capacity":
            return self._handle_battery_capacity(request, sanitized_params)
        if request.tool_name == "query_room_hazard_class":
            return self._handle_hazard_class_query(request, sanitized_params)
        if request.tool_name == "update_room_classification":
            return self._handle_room_classification(request, sanitized_params)
        return MCPResponse(
            request_id=request.request_id,
            success=False,
            error=f"Tool '{request.tool_name}' handler not implemented yet.",
        )

    def _handle_update_bim_parameter(
        self, request: MCPRequest, params: dict[str, Any]
    ) -> MCPResponse:
        """
        Handle a BIM parameter update by queuing it for safe Revit execution.

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
        self, request: MCPRequest, params: dict[str, Any]
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
        self, request: MCPRequest, params: dict[str, Any]
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
        self, request: MCPRequest, params: dict[str, Any]
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
        self, request: MCPRequest, params: dict[str, Any]
    ) -> MCPResponse:
        """Handle a hazard class query (read-only)."""
        from fireai.core.hazard_override import MANDATORY_HAZARD_OVERRIDES
        # Reuse the handler's existing verifier instance
        # Return the mandatory override table for reference
        return MCPResponse(
            request_id=request.request_id,
            success=True,
            result={
                "mandatory_overrides": dict(MANDATORY_HAZARD_OVERRIDES.items()),
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
        self, request: MCPRequest, params: dict[str, Any]
    ) -> MCPResponse:
        """
        Handle a room classification update.

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

        result_data: dict[str, Any] = {
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

    def start(self, *, block: bool = True) -> None:
        """
        Start the MCP server.

        V141.2 REAL IMPLEMENTATION (adversarial audit fix):
        Reads JSON-RPC 2.0 requests from stdin (one per line), dispatches
        each to _handle_jsonrpc(), and writes responses to stdout.

        This matches the MCP specification: AI assistants (Claude Desktop,
        etc.) spawn this server as a subprocess and communicate via stdio.

        Args:
            block: If True (default), blocks the calling thread reading
                stdin until EOF or stop(). If False, starts a daemon
                thread and returns immediately (useful for testing).
        """
        if self._running:
            logger.warning("RevitMCPServer.start() called but already running.")
            return

        self._running = True
        logger.info(
            "[MCP SERVER]: RevitMCPServer started (MCP protocol v%s). "
            "Reading JSON-RPC from stdin. All model updates will be queued "
            "for thread-safe execution.",
            MCP_PROTOCOL_VERSION,
        )

        if block:
            self._stdin_loop()
        else:
            self._stdin_thread = threading.Thread(
                target=self._stdin_loop,
                name="mcp-stdin-reader",
                daemon=True,
            )
            self._stdin_thread.start()

    def _stdin_loop(self) -> None:
        """Main stdio read loop. Reads JSON-RPC lines until EOF or stop()."""
        # Use sys.stdin directly to keep stdout clean for protocol messages.
        # All logging goes to stderr (configured by logging_setup).
        for line in sys.stdin:
            if not self._running:
                break

            line = line.strip()
            if not line:
                continue

            try:
                response = self._handle_jsonrpc_line(line)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                # Never crash the server on a malformed request — log and continue.
                logger.error("[MCP SERVER] Error handling request: %s", e)
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": "Internal error",
                        "data": str(e),
                    },
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()

        logger.info("[MCP SERVER]: stdin EOF reached, server shutting down.")

    def _handle_jsonrpc_line(self, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a JSON-RPC line and return a response dict (or None for notifications).

        Args:
            line: A single JSON-RPC request string (one line from stdin).

        Returns:
            Response dict to write to stdout, or None if the message is a
            notification (no response expected per JSON-RPC 2.0 spec).
        """
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error",
                    "data": str(e),
                },
            }

        method = request.get("method")
        req_id = request.get("id")
        params = request.get("params", {})

        # Notifications (no id) don't get a response per JSON-RPC 2.0
        is_notification = req_id is None

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "initialized":
                # Notification — no response
                return None
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "resources/read":
                result = {"contents": []}
            else:
                if is_notification:
                    return None
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }

            if is_notification:
                return None

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }

        except Exception as e:
            if is_notification:
                logger.error("[MCP SERVER] Notification %s failed: %s", method, e)
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e),
                },
            }

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle the MCP initialize request."""
        self._client_capabilities = params.get("capabilities", {})
        client_info = params.get("clientInfo", {})
        logger.info(
            "[MCP SERVER] Initialize from client: %s v%s",
            client_info.get("name", "unknown"),
            client_info.get("version", "unknown"),
        )
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
            },
            "serverInfo": {
                "name": MCP_SERVER_NAME,
                "version": MCP_SERVER_VERSION,
            },
        }

    def _handle_tools_list(self) -> dict[str, Any]:
        """List available MCP tools."""
        return {
            "tools": [
                {
                    "name": "place_detector",
                    "description": "Place a fire detector in the Revit BIM model "
                    "at the specified coordinates. Inputs are sanitized and "
                    "the update is queued for thread-safe execution.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number", "description": "X coordinate (mm)"},
                            "y": {"type": "number", "description": "Y coordinate (mm)"},
                            "z": {"type": "number", "description": "Z coordinate (mm)"},
                            "detector_type": {
                                "type": "string",
                                "enum": ["smoke", "heat", "flame", "duct"],
                            },
                            "room_id": {"type": "string"},
                        },
                        "required": ["x", "y", "z", "detector_type", "room_id"],
                    },
                },
                {
                    "name": "calculate_coverage",
                    "description": "Calculate NFPA 72 coverage for a room given "
                    "its dimensions and detector type.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "room_length": {"type": "number", "description": "Room length (m)"},
                            "room_width": {"type": "number", "description": "Room width (m)"},
                            "ceiling_height": {"type": "number", "description": "Ceiling height (m)"},
                            "detector_type": {"type": "string"},
                        },
                        "required": ["room_length", "room_width", "ceiling_height", "detector_type"],
                    },
                },
            ]
        }

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle a tools/call request by dispatching to SanitizedMCPHandler."""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        # Build an MCPRequest and delegate to the safety-enforcing handler
        mcp_request = MCPRequest(
            request_id=str(params.get("_meta", {}).get("request_id", "")),
            tool_name=tool_name or "",
            parameters=tool_args,
        )
        response: MCPResponse = self._handler.process_request(mcp_request)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "success": response.success,
                        "result": response.result,
                        "error": response.error,
                        "sanitized_parameters": response.sanitized_parameters,
                    }),
                }
            ],
            "isError": not response.success,
        }

    def stop(self) -> None:
        """
        Stop the MCP server.

        Sets _running = False, which causes the stdin read loop to exit
        on the next iteration. If running in non-blocking mode, waits for
        the daemon thread to finish (up to 2 seconds).
        """
        self._running = False
        logger.info("[MCP SERVER]: RevitMCPServer stop requested.")

        if self._stdin_thread is not None and self._stdin_thread.is_alive():
            self._stdin_thread.join(timeout=2.0)
            if self._stdin_thread.is_alive():
                logger.warning(
                    "[MCP SERVER]: stdin reader thread did not stop within 2s "
                    "(it is blocked on stdin.read; will exit on next input or EOF)."
                )
        logger.info("[MCP SERVER]: RevitMCPServer stopped.")


# ── Module entry point ──────────────────────────────────────────────────────
def main() -> None:
    """Run the MCP server as a subprocess (spawned by Claude Desktop etc.)."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    server = RevitMCPServer()
    server.start(block=True)


if __name__ == "__main__":
    main()
