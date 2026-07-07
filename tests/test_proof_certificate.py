"""
tests/test_proof_certificate.py
================================
Comprehensive test suite for fireai/core/spatial_engine/proof_certificate.py

SAFETY CRITICAL: The proof certificate provides mathematical proof that
detector coverage meets NFPA 72 requirements. A faulty certificate could
lead to areas of a building without adequate fire detection — a direct
life-safety hazard.

Key features tested:
  - δ-Conservative grid verification method
  - Hash computation and verification (tamper detection)
  - Seal and verify_hash lifecycle
  - JSON serialization/deserialization
  - ProofCertificateGenerator with various room configurations
  - Edge cases: zero detectors, empty rooms, high ceilings
"""

from __future__ import annotations

import json
import math

import pytest

from fireai.core.spatial_engine.density_optimizer import DETECTOR_RADIUS
from fireai.core.spatial_engine.proof_certificate import (
    ProofCertificate,
    ProofCertificateGenerator,
)

# ─────────────────────────────────────────────────────────────────────────────
# ProofCertificate Dataclass Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProofCertificate:
    """Test ProofCertificate dataclass, hash, seal, serialization."""

    def _make_certificate(self):
        return ProofCertificate(
            room_id="R-101",
            room_width_m=10.0,
            room_length_m=10.0,
            room_ceiling_height_m=3.0,
            room_area_sqm=100.0,
            n_detectors=3,
            detector_positions=[(2.5, 2.5), (7.5, 2.5), (5.0, 7.5)],
            detector_type="smoke",
            detector_radius_m=6.37,
            grid_step_m=0.20,
            effective_radius_m=6.23,
            delta_margin_m=0.14,
            n_grid_points=2601,
            n_covered=2601,
            n_uncovered=0,
            coverage_guaranteed=True,
            coverage_lower_bound_pct=100.0,
            uncovered_area_upper_bound_sqm=0.0,
            nfpa_compliant=True,
            wall_coverage_complete=True,
            spacing_compliant=True,
        )

    def test_creation(self):
        cert = self._make_certificate()
        assert cert.room_id == "R-101"
        assert cert.n_detectors == 3

    def test_compute_hash(self):
        cert = self._make_certificate()
        h = cert.compute_hash()
        assert len(h) == 64  # Full SHA-256 hex

    def test_compute_hash_deterministic(self):
        """Same certificate data → same hash."""
        cert1 = self._make_certificate()
        cert2 = self._make_certificate()
        assert cert1.compute_hash() == cert2.compute_hash()

    def test_compute_hash_changes_on_tamper(self):
        """Changing a field must produce a different hash."""
        cert1 = self._make_certificate()
        cert2 = self._make_certificate()
        cert2.room_id = "R-999"
        assert cert1.compute_hash() != cert2.compute_hash()

    def test_seal(self):
        """Seal should set hash and timestamp."""
        cert = self._make_certificate()
        assert cert.proof_hash == ""
        assert cert.timestamp == ""
        cert.seal()
        assert cert.proof_hash != ""
        assert len(cert.proof_hash) == 64
        assert cert.timestamp != ""

    def test_verify_hash_valid(self):
        cert = self._make_certificate()
        cert.seal()
        assert cert.verify_hash() is True

    def test_verify_hash_tampered(self):
        """Tampering with sealed certificate should fail verification."""
        cert = self._make_certificate()
        cert.seal()
        cert.n_detectors = 99  # Tamper!
        assert cert.verify_hash() is False

    def test_to_json(self):
        cert = self._make_certificate()
        cert.seal()
        json_str = cert.to_json()
        data = json.loads(json_str)
        assert data["room_id"] == "R-101"
        assert data["proof_hash"] == cert.proof_hash

    def test_from_json(self):
        cert = self._make_certificate()
        cert.seal()
        json_str = cert.to_json()
        restored = ProofCertificate.from_json(json_str)
        assert restored.room_id == cert.room_id
        assert restored.proof_hash == cert.proof_hash

    def test_round_trip_json(self):
        cert = self._make_certificate()
        cert.seal()
        json_str = cert.to_json()
        restored = ProofCertificate.from_json(json_str)
        assert restored.compute_hash() == cert.compute_hash()

    def test_default_values(self):
        cert = ProofCertificate(
            room_id="R",
            room_width_m=1,
            room_length_m=1,
            room_ceiling_height_m=1,
            room_area_sqm=1,
            n_detectors=0,
            detector_positions=[],
        )
        assert cert.proof_method == "delta_conservative_grid"
        assert cert.grid_step_m == 0.20  # NOSONAR — S1244: import retained for re-export / API surface
        assert cert.wall_min_m == 0.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert cert.fireai_version == "1.0.0"

    def test_warnings_default_empty(self):
        cert = ProofCertificate(
            room_id="R", room_width_m=1, room_length_m=1,
            room_ceiling_height_m=1, room_area_sqm=1,
            n_detectors=0, detector_positions=[],
        )
        assert cert.warnings == []


