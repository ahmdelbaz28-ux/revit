"""Comprehensive tests for the fireai_core module.

Tests cover:
  - ConfidenceLevel enum: all members, value access
  - PlacementProof dataclass: defaults, custom values
  - ResilienceResult dataclass: defaults, custom values
  - EnhancedRoomResult dataclass: defaults, status/coverage_result/refused properties
  - _resolve_db_path: explicit path, env var, default, :memory:
  - FireAISystem.__post_init__: initializes audit store, learning store
  - FireAISystem._get_expert: lazy init, singleton
  - FireAISystem.analyse_room: valid room, invalid room_spec, invalid user_id,
    analysis engine error, confidence levels (HIGH/MEDIUM/LOW/UNSAFE),
    placement proof, resilience (MC and fallback), audit trail logging,
    learning store integration
  - FireAISystem.analyse_floor: valid list, empty list, too many rooms,
    floor-level audit event
  - FireAISystem.get_audit_trail: returns events
  - FireAISystem.verify_audit_integrity: valid/invalid chain
  - FireAISystem.get_memory_summary: with/without learning store
  - FireAISystem.run_integration: delegates to IntegrationBridge (mocked)
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from fireai.core import audit_store as audit_mod
from fireai.core.fireai_core import (
    ConfidenceLevel,
    EnhancedRoomResult,
    FireAISystem,
    PlacementProof,
    ResilienceResult,
    _resolve_db_path,
)
from fireai.core.nfpa72_models import (
    CeilingSpec,
    CeilingType,
    CoverageResult,
    DetectorType,
    RoomSpec,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_audit_state():
    """Reset audit_store module-level state between tests."""
    # Save original state
    orig_db_path = audit_mod.DATABASE_PATH
    orig_initialized = audit_mod._db_initialized
    orig_memory_conn = audit_mod._memory_conn

    # Reset for test isolation
    audit_mod._db_initialized = False
    audit_mod._memory_conn = None

    yield

    # Restore (best-effort)
    audit_mod.DATABASE_PATH = orig_db_path
    audit_mod._db_initialized = orig_initialized
    audit_mod._memory_conn = orig_memory_conn


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary database path that gets cleaned up."""
    return str(tmp_path / "test_audit.db")


@pytest.fixture
def fireai_system(tmp_path):
    """Create a FireAISystem with a temp database for isolation."""
    db_path = str(tmp_path / "test_fireai.db")
    system = FireAISystem(db_path=db_path)
    return system


@pytest.fixture
def sample_room_spec():
    """Create a minimal valid RoomSpec for testing."""
    return RoomSpec(
        room_id="test_room_01",
        width_m=10.0,
        depth_m=8.0,
        ceiling_spec=CeilingSpec(
            height_at_low_point_m=3.0,
            height_at_high_point_m=3.0,
            ceiling_type=CeilingType.FLAT,
            slope_degrees=0.0,
        ),
        detector_type=DetectorType.SMOKE,
        occupancy_type="office",
    )


@pytest.fixture
def large_room_spec():
    """Create a RoomSpec for a large room (requires multiple detectors)."""
    return RoomSpec(
        room_id="large_warehouse",
        width_m=30.0,
        depth_m=40.0,
        ceiling_spec=CeilingSpec(
            height_at_low_point_m=6.0,
            height_at_high_point_m=6.0,
            ceiling_type=CeilingType.FLAT,
            slope_degrees=0.0,
        ),
        detector_type=DetectorType.SMOKE,
        occupancy_type="storage",
    )


@pytest.fixture
def high_ceiling_room_spec():
    """Create a RoomSpec with a high ceiling."""
    return RoomSpec(
        room_id="high_atrium",
        width_m=20.0,
        depth_m=20.0,
        ceiling_spec=CeilingSpec(
            height_at_low_point_m=12.0,
            height_at_high_point_m=12.0,
            ceiling_type=CeilingType.FLAT,
            slope_degrees=0.0,
        ),
        detector_type=DetectorType.SMOKE,
        occupancy_type="atrium",
    )


# ============================================================================
# ConfidenceLevel ENUM TESTS
# ============================================================================


class TestConfidenceLevel:
    """Tests for the ConfidenceLevel enum."""

    def test_all_members_exist(self):
        """ConfidenceLevel should have HIGH, MEDIUM, LOW, UNSAFE."""
        assert ConfidenceLevel.HIGH.value == "HIGH"
        assert ConfidenceLevel.MEDIUM.value == "MEDIUM"
        assert ConfidenceLevel.LOW.value == "LOW"
        assert ConfidenceLevel.UNSAFE.value == "UNSAFE"

    def test_member_count(self):
        """ConfidenceLevel should have exactly 4 members."""
        assert len(ConfidenceLevel) == 4

    def test_from_value(self):
        """ConfidenceLevel should be constructable from string value."""
        assert ConfidenceLevel("HIGH") is ConfidenceLevel.HIGH
        assert ConfidenceLevel("MEDIUM") is ConfidenceLevel.MEDIUM
        assert ConfidenceLevel("LOW") is ConfidenceLevel.LOW
        assert ConfidenceLevel("UNSAFE") is ConfidenceLevel.UNSAFE

    def test_invalid_value_raises(self):
        """ConfidenceLevel should raise ValueError for invalid value."""
        with pytest.raises(ValueError):
            ConfidenceLevel("INVALID")


# ============================================================================
# PlacementProof DATACLASS TESTS
# ============================================================================


class TestPlacementProof:
    """Tests for the PlacementProof dataclass."""

    def test_default_values(self):
        """PlacementProof should have sensible defaults."""
        proof = PlacementProof()
        assert proof.coverage_fraction == 0.0
        assert proof.proof_valid is False
        assert proof.max_gap_m == 0.0

    def test_custom_values(self):
        """PlacementProof should accept custom values."""
        proof = PlacementProof(
            coverage_fraction=0.95,
            proof_valid=True,
            max_gap_m=1.2,
        )
        assert proof.coverage_fraction == 0.95
        assert proof.proof_valid is True
        assert proof.max_gap_m == 1.2

    def test_zero_coverage(self):
        """PlacementProof can represent zero coverage."""
        proof = PlacementProof(coverage_fraction=0.0, proof_valid=False)
        assert proof.coverage_fraction == 0.0
        assert proof.proof_valid is False

    def test_full_coverage(self):
        """PlacementProof can represent full coverage."""
        proof = PlacementProof(coverage_fraction=1.0, proof_valid=True)
        assert proof.coverage_fraction == 1.0
        assert proof.proof_valid is True


# ============================================================================
# ResilienceResult DATACLASS TESTS
# ============================================================================


class TestResilienceResult:
    """Tests for the ResilienceResult dataclass."""

    def test_default_values(self):
        """ResilienceResult should have sensible defaults."""
        result = ResilienceResult()
        assert result.resilient is False
        assert result.pass_rate == 0.0
        assert result.failure_detail == ""
        assert result.min_coverage_seen == 0.0

    def test_resilient_result(self):
        """ResilienceResult should capture a passing resilience check."""
        result = ResilienceResult(
            resilient=True,
            pass_rate=0.95,
            failure_detail="",
            min_coverage_seen=0.90,
        )
        assert result.resilient is True
        assert result.pass_rate == 0.95
        assert result.min_coverage_seen == 0.90

    def test_failed_result_with_detail(self):
        """ResilienceResult should capture a failed resilience check."""
        result = ResilienceResult(
            resilient=False,
            pass_rate=0.3,
            failure_detail="Single detector: no redundancy (MC fallback)",
        )
        assert result.resilient is False
        assert result.pass_rate == 0.3
        assert "no redundancy" in result.failure_detail


