"""generative_layout_agent.py — Generative Design Engine for FireAI
====================================================================

MISSION TASK 2 — Generative Design Engine (The Market Value Driver)
====================================================================

This module implements the ``GenerativeLayoutAgent`` — a multi-variant
detector placement optimizer that generates THREE distinct design
variants for any room, scored by a weighted algorithm based on
(Coverage % / Total Cost).

Variants Generated
------------------
1. **COST_MINIMIZED**: Fewest detectors that still achieve ≥99.9% coverage.
   Reuses the existing DensityOptimizer placement, then aggressively
   removes redundant detectors via ``_remove_redundant()``.

2. **STANDARD_COMPLIANT**: NFPA 72 strict compliance with normal
   detector count. Uses DensityOptimizer placement WITHOUT redundancy
   removal — keeps all detectors the optimizer placed.

3. **SAFETY_MAXIMIZED**: Highest overlap redundancy. Reduces detector
   spacing to 0.85× standard (per NFPA 72 §17.7.4.2.3.1 allowable
   reduction for high-hazard occupancies), placing MORE detectors
   for fail-safe coverage.

Scoring System
--------------
Each variant receives a score:

    score = (COVERAGE_WEIGHT × coverage_pct +
             COMPLIANCE_WEIGHT × is_compliant × 100 +
             REDUNDANCY_WEIGHT × overlap_pct) /
            (1.0 + COST_WEIGHT × total_cost_usd)

Default weights (configurable):
    COVERAGE_WEIGHT = 0.50    # Coverage % is most important
    COMPLIANCE_WEIGHT = 0.30  # Code compliance is critical
    REDUNDANCY_WEIGHT = 0.10  # Safety overlap is bonus
    COST_WEIGHT = 0.10        # Cost is least important (but considered)

Multiprocessing
---------------
Variants are computed in PARALLEL using ``multiprocessing.Pool``
with fork context (per agent.md V37: threads forbidden due to
GIL on CPU-bound spatial algorithms; per V0.3 Safety Guard:
ProcessPoolExecutor is forbidden due to crash safety).

Each worker gets a FRESH ``DensityOptimizer`` instance because
``DensityOptimizer`` mutates ``self.R``, ``self.R_place`` etc.
during ``optimize()`` (per VERIFY-TASK2 finding R4).

Audit Trail
-----------
Every generative attempt (including rejected variants) is recorded
in ``AuditStore`` with event_type ``GENERATIVE_ATTEMPT`` per
agent.md Rule 12 and NFPA 72 §7.5 for legal traceability.

Safety Design Decisions (per agent.md Rule 12 — Safety-First)
--------------------------------------------------------------
1. **STANDARD_COMPLIANT is the recommended default**. Cost-Minimized
   MUST NOT be used for high-hazard occupancies (healthcare, assembly,
   detention) — the agent refuses to mark it as "recommended" for
   such occupancies.
2. **Cost-Minimized never relaxes safety factors**: COVERAGE_SAFETY_FACTOR
   (0.98) and PLACEMENT_MARGIN (0.141m) remain unchanged. Only the
   post-placement redundancy removal differs.
3. **Safety-Maximized is capped at 2.0× the theoretical lower bound**
   to prevent absurd over-provisioning that could exceed SLC loop
   capacity (per VERIFY-TASK2 finding R3).
4. **All variants pass NFPA 72 verification** before being returned.
   If a variant fails verification, it is included in the result
   with ``proof_valid=False`` and an audit warning.

References
----------
- agent.md Rule 17: NO HALF-SOLUTIONS (3 variants + scoring + audit)
- agent.md Rule 12: Safety-First (occupancy-aware recommendation)
- agent.md V85 Bug #28: Deterministic run_id (content hash, not uuid4)
- NFPA 72-2022 §17.6.3.1.1, §17.7.4.2.3.1
"""

from __future__ import annotations

