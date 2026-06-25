"""test_v133_phase2_3_ai.py — Tests for PHASE 2 (LangWatch) and PHASE 3 (Smithery MCP).

Validates LangWatch integration (in workflow_service context, NOT analysis_pipeline)
and Smithery MCP (read-only + human-approved writes).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# LangWatch Integration Tests (PHASE 2 — Corrected Target)
# ---------------------------------------------------------------------------


class TestLangWatchIntegration:
    """Tests for LangWatch AI observability (in workflow_service context)."""

    def test_langwatch_client_initializes_without_api_key(self, monkeypatch):
        """Without API key, client should still initialize (no-op mode)."""
        monkeypatch.delenv("LANGWATCH_API_KEY", raising=False)
        from fireai.infrastructure.langwatch_integration import LangWatchClient
        client = LangWatchClient()
        assert client.is_available is False

    def test_trace_decorator_works_without_langwatch(self, monkeypatch):
        """Decorator should be pass-through when LangWatch unavailable."""
        monkeypatch.delenv("LANGWATCH_API_KEY", raising=False)
        from fireai.infrastructure.langwatch_integration import trace_llm_call

        @trace_llm_call("test_operation")
        def test_func(x: int) -> int:
            return x * 2

        assert test_func(5) == 10

    def test_hallucination_check_safe_spacing(self):
        """Spacing within NFPA 72 limits should NOT be flagged as hallucination."""
        from fireai.infrastructure.langwatch_integration import hallucination_check_spacing
        result = hallucination_check_spacing(
            suggested_spacing_m=8.0,  # < 9.1m max for smoke
            detector_type="smoke",
        )
        assert result["is_hallucination"] is False
        assert result["confidence"] > 0.0
        assert result["max_allowed_m"] == 9.1

    def test_hallucination_check_violating_spacing(self):
        """Spacing exceeding NFPA 72 limits should be flagged as hallucination."""
        from fireai.infrastructure.langwatch_integration import hallucination_check_spacing
        result = hallucination_check_spacing(
            suggested_spacing_m=12.0,  # > 9.1m max for smoke
            detector_type="smoke",
        )
        assert result["is_hallucination"] is True
        assert result["confidence"] == 0.0
        assert "HALLUCINATION DETECTED" in result["warning"]

    def test_hallucination_check_heat_detector(self):
        """Heat detector spacing should use 6.1m limit."""
        from fireai.infrastructure.langwatch_integration import hallucination_check_spacing
        result = hallucination_check_spacing(
            suggested_spacing_m=7.0,  # > 6.1m max for heat
            detector_type="heat",
        )
        assert result["is_hallucination"] is True
        assert result["max_allowed_m"] == 6.1

    def test_hallucination_check_nan_spacing(self):
        """NaN spacing should be flagged as hallucination."""
        from fireai.infrastructure.langwatch_integration import hallucination_check_spacing
        result = hallucination_check_spacing(
            suggested_spacing_m=float("nan"),
            detector_type="smoke",
        )
        assert result["is_hallucination"] is True

    def test_record_confidence_score_valid(self):
        """Valid confidence score should be recorded."""
        from fireai.infrastructure.langwatch_integration import record_confidence_score
        # Should not raise
        record_confidence_score(
            decision="smoke_detector_placement",
            confidence=0.85,
            reasoning="NFPA 72 §17.6.3 spacing met",
        )

    def test_record_confidence_score_invalid_clamped(self):
        """Out-of-range confidence should be clamped, not rejected."""
        from fireai.infrastructure.langwatch_integration import record_confidence_score
        # Should not raise — clamps to [0, 1]
        record_confidence_score(
            decision="test",
            confidence=1.5,  # Out of range
        )
        record_confidence_score(
            decision="test",
            confidence=-0.5,  # Out of range
        )

    def test_nfpa72_constants_correct(self):
        """NFPA 72 spacing constants should match the code."""
        from fireai.infrastructure.langwatch_integration import (
            NFPA72_MAX_SMOKE_SPACING_M,
            NFPA72_MAX_HEAT_SPACING_M,
        )
        assert NFPA72_MAX_SMOKE_SPACING_M == 9.1  # 30 ft
        assert NFPA72_MAX_HEAT_SPACING_M == 6.1   # 20 ft


# ---------------------------------------------------------------------------
# Smithery MCP Tests (PHASE 3 — Redesigned for Safety)
# ---------------------------------------------------------------------------


class TestSmitheryMCP:
    """Tests for Smithery MCP integration (read-only + human-approved writes)."""

    def test_client_initializes_without_api_key(self, monkeypatch):
        """Without API key, client should still work (local docs only)."""
        monkeypatch.delenv("SMITHERY_API_KEY", raising=False)
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        assert client.api_key is None

    def test_search_revit_api_returns_list(self):
        """search_revit_api should return a list (possibly empty)."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        results = client.search_revit_api("Wall", revit_version="2023")
        assert isinstance(results, list)

    def test_verify_revit_class_returns_bool(self):
        """verify_revit_class should return a boolean."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        result = client.verify_revit_class("Wall", revit_version="2023")
        assert isinstance(result, bool)

    def test_propose_create_detector_returns_proposed_action(self):
        """propose_create_detector should return a ProposedAction (NOT execute)."""
        from fireai.mcp_server.smithery_mcp_integration import (
            SmitheryMCPClient,
            ActionType,
            ActionStatus,
        )
        client = SmitheryMCPClient()
        action = client.propose_create_detector(
            room_id="R-001",
            position=(5.0, 3.0, 2.8),
            detector_type="smoke",
            rationale="NFPA 72 §17.6.3 requires coverage",
            confidence=0.9,
        )
        assert action.action_type == ActionType.CREATE
        assert action.status == ActionStatus.PROPOSED  # NOT EXECUTED
        assert action.parameters["room_id"] == "R-001"
        assert action.parameters["detector_type"] == "smoke"

    def test_propose_update_element_returns_proposed_action(self):
        """propose_update_element should return a ProposedAction (NOT execute)."""
        from fireai.mcp_server.smithery_mcp_integration import (
            SmitheryMCPClient,
            ActionType,
        )
        client = SmitheryMCPClient()
        action = client.propose_update_element(
            element_id="ELEMENT-001",
            updates={"position": [6.0, 3.0, 2.8]},
            rationale="Improved coverage",
        )
        assert action.action_type == ActionType.UPDATE
        assert action.element_id == "ELEMENT-001"

    def test_propose_delete_element_includes_warning(self):
        """DELETE proposals should include a warning about human approval."""
        from fireai.mcp_server.smithery_mcp_integration import (
            SmitheryMCPClient,
            ActionType,
        )
        client = SmitheryMCPClient()
        action = client.propose_delete_element(
            element_id="ELEMENT-002",
            rationale="Duplicate detector",
        )
        assert action.action_type == ActionType.DELETE
        assert "DELETE PROPOSAL" in action.rationale
        assert "human approval" in action.rationale.lower()

    def test_proposed_action_has_unique_id(self):
        """Each proposal should have a unique ID."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        a1 = client.propose_create_detector("R-001", (1, 1, 1))
        a2 = client.propose_create_detector("R-001", (2, 2, 2))
        assert a1.id != a2.id

    def test_proposed_action_includes_timestamp(self):
        """Proposals should include an ISO timestamp."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        action = client.propose_create_detector("R-001", (1, 1, 1))
        assert action.proposed_at  # Not empty
        assert "T" in action.proposed_at  # ISO format

    def test_read_rooms_from_bim_returns_list(self):
        """read_rooms_from_bim should return a list (possibly empty)."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        rooms = client.read_rooms_from_bim()
        assert isinstance(rooms, list)

    def test_connect_to_smithery_without_key_returns_false(self, monkeypatch):
        """Without API key, connect_to_smithery should return False."""
        monkeypatch.delenv("SMITHERY_API_KEY", raising=False)
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        assert client.connect_to_smithery() is False

    def test_get_smithery_client_returns_singleton(self):
        """get_smithery_client should return the same instance."""
        from fireai.mcp_server.smithery_mcp_integration import (
            get_smithery_client,
            SmitheryMCPClient,
        )
        c1 = get_smithery_client()
        c2 = get_smithery_client()
        assert c1 is c2
        assert isinstance(c1, SmitheryMCPClient)