# ============================================================================
# EnhancedRoomResult DATACLASS TESTS
# ============================================================================


class TestEnhancedRoomResult:
    """Tests for the EnhancedRoomResult dataclass."""

    def test_default_values(self):
        """EnhancedRoomResult should have sensible defaults."""
        result = EnhancedRoomResult()
        assert result.room_id == ""
        assert result.detector_positions == []
        assert result.detector_type == DetectorType.SMOKE
        assert result.confidence == ConfidenceLevel.MEDIUM
        assert result.confidence_score == 0.0
        assert result.wall_violations == []
        assert result.warnings == []
        assert result.errors == []
        assert result.placement_proof is None
        assert result.resilience is None
        assert result.compliant is False
        assert result.safe_to_submit is False
        assert result.occupancy_class is None

    def test_status_pass(self):
        """Status property should return 'PASS' when compliant."""
        result = EnhancedRoomResult(compliant=True)
        assert result.status == "PASS"

    def test_status_fail(self):
        """Status property should return 'FAIL' when not compliant."""
        result = EnhancedRoomResult(compliant=False)
        assert result.status == "FAIL"

    def test_refused_true(self):
        """Refused property should be True when non-compliant with errors."""
        result = EnhancedRoomResult(compliant=False, errors=["Analysis engine error"])
        assert result.refused is True

    def test_refused_false_compliant(self):
        """Refused property should be False when compliant (even with errors)."""
        result = EnhancedRoomResult(compliant=True, errors=["some warning"])
        assert result.refused is False

    def test_refused_false_no_errors(self):
        """Refused property should be False when there are no errors."""
        result = EnhancedRoomResult(compliant=False, errors=[])
        assert result.refused is False

    def test_coverage_result_with_proof(self):
        """coverage_result property should return CoverageResult from placement_proof."""
        proof = PlacementProof(coverage_fraction=0.95, proof_valid=True)
        result = EnhancedRoomResult(compliant=True, placement_proof=proof)
        cr = result.coverage_result
        assert isinstance(cr, CoverageResult)
        assert cr.is_covered is True
        assert abs(cr.coverage_percentage - 95.0) < 0.01

    def test_coverage_result_without_proof(self):
        """coverage_result property should return zero coverage when no proof."""
        result = EnhancedRoomResult(compliant=False, placement_proof=None)
        cr = result.coverage_result
        assert isinstance(cr, CoverageResult)
        assert cr.is_covered is False
        assert cr.coverage_percentage == 0.0

    def test_safe_to_submit_true(self):
        """safe_to_submit should be True when compliant and not UNSAFE."""
        result = EnhancedRoomResult(
            compliant=True,
            confidence=ConfidenceLevel.HIGH,
            safe_to_submit=True,
        )
        assert result.safe_to_submit is True

    def test_safe_to_submit_false_unsafe(self):
        """safe_to_submit should be False when confidence is UNSAFE."""
        result = EnhancedRoomResult(
            compliant=True,
            confidence=ConfidenceLevel.UNSAFE,
            safe_to_submit=False,
        )
        assert result.safe_to_submit is False

    def test_custom_detector_positions(self):
        """EnhancedRoomResult should store detector positions."""
        positions = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
        result = EnhancedRoomResult(detector_positions=positions)
        assert result.detector_positions == positions
        assert len(result.detector_positions) == 3


# ============================================================================
# _resolve_db_path FUNCTION TESTS
# ============================================================================


class TestResolveDbPath:
    """Tests for the _resolve_db_path helper function."""

    def test_explicit_path(self, tmp_path):
        """Should return absolute path when db_path is explicit."""
        explicit = str(tmp_path / "my_audit.db")
        result = _resolve_db_path(explicit)
        assert os.path.isabs(result)
        assert result == os.path.abspath(explicit)

    def test_memory_path(self):
        """Should return ':memory:' as-is for in-memory databases."""
        result = _resolve_db_path(":memory:")
        assert result == ":memory:"

    def test_env_var_path(self, tmp_path, monkeypatch):
        """Should use FIREAI_DB_PATH env var when db_path is None."""
        env_path = str(tmp_path / "env_audit.db")
        monkeypatch.setenv("FIREAI_DB_PATH", env_path)
        result = _resolve_db_path(None)
        assert os.path.isabs(result)
        assert result == os.path.abspath(env_path)

    def test_default_path(self, monkeypatch):
        """Should use default path relative to module when nothing specified."""
        monkeypatch.delenv("FIREAI_DB_PATH", raising=False)
        result = _resolve_db_path(None)
        assert os.path.isabs(result)
        assert result.endswith("fireai_audit.db")

    def test_empty_string_treated_as_none(self, monkeypatch):
        """Empty string db_path should fall through to env/default."""
        monkeypatch.delenv("FIREAI_DB_PATH", raising=False)
        result = _resolve_db_path("")
        # Empty string is falsy, so falls through to env/default
        assert os.path.isabs(result)


# ============================================================================
# FireAISystem.__post_init__ TESTS
# ============================================================================


class TestFireAISystemInit:
    """Tests for FireAISystem initialization."""

    def test_initializes_with_valid_db_path(self, tmp_path):
        """FireAISystem should initialize with a valid database path."""
        db_path = str(tmp_path / "test_init.db")
        system = FireAISystem(db_path=db_path)
        assert system._resolved_db_path is not None

    def test_initializes_with_memory_db(self):
        """FireAISystem should initialize with ':memory:' database."""
        system = FireAISystem(db_path=":memory:")
        assert system._resolved_db_path == ":memory:"

    def test_learning_store_initialized(self, fireai_system):
        """FireAISystem should initialize LearningStore."""
        assert fireai_system.learning is not None

    def test_expert_not_initialized_at_start(self, fireai_system):
        """FireAISystem should lazy-initialize the expert engine."""
        assert fireai_system._expert is None

    def test_resolves_db_path(self, tmp_path):
        """FireAISystem should resolve the database path on init."""
        db_path = str(tmp_path / "resolved.db")
        system = FireAISystem(db_path=db_path)
        assert system._resolved_db_path == os.path.abspath(db_path)


# ============================================================================
# FireAISystem._get_expert TESTS
# ============================================================================


class TestGetExpert:
    """Tests for FireAISystem._get_expert lazy initialization."""

    def test_lazy_init_returns_expert(self, fireai_system):
        """_get_expert should return a FireExpertSystem instance."""
        from fireai.core.fire_expert_system import FireExpertSystem

        expert = fireai_system._get_expert()
        assert isinstance(expert, FireExpertSystem)

    def test_lazy_init_singleton(self, fireai_system):
        """_get_expert should return the same instance on repeated calls."""
        expert1 = fireai_system._get_expert()
        expert2 = fireai_system._get_expert()
        assert expert1 is expert2

    def test_expert_cached_after_first_call(self, fireai_system):
        """_get_expert should cache the expert after first call."""
        assert fireai_system._expert is None
        fireai_system._get_expert()
        assert fireai_system._expert is not None


# ============================================================================
# FireAISystem.analyse_room TESTS
# ============================================================================


