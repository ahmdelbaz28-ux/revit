"""
topology_graph_service.py — Neo4j-backed Network Topology Graph
====================================================================

Provides graph-based topology awareness for electrical networks. Without
this, agents cannot answer "if I trip this breaker, which loads are
affected?" — a fundamental question for power system analysis.

Capabilities:
1. **Topology Awareness**: Electrical network as graph (Bus → Line →
   Transformer → Load) with properties (impedance, rating, status).
2. **CIM Integration**: Convert CIM CGMES directly to Neo4j graph nodes/edges.
3. **Impact Analysis**: "If I trip this breaker, which loads are affected?"
   answered with Cypher query in <10ms.
4. **Digital Twin State**: Every network element = node, every relationship
   = edge with properties (impedance, rating, status, voltage_level).

Architecture:
- Uses Neo4j as the graph database (docker-compose service)
- Falls back to in-memory graph when server unavailable (dev mode)
- Cypher queries for complex graph traversals
- Node labels: Bus, Line, Transformer, Load, Breaker, Generator
- Relationship types: CONNECTED_TO, FEEDS, PROTECTED_BY, PARALLEL_WITH

References:
- Neo4j Python driver: https://neo4j.com/docs/api/python-driver/
- CIM CGMES: IEC 61970/61968
- agent.md Rule 12: Topology data is ADVISORY for AI agents
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEO4J_URI_ENV = "NEO4J_URI"
NEO4J_URI_DEFAULT = "bolt://localhost:7687"
NEO4J_USER_ENV = "NEO4J_USER"
NEO4J_USER_DEFAULT = "neo4j"
NEO4J_PASSWORD_ENV = "NEO4J_PASSWORD"
NEO4J_PASSWORD_DEFAULT = "etap_password"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ElementType(str, Enum):
    """Types of electrical network elements (Neo4j node labels)."""

    BUS = "Bus"
    LINE = "Line"
    TRANSFORMER = "Transformer"
    LOAD = "Load"
    BREAKER = "Breaker"
    GENERATOR = "Generator"
    CAPACITOR = "Capacitor"
    MOTOR = "Motor"
    PANEL = "Panel"


class RelationshipType(str, Enum):
    """Types of relationships between network elements (Neo4j edge types)."""

    CONNECTED_TO = "CONNECTED_TO"
    FEEDS = "FEEDS"
    PROTECTED_BY = "PROTECTED_BY"
    PARALLEL_WITH = "PARALLEL_WITH"
    UPSTREAM_OF = "UPSTREAM_OF"
    DOWNSTREAM_OF = "DOWNSTREAM_OF"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class NetworkElement:
    """
    A single electrical network element (Neo4j node).

    Attributes:
        element_id: Unique identifier (e.g., "BUS-001", "LINE-042").
        element_type: Type of element (Bus, Line, Transformer, etc.).
        name: Human-readable name.
        properties: Element properties (impedance, rating, voltage, status).
    """

    element_id: str
    element_type: ElementType
    name: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type.value,
            "name": self.name,
            "properties": self.properties,
        }


@dataclass
class NetworkConnection:
    """
    A connection between two network elements (Neo4j edge).

    Attributes:
        from_element: Source element ID.
        to_element: Target element ID.
        relationship_type: Type of relationship.
        properties: Connection properties (impedance, length, status).
    """

    from_element: str
    to_element: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_element,
            "to": self.to_element,
            "relationship_type": self.relationship_type.value,
            "properties": self.properties,
        }


@dataclass
class ImpactAnalysisResult:
    """
    Result of a breaker trip impact analysis.

    Attributes:
        breaker_id: The breaker that was tripped.
        affected_loads: List of load IDs affected by the trip.
        affected_buses: List of bus IDs that lose power.
        path_count: Number of paths analyzed.
        analysis_ms: Time taken for the analysis.
    """

    breaker_id: str
    affected_loads: List[str] = field(default_factory=list)
    affected_buses: List[str] = field(default_factory=list)
    path_count: int = 0
    analysis_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "breaker_id": self.breaker_id,
            "affected_loads": self.affected_loads,
            "affected_buses": self.affected_buses,
            "affected_count": len(self.affected_loads) + len(self.affected_buses),
            "path_count": self.path_count,
            "analysis_ms": round(self.analysis_ms, 2),
        }


# ---------------------------------------------------------------------------
# Topology Graph Service
# ---------------------------------------------------------------------------


class TopologyGraphService:
    """
    Neo4j-backed network topology graph service.

    Usage:
        service = TopologyGraphService()

        # Add elements
        service.add_element(NetworkElement(
            element_id="BUS-001",
            element_type=ElementType.BUS,
            name="Main Switchgear",
            properties={"voltage_kv": 13.8, "rating_amps": 2000},
        ))

        # Add connections
        service.add_connection(NetworkConnection(
            from_element="BUS-001",
            to_element="BUS-002",
            relationship_type=RelationshipType.FEEDS,
            properties={"impedance_ohm": 0.05, "length_m": 100},
        ))

        # Impact analysis: "If I trip this breaker, what's affected?"
        result = service.analyze_breaker_impact("BRK-001")
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """
        Initialize the topology graph service.

        Args:
            uri: Neo4j bolt URI. If None, reads from env var.
            user: Neo4j username. If None, reads from env var.
            password: Neo4j password. If None, reads from env var.
        """
        self._uri = uri or os.environ.get(NEO4J_URI_ENV, NEO4J_URI_DEFAULT)
        self._user = user or os.environ.get(NEO4J_USER_ENV, NEO4J_USER_DEFAULT)
        self._password = password or os.environ.get(NEO4J_PASSWORD_ENV, NEO4J_PASSWORD_DEFAULT)
        self._driver = None
        self._initialized = False
        # Fallback in-memory graph (for dev mode without Neo4j)
        self._in_memory_nodes: Dict[str, NetworkElement] = {}
        self._in_memory_edges: List[NetworkConnection] = []

    # ------------------------------------------------------------------
    # Lazy Initialization
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Initialize Neo4j driver (lazy)."""
        if self._initialized:
            return

        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            # Test connection
            with self._driver.session() as session:
                session.run("RETURN 1").consume()

            # Create constraints and indexes
            self._create_schema()

            logger.info("Neo4j connected to %s", self._uri)
        except Exception as exc:
            logger.warning(
                "Neo4j initialization failed (%s). Topology graph will use in-memory fallback.",
                exc,
            )
            self._driver = None

        self._initialized = True

    def _create_schema(self) -> None:
        """Create Neo4j constraints and indexes."""
        if self._driver is None:
            return

        try:
            with self._driver.session() as session:
                # Create unique constraint on element_id for each label
                for element_type in ElementType:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{element_type.value}) REQUIRE n.element_id IS UNIQUE"
                    )
        except Exception as exc:
            logger.debug("Schema creation: %s", exc)

    # ------------------------------------------------------------------
    # Add Elements
    # ------------------------------------------------------------------

    def add_element(self, element: NetworkElement) -> bool:
        """
        Add a network element to the graph.

        Args:
            element: NetworkElement to add.

        Returns:
            True if added, False if failed.
        """
        self._initialize()

        if self._driver is None:
            # In-memory fallback
            self._in_memory_nodes[element.element_id] = element
            return True

        try:
            with self._driver.session() as session:
                session.run(
                    f"MERGE (n:{element.element_type.value} {{element_id: $id}}) "
                    "SET n.name = $name, n += $props",
                    id=element.element_id,
                    name=element.name,
                    props=element.properties,
                )
            return True
        except Exception as exc:
            logger.error("Failed to add element: %s", exc)
            return False

    def add_connection(self, connection: NetworkConnection) -> bool:
        """
        Add a connection between two elements.

        Args:
            connection: NetworkConnection to add.

        Returns:
            True if added, False if failed.
        """
        self._initialize()

        if self._driver is None:
            # In-memory fallback
            self._in_memory_edges.append(connection)
            return True

        try:
            with self._driver.session() as session:
                session.run(
                    "MATCH (a {element_id: $from_id}), (b {element_id: $to_id}) "
                    f"MERGE (a)-[r:{connection.relationship_type.value}]->(b) "
                    "SET r += $props",
                    from_id=connection.from_element,
                    to_id=connection.to_element,
                    props=connection.properties,
                )
            return True
        except Exception as exc:
            logger.error("Failed to add connection: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Impact Analysis
    # ------------------------------------------------------------------

    def analyze_breaker_impact(
        self,
        breaker_id: str,
        max_depth: int = 20,
    ) -> ImpactAnalysisResult:
        """
        Analyze the impact of tripping a breaker.

        Answers: "If I trip this breaker, which loads and buses are affected?"

        Uses Cypher graph traversal to find all downstream elements that
        lose power when the breaker is opened.

        Args:
            breaker_id: ID of the breaker to trip.
            max_depth: Maximum traversal depth (prevents infinite loops).

        Returns:
            ImpactAnalysisResult with affected loads and buses.
        """
        import time

        t_start = time.perf_counter()

        self._initialize()

        if self._driver is None:
            return self._in_memory_impact_analysis(breaker_id, t_start)

        try:
            with self._driver.session() as session:
                # Find all Load nodes downstream of the breaker
                # Traversal: Breaker → FEEDS/CONNECTED_TO → * → Load
                # V141 FIX: Neo4j Cypher doesn't allow parameterized depth in relationship patterns.
                # Use string interpolation for depth (safe — max_depth is an int we control).
                cypher_query = (
                    "MATCH (b:Breaker {element_id: $breaker_id}) "
                    f"MATCH path = (b)-[:FEEDS|CONNECTED_TO*1..{max_depth}]->(target) "
                    "WHERE target:Load OR target:Bus "
                    "WITH DISTINCT target, path "
                    "WHERE NOT target.element_id = $breaker_id "
                    "RETURN "
                    "  collect(DISTINCT CASE WHEN target:Load THEN target.element_id END) AS affected_loads, "
                    "  collect(DISTINCT CASE WHEN target:Bus THEN target.element_id END) AS affected_buses, "
                    "  count(path) AS path_count"
                )
                result = session.run(cypher_query, breaker_id=breaker_id)

                record = result.single()
                elapsed_ms = (time.perf_counter() - t_start) * 1000.0

                if record:
                    return ImpactAnalysisResult(
                        breaker_id=breaker_id,
                        affected_loads=record["affected_loads"] or [],
                        affected_buses=record["affected_buses"] or [],
                        path_count=record["path_count"] or 0,
                        analysis_ms=elapsed_ms,
                    )

                return ImpactAnalysisResult(
                    breaker_id=breaker_id,
                    analysis_ms=elapsed_ms,
                )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            logger.error("Impact analysis failed: %s", exc)
            return ImpactAnalysisResult(
                breaker_id=breaker_id,
                analysis_ms=elapsed_ms,
            )

    def _in_memory_impact_analysis(self, breaker_id: str, t_start: float) -> ImpactAnalysisResult:
        """Fallback impact analysis using in-memory graph (BFS)."""
        import time
        from collections import deque

        affected_loads: Set[str] = set()
        affected_buses: Set[str] = set()
        visited: Set[str] = set()
        queue = deque([(breaker_id, 0)])
        path_count = 0

        while queue:
            current, depth = queue.popleft()
            if depth > 20 or current in visited:
                continue
            visited.add(current)

            node = self._in_memory_nodes.get(current)
            if node:
                if node.element_type == ElementType.LOAD:
                    affected_loads.add(current)
                elif node.element_type == ElementType.BUS:
                    affected_buses.add(current)

            # Find downstream connections
            for edge in self._in_memory_edges:
                if edge.from_element == current and edge.to_element not in visited:
                    queue.append((edge.to_element, depth + 1))
                    path_count += 1

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        return ImpactAnalysisResult(
            breaker_id=breaker_id,
            affected_loads=list(affected_loads),
            affected_buses=list(affected_buses),
            path_count=path_count,
            analysis_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_downstream_elements(
        self,
        element_id: str,
        max_depth: int = 10,
    ) -> List[NetworkElement]:
        """
        Get all elements downstream of the given element.

        Args:
            element_id: Starting element ID.
            max_depth: Maximum traversal depth.

        Returns:
            List of downstream NetworkElement objects.
        """
        self._initialize()

        if self._driver is None:
            # In-memory BFS
            result: List[NetworkElement] = []
            visited: Set[str] = set()
            queue = [(element_id, 0)]

            while queue:
                current, depth = queue.pop(0)
                if depth > max_depth or current in visited:
                    continue
                visited.add(current)

                for edge in self._in_memory_edges:
                    if edge.from_element == current and edge.to_element not in visited:
                        node = self._in_memory_nodes.get(edge.to_element)
                        if node:
                            result.append(node)
                        queue.append((edge.to_element, depth + 1))

            return result

        try:
            with self._driver.session() as session:
                result = session.run(
                    """
                    MATCH (start {element_id: $id})
                    MATCH path = (start)-[:FEEDS|CONNECTED_TO*1..$depth]->(target)
                    WITH DISTINCT target
                    RETURN target.element_id AS id, labels(target)[0] AS type,
                           target.name AS name, target AS props
                    """,
                    id=element_id,
                    depth=max_depth,
                )

                elements: List[NetworkElement] = []
                for record in result:
                    type_str = record["type"] or "Bus"
                    try:
                        et = ElementType(type_str)
                    except ValueError:
                        et = ElementType.BUS
                    elements.append(
                        NetworkElement(
                            element_id=record["id"],
                            element_type=et,
                            name=record["name"] or "",
                            properties=dict(record["props"]) if record["props"] else {},
                        )
                    )
                return elements

        except Exception as exc:
            logger.error("Get downstream failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Check Neo4j connectivity."""
        self._initialize()
        if self._driver is None:
            return {
                "healthy": False,
                "uri": self._uri,
                "error": "Neo4j driver not initialized",
                "fallback": "in-memory graph",
                "nodes": len(self._in_memory_nodes),
                "edges": len(self._in_memory_edges),
            }

        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (n) RETURN count(n) AS node_count, count {()-[]->()} AS edge_count"
                )
                record = result.single()

            return {
                "healthy": True,
                "uri": self._uri,
                "nodes": record["node_count"] if record else 0,
                "edges": record["edge_count"] if record else 0,
            }
        except Exception as exc:
            return {
                "healthy": False,
                "uri": self._uri,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_topology_service: Optional[TopologyGraphService] = None


def get_topology_service() -> TopologyGraphService:
    """Get the singleton TopologyGraphService instance."""
    global _topology_service
    if _topology_service is None:
        _topology_service = TopologyGraphService()
    return _topology_service


__all__ = [
    "NEO4J_PASSWORD_DEFAULT",
    "NEO4J_URI_DEFAULT",
    "NEO4J_USER_DEFAULT",
    "ElementType",
    "ImpactAnalysisResult",
    "NetworkConnection",
    "NetworkElement",
    "RelationshipType",
    "TopologyGraphService",
    "get_topology_service",
]
