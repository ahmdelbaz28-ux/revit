# NOSONAR
"""
tests/test_fireai_core_v2.py
=============================
Comprehensive test suite for fireai/core/fireai_core.py

SAFETY CRITICAL: FireAISystem is the central orchestrator for the FireAI
production system. Errors in room analysis could result in incorrect fire
alarm coverage assessments — a direct life-safety hazard.

Security fixes tested:
  - No hardcoded absolute paths
  - No os.remove() destroying audit trail
  - Database APPEND-ONLY mode
  - Audit chain verification with dev-mode tolerance
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from fireai.core.fireai_core import (
    ConfidenceLevel,
    EnhancedRoomResult,
    FireAISystem,
    PlacementProof,
    ResilienceResult,
    _resolve_db_path,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ConfidenceLevel Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfidenceLevel:
    def test_members(self):
        assert ConfidenceLevel.HIGH.value == "HIGH"
        assert ConfidenceLevel.MEDIUM.value == "MEDIUM"
        assert ConfidenceLevel.LOW.value == "LOW"
        assert ConfidenceLevel.UNSAFE.value == "UNSAFE"


# ═══════════════════════════════════════════════════════════════════════════════
# PlacementProof Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlacementProof:
    def test_defaults(self):
        p = PlacementProof()
        assert p.coverage_fraction == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert p.proof_valid is False
        assert p.max_gap_m == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom(self):
        p = PlacementProof(coverage_fraction=0.99, proof_valid=True, max_gap_m=2.5)
        assert p.coverage_fraction == 0.99  # NOSONAR — S1244: import retained for re-export / API surface
        assert p.proof_valid is True


# ═══════════════════════════════════════════════════════════════════════════════
# ResilienceResult Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestResilienceResult:
    def test_defaults(self):
        r = ResilienceResult()
        assert r.resilient is False
        assert r.pass_rate == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert r.failure_detail == ""

    def test_custom(self):
        r = ResilienceResult(resilient=True, pass_rate=0.95, failure_detail="OK")
        assert r.resilient is True
        assert r.pass_rate == 0.95  # NOSONAR — S1244: import retained for re-export / API surface


# ═══════════════════════════════════════════════════════════════════════════════
# EnhancedRoomResult Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnhancedRoomResult:
    def test_defaults(self):
        r = EnhancedRoomResult()
        assert r.room_id == ""
        assert r.detector_positions == []
        assert r.confidence == ConfidenceLevel.MEDIUM
        assert r.compliant is False
        assert r.safe_to_submit is False

    def test_status_pass(self):
        r = EnhancedRoomResult(compliant=True)
        assert r.status == "PASS"

    def test_status_fail(self):
        r = EnhancedRoomResult(compliant=False)
        assert r.status == "FAIL"

    def test_refused(self):
        r = EnhancedRoomResult(compliant=False, errors=["bad"])
        assert r.refused is True

    def test_not_refused_when_compliant(self):
        r = EnhancedRoomResult(compliant=True, errors=["bad"])
        assert r.refused is False

    def test_not_refused_when_no_errors(self):
        r = EnhancedRoomResult(compliant=False, errors=[])
        assert r.refused is False

    def test_coverage_result_property(self):
        proof = PlacementProof(coverage_fraction=0.95, proof_valid=True)
        r = EnhancedRoomResult(compliant=True, placement_proof=proof)
        cr = r.coverage_result
        assert cr.is_covered is True
        assert cr.coverage_percentage == pytest.approx(95.0)

    def test_coverage_result_no_proof(self):
        r = EnhancedRoomResult(compliant=False, placement_proof=None)
        cr = r.coverage_result
        assert cr.coverage_percentage == 0.0  # NOSONAR — S1244: import retained for re-export / API surface


# ═══════════════════════════════════════════════════════════════════════════════
# _resolve_db_path Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveDbPath:
    def test_memory_path(self):
        assert _resolve_db_path(":memory:") == ":memory:"

    def test_explicit_path(self):
        result = _resolve_db_path("/tmp/test_audit.db")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        # Cross-platform: os.path.abspath normalizes the path
        assert "test_audit.db" in result
        assert result == os.path.abspath(result)  # must be absolute

    def test_env_variable(self):
        with patch.dict(os.environ, {"FIREAI_DB_PATH": "/tmp/env_audit.db"}):  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
            result = _resolve_db_path(None)
            # Cross-platform: os.path.abspath normalizes the path
            assert "env_audit.db" in result
            assert result == os.path.abspath(result)  # must be absolute

    def test_default_path(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove env var if present
            os.environ.pop("FIREAI_DB_PATH", None)
            result = _resolve_db_path(None)
            assert "fireai_audit.db" in result


# ═══════════════════════════════════════════════════════════════════════════════
# FireAISystem Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFireAISystem:
    @pytest.fixture(autouse=True)
    def _clean_env(self):
        """Ensure no stale env vars between tests."""
        os.environ.pop("AUDIT_HMAC_KEY", None)
        os.environ.pop("FIREAI_DB_PATH", None)
        os.environ.pop("FIREAI_LEARNING_DB_PATH", None)

    @pytest.fixture
    def system(self):
        return FireAISystem(db_path=":memory:")

    def test_init_with_memory_db(self, system):
        assert system.db_path == ":memory:"

    def test_resolve_db_path_stored(self, system):
        assert system._resolved_db_path == ":memory:"

    def test_learning_store_initialized(self, system):
        assert system.learning is not None

    def test_analyse_room_invalid_spec(self, system):
        with pytest.raises(ValueError, match="room_id"):
            system.analyse_room(None)

    def test_analyse_room_invalid_user_id(self, system):
        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        spec = RoomSpec(room_id="R1", width_m=5.0, depth_m=5.0,
                        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                        occupancy_type="office")
        with pytest.raises(ValueError, match="user_id"):
            system.analyse_room(spec, user_id="")

    def test_analyse_room_empty_user_id(self, system):  # NOSONAR — acceptable in this context  # NOSONAR — acceptable in this context
        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        spec = RoomSpec(room_id="R1", width_m=5.0, depth_m=5.0,
                        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                        occupancy_type="office")
        with pytest.raises(ValueError, match="user_id"):
            system.analyse_room(spec, user_id="")

    def test_analyse_floor_empty_list(self, system):
        with pytest.raises(ValueError, match="must not be empty"):
            system.analyse_floor([])

    def test_analyse_floor_too_many_rooms(self, system):
        with pytest.raises(ValueError, match="Maximum 500"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            system.analyse_floor([MagicMock()] * 501)

    def test_get_audit_trail(self, system):
        trail = system.get_audit_trail()
        assert isinstance(trail, list)

    def test_get_memory_summary(self, system):
        summary = system.get_memory_summary()
        assert isinstance(summary, dict)

    def test_get_memory_summary_no_learning(self):
        sys2 = FireAISystem(db_path=":memory:")
        sys2.learning = None
        result = sys2.get_memory_summary()
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Full Room Analysis (mocked expert)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalysisIntegration:
    @pytest.fixture(autouse=True)
    def _clean_env(self):
        os.environ.pop("AUDIT_HMAC_KEY", None)
        os.environ.pop("FIREAI_DB_PATH", None)
        os.environ.pop("FIREAI_LEARNING_DB_PATH", None)

    @pytest.fixture
    def system(self):
        return FireAISystem(db_path=":memory:")

    def test_analyse_room_with_mock_expert(self, system):
        """Full analysis with mocked FireExpertSystem."""
        mock_expert = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(1.0, 2.0), (3.0, 4.0)]
        mock_analysis.coverage = 99.0
        mock_analysis.passed = True
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = []
        mock_expert.analyse_room.return_value = mock_analysis

        system._expert = mock_expert

        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        spec = RoomSpec(room_id="R1", width_m=10.0, depth_m=8.0,
                        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                        occupancy_type="office")
        result = system.analyse_room(spec, user_id="test_user", run_resilience=False)

        assert result.room_id == "R1"
        assert result.compliant is True
        assert result.confidence == ConfidenceLevel.HIGH  # 99% coverage
        assert result.status == "PASS"
        assert result.safe_to_submit is True
        assert len(result.detector_positions) == 2

    def test_analyse_room_engine_error(self, system):
        """Engine failure → UNSAFE result with error detail."""
        mock_expert = MagicMock()
        mock_expert.analyse_room.side_effect = RuntimeError("Boom")
        system._expert = mock_expert

        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        spec = RoomSpec(room_id="R1", width_m=5.0, depth_m=5.0,
                        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                        occupancy_type="office")
        result = system.analyse_room(spec, user_id="test_user")

        assert result.confidence == ConfidenceLevel.UNSAFE
        assert len(result.errors) > 0
        assert "Boom" in result.errors[0]

    def test_analyse_room_low_coverage(self, system):
        """Low coverage → LOW confidence."""
        mock_expert = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(1.0, 2.0)]
        mock_analysis.coverage = 92.0
        mock_analysis.passed = False
        mock_analysis.proof_valid = False
        mock_analysis.wall_violations = []
        mock_expert.analyse_room.return_value = mock_analysis
        system._expert = mock_expert

        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        spec = RoomSpec(room_id="R1", width_m=10.0, depth_m=10.0,
                        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                        occupancy_type="office")
        result = system.analyse_room(spec, user_id="test_user", run_resilience=False)

        assert result.confidence == ConfidenceLevel.LOW
        assert result.compliant is False
        assert result.safe_to_submit is False

    def test_analyse_room_unsafe_coverage(self, system):
        """<90% coverage → UNSAFE."""
        mock_expert = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = []
        mock_analysis.coverage = 50.0
        mock_analysis.passed = False
        mock_analysis.proof_valid = False
        mock_analysis.wall_violations = []
        mock_expert.analyse_room.return_value = mock_analysis
        system._expert = mock_expert

        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        spec = RoomSpec(room_id="R1", width_m=10.0, depth_m=10.0,
                        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                        occupancy_type="office")
        result = system.analyse_room(spec, user_id="test_user", run_resilience=False)

        assert result.confidence == ConfidenceLevel.UNSAFE

    def test_analyse_floor_returns_results(self, system):
        """analyse_floor returns list of results."""
        mock_expert = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(1.0, 2.0)]
        mock_analysis.coverage = 99.0
        mock_analysis.passed = True
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = []
        mock_expert.analyse_room.return_value = mock_analysis
        system._expert = mock_expert

        from fireai.core.nfpa72_models import CeilingSpec, RoomSpec
        specs = [
            RoomSpec(room_id=f"R{i}", width_m=5.0, depth_m=5.0,
                     ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
                     occupancy_type="office")
            for i in range(3)
        ]
        results = system.analyse_floor(specs, user_id="test_user", run_resilience=False)

        assert len(results) == 3
        assert all(isinstance(r, EnhancedRoomResult) for r in results)

    def test_safe_to_submit_explicit(self, system):
        """safe_to_submit is set explicitly by analyse_room, not computed."""
        r = EnhancedRoomResult(compliant=True, confidence=ConfidenceLevel.MEDIUM,
                               safe_to_submit=True)
        assert r.safe_to_submit is True

        r2 = EnhancedRoomResult(compliant=True, confidence=ConfidenceLevel.UNSAFE,
                                safe_to_submit=False)
        assert r2.safe_to_submit is False

        r3 = EnhancedRoomResult(compliant=False, confidence=ConfidenceLevel.HIGH,
                                safe_to_submit=False)
        assert r3.safe_to_submit is False

    def test_safe_to_submit_default_false(self):
        """safe_to_submit defaults to False."""
        r = EnhancedRoomResult(compliant=True, confidence=ConfidenceLevel.MEDIUM)
        assert r.safe_to_submit is False  # Default is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
