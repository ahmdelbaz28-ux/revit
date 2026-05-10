"""
Compliance Oracle (Truth-Verification Kernel)
=============================================
Stateless pipeline that:
1. Normalizes geometry via SpatialNormalizer
2. Runs spatial_field_engine.evaluate_compliance to get raw violations
3. Passes violations to core.truth_model.evaluate_truth for final state
4. Computes semantic checksum (NO message field)
5. Returns final state (PASS/FAIL/REJECTED_HARD/REJECTED_AMBIGUOUS)

This Oracle contains NO business logic. It is a pure transformer.

=========================
HARD ENFORCEMENT GATE CONTRACT
=========================
Only ComplianceOracle.verify_truth() may call TruthModel.
No other function in the system is allowed to import or call evaluate_truth.
This Gate is the sole decision boundary.
"""

import os
import sys
# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List
from core.models import Room, Device, Obstruction, Violation
from core.truth_model import quantize_point, _is_geometry_valid, _is_ambiguous
from core.truth_deriver import derive_truth, TruthViolation, compare_truths, NFPAConstraintModel as TruthNFPAConstraintModel
from core.contract import validate_violation
from validation.spatial_normalizer import SpatialNormalizer
from spatial_field_engine import evaluate_compliance, NFPAConstraintModel
import hashlib


# =============================================================================
# Private Truth State (inside Oracle only)
# =============================================================================

class _TruthState(Enum):
    """The only permitted truth states - INSIDE Oracle only"""
    PASS = "PASS"                    # Valid geometry, no violations
    FAIL = "FAIL"                   # Valid geometry, measurable violations
    REJECTED_HARD = "REJECTED_HARD"  # Invalid geometry (cannot process)
    REJECTED_AMBIGUOUS = "REJECTED_AMBIGUOUS"  # Ambiguous case (needs review)


# =============================================================================
# Decision Record (Immutable)
# =============================================================================

@dataclass(frozen=True)
class DecisionRecord:
    """Immutable decision record after issuance."""
    timestamp: str
    status: str  # PASS, FAIL, REJECTED_HARD, REJECTED_AMBIGUOUS
    checksum: str
    violations_count: int
    input_hash: str  # Hash of inputs to prevent recalculation


# =============================================================================
# Input Hash Computation (Internal)
# =============================================================================

def _compute_input_hash(room: Room, devices: List[Device], obstructions: List[Obstruction]) -> str:
    """Compute SHA256 from element IDs and coordinates to prevent input replay."""
    data = room.id
    for d in devices:
        data += f"|{d.id}|{d.position.x}|{d.position.y}"
    for o in obstructions:
        bounds = o.geometry.bounds
        data += f"|{o.id}|{bounds[0]:.2f}|{bounds[1]:.2f}"
    return hashlib.sha256(data.encode()).hexdigest()


# =============================================================================
# Semantic Checksum (Internal)
# =============================================================================

def _semantic_checksum(violations: List[Violation]) -> str:
    """SHA256 over (rule, device_id, quantized location, value, threshold)."""
    if not violations:
        return hashlib.sha256(b"").hexdigest()
    
    data = ""
    for v in sorted(violations, key=lambda x: (x.rule, x.device_id)):
        qx, qy = (0.0, 0.0)
        if v.location is not None:
            qx, qy = quantize_point(v.location) if hasattr(v.location, 'x') else (0.0, 0.0)
        data += f"{v.rule}|{v.device_id}|{qx:.2f}|{qy:.2f}|{v.value:.6f}|{v.threshold:.6f}\n"
    
    return hashlib.sha256(data.encode()).hexdigest()


# =============================================================================
# Compliance Oracle
# =============================================================================

