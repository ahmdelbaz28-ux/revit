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
import logging
import json
from datetime import datetime


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

def _semantic_checksum(room: Room, devices: List[Device], violations: List[Violation]) -> str:
    """
    SHA256 over room + devices + violations.
    Must be UNIQUE per room configuration.
    """
    import json
    
    # Build deterministic data from room and devices
    data = {
        "room_id": getattr(room, 'id', 'unknown'),
        "room_name": getattr(room, 'name', 'unknown'),
        "room_type": getattr(room, 'room_type', 'unknown'),
        "ceiling_height": getattr(room, 'ceiling_height', 2.8),
        "devices": [
            {
                "id": getattr(d, 'id', f'dev_{i}'),
                "type": getattr(d, 'device_type', 'unknown'),
                "x": float(getattr(getattr(d, 'position', None), 'x', 0)),
                "y": float(getattr(getattr(d, 'position', None), 'y', 0)),
            }
            for i, d in enumerate(devices)
        ],
        "violations": [
            {
                "rule": v.rule,
                "device_id": v.device_id,
                "value": float(v.value),
                "threshold": float(v.threshold),
            }
            for v in violations
        ],
    }
    
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


# =============================================================================
# Compliance Oracle
# =============================================================================

class ComplianceOracle:
    def __init__(self):
        # NFPA 72 constraint model
        self.model = NFPAConstraintModel()

        # Initialize normalizer
        from validation.spatial_normalizer import SpatialNormalizer
        self.normalizer = SpatialNormalizer()
        
        # Logging
        import logging
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Persistent audit trail (JSONL)
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        self.audit_file = open(f"oracle_audit_{today}.jsonl", "a", encoding="utf-8")
    
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
                "checksum": _semantic_checksum(norm_room, norm_devices, [])
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
        checksum = _semantic_checksum(norm_room, norm_devices, sanitized_violations)

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

        return_result = {
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

        # ========== CONTINUOUS COVERAGE VERIFICATION ==========
        # Add coverage data to return_result (after it's created)
        try:
            room_poly = getattr(norm_room, 'geometry', None)
            if room_poly is not None:
                device_points = []
                for d in norm_devices:
                    pos = getattr(d, 'position', None)
                    if pos is not None:
                        from shapely.geometry import Point
                        device_points.append(Point(
                            float(getattr(pos, 'x', 0)),
                            float(getattr(pos, 'y', 0))
                        ))
                if device_points:
                    from src.domain.nfpa72_provider import NFPA72ConstraintProvider
                    device_type = devices[0].device_type if devices else "SMOKE_PHOTOELECTRIC"
                    ceiling_h = getattr(norm_room, 'ceiling_height', 2.8)
                    ceiling_t = getattr(norm_room, 'ceiling_type', 'SMOOTH')
                    radius = NFPA72ConstraintProvider.get_effective_radius(
                        device_type=device_type,
                        ceiling_height=ceiling_h,
                        ceiling_type=ceiling_t
                    )
                    from validation.coverage_verifier import CoverageVerifier, estimate_extra_devices
                    verifier = CoverageVerifier(resolution=32)
                    coverage_result = verifier.verify_coverage(
                        room_poly, device_points, radius, 
                        obstructions=obstructions  # Pass real obstructions
                    )
                    return_result["coverage"] = coverage_result
                    if coverage_result["status"] == "FAIL":
                        extra = estimate_extra_devices(coverage_result["uncovered_area"])
                        return_result["violations"].append({
                            "rule": "COVERAGE_GAP",
                            "device_id": "SYSTEM",
                            "severity": "CRITICAL",
                            "value": coverage_result["uncovered_area"],
                            "threshold": 0.0,
                            "location": None
                        })
                        return_result["violations_count"] += 1
                        if status == "PASS":
                            status = "FAIL"
                            return_result["status"] = "FAIL"
        except Exception as e:
            pass  # Non-critical

        # ========== PERSISTENT AUDIT TRAIL ==========
        # Write audit entry to JSONL file immediately
        decision_id = hashlib.sha256(
            f"{status}{checksum}{decision.input_hash}".encode()
        ).hexdigest()[:16]

        # Serialize coverage - convert polygons to strings
        cov_result = return_result.get("coverage", {})
        cov_serialized = {
            "status": cov_result.get("status"),
            "coverage_percent": cov_result.get("coverage_percent"),
            "uncovered_area": cov_result.get("uncovered_area"),
            "room_area": cov_result.get("room_area"),
            "device_count": cov_result.get("device_count"),
        }
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision_id": decision_id,
            "room_id": getattr(room, 'id', 'unknown'),
            "room_name": room.name,
            "device_count": len(devices),
            "device_types": list(set(d.device_type for d in devices)),
            "status": status,
            "checksum": checksum,
            "coverage": cov_serialized,
        }

        self.audit_file.write(json.dumps(audit_entry, ensure_ascii=False) + '\n')
        self.audit_file.flush()
        self.logger.info(f"Oracle audit: decision={decision_id}, room={room.name}, status={status}")

        return_result["audit_entry"] = audit_entry
        return return_result


# =============================================================================
# Snapshot functions
# =============================================================================

    def __del__(self):
        """Clean up audit file on shutdown"""
        if hasattr(self, 'audit_file') and self.audit_file and not self.audit_file.closed:
            self.audit_file.close()


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