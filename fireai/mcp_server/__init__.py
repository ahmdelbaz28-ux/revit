"""fireai.mcp_server — Model Context Protocol Server for Revit Integration
=======================================================================
LIFE-SAFETY CRITICAL: This module provides the bridge between AI assistants
(Claude, GPT, etc.) and the Revit BIM model. It is the PRIMARY attack
surface for injection attacks and the PRIMARY source of thread-safety
violations.

Safety Architecture:
  1. ALL inputs from external sources (MCP clients) are sanitized via
     bim_input_sanitizer before any processing
  2. ALL Revit model writes are queued through ThreadSafeModelUpdateQueue
     — never executed directly from MCP handler threads
  3. NO eval(), exec(), subprocess, or dynamic code execution
  4. ALL database operations use parameterized queries
  5. ALL engineering calculations use validated, bounded inputs

Standards:
  - OWASP Top 10 A03:2021 (Injection Prevention)
  - ISO 17822 (Software Quality in Building Engineering)
  - Revit API SDK Concurrency Guidelines
  - NFPA 13-2022 Chapter 23 (Hydraulic Calculations)
  - NFPA 72-2022 §10.6.7 (Battery Sizing)

This module was created in response to Forensic Audit Finding 1 (Catastrophic)
and Finding 4 (Catastrophic) — no MCP server existed previously, creating
an uncontrolled integration point. This module provides a SAFE foundation
for all MCP/Revit communication.
"""

from fireai.mcp_server.revit_mcp_server import RevitMCPServer
from fireai.mcp_server.sanitized_handler import (
    MCPRequest,
    MCPResponse,
    SanitizedMCPHandler,
)
from fireai.mcp_server.thread_safe_queue import (
    ModelUpdateAction,
    ModelUpdateResult,
    ThreadSafeModelUpdateQueue,
)
from fireai.mcp_server.thread_safe_queue import (
    ModelUpdateStatus as ModelUpdateStatus,
)
from fireai.mcp_server.thread_safe_queue import (
    ModelUpdateType as ModelUpdateType,
)

__all__ = [
    "MCPRequest",
    "MCPResponse",
    "ModelUpdateAction",
    "ModelUpdateResult",
    "RevitMCPServer",
    "SanitizedMCPHandler",
    "ThreadSafeModelUpdateQueue",
]
