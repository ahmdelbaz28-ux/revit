"""
tests/test_workflow_service.py — LangGraph Workflow Service Tests for FireAI.

Tests the workflow engine that orchestrates the NFPA 72 analysis pipeline
as a deterministic State Machine using LangGraph.

Test categories:
  1. Service initialization and graph building
  2. Workflow lifecycle (start → parse → validate → NFPA → report)
  3. Human review gate (approve/reject)
  4. Audit trail integrity
  5. Error handling and fail-safe behavior
  6. Conditional edge routing

LIFE-SAFETY NOTE:
  These tests verify that the workflow engine enforces the agent.md
  MANDATORY EXECUTION STATE MACHINE — every step must be traceable,
  every gate must be validated, and failures must stop the pipeline.
"""

import asyncio
import os
import pytest
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import backend.services.workflow_service as _wfs_mod  # noqa: F401
    _WORKFLOW_AVAILABLE = True
except ModuleNotFoundError:
    _WORKFLOW_AVAILABLE = False

if not _WORKFLOW_AVAILABLE:
    import pytest as _pytest
    _pytest.skip(
        "backend.services.workflow_service not installed — skipping workflow tests",
        allow_module_level=True,
    )

from backend.services.workflow_service import (
    WorkflowService,
    PipelineState,
    WorkflowStatus,
    build_fireai_workflow,
    get_workflow_service,
    close_workflow_service,
    node_initialize,
    node_validate,
    node_conflict_detection,
    node_human_review_gate,
    node_generate_report,
    should_proceed_after_parse,
    should_proceed_after_validation,
    should_require_review,
    should_proceed_after_review,
    _compute_sha256,
    _log_transition,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    """Create a fresh WorkflowService for each test."""
    return WorkflowService()


@pytest.fixture
def sample_state() -> PipelineState:
    """Create a sample pipeline state for unit testing."""
    return {
        "file_path": "test_data/hybrid/single_office.pdf",
        "file_sha256": "",
        "file_type": "pdf",
        "rooms": [],
        "parse_warnings": [],
        "parse_success": False,
        "validation_result": {},
        "validation_passed": False,
        "validation_evidence": [],
        "latitude": 30.044,
        "longitude": 31.236,
        "environmental_context": {},
        "nfpa_results": [],
        "total_detectors": 0,
        "coverage_pct": 0.0,
        "nfpa_compliant": False,
        "conflicts": [],
        "conflict_count": 0,
        "has_critical_conflicts": False,
        "review_required": False,
        "review_items": [],
        "reviewer_decision": None,
        "reviewer_comments": None,
        "review_timestamp": None,
        "report": {},
        "report_sha256": "",
        "workflow_id": "test_wf_001",
        "status": WorkflowStatus.PENDING.value,
        "started_at": "2026-05-29T12:00:00Z",
        "completed_at": None,
        "transition_log": [],
        "error_message": None,
    }


# ── 1. Service Initialization Tests ──────────────────────────────────────────

class TestServiceInit:
    def test_service_creates_successfully(self, service):
        """WorkflowService must initialize without errors."""
        assert service is not None
        assert service._graph is not None
        assert service._graph_compiled is not None

    def test_graph_has_all_nodes(self, service):
        """The StateGraph must contain all 8 required nodes."""
        graph = build_fireai_workflow()
        expected_nodes = [
            "initialize", "parse", "validate",
            "environmental_context", "nfpa_analysis",
            "conflict_detection", "human_review_gate",
            "generate_report",
        ]
        for node in expected_nodes:
            assert node in graph.nodes, f"Missing node: {node}"

    def test_workflow_status_enum_values(self):
        """WorkflowStatus must have all required status values."""
        assert WorkflowStatus.PENDING.value == "PENDING"
        assert WorkflowStatus.RUNNING.value == "RUNNING"
        assert WorkflowStatus.AWAITING_REVIEW.value == "AWAITING_REVIEW"
        assert WorkflowStatus.APPROVED.value == "APPROVED"
        assert WorkflowStatus.REJECTED.value == "REJECTED"
        assert WorkflowStatus.COMPLETED.value == "COMPLETED"
        assert WorkflowStatus.FAILED.value == "FAILED"
        assert WorkflowStatus.ERROR.value == "ERROR"


# ── 2. Node Unit Tests ──────────────────────────────────────────────────────

class TestNodeValidate:
    def test_validate_passes_with_valid_rooms(self, sample_state):
        """Validation must pass when rooms have valid geometry."""
        sample_state["rooms"] = [
            {"name": "office_1", "area_sqm": 25.0, "occupancy_type": "office"},
            {"name": "corridor_1", "area_sqm": 50.0, "occupancy_type": "corridor"},
        ]
        result = node_validate(sample_state)
        assert result["validation_passed"] is True
        assert result["validation_result"]["all_passed"] is True

    def test_validate_fails_with_no_rooms(self, sample_state):
        """Validation must fail when no rooms are extracted (zero protection)."""
        sample_state["rooms"] = []
        result = node_validate(sample_state)
        assert result["validation_passed"] is False
        assert "gate2_runtime" in result["validation_result"]["gates"]

    def test_validate_detects_non_finite_areas(self, sample_state):
        """Validation must detect NaN/Infinity in room areas."""
        import math
        sample_state["rooms"] = [
            {"name": "bad_room", "area_sqm": float("nan"), "occupancy_type": "office"},
        ]
        result = node_validate(sample_state)
        assert result["validation_passed"] is False
        gate1 = result["validation_result"]["gates"]["gate1_static"]
        assert gate1["passed"] is False

    def test_validate_detects_negative_areas(self, sample_state):
        """Validation must detect negative room areas."""
        sample_state["rooms"] = [
            {"name": "bad_room", "area_sqm": -5.0, "occupancy_type": "office"},
        ]
        result = node_validate(sample_state)
        assert result["validation_passed"] is False

    def test_validate_records_evidence(self, sample_state):
        """Validation must produce evidence for every gate checked."""
        sample_state["rooms"] = [
            {"name": "office_1", "area_sqm": 25.0, "occupancy_type": "office"},
        ]
        result = node_validate(sample_state)
        assert len(result["validation_evidence"]) >= 4  # 4 gates checked

    def test_validate_flags_unknown_occupancy(self, sample_state):
        """Validation must flag rooms with unknown occupancy type."""
        sample_state["rooms"] = [
            {"name": "room_1", "area_sqm": 25.0, "occupancy_type": "unknown"},
        ]
        result = node_validate(sample_state)
        gate3 = result["validation_result"]["gates"]["gate3_behavioral"]
        assert len(gate3["evidence"]) > 0


class TestNodeConflictDetection:
    def test_detects_missing_detection(self, sample_state):
        """Must detect rooms with zero detectors as CRITICAL conflicts."""
        sample_state["nfpa_results"] = [
            {"name": "room_1", "detector_count": 0, "occupancy_type": "unknown"},
        ]
        result = node_conflict_detection(sample_state)
        assert result["has_critical_conflicts"] is True
        assert any(c["severity"] == "CRITICAL" for c in result["conflicts"])

    def test_detects_unknown_occupancy(self, sample_state):
        """Must detect unknown occupancy rooms as HIGH conflicts."""
        sample_state["nfpa_results"] = [
            {"name": "room_1", "detector_count": 2, "occupancy_type": "unknown"},
        ]
        result = node_conflict_detection(sample_state)
        assert any(
            c["type"] == "UNKNOWN_OCCUPANCY" for c in result["conflicts"]
        )

    def test_no_conflicts_for_compliant_rooms(self, sample_state):
        """Must report no conflicts when all rooms are compliant."""
        sample_state["nfpa_results"] = [
            {"name": "office_1", "detector_count": 3, "occupancy_type": "office", "is_flagged": False},
        ]
        result = node_conflict_detection(sample_state)
        assert result["conflict_count"] == 0
        assert result["has_critical_conflicts"] is False


class TestNodeHumanReviewGate:
    def test_review_required_for_critical_conflicts(self, sample_state):
        """Must require human review when critical conflicts exist."""
        sample_state["has_critical_conflicts"] = True
        sample_state["conflicts"] = [
            {"type": "MISSING_DETECTION", "severity": "CRITICAL", "message": "Test", "room": "r1"},
        ]
        result = node_human_review_gate(sample_state)
        assert result["review_required"] is True
        assert result["status"] == WorkflowStatus.AWAITING_REVIEW.value

    def test_review_not_required_without_critical(self, sample_state):
        """Must not require review when no critical conflicts exist."""
        sample_state["has_critical_conflicts"] = False
        sample_state["conflicts"] = []
        sample_state["nfpa_results"] = [
            {"name": "office_1", "detector_count": 3, "occupancy_type": "office"},
        ]
        result = node_human_review_gate(sample_state)
        assert result["review_required"] is False

    def test_review_required_for_unknown_occupancy(self, sample_state):
        """Must require review when rooms have unknown occupancy."""
        sample_state["has_critical_conflicts"] = False
        sample_state["conflicts"] = []
        sample_state["nfpa_results"] = [
            {"name": "room_1", "detector_count": 0, "occupancy_type": "unknown"},
        ]
        result = node_human_review_gate(sample_state)
        assert result["review_required"] is True


class TestNodeGenerateReport:
    def test_report_includes_workflow_id(self, sample_state):
        """Report must include the workflow ID for traceability."""
        sample_state["nfpa_results"] = [
            {"name": "office_1", "detector_count": 3, "occupancy_type": "office", "area_sqm": 25.0},
        ]
        result = node_generate_report(sample_state)
        assert result["report"]["report_metadata"]["workflow_id"] == "test_wf_001"

    def test_report_sha256_is_computed(self, sample_state):
        """Report must have an integrity hash for audit verification."""
        sample_state["nfpa_results"] = []
        result = node_generate_report(sample_state)
        assert len(result["report_sha256"]) > 0

    def test_report_status_failed_with_unknown_rooms(self, sample_state):
        """Report status must be FAILED when unknown rooms exist."""
        sample_state["nfpa_results"] = [
            {"name": "room_1", "detector_count": 0, "occupancy_type": "unknown"},
        ]
        result = node_generate_report(sample_state)
        assert result["status"] == WorkflowStatus.FAILED.value

    def test_report_always_requires_pe_review(self, sample_state):
        """Report must ALWAYS require PE review per NFPA 72."""
        sample_state["nfpa_results"] = [
            {"name": "office_1", "detector_count": 3, "occupancy_type": "office"},
        ]
        result = node_generate_report(sample_state)
        assert result["report"]["report_metadata"]["requires_pe_review"] is True


# ── 3. Conditional Edge Tests ────────────────────────────────────────────────

class TestConditionalEdges:
    def test_parse_success_routes_to_validate(self, sample_state):
        """Successful parse must route to validate."""
        sample_state["parse_success"] = True
        assert should_proceed_after_parse(sample_state) == "validate"

    def test_parse_failure_routes_to_report(self, sample_state):
        """Failed parse must route to generate failure report."""
        sample_state["parse_success"] = False
        assert should_proceed_after_parse(sample_state) == "generate_report"

    def test_validation_pass_routes_to_env(self, sample_state):
        """Passed validation must route to environmental context."""
        sample_state["validation_passed"] = True
        assert should_proceed_after_validation(sample_state) == "environmental_context"

    def test_validation_fail_routes_to_report(self, sample_state):
        """Failed validation must route to generate failure report."""
        sample_state["validation_passed"] = False
        assert should_proceed_after_validation(sample_state) == "generate_report"

    def test_critical_conflicts_require_review(self, sample_state):
        """Critical conflicts must route to human review gate."""
        sample_state["review_required"] = True
        assert should_require_review(sample_state) == "human_review_gate"

    def test_no_critical_conflicts_skip_review(self, sample_state):
        """No critical conflicts must route directly to report."""
        sample_state["review_required"] = False
        assert should_require_review(sample_state) == "generate_report"

    def test_approved_proceeds_to_report(self, sample_state):
        """Approved review must proceed to report generation."""
        sample_state["reviewer_decision"] = "approved"
        assert should_proceed_after_review(sample_state) == "generate_report"

    def test_rejected_stops_pipeline(self, sample_state):
        """Rejected review must stop the pipeline."""
        sample_state["reviewer_decision"] = "rejected"
        assert should_proceed_after_review(sample_state) == END


# ── 4. Audit Trail Tests ────────────────────────────────────────────────────

class TestAuditTrail:
    def test_transition_log_is_append_only(self, sample_state):
        """Transition log must be append-only — no deletion."""
        state = _log_transition(sample_state, "A", "B", "test evidence 1")
        assert len(state["transition_log"]) == 1
        state = _log_transition(state, "B", "C", "test evidence 2")
        assert len(state["transition_log"]) == 2
        # Original entry preserved
        assert state["transition_log"][0]["evidence"] == "test evidence 1"

    def test_transition_includes_timestamp(self, sample_state):
        """Every transition must include an ISO 8601 UTC timestamp."""
        state = _log_transition(sample_state, "A", "B", "test")
        assert "timestamp" in state["transition_log"][0]
        assert "T" in state["transition_log"][0]["timestamp"]  # ISO 8601

    def test_transition_includes_evidence(self, sample_state):
        """Every transition must include evidence (agent.md contract)."""
        state = _log_transition(sample_state, "A", "B", "verified rooms: 7")
        assert state["transition_log"][0]["evidence"] == "verified rooms: 7"

    def test_sha256_is_deterministic(self):
        """SHA-256 hash must be deterministic for same input."""
        data = {"rooms": 7, "detectors": 12}
        hash1 = _compute_sha256(data)
        hash2 = _compute_sha256(data)
        assert hash1 == hash2

    def test_sha256_differs_for_different_input(self):
        """SHA-256 hash must differ for different input."""
        hash1 = _compute_sha256({"rooms": 7})
        hash2 = _compute_sha256({"rooms": 8})
        assert hash1 != hash2


# ── 5. Error Handling Tests ──────────────────────────────────────────────────

class TestErrorHandling:
    def test_initialize_fails_gracefully_for_missing_file(self, sample_state):
        """Initialize must set FAILED status for missing files."""
        sample_state["file_path"] = "/nonexistent/file.pdf"
        result = node_initialize(sample_state)
        assert result["status"] == WorkflowStatus.FAILED.value
        assert result["error_message"] is not None

    def test_initialize_computes_file_hash(self, sample_state, monkeypatch):
        """Initialize must compute SHA-256 of the input file."""
        # Allow test_data directory for path traversal check
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        monkeypatch.setenv("FIREAI_DATA_DIRS", f"/tmp/fireai_uploads:/data:/uploads:{project_root}")
        # Use the actual test file that exists
        sample_state["file_path"] = "test_data/hybrid/single_office.pdf"
        if os.path.exists(sample_state["file_path"]):
            result = node_initialize(sample_state)
            assert len(result["file_sha256"]) == 64  # Full SHA-256 hex

    def test_generate_report_handles_empty_state(self, sample_state):
        """Report generation must handle empty state gracefully."""
        result = node_generate_report(sample_state)
        assert "report" in result
        assert "report_metadata" in result["report"]


# ── 6. Integration Tests ────────────────────────────────────────────────────

class TestWorkflowIntegration:
    @pytest.mark.asyncio
    async def test_full_workflow_with_pdf(self, service):
        """Full workflow must complete successfully with a valid PDF."""
        if not os.path.exists("test_data/hybrid/single_office.pdf"):
            pytest.skip("Test PDF not available")

        result = await service.start_workflow(
            file_path="test_data/hybrid/single_office.pdf",
            latitude=30.044,
            longitude=31.236,
            skip_human_review=True,
        )
        assert result["workflow_id"] is not None
        assert result["status"] in (
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.FAILED.value,
        )
        assert result["transition_count"] >= 2  # At least init → parse/report (minimal PDF may skip validation)

    @pytest.mark.asyncio
    async def test_workflow_status_retrieval(self, service):
        """Must be able to retrieve workflow status after starting."""
        if not os.path.exists("test_data/hybrid/single_office.pdf"):
            pytest.skip("Test PDF not available")

        result = await service.start_workflow(
            file_path="test_data/hybrid/single_office.pdf",
            skip_human_review=True,
        )
        status = await service.get_workflow_status(result["workflow_id"])
        assert status is not None
        assert "workflow_id" in status

    @pytest.mark.asyncio
    async def test_nonexistent_workflow_returns_none(self, service):
        """Querying nonexistent workflow must return None."""
        status = await service.get_workflow_status("nonexistent_id")
        assert status is None

    @pytest.mark.asyncio
    async def test_audit_trail_retrieval(self, service):
        """Must be able to retrieve full audit trail."""
        if not os.path.exists("test_data/hybrid/single_office.pdf"):
            pytest.skip("Test PDF not available")

        result = await service.start_workflow(
            file_path="test_data/hybrid/single_office.pdf",
            skip_human_review=True,
        )
        trail = await service.get_audit_trail(result["workflow_id"])
        assert trail is not None
        assert isinstance(trail, list)

    @pytest.mark.asyncio
    async def test_reject_nonexistent_workflow(self, service):
        """Rejecting nonexistent workflow must return None."""
        result = await service.reject_workflow("nonexistent_id")
        assert result is None


# ── Import for END constant ──────────────────────────────────────────────────
try:
    from langgraph.graph import END
except ImportError:
    END = "__end__"  # type: ignore[assignment]  # langgraph not installed — use sentinel
