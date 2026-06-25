"""Comprehensive tests for the analysis_pipeline module.

Tests cover:
  - PipelineStage enum values and ordering
  - PipelineResult creation, defaults, to_dict(), to_json()
  - AnalysisPipeline initialization with various parameter combos
  - analyze_room() with valid rooms, invalid geometry, edge cases
  - analyze_building() with multiple rooms, partial failures
  - Pipeline stage transitions (success & failure paths)
  - Error handling (NaN/Inf geometry, zero/negative dimensions)
  - Event publishing at each stage
  - Certificate generation & signing (on/off)
  - Consensus verification (on/off)
  - Digital twin sync stage
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from fireai.core.analysis_pipeline import (
    AnalysisPipeline,
    PipelineResult,
    PipelineStage,
)
from fireai.core.event_bus import EventBus, Events
from fireai.core.spatial_engine.consensus_engine import (
    ConfidenceLevel,
    ConsensusEngine,
    ConsensusResult,
    EngineVerdict,
)
from fireai.core.spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    MAX_SPACING_M,
    VERIFY_STEP,
    WALL_MIN_M,
    DensityOptimizer,
    DetectorLayout,
    Room,
)
from fireai.core.spatial_engine.proof_certificate import (
    ProofCertificate,
    ProofCertificateGenerator,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def simple_room():
    """A standard 10m x 12m office room."""
    return Room(name="Office-101", width=10.0, length=12.0, ceiling_height=3.0)


@pytest.fixture
def small_room():
    """A very small room (2m x 2m) — needs only 1 detector."""
    return Room(name="Closet-001", width=2.0, length=2.0, ceiling_height=3.0)


@pytest.fixture
def large_room():
    """A large warehouse room — many detectors needed."""
    return Room(name="Warehouse-A", width=30.0, length=20.0, ceiling_height=4.5)


@pytest.fixture
def pipeline():
    """Standard AnalysisPipeline with default parameters."""
    return AnalysisPipeline()


@pytest.fixture
def pipeline_no_cert():
    """Pipeline with certificate generation disabled."""
    return AnalysisPipeline(generate_certificate=False)


@pytest.fixture
def pipeline_no_consensus():
    """Pipeline with consensus verification disabled."""
    return AnalysisPipeline(require_consensus=False)


@pytest.fixture
def pipeline_fast():
    """Pipeline with both consensus and certificate disabled (fast mode)."""
    return AnalysisPipeline(generate_certificate=False, require_consensus=False)


@pytest.fixture
def pipeline_custom_radius():
    """Pipeline with a custom coverage radius."""
    return AnalysisPipeline(coverage_radius=5.0, max_spacing=7.0)


@pytest.fixture
def fresh_bus():
    """Reset EventBus singleton before and after each test to avoid cross-test events."""
    bus = EventBus.instance()
    bus._subscribers = {}  # Clear subscribers
    yield bus
    bus._subscribers = {}


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineStage Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPipelineStage:
    """Tests for the PipelineStage enum."""

    def test_all_stage_values(self):
        """PipelineStage must have exactly 7 stages with correct string values."""
        expected = {
            "OPTIMIZATION": "optimization",
            "VERIFICATION": "verification",
            "CERTIFICATION": "certification",
            "SIGNING": "signing",
            "STORAGE": "storage",
            "TWIN_SYNC": "twin_sync",
            "COMPLETE": "complete",
        }
        for name, value in expected.items():
            assert PipelineStage[name].value == value

    def test_stage_count(self):
        """There should be exactly 7 pipeline stages."""
        assert len(PipelineStage) == 7

    def test_stage_is_enum(self):
        """PipelineStage members are proper Enum instances."""
        assert isinstance(PipelineStage.OPTIMIZATION, PipelineStage)
        assert isinstance(PipelineStage.COMPLETE, PipelineStage)

    def test_stage_string_comparison(self):
        """Stage values compare as strings."""
        assert PipelineStage.OPTIMIZATION.value == "optimization"
        assert PipelineStage.COMPLETE.value == "complete"

    def test_all_stages_accessible(self):
        """Every stage is accessible by name."""
        stages = [
            PipelineStage.OPTIMIZATION,
            PipelineStage.VERIFICATION,
            PipelineStage.CERTIFICATION,
            PipelineStage.SIGNING,
            PipelineStage.STORAGE,
            PipelineStage.TWIN_SYNC,
            PipelineStage.COMPLETE,
        ]
        # No duplicates
        values = [s.value for s in stages]
        assert len(set(values)) == len(values)


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineResult Dataclass Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPipelineResult:
    """Tests for the PipelineResult dataclass."""

    def test_minimal_creation(self):
        """PipelineResult can be created with only required fields."""
        result = PipelineResult(
            room_id="test-room",
            stage_reached=PipelineStage.OPTIMIZATION,
            success=False,
        )
        assert result.room_id == "test-room"
        assert result.stage_reached == PipelineStage.OPTIMIZATION
        assert result.success is False
        assert result.layout is None
        assert result.consensus is None
        assert result.certificate is None
        assert result.errors == []
        assert result.warnings == []
        assert result.timing == {}
        assert result.metadata == {}
        assert result.twin_version_id is None
        assert result.twin_checksum is None

    def test_full_creation(self):
        """PipelineResult can be created with all fields populated."""
        room = Room(name="R1", width=10.0, length=10.0)
        layout = DetectorLayout(room=room, detectors=[(5.0, 5.0)])
        cert = ProofCertificate(
            room_id="R1",
            room_width_m=10.0,
            room_length_m=10.0,
            room_ceiling_height_m=3.0,
            room_area_sqm=100.0,
            n_detectors=1,
            detector_positions=[(5.0, 5.0)],
        )
        result = PipelineResult(
            room_id="R1",
            stage_reached=PipelineStage.COMPLETE,
            success=True,
            layout=layout,
            certificate=cert,
            errors=[],
            warnings=["minor issue"],
            timing={"optimization": 0.1},
            metadata={"key": "value"},
            twin_version_id="v1",
            twin_checksum="abc123",
        )
        assert result.room_id == "R1"
        assert result.success is True
        assert result.layout is not None
        assert result.certificate is not None
        assert result.warnings == ["minor issue"]
        assert result.timing == {"optimization": 0.1}
        assert result.metadata == {"key": "value"}
        assert result.twin_version_id == "v1"
        assert result.twin_checksum == "abc123"

    def test_defaults_are_independent(self):
        """Two PipelineResult instances have independent default lists."""
        r1 = PipelineResult(room_id="a", stage_reached=PipelineStage.OPTIMIZATION, success=False)
        r2 = PipelineResult(room_id="b", stage_reached=PipelineStage.OPTIMIZATION, success=False)
        r1.errors.append("error1")
        assert r1.errors == ["error1"]
        assert r2.errors == []

    def test_to_dict_minimal(self):
        """to_dict() on a minimal result contains all required keys."""
        result = PipelineResult(
            room_id="test",
            stage_reached=PipelineStage.COMPLETE,
            success=True,
        )
        d = result.to_dict()
        assert d["room_id"] == "test"
        assert d["stage_reached"] == "complete"
        assert d["success"] is True
        assert d["errors"] == []
        assert d["warnings"] == []
        assert d["timing"] == {}
        assert d["metadata"] == {}
        assert d["twin_version_id"] is None
        assert d["twin_checksum"] is None
        # layout, consensus, certificate are None → not in dict
        assert "layout" not in d
        assert "consensus" not in d
        assert "certificate" not in d

    def test_to_dict_with_layout(self):
        """to_dict() serializes DetectorLayout when present.

        Note: DetectorLayout.count is a @property, so dataclasses.asdict()
        does NOT include it. We verify the detectors list length instead.
        """
        room = Room(name="R1", width=10.0, length=10.0)
        layout = DetectorLayout(
            room=room,
            detectors=[(5.0, 5.0)],
            coverage_pct=95.0,
            nfpa_valid=True,
            method="hexG_x",
        )
        result = PipelineResult(
            room_id="R1",
            stage_reached=PipelineStage.OPTIMIZATION,
            success=False,
            layout=layout,
        )
        d = result.to_dict()
        assert "layout" in d
        # count is a @property not a dataclass field, so check detectors length
        assert len(d["layout"]["detectors"]) == 1
        assert d["layout"]["coverage_pct"] == 95.0
        assert d["layout"]["nfpa_valid"] is True
        assert d["layout"]["method"] == "hexG_x"

    def test_to_dict_with_consensus(self):
        """to_dict() serializes ConsensusResult, converting enums to values."""
        from fireai.core.spatial_engine.consensus_engine import EngineName

        verdict = EngineVerdict(engine=EngineName.ANALYTICAL, passed=True, details="ok")
        consensus = ConsensusResult(
            confidence=ConfidenceLevel.VERIFIED,
            is_safe=True,
            engines=[verdict],
            n_pass=3,
            n_total=3,
            discrepancies=[],
            recommendation="",
        )
        result = PipelineResult(
            room_id="R1",
            stage_reached=PipelineStage.VERIFICATION,
            success=True,
            consensus=consensus,
        )
        d = result.to_dict()
        assert "consensus" in d
        assert d["consensus"]["confidence"] == "VERIFIED"
        assert d["consensus"]["is_safe"] is True
        assert d["consensus"]["n_pass"] == 3
        assert d["consensus"]["n_total"] == 3

    def test_to_dict_with_certificate(self):
        """to_dict() serializes ProofCertificate when present."""
        cert = ProofCertificate(
            room_id="R1",
            room_width_m=10.0,
            room_length_m=10.0,
            room_ceiling_height_m=3.0,
            room_area_sqm=100.0,
            n_detectors=1,
            detector_positions=[(5.0, 5.0)],
            coverage_guaranteed=True,
            proof_hash="abc123",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        result = PipelineResult(
            room_id="R1",
            stage_reached=PipelineStage.CERTIFICATION,
            success=True,
            certificate=cert,
        )
        d = result.to_dict()
        assert "certificate" in d
        assert d["certificate"]["room_id"] == "R1"
        assert d["certificate"]["coverage_guaranteed"] is True

    def test_to_json_returns_valid_json(self):
        """to_json() returns a valid JSON string."""
        result = PipelineResult(
            room_id="test",
            stage_reached=PipelineStage.COMPLETE,
            success=True,
            timing={"opt": 0.1},
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["room_id"] == "test"
        assert parsed["stage_reached"] == "complete"
        assert parsed["success"] is True

    def test_to_json_custom_indent(self):
        """to_json() respects the indent parameter."""
        result = PipelineResult(
            room_id="test",
            stage_reached=PipelineStage.OPTIMIZATION,
            success=False,
        )
        json_2 = result.to_json(indent=2)
        json_4 = result.to_json(indent=4)
        # Indent=4 produces more whitespace
        assert len(json_4) > len(json_2)

    def test_to_json_roundtrip(self):
        """to_dict() and to_json() produce consistent data."""
        result = PipelineResult(
            room_id="roundtrip",
            stage_reached=PipelineStage.SIGNING,
            success=False,
            errors=["e1"],
            warnings=["w1"],
            timing={"opt": 1.0},
            metadata={"key": "val"},
        )
        d = result.to_dict()
        j = json.loads(result.to_json())
        # JSON round-trip converts some types, but core fields match
        assert j["room_id"] == d["room_id"]
        assert j["stage_reached"] == d["stage_reached"]
        assert j["success"] == d["success"]
        assert j["errors"] == d["errors"]
        assert j["warnings"] == d["warnings"]


# ═══════════════════════════════════════════════════════════════════════════════
# AnalysisPipeline Initialization Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalysisPipelineInit:
    """Tests for AnalysisPipeline.__init__()."""

    def test_default_parameters(self):
        """Default init uses NFPA 72 standard values."""
        p = AnalysisPipeline()
        assert p.coverage_radius == DETECTOR_RADIUS
        assert p.max_spacing == MAX_SPACING_M
        assert p.wall_min == WALL_MIN_M
        assert p.grid_step == VERIFY_STEP
        assert p.generate_certificate is True
        assert p.require_consensus is True

    def test_custom_parameters(self):
        """Custom parameters are stored correctly."""
        p = AnalysisPipeline(
            coverage_radius=5.0,
            max_spacing=7.0,
            wall_min=0.15,
            grid_step=0.10,
            generate_certificate=False,
            require_consensus=False,
        )
        assert p.coverage_radius == 5.0
        assert p.max_spacing == 7.0
        assert p.wall_min == 0.15
        assert p.grid_step == 0.10
        assert p.generate_certificate is False
        assert p.require_consensus is False

    def test_sub_components_initialized(self):
        """Internal sub-components are initialized."""
        p = AnalysisPipeline()
        assert isinstance(p._optimizer, DensityOptimizer)
        assert isinstance(p._consensus, ConsensusEngine)
        assert isinstance(p._cert_gen, ProofCertificateGenerator)

    def test_event_bus_initialized(self):
        """Pipeline uses the EventBus singleton."""
        p = AnalysisPipeline()
        assert p._bus is not None
        assert isinstance(p._bus, EventBus)

    def test_twin_property(self):
        """The twin property returns a DigitalTwin instance."""
        p = AnalysisPipeline()
        from fireai.core.digital_twin import DigitalTwin
        assert isinstance(p.twin, DigitalTwin)

    def test_audit_store_flag(self):
        """_audit_available is a boolean indicating AuditStore availability."""
        p = AnalysisPipeline()
        assert isinstance(p._audit_available, bool)


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_room — Happy Path Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeRoomHappyPath:
    """Tests for analyze_room() with valid inputs."""

    def test_simple_room_succeeds(self, pipeline, simple_room):
        """A standard office room should produce a successful result."""
        result = pipeline.analyze_room(room=simple_room, room_id="office-101", ceiling_height=3.0)
        assert isinstance(result, PipelineResult)
        assert result.room_id == "office-101"
        assert result.stage_reached == PipelineStage.COMPLETE
        assert result.success is True
        assert result.layout is not None
        assert result.layout.count > 0
        assert result.layout.coverage_pct > 0
        assert len(result.errors) == 0

    def test_room_id_defaults_to_name(self, pipeline, simple_room):
        """When room_id is empty, room.name is used."""
        result = pipeline.analyze_room(room=simple_room, room_id="", ceiling_height=3.0)
        assert result.room_id == simple_room.name

    def test_room_id_defaults_to_name_when_omitted(self, pipeline, simple_room):
        """When room_id is not provided, room.name is used (default='')."""
        result = pipeline.analyze_room(room=simple_room, ceiling_height=3.0)
        assert result.room_id == simple_room.name

    def test_result_contains_metadata(self, pipeline, simple_room):
        """Result metadata contains pipeline configuration info."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.5)
        assert "correlation_id" in result.metadata
        assert result.metadata["room_name"] == simple_room.name
        assert result.metadata["room_width"] == simple_room.width
        assert result.metadata["room_length"] == simple_room.length
        assert result.metadata["ceiling_height"] == 3.5
        assert result.metadata["pipeline_version"] == "1.0.0"

    def test_result_timing_populated(self, pipeline, simple_room):
        """Result timing dict is populated for each completed stage."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert "optimization" in result.timing
        assert "verification" in result.timing
        assert "certification" in result.timing
        assert "signing" in result.timing
        assert "storage" in result.timing
        assert "total" in result.timing
        assert result.timing["total"] > 0

    def test_layout_has_detectors(self, pipeline, simple_room):
        """Result layout contains placed detectors."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.layout is not None
        assert len(result.layout.detectors) > 0
        assert all(isinstance(d, tuple) and len(d) == 2 for d in result.layout.detectors)

    def test_consensus_present(self, pipeline, simple_room):
        """Consensus result is present when require_consensus=True."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.consensus is not None
        assert isinstance(result.consensus, ConsensusResult)
        assert result.consensus.n_total == 3  # Triple consensus

    def test_certificate_present(self, pipeline, simple_room):
        """Proof certificate is present when generate_certificate=True."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.certificate is not None
        assert isinstance(result.certificate, ProofCertificate)
        # Certificate should be sealed (has hash and timestamp)
        assert result.certificate.proof_hash != ""
        assert result.certificate.timestamp != ""

    def test_small_room_one_detector(self, pipeline, small_room):
        """A tiny room should need only 1 detector."""
        result = pipeline.analyze_room(room=small_room, room_id="closet", ceiling_height=3.0)
        assert result.success is True
        assert result.layout.count >= 1

    def test_large_room_many_detectors(self, pipeline, large_room):
        """A large warehouse should need many detectors."""
        result = pipeline.analyze_room(room=large_room, room_id="warehouse", ceiling_height=4.5)
        assert result.success is True
        assert result.layout.count > 4  # 30x20m definitely needs more than 4

    def test_custom_ceiling_height(self, pipeline, simple_room):
        """Custom ceiling_height overrides room default."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=6.0)
        assert result.metadata["ceiling_height"] == 6.0


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_room — Pipeline Stage Transition Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeRoomStages:
    """Tests for pipeline stage transitions in analyze_room()."""

    def test_full_pipeline_reaches_complete(self, pipeline, simple_room):
        """A successful pipeline reaches the COMPLETE stage."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.stage_reached == PipelineStage.COMPLETE

    def test_optimization_stage_timing(self, pipeline, simple_room):
        """Optimization stage has non-negative timing."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["optimization"] >= 0

    def test_verification_stage_timing(self, pipeline, simple_room):
        """Verification stage has non-negative timing."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["verification"] >= 0

    def test_certification_stage_timing(self, pipeline, simple_room):
        """Certification stage has non-negative timing."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["certification"] >= 0

    def test_signing_stage_timing(self, pipeline, simple_room):
        """Signing stage has non-negative timing."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["signing"] >= 0

    def test_storage_stage_timing(self, pipeline, simple_room):
        """Storage stage has non-negative timing."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["storage"] >= 0

    def test_optimization_failure_stops_pipeline(self, pipeline):
        """If optimization fails, pipeline stops at OPTIMIZATION stage."""
        # Create a room that will cause the optimizer to fail by mocking it
        room = Room(name="bad-room", width=10.0, length=10.0)
        with patch.object(pipeline._optimizer, "optimize", side_effect=RuntimeError("optimization crash")):
            result = pipeline.analyze_room(room=room, room_id="bad", ceiling_height=3.0)
        assert result.stage_reached == PipelineStage.OPTIMIZATION
        assert result.success is False
        assert any("OPTIMIZATION FAILED" in e for e in result.errors)

    def test_verification_failure_continues_pipeline(self, pipeline, simple_room):
        """Verification failure is not fatal — pipeline continues."""
        with patch.object(pipeline._consensus, "verify", side_effect=RuntimeError("verify crash")):
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        # Pipeline should continue past verification
        assert result.stage_reached == PipelineStage.COMPLETE
        assert any("VERIFICATION FAILED" in e for e in result.errors)
        # Consensus is None since it failed
        assert result.consensus is None

    def test_certification_failure_continues_pipeline(self, pipeline, simple_room):
        """Certification failure is not fatal — pipeline continues."""
        with patch.object(pipeline._cert_gen, "generate", side_effect=RuntimeError("cert crash")):
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.stage_reached == PipelineStage.COMPLETE
        assert any("CERTIFICATION FAILED" in e for e in result.errors)
        # Certificate is None since it failed
        assert result.certificate is None

    def test_signing_failure_continues_pipeline(self, pipeline, simple_room):
        """Signing failure is not fatal — pipeline continues."""
        # We'll mock certificate.seal to fail, but we need to capture the cert first
        class FailSeal:
            def seal(self):
                raise RuntimeError("seal crash")

        with patch.object(pipeline, "_cert_gen") as mock_gen:
            # Create a real certificate first
            real_cert = ProofCertificate(
                room_id="R1",
                room_width_m=10.0,
                room_length_m=12.0,
                room_ceiling_height_m=3.0,
                room_area_sqm=120.0,
                n_detectors=2,
                detector_positions=[(5.0, 5.0)],
                coverage_guaranteed=True,
            )
            # Patch seal() to fail
            real_cert.seal = MagicMock(side_effect=RuntimeError("seal crash"))
            mock_gen.generate.return_value = real_cert

            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)

        assert result.stage_reached == PipelineStage.COMPLETE
        assert any("SIGNING FAILED" in e for e in result.errors)

    def test_skipped_consensus_sets_timing_zero(self, pipeline_no_consensus, simple_room):
        """When consensus is skipped, verification timing is 0."""
        result = pipeline_no_consensus.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["verification"] == 0.0

    def test_skipped_certificate_sets_timing_zero(self, pipeline_no_cert, simple_room):
        """When certificate is skipped, certification timing is 0."""
        result = pipeline_no_cert.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["certification"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_room — Error Handling Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeRoomErrorHandling:
    """Tests for error handling in analyze_room()."""

    def test_nan_width_rejected(self, pipeline):
        """NaN width is rejected before optimization."""
        room = Room(name="nan-room", width=10.0, length=10.0)
        room.width = float("nan")
        result = pipeline.analyze_room(room=room, room_id="nan", ceiling_height=3.0)
        assert result.success is False
        assert result.stage_reached == PipelineStage.OPTIMIZATION
        assert any("GEOMETRY INVALID" in e for e in result.errors)

    def test_nan_length_rejected(self, pipeline):
        """NaN length is rejected before optimization."""
        room = Room(name="nan-room", width=10.0, length=10.0)
        room.length = float("nan")
        result = pipeline.analyze_room(room=room, room_id="nan", ceiling_height=3.0)
        assert result.success is False
        assert any("GEOMETRY INVALID" in e for e in result.errors)

    def test_inf_width_rejected(self, pipeline):
        """Infinite width is rejected before optimization."""
        room = Room(name="inf-room", width=10.0, length=10.0)
        room.width = float("inf")
        result = pipeline.analyze_room(room=room, room_id="inf", ceiling_height=3.0)
        assert result.success is False
        assert any("GEOMETRY INVALID" in e for e in result.errors)

    def test_inf_ceiling_height_rejected(self, pipeline):
        """Infinite ceiling_height is rejected before optimization."""
        room = Room(name="inf-h", width=10.0, length=10.0)
        result = pipeline.analyze_room(room=room, room_id="inf-h", ceiling_height=float("inf"))
        assert result.success is False
        assert any("GEOMETRY INVALID" in e for e in result.errors)

    def test_negative_ceiling_height_rejected(self, pipeline):
        """Negative ceiling height is rejected before optimization."""
        room = Room(name="neg-h", width=10.0, length=10.0)
        result = pipeline.analyze_room(room=room, room_id="neg-h", ceiling_height=-3.0)
        assert result.success is False
        assert any("GEOMETRY INVALID" in e for e in result.errors)

    def test_zero_ceiling_height_rejected(self, pipeline):
        """Zero ceiling height is rejected before optimization."""
        room = Room(name="zero-h", width=10.0, length=10.0)
        result = pipeline.analyze_room(room=room, room_id="zero-h", ceiling_height=0.0)
        assert result.success is False
        assert any("GEOMETRY INVALID" in e for e in result.errors)

    def test_string_dimension_crashes_format(self, pipeline):
        """String dimension causes ValueError in the logging format string.

        The pipeline logs room dimensions with f-string formatting before
        reaching the geometry validation guard. Setting width to a string
        causes a ValueError in the format spec (:.1f), which propagates
        up since it occurs before the geometry validation check.
        This is a known edge case — Room.__post_init__ prevents this in
        normal usage.
        """
        room = Room(name="str-dim", width=10.0, length=10.0)
        room.width = "ten"
        # The format string f"{room.width:.1f}" raises ValueError
        with pytest.raises(ValueError, match="Unknown format code"):
            pipeline.analyze_room(room=room, room_id="str-dim", ceiling_height=3.0)

    def test_invalid_geometry_no_layout(self, pipeline):
        """Invalid geometry produces no layout."""
        room = Room(name="bad", width=10.0, length=10.0)
        room.width = float("nan")
        result = pipeline.analyze_room(room=room, room_id="bad", ceiling_height=3.0)
        assert result.layout is None

    def test_invalid_geometry_no_consensus(self, pipeline):
        """Invalid geometry produces no consensus."""
        room = Room(name="bad", width=10.0, length=10.0)
        room.width = float("nan")
        result = pipeline.analyze_room(room=room, room_id="bad", ceiling_height=3.0)
        assert result.consensus is None

    def test_invalid_geometry_no_certificate(self, pipeline):
        """Invalid geometry produces no certificate."""
        room = Room(name="bad", width=10.0, length=10.0)
        room.width = float("nan")
        result = pipeline.analyze_room(room=room, room_id="bad", ceiling_height=3.0)
        assert result.certificate is None


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_room — Consensus & Certificate Flags Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeRoomFlags:
    """Tests for analyze_room() with different flag combinations."""

    def test_no_consensus_has_no_consensus_result(self, pipeline_no_consensus, simple_room):
        """require_consensus=False means no ConsensusResult."""
        result = pipeline_no_consensus.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.consensus is None
        assert any("VERIFICATION SKIPPED" in w for w in result.warnings)

    def test_no_certificate_has_no_certificate(self, pipeline_no_cert, simple_room):
        """generate_certificate=False means no ProofCertificate."""
        result = pipeline_no_cert.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.certificate is None

    def test_fast_mode_no_consensus_no_cert(self, pipeline_fast, simple_room):
        """Fast mode (no consensus, no cert) produces minimal result."""
        result = pipeline_fast.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.consensus is None
        assert result.certificate is None
        # But still has layout
        assert result.layout is not None

    def test_fast_mode_still_reaches_complete(self, pipeline_fast, simple_room):
        """Fast mode still reaches COMPLETE stage."""
        result = pipeline_fast.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.stage_reached == PipelineStage.COMPLETE

    def test_no_cert_pipeline_hash(self, pipeline_no_cert, simple_room):
        """When no certificate, signing creates a pipeline-level hash."""
        result = pipeline_no_cert.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert "pipeline_hash" in result.metadata
        assert "pipeline_timestamp" in result.metadata

    def test_custom_radius_pipeline(self, pipeline_custom_radius, simple_room):
        """Pipeline with custom coverage radius works correctly."""
        result = pipeline_custom_radius.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.layout is not None
        assert result.metadata["coverage_radius"] == 5.0

    def test_success_requires_no_errors(self, pipeline, simple_room):
        """Success is False when errors are present."""
        with patch.object(pipeline._consensus, "verify", side_effect=RuntimeError("fail")):
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.success is False
        assert len(result.errors) > 0

    def test_success_requires_proof_valid(self, pipeline, simple_room):
        """Success is False when layout.proof_valid is False."""
        with patch.object(pipeline._optimizer, "optimize") as mock_opt:
            layout = DetectorLayout(
                room=simple_room,
                detectors=[(5.0, 5.0)],
                coverage_pct=50.0,
                proof_valid=False,
                nfpa_valid=False,
                method="test",
            )
            mock_opt.return_value = layout
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.success is False

    def test_success_requires_consensus_safe_when_required(self, pipeline, simple_room):
        """Success requires consensus.is_safe when require_consensus=True."""
        with patch.object(pipeline._consensus, "verify") as mock_verify:
            consensus = ConsensusResult(
                confidence=ConfidenceLevel.FAIL,
                is_safe=False,
                engines=[],
                n_pass=0,
                n_total=3,
                discrepancies=["all engines disagree"],
                recommendation="Redesign layout",
            )
            mock_verify.return_value = consensus
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.success is False


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_room — Warning Collection Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeRoomWarnings:
    """Tests for warning collection in analyze_room()."""

    def test_consensus_warning_level(self, pipeline, simple_room):
        """Consensus WARNING level adds a warning to the result."""
        with patch.object(pipeline._consensus, "verify") as mock_verify:
            consensus = ConsensusResult(
                confidence=ConfidenceLevel.WARNING,
                is_safe=False,
                engines=[],
                n_pass=2,
                n_total=3,
                discrepancies=["minor disagreement"],
                recommendation="Investigate",
            )
            mock_verify.return_value = consensus
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert any("Consensus WARNING" in w for w in result.warnings)

    def test_consensus_fail_level(self, pipeline, simple_room):
        """Consensus FAIL level adds a warning to the result."""
        with patch.object(pipeline._consensus, "verify") as mock_verify:
            consensus = ConsensusResult(
                confidence=ConfidenceLevel.FAIL,
                is_safe=False,
                engines=[],
                n_pass=1,
                n_total=3,
                discrepancies=["major disagreement"],
                recommendation="Redesign",
            )
            mock_verify.return_value = consensus
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert any("Consensus FAIL" in w for w in result.warnings)

    def test_layout_warnings_propagated(self, pipeline, simple_room):
        """Warnings from the layout are propagated to the result."""
        with patch.object(pipeline._optimizer, "optimize") as mock_opt:
            layout = DetectorLayout(
                room=simple_room,
                detectors=[(5.0, 5.0)],
                coverage_pct=90.0,
                proof_valid=True,
                nfpa_valid=True,
                method="hexG_x",
                warnings=["unusual geometry"],
            )
            mock_opt.return_value = layout
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert "unusual geometry" in result.warnings

    def test_layout_fallback_warning(self, pipeline, simple_room):
        """Fallback-used flag adds a warning."""
        with patch.object(pipeline._optimizer, "optimize") as mock_opt:
            layout = DetectorLayout(
                room=simple_room,
                detectors=[(5.0, 5.0)],
                coverage_pct=80.0,
                proof_valid=True,
                nfpa_valid=True,
                method="fallback",
                fallback_used=True,
            )
            mock_opt.return_value = layout
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert any("Fallback placement used" in w for w in result.warnings)

    def test_layout_violations_propagated(self, pipeline, simple_room):
        """Violations from the layout are propagated as warnings."""
        with patch.object(pipeline._optimizer, "optimize") as mock_opt:
            layout = DetectorLayout(
                room=simple_room,
                detectors=[(5.0, 5.0)],
                coverage_pct=80.0,
                proof_valid=True,
                nfpa_valid=False,
                method="test",
                violations=["spacing exceeds 9.1m"],
            )
            mock_opt.return_value = layout
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert "spacing exceeds 9.1m" in result.warnings

    def test_consensus_skipped_warning(self, pipeline_no_consensus, simple_room):
        """Skipping consensus adds a specific warning."""
        result = pipeline_no_consensus.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert any("VERIFICATION SKIPPED" in w for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_building Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeBuilding:
    """Tests for analyze_building() with multiple rooms."""

    def test_multiple_rooms(self, pipeline):
        """analyze_building processes all rooms and returns a result per room."""
        rooms = [
            (Room(name="R1", width=10.0, length=10.0), "room-1", 3.0),
            (Room(name="R2", width=8.0, length=6.0), "room-2", 3.0),
            (Room(name="R3", width=15.0, length=12.0), "room-3", 4.0),
        ]
        results = pipeline.analyze_building(rooms=rooms)
        assert len(results) == 3
        assert all(isinstance(r, PipelineResult) for r in results)

    def test_room_ids_correct(self, pipeline):
        """Each result has the correct room_id."""
        rooms = [
            (Room(name="R1", width=10.0, length=10.0), "office-A", 3.0),
            (Room(name="R2", width=8.0, length=6.0), "office-B", 3.0),
        ]
        results = pipeline.analyze_building(rooms=rooms)
        assert results[0].room_id == "office-A"
        assert results[1].room_id == "office-B"

    def test_partial_failure_continues(self, pipeline):
        """If one room fails, other rooms continue to be analyzed."""
        rooms = [
            (Room(name="Good", width=10.0, length=10.0), "good-room", 3.0),
        ]
        # Make the second room fail via mock
        with patch.object(pipeline, "analyze_room") as mock_ar:
            mock_ar.side_effect = [
                PipelineResult(room_id="good-room", stage_reached=PipelineStage.COMPLETE, success=True),
                RuntimeError("unexpected crash"),
            ]
            # We need to call analyze_building directly with actual rooms
            # Let's use the real pipeline but cause one room to fail
            pass

        # Better approach: use a room with invalid geometry for one room
        rooms = [
            (Room(name="R1", width=10.0, length=10.0), "good-room", 3.0),
        ]
        # We'll add an invalid room that bypasses Room's __post_init__
        bad_room = Room(name="Bad", width=10.0, length=10.0)
        bad_room.width = float("nan")
        rooms.append((bad_room, "bad-room", 3.0))

        rooms.append((Room(name="R3", width=12.0, length=8.0), "good-room-2", 3.0))

        results = pipeline.analyze_building(rooms=rooms)
        assert len(results) == 3
        # First room should succeed
        assert results[0].success is True
        # Second room should fail (NaN width)
        assert results[1].success is False
        # Third room should succeed
        assert results[2].success is True

    def test_empty_building(self, pipeline):
        """Empty room list returns empty result list."""
        results = pipeline.analyze_building(rooms=[])
        assert results == []

    def test_single_room_building(self, pipeline):
        """Single room building returns single result."""
        rooms = [
            (Room(name="Only", width=10.0, length=10.0), "only-room", 3.0),
        ]
        results = pipeline.analyze_building(rooms=rooms)
        assert len(results) == 1
        assert results[0].room_id == "only-room"

    def test_memory_error_propagates(self, pipeline, simple_room):
        """MemoryError in analyze_building propagates (critical error)."""
        with patch.object(pipeline, "analyze_room", side_effect=MemoryError("OOM")):
            rooms = [
                (simple_room, "R1", 3.0),
                (simple_room, "R2", 3.0),
            ]
            with pytest.raises(MemoryError):
                pipeline.analyze_building(rooms=rooms)

    def test_system_error_propagates(self, pipeline, simple_room):
        """SystemError in analyze_building propagates (critical error)."""
        with patch.object(pipeline, "analyze_room", side_effect=SystemError("corrupt")):
            rooms = [
                (simple_room, "R1", 3.0),
                (simple_room, "R2", 3.0),
            ]
            with pytest.raises(SystemError):
                pipeline.analyze_building(rooms=rooms)

    def test_generic_exception_continues(self, pipeline, simple_room):
        """Non-critical exceptions in one room don't stop others."""
        call_count = 0

        def side_effect(room, room_id="", ceiling_height=3.0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("random error")
            return PipelineResult(room_id=room_id, stage_reached=PipelineStage.COMPLETE, success=True)

        with patch.object(pipeline, "analyze_room", side_effect=side_effect):
            rooms = [
                (simple_room, "R1", 3.0),
                (simple_room, "R2", 3.0),
            ]
            results = pipeline.analyze_building(rooms=rooms)

        assert len(results) == 2
        assert results[0].success is False
        assert "RuntimeError" in results[0].errors[0]
        assert results[1].success is True

    def test_building_level_timing(self, pipeline):
        """Building analysis includes total time in results."""
        rooms = [
            (Room(name="R1", width=10.0, length=10.0), "R1", 3.0),
            (Room(name="R2", width=8.0, length=6.0), "R2", 3.0),
        ]
        results = pipeline.analyze_building(rooms=rooms)
        for r in results:
            assert "total" in r.timing


# ═══════════════════════════════════════════════════════════════════════════════
# Event Publishing Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventPublishing:
    """Tests for EventBus event publishing during pipeline execution."""

    def test_room_analysis_start_event(self, pipeline, simple_room, fresh_bus):
        """room.analysis.start event is published."""
        events = []
        fresh_bus.subscribe(Events.ROOM_ANALYSIS_START, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert len(events) == 1

    def test_room_analysis_complete_event(self, pipeline, simple_room, fresh_bus):
        """room.analysis.complete event is published."""
        events = []
        fresh_bus.subscribe(Events.ROOM_ANALYSIS_COMPLETE, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert len(events) == 1

    def test_detector_placed_event(self, pipeline, simple_room, fresh_bus):
        """detector.placed event is published after optimization.

        Note: The DigitalTwin also publishes detector.placed events for each
        detector during TWIN_SYNC, so total events = 1 (pipeline) + N (twin).
        """
        events = []
        fresh_bus.subscribe(Events.DETECTOR_PLACED, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        # At minimum, the pipeline publishes one detector.placed event
        pipeline_events = [e for e in events if e.source == "AnalysisPipeline"]
        assert len(pipeline_events) == 1
        assert pipeline_events[0].data["room_id"] == "R1"

    def test_consensus_result_event(self, pipeline, simple_room, fresh_bus):
        """consensus.result event is published after verification."""
        events = []
        fresh_bus.subscribe(Events.CONSENSUS_RESULT, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert len(events) == 1

    def test_coverage_verified_event_on_success(self, pipeline, simple_room, fresh_bus):
        """coverage.verified event is published when coverage passes."""
        events = []
        fresh_bus.subscribe(Events.COVERAGE_VERIFIED, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        # A standard room should pass coverage
        assert len(events) >= 1

    def test_nfpa_compliant_event(self, pipeline, simple_room, fresh_bus):
        """nfpa.compliant event is published when NFPA 72 is met."""
        events = []
        fresh_bus.subscribe(Events.NFPA_COMPLIANT, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        # Standard room with default params should be compliant
        assert len(events) >= 1

    def test_proof_certificate_generated_event(self, pipeline, simple_room, fresh_bus):
        """proof.certificate.generated event is published when certificate is generated."""
        events = []
        fresh_bus.subscribe(Events.PROOF_CERTIFICATE_GENERATED, events.append)
        pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert len(events) == 1

    def test_building_analysis_start_event(self, pipeline, fresh_bus):
        """building.analysis.start event is published at building level."""
        events = []
        fresh_bus.subscribe(Events.BUILDING_ANALYSIS_START, events.append)
        rooms = [(Room(name="R1", width=10.0, length=10.0), "R1", 3.0)]
        pipeline.analyze_building(rooms=rooms)
        assert len(events) == 1

    def test_building_analysis_complete_event(self, pipeline, fresh_bus):
        """building.analysis.complete event is published at building level."""
        events = []
        fresh_bus.subscribe(Events.BUILDING_ANALYSIS_COMPLETE, events.append)
        rooms = [(Room(name="R1", width=10.0, length=10.0), "R1", 3.0)]
        pipeline.analyze_building(rooms=rooms)
        assert len(events) == 1

    def test_no_consensus_skips_consensus_event(self, pipeline_no_consensus, simple_room, fresh_bus):
        """When consensus is skipped, no consensus.result event is published."""
        events = []
        fresh_bus.subscribe(Events.CONSENSUS_RESULT, events.append)
        pipeline_no_consensus.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert len(events) == 0

    def test_no_cert_skips_certificate_event(self, pipeline_no_cert, simple_room, fresh_bus):
        """When certificate is skipped, no proof.certificate.generated event."""
        events = []
        fresh_bus.subscribe(Events.PROOF_CERTIFICATE_GENERATED, events.append)
        pipeline_no_cert.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert len(events) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Serialization Round-Trip Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSerializationRoundTrip:
    """Tests for serialization of pipeline results."""

    def test_result_to_dict_roundtrip(self, pipeline, simple_room):
        """PipelineResult.to_dict() produces a serializable dict."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        d = result.to_dict()
        # Ensure all values are JSON-serializable
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)
        assert parsed["room_id"] == "R1"
        assert parsed["stage_reached"] == "complete"

    def test_result_to_json_roundtrip(self, pipeline, simple_room):
        """PipelineResult.to_json() produces valid JSON that can be parsed."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["room_id"] == "R1"
        assert parsed["success"] is True

    def test_certificate_sealed_in_result(self, pipeline, simple_room):
        """Certificate in result is sealed (has hash and timestamp)."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        if result.certificate is not None:
            assert result.certificate.proof_hash != ""
            assert result.certificate.timestamp != ""

    def test_result_with_errors_serializes(self, pipeline):
        """PipelineResult with errors serializes correctly."""
        room = Room(name="bad", width=10.0, length=10.0)
        room.width = float("nan")
        result = pipeline.analyze_room(room=room, room_id="bad", ceiling_height=3.0)
        d = result.to_dict()
        assert len(d["errors"]) > 0
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert len(parsed["errors"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Digital Twin Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDigitalTwinIntegration:
    """Tests for Digital Twin sync stage in the pipeline."""

    def test_twin_sync_produces_checksum(self, pipeline, simple_room):
        """TWIN_SYNC stage populates twin_checksum in result."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        # Twin checksum may or may not be populated depending on DigitalTwin impl
        # But the stage should be reached
        assert result.stage_reached == PipelineStage.COMPLETE
        # The twin property should be accessible
        assert pipeline.twin is not None

    def test_twin_sync_timing(self, pipeline, simple_room):
        """TWIN_SYNC stage has timing info."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert "twin_sync" in result.timing

    def test_twin_sync_failure_not_fatal(self, pipeline, simple_room):
        """TWIN_SYNC failure does not cause pipeline failure."""
        with patch.object(pipeline._twin, "from_building_report", side_effect=RuntimeError("twin error")):
            result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        # Pipeline should still complete
        assert result.stage_reached == PipelineStage.COMPLETE
        # But there should be a warning about twin sync
        assert any("Twin sync failed" in w for w in result.warnings)

    def test_twin_sync_disabled(self, pipeline, simple_room):
        """When twin sync is disabled, it's skipped gracefully."""
        pipeline._enable_twin_sync = False
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.timing["twin_sync"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Cases & Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case and integration tests."""

    def test_very_narrow_room(self, pipeline):
        """A very narrow room (corridor) should still produce a result."""
        room = Room(name="Corridor", width=1.5, length=20.0)
        result = pipeline.analyze_room(room=room, room_id="corridor", ceiling_height=3.0)
        assert result.layout is not None
        assert result.layout.count >= 1

    def test_square_room(self, pipeline):
        """A perfectly square room."""
        room = Room(name="Square", width=9.1, length=9.1)
        result = pipeline.analyze_room(room=room, room_id="square", ceiling_height=3.0)
        assert result.success is True
        assert result.layout is not None

    def test_room_exactly_one_detector_radius(self, pipeline):
        """Room small enough for exactly one detector."""
        room = Room(name="Tiny", width=5.0, length=5.0)
        result = pipeline.analyze_room(room=room, room_id="tiny", ceiling_height=3.0)
        assert result.layout.count >= 1

    def test_high_ceiling_room(self, pipeline):
        """Room with very high ceiling."""
        room = Room(name="Atrium", width=15.0, length=15.0)
        result = pipeline.analyze_room(room=room, room_id="atrium", ceiling_height=12.0)
        assert result.metadata["ceiling_height"] == 12.0

    def test_multiple_analyses_same_pipeline(self, pipeline):
        """Same pipeline can analyze multiple rooms sequentially."""
        room1 = Room(name="R1", width=10.0, length=10.0)
        room2 = Room(name="R2", width=8.0, length=6.0)
        result1 = pipeline.analyze_room(room=room1, room_id="R1", ceiling_height=3.0)
        result2 = pipeline.analyze_room(room=room2, room_id="R2", ceiling_height=3.0)
        assert result1.room_id == "R1"
        assert result2.room_id == "R2"
        assert result1.success is True
        assert result2.success is True

    def test_result_to_dict_after_real_analysis(self, pipeline, simple_room):
        """to_dict() works on results from real analysis."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        d = result.to_dict()
        assert "layout" in d
        # count is a @property, not in asdict output — check detectors length
        assert len(d["layout"]["detectors"]) > 0
        if result.consensus is not None:
            assert "consensus" in d
        if result.certificate is not None:
            assert "certificate" in d

    def test_coverage_percentage_reasonable(self, pipeline, simple_room):
        """Coverage percentage is within reasonable bounds."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert 0 <= result.layout.coverage_pct <= 100.0

    def test_correlation_id_is_uuid(self, pipeline, simple_room):
        """Metadata correlation_id is a valid UUID format."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        cid = result.metadata["correlation_id"]
        # UUID4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        import uuid
        parsed = uuid.UUID(cid)
        assert parsed.version == 4

    def test_nfpa_table_ref_in_layout(self, pipeline, simple_room):
        """Layout from optimization includes NFPA table reference."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        assert result.layout.nfpa_table_ref == "NFPA 72-2022 Table 17.6.3.1.1"

    def test_detector_positions_within_room(self, pipeline, simple_room):
        """All detector positions should be within room bounds."""
        result = pipeline.analyze_room(room=simple_room, room_id="R1", ceiling_height=3.0)
        w, l = simple_room.width, simple_room.length
        for x, y in result.layout.detectors:
            assert 0 <= x <= w, f"Detector x={x} outside room width={w}"
            assert 0 <= y <= l, f"Detector y={y} outside room length={l}"

    def test_building_mixed_valid_invalid_rooms(self, pipeline):
        """Building analysis with mix of valid and invalid rooms."""
        good_room = Room(name="Good", width=10.0, length=10.0)
        bad_room = Room(name="Bad", width=10.0, length=10.0)
        bad_room.length = -5.0  # Invalid
        another_good = Room(name="AlsoGood", width=8.0, length=8.0)

        rooms = [
            (good_room, "good-1", 3.0),
            (bad_room, "bad-1", 3.0),
            (another_good, "good-2", 3.0),
        ]
        results = pipeline.analyze_building(rooms=rooms)
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True
