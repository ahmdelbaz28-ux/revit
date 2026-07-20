"""
test_v214_autocad_named_pipe_bridge.py — V214 regression tests for the C# AutoCAD
add-in project files + Python AutoCAD named pipe client in local_agent.py.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADDIN_DIR = REPO_ROOT / "autocad_addin" / "BazSparkAutoCADBridge"


class TestV214AutoCADAddinProject:
    """Verifies C# AutoCAD add-in project files and references."""

    def test_csproj_exists(self):
        """BazSparkAutoCADBridge.csproj must exist."""
        csproj = ADDIN_DIR / "BazSparkAutoCADBridge.csproj"
        assert csproj.exists(), f"Missing: {csproj}"

    def test_csproj_has_autocad_nuget_references(self):
        """The .csproj must reference AutoCAD.NET NuGet package."""
        csproj = ADDIN_DIR / "BazSparkAutoCADBridge.csproj"
        content = csproj.read_text(encoding="utf-8")
        assert "AutoCAD.NET" in content, "Must reference AutoCAD.NET NuGet package"

    def test_csproj_targets_net48(self):
        """The .csproj must target net48 (Standard AutoCAD .NET runtime compatibility)."""
        csproj = ADDIN_DIR / "BazSparkAutoCADBridge.csproj"
        content = csproj.read_text(encoding="utf-8")
        assert "<TargetFramework>net48</TargetFramework>" in content, "Must target net48"

    def test_application_cs_exists(self):
        """Application.cs must implement IExtensionApplication."""
        app = ADDIN_DIR / "Application.cs"
        assert app.exists(), f"Missing: {app}"
        content = app.read_text(encoding="utf-8")
        assert "IExtensionApplication" in content, "Must implement IExtensionApplication"
        assert "Initialize" in content, "Must have Initialize method"
        WriteToCommandLine = "WriteToCommandLine"
        assert WriteToCommandLine in content

    def test_local_agent_server_cs_exists(self):
        """LocalAgentServer.cs must exist and contain correct pipe name."""
        server = ADDIN_DIR / "LocalAgentServer.cs"
        assert server.exists(), f"Missing: {server}"
        content = server.read_text(encoding="utf-8")
        assert "bazspark_autocad" in content, "Must reference pipe 'bazspark_autocad'"
        assert "NamedPipeServerStream" in content

    def test_command_handler_cs_exists(self):
        """AutoCADCommandHandler.cs must implement DispatchCommand."""
        handler = ADDIN_DIR / "AutoCADCommandHandler.cs"
        assert handler.exists(), f"Missing: {handler}"
        content = handler.read_text(encoding="utf-8")
        assert "DispatchCommand" in content
        assert "draw_polyline" in content
        assert "draw_circle" in content


class TestV214PythonAutoCADNamedPipeClient:
    """Verifies AutoCAD Named Pipe client configuration in local_agent.py."""

    def test_pipe_name_matches_cs(self):
        """The Python AutoCAD pipe name must match the C# pipe name."""
        agent_path = REPO_ROOT / "scripts" / "local_agent.py"
        agent_content = agent_path.read_text(encoding="utf-8")

        # Verify the pipe name is configured correctly
        assert "bazspark_autocad" in agent_content, "local_agent.py must reference bazspark_autocad"

    def test_dispatcher_class_instantiation(self):
        """AutoCADNamedPipeDispatcher can be instantiated and behaves correctly."""
        sys.path.insert(0, str(REPO_ROOT))
        from scripts.local_agent import AutoCADNamedPipeDispatcher

        dispatcher = AutoCADNamedPipeDispatcher()
        assert hasattr(dispatcher, "available")
        assert hasattr(dispatcher, "send")

        if platform.system() != "Windows":
            assert dispatcher.available is False
            # Check sending command fails gracefully on non-windows
            res = dispatcher.send("get_info", {})
            assert res["success"] is False
            assert "Add-in not running" in res["error"] or "win32" in res["error"]
