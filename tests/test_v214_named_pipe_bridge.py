"""
test_v214_named_pipe_bridge.py — V214 regression tests for the C# Revit
add-in project files + Python named pipe client.

Verifies that:
  1. .csproj file exists with correct RevitAPI references
  2. .sln file exists
  3. .addin registration file exists
  4. NamedPipeServer.cs exists with the pipe name
  5. FireAIApplication.cs exists with IExternalApplication
  6. Python named_pipe_client.py exists and has correct API
  7. The pipe name matches between C# and Python
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADDIN_DIR = REPO_ROOT / "templates" / "revit_addin"


class TestV214RevitAddinProject:
    """V214: C# Revit add-in must have a buildable project (.csproj + .sln)."""

    def test_csproj_exists(self):
        """FireAIRevitAddin.csproj must exist."""
        csproj = ADDIN_DIR / "FireAIRevitAddin.csproj"
        assert csproj.exists(), f"Missing: {csproj}"

    def test_csproj_has_revit_api_references(self):
        """The .csproj must reference RevitAPI.dll + RevitAPIUI.dll."""
        csproj = ADDIN_DIR / "FireAIRevitAddin.csproj"
        content = csproj.read_text(encoding="utf-8")
        assert "RevitAPI" in content, "Must reference RevitAPI.dll"
        assert "RevitAPIUI" in content, "Must reference RevitAPIUI.dll"
        assert "HintPath" in content, "Must have HintPath for Revit DLLs"

    def test_csproj_targets_net6_windows(self):
        """The .csproj must target net6.0-windows (Revit 2024 requires .NET 6)."""
        csproj = ADDIN_DIR / "FireAIRevitAddin.csproj"
        content = csproj.read_text(encoding="utf-8")
        assert "net6.0-windows" in content, "Must target net6.0-windows"

    def test_sln_exists(self):
        """FireAIRevitAddin.sln must exist."""
        sln = ADDIN_DIR / "FireAIRevitAddin.sln"
        assert sln.exists(), f"Missing: {sln}"

    def test_addin_registration_file_exists(self):
        """FireAIRevitAddin.addin must exist for Revit registration."""
        addin = ADDIN_DIR / "FireAIRevitAddin.addin"
        assert addin.exists(), f"Missing: {addin}"
        content = addin.read_text(encoding="utf-8")
        assert "FireAIApplication" in content, "Must reference FireAIApplication class"
        assert "IExternalApplication" not in content  # .addin uses Type="Application"

    def test_named_pipe_server_cs_exists(self):
        """NamedPipeServer.cs must exist with the correct pipe name."""
        pipe_server = ADDIN_DIR / "NamedPipeServer.cs"
        assert pipe_server.exists(), f"Missing: {pipe_server}"
        content = pipe_server.read_text(encoding="utf-8")
        assert "FireAIRevitPipe" in content, "Must use the FireAIRevitPipe name"
        assert "NamedPipeServerStream" in content, "Must use NamedPipeServerStream"
        assert "IExternalEventHandler" not in content  # separate file

    def test_fireai_application_cs_exists(self):
        """FireAIApplication.cs must implement IExternalApplication."""
        app = ADDIN_DIR / "FireAIApplication.cs"
        assert app.exists(), f"Missing: {app}"
        content = app.read_text(encoding="utf-8")
        assert "IExternalApplication" in content, "Must implement IExternalApplication"
        assert "OnStartup" in content, "Must have OnStartup method"
        assert "OnShutdown" in content, "Must have OnShutdown method"
        assert "NamedPipeServer" in content, "Must create NamedPipeServer on startup"
        assert "ExternalEvent.Create" in content, "Must create ExternalEvent"

    def test_thread_safe_queue_handler_cs_unchanged(self):
        """ThreadSafeQueueHandler.cs must still exist (V213)."""
        handler = ADDIN_DIR / "ThreadSafeQueueHandler.cs"
        assert handler.exists(), f"Missing: {handler}"


class TestV214PythonNamedPipeClient:
    """V214: Python named_pipe_client.py must exist with correct API."""

    def test_module_exists(self):
        """named_pipe_client.py must exist in fireai/mcp_server/."""
        module = REPO_ROOT / "fireai" / "mcp_server" / "named_pipe_client.py"
        assert module.exists(), f"Missing: {module}"

    def test_pipe_name_matches_cs(self):
        """The Python pipe name must match the C# pipe name."""
        py_module = REPO_ROOT / "fireai" / "mcp_server" / "named_pipe_client.py"
        cs_file = ADDIN_DIR / "NamedPipeServer.cs"
        py_content = py_module.read_text(encoding="utf-8")
        cs_content = cs_file.read_text(encoding="utf-8")

        # Both must contain "FireAIRevitPipe"
        assert "FireAIRevitPipe" in py_content, "Python must reference FireAIRevitPipe"
        assert "FireAIRevitPipe" in cs_content, "C# must reference FireAIRevitPipe"

    def test_client_class_exists(self):
        """RevitNamedPipeClient class must exist."""
        from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient
        # import is always True (identity check tautology). Verify the symbol
        # is actually a class with the expected interface instead.
        assert isinstance(RevitNamedPipeClient, type)
        assert hasattr(RevitNamedPipeClient, "__init__")
        assert hasattr(RevitNamedPipeClient, "is_available")

    def test_client_is_available_returns_false_on_non_windows(self):
        """On non-Windows, is_available() must return False (not crash)."""
        from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient
        client = RevitNamedPipeClient()
        # On Linux CI, this must return False
        import platform
        if platform.system() != "Windows":
            assert client.is_available() is False

    def test_client_send_command_returns_error_on_non_windows(self):
        """On non-Windows, send_command must return status=error (not crash)."""
        from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient
        client = RevitNamedPipeClient()
        import platform
        if platform.system() != "Windows":
            result = client.send_command({"action": "set_parameter", "element_id": "1", "parameter_name": "X", "value": 1.0})
            assert result["status"] == "error"
            assert "not available" in result["message"].lower() or "named pipes" in result["message"].lower()

    def test_convenience_methods_exist(self):
        """The client must have convenience methods for common actions."""
        from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient
        client = RevitNamedPipeClient()
        assert hasattr(client, "send_set_parameter")
        assert hasattr(client, "send_set_string_parameter")
        assert hasattr(client, "send_create_wall")
        assert hasattr(client, "get_stats")

    def test_get_stats_returns_pipe_info(self):
        """get_stats() must return pipe_name + platform info."""
        from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient
        client = RevitNamedPipeClient()
        stats = client.get_stats()
        assert "pipe_name" in stats
        assert "FireAIRevitPipe" in stats["pipe_name"]
        assert "platform" in stats
        assert "is_windows" in stats
