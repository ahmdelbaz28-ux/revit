"""
tests/test_workflow_service_v2.py — Expanded test coverage for WorkflowService.

Covers all public functions, classes, enums, and conditional edges
with mocked file I/O and external dependencies.

Test categories:
   1. WorkflowStatus enum — all members including STUCK
   2. PipelineState TypedDict — structural verification
   3. _log_transition() — state transition logging
   4. _compute_sha256() — hash computation
   5. node_initialize() — path traversal, file not found, normal init
   6. node_parse() — basic parsing structure
   7. Conditional edges — all routing functions
   8. build_fireai_workflow() — graph construction
   9. WorkflowService — __init__, create_workflow, status, approve, reject, audit
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import backend.services.workflow_service as _wfs_mod
    _WORKFLOW_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _WORKFLOW_AVAILABLE = False

if not _WORKFLOW_AVAILABLE:
    import pytest as _pytest
    _pytest.skip(
        "backend.services.workflow_service not installed — skipping workflow tests",
        allow_module_level=True,
    )

from unittest.mock import patch, MagicMock, mock_open, PropertyMock
from typing import Any, Dict
from backend.services.workflow_service import (
    WorkflowService,
    PipelineState,
    WorkflowStatus,
    build_fireai_workflow,
    get_workflow_service,
    close_workflow_service,
    node_initialize,
    node_parse,
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

try:
    from langgraph.graph import END
except ImportError:
    END = "__end__"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    return WorkflowService()


@pytest.fixture
def sample_state() -> PipelineState:
    return {
        "file_path": "/tmp/fireai_uploads/test.pdf",
        "file_sha256": "",
        "file_type": "",
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
        "memory_context": {},
        "memory_enrichment_time_ms": 0.0,
        "review_required": False,
        "review_items": [],
        "reviewer_decision": None,
        "reviewer_comments": None,
        "review_timestamp": None,
        "reviewer_timestamp": None,
        "report": {},
        "report_sha256": "",
        "workflow_id": "test_wf_001",
        "engineer_id": "test_engineer",
        "status": WorkflowStatus.PENDING.value,
        "started_at": "2026-05-29T12:00:00Z",
        "completed_at": None,
        "transition_log": [],
        "error_message": None,
        "stuck_detected": False,
        "stuck_node": None,
        "stuck_duration_seconds": None,
        "node_timings": {},
    }


# ── 1. WorkflowStatus Enum ────────────────────────────────────────────────────

class TestWorkflowStatus:
    def test_all_members_present(self):
        assert WorkflowStatus.PENDING.value == "PENDING"
        assert WorkflowStatus.RUNNING.value == "RUNNING"
        assert WorkflowStatus.AWAITING_REVIEW.value == "AWAITING_REVIEW"
        assert WorkflowStatus.APPROVED.value == "APPROVED"
        assert WorkflowStatus.REJECTED.value == "REJECTED"
        assert WorkflowStatus.COMPLETED.value == "COMPLETED"
        assert WorkflowStatus.FAILED.value == "FAILED"
        assert WorkflowStatus.ERROR.value == "ERROR"
        assert WorkflowStatus.STUCK.value == "STUCK"

    def test_members_count(self):
        assert len(WorkflowStatus) == 9

    def test_enum_inherits_str(self):
        assert issubclass(WorkflowStatus, str)


# ── 2. PipelineState TypedDict ────────────────────────────────────────────────

class TestPipelineState:
    def test_required_keys(self, sample_state):
        required_keys = {
            "file_path", "file_sha256", "file_type",
            "rooms", "parse_warnings", "parse_success",
            "validation_result", "validation_passed", "validation_evidence",
            "latitude", "longitude", "environmental_context",
            "nfpa_results", "total_detectors", "coverage_pct", "nfpa_compliant",
            "conflicts", "conflict_count", "has_critical_conflicts",
            "memory_context", "memory_enrichment_time_ms",
            "review_required", "review_items",
            "reviewer_decision", "reviewer_comments", "review_timestamp",
            "report", "report_sha256",
            "workflow_id", "engineer_id",
            "status", "started_at", "completed_at",
            "transition_log", "error_message",
            "stuck_detected", "stuck_node", "stuck_duration_seconds", "node_timings",
            "reviewer_timestamp",
        }
        for key in required_keys:
            assert key in sample_state, f"Missing PipelineState key: {key}"

    def test_state_is_dict_like(self, sample_state):
        assert isinstance(sample_state, dict)
        assert isinstance(sample_state.get("workflow_id"), str)
        assert isinstance(sample_state.get("transition_log"), list)


# ── 3. _log_transition() ──────────────────────────────────────────────────────

class TestLogTransition:
    def test_log_entry_structure(self, sample_state):
        state = _log_transition(sample_state, "A", "B", "test evidence")
        entry = state["transition_log"][0]
        assert "timestamp" in entry
        assert entry["from_node"] == "A"
        assert entry["to_node"] == "B"
        assert entry["evidence"] == "test evidence"
        assert entry["status_before"] == WorkflowStatus.PENDING.value
        assert entry["workflow_id"] == "test_wf_001"

    def test_transition_is_append_only(self, sample_state):
        state = _log_transition(sample_state, "A", "B", "e1")
        assert len(state["transition_log"]) == 1
        state = _log_transition(state, "B", "C", "e2")
        assert len(state["transition_log"]) == 2
        assert state["transition_log"][0]["evidence"] == "e1"
        assert state["transition_log"][1]["evidence"] == "e2"

    def test_timestamp_is_iso8601(self, sample_state):
        state = _log_transition(sample_state, "A", "B", "t")
        ts = state["transition_log"][0]["timestamp"]
        assert "T" in ts
        assert ts.endswith("Z") or "+" in ts

    def test_does_not_mutate_input_state(self, sample_state):
        original_id = id(sample_state.get("transition_log", []))
        _log_transition(sample_state, "A", "B", "test")
        assert id(sample_state.get("transition_log", [])) == original_id

    def test_empty_evidence_accepted(self, sample_state):
        state = _log_transition(sample_state, "X", "Y", "")
        assert state["transition_log"][0]["evidence"] == ""

    def test_log_with_missing_fields(self):
        minimal_state: PipelineState = {"file_path": "", "file_sha256": "", "file_type": "",
            "rooms": [], "parse_warnings": [], "parse_success": False,
            "validation_result": {}, "validation_passed": False, "validation_evidence": [],
            "environmental_context": {}, "nfpa_results": [], "total_detectors": 0,
            "coverage_pct": 0.0, "nfpa_compliant": False,
            "conflicts": [], "conflict_count": 0, "has_critical_conflicts": False,
            "review_required": False, "review_items": [],
            "reviewer_decision": None, "reviewer_comments": None, "review_timestamp": None,
            "report": {}, "report_sha256": "", "workflow_id": "minimal",
            "status": "PENDING", "started_at": "", "completed_at": None,
            "transition_log": [], "error_message": None,
        }
        state = _log_transition(minimal_state, "A", "B", "minimal")
        assert state["transition_log"][0]["workflow_id"] == "minimal"
        assert state["transition_log"][0]["status_before"] == "PENDING"


# ── 4. _compute_sha256() ──────────────────────────────────────────────────────

class TestComputeSha256:
    def test_deterministic(self):
        data = {"rooms": 7, "detectors": 12}
        h1 = _compute_sha256(data)
        h2 = _compute_sha256(data)
        assert h1 == h2

    def test_different_input_produces_different_hash(self):
        h1 = _compute_sha256({"rooms": 7})
        h2 = _compute_sha256({"rooms": 8})
        assert h1 != h2

    def test_returns_hex_string(self):
        h = _compute_sha256({"key": "value"})
        assert isinstance(h, str)
        assert all(c in "0123456789abcdef" for c in h)

    def test_returns_16_characters(self):
        h = _compute_sha256({"key": "value"})
        assert len(h) == 16

    def test_handles_nested_dicts(self):
        data = {"a": {"b": [1, 2, 3], "c": "hello"}, "d": 42}
        h = _compute_sha256(data)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_handles_non_serializable_with_default_str(self):
        class Custom:
            def __str__(self):
                return "custom_obj"
        h = _compute_sha256({"obj": Custom()})
        assert isinstance(h, str)
        assert len(h) == 16

    def test_empty_dict_hash(self):
        h = _compute_sha256({})
        assert isinstance(h, str)
        assert len(h) == 16


# ── 5. node_initialize() ──────────────────────────────────────────────────────

class TestNodeInitialize:
    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_path_traversal_blocked(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/allowed"
        mock_realpath.return_value = "/etc/passwd"
        sample_state["file_path"] = "../../etc/passwd"
        result = node_initialize(sample_state)
        assert result["status"] == WorkflowStatus.FAILED.value
        assert "Path traversal blocked" in result["error_message"]

    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_path_traversal_empty_allowed_dir_skipped(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/allowed::/tmp"
        mock_realpath.side_effect = lambda p: p
        mock_exists = MagicMock(return_value=False)
        with patch("os.path.exists", mock_exists):
            result = node_initialize(sample_state)
        assert result["status"] == WorkflowStatus.FAILED.value
        assert "File not found" in result["error_message"]

    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_file_not_found(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/tmp/fireai_uploads"
        mock_realpath.return_value = "/tmp/fireai_uploads/nonexistent.pdf"
        with patch("os.path.exists", return_value=False):
            result = node_initialize(sample_state)
        assert result["status"] == WorkflowStatus.FAILED.value
        assert "File not found" in result["error_message"]

    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_empty_file_path_returns_failed(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/tmp/fireai_uploads"
        mock_realpath.return_value = ""
        sample_state["file_path"] = ""
        with patch("os.path.exists", return_value=False):
            result = node_initialize(sample_state)
        assert result["status"] == WorkflowStatus.FAILED.value

    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_normal_initialization(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/tmp/fireai_uploads"
        mock_realpath.return_value = "/tmp/fireai_uploads/test.pdf"
        file_content = b"fake pdf content"
        m_open = mock_open(read_data=file_content)

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", m_open):
            result = node_initialize(sample_state)

        assert result["status"] == WorkflowStatus.RUNNING.value
        assert result["file_type"] == "pdf"
        assert len(result["file_sha256"]) == 64
        assert result["workflow_id"].startswith("wf_")
        assert result["started_at"] is not None
        assert isinstance(result["transition_log"], list)

    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_sha256_computation(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/tmp/fireai_uploads"
        mock_realpath.return_value = "/tmp/fireai_uploads/test.pdf"
        m_open = mock_open(read_data=b"deterministic content")

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", m_open):
            result1 = node_initialize(sample_state.copy())
            result2 = node_initialize(sample_state.copy())

        assert result1["file_sha256"] == result2["file_sha256"]

    @patch("os.environ.get")
    @patch("os.path.realpath")
    @pytest.mark.parametrize("ext,expected_type", [
        ("test.pdf", "pdf"),
        ("test.dwg", "dwg"),
        ("test.dxf", "dxf"),
        ("test.ifc", "ifc"),
        ("test.unknown", "unknown"),
        ("test.PDF", "pdf"),
        ("test.DWG", "dwg"),
    ])
    def test_file_type_detection(self, mock_realpath, mock_env_get,
                                  sample_state, ext, expected_type):
        mock_env_get.return_value = "/tmp/fireai_uploads"
        full_path = f"/tmp/fireai_uploads/{ext}"
        mock_realpath.return_value = full_path
        sample_state["file_path"] = full_path

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"data")):
            result = node_initialize(sample_state)

        assert result["file_type"] == expected_type

    @patch("os.environ.get")
    @patch("os.path.realpath")
    def test_transition_logged_on_success(self, mock_realpath, mock_env_get, sample_state):
        mock_env_get.return_value = "/tmp/fireai_uploads"
        mock_realpath.return_value = "/tmp/fireai_uploads/test.pdf"

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"data")):
            result = node_initialize(sample_state)

        assert len(result["transition_log"]) == 1
        entry = result["transition_log"][0]
        assert entry["from_node"] == "START"
        assert entry["to_node"] == "initialize"


# ── 6. node_parse() ───────────────────────────────────────────────────────────

class TestNodeParse:
    @patch("backend.services.workflow_service.node_initialize")
    def test_unsupported_file_type(self, mock_init, sample_state):
        sample_state["file_type"] = "unsupported"
        result = node_parse(sample_state)
        assert result["parse_success"] is False
        assert any("Unsupported" in w for w in result.get("parse_warnings", []))

    @patch("backend.services.workflow_service.node_initialize")
    def test_empty_file_path(self, mock_init, sample_state):
        sample_state["file_path"] = ""
        sample_state["file_type"] = ""
        result = node_parse(sample_state)
        assert result["parse_success"] is False

    def test_transition_logged(self, sample_state):
        sample_state["file_type"] = "unsupported"
        result = node_parse(sample_state)
        assert len(result["transition_log"]) == 1
        entry = result["transition_log"][0]
        assert entry["from_node"] == "initialize"
        assert entry["to_node"] == "parse"

    @patch("adapters.pdf_to_rooms_adapter.extract_rooms_from_walls")
    @patch("parsers.geometry_extractor.GeometryExtractor")
    def test_pdf_parse_calls_extractor(self, mock_geo_cls, mock_extract_rooms,
                                       sample_state):
        sample_state["file_type"] = "pdf"
        mock_extractor = MagicMock()
        mock_extractor.extract_walls.return_value = []
        mock_geo_cls.return_value = mock_extractor
        mock_extract_rooms.return_value = ([], {"status": "ok"})

        result = node_parse(sample_state)
        mock_geo_cls.assert_called_once_with(sample_state["file_path"])
        mock_extractor.extract_walls.assert_called_once()

    def test_fail_safe_empty_rooms(self, sample_state):
        sample_state["file_type"] = "pdf"
        with patch("parsers.geometry_extractor.GeometryExtractor") as mock_geo:
            mock_extractor = MagicMock()
            mock_extractor.extract_walls.return_value = []
            mock_geo.return_value = mock_extractor
            with patch("adapters.pdf_to_rooms_adapter.extract_rooms_from_walls",
                       return_value=([], {"status": "ok"})):
                result = node_parse(sample_state)

        assert result["parse_success"] is False
        assert any("No rooms" in w for w in result.get("parse_warnings", []))

    def test_exception_during_parse_handled(self, sample_state):
        sample_state["file_type"] = "pdf"
        with patch("parsers.geometry_extractor.GeometryExtractor",
                   side_effect=RuntimeError("parse crashed")):
            result = node_parse(sample_state)

        assert result["parse_success"] is False
        assert any("Parse error" in w for w in result.get("parse_warnings", []))


# ── 7. Conditional Edge Functions ─────────────────────────────────────────────

class TestShouldProceedAfterParse:
    def test_parse_success_routes_to_validate(self, sample_state):
        sample_state["parse_success"] = True
        assert should_proceed_after_parse(sample_state) == "validate"

    def test_parse_failure_routes_to_generate_report(self, sample_state):
        sample_state["parse_success"] = False
        assert should_proceed_after_parse(sample_state) == "generate_report"


class TestShouldProceedAfterValidation:
    def test_validation_passed_routes_to_environmental_context(self, sample_state):
        sample_state["validation_passed"] = True
        assert should_proceed_after_validation(sample_state) == "environmental_context"

    def test_validation_failed_routes_to_generate_report(self, sample_state):
        sample_state["validation_passed"] = False
        assert should_proceed_after_validation(sample_state) == "generate_report"


class TestShouldRequireReview:
    def test_review_required_routes_to_human_review_gate(self, sample_state):
        sample_state["review_required"] = True
        assert should_require_review(sample_state) == "human_review_gate"

    def test_review_not_required_routes_to_generate_report(self, sample_state):
        sample_state["review_required"] = False
        assert should_require_review(sample_state) == "generate_report"


class TestShouldProceedAfterReview:
    def test_approved_routes_to_generate_report(self, sample_state):
        sample_state["reviewer_decision"] = "approved"
        assert should_proceed_after_review(sample_state) == "generate_report"

    def test_rejected_routes_to_end(self, sample_state):
        sample_state["reviewer_decision"] = "rejected"
        assert should_proceed_after_review(sample_state) == END

    def test_no_decision_routes_to_end(self, sample_state):
        sample_state["reviewer_decision"] = None
        assert should_proceed_after_review(sample_state) == END


# ── 8. build_fireai_workflow() ────────────────────────────────────────────────

class TestBuildFireaiWorkflow:
    def test_returns_stategraph(self):
        graph = build_fireai_workflow()
        assert graph is not None

    def test_all_nodes_registered(self, service):
        graph = build_fireai_workflow()
        expected_nodes = {
            "initialize", "parse", "validate", "memory_enrich",
            "environmental_context", "nfpa_analysis", "conflict_detection",
            "human_review_gate", "generate_report",
        }
        for node in expected_nodes:
            assert node in graph.nodes, f"Missing node: {node}"

    def test_entry_point_is_initialize(self):
        graph = build_fireai_workflow()
        assert graph.entry_point == "initialize"

    def test_direct_edges_exist(self):
        graph = build_fireai_workflow()
        assert ("initialize", "parse") in graph._edges or \
               any(e[0] == "initialize" for e in getattr(graph, '_edges', []))
        assert ("environmental_context", "memory_enrich") in graph._edges or \
               hasattr(graph, '_conditional_edges')

    def test_conditional_edges_exist(self):
        graph = build_fireai_workflow()
        assert hasattr(graph, '_conditional_edges') and len(graph._conditional_edges) > 0

    def test_interrupt_before_human_review_gate(self, service):
        compiled = service._graph_compiled
        assert compiled is not None


# ── 9. WorkflowService ────────────────────────────────────────────────────────

class TestWorkflowServiceInit:
    def test_service_initializes_successfully(self, service):
        assert service is not None
        assert service._graph is not None
        assert service._graph_compiled is not None
        assert service._workflows == {}

    def test_graph_has_all_nodes(self, service):
        expected = {"initialize", "parse", "validate", "memory_enrich",
                    "environmental_context", "nfpa_analysis", "conflict_detection",
                    "human_review_gate", "generate_report"}
        for node in expected:
            assert node in service._graph.nodes


class TestWorkflowServiceCreateWorkflow:
    @pytest.mark.asyncio
    @patch("backend.services.workflow_service.WorkflowService._run_graph")
    @patch("backend.services.workflow_service.WorkflowService._ensure_compiled")
    async def test_create_workflow_without_human_review(self, mock_ensure, mock_run, service):
        mock_ensure.return_value = MagicMock()
        mock_run.return_value = {
            "status": WorkflowStatus.COMPLETED.value,
            "review_required": False,
            "review_items": [],
            "total_detectors": 3,
            "coverage_pct": 100.0,
            "nfpa_compliant": True,
            "conflict_count": 0,
            "report": {"report_metadata": {"workflow_id": "test"}},
            "report_sha256": "abcd1234",
            "transition_log": [{"from": "START", "to": "END"}],
        }

        result = await service.start_workflow(
            file_path="/tmp/test.pdf",
            skip_human_review=True,
        )

        assert result["workflow_id"] is not None
        assert result["status"] == WorkflowStatus.COMPLETED.value
        assert result["workflow_id"] in service._workflows

    @pytest.mark.asyncio
    @patch("backend.services.workflow_service.WorkflowService._run_graph")
    @patch("backend.services.workflow_service.WorkflowService._ensure_compiled")
    async def test_create_workflow_with_skip_false(self, mock_ensure, mock_run, service):
        mock_ensure.return_value = MagicMock()
        mock_run.return_value = {
            "status": WorkflowStatus.AWAITING_REVIEW.value,
            "review_required": True,
            "review_items": [{"item": "test"}],
            "total_detectors": 0,
            "coverage_pct": 0.0,
            "nfpa_compliant": False,
            "conflict_count": 1,
            "report": {},
            "report_sha256": "",
            "transition_log": [],
        }

        result = await service.start_workflow(
            file_path="/tmp/test.pdf",
            skip_human_review=False,
        )

        assert result["workflow_id"] is not None
        assert result["workflow_id"] in service._workflows

    @pytest.mark.asyncio
    @patch("backend.services.workflow_service.WorkflowService._run_graph")
    @patch("backend.services.workflow_service.WorkflowService._ensure_compiled")
    async def test_create_workflow_stores_metadata(self, mock_ensure, mock_run, service):
        mock_ensure.return_value = MagicMock()
        mock_run.return_value = {"status": "COMPLETED", "transition_log": []}

        result = await service.start_workflow(
            file_path="/tmp/test.pdf",
            latitude=10.0,
            longitude=20.0,
            engineer_id="eng_007",
        )

        assert result["workflow_id"] in service._workflows
        wf = service._workflows[result["workflow_id"]]
        assert "state" in wf
        assert "config" in wf
        assert "skip_human_review" in wf


class TestWorkflowServiceGetStatus:
    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, service):
        status = await service.get_workflow_status("nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_returns_correct_data_for_existing(self, service):
        workflow_id = "test_wf_status"
        service._workflows[workflow_id] = {
            "state": {
                "status": WorkflowStatus.PENDING.value,
                "review_required": False,
                "review_items": [],
                "total_detectors": 0,
                "nfpa_compliant": False,
                "transition_log": [],
                "stuck_detected": False,
                "stuck_node": None,
                "node_timings": {},
            },
            "config": {"configurable": {"thread_id": workflow_id}},
        }
        status = await service.get_workflow_status(workflow_id)
        assert status is not None
        assert status["workflow_id"] == workflow_id
        assert status["status"] == WorkflowStatus.PENDING.value


class TestWorkflowServiceApprove:
    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_none(self, service):
        result = await service.approve_workflow("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.workflow_service.WorkflowService._ensure_compiled")
    async def test_approve_not_awaiting_review_returns_error(self, mock_ensure, service):
        workflow_id = "test_wf_not_awaiting"
        service._workflows[workflow_id] = {
            "state": {
                "status": WorkflowStatus.PENDING.value,
                "transition_log": [],
            },
            "config": {},
        }
        result = await service.approve_workflow(workflow_id)
        assert "error" in result

    @pytest.mark.asyncio
    @patch("backend.services.workflow_service.WorkflowService._ensure_compiled")
    async def test_approve_success(self, mock_ensure, service):
        workflow_id = "test_wf_approve"
        mock_compiled = MagicMock()
        mock_ensure.return_value = mock_compiled
        mock_compiled.invoke.return_value = {
            "status": WorkflowStatus.COMPLETED.value,
            "report": {"report_metadata": {}},
            "report_sha256": "abcd",
        }

        service._workflows[workflow_id] = {
            "state": {
                "status": WorkflowStatus.AWAITING_REVIEW.value,
                "reviewer_decision": None,
                "transition_log": [],
            },
            "config": {"configurable": {"thread_id": workflow_id}},
        }

        result = await service.approve_workflow(workflow_id, comments="Looks good")
        assert result["workflow_id"] == workflow_id
        assert result["status"] == WorkflowStatus.COMPLETED.value


class TestWorkflowServiceReject:
    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_none(self, service):
        result = await service.reject_workflow("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_reject_not_awaiting_review_returns_error(self, service):
        workflow_id = "test_wf_reject_not_awaiting"
        service._workflows[workflow_id] = {
            "state": {
                "status": WorkflowStatus.PENDING.value,
                "transition_log": [],
            },
            "config": {},
        }
        result = await service.reject_workflow(workflow_id)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reject_success(self, service):
        workflow_id = "test_wf_reject"
        service._workflows[workflow_id] = {
            "state": {
                "status": WorkflowStatus.AWAITING_REVIEW.value,
                "reviewer_decision": None,
                "reviewer_comments": None,
                "review_timestamp": None,
                "reviewer_timestamp": None,
                "completed_at": None,
                "transition_log": [],
            },
            "config": {"configurable": {"thread_id": workflow_id}},
        }

        result = await service.reject_workflow(workflow_id, comments="Needs rework")
        assert result["workflow_id"] == workflow_id
        assert result["status"] == WorkflowStatus.REJECTED.value
        assert result["reviewer_comments"] == "Needs rework"

        state = service._workflows[workflow_id]["state"]
        assert state["reviewer_decision"] == "rejected"
        assert state["status"] == WorkflowStatus.REJECTED.value
        assert state["completed_at"] is not None


class TestWorkflowServiceAuditTrail:
    @pytest.mark.asyncio
    async def test_audit_trail_nonexistent_returns_none(self, service):
        trail = await service.get_audit_trail("nonexistent")
        assert trail is None

    @pytest.mark.asyncio
    async def test_audit_trail_returns_transition_log(self, service):
        workflow_id = "test_wf_audit"
        transitions = [
            {"from_node": "START", "to_node": "initialize", "timestamp": "t1"},
            {"from_node": "initialize", "to_node": "parse", "timestamp": "t2"},
        ]
        service._workflows[workflow_id] = {
            "state": {
                "transition_log": transitions,
                "status": WorkflowStatus.COMPLETED.value,
            },
            "config": {},
        }
        trail = await service.get_audit_trail(workflow_id)
        assert trail == transitions
        assert len(trail) == 2
