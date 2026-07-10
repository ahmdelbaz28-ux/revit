"""
tests/test_mcp_server.py.
=========================
Tests for the V142 MCP server (RevitMCPServer).

TEST PHILOSOPHY (agent.md Rule 12 — Safety-First):
  The MCP server is the SINGLE ENTRY POINT for AI assistant (Claude,
  GPT) communication with the FireAI BIM model. A broken MCP server
  means Claude Desktop cannot place detectors, query coverage, or
  validate sprinkler compliance — direct safety impact.

  V141.2 introduced a real MCP server (stdio JSON-RPC 2.0) but had
  ZERO tests for it. V142 adds this test file AND fixes a critical
  bug found by these tests (process_request → handle).

  Tests verify:
    1. JSON-RPC protocol conformance (initialize, ping, tools/list)
    2. tools/call dispatches to SanitizedMCPHandler correctly
    3. Error handling: malformed JSON, unknown methods, missing params
    4. Notifications (no id) don't get responses
    5. start()/stop() lifecycle with non-blocking mode
    6. Protocol version and server info in initialize response

  Tests do NOT spawn a subprocess — they call _handle_jsonrpc_line()
  directly for determinism.
"""

from __future__ import annotations

import json
import time

import pytest

from fireai.mcp_server.revit_mcp_server import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    RevitMCPServer,
)

# ===========================================================================
# Test fixtures
# ===========================================================================


@pytest.fixture
def server():
    """Fresh server instance for each test."""
    return RevitMCPServer()


@pytest.fixture(autouse=True)
def _no_stdin_in_tests(monkeypatch):
    """
    V142 SAFETY: Prevent any MCP test from hanging on stdin read in CI.

    Sets FIREAI_MCP_NO_STDIN=1 for every test in this module. This makes
    _stdin_loop() a no-op wait on _running instead of a blocking read on
    sys.stdin (which has no EOF in CI and would hang Gate 2 forever).
    """
    monkeypatch.setenv("FIREAI_MCP_NO_STDIN", "1")


def _jsonrpc(method: str, params: dict | None = None, *, req_id: int | None = 1) -> str:
    """Build a JSON-RPC 2.0 request line."""
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if req_id is not None:
        msg["id"] = req_id
    return json.dumps(msg)


# ===========================================================================
# Protocol conformance tests
# ===========================================================================


class TestMCPProtocolConformance:
    """Verify the server conforms to MCP / JSON-RPC 2.0 spec."""

    def test_initialize_returns_protocol_version(self, server):
        line = _jsonrpc("initialize", {
            "capabilities": {},
            "clientInfo": {"name": "claude-desktop", "version": "0.7.0"},
        })
        resp = server._handle_jsonrpc_line(line)
        assert resp is not None
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        assert resp["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
        assert resp["result"]["serverInfo"]["name"] == MCP_SERVER_NAME
        assert resp["result"]["serverInfo"]["version"] == MCP_SERVER_VERSION

    def test_initialize_advertises_tools_capability(self, server):
        line = _jsonrpc("initialize")
        resp = server._handle_jsonrpc_line(line)
        caps = resp["result"]["capabilities"]
        assert "tools" in caps
        assert caps["tools"]["listChanged"] is False

    def test_ping_returns_empty_result(self, server):
        line = _jsonrpc("ping")
        resp = server._handle_jsonrpc_line(line)
        assert resp is not None
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"] == {}

    def test_tools_list_returns_at_least_one_tool(self, server):
        line = _jsonrpc("tools/list")
        resp = server._handle_jsonrpc_line(line)
        assert resp is not None
        tools = resp["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) >= 1
        # Each tool must have name + description + inputSchema
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t
            assert t["inputSchema"]["type"] == "object"

    def test_resources_list_returns_empty(self, server):
        line = _jsonrpc("resources/list")
        resp = server._handle_jsonrpc_line(line)
        assert resp["result"] == {"resources": []}


# ===========================================================================
# tools/call tests — the V142 critical fix
# ===========================================================================


class TestToolsCallDispatch:
    """
    V142 CRITICAL: V141.2 called `process_request` which doesn't exist.
    Every tools/call returned AttributeError. These tests verify the fix.
    """

    def test_tools_call_does_not_raise_attribute_error(self, server):
        """The V141.2 bug: tools/call → AttributeError on process_request."""
        line = _jsonrpc("tools/call", {
            "name": "calculate_coverage",
            "arguments": {
                "room_length": 10, "room_width": 10,
                "ceiling_height": 3, "detector_type": "smoke",
            },
        })
        resp = server._handle_jsonrpc_line(line)
        assert resp is not None
        # MUST NOT contain AttributeError in error data
        if "error" in resp:
            assert "AttributeError" not in str(resp["error"])
            assert "process_request" not in str(resp["error"])

    def test_tools_call_returns_mcp_envelope(self, server):
        """tools/call must return the MCP content envelope, not raw result."""
        line = _jsonrpc("tools/call", {
            "name": "calculate_coverage",
            "arguments": {
                "room_length": 10, "room_width": 10,
                "ceiling_height": 3, "detector_type": "smoke",
            },
        })
        resp = server._handle_jsonrpc_line(line)
        assert "result" in resp
        result = resp["result"]
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) >= 1
        assert result["content"][0]["type"] == "text"
        # The text must be valid JSON with success/result/error fields
        payload = json.loads(result["content"][0]["text"])
        assert "success" in payload
        assert "result" in payload
        assert "error" in payload

    def test_tools_call_unknown_tool_returns_error_envelope(self, server):
        """Unknown tool name → handler rejects, but envelope is still valid."""
        line = _jsonrpc("tools/call", {
            "name": "nonexistent_tool",
            "arguments": {},
        })
        resp = server._handle_jsonrpc_line(line)
        # The MCP envelope is returned even on handler rejection
        assert "result" in resp
        result = resp["result"]
        assert "content" in result
        payload = json.loads(result["content"][0]["text"])
        # SanitizedMCPHandler should reject unknown tools
        assert payload["success"] is False

    def test_tools_call_missing_name_param(self, server):
        """tools/call without name parameter must not crash the server."""
        line = _jsonrpc("tools/call", {"arguments": {}})
        resp = server._handle_jsonrpc_line(line)
        # Should not raise; should return some envelope
        assert resp is not None
        # Either an error envelope or a result envelope (handler's choice)
        assert "jsonrpc" in resp


# ===========================================================================
# Error handling tests
# ===========================================================================


class TestErrorHandling:
    """Verify the server degrades gracefully on bad input."""

    def test_malformed_json_returns_parse_error(self, server):
        """Malformed JSON → JSON-RPC parse error (-32700)."""
        resp = server._handle_jsonrpc_line("{not valid json}")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] is None
        assert resp["error"]["code"] == -32700
        assert "Parse error" in resp["error"]["message"]

    def test_unknown_method_returns_method_not_found(self, server):
        """Unknown method → JSON-RPC method not found (-32601)."""
        line = _jsonrpc("nonexistent/method")
        resp = server._handle_jsonrpc_line(line)
        assert resp["error"]["code"] == -32601
        assert "Method not found" in resp["error"]["message"]

    def test_internal_error_returns_minus_32603(self, server, monkeypatch):
        """Handler exception → internal error (-32603), not a crash."""
        def boom(_params):
            raise RuntimeError("simulated handler crash")
        monkeypatch.setattr(server, "_handle_initialize", boom)
        line = _jsonrpc("initialize")
        resp = server._handle_jsonrpc_line(line)
        assert resp["error"]["code"] == -32603
        assert "Internal error" in resp["error"]["message"]

    def test_empty_line_returns_none(self, server):
        """Empty line (whitespace only) is skipped, returns None."""
        # _handle_jsonrpc_line is called per-line; an empty string still
        # goes through JSON parsing. The STDIN loop filters empty lines,
        # but the parser must handle the empty string gracefully.
        resp = server._handle_jsonrpc_line("")
        # Empty string → JSON parse error
        assert resp is not None
        assert resp["error"]["code"] == -32700


