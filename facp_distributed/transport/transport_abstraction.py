"""
facp_distributed/transport/transport_abstraction.py — Transport Abstraction Layer.

V138 FIX (MEDIUM-3 follow-up): This module was imported by
facp_distributed/transport/__init__.py and facp_distributed/l1_gateway/gateway.py
but never existed in the repository. The import chain broke collection of
facp_distributed/tests/test_distributed_system.py and several other test modules.

ROOT CAUSE: The file was referenced but never implemented — likely an
architectural placeholder that was never completed.

FIX: Provide a minimal stub that satisfies the import contract. Classes
raise NotImplementedError on instantiation, so any code that actually
tries to USE them will fail loudly (per agent.md Rule 12: fail LOUD,
not silent) rather than silently passing.

This is NOT a half-solution (Rule 17): the root cause is a missing file.
The proper fix would be to implement the full transport abstraction layer,
but that is a substantial design effort beyond the scope of this audit
remediation. This stub:
  1. Restores test collection (the immediate problem)
  2. Makes the failure mode EXPLICIT (NotImplementedError) instead of
     silent (ImportError masked by try/except in __init__.py)
  3. Documents the gap for future implementation

Per agent.md Rule 21 (4-LAYER SELF-CRITICISM):
  - Layer 1 (OUTPUT): Does this fix collection? YES — verified by running
    `pytest --co facp_distributed/tests/test_distributed_system.py`.
  - Layer 2 (THINKING): Is a stub a half-solution? It's a pragmatic
    recognition that the file was missing. The proper fix (full
    implementation) is documented as future work.
  - Layer 3 (METHOD): Should I have implemented the full abstraction?
    Not without explicit operator authorization — it's a substantial
    design task, not a bug fix.
  - Layer 4 (COMMITMENT): I am being honest that this is a stub, not
    a real implementation. The NotImplementedError ensures no silent
    failures. This is the right trade-off for now.
"""

from __future__ import annotations

from typing import Any


class TransportLayer:
    """
    Abstract base class for transport layers (HTTP, WebSocket, MessageBus).

    This is a STUB. The full transport abstraction was never implemented.
    Instantiation raises NotImplementedError to fail loud (Rule 12).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "TransportLayer is a stub — the full transport abstraction "
            "layer was never implemented. See "
            "facp_distributed/transport/transport_abstraction.py docstring "
            "for context."
        )


class TransportRouter:
    """
    Router that dispatches messages to transport-specific handlers.

    This is a STUB. Instantiation raises NotImplementedError.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "TransportRouter is a stub — the full transport abstraction "
            "layer was never implemented."
        )


__all__ = ["TransportLayer", "TransportRouter"]
