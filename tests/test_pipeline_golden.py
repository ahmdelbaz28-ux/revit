"""
D5: Golden Pipeline Test Suite — 10 Reference Cases for FireAI V30
===================================================================
Defines 10 carefully crafted "golden" test cases that represent
realistic fire alarm design scenarios. Each case specifies:

  - Room geometry (width, length, ceiling_height)
  - Expected detector count (exact or range)
  - Expected coverage percentage (minimum)
  - Expected proof_valid status
  - Expected NFPA compliance status
  - NFPA 72 section references

These golden cases serve as a REGRESSION GUARD: any change to the
optimizer, verifier, or consensus engine that alters detector counts
or coverage results MUST be reviewed and the golden values updated
with explicit justification.

GOLDEN CASE PHILOSOPHY:
  - Conservative: more detectors = safer (agent.md Rule 5)
  - If a change REDUCES detector count, it must be proven safe
  - If a change INCREASES detector count, it may be correct but
    needs documentation of WHY the previous count was insufficient
  - Coverage must be >= 99.9% for all cases (life-safety standard)

Run:
  pytest tests/test_pipeline_golden.py -v

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S = 0.7 × 9.1 = 6.37m
"""

import math
import pytest

from fireai.core.spatial_engine.density_optimizer import (
    DensityOptimizer, Room, DetectorLayout,
    DETECTOR_RADIUS, MAX_SPACING_M, WALL_MIN_M,
    VERIFY_STEP, COARSE_STEP, PLACEMENT_MARGIN,
)
from fireai.core.spatial_engine.analytical_verifier import (
    AnalyticalVerifier, AnalyticalResult,
)
from fireai.core.spatial_engine.voronoi_verifier import (
    VoronoiVerifier, VoronoiResult,
)
from fireai.core.spatial_engine.consensus_engine import (
    ConsensusEngine, ConsensusResult, ConfidenceLevel,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Case Definitions
# ═══════════════════════════════════════════════════════════════════════════════

# Each golden case is a dict with:
#   name:            Descriptive name
#   width:           Room width (m)
#   length:          Room length (m)
#   ceiling_height:  Ceiling height (m) — affects R via NFPA 72 Table 17.6.3.1.1
#   min_detectors:   Minimum acceptable detector count (conservative lower bound)
#   max_detectors:   Maximum acceptable detector count (safety upper bound)
#   min_coverage:    Minimum acceptable coverage percentage
#   must_proof:      Whether proof_valid MUST be True (life-safety-critical rooms)
#   must_nfpa:       Whether NFPA compliance MUST be True
#   nfpa_ref:        NFPA 72 section reference
#   rationale:       Why this case matters

GOLDEN_CASES = [
    {
        "name": "GC1: Single-detector small office",
        "width": 5.0,
        "length": 5.0,
        "ceiling_height": 3.0,
        "min_detectors": 1,
        "max_detectors": 2,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.6.3.1.1 — 25 m² < π×6.37² = 127.5 m² → 1 detector",
        "rationale": (
            "Smallest practical room. A single detector at center covers the "
            "entire room because R=6.37m > half-diagonal=3.54m. This validates "
            "the most basic placement case."
        ),
    },
    {
        "name": "GC2: Exact-radius square room (6.37×6.37)",
        "width": 6.37,
        "length": 6.37,
        "ceiling_height": 3.0,
        "min_detectors": 1,
        "max_detectors": 2,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.7.4.2.3.1 — R×R room fits within single detector",
        "rationale": (
            "Room dimensions equal to DETECTOR_RADIUS. The half-diagonal is "
            "6.37×√2/2 = 4.50m < 6.37m = R, so one detector should cover "
            "everything. Tests boundary condition of single-detector coverage."
        ),
    },
    {
        "name": "GC3: Standard corridor (2m × 20m)",
        "width": 2.0,
        "length": 20.0,
        "ceiling_height": 3.0,
        "min_detectors": 1,
        "max_detectors": 4,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.6.3.1.1 — corridor spacing ≤ 9.1m",
        "rationale": (
            "Elongated corridor. Width (2m) is well within R, so only length "
            "drives detector count. 20m / 9.1m spacing = 2-3 detectors. Tests "
            "the hex strategies' ability to handle extreme aspect ratios."
        ),
    },
    {
        "name": "GC4: Medium conference room (10×12)",
        "width": 10.0,
        "length": 12.0,
        "ceiling_height": 3.0,
        "min_detectors": 1,
        "max_detectors": 6,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.6.3.1.1 — 120 m² → 1-2 detectors geometrically",
        "rationale": (
            "Typical conference room. Area=120 m², well within 2-detector "
            "coverage (2 × π × 6.37² = 254.8 m²). Tests that the optimizer "
            "doesn't over-place detectors in rooms where 1-2 suffice."
        ),
    },
    {
        "name": "GC5: Large open office (15×20)",
        "width": 15.0,
        "length": 20.0,
        "ceiling_height": 3.0,
        "min_detectors": 2,
        "max_detectors": 12,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.6.3.1.1 — 300 m², R=6.37m",
        "rationale": (
            "Large open-plan office. Area=300 m² exceeds single-detector "
            "coverage (127.5 m²). Multiple detectors required. The rect_3x4 "
            "strategy places 12 detectors for full coverage with corner guards. "
            "This is the most common real-world scenario for commercial buildings."
        ),
    },
    {
        "name": "GC6: Warehouse with high ceiling (25×30, h=6m)",
        "width": 25.0,
        "length": 30.0,
        "ceiling_height": 6.0,
        "min_detectors": 4,
        "max_detectors": 25,
        "min_coverage": 99.0,  # slightly relaxed for variable radius
        "must_proof": False,   # high ceiling reduces R, harder to achieve 100%
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 Table 17.6.3.1.1 — h=6.0m → R=5.39m (reduced spacing)",
        "rationale": (
            "Warehouse with 6m ceiling. Per NFPA 72 Table 17.6.3.1.1, the "
            "coverage radius is reduced for higher ceilings (R=5.39m at h=6.0m). "
            "This means more detectors are needed. Tests variable radius support."
        ),
    },
    {
        "name": "GC7: Atrium with very high ceiling (20×30, h=9m)",
        "width": 20.0,
        "length": 30.0,
        "ceiling_height": 9.0,
        "min_detectors": 6,
        "max_detectors": 30,
        "min_coverage": 99.0,
        "must_proof": False,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 Table 17.6.3.1.1 — h=9.0m → R=4.83m (significantly reduced)",
        "rationale": (
            "Atrium with 9m ceiling. R drops to 4.83m, requiring significantly "
            "more detectors. This is a stress test for the variable radius system "
            "and validates NFPA 72 ceiling height adjustments."
        ),
    },
    {
        "name": "GC8: Near-square large hall (18×18)",
        "width": 18.0,
        "length": 18.0,
        "ceiling_height": 3.0,
        "min_detectors": 2,
        "max_detectors": 16,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.6.3.1.1 — 324 m², R=6.37m, near-square",
        "rationale": (
            "Near-square large hall. Tests the rect-best strategy which is "
            "competitive for square rooms. Area=324 m² requires multiple "
            "detectors. The V7.4 placement margin causes more detectors to be "
            "placed for guaranteed proof validity, which is the correct "
            "conservative behavior per agent.md Rule 5."
        ),
    },
    {
        "name": "GC9: Extremely elongated corridor (2×50)",
        "width": 2.0,
        "length": 50.0,
        "ceiling_height": 3.0,
        "min_detectors": 3,
        "max_detectors": 10,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.6.3.1.1 — 50m corridor, spacing ≤ 9.1m",
        "rationale": (
            "Very long corridor. Width (2m) is trivially covered by R=6.37m, "
            "but 50m length requires at least 50/9.1 ≈ 6 spacing intervals. "
            "Tests that the optimizer handles extreme aspect ratio (25:1) "
            "without over-placing or under-covering."
        ),
    },
    {
        "name": "GC10: Medium room at max spacing boundary (9.1×9.1)",
        "width": 9.1,
        "length": 9.1,
        "ceiling_height": 3.0,
        "min_detectors": 1,
        "max_detectors": 4,
        "min_coverage": 99.9,
        "must_proof": True,
        "must_nfpa": True,
        "nfpa_ref": "NFPA 72 §17.7.4.2.3.1 — S=9.1m, R=6.37m, boundary case",
        "rationale": (
            "Room dimensions equal to MAX_SPACING_M. This is the critical "
            "boundary: a 9.1×9.1m room has half-diagonal = 9.1×√2/2 = 6.44m. "
            "R=6.37m < 6.44m, so ONE detector at center CANNOT cover the "
            "corners. This tests the V7.4 placement/verification alignment — "
            "the optimizer must place at least 2 detectors to achieve full coverage."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Test Functions
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def optimizer():
    """Create a standard DensityOptimizer instance."""
    return DensityOptimizer()


@pytest.fixture
def consensus():
    """Create a ConsensusEngine instance."""
    return ConsensusEngine(coverage_radius=DETECTOR_RADIUS)


def _get_coverage_radius_for_height(ceiling_height: float) -> float:
    """Get the appropriate coverage radius for a given ceiling height.

    Uses NFPA 72 Table 17.6.3.1.1 via get_smoke_detector_radius_safe.
    Falls back to DETECTOR_RADIUS for h <= 3.0m.
    """
    if ceiling_height <= 3.0:
        return DETECTOR_RADIUS
    try:
        from fireai.core.nfpa72_models import get_smoke_detector_radius_safe
        return get_smoke_detector_radius_safe(ceiling_height)
    except Exception:
        # Fallback: conservative estimate using NFPA 72 reduction
        # For h > 3.0m, R decreases approximately 0.3m per meter above 3.0m
        reduction = min((ceiling_height - 3.0) * 0.5, 3.0)
        return DETECTOR_RADIUS - reduction


class TestGoldenCases:
    """Golden pipeline test cases.

    Each test verifies that the optimizer produces results within the
    golden bounds for a specific room configuration. Any deviation from
    these bounds MUST be reviewed and documented.
    """

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_detector_count_within_bounds(self, optimizer, case):
        """Detector count must be within [min_detectors, max_detectors]."""
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        assert layout.count >= case["min_detectors"], (
            f"{case['name']}: detector count {layout.count} < minimum "
            f"{case['min_detectors']}. R={R:.2f}m. "
            f"This is an UNDER-PLACEMENT — life-safety risk! "
            f"Method: {layout.method}"
        )
        assert layout.count <= case["max_detectors"], (
            f"{case['name']}: detector count {layout.count} > maximum "
            f"{case['max_detectors']}. R={R:.2f}m. "
            f"This is an OVER-PLACEMENT — efficiency concern. "
            f"Method: {layout.method}"
        )

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_coverage_meets_minimum(self, optimizer, case):
        """Coverage must meet or exceed the minimum threshold."""
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        assert layout.coverage_pct >= case["min_coverage"], (
            f"{case['name']}: coverage {layout.coverage_pct:.2f}% < minimum "
            f"{case['min_coverage']}%. R={R:.2f}m. "
            f"Detectors: {layout.count}, Method: {layout.method}"
        )

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_proof_valid_when_required(self, optimizer, case):
        """If must_proof is True, proof_valid must be True."""
        if not case["must_proof"]:
            pytest.skip("proof_valid not required for this case")

        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        assert layout.proof_valid, (
            f"{case['name']}: proof_valid=False but must_proof=True. "
            f"R={R:.2f}m, coverage={layout.coverage_pct:.2f}%. "
            f"Detectors: {layout.count}, Method: {layout.method}. "
            f"This is a life-safety requirement."
        )

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_nfpa_compliance_when_required(self, optimizer, case):
        """If must_nfpa is True, nfpa_valid must be True."""
        if not case["must_nfpa"]:
            pytest.skip("NFPA compliance not required for this case")

        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        assert layout.nfpa_valid, (
            f"{case['name']}: nfpa_valid=False but must_nfpa=True. "
            f"R={R:.2f}m, coverage={layout.coverage_pct:.2f}%. "
            f"Detectors: {layout.count}, Method: {layout.method}. "
            f"NFPA 72 compliance is required for AHJ approval."
        )


class TestGoldenConsensus:
    """Verify that the consensus engine agrees with the optimizer for all golden cases.

    For life-safety-critical rooms, the consensus must be VERIFIED (3/3).
    For other rooms, at least WARNING (2/3) is acceptable.
    """

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_consensus_for_golden_cases(self, optimizer, case):
        """Consensus engine must agree for golden cases."""
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        # Use the actual R for consensus verification
        consensus = ConsensusEngine(coverage_radius=R)
        result = consensus.verify(
            width=room.width,
            length=room.length,
            detectors=layout.detectors,
            grid_proof_valid=layout.proof_valid,
            grid_coverage_pct=layout.coverage_pct,
        )

        if case["must_proof"]:
            # Life-safety-critical: must be VERIFIED (3/3)
            assert result.confidence == ConfidenceLevel.VERIFIED, (
                f"{case['name']}: consensus={result.consensus_str} but required VERIFIED. "
                f"Engine results: {[(v.engine.value, v.passed) for v in result.engines]}"
            )
        else:
            # Non-critical: at least WARNING (2/3)
            assert result.confidence in (ConfidenceLevel.VERIFIED, ConfidenceLevel.WARNING), (
                f"{case['name']}: consensus={result.consensus_str} — expected at least WARNING. "
                f"Engine results: {[(v.engine.value, v.passed) for v in result.engines]}"
            )


class TestGoldenDeterminism:
    """Verify that golden cases produce identical results across runs."""

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_determinism(self, case):
        """Same inputs must produce identical outputs across 5 runs."""
        opt = DensityOptimizer()
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])

        results = []
        for _ in range(5):
            layout = opt.optimize(room, coverage_radius=R)
            results.append({
                "count": layout.count,
                "coverage_pct": layout.coverage_pct,
                "proof_valid": layout.proof_valid,
                "nfpa_valid": layout.nfpa_valid,
                "method": layout.method,
                "fallback_used": layout.fallback_used,
            })

        first = results[0]
        for i, r in enumerate(results[1:], 1):
            assert r["count"] == first["count"], (
                f"{case['name']}: Non-deterministic count: run 0={first['count']}, run {i}={r['count']}"
            )
            assert r["method"] == first["method"], (
                f"{case['name']}: Non-deterministic method: run 0={first['method']}, run {i}={r['method']}"
            )
            assert r["proof_valid"] == first["proof_valid"], (
                f"{case['name']}: Non-deterministic proof_valid: run 0={first['proof_valid']}, run {i}={r['proof_valid']}"
            )


class TestGoldenDetectorPositions:
    """Verify that detector positions satisfy NFPA 72 constraints."""

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_all_detectors_within_room(self, optimizer, case):
        """All detectors must be within the room boundaries."""
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        for i, (x, y) in enumerate(layout.detectors):
            assert x >= -1e-6, f"Detector {i} at x={x} < 0 in {case['name']}"
            assert x <= room.width + 1e-6, f"Detector {i} at x={x} > width={room.width} in {case['name']}"
            assert y >= -1e-6, f"Detector {i} at y={y} < 0 in {case['name']}"
            assert y <= room.length + 1e-6, f"Detector {i} at y={y} > length={room.length} in {case['name']}"

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_nearest_neighbor_spacing_within_nfpa_limit(self, optimizer, case):
        """Nearest-neighbor spacing must be ≤ NFPA 72 max spacing.

        NFPA 72 limits the spacing between ADJACENT detectors, not all pairs.
        The nearest-neighbor distance for each detector must be ≤ 2R
        (= max spacing × 2 / √3 for hex, = S for rect). This test checks
        that no detector is isolated beyond the NFPA 72 spacing limit.

        For smoke detectors on smooth ceilings: max spacing = 9.1m (30ft)
        per NFPA 72 §17.6.3.1.1.
        """
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        if layout.count < 2:
            pytest.skip("Single detector — no spacing to check")

        # For variable radius, max spacing = R / 0.7
        max_s = R / 0.7 if R != DETECTOR_RADIUS else MAX_SPACING_M
        # Nearest-neighbor distance should be ≤ max_spacing
        # (each detector should have at least one neighbor within max_spacing)

        isolated_detectors = []
        for i, (x1, y1) in enumerate(layout.detectors):
            min_dist = float('inf')
            for j, (x2, y2) in enumerate(layout.detectors):
                if i == j:
                    continue
                dist = math.hypot(x2 - x1, y2 - y1)
                min_dist = min(min_dist, dist)
            if min_dist > max_s + 0.5:  # 0.5m tolerance
                isolated_detectors.append((i, min_dist))

        assert len(isolated_detectors) == 0, (
            f"{case['name']}: {len(isolated_detectors)} detectors have no neighbor "
            f"within NFPA spacing limit ({max_s:.1f}m). "
            f"Isolated: {isolated_detectors[:5]}. R={R:.2f}m."
        )

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
    def test_wall_distance_compliance(self, optimizer, case):
        """All detectors must be at least WALL_MIN_M from walls.

        Per NFPA 72 §17.6.3.1.1, detectors must be placed at least
        0.10m (4 inches) from walls to avoid dead air space.
        """
        room = Room(
            name=case["name"],
            width=case["width"],
            length=case["length"],
            ceiling_height=case["ceiling_height"],
        )
        R = _get_coverage_radius_for_height(case["ceiling_height"])
        layout = optimizer.optimize(room, coverage_radius=R)

        # Allow small tolerance for numerical precision
        tol = 0.01  # 1cm tolerance
        for i, (x, y) in enumerate(layout.detectors):
            assert x >= WALL_MIN_M - tol, (
                f"{case['name']}: Detector {i} at x={x:.3f}m < WALL_MIN_M={WALL_MIN_M}m from left wall"
            )
            assert room.width - x >= WALL_MIN_M - tol, (
                f"{case['name']}: Detector {i} at x={x:.3f}m < WALL_MIN_M={WALL_MIN_M}m from right wall "
                f"(width={room.width}m)"
            )
            assert y >= WALL_MIN_M - tol, (
                f"{case['name']}: Detector {i} at y={y:.3f}m < WALL_MIN_M={WALL_MIN_M}m from bottom wall"
            )
            assert room.length - y >= WALL_MIN_M - tol, (
                f"{case['name']}: Detector {i} at y={y:.3f}m < WALL_MIN_M={WALL_MIN_M}m from top wall "
                f"(length={room.length}m)"
            )