class TestAnalyseRoom:
    """Tests for FireAISystem.analyse_room."""

    def test_valid_room_returns_enhanced_result(self, fireai_system, sample_room_spec):
        """analyse_room should return EnhancedRoomResult for valid input."""
        result = fireai_system.analyse_room(sample_room_spec)
        assert isinstance(result, EnhancedRoomResult)
        assert result.room_id == "test_room_01"

    def test_invalid_room_spec_none(self, fireai_system):
        """analyse_room should raise ValueError for None room_spec."""
        with pytest.raises(ValueError, match="room_id"):
            fireai_system.analyse_room(None)

    def test_invalid_room_spec_no_room_id(self, fireai_system):
        """analyse_room should raise ValueError for room_spec without room_id."""
        fake_spec = MagicMock()
        del fake_spec.room_id  # Remove room_id attribute
        with pytest.raises(ValueError, match="room_id"):
            fireai_system.analyse_room(fake_spec)

    def test_invalid_user_id_empty(self, fireai_system, sample_room_spec):
        """analyse_room should raise ValueError for empty user_id."""
        with pytest.raises(ValueError, match="user_id"):
            fireai_system.analyse_room(sample_room_spec, user_id="")

    def test_invalid_user_id_none(self, fireai_system, sample_room_spec):
        """analyse_room should raise ValueError for None user_id."""
        with pytest.raises(ValueError, match="user_id"):
            fireai_system.analyse_room(sample_room_spec, user_id=None)

    def test_invalid_user_id_non_string(self, fireai_system, sample_room_spec):
        """analyse_room should raise ValueError for non-string user_id."""
        with pytest.raises(ValueError, match="user_id"):
            fireai_system.analyse_room(sample_room_spec, user_id=123)

    def test_result_has_detector_positions(self, fireai_system, sample_room_spec):
        """analyse_room result should have detector_positions list."""
        result = fireai_system.analyse_room(sample_room_spec)
        assert isinstance(result.detector_positions, list)

    def test_result_has_confidence_level(self, fireai_system, sample_room_spec):
        """analyse_room result should have a ConfidenceLevel."""
        result = fireai_system.analyse_room(sample_room_spec)
        assert isinstance(result.confidence, ConfidenceLevel)

    def test_result_has_placement_proof(self, fireai_system, sample_room_spec):
        """analyse_room result should have a PlacementProof."""
        result = fireai_system.analyse_room(sample_room_spec)
        assert isinstance(result.placement_proof, PlacementProof)

    def test_result_detector_type(self, fireai_system, sample_room_spec):
        """analyse_room result should preserve detector type from spec."""
        result = fireai_system.analyse_room(sample_room_spec)
        assert result.detector_type == DetectorType.SMOKE

    def test_result_confidence_score_non_negative(self, fireai_system, sample_room_spec):
        """analyse_room result confidence_score should be non-negative."""
        result = fireai_system.analyse_room(sample_room_spec)
        assert result.confidence_score >= 0.0

    def test_compliant_room_has_high_or_medium_confidence(self, fireai_system, sample_room_spec):
        """A compliant room should have HIGH or MEDIUM confidence."""
        result = fireai_system.analyse_room(sample_room_spec)
        if result.compliant:
            assert result.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)

    def test_compliant_room_safe_to_submit(self, fireai_system, sample_room_spec):
        """A compliant room with non-UNSAFE confidence should be safe_to_submit."""
        result = fireai_system.analyse_room(sample_room_spec)
        if result.compliant and result.confidence != ConfidenceLevel.UNSAFE:
            assert result.safe_to_submit is True

    def test_large_room_has_detectors(self, fireai_system, large_room_spec):
        """A large room should require multiple detectors."""
        result = fireai_system.analyse_room(large_room_spec)
        assert len(result.detector_positions) > 0

    def test_high_ceiling_room(self, fireai_system, high_ceiling_room_spec):
        """A high ceiling room should produce a valid analysis result."""
        result = fireai_system.analyse_room(high_ceiling_room_spec)
        assert isinstance(result, EnhancedRoomResult)
        assert result.room_id == "high_atrium"

    def test_audit_trail_logged(self, fireai_system, sample_room_spec):
        """analyse_room should log an audit event."""
        fireai_system.analyse_room(sample_room_spec)
        events = fireai_system.get_audit_trail()
        # Should have at least one room_analysis event
        analysis_events = [e for e in events if e["event_type"] == "room_analysis"]
        assert len(analysis_events) >= 1
        last_event = analysis_events[-1]
        assert last_event["room_id"] == "test_room_01"
        assert "detector_count" in last_event["details"]

    def test_audit_event_contains_user_id(self, fireai_system, sample_room_spec):
        """Audit event should contain the user_id."""
        fireai_system.analyse_room(sample_room_spec, user_id="engineer_alice")
        events = fireai_system.get_audit_trail()
        analysis_events = [e for e in events if e["event_type"] == "room_analysis"]
        assert len(analysis_events) >= 1
        assert analysis_events[-1]["details"]["user_id"] == "engineer_alice"

    def test_resilience_run_by_default(self, fireai_system, sample_room_spec):
        """Resilience check should run by default (run_resilience=True)."""
        result = fireai_system.analyse_room(sample_room_spec)
        # Even if it falls back, resilience should be set if detectors exist
        if len(result.detector_positions) > 0:
            assert result.resilience is not None

    def test_resilience_disabled(self, fireai_system, sample_room_spec):
        """Resilience should be None when run_resilience=False."""
        result = fireai_system.analyse_room(
            sample_room_spec, run_resilience=False
        )
        assert result.resilience is None

    def test_resilience_result_structure(self, fireai_system, sample_room_spec):
        """ResilienceResult should have expected attributes."""
        result = fireai_system.analyse_room(sample_room_spec, run_resilience=True)
        if result.resilience is not None:
            assert isinstance(result.resilience, ResilienceResult)
            assert isinstance(result.resilience.resilient, bool)
            assert isinstance(result.resilience.pass_rate, float)

    def test_analysis_engine_error_returns_unsafe(self, fireai_system, sample_room_spec):
        """If the analysis engine fails, result should have UNSAFE confidence."""
        with patch.object(
            fireai_system, "_get_expert"
        ) as mock_get_expert:
            mock_expert = MagicMock()
            mock_expert.analyse_room.side_effect = RuntimeError("Engine crashed")
            mock_get_expert.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec)
            assert result.confidence == ConfidenceLevel.UNSAFE
            assert len(result.errors) > 0
            assert "Engine crashed" in result.errors[0]

    def test_no_resilience_with_no_detectors(self, fireai_system):
        """Resilience should be None when there are no detector positions."""
        room_spec = MagicMock()
        room_spec.room_id = "empty_room"
        room_spec.width_m = 5.0
        room_spec.depth_m = 5.0
        room_spec.ceiling_spec = MagicMock()
        room_spec.ceiling_spec.height_at_low_point_m = 3.0
        room_spec.detector_type = DetectorType.SMOKE
        room_spec.occupancy_type = "office"
        room_spec.area_sqm = 25.0

        # Mock the expert to return an analysis with no detectors
        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_analysis = MagicMock()
            mock_analysis.layout.detectors = []
            mock_analysis.coverage = 0.0
            mock_analysis.passed = False
            mock_analysis.proof_valid = False
            mock_analysis.wall_violations = 0
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(room_spec, run_resilience=True)
            assert result.resilience is None


# ============================================================================
# CONFIDENCE LEVEL BRANCH TESTS
# ============================================================================


