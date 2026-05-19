import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class ProofStatus(Enum):
    VALID = "valid"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class ClauseStatus(Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class NFPAProofClause:
    clause_id: str
    nfpa_reference: str
    description: str
    status: ClauseStatus
    evidence: Dict[str, Any]
    violation_detail: Optional[str] = None


@dataclass
class FeasibilityCertificate:
    constraint_graph_valid: bool
    geometric_feasibility: bool
    topology_preserved: bool
    spectral_stability: float
    issued_at: str


@dataclass
class ProofObject:
    decision_id: str
    ontology_version: str
    nfpa_version: str
    jurisdiction: str
    input_geometry_hash: str
    decision_semantics_hash: str
    satisfied_clauses: List[NFPAProofClause]
    violated_clauses: List[NFPAProofClause]
    feasibility_certificate: FeasibilityCertificate
    spectral_advisory_trace: Dict[str, float]
    rejected_actions: List[str]
    cad_realization_trace: List[str]
    deterministic_replay_hash: str
    signature: str
    issued_at: str
    status: ProofStatus


class CanonicalProofSerializer:
    def canonicalize_geometry(self, vertices: List[Dict]) -> str:
        sorted_vertices = sorted(vertices, key=lambda v: (v.get("x", 0), v.get("y", 0), v.get("z", 0)))
        normalized = []
        for v in sorted_vertices:
            normalized.append({
                "x": round(v.get("x", 0), 6),
                "y": round(v.get("y", 0), 6),
                "z": round(v.get("z", 0), 6),
                "type": v.get("type", "unknown")
            })
        return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()

    def canonicalize_decision(self, decision_data: Dict) -> str:
        canonical = {
            "decision_type": decision_data.get("decision_type"),
            "target_id": decision_data.get("target_id"),
            "action": decision_data.get("action"),
            "priority": decision_data.get("priority"),
            "ontology_version": decision_data.get("ontology_version"),
            "nfpa_version": decision_data.get("nfpa_version"),
            "jurisdiction": decision_data.get("jurisdiction")
        }
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()

    def canonicalize_derivation_graph(self, proof: ProofObject) -> str:
        derivation_data = {
            "input_geometry_hash": proof.input_geometry_hash,
            "decision_semantics_hash": proof.decision_semantics_hash,
            "satisfied_clauses": sorted([c.clause_id for c in proof.satisfied_clauses]),
            "violated_clauses": sorted([c.clause_id for c in proof.violated_clauses]),
            "rejected_actions": sorted(proof.rejected_actions),
            "feasibility_certificate": {
                "constraint_valid": proof.feasibility_certificate.constraint_graph_valid,
                "geometric_feasibility": proof.feasibility_certificate.geometric_feasibility,
                "topology_preserved": proof.feasibility_certificate.topology_preserved,
                "spectral_stability": round(proof.feasibility_certificate.spectral_stability, 6)
            },
            "ontology_version": proof.ontology_version,
            "nfpa_version": proof.nfpa_version,
            "jurisdiction": proof.jurisdiction
        }
        return hashlib.sha256(json.dumps(derivation_data, sort_keys=True).encode()).hexdigest()


class RegulatoryProofEngine:
    def __init__(self, ontology_version: str = "v1.0", nfpa_version: str = "NFPA72-2022", jurisdiction: str = "default"):
        self.ontology_version = ontology_version
        self.nfpa_version = nfpa_version
        self.jurisdiction = jurisdiction
        self.serializer = CanonicalProofSerializer()

    def construct_proof(self, decision_data: Dict, constraints_state: Dict, feasibility_data: Dict, spectral_data: Dict, cad_trace: List[str], rejected_actions: List[str], vertices: List[Dict]) -> ProofObject:
        if not self._is_decision_complete(decision_data):
            return self._empty_proof(ProofStatus.INCOMPLETE)

        geometry_hash = self.serializer.canonicalize_geometry(vertices)
        decision_hash = self.serializer.canonicalize_decision(decision_data)

        satisfied, violated = self._evaluate_clauses(constraints_state)

        certificate = FeasibilityCertificate(
            constraint_graph_valid=feasibility_data.get("is_valid", False),
            geometric_feasibility=feasibility_data.get("geometric_feasibility", False),
            topology_preserved=feasibility_data.get("topology_preserved", False),
            spectral_stability=spectral_data.get("spectral_radius", 1.0),
            issued_at=datetime.now(timezone.utc).isoformat()
        )

        spectral_trace = {
            "composite_risk_index": spectral_data.get("composite_risk_index", 0.0),
            "spectral_radius": spectral_data.get("spectral_radius", 0.0),
            "risk_level": spectral_data.get("risk_level", "LOW"),
            "failure_probability": spectral_data.get("dimensions", {}).get("failure_probability", 0.0),
            "coverage_loss": spectral_data.get("dimensions", {}).get("coverage_loss", 0.0)
        }

        proof = ProofObject(
            decision_id=decision_data.get("decision_id", "unknown"),
            ontology_version=self.ontology_version,
            nfpa_version=self.nfpa_version,
            jurisdiction=self.jurisdiction,
            input_geometry_hash=geometry_hash,
            decision_semantics_hash=decision_hash,
            satisfied_clauses=satisfied,
            violated_clauses=violated,
            feasibility_certificate=certificate,
            spectral_advisory_trace=spectral_trace,
            rejected_actions=rejected_actions,
            cad_realization_trace=cad_trace,
            deterministic_replay_hash="",
            signature="",
            issued_at=datetime.now(timezone.utc).isoformat(),
            status=ProofStatus.VALID if len(violated) == 0 and certificate.constraint_graph_valid else ProofStatus.FAILED
        )

        proof.deterministic_replay_hash = self.serializer.canonicalize_derivation_graph(proof)
        proof.signature = hashlib.sha256(f"{proof.deterministic_replay_hash}_{proof.issued_at}".encode()).hexdigest()

        return proof

    def verify_proof(self, proof: ProofObject) -> bool:
        if proof.status == ProofStatus.INCOMPLETE:
            return False

        expected_hash = self.serializer.canonicalize_derivation_graph(proof)
        if expected_hash != proof.deterministic_replay_hash:
            return False

        expected_signature = hashlib.sha256(f"{proof.deterministic_replay_hash}_{proof.issued_at}".encode()).hexdigest()
        if expected_signature != proof.signature:
            return False

        if proof.ontology_version != self.ontology_version:
            return False
        if proof.nfpa_version != self.nfpa_version:
            return False
        if proof.jurisdiction != self.jurisdiction:
            return False

        return True

    def replay_decision(self, proof: ProofObject, current_geometry_hash: str, current_decision_hash: str) -> bool:
        if not self.verify_proof(proof):
            return False
        if current_geometry_hash != proof.input_geometry_hash:
            return False
        if current_decision_hash != proof.decision_semantics_hash:
            return False
        return True

    def _evaluate_clauses(self, constraints_state: Dict) -> tuple:
        satisfied = []
        violated = []

        spacing_violation = constraints_state.get("SPACING_VIOLATION", 0.0)
        if spacing_violation > 0.05:
            violated.append(NFPAProofClause(
                clause_id="NFPA72-17.6.3",
                nfpa_reference="NFPA 72 §17.6.3",
                description="Maximum detector spacing shall not exceed 15 meters",
                status=ClauseStatus.VIOLATED,
                evidence={"violation": spacing_violation},
                violation_detail=f"Spacing violation: {spacing_violation:.2f}"
            ))
        else:
            satisfied.append(NFPAProofClause(
                clause_id="NFPA72-17.6.3",
                nfpa_reference="NFPA 72 §17.6.3",
                description="Maximum detector spacing shall not exceed 15 meters",
                status=ClauseStatus.SATISFIED,
                evidence={"violation": 0.0}
            ))

        coverage = constraints_state.get("COVERAGE", 1.0)
        if coverage < 0.90:
            violated.append(NFPAProofClause(
                clause_id="NFPA72-17.6.3.1",
                nfpa_reference="NFPA 72 §17.6.3.1",
                description="Detector coverage shall be at least 90%",
                status=ClauseStatus.VIOLATED,
                evidence={"coverage": coverage},
                violation_detail=f"Coverage {coverage:.1%} below 90%"
            ))
        else:
            satisfied.append(NFPAProofClause(
                clause_id="NFPA72-17.6.3.1",
                nfpa_reference="NFPA 72 §17.6.3.1",
                description="Detector coverage shall be at least 90%",
                status=ClauseStatus.SATISFIED,
                evidence={"coverage": coverage}
            ))

        return satisfied, violated

    def _is_decision_complete(self, decision_data: Dict) -> bool:
        required_fields = ["decision_id", "decision_type", "action"]
        for field in required_fields:
            if field not in decision_data or decision_data[field] is None:
                return False
        return True

    def _empty_proof(self, status: ProofStatus) -> ProofObject:
        return ProofObject(
            decision_id="",
            ontology_version=self.ontology_version,
            nfpa_version=self.nfpa_version,
            jurisdiction=self.jurisdiction,
            input_geometry_hash="",
            decision_semantics_hash="",
            satisfied_clauses=[],
            violated_clauses=[],
            feasibility_certificate=FeasibilityCertificate(False, False, False, 1.0, ""),
            spectral_advisory_trace={},
            rejected_actions=[],
            cad_realization_trace=[],
            deterministic_replay_hash="",
            signature="",
            issued_at=datetime.now(timezone.utc).isoformat(),
            status=status
        )