"""
Distributed FireAI Agent Communication Protocol (FACP) System

This package implements a 3-tier distributed architecture:
  L1 — Gateway (API entry)
  L2 — Orchestrator (agent management, load balancing, task scheduling)
  L3 — Engine Workers (engine controllers)

Sub-packages:
  event_bus, l1_gateway, l2_orchestrator, l3_engine_workers,
  protocol, security, transport

NOTE: Sub-modules are imported lazily (via their own __init__.py) to keep
the top-level import lightweight. The test suite imports the specific
sub-modules it needs (e.g. ``from ..event_bus.cluster_communicator import ...``),
which requires this top-level package marker to exist.
"""

__all__: list[str] = []