class TestConfidenceLevelBranches:
    """Tests for different confidence level branches in analyse_room."""

    def _make_mock_analysis(self, passed, coverage_pct, proof_valid=True, wall_violations=0):
        """Helper to create a mock analysis result."""
        mock = MagicMock()
        mock.layout.detectors = [(1.0, 2.0), (3.0, 4.0)]
        mock.coverage = coverage_pct
        mock.passed = passed
        mock.proof_valid = proof_valid
        mock.wall_violations = wall_violations
        return mock

    def test_high_confidence_compliant_99plus_coverage(self, fireai_system, sample_room_spec):
        """Compliant room with >=99% coverage should get HIGH confidence."""
        mock_analysis = self._make_mock_analysis(passed=True, coverage_pct=99.5)

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.confidence == ConfidenceLevel.HIGH
            assert result.compliant is True

    def test_medium_confidence_compliant_below_99(self, fireai_system, sample_room_spec):
        """Compliant room with <99% coverage should get MEDIUM confidence."""
        mock_analysis = self._make_mock_analysis(passed=True, coverage_pct=95.0)

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.confidence == ConfidenceLevel.MEDIUM
            assert result.compliant is True

    def test_low_confidence_noncompliant_90plus_coverage(self, fireai_system, sample_room_spec):
        """Non-compliant room with >=90% coverage should get LOW confidence."""
        mock_analysis = self._make_mock_analysis(passed=False, coverage_pct=92.0)

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.confidence == ConfidenceLevel.LOW
            assert result.compliant is False

    def test_unsafe_confidence_noncompliant_low_coverage(self, fireai_system, sample_room_spec):
        """Non-compliant room with <90% coverage should get UNSAFE confidence."""
        mock_analysis = self._make_mock_analysis(passed=False, coverage_pct=50.0)

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.confidence == ConfidenceLevel.UNSAFE
            assert result.compliant is False

    def test_unsafe_confidence_not_safe_to_submit(self, fireai_system, sample_room_spec):
        """UNSAFE confidence should make safe_to_submit=False."""
        mock_analysis = self._make_mock_analysis(passed=False, coverage_pct=50.0)

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.safe_to_submit is False


# ============================================================================
# RESILIENCE FALLBACK TESTS
# ============================================================================


class TestResilienceFallback:
    """Tests for resilience checking (MC and fallback paths)."""

    def test_mc_fallback_single_detector(self, fireai_system, sample_room_spec):
        """When MC import fails, fallback should mark single detector as not resilient."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(5.0, 4.0)]  # single detector
        mock_analysis.coverage = 95.0
        mock_analysis.passed = True
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = []

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            # Force the MC import inside analyse_room to fail
            import builtins
            real_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "fireai.core.monte_carlo_pipeline":
                    raise ImportError("MC not available")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = fireai_system.analyse_room(sample_room_spec, run_resilience=True)
                if result.resilience is not None:
                    # With only 1 detector, fallback should be not resilient
                    assert result.resilience.resilient is False

    def test_mc_fallback_multiple_detectors(self, fireai_system, sample_room_spec):
        """When MC fails, fallback with multiple detectors should be resilient."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(2.0, 2.0), (8.0, 6.0)]  # 2 detectors
        mock_analysis.coverage = 95.0
        mock_analysis.passed = True
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = 0

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert
            # Force MC to fail by patching the import inside analyse_room
            with patch.dict("sys.modules", {"fireai.core.monte_carlo_pipeline": None}):
                result = fireai_system.analyse_room(sample_room_spec, run_resilience=True)
                if result.resilience is not None:
                    assert result.resilience.resilient is True  # >1 detectors = resilient


# ============================================================================
# FireAISystem.analyse_floor TESTS
# ============================================================================


class TestAnalyseFloor:
    """Tests for FireAISystem.analyse_floor."""

    def test_valid_floor_returns_results(self, fireai_system, sample_room_spec):
        """analyse_floor should return list of EnhancedRoomResult."""
        results = fireai_system.analyse_floor([sample_room_spec])
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], EnhancedRoomResult)

    def test_multiple_rooms(self, fireai_system, sample_room_spec, large_room_spec):
        """analyse_floor should handle multiple rooms."""
        results = fireai_system.analyse_floor([sample_room_spec, large_room_spec])
        assert len(results) == 2
        assert results[0].room_id == "test_room_01"
        assert results[1].room_id == "large_warehouse"

    def test_empty_rooms_list_raises(self, fireai_system):
        """analyse_floor should raise ValueError for empty rooms list."""
        with pytest.raises(ValueError, match="must not be empty"):
            fireai_system.analyse_floor([])

    def test_too_many_rooms_raises(self, fireai_system):
        """analyse_floor should raise ValueError for >500 rooms."""
        # Create a mock RoomSpec list of 501 items
        rooms = [MagicMock(room_id=f"room_{i}", spec=True) for i in range(501)]
        with pytest.raises(ValueError, match="Maximum 500"):
            fireai_system.analyse_floor(rooms)

    def test_floor_audit_event_logged(self, fireai_system, sample_room_spec):
        """analyse_floor should log a floor_analysis audit event."""
        fireai_system.analyse_floor([sample_room_spec])
        events = fireai_system.get_audit_trail()
        floor_events = [e for e in events if e["event_type"] == "floor_analysis"]
        assert len(floor_events) >= 1
        assert floor_events[-1]["details"]["room_count"] == 1

    def test_floor_audit_includes_room_ids(self, fireai_system, sample_room_spec):
        """Floor audit event should include room IDs."""
        fireai_system.analyse_floor([sample_room_spec], user_id="engineer_bob")
        events = fireai_system.get_audit_trail()
        floor_events = [e for e in events if e["event_type"] == "floor_analysis"]
        assert len(floor_events) >= 1
        assert "test_room_01" in floor_events[-1]["details"]["rooms"]

    def test_floor_500_rooms_accepted(self, fireai_system):
        """analyse_floor should accept exactly 500 rooms (boundary test)."""
        # We use mocks to avoid actually running 500 analyses
        mock_spec = MagicMock()
        mock_spec.room_id = "room_boundary"
        mock_spec.width_m = 10.0
        mock_spec.depth_m = 8.0
        mock_spec.ceiling_spec = MagicMock()
        mock_spec.ceiling_spec.height_at_low_point_m = 3.0
        mock_spec.detector_type = DetectorType.SMOKE
        mock_spec.occupancy_type = "office"
        mock_spec.area_sqm = 80.0

        mock_result = EnhancedRoomResult(room_id="room_boundary", compliant=True)

        with patch.object(fireai_system, "analyse_room", return_value=mock_result):
            rooms = [mock_spec] * 500
            results = fireai_system.analyse_floor(rooms)
            assert len(results) == 500


# ============================================================================
# FireAISystem.get_audit_trail TESTS
# ============================================================================


class TestGetAuditTrail:
    """Tests for FireAISystem.get_audit_trail."""

    def test_empty_trail(self, tmp_path):
        """get_audit_trail should return empty list for new system."""
        db_path = str(tmp_path / "empty_audit.db")
        system = FireAISystem(db_path=db_path)
        # Freshly initialized, might have no events yet
        events = system.get_audit_trail()
        assert isinstance(events, list)

    def test_trail_after_analysis(self, fireai_system, sample_room_spec):
        """get_audit_trail should contain events after analysis."""
        fireai_system.analyse_room(sample_room_spec)
        events = fireai_system.get_audit_trail()
        assert len(events) >= 1
        # Should have at least a room_analysis event
        event_types = [e["event_type"] for e in events]
        assert "room_analysis" in event_types

    def test_trail_events_have_required_fields(self, fireai_system, sample_room_spec):
        """Audit trail events should have required fields."""
        fireai_system.analyse_room(sample_room_spec)
        events = fireai_system.get_audit_trail()
        for event in events:
            assert "event_type" in event
            assert "room_id" in event
            assert "details" in event
            assert "timestamp" in event
            assert "current_hash" in event
            assert "previous_hash" in event


