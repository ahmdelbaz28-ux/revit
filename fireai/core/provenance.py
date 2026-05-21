"""
fireai/core/provenance.py
=========================
Re-export shim for DecisionProvenance and related audit classes.

V14: Previously, routing_global_class_a.py imported directly from
src.v8_core.decision_provenance — a cross-package dependency that
is fragile for deployment. This shim provides a stable import path
within the fireai package tree.

If src.v8_core.decision_provenance is not available (e.g., stripped
deployment), all exports default to None and the caller should handle
the ImportError gracefully.

Usage:
    from fireai.core.provenance import DecisionProvenance, RuleApplied
"""
from __future__ import annotations

try:
    from src.v8_core.decision_provenance import (
        DecisionProvenance,
        RuleApplied,
        ConfidenceScore,
        ConfidenceLevel,
        Violation,
    )
except ImportError:
    # Graceful degradation — caller must handle None values
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]

__all__ = [
    "DecisionProvenance",
    "RuleApplied",
    "ConfidenceScore",
    "ConfidenceLevel",
    "Violation",
]