class ComplianceOracle:
    def __init__(self):
        self.normalizer = SpatialNormalizer()
        self.model = NFPAConstraintModel()
    
    def __evaluate_constraints(self, room, devices, obstructions, violations, repaired=False):
        """
        Internal constraint evaluator. Replaces truth_model.evaluate_truth().
        Does NOT return TruthState. Returns raw evaluation data only.
        
        Judgment rules (ordered by priority):
        1. If geometry invalid or devices outside room → REJECTED_HARD
        2. If there's ambiguity → REJECTED_AMBIGUOUS
        3. If geometry valid and no violations → PASS
        4. If geometry valid and measurable violations exist → FAIL
        """
        from core.truth_model import _is_geometry_valid as is_valid, _is_ambiguous as is_amb
        
        # Rule 1: Check for invalid geometry or devices outside room
        if not is_valid(room):
            return _TruthState.REJECTED_HARD
        
        for device in devices:
            if not room.geometry.covers(device.position):
                return _TruthState.REJECTED_HARD
        
        # Check obstructions are inside room
        for obs in obstructions:
            if not room.geometry.contains(obs.geometry):
                return _TruthState.REJECTED_HARD
        
        # Rule 2: Check for ambiguity
        if is_amb(room, devices, obstructions):
            return _TruthState.REJECTED_AMBIGUOUS
        
        # Rule 3 & 4: Judge based on violations
        if violations:
            return _TruthState.FAIL
        
        return _TruthState.PASS
    
    def verify_truth(self, room: Room, devices: List[Device],
                   obstructions: List[Obstruction], source_units: str = "meters") -> dict:
        """
        Stateless truth verification pipeline.
        
        Returns:
            dict with: status, violations_count, violations, audit_trail, checksum
        """
        # Step 1: Normalize
        norm_room, norm_devices, norm_obs, errors = self.normalizer.normalize(
            room, devices, obstructions, source_units
        )
        
        # If critical geometry errors, immediately REJECTED_HARD
        from validation.spatial_normalizer import ErrorSeverity
        if any(e.severity == ErrorSeverity.CRITICAL for e in errors):
            return {
                "status": "REJECTED_HARD",
                "violations_count": 0,
                "violations": [],
                "audit_trail": "Critical geometry error(s) found.",
                "checksum": _semantic_checksum([])
            }

        # Initialize audit trail for cross-verification
        audit_trail = []

        # Step 2: Engine raw output
        _, raw_violations = evaluate_compliance(
            norm_room, norm_devices, norm_obs, self.model
        )

        # Contract enforcement: strip forbidden fields from violations
        # The engine may use 'message' internally, but final output must not include it
        sanitized_violations = []
        for v in raw_violations:
            # Create clean Violation without forbidden fields
            sanitized = Violation(
                rule=v.rule,
                device_id=v.device_id,
                severity=v.severity,
                value=v.value,
                threshold=v.threshold,
                location=v.location
            )
            validate_violation(sanitized)
            sanitized_violations.append(sanitized)

        # Step 3a: Cross-verify with independent truth deriver
        try:
            truth_model_inst = TruthNFPAConstraintModel()
            truth_violations = derive_truth(
                norm_room, norm_devices, norm_obs, truth_model_inst
            )
            comparison = compare_truths(sanitized_violations, truth_violations)
            
            if comparison['summary'] != "CONSISTENT":
                audit_trail.append(
                    f"[DIVERGENCE] Truth deriver mismatch: "
                    f"matched={comparison['matched']}, "
                    f"missing={comparison['missing_in_engine']}, "
                    f"extra={comparison['extra_in_engine']}"
                )
        except Exception as e:
            audit_trail.append(f"[CROSS-VERIFY ERROR] {str(e)}")

        # Step 3: Issue decision (internal constraint evaluation)
        truth_state = self._ComplianceOracle__evaluate_constraints(
            norm_room, norm_devices, norm_obs, sanitized_violations
        )

        # Step 4: Deterministic checksum
        checksum = _semantic_checksum(sanitized_violations)

        # Map TruthState to output string
        status = truth_state.value  # PASS, FAIL, REJECTED_HARD, REJECTED_AMBIGUOUS

        # Create immutable decision record (timestamp for logging, but decision_id is deterministic)
        decision = DecisionRecord(
            timestamp=datetime.now().isoformat(),
            status=status,
            checksum=checksum,
            violations_count=len(sanitized_violations),
            input_hash=_compute_input_hash(norm_room, norm_devices, norm_obs)
        )

        return {
            "status": status,
            "violations_count": len(sanitized_violations),
            "violations": [
                {
                    "rule": v.rule,
                    "device_id": v.device_id,
                    "severity": v.severity,
                    "value": v.value,
                    "threshold": v.threshold,
                    "location": (
                        quantize_point(v.location) if v.location else None
                    )
                }
                for v in sanitized_violations
            ],
            "audit_trail": "\n".join(audit_trail),
            "checksum": checksum,
            "decision_id": hashlib.sha256(
                f"{status}{checksum}{decision.input_hash}".encode()
            ).hexdigest()[:16],
            "input_hash": decision.input_hash
        }