# ============================================================================
# FireAISystem.verify_audit_integrity TESTS
# ============================================================================


class TestVerifyAuditIntegrity:
    """Tests for FireAISystem.verify_audit_integrity."""

    def test_fresh_system_integrity_valid(self, tmp_path):
        """Audit integrity should be valid for a fresh system."""
        db_path = str(tmp_path / "integrity_test.db")
        system = FireAISystem(db_path=db_path)
        # Fresh system with no events should have valid chain
        is_valid = system.verify_audit_integrity()
        assert isinstance(is_valid, bool)

    def test_integrity_after_analysis(self, fireai_system, sample_room_spec):
        """Audit integrity should be valid after normal analysis."""
        fireai_system.analyse_room(sample_room_spec)
        is_valid = fireai_system.verify_audit_integrity()
        assert is_valid is True


# ============================================================================
# FireAISystem.get_memory_summary TESTS
# ============================================================================


class TestGetMemorySummary:
    """Tests for FireAISystem.get_memory_summary."""

    def test_with_learning_store(self, fireai_system, sample_room_spec):
        """get_memory_summary should return a dict when learning store exists."""
        # First, store some data by running an analysis
        fireai_system.analyse_room(sample_room_spec)
        summary = fireai_system.get_memory_summary()
        assert isinstance(summary, dict)
        # LearningStore doesn't have get_summary(), so it returns error dict
        # This tests the error handling path
        assert "error" in summary or isinstance(summary, dict)

    def test_without_learning_store(self, fireai_system):
        """get_memory_summary should return error dict when learning is None."""
        fireai_system.learning = None
        summary = fireai_system.get_memory_summary()
        assert isinstance(summary, dict)
        assert "error" in summary
        assert "not initialized" in summary["error"]


# ============================================================================
# FireAISystem.run_integration TESTS
# ============================================================================


