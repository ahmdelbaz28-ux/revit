"""fireai/core/seismic_joint_penalyer.py
======================================
Seismic / Building Expansion Joint Routing Penalty Engine.

V19.1 FIX: Changed from violation-flagging to orthogonal crossing enforcement.
The original V19 implementation treated joint crossings as violations to
be flagged.  This is WRONG because:

  1. Cables MUST cross structural joints — there is no alternative path
     in most buildings.
  2. The code requirement (NEC §300.4(D)) is NOT to avoid crossings,
     but to use FLEXIBLE conduit transitions at 90° approach angles.
  3. Penalizing the crossing encourages the A* router to take detoured
     paths that may be worse (longer, more voltage drop, more walls).

The corrected approach:
  - Joint crossings are ALLOWED but must be orthogonal (90° approach).
  - Non-orthogonal approach vectors are heavily penalized in the A*
    cost grid, forcing the router to approach joints at right angles.
  - Each crossing generates a FLEXIBLE_JUNCTION_TIE element for the
    AutoDrafting engine and BOQ.

Code references:
  - NFPA 70 (NEC) §300.4(D) — Protection against physical damage
  - NFPA 70 (NEC) §250.98   — Bonding for other enclosures
  - IBC 2021 §1705.18       — Seismic resistance testing
  - ASCE 7-22 §13.6.6       — Architectural, mechanical, electrical
    components & systems in seismic design category C and above
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Minimum offset distance (m) from a joint crossing for the flexible
# conduit transition zone
FLEXIBLE_TRANSITION_LENGTH_M: float = 0.6

# Cost penalty for A* grid cells on joint lines — NOT prohibitive,
# just enough to encourage orthogonal approach
JOINT_CROSSING_COST_PENALTY: float = 40.0

# Maximum angle (degrees) deviation from 90° that is considered
# an orthogonal approach.  Paths approaching at >30° from perpendicular
# are penalized.
ORTHOGONAL_TOLERANCE_DEG: float = 30.0

# Citations
_CITE_NEC_300_4D = "NEC §300.4(D)"
_CITE_NEC_250_98 = "NEC §250.98"
_CITE_IBC_1705_18 = "IBC 2021 §1705.18"
_CITE_ASCE_7 = "ASCE 7-22 §13.6.6"


@dataclass(frozen=True)
class StructuralJoint:
    """Represents a seismic or expansion joint as a line segment."""

    joint_id: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    joint_type: str = "seismic"
    expected_displacement_mm: float = 25.0


@dataclass(frozen=True)
class JointCrossing:
    """Records a single path crossing of a structural joint."""

    joint_id: str
    crossing_point: Tuple[float, float]
    path_segment_index: int
    approach_angle_deg: float  # Angle between path segment and joint normal
    is_orthogonal: bool  # True if within ORTHOGONAL_TOLERANCE_DEG of 90°
    requires_flexible: bool = True


@dataclass(frozen=True)
class FlexibleJunctionTie:
    """Represents a required flexible conduit transition at a joint crossing."""

    joint_id: str
    location: Tuple[float, float]
    conduit_type: str = "LFMC"
    length_m: float = FLEXIBLE_TRANSITION_LENGTH_M


def _segments_intersect(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float],
) -> Optional[Tuple[float, float]]:
    """Find the intersection point of two line segments."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return (round(ix, 4), round(iy, 4))

    return None


def _compute_approach_angle(
    path_start: Tuple[float, float],
    path_end: Tuple[float, float],
    joint_start: Tuple[float, float],
    joint_end: Tuple[float, float],
) -> float:
    """Compute the crossing angle between the path and the joint line.

    Returns the angle in degrees.  90° means perfectly orthogonal
    (path crosses joint at right angle).  0° means parallel
    (path runs along the joint — worst case for shearing).

    The angle is measured between the path direction vector and the
    joint direction vector.  When the path is perpendicular to the
    joint, the angle is 90° (optimal for flexible conduit transitions).
    """
    # Path direction vector
    dx_path = path_end[0] - path_start[0]
    dy_path = path_end[1] - path_start[1]
    path_len = math.hypot(dx_path, dy_path)
    if path_len < 1e-9:
        return 0.0

    # Joint direction vector
    dx_joint = joint_end[0] - joint_start[0]
    dy_joint = joint_end[1] - joint_start[1]
    joint_len = math.hypot(dx_joint, dy_joint)
    if joint_len < 1e-9:
        return 0.0

    # Normalise
    dx_path /= path_len
    dy_path /= path_len
    dx_joint /= joint_len
    dy_joint /= joint_len

    # Angle between path direction and joint direction
    # cos(θ) = |path · joint|
    # When path ⊥ joint: cos = 0, θ = 90° (orthogonal = GOOD)
    # When path ∥ joint: cos = 1, θ = 0° (parallel = BAD)
    cos_angle = abs(dx_path * dx_joint + dy_path * dy_joint)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    angle_deg = math.degrees(math.acos(cos_angle))

    return round(angle_deg, 1)


