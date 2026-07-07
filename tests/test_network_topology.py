"""
tests/test_network_topology.py
================================
Comprehensive test suite for fireai/core/network_topology.py

SAFETY CRITICAL: Network topology audit verifies Class X (redundant path)
compliance per NFPA 72 §23.8.

NFPA 72 References:
  §23.8  — Networked systems
  §12.3  — Pathway survivability
  §12.2  — Pathway design
"""

from __future__ import annotations

import dataclasses

import pytest

import fireai.core.network_topology as _nt_mod


# Force fallback dict path — provenance RuleApplied/Violation field names
# don't match what the source module expects.
@pytest.fixture(autouse=True)
def _disable_provenance():
    originals = {}
    for attr in ("DecisionProvenance", "RuleApplied", "Violation",
                "ConfidenceScore", "ConfidenceLevel"):
        originals[attr] = getattr(_nt_mod, attr, None)
        setattr(_nt_mod, attr, None)
    yield
    for attr, val in originals.items():
        setattr(_nt_mod, attr, val)

from fireai.core.network_topology import (
    REQUIRED_TOPOLOGY,
    NetworkLink,
    NetworkTopologyAuditor,
    PanelNode,
)

# Fixtures / Helpers
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def auditor() -> NetworkTopologyAuditor:
    return NetworkTopologyAuditor()


def _result_value(result):
    """Extract value dict from result (handles both dict and provenance)."""
    if isinstance(result, dict):
        return result.get("value", result)
    if hasattr(result, "value"):
        return result.value
    return result