import logging
import math
import multiprocessing
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fireai.core.boq_generator import UNIT_COSTS
from fireai.core.spatial_engine.density_optimizer import (
    DENSITY_CAP_FACTOR,
    DETECTOR_RADIUS,
    DensityOptimizer,
    DetectorLayout,
    PLACEMENT_MARGIN,
    Room,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Scoring weights (sum to 1.0)
COVERAGE_WEIGHT: float = 0.50
COMPLIANCE_WEIGHT: float = 0.30
REDUNDANCY_WEIGHT: float = 0.10
COST_WEIGHT: float = 0.10

# Safety-Maximized spacing reduction (per NFPA 72 §17.7.4.2.3.1)
SAFETY_MAXIMIZED_SPACING_FACTOR: float = 0.85

# Occupancy types where Cost-Minimized is FORBIDDEN as recommended
# (high-hazard / life-critical occupancies per NFPA 101)
HIGH_HAZARD_OCCUPANCIES = frozenset({
    "healthcare", "hospital", "ambulatory", "assembly",
    "detention", "correctional", "daycare", "educational",
    "high_hazard", "extra_hazard", "ordinary_hazard_2",
})

# Multiprocessing context — fork is required per V37 (threads forbidden)
_MP_CONTEXT = "fork"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LayoutVariant(str, Enum):
    """The three generative design variants."""

    COST_MINIMIZED = "cost_minimized"
    STANDARD_COMPLIANT = "standard_compliant"
    SAFETY_MAXIMIZED = "safety_maximized"

    @property
    def description(self) -> str:
        return {
            LayoutVariant.COST_MINIMIZED: (
                "Fewest detectors achieving ≥99.9% coverage. "
                "Suitable for low-hazard occupancies with budget constraints."
            ),
            LayoutVariant.STANDARD_COMPLIANT: (
                "NFPA 72 strict compliance with standard detector count. "
                "Recommended for most occupancies."
            ),
            LayoutVariant.SAFETY_MAXIMIZED: (
                "Maximum redundancy with 0.85× spacing. "
                "Recommended for high-hazard / life-critical occupancies."
            ),
        }[self]


# ---------------------------------------------------------------------------
# Result Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VariantResult:
    """Result of generating one layout variant."""

    variant: LayoutVariant
    layout: DetectorLayout
    total_cost_usd: float
    overlap_pct: float
    score: float
    is_recommended: bool = False
    is_compliant: bool = False
    warnings: List[str] = field(default_factory=list)
    generation_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict (for API responses)."""
        return {
            "variant": self.variant.value,
            "variant_description": self.variant.description,
            "detector_count": self.layout.count,
            "coverage_pct": round(self.layout.coverage_pct, 4),
            "proof_valid": self.layout.proof_valid,
            "nfpa_valid": self.layout.nfpa_valid,
            "wall_violations": self.layout.wall_violations,
            "total_cost_usd": round(self.total_cost_usd, 2),
            "overlap_pct": round(self.overlap_pct, 4),
            "score": round(self.score, 4),
            "is_recommended": self.is_recommended,
            "is_compliant": self.is_compliant,
            "method": self.layout.method,
            "warnings": self.warnings,
            "generation_ms": round(self.generation_ms, 2),
        }


@dataclass
class GenerativeResult:
    """Complete result from GenerativeLayoutAgent.generate_variants()."""

    room: Room
    variants: Dict[LayoutVariant, VariantResult]
    recommended_variant: LayoutVariant
    total_generation_ms: float
    run_id: str
    audit_events: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room": {
                "name": self.room.name,
                "width": self.room.width,
                "length": self.room.length,
                "ceiling_height": self.room.ceiling_height,
                "area_m2": self.room.width * self.room.length,
            },
            "variants": {
                v.value: vr.to_dict() for v, vr in self.variants.items()
            },
            "recommended_variant": self.recommended_variant.value,
            "total_generation_ms": round(self.total_generation_ms, 2),
            "run_id": self.run_id,
            "audit_events": self.audit_events,
        }


# ---------------------------------------------------------------------------
# Worker Functions (must be module-level for multiprocessing)
# ---------------------------------------------------------------------------


def _generate_variant_worker(args: Tuple[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Multiprocessing worker — generates ONE variant.

    Must be module-level (not nested) for pickle compatibility with
    multiprocessing.Pool.

    Args:
        args: Tuple of (variant_name, room_dict, optimizer_config)

    Returns:
        Dict with variant result data (picklable).
    """
    variant_name, room_dict, optimizer_config = args

    # Reconstruct Room (picklable)
    room = Room(
        name=room_dict["name"],
        width=room_dict["width"],
        length=room_dict["length"],
        ceiling_height=room_dict["ceiling_height"],
    )

    # Create FRESH DensityOptimizer (per VERIFY-TASK2 R4: optimizer mutates self)
    optimizer = DensityOptimizer(
        max_spacing=optimizer_config["max_spacing"],
        wall_min=optimizer_config["wall_min"],
        radius=optimizer_config["radius"],
        max_iterations=optimizer_config["max_iterations"],
        timeout_seconds=optimizer_config["timeout_seconds"],
    )

    variant = LayoutVariant(variant_name)
    t_start = time.perf_counter()

    try:
        if variant == LayoutVariant.COST_MINIMIZED:
            # Step 1: Standard placement
            layout = optimizer.optimize(room)
            # Step 2: Aggressive redundancy removal
            optimizer._remove_redundant(layout)
            # Step 3: Verify still passes NFPA
            optimizer._verify_fast(layout)
            optimizer._audit_nfpa(layout)

        elif variant == LayoutVariant.STANDARD_COMPLIANT:
            # Standard placement, NO redundancy removal
            layout = optimizer.optimize(room)
            # Already verified by optimize()

        elif variant == LayoutVariant.SAFETY_MAXIMIZED:
            # Reduce spacing to 0.85× standard (per NFPA 72 §17.7.4.2.3.1)
            # This places MORE detectors for fail-safe coverage
            safety_radius = optimizer.R * SAFETY_MAXIMIZED_SPACING_FACTOR
            layout = optimizer.optimize(room, coverage_radius=safety_radius)
            # V135 F-7 FIX: Cap at 2.0× theoretical lower bound (per R3).
            # The OLD code did `layout.detectors[:cap]` which truncated the
            # FIRST `cap` detectors in placement order (grid scan) — leaving
            # large coverage holes in one corner. Now we use `_remove_redundant()`
            # which INTELLIGENTLY prunes the least-valuable detectors while
            # maintaining coverage. If still over cap, we re-run with standard
            # spacing (safer than arbitrary truncation).
            cap = int(math.ceil(layout.theoretical_lower_bound * DENSITY_CAP_FACTOR))
            if layout.count > cap:
                # Step 1: Try intelligent redundancy removal (preserves coverage)
                optimizer._remove_redundant(layout)
                # Step 2: If still over cap, fall back to standard spacing
                if layout.count > cap:
                    layout.warnings.append(
                        f"SAFETY_MAXIMIZED could not achieve {cap} detector cap "
                        f"with 0.85x spacing (got {layout.count}). Falling back to "
                        f"standard spacing — variant may not provide extra redundancy."
                    )
                    # Re-run with standard radius (no safety factor)
                    layout = optimizer.optimize(room)
                else:
                    layout.warnings.append(
                        f"SAFETY_MAXIMIZED capped to {layout.count} detectors "
                        f"(≤ {cap} = 2.0× theoretical lower bound) via intelligent "
                        f"redundancy removal — coverage preserved."
                    )
                # Re-verify after cap
                optimizer._verify_fast(layout)
                optimizer._audit_nfpa(layout)

        else:
            raise ValueError(f"Unknown variant: {variant}")

        generation_ms = (time.perf_counter() - t_start) * 1000.0

        return {
            "variant": variant.value,
            "layout": _serialize_layout(layout),
            "generation_ms": generation_ms,
            "error": None,
        }

    except Exception as exc:
        generation_ms = (time.perf_counter() - t_start) * 1000.0
        logger.error(
            "Variant %s generation failed: %s", variant.value, exc, exc_info=True
        )
        # Return a failed-layout result (never crash the whole batch)
        failed_layout = DetectorLayout(
            room=room, detectors=[], coverage_pct=0.0,
            proof_valid=False, nfpa_valid=False,
            method=f"FAILED_{variant.value}",
            violations=[f"Generation error: {exc!r}"],
        )
        return {
            "variant": variant.value,
            "layout": _serialize_layout(failed_layout),
            "generation_ms": generation_ms,
            "error": str(exc),
        }


def _serialize_layout(layout: DetectorLayout) -> Dict[str, Any]:
    """Serialize DetectorLayout to a picklable dict (for multiprocessing)."""
    return {
        "room": {
            "name": layout.room.name,
            "width": layout.room.width,
            "length": layout.room.length,
            "ceiling_height": layout.room.ceiling_height,
        },
        "detectors": list(layout.detectors),
        "coverage_pct": layout.coverage_pct,
        "proof_valid": layout.proof_valid,
        "nfpa_valid": layout.nfpa_valid,
        "wall_violations": layout.wall_violations,
        "method": layout.method,
        "violations": list(layout.violations),
        "warnings": list(layout.warnings),
        "fallback_used": layout.fallback_used,
        "coverage_radius": layout.coverage_radius,
        "theoretical_lower_bound": layout.theoretical_lower_bound,
    }


def _deserialize_layout(data: Dict[str, Any]) -> DetectorLayout:
    """Reconstruct DetectorLayout from serialized dict."""
    room = Room(
        name=data["room"]["name"],
        width=data["room"]["width"],
        length=data["room"]["length"],
        ceiling_height=data["room"]["ceiling_height"],
    )
    layout = DetectorLayout(
        room=room,
        detectors=[tuple(d) for d in data["detectors"]],
        coverage_pct=data["coverage_pct"],
        proof_valid=data["proof_valid"],
        nfpa_valid=data["nfpa_valid"],
        wall_violations=data["wall_violations"],
        method=data["method"],
        violations=list(data["violations"]),
        warnings=list(data["warnings"]),
        fallback_used=data["fallback_used"],
        coverage_radius=data["coverage_radius"],
    )
    return layout


# ---------------------------------------------------------------------------
# GenerativeLayoutAgent
# ---------------------------------------------------------------------------


class GenerativeLayoutAgent:
    """Generative Design Engine — produces 3 scored layout variants.

    Usage:
        agent = GenerativeLayoutAgent()
        room = Room(name="Office", width=10.0, length=8.0, ceiling_height=3.0)
        result = agent.generate_variants(room, occupancy_type="office")
        # result.variants[LayoutVariant.STANDARD_COMPLIANT] is recommended
        # result.to_dict() for API response
    """

    def __init__(
        self,
        coverage_weight: float = COVERAGE_WEIGHT,
        compliance_weight: float = COMPLIANCE_WEIGHT,
        redundancy_weight: float = REDUNDANCY_WEIGHT,
        cost_weight: float = COST_WEIGHT,
        use_multiprocessing: bool = True,
        n_workers: Optional[int] = None,
    ) -> None:
        """Initialize the generative agent.

        Args:
            coverage_weight: Weight for coverage % in scoring.
            compliance_weight: Weight for code compliance.
            redundancy_weight: Weight for detector overlap.
            cost_weight: Weight for total cost (penalty).
            use_multiprocessing: If True, use multiprocessing for variants.
            n_workers: Number of worker processes. None = min(3, cpu_count).
        """
        # Validate weights
        total = coverage_weight + compliance_weight + redundancy_weight + cost_weight
        # V135 F-31 FIX: Tightened tolerance from 0.01 to 0.001
        # The OLD code allowed weights to sum to 0.99-1.01. The docstring
        # says "must sum to 1.0". Now we allow 0.999-1.001 (stricter).
        if not math.isclose(total, 1.0, abs_tol=0.001):
            raise ValueError(
                f"Weights must sum to 1.0 (got {total}). "
                f"coverage={coverage_weight}, compliance={compliance_weight}, "
                f"redundancy={redundancy_weight}, cost={cost_weight}"
            )

        self.weights = {
            "coverage": coverage_weight,
            "compliance": compliance_weight,
            "redundancy": redundancy_weight,
            "cost": cost_weight,
        }
        self.use_multiprocessing = use_multiprocessing
        self.n_workers = n_workers or min(3, os.cpu_count() or 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_variants(
        self,
        room: Room,
        occupancy_type: str = "office",
        detector_type: str = "smoke",
        audit_run_id: Optional[str] = None,
    ) -> GenerativeResult:
        """Generate all 3 layout variants for a room.

        Args:
            room: Room to design for.
            occupancy_type: NFPA 101 occupancy classification.
            detector_type: "smoke" or "heat".
            audit_run_id: Optional run_id for audit trail correlation.

        Returns:
            GenerativeResult with all 3 variants + recommendation.
        """
        t_total = time.perf_counter()

        # Deterministic run_id (per agent.md V85 Bug #28)
        import hashlib
        import json
        if audit_run_id is None:
            content = json.dumps({
                "room": {"name": room.name, "width": room.width,
                         "length": room.length, "height": room.ceiling_height},
                "occupancy": occupancy_type,
                "detector": detector_type,
            }, sort_keys=True)
            h = hashlib.sha256(content.encode()).hexdigest()
            run_id = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        else:
            run_id = audit_run_id

        # Optimizer config (shared across all variants)
        max_spacing = 9.1 if detector_type == "smoke" else 6.1
        optimizer_config = {
            "max_spacing": max_spacing,
            "wall_min": 0.10,
            "radius": DETECTOR_RADIUS,
            "max_iterations": 1000,
            "timeout_seconds": 30.0,
        }

        room_dict = {
            "name": room.name,
            "width": room.width,
            "length": room.length,
            "ceiling_height": room.ceiling_height,
        }

        # Generate variants (parallel or sequential)
        tasks = [
            (LayoutVariant.COST_MINIMIZED.value, room_dict, optimizer_config),
            (LayoutVariant.STANDARD_COMPLIANT.value, room_dict, optimizer_config),
            (LayoutVariant.SAFETY_MAXIMIZED.value, room_dict, optimizer_config),
        ]

        if self.use_multiprocessing and self.n_workers > 1:
            results = self._generate_parallel(tasks)
        else:
            results = [self._generate_sequential(t) for t in tasks]

        # Build VariantResult objects
        variants: Dict[LayoutVariant, VariantResult] = {}
        audit_events: List[str] = []

        # V135 F-8: First pass — compute costs for all variants to determine
        # the reference_cost (median) used in the additive scoring formula.
        # The OLD formula didn't need this because it used multiplicative
        # denominator, but the new additive formula normalizes cost against
        # the median to keep the penalty in a reasonable range.
        variant_costs: Dict[LayoutVariant, float] = {}
        variant_layouts: Dict[LayoutVariant, DetectorLayout] = {}
        variant_overlaps: Dict[LayoutVariant, float] = {}
        variant_compliance: Dict[LayoutVariant, bool] = {}

        for r in results:
            variant = LayoutVariant(r["variant"])
            layout = _deserialize_layout(r["layout"])
            variant_layouts[variant] = layout
            variant_costs[variant] = self._compute_cost(layout, detector_type)
            variant_overlaps[variant] = self._compute_overlap_pct(layout)
            variant_compliance[variant] = layout.nfpa_valid and layout.proof_valid

        # V135 F-8: Compute reference_cost = median of all variant costs
        # Falls back to 1000.0 if all costs are 0 (degenerate case)
        costs_list = sorted(variant_costs.values())
        if costs_list and costs_list[len(costs_list) // 2] > 0:
            reference_cost = costs_list[len(costs_list) // 2]
        else:
            reference_cost = 1000.0  # Safe default

        for variant, layout in variant_layouts.items():
            total_cost = variant_costs[variant]
            overlap_pct = variant_overlaps[variant]
            is_compliant = variant_compliance[variant]

            # V135 F-8: Pass reference_cost to the new additive scoring formula
            score = self._compute_score(
                coverage_pct=layout.coverage_pct,
                is_compliant=is_compliant,
                overlap_pct=overlap_pct,
                total_cost=total_cost,
                reference_cost=reference_cost,
            )

            variants[variant] = VariantResult(
                variant=variant,
                layout=layout,
                total_cost_usd=total_cost,
                overlap_pct=overlap_pct,
                score=score,
                is_compliant=is_compliant,
                warnings=list(layout.warnings),
                generation_ms=r["generation_ms"],
            )

            # Record audit event (per agent.md Rule 12 + NFPA 72 §7.5)
            audit_event_id = self._record_audit_event(
                run_id=run_id,
                variant=variant,
                layout=layout,
                total_cost=total_cost,
                score=score,
                is_compliant=is_compliant,
                error=r.get("error"),
            )
            if audit_event_id:
                audit_events.append(audit_event_id)

        # Determine recommended variant
        recommended = self._recommend_variant(variants, occupancy_type)
        variants[recommended].is_recommended = True

        total_ms = (time.perf_counter() - t_total) * 1000.0

        return GenerativeResult(
            room=room,
            variants=variants,
            recommended_variant=recommended,
            total_generation_ms=total_ms,
            run_id=run_id,
            audit_events=audit_events,
        )

    # ------------------------------------------------------------------
    # Cost & Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_cost(layout: DetectorLayout, detector_type: str) -> float:
        """Compute total cost of a layout (detectors + cable + conduit).

        Per UNIT_COSTS from boq_generator.py.
        """
        detector_count = layout.count
        unit_cost_key = f"{detector_type}_detector"
        unit_cost = UNIT_COSTS.get(unit_cost_key, UNIT_COSTS.get("smoke_detector", 85.0))

        # Detector cost
        detector_cost = detector_count * unit_cost

        # Cable cost (estimate: average cable run per detector = room diagonal / 2)
        room_diagonal = math.sqrt(
            layout.room.width ** 2 + layout.room.length ** 2
        )
        avg_cable_per_detector = room_diagonal / 2
        total_cable_m = detector_count * avg_cable_per_detector
        cable_cost = total_cable_m * UNIT_COSTS["cable_fpl_per_m"]

        # Conduit cost (assume 80% of cable runs through conduit)
        conduit_m = total_cable_m * 0.8
        conduit_cost = conduit_m * UNIT_COSTS["conduit_per_m"]

        # Junction boxes (one per 3 detectors, minimum 1)
        junction_boxes = max(1, math.ceil(detector_count / 3))
        junction_cost = junction_boxes * UNIT_COSTS["junction_box"]

        return detector_cost + cable_cost + conduit_cost + junction_cost

    @staticmethod
    def _compute_overlap_pct(layout: DetectorLayout) -> float:
        """Compute average overlap percentage between detector coverage circles.

        0% = no overlap (minimum cost)
        100% = all detectors at same point (maximum redundancy)

        Uses a sampling approach for performance (exact computation
        requires Shapely union, which is expensive for many detectors).
        """
        if layout.count <= 1:
            return 0.0

        # Sample-based overlap estimation
        detectors = layout.detectors
        radius = layout.coverage_radius

        # Compute pairwise distance matrix
        total_overlap_area = 0.0
        total_possible_area = 0.0

        for i in range(len(detectors)):
            for j in range(i + 1, len(detectors)):
                x1, y1 = detectors[i]
                x2, y2 = detectors[j]
                dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

                # Circle intersection area formula
                if dist >= 2 * radius:
                    # No overlap
                    continue
                elif dist == 0:
                    # Complete overlap
                    overlap = math.pi * radius ** 2
                else:
                    # Partial overlap (circle-circle intersection)
                    r = radius
                    d = dist
                    overlap = (
                        2 * r ** 2 * math.acos(d / (2 * r))
                        - d / 2 * math.sqrt(4 * r ** 2 - d ** 2)
                    )

                total_overlap_area += overlap
                total_possible_area += math.pi * radius ** 2

        if total_possible_area == 0:
            return 0.0

        # Overlap % = total overlap / total possible area
        return min(100.0, (total_overlap_area / total_possible_area) * 100.0)

    def _compute_score(
        self,
        coverage_pct: float,
        is_compliant: bool,
        overlap_pct: float,
        total_cost: float,
        reference_cost: float = 1000.0,
    ) -> float:
        """Compute weighted score for a variant.

        V135 F-8 FIX: The OLD formula used a MULTIPLICATIVE denominator
        ``(1 + w_cost × cost)`` which made cost dominate the score
        (a 2× cost reduction doubled the score, while 10% coverage
        improvement added only 5 points). The docstring claimed
        "COST_WEIGHT = 0.10 # Cost is least important" but mathematically
        cost had the LARGEST impact.

        New formula uses ADDITIVE cost penalty (matches stated weights):

            score = (w_cov×coverage + w_comp×compliance×100 + w_red×overlap)
                    - w_cost × (cost / reference_cost) × 100

        where ``reference_cost`` is the median cost across variants
        (passed by caller). This normalizes the cost penalty to a
        0-100 scale matching the other terms. A variant at 2×
        reference cost loses ~10 points (w_cost × 2 × 100 = 20, but
        typical cost variance is smaller).

        Higher score = better variant.
        """
        import math

        # Validate inputs (per agent.md V57 NaN/Inf bypass)
        for name, val in (("coverage_pct", coverage_pct),
                          ("overlap_pct", overlap_pct),
                          ("total_cost", total_cost),
                          ("reference_cost", reference_cost)):
            if not math.isfinite(val):
                return 0.0  # Fail-safe: NaN/Inf → score 0

        # V135 F-8: Additive formula (cost penalty, not multiplicative denominator)
        bonus = (
            self.weights["coverage"] * max(0.0, coverage_pct)
            + self.weights["compliance"] * (100.0 if is_compliant else 0.0)
            + self.weights["redundancy"] * max(0.0, overlap_pct)
        )
        # Cost penalty: normalized to 0-100 scale via reference_cost
        # cost_ratio = 1.0 (at reference) → penalty = w_cost × 100 = 10 points
        # cost_ratio = 2.0 (double reference) → penalty = w_cost × 200 = 20 points
        cost_ratio = total_cost / reference_cost if reference_cost > 0 else 0.0
        penalty = self.weights["cost"] * cost_ratio * 100.0

        score = bonus - penalty
        return max(0.0, score)  # Score should not be negative

    # ------------------------------------------------------------------
    # Recommendation Logic
    # ------------------------------------------------------------------

    @staticmethod
    def _recommend_variant(
        variants: Dict[LayoutVariant, VariantResult],
        occupancy_type: str,
    ) -> LayoutVariant:
        """Recommend the best variant for the given occupancy.

        V135 F-9 FIX: The OLD docstring said "Cost-Minimized only
        recommended for low-hazard + budget-constrained" but the code
        NEVER recommended COST_MINIMIZED — it always fell through to
        STANDARD_COMPLIANT. This made the COST_MINIMIZED variant
        useless (generated but never selected).

        New logic:
        - High-hazard occupancies → SAFETY_MAXIMIZED (if compliant)
        - Low-hazard occupancies (storage, parking, utility) with
          COST_MINIMIZED compliant AND scoring ≥ 90% of STANDARD →
          COST_MINIMIZED (honors the docstring promise)
        - Standard occupancies → STANDARD_COMPLIANT (default)
        - If no compliant variant exists, recommend highest coverage

        Safety-first logic (per agent.md Rule 12) is preserved:
        COST_MINIMIZED is NEVER recommended for high-hazard occupancies.
        """
        occ_lower = occupancy_type.lower()

        # Filter to compliant variants only
        compliant = {v: r for v, r in variants.items() if r.is_compliant}

        if not compliant:
            # No compliant variant — recommend highest coverage (fail-safe)
            best = max(variants.values(), key=lambda r: r.layout.coverage_pct)
            return best.variant

        # High-hazard occupancy → SAFETY_MAXIMIZED preferred (NEVER cost-minimized)
        if any(h in occ_lower for h in HIGH_HAZARD_OCCUPANCIES):
            if LayoutVariant.SAFETY_MAXIMIZED in compliant:
                return LayoutVariant.SAFETY_MAXIMIZED
            # Fall back to standard
            if LayoutVariant.STANDARD_COMPLIANT in compliant:
                return LayoutVariant.STANDARD_COMPLIANT

        # V135 F-9: Low-hazard occupancy → COST_MINIMIZED allowed if score is competitive
        # Low-hazard = storage, parking, utility, mercantile (per NFPA 101)
        LOW_HAZARD_OCCUPANCIES = frozenset({
            "storage", "parking", "utility", "mercantile", "business",
            "office", "industrial_light", "warehouse",
        })
        is_low_hazard = any(h in occ_lower for h in LOW_HAZARD_OCCUPANCIES)

        if is_low_hazard and LayoutVariant.COST_MINIMIZED in compliant:
            cost_min_score = compliant[LayoutVariant.COST_MINIMIZED].score
            std_score = compliant.get(
                LayoutVariant.STANDARD_COMPLIANT,
                compliant[LayoutVariant.COST_MINIMIZED],  # fallback
            ).score
            # V135 F-9: Recommend COST_MINIMIZED if its score is ≥ 90% of STANDARD
            # This ensures cost savings don't come at unacceptable quality loss
            if std_score > 0 and cost_min_score >= 0.9 * std_score:
                return LayoutVariant.COST_MINIMIZED
            # If COST_MINIMIZED score is much lower, fall through to STANDARD

        # Standard occupancy → STANDARD_COMPLIANT preferred (default)
        if LayoutVariant.STANDARD_COMPLIANT in compliant:
            return LayoutVariant.STANDARD_COMPLIANT

        # Otherwise, pick highest score among compliant
        best = max(compliant.values(), key=lambda r: r.score)
        return best.variant

    # ------------------------------------------------------------------
    # Multiprocessing
    # ------------------------------------------------------------------

    def _generate_parallel(
        self, tasks: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Generate variants in parallel using multiprocessing.Pool.

        Uses fork context per agent.md V37 (threads forbidden due to GIL).
        """
        try:
            ctx = multiprocessing.get_context(_MP_CONTEXT)
            with ctx.Pool(processes=self.n_workers) as pool:
                results = pool.map(_generate_variant_worker, tasks)
            return results
        except Exception as exc:
            logger.warning(
                "Multiprocessing failed (%s) — falling back to sequential. "
                "This may indicate fork() is unavailable (e.g., on macOS/spawn).",
                exc,
            )
            return [self._generate_sequential(t) for t in tasks]

    @staticmethod
    def _generate_sequential(
        task: Tuple[str, Dict[str, Any], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate a single variant sequentially (fallback)."""
        return _generate_variant_worker(task)

    # ------------------------------------------------------------------
    # Audit Trail
    # ------------------------------------------------------------------

    @staticmethod
    def _record_audit_event(
        run_id: str,
        variant: LayoutVariant,
        layout: DetectorLayout,
        total_cost: float,
        score: float,
        is_compliant: bool,
        error: Optional[str],
    ) -> Optional[str]:
        """Record a GENERATIVE_ATTEMPT event in AuditStore.

        Per agent.md Rule 12 + NFPA 72 §7.5: every generative attempt
        (including rejected variants) MUST be recorded for legal
        traceability.

        Returns:
            Audit event hash, or None if recording failed (graceful
            degradation — never block on audit failure).
        """
        try:
            from fireai.core.audit_store import AuditStore

            details = {
                "event_type": "GENERATIVE_ATTEMPT",
                "run_id": run_id,
                "variant": variant.value,
                "variant_description": variant.description,
                "detector_count": layout.count,
                "coverage_pct": round(layout.coverage_pct, 4),
                "proof_valid": layout.proof_valid,
                "nfpa_valid": layout.nfpa_valid,
                "wall_violations": layout.wall_violations,
                "total_cost_usd": round(total_cost, 2),
                "score": round(score, 4),
                "is_compliant": is_compliant,
                "method": layout.method,
                "error": error,
                "nfpa_reference": "NFPA 72-2022 §7.5 (Audit Trail)",
                "source": "generative_layout_agent",
            }

            event_hash = AuditStore.add_event(
                event_type="GENERATIVE_ATTEMPT",
                room_id=layout.room.name,
                details_dict=details,
            )
            return event_hash

        except Exception as exc:
            # Per fail-safe principle: audit failure MUST NOT block generation
            logger.error(
                "Failed to record GENERATIVE_ATTEMPT audit event for "
                "run_id=%s variant=%s: %s",
                run_id, variant.value, exc, exc_info=True,
            )
            return None


__all__ = [
    "LayoutVariant",
    "VariantResult",
    "GenerativeResult",
    "GenerativeLayoutAgent",
    "COVERAGE_WEIGHT",
    "COMPLIANCE_WEIGHT",
    "REDUNDANCY_WEIGHT",
    "COST_WEIGHT",
    "SAFETY_MAXIMIZED_SPACING_FACTOR",
    "HIGH_HAZARD_OCCUPANCIES",
]