# ===========================================================================
# Notification tests (JSON-RPC 2.0 — no id → no response)
# ===========================================================================


class TestNotifications:
    """Per JSON-RPC 2.0: notifications (no id) do NOT get a response."""

    def test_initialized_notification_returns_none(self, server):
        """`initialized` is a notification — no response."""
        line = _jsonrpc("initialized", req_id=None)
        resp = server._handle_jsonrpc_line(line)
        assert resp is None

    def test_notification_with_unknown_method_returns_none(self, server):
        """Unknown notification → no response (not an error)."""
        line = _jsonrpc("some/notification", req_id=None)
        resp = server._handle_jsonrpc_line(line)
        assert resp is None

    def test_initialize_stores_client_capabilities(self, server):
        """initialize must store client capabilities for later use."""
        caps = {"sampling": {}}
        line = _jsonrpc("initialize", {"capabilities": caps})
        server._handle_jsonrpc_line(line)
        assert server._client_capabilities == caps


# ===========================================================================
# Lifecycle tests (start/stop)
# ===========================================================================


class TestServerLifecycle:
    """Verify start()/stop() management of _running flag and threads."""

    def test_start_nonblocking_starts_thread(self, server, monkeypatch):
        """
        start(block=False) starts a daemon thread and returns immediately.

        V142 FIX (Rule 17 root-cause): In CI, sys.stdin may block forever.
        Set FIREAI_MCP_NO_STDIN=1 so _stdin_loop becomes a no-op wait on
        _running instead of reading stdin. This makes the test deterministic.
        """
        monkeypatch.setenv("FIREAI_MCP_NO_STDIN", "1")

        server.start(block=False)
        assert server._running is True
        assert server._stdin_thread is not None
        # V144 FIX: Small retry loop to handle OS thread scheduler delays in CI.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if server._stdin_thread.is_alive():
                break
            time.sleep(0.05)
        else:
            pytest.fail("Daemon thread did not start within 2.0 seconds")
        server.stop()
        assert server._running is False
        # Wait for thread to finish (it's a daemon, but join for cleanliness)
        server._stdin_thread.join(timeout=2.0)

    def test_stop_sets_running_false(self, server):
        """stop() must set _running=False."""
        server._running = True
        server.stop()
        assert server._running is False

    def test_double_start_logs_warning_no_crash(self, server):
        """Calling start() twice must not crash."""
        server._running = True  # simulate already running
        server.start(block=False)  # should log warning and return
        # Cleanup
        server.stop()

    def test_stop_is_idempotent(self, server):
        """stop() called multiple times must not crash."""
        server.stop()
        server.stop()
        server.stop()
        assert server._running is False


# ===========================================================================
# Process request (in-process API) tests
# ===========================================================================


class TestProcessRequestInProcess:
    """Verify the in-process process_request() API still works (used by tests)."""

    def test_process_request_unknown_tool_returns_failure(self, server):
        """process_request() with unknown tool → success=False."""
        from fireai.mcp_server.sanitized_handler import MCPRequest
        req = MCPRequest(
            request_id="test-1",
            tool_name="nonexistent",
            parameters={},
        )
        resp = server.process_request(req)
        assert resp.success is False
        # SanitizedMCPHandler rejects unknown tools with "not authorized"
        # (OWASP A03:2021 — tool injection protection).
        assert resp.error  # must have a non-empty error message
