"""fireai/core/routing_global_class_a.py
=====================================
WRAPPER — Delegates to EliteClassARouter (routing_engine_v10.py).

This module is retained for backward compatibility. The canonical
Class A routing engine is EliteClassARouter in routing_engine_v10.py
which provides BOTH Class A separation AND firestopping detection
in a single unified engine.

Why this wrapper exists:
  - routing_global_class_a.py was created first (V12) with DecisionProvenance audit
  - routing_engine_v10.py was created second (V12) with unified Class A + Firestopping
  - Having two engines doing the same thing differently caused confusion
  - V13: This file is now a thin wrapper that delegates to the canonical engine
    and converts RouteSegment output to DecisionProvenance for audit compatibility

The canonical engine: fireai.core.routing_engine_v10.EliteClassARouter
"""

from __future__ import annotations

from typing import List, Tuple

from fireai.core.provenance import (
    ConfidenceLevel,
    ConfidenceScore,
    DecisionProvenance,
    RuleApplied,
    Violation,
)
from fireai.core.routing_engine_v10 import EliteClassARouter


class EliteGlobalRouter:
    """Backward-compatible wrapper around EliteClassARouter.

    Converts the canonical RouteSegment output to DecisionProvenance
    format for audit trail compatibility.

    Parameters
    ----------
        global_bounds: (min_x, min_y, max_x, max_y) in meters.
        resolution: Grid cell size in meters (default 0.25m).

    """

    def __init__(self, global_bounds: Tuple[float, float, float, float], resolution: float = 0.25):
        min_x, min_y, max_x, max_y = global_bounds
        width = max_x - min_x
        length = max_y - min_y
        self._router = EliteClassARouter(
            width=width,
            length=length,
            resolution=resolution,
        )
        self._min_x = min_x
        self._min_y = min_y

    def apply_class_a_separation(self, outgoing_path: List[Tuple[float, float]], min_sep_m: float = 1.0) -> None:
        """No-op for backward compatibility. Separation is applied internally
        by EliteClassARouter.generate_class_a_loop().
        """
        pass  # Delegated to EliteClassARouter internally

    def route_class_a_loop(
        self, panel: Tuple[float, float], terminal_device: Tuple[float, float]
    ) -> DecisionProvenance:
        """Compute a full Class A loop via EliteClassARouter and wrap
        the result in a DecisionProvenance for audit trail compatibility.

        Parameters
        ----------
            panel: (x, y) coordinates of the fire alarm panel.
            terminal_device: (x, y) coordinates of the last device on the loop.

        Returns
        -------
            DecisionProvenance with:
              - value: {"out_path": [...], "return_path": [...]}
              - rules_applied: NFPA 72 S12.2.2 with 1.0m constant
              - violations: CRITICAL if return path blocked

        """
        try:
            result = self._router.generate_class_a_loop(panel, [terminal_device])

            out_seg = result["outgoing_class_a"]
            ret_seg = result["return_class_a"]

            rule_applied = RuleApplied(
                citation="NFPA 72 §12.2.2; NEC 760.154; Engineering practice",
                constant_id="CLASS_A_SEP",
                value_used=1.0,
                unit="m",
            )

            # Include firestopping info in the audit trail
            all_firestops = out_seg.firestop_nodes + ret_seg.firestop_nodes
            firestop_note = ""
            if all_firestops:
                firestop_note = f" | {len(all_firestops)} fire-rated wall penetration(s) detected (IBC S714)"

            return DecisionProvenance.new(
                decision_type="class_a_route_creation",
                value={"out_path": out_seg.path, "return_path": ret_seg.path},
                inputs={"panel": panel, "terminal_node": terminal_device},
                rules_applied=[rule_applied],
                algorithm={"name": "astar_matrix_masking", "version": "v13_unified"},
                confidence=ConfidenceScore(
                    level=ConfidenceLevel.HIGH,
                    value=1.0,
                    reason="Class A routing",
                    standard_reference="HIGH",
                ),
                selected_because=f"Geographic constraint satisfied for isolation routing.{firestop_note}",
                violations=[],
            )

        except ValueError as e:
            # Return path could not satisfy separation constraint
            violation = Violation(
                severity="CRITICAL",
                citation="NFPA 72 §12.2.2; NEC 760.154",
                description=str(e),
            )
            rule_applied = RuleApplied(
                citation="NFPA 72 §12.2.2; NEC 760.154; Engineering practice",
                constant_id="CLASS_A_SEP",
                value_used=1.0,
                unit="m",
            )
            return DecisionProvenance.new(
                decision_type="class_a_route_creation",
                value=None,
                inputs={"panel": panel, "terminal_node": terminal_device},
                rules_applied=[rule_applied],
                algorithm={"name": "astar_matrix_masking", "version": "v13_unified"},
                confidence=ConfidenceScore(
                    level=ConfidenceLevel.LOW,
                    value=0.0,
                    reason="Class A routing failed",
                    standard_reference="REFUSE",
                ),
                selected_because="Return path blocked by separation constraint",
                violations=[violation],
            )
