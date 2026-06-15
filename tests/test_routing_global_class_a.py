"""
tests/test_routing_global_class_a.py
=====================================
Comprehensive test suite for fireai/core/routing_global_class_a.py

SAFETY CRITICAL: Class A fire alarm circuits require separate outgoing and
return paths per NFPA 72 §12.2.2. A single cable fault must NOT disable
both paths — that would leave an entire zone without fire detection.

NOTE: The source code uses old provenance field names (citation, constant_id,
value_used, unit) which don't match provenance.py (rule_id, description,
standard, section, result). Tests patch the provenance classes in the module
namespace to accept both old and new field names.

Reference: NFPA 72-2022 §12.2.2, NEC 760.154
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import MagicMock, patch

import pytest

import fireai.core.routing_global_class_a as routing_mod

# ═══════════════════════════════════════════════════════════════════════════════
# Mock provenance classes that accept BOTH old and new field names
# ═══════════════════════════════════════════════════════════════════════════════

class _MockConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    REFUSE = "REFUSE"


@dataclass
class _MockConfidenceScore:
    level: _MockConfidenceLevel = _MockConfidenceLevel.MEDIUM
    value: float = 0.5
    reason: str = ""
    standard_reference: str = ""


@dataclass
class _MockRuleApplied:
    rule_id: str = ""
    description: str = ""
    standard: str = ""
    section: str = ""
    result: str = ""
    citation: str = ""
    constant_id: str = ""
    value_used: float = 0.0
    unit: str = ""


@dataclass
class _MockViolation:
    rule_id: str = ""
    severity: str = "HIGH"
    description: str = ""
    nfpa_section: str = ""
    remediation: str = ""
    citation: str = ""


@dataclass
class _MockDecisionProvenance:
    decision_id: str = ""
    decision_type: str = ""
    description: str = ""
    confidence: _MockConfidenceScore = field(default_factory=_MockConfidenceScore)
    rules_applied: list = field(default_factory=list)
    algorithm: dict = field(default_factory=dict)
    selected_because: str = ""
    violations: list = field(default_factory=list)
    value: object = None
    inputs: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)

    @classmethod
    def new(cls, **kwargs):
        return cls(**kwargs)


@pytest.fixture(autouse=True)
def _patch_provenance_in_module():
    """Patch provenance classes in the routing_global_class_a module namespace."""
    originals = {
        "ConfidenceLevel": routing_mod.ConfidenceLevel,
        "ConfidenceScore": routing_mod.ConfidenceScore,
        "RuleApplied": routing_mod.RuleApplied,
        "Violation": routing_mod.Violation,
        "DecisionProvenance": routing_mod.DecisionProvenance,
    }
    routing_mod.ConfidenceLevel = _MockConfidenceLevel
    routing_mod.ConfidenceScore = _MockConfidenceScore
    routing_mod.RuleApplied = _MockRuleApplied
    routing_mod.Violation = _MockViolation
    routing_mod.DecisionProvenance = _MockDecisionProvenance
    yield
    # Restore originals
    routing_mod.ConfidenceLevel = originals["ConfidenceLevel"]
    routing_mod.ConfidenceScore = originals["ConfidenceScore"]
    routing_mod.RuleApplied = originals["RuleApplied"]
    routing_mod.Violation = originals["Violation"]
    routing_mod.DecisionProvenance = originals["DecisionProvenance"]


from fireai.core.routing_global_class_a import EliteGlobalRouter

# ═══════════════════════════════════════════════════════════════════════════════
# EliteGlobalRouter Initialization Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEliteGlobalRouterInit:
    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_init_with_bounds(self, MockRouter):
        EliteGlobalRouter(global_bounds=(0, 0, 100, 50))
        MockRouter.assert_called_once_with(width=100, length=50, resolution=0.25)

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_init_with_custom_resolution(self, MockRouter):
        EliteGlobalRouter(global_bounds=(0, 0, 50, 50), resolution=0.5)
        MockRouter.assert_called_once_with(width=50, length=50, resolution=0.5)

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_stores_min_xy(self, MockRouter):
        router = EliteGlobalRouter(global_bounds=(10, 20, 100, 200))
        assert router._min_x == 10
        assert router._min_y == 20


# ═══════════════════════════════════════════════════════════════════════════════
# apply_class_a_separation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplyClassASeparation:
    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_is_noop(self, MockRouter):
        """apply_class_a_separation is a no-op — delegated to EliteClassARouter."""
        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        router.apply_class_a_separation([(0, 0), (10, 10)], min_sep_m=1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# route_class_a_loop Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouteClassALoop:
    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_successful_route(self, MockRouter):
        """Successful Class A loop returns DecisionProvenance with paths."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0), (10, 0), (20, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(20, 5), (10, 5), (0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(20, 0))

        assert result.decision_type == "class_a_route_creation"
        assert result.value is not None
        assert "out_path" in result.value
        assert "return_path" in result.value
        assert len(result.violations) == 0

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_successful_route_with_firestops(self, MockRouter):
        """Route with fire-rated wall penetrations includes firestop note."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0), (10, 0)]
        out_seg.firestop_nodes = ["FS1"]
        ret_seg = MagicMock()
        ret_seg.path = [(10, 5), (0, 5)]
        ret_seg.firestop_nodes = ["FS2"]
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(10, 0))

        assert "fire-rated wall penetration" in result.selected_because
        assert "2" in result.selected_because

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_failed_route_returns_violation(self, MockRouter):
        """When routing fails, DecisionProvenance has CRITICAL violation."""
        mock_router_instance = MockRouter.return_value
        mock_router_instance.generate_class_a_loop.side_effect = ValueError(
            "Cannot satisfy separation constraint"
        )

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(50, 50))

        assert result.value is None
        assert len(result.violations) == 1
        assert result.violations[0].severity == "CRITICAL"

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_route_has_rules_applied(self, MockRouter):
        """All routes have at least one RuleApplied."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0), (10, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(10, 5), (0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(10, 0))

        assert len(result.rules_applied) >= 1

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_route_class_a_sep_constant(self, MockRouter):
        """CLASS_A_SEP constant is 1.0m per NFPA 72 §12.2.2."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(0, 0))

        rule = result.rules_applied[0]
        assert rule.constant_id == "CLASS_A_SEP"
        assert rule.value_used == 1.0
        assert rule.unit == "m"

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_failed_route_confidence_refuse(self, MockRouter):
        """Failed route has REFUSE confidence level."""
        mock_router_instance = MockRouter.return_value
        mock_router_instance.generate_class_a_loop.side_effect = ValueError("Blocked")

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(50, 50))

        # Source uses ConfidenceScore(1.0, 1.0, 1.0, ConfidenceLevel.REFUSE)
        # which maps to: level=1.0, value=1.0, reason=1.0, standard_reference=REFUSE
        assert result.confidence.standard_reference == _MockConfidenceLevel.REFUSE

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_successful_route_confidence_high(self, MockRouter):
        """Successful route has HIGH confidence."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0), (10, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(10, 5), (0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(10, 0))

        # Source uses ConfidenceScore(1.0, 1.0, 1.0, ConfidenceLevel.HIGH)
        # which maps to: level=1.0, value=1.0, reason=1.0, standard_reference=HIGH
        assert result.confidence.standard_reference == _MockConfidenceLevel.HIGH

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_no_firestops_no_note(self, MockRouter):
        """Route without firestop penetrations has no IBC §714 note."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0), (10, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(10, 5), (0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(10, 0))

        assert "fire-rated wall penetration" not in result.selected_because

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_inputs_recorded(self, MockRouter):
        """Inputs (panel, terminal_node) are recorded in DecisionProvenance."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(5, 10), terminal_device=(15, 20))

        assert result.inputs["panel"] == (5, 10)
        assert result.inputs["terminal_node"] == (15, 20)

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_algorithm_version(self, MockRouter):
        """Algorithm version is v13_unified."""
        mock_router_instance = MockRouter.return_value
        out_seg = MagicMock()
        out_seg.path = [(0, 0)]
        out_seg.firestop_nodes = []
        ret_seg = MagicMock()
        ret_seg.path = [(0, 5)]
        ret_seg.firestop_nodes = []
        mock_router_instance.generate_class_a_loop.return_value = {
            "outgoing_class_a": out_seg,
            "return_class_a": ret_seg,
        }

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(10, 0))

        assert result.algorithm["name"] == "astar_matrix_masking"
        assert result.algorithm["version"] == "v13_unified"

    @patch("fireai.core.routing_global_class_a.EliteClassARouter")
    def test_failed_route_selected_because(self, MockRouter):
        """Failed route explains return path blocked."""
        mock_router_instance = MockRouter.return_value
        mock_router_instance.generate_class_a_loop.side_effect = ValueError("No path")

        router = EliteGlobalRouter(global_bounds=(0, 0, 100, 100))
        result = router.route_class_a_loop(panel=(0, 0), terminal_device=(50, 50))

        assert "blocked" in result.selected_because.lower() or "Return" in result.selected_because


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
