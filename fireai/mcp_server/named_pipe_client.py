r"""
named_pipe_client.py — Python side of the named pipe bridge to the C# Revit add-in.

V214 FIX: Previously the Python MCP server (revit_mcp_server.py) enqueued
model update actions in a local ThreadSafeModelUpdateQueue, but no C# add-in
consumed from it — so writes were silently dropped (V133 safety redesign
defeated). Now this client sends commands over a named pipe to the C#
FireAIRevitAddin which executes them on the Revit UI thread.

PIPE NAME: \\\\.\\pipe\\FireAIRevitPipe (matches C# NamedPipeServer.cs)

PROTOCOL:
  Request (newline-delimited JSON):
    {"action": "set_parameter", "element_id": "12345",
     "parameter_name": "Diameter", "value": 25.0,
     "nfpa_reference": "NFPA 72 §17.7.3.2.3"}

  Response (newline-delimited JSON):
    {"status": "queued", "pending_count": 3, "total_received": 42, "total_queued": 40}
    OR
    {"status": "error", "message": "Invalid action type"}

USAGE:
  from fireai.mcp_server.named_pipe_client import RevitNamedPipeClient

  client = RevitNamedPipeClient()
  if client.is_available():
      response = client.send_command({
          "action": "set_parameter",
          "element_id": "12345",
          "parameter_name": "Diameter",
          "value": 25.0,
          "nfpa_reference": "NFPA 72 §17.7.3.2.3",
      })
      if response.get("status") == "queued":
          print(f"Action queued (pending: {response.get('pending_count')})")
      else:
          print(f"Error: {response.get('message')}")
  else:
      print("C# add-in not running — start Revit with the FireAI add-in installed")

PLATFORM:
  Windows only (named pipes are a Windows feature). On Linux/Mac, this
  client returns is_available()=False and all send_command calls return
  {"status": "error", "message": "Named pipes not available on this platform"}.
"""

from __future__ import annotations

import json
import logging
import platform
from typing import Any

logger = logging.getLogger(__name__)

_PIPE_NAME = r"\\.\pipe\FireAIRevitPipe"
_TIMEOUT_SECONDS = 10.0


class RevitNamedPipeClient:
    r"""
    Client for the C# Revit add-in named pipe server.

    On Windows, connects to \\\\.\\pipe\\FireAIRevitPipe.
    On Linux/Mac, is_available() returns False (named pipes are Windows-only).
    """

    def __init__(self, pipe_name: str = _PIPE_NAME) -> None:
        self._pipe_name = pipe_name
        self._is_windows = platform.system() == "Windows"
        if not self._is_windows:
            logger.info(
                "RevitNamedPipeClient: named pipes are Windows-only. "
                "On Linux/Mac, all send_command calls will return an error. "
                "Use the IFC pipeline (fireai.bridges.ifc_pipeline) for "
                "cross-platform Revit integration."
            )

    def is_available(self) -> bool:
        """
        Check if the named pipe is available (Windows + pipe server running).

        Returns:
            True if on Windows AND the pipe exists AND the C# add-in is
            listening. False otherwise.
        """
        if not self._is_windows:
            return False

        try:
            # Try to connect with a very short timeout to check availability
            import pywintypes
            import win32file
            import win32pipe  # noqa: F401 — Windows-only

            try:
                handle = win32file.CreateFile(
                    self._pipe_name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                win32file.CloseHandle(handle)
                return True
            except pywintypes.error:
                # Pipe not found or not available
                return False
        except ImportError:
            logger.warning(
                "pywin32 not installed — cannot check named pipe availability. "
                "Install with: pip install pywin32"
            )
            return False

    def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """
        Send a JSON command to the C# Revit add-in via named pipe.

        Args:
            command: Dict with at least an "action" key. Supported actions:
                - set_parameter: {action, element_id, parameter_name, value, nfpa_reference?}
                - set_string_parameter: {action, element_id, parameter_name, value, nfpa_reference?}
                - create_wall: {action, start_point: [x,y,z], end_point: [x,y,z], level?}

        Returns:
            Dict with "status" key:
                - {"status": "queued", "pending_count": N, ...} on success
                - {"status": "error", "message": "..."} on failure
        """
        if not self._is_windows:
            return {
                "status": "error",
                "message": (
                    "Named pipes not available on this platform. "
                    "Use the IFC pipeline (fireai.bridges.ifc_pipeline) for "
                    "cross-platform Revit integration."
                ),
            }

        try:
            import pywintypes
            import win32file
            import win32pipe  # noqa: F401 — Windows-only
        except ImportError:
            return {
                "status": "error",
                "message": "pywin32 not installed. Install with: pip install pywin32",
            }

        # Serialize command as newline-delimited JSON
        message = json.dumps(command) + "\n"
        message_bytes = message.encode("utf-8")

        try:
            # Connect to the pipe
            handle = win32file.CreateFile(
                self._pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except pywintypes.error as e:
            return {
                "status": "error",
                "message": (
                    f"Cannot connect to named pipe '{self._pipe_name}'. "
                    f"Is the FireAI Revit add-in running? Error: {e}"
                ),
            }

        try:
            # Send the command
            win32file.WriteFile(handle, message_bytes)

            # Read the response (newline-delimited JSON)
            response_bytes = b""
            while True:
                try:
                    result, data = win32file.ReadFile(handle, 4096)
                    if data:
                        response_bytes += data
                        if b"\n" in data:
                            break
                    if result != 0:  # 0 = more data, non-zero = done
                        break
                except pywintypes.error:
                    break

            response_str = response_bytes.decode("utf-8", errors="ignore").strip()
            if not response_str:
                return {
                    "status": "error",
                    "message": "Empty response from C# add-in",
                }

            try:
                return json.loads(response_str)
            except json.JSONDecodeError as je:
                return {
                    "status": "error",
                    "message": f"Invalid JSON response: {je}",
                    "raw_response": response_str[:200],
                }

        finally:
            win32file.CloseHandle(handle)

    def send_set_parameter(
        self,
        element_id: str,
        parameter_name: str,
        value: float,
        nfpa_reference: str = "",
    ) -> dict[str, Any]:
        """Convenience method for set_parameter action."""
        return self.send_command({
            "action": "set_parameter",
            "element_id": str(element_id),
            "parameter_name": parameter_name,
            "value": float(value),
            "nfpa_reference": nfpa_reference,
        })

    def send_set_string_parameter(
        self,
        element_id: str,
        parameter_name: str,
        value: str,
        nfpa_reference: str = "",
    ) -> dict[str, Any]:
        """Convenience method for set_string_parameter action."""
        return self.send_command({
            "action": "set_string_parameter",
            "element_id": str(element_id),
            "parameter_name": parameter_name,
            "value": str(value),
            "nfpa_reference": nfpa_reference,
        })

    def send_create_wall(
        self,
        start_point: list[float],
        end_point: list[float],
        level: str = "Level 1",
    ) -> dict[str, Any]:
        """Convenience method for create_wall action. Coordinates in mm."""
        return self.send_command({
            "action": "create_wall",
            "start_point": [float(c) for c in start_point],
            "end_point": [float(c) for c in end_point],
            "level": level,
        })

    def get_stats(self) -> dict[str, Any]:
        """Get connection status and statistics."""
        return {
            "pipe_name": self._pipe_name,
            "platform": platform.system(),
            "is_windows": self._is_windows,
            "is_available": self.is_available(),
        }