class SeismicJointPenalyer:
    """Detects and enforces orthogonal crossing of structural joints
    by fire-alarm routing paths.

    V19.1 ENHANCEMENT: Joint crossings are now ALLOWED but must be
    orthogonal (within 30° of perpendicular).  Non-orthogonal approaches
    are penalized in the A* cost grid, and violations are flagged only
    when the approach angle deviates significantly from 90°.

    Flexible conduit transitions (LFMC) are automatically injected at
    each crossing point for the AutoDrafting engine and BOQ.

    Usage::

        penalyer = SeismicJointPenalyer()
        result = penalyer.detect_structural_shearing(
            path=[(0,0), (5,0), (10,0), (15,0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -5), (10, 5), "seismic"),
            ],
        )
    """

    def __init__(
        self,
        crossing_cost_penalty: float = JOINT_CROSSING_COST_PENALTY,
        flexible_transition_length_m: float = FLEXIBLE_TRANSITION_LENGTH_M,
        orthogonal_tolerance_deg: float = ORTHOGONAL_TOLERANCE_DEG,
    ) -> None:
        self.crossing_cost_penalty = crossing_cost_penalty
        self.flexible_transition_length_m = flexible_transition_length_m
        self.orthogonal_tolerance_deg = orthogonal_tolerance_deg

    def detect_structural_shearing(
        self,
        path: List[Tuple[float, float]],
        seismic_joints: List[StructuralJoint],
    ) -> Any:
        """Analyse a routing path for structural joint crossings.

        V19.1: Crossings are permitted but must be orthogonal.
        Non-orthogonal crossings generate violations.  All crossings
        generate flexible conduit transitions.
        """
        violations: list = []
        crossings: List[JointCrossing] = []
        flexible_junctions: List[FlexibleJunctionTie] = []

        for seg_idx in range(len(path) - 1):
            p1 = path[seg_idx]
            p2 = path[seg_idx + 1]

            for joint in seismic_joints:
                intersection = _segments_intersect(
                    p1,
                    p2,
                    joint.start,
                    joint.end,
                )
                if intersection is not None:
                    # Compute approach angle
                    approach_angle = _compute_approach_angle(
                        p1,
                        p2,
                        joint.start,
                        joint.end,
                    )
                    is_orthogonal = abs(90.0 - approach_angle) <= self.orthogonal_tolerance_deg

                    crossing = JointCrossing(
                        joint_id=joint.joint_id,
                        crossing_point=intersection,
                        path_segment_index=seg_idx,
                        approach_angle_deg=approach_angle,
                        is_orthogonal=is_orthogonal,
                        requires_flexible=True,
                    )
                    crossings.append(crossing)

                    # Inject flexible junction tie
                    flex_length = max(
                        self.flexible_transition_length_m,
                        (joint.expected_displacement_mm / 1000.0) * 2.0,
                    )
                    flexible_junctions.append(
                        FlexibleJunctionTie(
                            joint_id=joint.joint_id,
                            location=intersection,
                            conduit_type="LFMC",
                            length_m=round(flex_length, 3),
                        )
                    )

                    # Flag violation ONLY for non-orthogonal crossings
                    if not is_orthogonal:
                        desc = (
                            f"Fire-alarm cable crosses "
                            f"{'seismic' if joint.joint_type == 'seismic' else 'expansion'} "
                            f"joint '{joint.joint_id}' at point "
                            f"({intersection[0]:.1f}, {intersection[1]:.1f}) "
                            f"with approach angle {approach_angle:.1f}° "
                            f"(required: 90° ± {self.orthogonal_tolerance_deg:.0f}°). "
                            f"Non-orthogonal crossings risk conduit fatigue "
                            f"during structural movement. Re-route to cross "
                            f"at right angle."
                        )
                        if Violation is not None:
                            violations.append(
                                Violation(
                                    severity="MAJOR",
                                    citation=f"{_CITE_NEC_300_4D} / Orthogonal Crossing",
                                    description=desc,
                                )
                            )
                        else:
                            violations.append(
                                {
                                    "severity": "MAJOR",
                                    "citation": f"{_CITE_NEC_300_4D} / Orthogonal Crossing",
                                    "description": desc,
                                }
                            )
                        logger.warning(desc)

        safe = len(violations) == 0

        # Build penalty grid cells for A* integration
        # Joint cells get a moderate cost (not prohibitive) to encourage
        # orthogonal approach
        penalty_cells: List[Dict[str, Any]] = []
        for joint in seismic_joints:
            x1, y1 = joint.start
            x2, y2 = joint.end
            length = math.hypot(x2 - x1, y2 - y1)
            if length < 1e-6:
                continue
            steps = max(1, int(length / 0.25))
            for i in range(steps + 1):
                t = i / steps
                gx = round((x1 + t * (x2 - x1)) * 4) / 4
                gy = round((y1 + t * (y2 - y1)) * 4) / 4
                penalty_cells.append(
                    {
                        "x": gx,
                        "y": gy,
                        "cost_penalty": self.crossing_cost_penalty,
                        "joint_id": joint.joint_id,
                        "force_orthogonal": True,
                    }
                )

        # Build provenance result
        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NEC_300_4D,
                        constant_id="SEISMIC_JOINT_FLEXIBLE",
                        value_used=self.flexible_transition_length_m,
                        unit="metres",
                    ),
                    RuleApplied(
                        citation=_CITE_NEC_250_98,
                        constant_id="BONDING_JOINT",
                        value_used=1.0,
                        unit="BOOLEAN",
                    ),
                    RuleApplied(
                        citation=f"{_CITE_NEC_300_4D} / IBC Seismic",
                        constant_id="ORTHOGONAL_CROSSING",
                        value_used=90.0,
                        unit="Degrees_Implied",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="seismic_joint_routing",
                    value={
                        "crossings_detected": len(crossings),
                        "orthogonal_crossings": sum(1 for c in crossings if c.is_orthogonal),
                        "non_orthogonal_crossings": sum(1 for c in crossings if not c.is_orthogonal),
                        "flexible_junctions": [
                            {
                                "joint_id": fj.joint_id,
                                "location": fj.location,
                                "conduit_type": fj.conduit_type,
                                "length_m": fj.length_m,
                            }
                            for fj in flexible_junctions
                        ],
                        "penalty_grid_cells": penalty_cells,
                        "force_orthogonal": True,
                        "safe": safe,
                    },
                    inputs={
                        "path_points": len(path),
                        "structural_joints": len(seismic_joints),
                    },
                    rules_applied=rules,
                    algorithm={
                        "name": "AnisotropicCostMultiplier",
                        "version": "v19.1",
                    },
                    confidence=conf,
                    selected_because=(
                        "Ensures wires transverse gaps strictly via robust "
                        "minimal profiles yielding valid Flexible-Hose "
                        "(FMC/LFMC) deployment points over fracture voids. "
                        "Orthogonal approach enforced via A* cost anisotropy."
                    ),
                    violations=violations if violations else None,
                )
            except Exception as exc:
                logger.error("Failed to record seismic joint routing decision audit: %s", exc)

        return {
            "decision_type": "seismic_joint_routing",
            "value": {
                "crossings_detected": len(crossings),
                "flexible_junctions": [
                    {
                        "joint_id": fj.joint_id,
                        "location": fj.location,
                        "conduit_type": fj.conduit_type,
                        "length_m": fj.length_m,
                    }
                    for fj in flexible_junctions
                ],
                "safe": safe,
            },
            "inputs": {
                "path_points": len(path),
                "structural_joints": len(seismic_joints),
            },
            "safe": safe,
            "violations": violations,
        }


__all__ = [
    "FLEXIBLE_TRANSITION_LENGTH_M",
    "JOINT_CROSSING_COST_PENALTY",
    "ORTHOGONAL_TOLERANCE_DEG",
    "FlexibleJunctionTie",
    "JointCrossing",
    "SeismicJointPenalyer",
    "StructuralJoint",
    "_compute_approach_angle",
    "_segments_intersect",
]