# ---------------------------------------------------------------------------
# Safety Design Verification Tests
# ---------------------------------------------------------------------------


class TestSafetyDesign:
    """Verify the SAFETY-ORIENTED REDESIGN of PHASE 3."""

    def test_proposed_action_status_is_proposed(self):
        """All AI-proposed actions must have status=PROPOSED (never APPROVED/EXECUTED)."""
        from fireai.mcp_server.smithery_mcp_integration import (
            SmitheryMCPClient,
            ActionStatus,
        )
        client = SmitheryMCPClient()
        action = client.propose_create_detector("R-001", (1, 1, 1))
        assert action.status == ActionStatus.PROPOSED
        # Critical: AI must NOT be able to set status to APPROVED or EXECUTED
        assert action.status != ActionStatus.APPROVED
        assert action.status != ActionStatus.EXECUTED

    def test_proposed_action_to_dict_includes_safety_fields(self):
        """Serialized proposals should include review tracking fields."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        action = client.propose_create_detector("R-001", (1, 1, 1))
        d = action.to_dict()
        assert "status" in d
        assert "reviewed_by" in d
        assert "reviewed_at" in d
        assert "review_notes" in d
        # reviewed_by should be None until a human reviews
        assert d["reviewed_by"] is None

    def test_no_direct_execute_method_exists(self):
        """SmitheryMCPClient must NOT have an execute_action method."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        # Verify there's no method to directly execute a proposed action
        assert not hasattr(client, "execute_action")
        assert not hasattr(client, "execute_proposal")
        assert not hasattr(client, "apply_action")
        assert not hasattr(client, "commit_action")

    def test_only_propose_methods_exist(self):
        """SmitheryMCPClient should only have 'propose_*' methods for writes."""
        from fireai.mcp_server.smithery_mcp_integration import SmitheryMCPClient
        client = SmitheryMCPClient()
        # Write methods should all start with "propose_"
        write_methods = [
            m for m in dir(client)
            if callable(getattr(client, m)) and not m.startswith("_")
            and m not in ("search_revit_api", "verify_revit_class",
                         "read_rooms_from_bim", "connect_to_smithery")
        ]
        for method in write_methods:
            assert method.startswith("propose_"), (
                f"Method {method} does not start with 'propose_' — "
                "AI must NOT be able to execute writes directly"
            )