# ─────────────────────────────────────────────────────────────────────────────
# ProofCertificateGenerator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProofCertificateGenerator:
    """Test the generator that creates certificates via grid verification."""

    def test_default_parameters(self):
        gen = ProofCertificateGenerator()
        assert gen.delta == 0.20  # NOSONAR — S1244: import retained for re-export / API surface
        assert gen.R == DETECTOR_RADIUS
        assert gen.S == 9.1  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_parameters(self):
        gen = ProofCertificateGenerator(grid_step=0.10, coverage_radius=5.0, max_spacing=7.0)
        assert gen.delta == 0.10  # NOSONAR — S1244: import retained for re-export / API surface
        assert gen.R == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert gen.S == 7.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_delta_margin_calculation(self):
        gen = ProofCertificateGenerator(grid_step=0.20)
        expected = 0.20 * math.sqrt(2) / 2
        assert gen.delta_margin == pytest.approx(expected, abs=0.001)

    def test_effective_radius(self):
        """R_eff = R - delta_margin."""
        gen = ProofCertificateGenerator(grid_step=0.20, coverage_radius=6.37)
        expected = 6.37 - 0.20 * math.sqrt(2) / 2
        assert gen.R_eff == pytest.approx(expected, abs=0.001)

    def test_small_room_one_detector_full_coverage(self):
        """Small room with one well-placed detector should have full coverage."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-SMALL",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
        )
        assert cert.coverage_guaranteed is True
        assert cert.n_uncovered == 0
        assert cert.coverage_lower_bound_pct == 100.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert cert.nfpa_compliant is False  # not set to True in this call

    def test_large_room_few_detectors_uncovered(self):
        """Large room with too few detectors should have uncovered points."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-LARGE",
            width=30.0, length=30.0, ceiling_height=3.0,
            detectors=[(5, 5)],  # Only 1 detector for 30×30m room
        )
        assert cert.n_uncovered > 0
        assert cert.coverage_guaranteed is False
        assert cert.coverage_lower_bound_pct < 100.0

    def test_coverage_lower_bound_formula(self):
        """When uncovered: lower_bound = max(0, 100 * (1 - N_uncovered * δ² / A))."""
        gen = ProofCertificateGenerator(grid_step=0.20, coverage_radius=1.0)
        cert = gen.generate(
            room_id="R-TEST",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(0.5, 0.5)],  # Very small radius, will leave many uncovered
        )
        if cert.n_uncovered > 0:
            expected_upper = cert.n_uncovered * (0.20 ** 2)
            assert cert.uncovered_area_upper_bound_sqm == pytest.approx(expected_upper, abs=0.01)
            expected_bound = max(0.0, 100.0 * (1 - expected_upper / 100.0))
            assert cert.coverage_lower_bound_pct == pytest.approx(expected_bound, abs=0.01)

    def test_detector_positions_in_certificate(self):
        """Certificate should contain the exact detector positions."""
        gen = ProofCertificateGenerator()
        positions = [(2.5, 2.5), (7.5, 7.5)]
        cert = gen.generate(
            room_id="R-POS",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=positions,
        )
        assert len(cert.detector_positions) == 2
        assert cert.n_detectors == 2

    def test_room_dimensions_in_certificate(self):
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-DIM",
            width=8.0, length=12.0, ceiling_height=4.0,
            detectors=[(4, 6)],
        )
        assert cert.room_width_m == 8.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert cert.room_length_m == 12.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert cert.room_ceiling_height_m == 4.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert cert.room_area_sqm == 96.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_detector_type_propagated(self):
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-HEAT",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
            detector_type="heat",
        )
        assert cert.detector_type == "heat"

    def test_nfpa_compliant_flag(self):
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-NFPA",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
            nfpa_compliant=True,
        )
        assert cert.nfpa_compliant is True

    def test_wall_coverage_complete_flag(self):
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-WALL",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
            wall_coverage_complete=True,
        )
        assert cert.wall_coverage_complete is True

    def test_spacing_compliant_flag(self):
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-SPACE",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
            spacing_compliant=True,
        )
        assert cert.spacing_compliant is True

    def test_warnings_uncovered(self):
        """Uncovered points should generate a warning."""
        gen = ProofCertificateGenerator(grid_step=0.20, coverage_radius=1.0)
        cert = gen.generate(
            room_id="R-WARN",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(0.5, 0.5)],
        )
        if cert.n_uncovered > 0:
            assert any("uncovered" in w.lower() for w in cert.warnings)

    def test_warnings_low_coverage(self):
        """Coverage below 99.9% should generate a warning."""
        gen = ProofCertificateGenerator(grid_step=0.20, coverage_radius=1.0)
        cert = gen.generate(
            room_id="R-LOW",
            width=20.0, length=20.0, ceiling_height=3.0,
            detectors=[(0.5, 0.5)],
        )
        if cert.coverage_lower_bound_pct < 99.9:
            assert any("99.9" in w for w in cert.warnings)

    def test_warnings_high_ceiling(self):
        """Ceiling height > 9.1m should generate a warning."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-HIGH",
            width=5.0, length=5.0, ceiling_height=10.0,
            detectors=[(2.5, 2.5)],
        )
        assert any("9.1m" in w for w in cert.warnings)

    def test_proof_method_is_delta_conservative(self):
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-PM",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
        )
        assert cert.proof_method == "delta_conservative_grid"

    def test_grid_step_propagated(self):
        gen = ProofCertificateGenerator(grid_step=0.10)
        cert = gen.generate(
            room_id="R-GS",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
        )
        assert cert.grid_step_m == 0.10  # NOSONAR — S1244: import retained for re-export / API surface

    def test_zero_detectors(self):
        """Room with no detectors should have all points uncovered."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-NODET",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[],
        )
        assert cert.n_uncovered == cert.n_grid_points
        assert cert.n_covered == 0
        assert cert.coverage_guaranteed is False

    def test_detector_at_room_corner(self):
        """Detector in corner should cover less area but not crash."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-CORNER",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(0, 0)],
        )
        assert cert.n_grid_points > 0
        assert cert.n_covered > 0

    def test_seal_and_verify(self):
        """Full lifecycle: generate → seal → verify."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-LIFE",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
            nfpa_compliant=True,
        )
        cert.seal()
        assert cert.verify_hash() is True
        assert cert.proof_hash != ""
        assert cert.timestamp != ""

    def test_json_round_trip(self):
        """Certificate survives JSON round-trip."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-JSON",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
        )
        cert.seal()
        json_str = cert.to_json()
        restored = ProofCertificate.from_json(json_str)
        assert restored.room_id == cert.room_id
        assert restored.proof_hash == cert.proof_hash
        assert restored.verify_hash() is True


# ─────────────────────────────────────────────────────────────────────────────
# Mathematical Correctness Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMathematicalCorrectness:
    """Verify the mathematical foundation of the proof method."""

    def test_grid_point_count_for_square_room(self):
        """Grid points for a square room with step δ."""
        gen = ProofCertificateGenerator(grid_step=1.0)
        cert = gen.generate(
            room_id="R-MATH",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(5, 5)],
        )
        # For 10×10 room with step=1.0: xs = 0,1,2,...,10 (11) × ys = 0,1,...,10 (11)
        # = 121 grid points
        assert cert.n_grid_points == 121

    def test_coverage_guaranteed_means_all_covered(self):
        """coverage_guaranteed=True ↔ n_uncovered=0."""
        gen = ProofCertificateGenerator()
        cert = gen.generate(
            room_id="R-CG",
            width=5.0, length=5.0, ceiling_height=3.0,
            detectors=[(2.5, 2.5)],
        )
        if cert.n_uncovered == 0:
            assert cert.coverage_guaranteed is True
        else:
            assert cert.coverage_guaranteed is False

    def test_uncovered_area_uses_square_cell(self):
        """V15 FIX: uncovered area uses δ² (square cell), not π(δ/2)²."""
        gen = ProofCertificateGenerator(grid_step=0.20, coverage_radius=1.0)
        cert = gen.generate(
            room_id="R-V15",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(0.5, 0.5)],
        )
        if cert.n_uncovered > 0:
            # Square cell: uncovered_area = n_uncovered * δ²
            expected = cert.n_uncovered * (0.20 ** 2)
            assert cert.uncovered_area_upper_bound_sqm == pytest.approx(expected, abs=0.01)

    def test_effective_radius_less_than_coverage_radius(self):
        """R_eff = R - δ√2/2 < R always (for δ > 0)."""
        gen = ProofCertificateGenerator()
        assert gen.R_eff < gen.R

    def test_multiple_detectors_cover_larger_area(self):
        """More detectors should cover more grid points."""
        gen = ProofCertificateGenerator(coverage_radius=3.0)
        cert1 = gen.generate(
            room_id="R-1DET",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(5, 5)],
        )
        cert2 = gen.generate(
            room_id="R-2DET",
            width=10.0, length=10.0, ceiling_height=3.0,
            detectors=[(3, 3), (7, 7)],
        )
        assert cert2.n_covered >= cert1.n_covered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
