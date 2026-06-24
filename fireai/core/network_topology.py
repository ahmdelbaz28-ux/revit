"""fireai/core/network_topology.py
=================================
Master Network Backbone Topology & Class X Redundancy Router.

V20 CRITICAL LIFE-SAFETY MODULE.

In campus-scale installations with multiple FACP panels (master +
satellites), the network communication backbone between panels must
survive any single point of failure.  NFPA 72 §23.8 and §12.3
mandate Class X (redundant path) connectivity for network links
between fire alarm control panels.

Without Class X redundancy:
  - A single cable cut in a building corridor severs ALL downstream
    panels from the master, leaving them as orphaned stand-alone units.
  - Coordinated evacuation sequences, strobe synchronization, and
    fire department notification are lost for the affected buildings.
  - Each orphaned panel operates independently, potentially causing
    conflicting instructions to occupants.

This module:
  1. Analyses the physical topology of network links between panels.
  2. Verifies Class X (redundant path) compliance for every link.
  3. Generates fiber optic or copper trunk routing recommendations.
  4. Flags single-point-of-failure links that violate NFPA 72 §23.8.

Topology types:
  - **Star**: All panels connect to a single hub.  Hub failure = total loss.
  - **Daisy-chain**: Panels connect in series.  Any mid-chain cut isolates
    all downstream panels.  FORBIDDEN for life-safety networks.
  - **Ring (Class X)**: Panels connect in a loop.  Any single cut leaves
    all panels connected via the alternate path.  REQUIRED per NFPA 72.
  - **Dual-fiber ring**: Redundant fiber optic paths — gold standard.

Code references:
  - NFPA 72-2022 §23.8  — Networked systems
  - NFPA 72-2022 §12.3  — Pathway survivability
  - UL 864 10th Edition — Network communication integrity
  - NFPA 72-2022 §12.2  — Pathway design

Provenance:
  Returns ``DecisionProvenance`` via the ``.new()`` factory when
  ``src.v8_core`` is available; degrades gracefully to plain dict.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Required topology for NFPA 72 compliance
REQUIRED_TOPOLOGY: str = "ring"  # Class X = ring / dual-path

# Citations
_CITE_NFPA72_23_8 = "NFPA 72-2022 §23.8"
_CITE_NFPA72_12_3 = "NFPA 72-2022 §12.3"
_CITE_NFPA72_12_2 = "NFPA 72-2022 §12.2"
_CITE_UL864 = "UL 864 10th Ed."


@dataclass(frozen=True)
class PanelNode:
    """Represents a FACP panel in the network topology.

    Attributes:
        panel_id: Unique panel identifier (e.g. "FACP-01").
        building_id: Building identifier (e.g. "BLDG-A").
        location: (x, y) coordinate for routing.
        is_master: Whether this is the master (central) panel.

    """

    panel_id: str
    building_id: str
    location: Tuple[float, float] = (0.0, 0.0)
    is_master: bool = False


@dataclass(frozen=True)
class NetworkLink:
    """Represents a physical network link between two panels.

    Attributes:
        link_id: Unique link identifier.
        from_panel: Source panel ID.
        to_panel: Destination panel ID.
        link_type: "copper", "fiber_single", "fiber_dual".
        is_class_x: Whether this link has redundant path (Class X).
        length_m: Physical cable length in metres.

    """

    link_id: str
    from_panel: str
    to_panel: str
    link_type: str = "copper"
    is_class_x: bool = False
    length_m: float = 0.0


class NetworkTopologyAuditor:
    """Audits and designs the master network backbone topology
    for Class X compliance per NFPA 72 §23.8.

    The auditor analyses the network graph formed by panel nodes and
    inter-panel links, verifying that:
      1. Every panel has at least two independent paths to the master.
      2. No single link failure can isolate any panel.
      3. The overall topology forms a ring (Class X) or better.

    Usage::

        auditor = NetworkTopologyAuditor()
        result = auditor.audit_network_topology(
            panels=[...],
            links=[...],
        )
    """

    def __init__(self) -> None:
        pass

    def audit_network_topology(
        self,
        panels: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
    ) -> Any:
        """Audit the network topology for Class X compliance.

        Args:
            panels: Each dict must have:
                - ``panel_id`` (str): Panel identifier.
                - ``building_id`` (str, optional): Building ID.
                - ``is_master`` (bool, optional): Master panel flag.
            links: Each dict must have:
                - ``link_id`` (str): Link identifier.
                - ``from_panel`` (str): Source panel ID.
                - ``to_panel`` (str): Destination panel ID.
                - ``link_type`` (str, optional): Cable type.
                - ``is_class_x`` (bool, optional): Redundant path flag.
                - ``length_m`` (float, optional): Cable length.

        Returns:
            ``DecisionProvenance`` or plain dict.

        """
        violations: list = []
        fiber_recommendations: List[Dict[str, Any]] = []

        # Build adjacency graph
        panel_ids = set()
        master_id = None
        master_count = 0
        for p in panels:
            pid = p.get("panel_id", "UNKNOWN")
            panel_ids.add(pid)
            if p.get("is_master", False):
                master_id = pid
                master_count += 1

        # HIGH: No master panel with multiple panels
        if master_id is None and len(panel_ids) > 1:
            desc = (
                f"No master panel designated in a {len(panel_ids)}-panel "
                f"network. NFPA 72 \u00a723.8 requires a designated master "
                f"panel for coordinated evacuation and notification. "
                f"Without a master, no panel can orchestrate network-wide "
                f"alarm sequences."
            )
            if Violation is not None:
                violations.append(
                    Violation(
                        severity="CRITICAL",
                        citation=_CITE_NFPA72_23_8,
                        description=desc,
                    )
                )
            else:
                violations.append(
                    {
                        "severity": "CRITICAL",
                        "citation": _CITE_NFPA72_23_8,
                        "description": desc,
                    }
                )
            logger.critical(desc)

        # MEDIUM: Multiple masters silently overwritten
        if master_count > 1:
            desc = (
                f"{master_count} master panels designated. Only one master "
                f"is permitted per NFPA 72 \u00a723.8 network. Multiple masters "
                f"cause conflicting command authority and synchronization "
                f"failures."
            )
            if Violation is not None:
                violations.append(
                    Violation(
                        severity="HIGH",
                        citation=_CITE_NFPA72_23_8,
                        description=desc,
                    )
                )
            else:
                violations.append(
                    {
                        "severity": "HIGH",
                        "citation": _CITE_NFPA72_23_8,
                        "description": desc,
                    }
                )
            logger.warning(desc)

        # Build adjacency list (undirected)
        adj: Dict[str, List[str]] = {pid: [] for pid in panel_ids}
        link_details: Dict[str, Dict[str, Any]] = {}

        for link in links:
            lid = link.get("link_id", "UNKNOWN")
            from_p = link.get("from_panel", "")
            to_p = link.get("to_panel", "")
            is_class_x = link.get("is_class_x", False)
            link_type = link.get("link_type", "copper")
            length_m = float(link.get("length_m", 0.0))

            if from_p in panel_ids and to_p in panel_ids:
                adj[from_p].append(to_p)
                adj[to_p].append(from_p)
                link_details[lid] = {
                    "from": from_p,
                    "to": to_p,
                    "is_class_x": is_class_x,
                    "link_type": link_type,
                    "length_m": length_m,
                }

        # Check 1: Every non-master panel must have ≥2 connections
        # (Class X = redundant path)
        #
        # V20.2 FIX: Now also verifies 2-edge-connectivity (bridge-finding).
        # Previously only checked degree (number of adjacent links) per panel,
        # which is NECESSARY but NOT SUFFICIENT. A panel can have degree ≥2
        # yet still be isolated from the master by a single link cut if its
        # redundant connections both route through the same neighbor.
        # Now uses Tarjan's bridge-finding algorithm to detect bridge edges
        # that would disconnect the graph if cut.
        for pid in panel_ids:
            if pid == master_id:
                continue
            connections = adj.get(pid, [])
            if len(connections) < 2:
                desc = (
                    f"Panel '{pid}' has only {len(connections)} network "
                    f"connection(s). NFPA 72 §23.8 requires Class X "
                    f"(minimum 2 independent paths) for life-safety "
                    f"network backbone. A single cable cut will isolate "
                    f"this panel from the master."
                )
                if Violation is not None:
                    violations.append(
                        Violation(
                            severity="CRITICAL",
                            citation=_CITE_NFPA72_23_8,
                            description=desc,
                        )
                    )
                else:
                    violations.append(
                        {
                            "severity": "CRITICAL",
                            "citation": _CITE_NFPA72_23_8,
                            "description": desc,
                        }
                    )
                logger.critical(desc)

        # Check 2: All non-Class-X links are single points of failure
        for lid, details in link_details.items():
            if not details["is_class_x"]:
                fiber_recommendations.append(
                    {
                        "link_id": lid,
                        "from": details["from"],
                        "to": details["to"],
                        "current_type": details["link_type"],
                        "recommended_type": "fiber_dual",
                        "reason": (
                            f"{details['link_type']} link without Class X "
                            f"redundancy is a single point of failure. "
                            f"Replace with dual fiber optic ring per "
                            f"NFPA 72 §23.8."
                        ),
                    }
                )

        # Check 3: Master panel must have ≥2 connections (if network >1)
        if master_id and len(panel_ids) > 1:
            master_connections = adj.get(master_id, [])
            if len(master_connections) < 2:
                desc = (
                    f"Master panel '{master_id}' has only "
                    f"{len(master_connections)} connection(s). The master "
                    f"is the single point of failure for the entire "
                    f"network. Ring topology requires ≥2 connections."
                )
                if Violation is not None:
                    violations.append(
                        Violation(
                            severity="CRITICAL",
                            citation=_CITE_NFPA72_23_8,
                            description=desc,
                        )
                    )
                else:
                    violations.append(
                        {
                            "severity": "CRITICAL",
                            "citation": _CITE_NFPA72_23_8,
                            "description": desc,
                        }
                    )
                logger.critical(desc)

        # Determine topology type
        topology_type = self._classify_topology(adj, panel_ids)

        # CRITICAL: Disconnected rings — degree-2 nodes but not fully connected
        if topology_type == "disconnected_rings":
            desc = (
                "Network panels each have 2 connections but the graph is "
                "not fully connected. The topology consists of isolated "
                "ring segments, which means some panels cannot reach the "
                "master at all. NFPA 72 §23.8 requires all panels to be "
                "on a single connected Class X network."
            )
            if Violation is not None:
                violations.append(
                    Violation(
                        severity="CRITICAL",
                        citation=_CITE_NFPA72_23_8,
                        description=desc,
                    )
                )
            else:
                violations.append(
                    {
                        "severity": "CRITICAL",
                        "citation": _CITE_NFPA72_23_8,
                        "description": desc,
                    }
                )
            logger.critical(desc)

        # V20.2 FIX: Check 4 — Bridge detection (2-edge-connectivity).
        # A bridge edge is one whose removal disconnects the graph.
        # NFPA 72 §23.8 requires NO single point of failure in the
        # network backbone. If any bridge exists between a non-master
        # panel and the master, that panel can be isolated by a single
        # cable cut — violating Class X redundancy.
        if master_id and len(panel_ids) > 2:
            bridges = self._find_bridges(adj, panel_ids)
            for bridge_from, bridge_to in bridges:
                # Only flag bridges that could isolate a panel from the master
                # Check if removing this bridge disconnects any panel from master
                test_adj = {p: list(neighbors) for p, neighbors in adj.items()}
                if bridge_to in test_adj.get(bridge_from, []):
                    test_adj[bridge_from].remove(bridge_to)
                if bridge_from in test_adj.get(bridge_to, []):
                    test_adj[bridge_to].remove(bridge_from)
                # Find panels disconnected from master
                reachable = set()
                queue = deque([master_id])
                reachable.add(master_id)
                while queue:
                    node = queue.popleft()
                    for neighbor in test_adj.get(node, []):
                        if neighbor not in reachable:
                            reachable.add(neighbor)
                            queue.append(neighbor)
                disconnected = panel_ids - reachable
                if disconnected:
                    desc = (
                        f"BRIDGE_EDGE: Link '{bridge_from}' ↔ '{bridge_to}' is a "
                        f"single point of failure. Removing this link disconnects "
                        f"{len(disconnected)} panel(s) from the master: "
                        f"{sorted(disconnected)}. NFPA 72 §23.8 requires Class X "
                        f"redundancy — no single cable cut may isolate any panel. "
                        f"Add a redundant path between these panels."
                    )
                    if Violation is not None:
                        violations.append(
                            Violation(
                                severity="CRITICAL",
                                citation=_CITE_NFPA72_23_8,
                                description=desc,
                            )
                        )
                    else:
                        violations.append(
                            {
                                "severity": "CRITICAL",
                                "citation": _CITE_NFPA72_23_8,
                                "description": desc,
                            }
                        )
                    logger.critical(desc)

        # Classify overall compliance
        is_class_x_compliant = len(violations) == 0 and topology_type in ("ring", "mesh")
        safe = len(violations) == 0

        # Build provenance result
        if DecisionProvenance is not None:
            try:
                rules = [
                    RuleApplied(
                        citation=_CITE_NFPA72_23_8,
                        constant_id="CLASS_X_NETWORK",
                        value_used=2.0,
                        unit="minimum_paths",
                    ),
                    RuleApplied(
                        citation=_CITE_NFPA72_12_3,
                        constant_id="PATHWAY_SURVIVABILITY",
                        value_used=1.0,
                        unit="BOOLEAN",
                    ),
                ]
                conf = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH if safe else ConfidenceLevel.LOW,
                )
                return DecisionProvenance.new(
                    decision_type="network_topology_audit",
                    value={
                        "topology_type": topology_type,
                        "is_class_x_compliant": is_class_x_compliant,
                        "fiber_recommendations": fiber_recommendations,
                        "total_panels": len(panel_ids),
                        "total_links": len(links),
                        "single_points_of_failure": len(violations),
                        "safe": safe,
                    },
                    inputs={
                        "panels": len(panels),
                        "links": len(links),
                        "master_id": master_id,
                    },
                    rules_applied=rules,
                    algorithm={"name": "RedundantPathFinder", "version": "v20"},
                    confidence=conf,
                    selected_because=(
                        "Network backbone between FACP panels must survive any "
                        "single point of failure per NFPA 72 §23.8. Class X "
                        "(ring/dual-path) topology ensures no single cable cut "
                        "can isolate any panel from the master."
                    ),
                    violations=violations if violations else None,
                )
            except Exception as exc:
                logger.warning("Failed to record network topology audit decision: %s", exc)

        return {
            "decision_type": "network_topology_audit",
            "value": {
                "topology_type": topology_type,
                "is_class_x_compliant": is_class_x_compliant,
                "fiber_recommendations": fiber_recommendations,
                "safe": safe,
            },
            "safe": safe,
            "violations": violations,
        }

    def _classify_topology(
        self,
        adj: Dict[str, List[str]],
        panel_ids: set,
    ) -> str:
        """Classify the network topology type.

        Returns:
            "star", "daisy_chain", "ring", "disconnected_rings", "mesh",
            or "unknown".

        """
        if len(panel_ids) <= 1:
            return "single_panel"

        # Count connections per panel
        conn_counts = {pid: len(adj.get(pid, [])) for pid in panel_ids}

        # Ring: every panel has exactly 2 connections AND graph is connected
        if all(c == 2 for c in conn_counts.values()):
            if self._is_connected(adj, panel_ids):
                return "ring"
            return "disconnected_rings"

        # Star: one hub has N-1 connections, all others have 1
        max_conn = max(conn_counts.values())
        min_conn = min(conn_counts.values())
        hubs = sum(1 for c in conn_counts.values() if c == max_conn)

        if hubs == 1 and max_conn == len(panel_ids) - 1 and min_conn == 1:
            return "star"

        # Mesh: multiple panels with >2 connections
        if sum(1 for c in conn_counts.values() if c > 2) > 1:
            return "mesh"

        # Daisy-chain: exactly 2 endpoints with 1 connection each,
        # all intermediates with exactly degree 2
        endpoints = sum(1 for c in conn_counts.values() if c == 1)
        intermediates = [c for c in conn_counts.values() if c != 1]
        if endpoints == 2 and all(c == 2 for c in intermediates):
            return "daisy_chain"

        return "unknown"

    @staticmethod
    def _is_connected(
        adj: Dict[str, List[str]],
        panel_ids: set,
    ) -> bool:
        """Check whether the graph is fully connected using BFS.

        Returns:
            True if all panels are reachable from any starting panel.

        """
        if not panel_ids:
            return True
        start = next(iter(panel_ids))
        visited = set()
        queue = deque([start])
        visited.add(start)
        while queue:
            node = queue.popleft()
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited == panel_ids

    @staticmethod
    def _find_bridges(
        adj: Dict[str, List[str]],
        panel_ids: set,
    ) -> List[Tuple[str, str]]:
        """Find all bridge edges using Tarjan's algorithm.

        A bridge is an edge whose removal increases the number of
        connected components. In a life-safety network, a bridge is
        a single point of failure that violates NFPA 72 §23.8.

        Returns:
            List of (from_panel, to_panel) tuples that are bridge edges.

        """
        # Tarjan's bridge-finding: O(V + E)
        visited = set()
        disc = {}  # discovery time
        low = {}  # low-link value
        parent = {}
        bridges = []
        timer = [0]  # mutable counter

        def dfs(u):
            visited.add(u)
            disc[u] = low[u] = timer[0]
            timer[0] += 1
            for v in adj.get(u, []):
                if v not in visited:
                    parent[v] = u
                    dfs(v)
                    low[u] = min(low[u], low[v])
                    # If low[v] > disc[u], (u,v) is a bridge
                    if low[v] > disc[u]:
                        bridges.append((u, v))
                elif v != parent.get(u):
                    low[u] = min(low[u], disc[v])

        for pid in panel_ids:
            if pid not in visited:
                parent[pid] = None
                dfs(pid)

        return bridges


__all__ = [
    "REQUIRED_TOPOLOGY",
    "NetworkLink",
    "NetworkTopologyAuditor",
    "PanelNode",
]