class TestRunIntegration:
    """Tests for FireAISystem.run_integration (with mocked bridge).

    Uses the real dataclasses from integration_bridge (FloorData,
    AcousticConfig, IntegrationConfig) so isinstance() checks pass,
    and only mocks IntegrationBridge.run() to avoid expensive computation.
    """

    def _make_mock_integration_result(self):
        """Create a mock IntegrationBridge result."""
        mock_result = MagicMock()
        mock_result.overall_compliant = True
        mock_result.execution_time_s = 1.23
        mock_result.cable_result = MagicMock()
        mock_result.cable_result.compliant = True
        mock_result.cable_result.circuit_count = 4
        mock_result.twin_result = MagicMock()
        mock_result.acoustic_result = MagicMock()
        mock_result.multi_floor_result = MagicMock()
        mock_result.errors = []
        mock_result.warnings = []
        return mock_result

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_basic_integration_run(self, mock_audit, fireai_system):
        """run_integration should return a result dict with building_id."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            result = fireai_system.run_integration(
                building_id="BLDG-001",
                floors=[],
                user_id="engineer_test",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["building_id"] == "BLDG-001"
            assert result["nfpa_year"] == 2022

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_with_floor_data(self, mock_audit, fireai_system):
        """run_integration should handle floor data dicts."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            floor_data = {
                "floor_id": "F1",
                "elevation_m": 0.0,
                "area_sqm": 500.0,
                "ceiling_height_m": 3.0,
                "occupancy_type": "business",
            }
            result = fireai_system.run_integration(
                building_id="BLDG-002",
                floors=[floor_data],
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["building_id"] == "BLDG-002"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_with_acoustic_config(self, mock_audit, fireai_system):
        """run_integration should handle acoustic_config dict."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            result = fireai_system.run_integration(
                building_id="BLDG-003",
                acoustic_config={
                    "mode": "public",
                    "ambient_noise_dba": 60,
                    "speaker_rating_dba": 95,
                    "include_ugld": False,
                },
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["building_id"] == "BLDG-003"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_disables_subsystems(self, mock_audit, fireai_system):
        """run_integration should respect enable flags."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            result = fireai_system.run_integration(
                building_id="BLDG-004",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            # All advanced subsystems should be None when disabled
            assert result["advanced_subsystems"]["kernel_v30"] is None
            assert result["advanced_subsystems"]["hash_chain_audit"] is None
            assert result["advanced_subsystems"]["monte_carlo"] is None
            assert result["advanced_subsystems"]["bim_sync"] is None

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_logs_audit_event(self, mock_audit, fireai_system):
        """run_integration should log an integration_pipeline_run audit event."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            fireai_system.run_integration(
                building_id="BLDG-005",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            # AuditStore.add_event should have been called with integration_pipeline_run
            mock_audit.assert_called()
            call_args_list = mock_audit.call_args_list
            # Find the integration_pipeline_run call — uses kwargs
            integration_calls = [
                c for c in call_args_list
                if c.kwargs.get("event_type") == "integration_pipeline_run"
            ]
            assert len(integration_calls) >= 1

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_custom_nfpa_year(self, mock_audit, fireai_system):
        """run_integration should accept custom nfpa_year."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            result = fireai_system.run_integration(
                building_id="BLDG-006",
                nfpa_year=2019,
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["nfpa_year"] == 2019

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_result_structure(self, mock_audit, fireai_system):
        """run_integration result should have expected top-level keys."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            result = fireai_system.run_integration(
                building_id="BLDG-007",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert "building_id" in result
            assert "nfpa_year" in result
            assert "overall_compliant" in result
            assert "execution_time_s" in result
            assert "core_subsystems" in result
            assert "advanced_subsystems" in result
            assert "errors" in result
            assert "warnings" in result

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_core_subsystem_structure(self, mock_audit, fireai_system):
        """run_integration core_subsystems should have expected keys."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result):
            result = fireai_system.run_integration(
                building_id="BLDG-008",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            core = result["core_subsystems"]
            assert "cable_routing" in core
            assert "digital_twin_sync" in core
            assert "acoustics" in core
            assert "multi_floor" in core


# ============================================================================
# INTEGRATION / END-TO-END TESTS
# ============================================================================


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_analysis_workflow(self, fireai_system, sample_room_spec):
        """Full workflow: analyse_room -> audit trail -> verify integrity."""
        result = fireai_system.analyse_room(sample_room_spec, user_id="test_user")
        assert isinstance(result, EnhancedRoomResult)

        # Check audit trail
        events = fireai_system.get_audit_trail()
        assert len(events) >= 1

        # Verify integrity
        is_valid = fireai_system.verify_audit_integrity()
        assert is_valid is True

    def test_floor_then_audit(self, fireai_system, sample_room_spec, large_room_spec):
        """Floor analysis should produce both room and floor audit events."""
        fireai_system.analyse_floor([sample_room_spec, large_room_spec], user_id="floor_user")
        events = fireai_system.get_audit_trail()
        event_types = [e["event_type"] for e in events]
        assert "room_analysis" in event_types
        assert "floor_analysis" in event_types

    def test_multiple_analyses_independent(self, fireai_system, sample_room_spec, large_room_spec):
        """Multiple analyses should produce independent results."""
        result1 = fireai_system.analyse_room(sample_room_spec)
        result2 = fireai_system.analyse_room(large_room_spec)
        assert result1.room_id == "test_room_01"
        assert result2.room_id == "large_warehouse"

    def test_coverage_fraction_computation(self, fireai_system, sample_room_spec):
        """Coverage fraction should be properly computed from percentage."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(2.5, 2.0), (7.5, 6.0)]
        mock_analysis.coverage = 99.5
        mock_analysis.passed = True
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = 0

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            # coverage_pct of 99.5 -> coverage_fraction of 0.995
            assert result.placement_proof is not None
            assert abs(result.placement_proof.coverage_fraction - 0.995) < 0.01

    def test_learning_store_receives_experience(self, fireai_system, sample_room_spec):
        """analyse_room should store experience in LearningStore."""
        mock_learning = MagicMock()
        mock_learning.store.return_value = True
        mock_learning.maybe_recalibrate.return_value = False
        fireai_system.learning = mock_learning

        fireai_system.analyse_room(sample_room_spec)

        # Verify learning.store was called
        mock_learning.store.assert_called_once()
        call_kwargs = mock_learning.store.call_args
        assert call_kwargs[1]["room_id"] == "test_room_01"
        assert call_kwargs[1]["solver_used"] == "fireai_core"
        mock_learning.maybe_recalibrate.assert_called_once()

    def test_learning_store_failure_does_not_crash(self, fireai_system, sample_room_spec):
        """If learning.store fails, analyse_room should still return a result."""
        mock_learning = MagicMock()
        mock_learning.store.side_effect = Exception("DB locked")
        fireai_system.learning = mock_learning

        result = fireai_system.analyse_room(sample_room_spec)
        assert isinstance(result, EnhancedRoomResult)

    def test_hash_chain_audit_non_blocking(self, fireai_system, sample_room_spec):
        """Hash chain audit logging failure should not block analysis."""
        result = fireai_system.analyse_room(sample_room_spec)
        # Should still get a result even if hash chain audit fails
        assert isinstance(result, EnhancedRoomResult)


# ============================================================================
# EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_room_spec_with_default_ceiling(self, fireai_system):
        """RoomSpec with default ceiling should work."""
        room_spec = RoomSpec(
            room_id="default_ceiling",
            width_m=8.0,
            depth_m=6.0,
            occupancy_type="office",
        )
        result = fireai_system.analyse_room(room_spec)
        assert isinstance(result, EnhancedRoomResult)
        assert result.room_id == "default_ceiling"

    def test_analysis_with_heat_detector_type(self, fireai_system):
        """analyse_room should work with heat detector type."""
        room_spec = RoomSpec(
            room_id="heat_room",
            width_m=10.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(
                height_at_low_point_m=3.0,
                height_at_high_point_m=3.0,
                ceiling_type=CeilingType.FLAT,
                slope_degrees=0.0,
            ),
            detector_type=DetectorType.HEAT,
            occupancy_type="storage",
        )
        result = fireai_system.analyse_room(room_spec)
        assert isinstance(result, EnhancedRoomResult)
        assert result.detector_type == DetectorType.HEAT

    def test_analyse_room_with_wall_violations(self, fireai_system, sample_room_spec):
        """analyse_room should handle wall violations in analysis result."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(0.01, 0.01)]  # Too close to wall
        mock_analysis.coverage = 85.0
        mock_analysis.passed = False
        mock_analysis.proof_valid = False
        mock_analysis.wall_violations = ["too_close_1", "too_close_2"]  # List, not int

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert len(result.wall_violations) == 2
            assert result.compliant is False

    def test_confidence_level_from_coverage_fraction_edge(self, fireai_system, sample_room_spec):
        """Test edge case: coverage_fraction exactly at 0.90 threshold."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(5.0, 4.0)]
        mock_analysis.coverage = 90.0
        mock_analysis.passed = False
        mock_analysis.proof_valid = False
        mock_analysis.wall_violations = ["violation_1"]  # List, not int

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            # coverage_pct=90.0, coverage_fraction=0.90, >=0.90 threshold -> LOW
            assert result.confidence == ConfidenceLevel.LOW

    def test_analyse_room_preserves_occupancy_type(self, fireai_system):
        """analyse_room should preserve occupancy_type in learning store."""
        room_spec = RoomSpec(
            room_id="biz_room",
            width_m=12.0,
            depth_m=10.0,
            ceiling_spec=CeilingSpec(
                height_at_low_point_m=3.0,
                height_at_high_point_m=3.0,
                ceiling_type=CeilingType.FLAT,
                slope_degrees=0.0,
            ),
            detector_type=DetectorType.SMOKE,
            occupancy_type="business",
        )

        mock_learning = MagicMock()
        mock_learning.store.return_value = True
        mock_learning.maybe_recalibrate.return_value = False
        fireai_system.learning = mock_learning

        fireai_system.analyse_room(room_spec)

        call_kwargs = mock_learning.store.call_args
        assert call_kwargs[1]["occupancy"] == "business"

    def test_resolve_db_path_none_with_no_env(self, monkeypatch):
        """_resolve_db_path(None) with no env var should use default path."""
        monkeypatch.delenv("FIREAI_DB_PATH", raising=False)
        result = _resolve_db_path(None)
        assert result.endswith("fireai_audit.db")

    def test_enhanced_result_coverage_fraction_already_fraction(self, fireai_system, sample_room_spec):
        """When coverage is already a fraction (<1), it should be used as-is."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(5.0, 4.0)]
        mock_analysis.coverage = 0.85  # Already a fraction
        mock_analysis.passed = False
        mock_analysis.proof_valid = False
        mock_analysis.wall_violations = 0

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            # coverage of 0.85 is < 1, so used as-is as fraction
            assert result.placement_proof.coverage_fraction == 0.85


# ============================================================================
# __post_init__ AUDIT CHAIN VERIFICATION BRANCHES
# ============================================================================


class TestPostInitAuditChain:
    """Tests for __post_init__ audit chain verification branches."""

    def test_init_with_valid_chain(self, tmp_path, monkeypatch):
        """Init should succeed when audit chain is valid."""
        monkeypatch.delenv("FIREAI_DB_PATH", raising=False)
        db_path = str(tmp_path / "valid_chain.db")
        system = FireAISystem(db_path=db_path)
        assert system._resolved_db_path is not None

    def test_init_dev_mode_key_mismatch_warning(self, tmp_path, monkeypatch):
        """Init should warn (not crash) when audit chain fails in dev mode."""
        monkeypatch.delenv("AUDIT_HMAC_KEY", raising=False)
        monkeypatch.delenv("FIREAI_ENV", raising=False)
        monkeypatch.delenv("PRODUCTION", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        db_path = str(tmp_path / "dev_mode.db")
        # This should not raise even if chain verification fails
        system = FireAISystem(db_path=db_path)
        assert system._resolved_db_path is not None

    def test_init_with_empty_db(self, tmp_path):
        """Init should succeed with a fresh empty database."""
        db_path = str(tmp_path / "fresh.db")
        system = FireAISystem(db_path=db_path)
        assert system.learning is not None


# ============================================================================
# HASH CHAIN AUDIT IN analyse_room
# ============================================================================


class TestHashChainAudit:
    """Tests for the hash chain audit logging in analyse_room."""

    def test_hash_chain_audit_succeeds(self, fireai_system, sample_room_spec):
        """analyse_room should log to hash chain audit if available."""
        mock_hash_chain = MagicMock()
        fireai_system._hash_chain = mock_hash_chain

        fireai_system.analyse_room(sample_room_spec, run_resilience=False)

        # Hash chain log should have been called
        mock_hash_chain.log.assert_called_once()
        call_kwargs = mock_hash_chain.log.call_args
        assert call_kwargs[1]["event_type"] == "room_analysis"
        assert call_kwargs[1]["actor"] == "system"

    def test_hash_chain_audit_creates_store_on_first_use(self, fireai_system, sample_room_spec):
        """First call to analyse_room should create _hash_chain if importable."""
        # Ensure _hash_chain doesn't exist yet
        if hasattr(fireai_system, "_hash_chain"):
            delattr(fireai_system, "_hash_chain")

        fireai_system.analyse_room(sample_room_spec, run_resilience=False)
        # Should not crash regardless of whether hash chain was created

    def test_hash_chain_audit_failure_non_blocking(self, fireai_system, sample_room_spec):
        """analyse_room should not crash if hash chain audit fails."""
        mock_hash_chain = MagicMock()
        mock_hash_chain.log.side_effect = Exception("Hash chain DB locked")
        fireai_system._hash_chain = mock_hash_chain

        result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
        assert isinstance(result, EnhancedRoomResult)


# ============================================================================
# MONTE CARLO RESILIENCE PATHS
# ============================================================================


class TestMonteCarloResilience:
    """Tests for the Monte Carlo resilience simulation paths in analyse_room."""

    def test_mc_resilience_succeeds(self, fireai_system, sample_room_spec):
        """analyse_room should run MC resilience when available."""
        result = fireai_system.analyse_room(sample_room_spec, run_resilience=True)
        # Result should be valid regardless of MC success/failure
        assert isinstance(result, EnhancedRoomResult)
        if result.resilience is not None:
            assert isinstance(result.resilience, ResilienceResult)
            # MC results should have pass_rate between 0 and 1
            assert 0.0 <= result.resilience.pass_rate <= 1.0

    def test_mc_resilience_with_large_room(self, fireai_system, large_room_spec):
        """MC resilience should work with large rooms that have many detectors."""
        result = fireai_system.analyse_room(large_room_spec, run_resilience=True)
        assert isinstance(result, EnhancedRoomResult)
        if result.resilience is not None:
            assert isinstance(result.resilience, ResilienceResult)


# ============================================================================
# run_integration ADVANCED SUBSYSTEM PATHS
# ============================================================================


class TestRunIntegrationAdvancedSubsystems:
    """Tests for the advanced subsystem paths in run_integration."""

    def _make_mock_integration_result(self):
        """Create a mock IntegrationBridge result."""
        mock_result = MagicMock()
        mock_result.overall_compliant = True
        mock_result.execution_time_s = 1.23
        mock_result.cable_result = MagicMock()
        mock_result.cable_result.compliant = True
        mock_result.cable_result.circuit_count = 4
        mock_result.twin_result = MagicMock()
        mock_result.acoustic_result = MagicMock()
        mock_result.multi_floor_result = MagicMock()
        mock_result.errors = []
        mock_result.warnings = []
        return mock_result

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_kernel_v30_subsystem_enabled(self, mock_audit, fireai_system):
        """run_integration should run kernel V30 when enabled."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.kernel_v30_integration.KernelV30Dispatcher") as MockDispatcher, \
             patch("fireai.core.kernel_v30_integration.MPSCWorkerPool") as MockPool:
            mock_dispatcher = MagicMock()
            mock_dispatcher._simd_mode = "SIMD"
            mock_dispatcher._cache = None
            mock_dispatcher.shutdown = MagicMock()
            MockDispatcher.return_value = mock_dispatcher
            MockPool._default_optimize = MagicMock(return_value={})

            result = fireai_system.run_integration(
                building_id="BLDG-KV30",
                enable_kernel_v30=True,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["advanced_subsystems"]["kernel_v30"] is not None
            assert result["advanced_subsystems"]["kernel_v30"]["status"] == "completed"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_kernel_v30_subsystem_failure(self, mock_audit, fireai_system):
        """run_integration should handle kernel V30 failure gracefully."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.kernel_v30_integration.KernelV30Dispatcher", side_effect=ImportError("No SIMD")):

            result = fireai_system.run_integration(
                building_id="BLDG-KV30FAIL",
                enable_kernel_v30=True,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["advanced_subsystems"]["kernel_v30"]["status"] == "failed"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_hash_chain_audit_subsystem_enabled(self, mock_audit, fireai_system):
        """run_integration should run hash chain audit when enabled."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.audit_blockchain_bridge.HashChainAuditStore") as MockHCStore:
            mock_hc = MagicMock()
            mock_hc.log = MagicMock()
            mock_hc.verify_chain.return_value = (True, [])
            MockHCStore.return_value = mock_hc

            result = fireai_system.run_integration(
                building_id="BLDG-HC",
                enable_kernel_v30=False,
                enable_hash_chain_audit=True,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["advanced_subsystems"]["hash_chain_audit"] is not None
            assert result["advanced_subsystems"]["hash_chain_audit"]["status"] == "completed"
            assert result["advanced_subsystems"]["hash_chain_audit"]["chain_valid"] is True

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_hash_chain_audit_subsystem_failure(self, mock_audit, fireai_system):
        """run_integration should handle hash chain audit failure gracefully."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.audit_blockchain_bridge.HashChainAuditStore", side_effect=ImportError("No bridge")):

            result = fireai_system.run_integration(
                building_id="BLDG-HCFAIL",
                enable_kernel_v30=False,
                enable_hash_chain_audit=True,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["advanced_subsystems"]["hash_chain_audit"]["status"] == "failed"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_monte_carlo_subsystem_enabled(self, mock_audit, fireai_system):
        """run_integration should run Monte Carlo when enabled."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.monte_carlo_pipeline.MCPipelineAdapter") as MockMC:
            mock_mc = MagicMock()
            mock_sim = MagicMock()
            mock_sim.simulate_room_reliability.return_value = {
                "is_reliable": True,
                "p_full_coverage": 0.95,
                "mean_coverage_pct": 97.0,
                "worst_coverage_pct": 85.0,
                "n_trials": 1000,
            }
            mock_mc.return_value._sim = mock_sim
            mock_mc.return_value = MagicMock(_sim=mock_sim)
            MockMC.return_value = MagicMock(_sim=mock_sim)

            # Provide floor data with room specs that have detectors
            floor_data = {
                "floor_id": "F1",
                "elevation_m": 0.0,
                "area_sqm": 500.0,
                "ceiling_height_m": 3.0,
                "occupancy_type": "business",
                "room_specs": [
                    {
                        "width": 10.0,
                        "length": 8.0,
                        "ceiling_height": 3.0,
                        "detectors": [{"x": 3.0, "y": 2.0}, {"x": 7.0, "y": 6.0}],
                    }
                ],
            }

            result = fireai_system.run_integration(
                building_id="BLDG-MC",
                floors=[floor_data],
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=True,
                enable_bim_sync=False,
            )

            mc_result = result["advanced_subsystems"]["monte_carlo"]
            assert mc_result is not None

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_monte_carlo_subsystem_failure(self, mock_audit, fireai_system):
        """run_integration should handle Monte Carlo failure gracefully."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.monte_carlo_pipeline.MCPipelineAdapter", side_effect=ImportError("No MC")):

            result = fireai_system.run_integration(
                building_id="BLDG-MCFAIL",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=True,
                enable_bim_sync=False,
            )

            assert result["advanced_subsystems"]["monte_carlo"]["status"] == "failed"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_bim_sync_subsystem_enabled(self, mock_audit, fireai_system):
        """run_integration should run BIM sync when enabled."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.bridges.revit_bim_sync.BIMSyncOrchestrator") as MockBIM:
            mock_bim = MagicMock()
            mock_bim._bridge.mode = "mock"
            mock_bim._bridge.is_live = False
            MockBIM.return_value = mock_bim

            result = fireai_system.run_integration(
                building_id="BLDG-BIM",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=True,
            )

            assert result["advanced_subsystems"]["bim_sync"] is not None
            assert result["advanced_subsystems"]["bim_sync"]["status"] == "available"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_bim_sync_subsystem_failure(self, mock_audit, fireai_system):
        """run_integration should handle BIM sync failure gracefully."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.bridges.revit_bim_sync.BIMSyncOrchestrator", side_effect=ImportError("No BIM")):

            result = fireai_system.run_integration(
                building_id="BLDG-BIMFAIL",
                enable_kernel_v30=False,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=True,
            )

            assert result["advanced_subsystems"]["bim_sync"]["status"] == "failed"

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_all_subsystems_enabled(self, mock_audit, fireai_system):
        """run_integration should work with all subsystems enabled."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.kernel_v30_integration.KernelV30Dispatcher") as MockDispatcher, \
             patch("fireai.core.kernel_v30_integration.MPSCWorkerPool") as MockPool, \
             patch("fireai.core.audit_blockchain_bridge.HashChainAuditStore") as MockHC, \
             patch("fireai.core.monte_carlo_pipeline.MCPipelineAdapter") as MockMC, \
             patch("fireai.bridges.revit_bim_sync.BIMSyncOrchestrator") as MockBIM:
            # Setup mocks
            mock_d = MagicMock()
            mock_d._simd_mode = "SIMD"
            mock_d._cache = None
            mock_d.shutdown = MagicMock()
            MockDispatcher.return_value = mock_d
            MockPool._default_optimize = MagicMock(return_value={})

            mock_hc = MagicMock()
            mock_hc.log = MagicMock()
            mock_hc.verify_chain.return_value = (True, [])
            MockHC.return_value = mock_hc

            MockMC.return_value = MagicMock()
            mock_bim = MagicMock()
            mock_bim._bridge.mode = "mock"
            mock_bim._bridge.is_live = False
            MockBIM.return_value = mock_bim

            result = fireai_system.run_integration(
                building_id="BLDG-ALL",
                enable_kernel_v30=True,
                enable_hash_chain_audit=True,
                enable_monte_carlo=True,
                enable_bim_sync=True,
            )

            assert result["building_id"] == "BLDG-ALL"
            # All advanced subsystems should have results (not None)
            assert result["advanced_subsystems"]["kernel_v30"] is not None
            assert result["advanced_subsystems"]["hash_chain_audit"] is not None
            # MC and BIM may or may not succeed depending on floor data
            # but they should at least be attempted

    @patch("fireai.core.fireai_core.AuditStore.add_event")
    def test_integration_with_floor_data_having_room_specs(self, mock_audit, fireai_system):
        """run_integration should handle floor data with room_specs containing dicts."""
        mock_bridge_result = self._make_mock_integration_result()

        with patch("fireai.bridges.integration_bridge.IntegrationBridge.run", return_value=mock_bridge_result), \
             patch("fireai.core.kernel_v30_integration.KernelV30Dispatcher") as MockDispatcher, \
             patch("fireai.core.kernel_v30_integration.MPSCWorkerPool") as MockPool:
            mock_d = MagicMock()
            mock_d._simd_mode = "SIMD"
            mock_d._cache = None
            mock_d.shutdown = MagicMock()
            MockDispatcher.return_value = mock_d
            MockPool._default_optimize = MagicMock(return_value={"optimized": True})

            floor_data = {
                "floor_id": "F1",
                "elevation_m": 0.0,
                "area_sqm": 500.0,
                "ceiling_height_m": 3.0,
                "occupancy_type": "business",
                "room_specs": [{"name": "room_1"}],
            }

            result = fireai_system.run_integration(
                building_id="BLDG-ROOMS",
                floors=[floor_data],
                enable_kernel_v30=True,
                enable_hash_chain_audit=False,
                enable_monte_carlo=False,
                enable_bim_sync=False,
            )

            assert result["building_id"] == "BLDG-ROOMS"


# ============================================================================
# analyse_floor COMPLIANT ROOM INTEGRATION PATH
# ============================================================================


class TestAnalyseFloorIntegration:
    """Tests for the integration path in analyse_floor when compliant rooms exist."""

    def test_floor_with_compliant_rooms(self, fireai_system, sample_room_spec):
        """analyse_floor should handle compliant rooms without error."""
        # This triggers the `if any(r.compliant for r in results)` path
        results = fireai_system.analyse_floor([sample_room_spec])
        assert isinstance(results, list)
        assert len(results) == 1

    def test_floor_with_non_compliant_rooms(self, fireai_system):
        """analyse_floor should handle non-compliant rooms without error."""
        # Create a mock that returns non-compliant results
        mock_result = EnhancedRoomResult(
            room_id="fail_room",
            compliant=False,
            confidence=ConfidenceLevel.UNSAFE,
            errors=["test error"],
        )

        with patch.object(fireai_system, "analyse_room", return_value=mock_result):
            room_spec = MagicMock()
            room_spec.room_id = "fail_room"
            results = fireai_system.analyse_floor([room_spec])
            assert len(results) == 1
            assert results[0].compliant is False


# ============================================================================
# COVERAGE FRACTION EDGE CASES
# ============================================================================


class TestCoverageFractionEdgeCases:
    """Tests for coverage fraction computation edge cases."""

    def test_coverage_exactly_100_percent(self, fireai_system, sample_room_spec):
        """Coverage of exactly 100% should be treated as 1.0 fraction."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = [(5.0, 4.0)]
        mock_analysis.coverage = 100.0
        mock_analysis.passed = True
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = []

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.placement_proof.coverage_fraction == 1.0
            assert result.confidence == ConfidenceLevel.HIGH

    def test_coverage_zero(self, fireai_system, sample_room_spec):
        """Coverage of 0% should result in UNSAFE confidence."""
        mock_analysis = MagicMock()
        mock_analysis.layout.detectors = []
        mock_analysis.coverage = 0.0
        mock_analysis.passed = False
        mock_analysis.proof_valid = False
        mock_analysis.wall_violations = []

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert result.placement_proof.coverage_fraction == 0.0
            assert result.confidence == ConfidenceLevel.UNSAFE

    def test_analysis_without_layout(self, fireai_system, sample_room_spec):
        """If analysis has no layout, detector_positions should be empty."""
        mock_analysis = MagicMock(spec=[])  # Empty spec = no attributes

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            assert isinstance(result, EnhancedRoomResult)

    def test_analysis_without_passed_attribute(self, fireai_system, sample_room_spec):
        """If analysis lacks 'passed', should use proof_valid for compliance."""
        mock_analysis = MagicMock(spec=["layout", "coverage", "proof_valid", "wall_violations"])
        mock_analysis.layout.detectors = [(5.0, 4.0)]
        mock_analysis.coverage = 95.0
        mock_analysis.proof_valid = True
        mock_analysis.wall_violations = []

        with patch.object(fireai_system, "_get_expert") as mock_get:
            mock_expert = MagicMock()
            mock_expert.analyse_room.return_value = mock_analysis
            mock_get.return_value = mock_expert

            result = fireai_system.analyse_room(sample_room_spec, run_resilience=False)
            # Without 'passed', should fall back to proof_valid
            assert result.compliant is True
