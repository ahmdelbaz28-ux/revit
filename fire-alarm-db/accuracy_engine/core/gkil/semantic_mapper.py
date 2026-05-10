from typing import List, Dict, Tuple, Optional
from core.risk_tensor.constraint_graph import DifferentiableConstraintGraph
from core.gkil.decision_stratification import DecisionStratificationEngine
from core.gkil.cad_data_model import (
    CADGraph, CADVertex, CADEdge, CADConstraint, CADZone, CADEntityType
)


class SemanticGeometryMapper:
    def __init__(self):
        self.tolerance_meters = 0.01
        self.vertex_counter = 0
        self.edge_counter = 0
        self.constraint_counter = 0
        self.zone_counter = 0

    def spectral_to_cad(self, topology, constraint_graph, spectral_metadata: Dict) -> CADGraph:
        vertices = []
        edges = []
        constraints = []
        zones = []

        for node in topology.nodes:
            cad_vertex = self._map_node_to_vertex(node, spectral_metadata)
            vertices.append(cad_vertex)

        for edge in topology.edges:
            cad_edge = self._map_edge_to_cad(edge)
            edges.append(cad_edge)

        if constraint_graph:
            dcge_results = constraint_graph.evaluate({})
            for constraint_id, result in dcge_results.items():
                cad_constraint = self._map_constraint_to_cad(constraint_id, result, vertices)
                constraints.append(cad_constraint)

        room_id = getattr(topology, 'room_id', 'unknown')
        zone = CADZone(
            zone_id=f"ZONE_{self._next_zone_id()}",
            zone_name=f"Zone_{room_id}",
            vertices=[v.vertex_id for v in vertices],
            spectral_risk=spectral_metadata.get("risk_index", 0.0),
            stability_index=spectral_metadata.get("spectral_radius", 0.0)
        )
        zones.append(zone)

        return CADGraph(
            graph_id=f"CAD_GRAPH_{room_id}",
            project_name=spectral_metadata.get("project_name", "Unknown"),
            vertices=vertices,
            edges=edges,
            constraints=constraints,
            zones=zones,
            metadata=spectral_metadata
        )

    def _map_node_to_vertex(self, node, spectral_metadata: Dict) -> CADVertex:
        self.vertex_counter += 1
        entity_type = self._infer_entity_type(node)

        return CADVertex(
            vertex_id=f"VERTEX_{self.vertex_counter}",
            x=getattr(node, 'x', 0.0),
            y=getattr(node, 'y', 0.0),
            z=getattr(node, 'z', 3.0) if hasattr(node, 'z') else 3.0,
            entity_type=entity_type,
            properties={
                "node_type": node.node_type,
                "status": node.status,
                "zone_id": getattr(node, 'zone_id', 'unknown')
            },
            spectral_metadata={
                "failure_probability": getattr(node, 'failure_probability', 0.0),
                "coverage_strength": getattr(node, 'coverage_strength', 1.0),
                "influence_radius": getattr(node, 'influence_radius', 7.5),
                "risk_index": spectral_metadata.get("risk_index", 0.0)
            }
        )

    def _map_edge_to_cad(self, edge) -> CADEdge:
        self.edge_counter += 1

        return CADEdge(
            edge_id=f"EDGE_{self.edge_counter}",
            from_vertex=f"VERTEX_{edge.from_node}",
            to_vertex=f"VERTEX_{edge.to_node}",
            edge_type=edge.relationship if hasattr(edge, 'relationship') else "generic",
            length=edge.weight * 10.0 if hasattr(edge, 'weight') else 0.0,
            properties={
                "relationship": edge.relationship if hasattr(edge, 'relationship') else "unknown",
                "weight": edge.weight if hasattr(edge, 'weight') else 1.0
            }
        )

    def _map_constraint_to_cad(self, constraint_id: str, result: Dict, vertices: List[CADVertex]) -> CADConstraint:
        self.constraint_counter += 1

        constraint_type_map = {
            "COLLISION_DETECT": "geometric_collision",
            "MIN_SPACING": "distance_constraint",
            "COVERAGE_RADIUS": "coverage_constraint",
            "MOUNTING_FEASIBILITY": "geometric_feasibility",
            "CONNECTIVITY_VALID": "topology_constraint"
        }

        NFPA_map = {
            "COLLISION_DETECT": "NFPA 72 - General",
            "MIN_SPACING": "NFPA 72 17.6.3",
            "COVERAGE_RADIUS": "NFPA 72 17.6.3.1",
            "MOUNTING_FEASIBILITY": "NFPA 72 17.7",
            "CONNECTIVITY_VALID": "NFPA 72 17.7.1"
        }

        return CADConstraint(
            constraint_id=f"CONSTRAINT_{self.constraint_counter}",
            constraint_type=constraint_type_map.get(constraint_id, "unknown"),
            source_rule=constraint_id,
            NFPA_reference=NFPA_map.get(constraint_id, "NFPA 72"),
            severity=result.get("priority", "MEDIUM"),
            target_entities=[v.vertex_id for v in vertices[:2]] if vertices else [],
            constraint_function=constraint_id,
            parameters={
                "weight": result.get("weight", 1.0),
                "violation": result.get("violation", 0.0),
                "passed": result.get("passed", True)
            }
        )

    def _infer_entity_type(self, node) -> CADEntityType:
        node_type = getattr(node, 'node_type', '')
        if 'detector' in node_type:
            return CADEntityType.DETECTOR
        elif 'panel' in node_type:
            return CADEntityType.PANEL
        elif 'cable' in node_type:
            return CADEntityType.CABLE_PATH
        return CADEntityType.DETECTOR

    def _next_zone_id(self) -> int:
        self.zone_counter += 1
        return self.zone_counter

    def validate_decision_preservation(self, states: List[Dict], decisions: List[str]) -> Dict:
        engine = DecisionStratificationEngine()
        strata_map = engine.construct_quotient_map(states, decisions)
        validation = engine.validate_stratification()

        return {
            "is_valid": validation["is_valid"],
            "violations": validation["violations"],
            "total_strata": validation["total_strata"],
            "decision_classes": validation["decision_classes"],
            "sufficient_statistics": [
                {
                    "metric_name": s.metric_name,
                    "importance_score": s.importance_score,
                    "decision_correlation": s.decision_correlation,
                    "preserves_boundary": s.preserves_boundary
                }
                for s in engine.sufficient_stats[:5]
            ],
            "boundary_metrics": engine.boundary_metrics
        }