# =============================================================================
# Snapshot functions
# =============================================================================

def save_snapshot(room: Room, devices: List[Device], obstructions: List[Obstruction],
               output_path: str, source_units: str = "meters"):
    """Save verification result to JSON file."""
    import json
    oracle = ComplianceOracle()
    result = oracle.verify_truth(room, devices, obstructions, source_units)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)


def verify_snapshot(room: Room, devices: List[Device], obstructions: List[Obstruction],
                  snapshot_path: str, source_units: str = "meters") -> bool:
    """Compare current result with saved snapshot."""
    import json, os
    if not os.path.exists(snapshot_path):
        return False
    with open(snapshot_path, 'r') as f:
        snapshot = json.load(f)
    oracle = ComplianceOracle()
    result = oracle.verify_truth(room, devices, obstructions, source_units)
    return snapshot["checksum"] == result["checksum"]


def compare_snapshots(path1: str, path2: str) -> dict:
    """Compare two JSON snapshot files."""
    import json, os
    if not os.path.exists(path1) or not os.path.exists(path2):
        return {"error": "Snapshot file missing"}
    with open(path1) as f1, open(path2) as f2:
        s1, s2 = json.load(f1), json.load(f2)
    return {
        "checksums_match": s1["checksum"] == s2["checksum"],
        "status_match": s1["status"] == s2["status"],
        "violations_match": s1["violations_count"] == s2["violations_count"],
        "regression_detected": s1["checksum"] != s2["checksum"]
    }


# =============================================================================
# Self-test
# =============================================================================

def _run_self_test():
    from shapely.geometry import Point, Polygon
    print("=" * 60)
    print("TRUTH-DRIVEN ORACLE SELF-TEST")
    print("=" * 60)
    
    room = Room(
        id="r", name="Test",
        geometry=Polygon([(0,0),(10,0),(10,10),(0,10),(0,0)]),
        ceiling_height=3.0
    )
    devices = [
        Device(id="d1", device_type="SMOKE_PHOTOELECTRIC", position=Point(5,5))
    ]
    obstructions = []
    
    oracle = ComplianceOracle()
    res1 = oracle.verify_truth(room, devices, obstructions)
    res2 = oracle.verify_truth(room, devices, obstructions)
    
    print(f"Run1: {res1['status']} | {res1['checksum'][:16]}... | decision_id: {res1.get('decision_id', 'N/A')}")
    print(f"Run2: {res2['status']} | {res2['checksum'][:16]}... | decision_id: {res2.get('decision_id', 'N/A')}")
    print(f"Checksums match: {res1['checksum'] == res2['checksum']}")
    print(f"Decision IDs match: {res1.get('decision_id') == res2.get('decision_id')}")
    print(f"Input hashes match: {res1.get('input_hash') == res2.get('input_hash')}")
    print("=" * 60)
    
    if res1['checksum'] == res2['checksum'] and res1.get('decision_id') == res2.get('decision_id'):
        print("✓ DETERMINISM VERIFIED")
    else:
        print("✗ DETERMINISM FAILED")
    print("=" * 60)


if __name__ == "__main__":
    _run_self_test()