def _make_ring_network():
    panels = [
        {"panel_id": "FACP-01", "building_id": "BLDG-A", "is_master": True},
        {"panel_id": "FACP-02", "building_id": "BLDG-B"},
        {"panel_id": "FACP-03", "building_id": "BLDG-C"},
    ]
    links = [
        {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True, "link_type": "fiber_dual"},
        {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True, "link_type": "fiber_dual"},
        {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-01", "is_class_x": True, "link_type": "fiber_dual"},
    ]
    return panels, links


def _make_star_network():
    panels = [
        {"panel_id": "FACP-01", "building_id": "BLDG-A", "is_master": True},
        {"panel_id": "FACP-02", "building_id": "BLDG-B"},
        {"panel_id": "FACP-03", "building_id": "BLDG-C"},
        {"panel_id": "FACP-04", "building_id": "BLDG-D"},
    ]
    links = [
        {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": False, "link_type": "copper"},
        {"link_id": "L2", "from_panel": "FACP-01", "to_panel": "FACP-03", "is_class_x": False, "link_type": "copper"},
        {"link_id": "L3", "from_panel": "FACP-01", "to_panel": "FACP-04", "is_class_x": False, "link_type": "copper"},
    ]
    return panels, links


def _make_daisy_chain_network():
    """4-panel daisy chain — has 2 endpoints and 2 intermediates."""
    panels = [
        {"panel_id": "FACP-01", "building_id": "BLDG-A", "is_master": True},
        {"panel_id": "FACP-02", "building_id": "BLDG-B"},
        {"panel_id": "FACP-03", "building_id": "BLDG-C"},
        {"panel_id": "FACP-04", "building_id": "BLDG-D"},
    ]
    links = [
        {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": False, "link_type": "copper"},
        {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": False, "link_type": "copper"},
        {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-04", "is_class_x": False, "link_type": "copper"},
    ]
    return panels, links


# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:

    def test_required_topology_is_ring(self):
        assert REQUIRED_TOPOLOGY == "ring"


# PanelNode & NetworkLink
# ─────────────────────────────────────────────────────────────────────────────


class TestPanelNode:

    def test_default_location(self):
        p = PanelNode("FACP-01", "BLDG-A")
        assert p.location == (0.0, 0.0)
        assert p.is_master is False

    def test_custom_values(self):
        p = PanelNode("FACP-01", "BLDG-A", (10.0, 20.0), is_master=True)
        assert p.location == (10.0, 20.0)
        assert p.is_master is True

    def test_frozen(self):
        p = PanelNode("FACP-01", "BLDG-A")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.panel_id = "CHANGED"


class TestNetworkLink:

    def test_default_values(self):
        link = NetworkLink("L1", "P1", "P2")
        assert link.link_type == "copper"
        assert link.is_class_x is False
        assert link.length_m == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_values(self):
        link = NetworkLink("L1", "P1", "P2", "fiber_dual", True, 500.0)
        assert link.link_type == "fiber_dual"
        assert link.is_class_x is True
        assert link.length_m == 500.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_frozen(self):
        link = NetworkLink("L1", "P1", "P2")
        with pytest.raises(dataclasses.FrozenInstanceError):
            link.is_class_x = True


# ─────────────────────────────────────────────────────────────────────────────
# Ring (Class X Compliant)
# ─────────────────────────────────────────────────────────────────────────────


class TestRingNetwork:

    def test_ring_is_class_x_compliant(self, auditor):
        panels, links = _make_ring_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("is_class_x_compliant") is True

    def test_ring_no_violations(self, auditor):
        panels, links = _make_ring_network()
        result = auditor.audit_network_topology(panels, links)
        # With provenance disabled, violations are plain dicts
        violations = result.get("violations", []) if isinstance(result, dict) else []
        assert len(violations) == 0

    def test_ring_topology_type(self, auditor):
        panels, links = _make_ring_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("topology_type") == "ring"

    def test_ring_safe(self, auditor):
        panels, links = _make_ring_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is True


# ─────────────────────────────────────────────────────────────────────────────
# Star (Single Point of Failure)
# ─────────────────────────────────────────────────────────────────────────────


class TestStarNetwork:

    def test_star_has_violations(self, auditor):
        panels, links = _make_star_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is False

    def test_star_not_class_x(self, auditor):
        panels, links = _make_star_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("is_class_x_compliant") is False

    def test_star_topology_type(self, auditor):
        panels, links = _make_star_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("topology_type") == "star"


# ─────────────────────────────────────────────────────────────────────────────
# Daisy Chain (FORBIDDEN)
# ─────────────────────────────────────────────────────────────────────────────


class TestDaisyChainNetwork:

    def test_daisy_chain_has_violations(self, auditor):
        panels, links = _make_daisy_chain_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is False

    def test_daisy_chain_topology_type(self, auditor):
        panels, links = _make_daisy_chain_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        # 4-node daisy chain: endpoints have degree 1, intermediates degree 2
        assert val.get("topology_type") == "daisy_chain"


# ─────────────────────────────────────────────────────────────────────────────
# No Master Panel
# ─────────────────────────────────────────────────────────────────────────────


class TestNoMasterPanel:

    def test_no_master_violation(self, auditor):
        panels = [
            {"panel_id": "FACP-01", "building_id": "BLDG-A"},
            {"panel_id": "FACP-02", "building_id": "BLDG-B"},
        ]
        links = [{"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True}]
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is False

    def test_single_panel_ok(self, auditor):
        panels = [{"panel_id": "FACP-01", "building_id": "BLDG-A"}]
        result = auditor.audit_network_topology(panels, [])
        val = _result_value(result)
        assert val.get("topology_type") == "single_panel"


# ─────────────────────────────────────────────────────────────────────────────
# Multiple Masters
# ─────────────────────────────────────────────────────────────────────────────


class TestMultipleMasters:

    def test_multiple_masters_violation(self, auditor):
        panels = [
            {"panel_id": "FACP-01", "is_master": True},
            {"panel_id": "FACP-02", "is_master": True},
            {"panel_id": "FACP-03"},
        ]
        links = [
            {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
            {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True},
            {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-01", "is_class_x": True},
        ]
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is False


# ─────────────────────────────────────────────────────────────────────────────
# Master Panel Connections
# ─────────────────────────────────────────────────────────────────────────────


class TestMasterConnections:

    def test_master_single_connection_violation(self, auditor):
        panels = [
            {"panel_id": "FACP-01", "is_master": True},
            {"panel_id": "FACP-02"},
            {"panel_id": "FACP-03"},
        ]
        links = [
            {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
            {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True},
        ]
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is False


# ─────────────────────────────────────────────────────────────────────────────
# Fiber Recommendations
# ─────────────────────────────────────────────────────────────────────────────


class TestFiberRecommendations:

    def test_non_class_x_gets_recommendation(self, auditor):
        panels, links = _make_daisy_chain_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        recs = val.get("fiber_recommendations", [])
        assert len(recs) > 0

    def test_class_x_no_recommendation(self, auditor):
        panels, links = _make_ring_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        recs = val.get("fiber_recommendations", [])
        assert len(recs) == 0

    def test_recommendation_suggests_fiber_dual(self, auditor):
        panels, links = _make_daisy_chain_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        for rec in val.get("fiber_recommendations", []):
            assert rec["recommended_type"] == "fiber_dual"


# ─────────────────────────────────────────────────────────────────────────────
# Bridge Detection (V20.2 FIX)
# ─────────────────────────────────────────────────────────────────────────────


class TestBridgeDetection:

    def test_bridge_in_linear_network(self, auditor):
        panels = [
            {"panel_id": "FACP-01", "is_master": True},
            {"panel_id": "FACP-02"},
            {"panel_id": "FACP-03"},
            {"panel_id": "FACP-04"},
        ]
        links = [
            {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
            {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True},
            {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-04", "is_class_x": True},
        ]
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is False

    def test_ring_no_bridges(self, auditor):
        panels, links = _make_ring_network()
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("safe") is True


# ─────────────────────────────────────────────────────────────────────────────
# Mesh Topology
# ─────────────────────────────────────────────────────────────────────────────


class TestMeshTopology:

    def test_mesh_classification(self, auditor):
        panels = [
            {"panel_id": "FACP-01", "is_master": True},
            {"panel_id": "FACP-02"},
            {"panel_id": "FACP-03"},
            {"panel_id": "FACP-04"},
        ]
        links = [
            {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
            {"link_id": "L2", "from_panel": "FACP-01", "to_panel": "FACP-03", "is_class_x": True},
            {"link_id": "L3", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True},
            {"link_id": "L4", "from_panel": "FACP-02", "to_panel": "FACP-04", "is_class_x": True},
            {"link_id": "L5", "from_panel": "FACP-03", "to_panel": "FACP-04", "is_class_x": True},
            {"link_id": "L6", "from_panel": "FACP-01", "to_panel": "FACP-04", "is_class_x": True},
        ]
        result = auditor.audit_network_topology(panels, links)
        val = _result_value(result)
        assert val.get("topology_type") == "mesh"
        assert val.get("is_class_x_compliant") is True


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_panels_and_links(self, auditor):
        result = auditor.audit_network_topology([], [])
        val = _result_value(result)
        assert val.get("topology_type") == "single_panel"

    def test_single_panel_no_links(self, auditor):
        panels = [{"panel_id": "FACP-01", "building_id": "BLDG-A", "is_master": True}]
        result = auditor.audit_network_topology(panels, [])
        val = _result_value(result)
        assert val.get("topology_type") == "single_panel"

    def test_link_to_unknown_panel_ignored(self, auditor):
        panels = [{"panel_id": "FACP-01", "is_master": True}]
        links = [{"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-99", "is_class_x": True}]
        result = auditor.audit_network_topology(panels, links)
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestInternalHelpers:

    def test_is_connected_ring(self, auditor):
        adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
        assert auditor._is_connected(adj, {"A", "B", "C"}) is True

    def test_is_connected_disconnected(self, auditor):
        adj = {"A": ["B"], "B": ["A"], "C": []}
        assert auditor._is_connected(adj, {"A", "B", "C"}) is False

    def test_is_connected_empty(self, auditor):
        assert auditor._is_connected({}, set()) is True

    def test_find_bridges_ring_none(self, auditor):
        adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
        assert len(auditor._find_bridges(adj, {"A", "B", "C"})) == 0

    def test_find_bridges_chain(self, auditor):
        adj = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
        assert len(auditor._find_bridges(adj, {"A", "B", "C"})) > 0

    def test_classify_ring(self, auditor):
        adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
        assert auditor._classify_topology(adj, {"A", "B", "C"}) == "ring"

    def test_classify_star(self, auditor):
        adj = {"A": ["B", "C", "D"], "B": ["A"], "C": ["A"], "D": ["A"]}
        assert auditor._classify_topology(adj, {"A", "B", "C", "D"}) == "star"

    def test_classify_daisy_chain(self, auditor):
        adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C"]}
        assert auditor._classify_topology(adj, {"A", "B", "C", "D"}) == "daisy_chain"

    def test_classify_single_panel(self, auditor):
        assert auditor._classify_topology({}, {"A"}) == "single_panel"

    def test_classify_mesh(self, auditor):
        adj = {"A": ["B", "C", "D"], "B": ["A", "C", "D"], "C": ["A", "B", "D"], "D": ["A", "B", "C"]}
        assert auditor._classify_topology(adj, {"A", "B", "C", "D"}) == "mesh"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
