"""
test_sanitized_handler.py — Tests for fireai/mcp_server/sanitized_handler.py.

Verifies input sanitization, tool whitelisting, parameter validation,
and code injection detection.
"""
from __future__ import annotations

from fireai.mcp_server.sanitized_handler import (
    MCPRequest,
    SanitizedMCPHandler,
)

ALLOWED_TOOLS = SanitizedMCPHandler.ALLOWED_TOOLS


class TestSanitizedMCPHandler:
    """High-level handler tests."""

    def setup_method(self):
        self.handler = SanitizedMCPHandler()

    def test_unknown_tool_rejected(self):
        req = MCPRequest(tool_name="evil_tool", parameters={})
        resp = self.handler.handle(req)
        assert resp.success is False
        assert "not authorized" in resp.error

    def test_allowed_tool_accepted(self):
        req = MCPRequest(tool_name="export_report", parameters={})
        resp = self.handler.handle(req)
        assert resp.success is True

    def test_known_tool_wrong_params_rejected(self):
        req = MCPRequest(
            tool_name="update_bim_parameter",
            parameters={},
        )
        resp = self.handler.handle(req)
        assert resp.success is False

    def test_code_injection_in_string_rejected(self):
        req = MCPRequest(
            tool_name="update_bim_parameter",
            parameters={
                "element_id": "123",
                "parameter_name": "Diameter",
                "parameter_value": "; import os; os.system('rm -rf /')",
            },
        )
        resp = self.handler.handle(req)
        assert resp.success is False
        assert "injection" in resp.error.lower() or "Forbidden" in resp.error

    def test_eval_in_parameter_rejected(self):
        req = MCPRequest(
            tool_name="update_bim_parameter",
            parameters={
                "element_id": "123",
                "parameter_name": "eval('malicious')",
                "parameter_value": "2.0",
            },
        )
        resp = self.handler.handle(req)
        assert resp.success is False

    def test_subprocess_in_parameter_rejected(self):
        req = MCPRequest(
            tool_name="update_bim_parameter",
            parameters={
                "element_id": "123",
                "parameter_name": "subprocess.call(['rm','-rf','/'])",
                "parameter_value": "2.0",
            },
        )
        resp = self.handler.handle(req)
        assert resp.success is False

    def test_valid_update_bim_parameter(self):
        req = MCPRequest(
            tool_name="update_bim_parameter",
            parameters={
                "element_id": "12345",
                "parameter_name": "Diameter",
                "parameter_value": "2.067",
            },
        )
        resp = self.handler.handle(req)
        assert resp.success is True
        assert resp.result["element_id"] == "12345"
        assert resp.result["parameter_name"] == "Diameter"
        assert resp.result["parameter_value"] == "2.067"

    def test_request_log_updated(self):
        req = MCPRequest(tool_name="export_report", parameters={})
        self.handler.handle(req)
        log = self.handler.get_request_log(last_n=1)
        assert len(log) == 1
        assert log[0]["tool_name"] == "export_report"


class TestAllowedTools:
    """The whitelist of allowed tools."""

    def test_allowed_tools_contains_expected(self):
        expected = {
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
        assert expected == ALLOWED_TOOLS
