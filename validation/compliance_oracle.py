"""
Validation Layer - Compliance Oracle (Truth-Verification Kernel)
=============================================================
Rewritten to be a truth-verification kernel, no I/O.

Uses core/truth_model.py as the single source of truth.
Outputs only: PASS, FAIL, REJECTED_HARD, REJECTED_AMBIGUOUS
"""

import hashlib
import json
import os
import sys
from typing import List, Tuple

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NEW IMPORTS - only from core and validation layers
from core.models import Room, Device, Obstruction, Violation
from core.truth_model import evaluate_truth, TruthState, quantize_point
from validation.spatial_normalizer import SpatialNormalizer
from validation.tolerance_model import ToleranceModel
from spatial_field_engine import evaluate_compliance, NFPAConstraintModel


# =============================================================================
# Semantic Checksum (no message)
# =============================================================================

def _semantic_checksum(violations: List[Violation]) -> str:
    """
    Calculate SHA256 using ONLY:
    - rule
    - device_id
    - location (quantized to 0.01m grid)
    - value and threshold with 6 decimal places
    
    Does NOT use message.
    """
    if not violations:
        return hashlib.sha256(b"").hexdigest()
    
    data = ""
    for v in sorted(violations, key=lambda x: (x.rule, x.device_id)):
        # Quantize location
        loc = v.location if v.location else (0, 0)
        qx, qy = quantize_point(loc) if hasattr(loc, 'x') else (0, 0)
        
        data += f"{v.rule}|{v.device_id}|{qx:.2f}|{qy:.2f}|{v.value:.6f}|{v.threshold:.6f}\n"
    
    return hashlib.sha256(data.encode()).hexdigest()


# =============================================================================
# Compliance Oracle (Truth-Verification Kernel)
# =============================================================================

class ComplianceOracle:
    """
    Truth-verification kernel.
    
    Invokes Normalizer, then Engine, then evaluates truth.
    Returns ONLY: PASS, FAIL, REJECTED_HARD, REJECTED_AMBIGUOUS
    
    This Oracle does NOT perform I/O. It accepts direct model inputs.
    """
    
    def __init__(self, tolerance_model: ToleranceModel = None):
        if tolerance_model is None:
            tolerance_model = ToleranceModel()
        self.tolerance_model = tolerance_model
        self.normalizer = SpatialNormalizer(tolerance_model)
        self.model = NFPAConstraintModel()
    
    def verify_truth(
        self,
        room: Room,
        devices: List[Device],
        obstructions: List[Obstruction],
        source_units: str = "meters"
    ) -> dict:
        """
        Full truth-verification path:
        1. Normalize inputs via Normalizer
        2. If rejected -> REJECTED_HARD or REJECTED_AMBIGUOUS
        3. Run evaluate_compliance on normalized inputs
        4. Call evaluate_truth(..., violations, repaired=...) for final state
        5. Generate semantic checksum
        6. Return dict with status, violations, checksum, audit_trail
        
        Returns:
            dict with:
            - status: PASS | FAIL | REJECTED_HARD | REJECTED_AMBIGUOUS
            - violations_count: int
            - violations: list
            - audit_trail: str
            - checksum: str
        """
        from validation.spatial_normalizer import GeometryError, ErrorSeverity
        
        violations: List[Violation] = []
        audit_trail = []
        repaired = False
        
        # Step 1: Normalize geometry
        normalized_room, norm_devices, norm_obs, norm_errors = self.normalizer.normalize(
            room, devices, obstructions, source_units
        )
        
        # Check for critical geometry errors
        critical_errors = [e for e in norm_errors if e.severity == ErrorSeverity.CRITICAL]
        if critical_errors:
            for e in critical_errors:
                audit_trail.append(f"[REJECTED_HARD] {e.entity_id}: {e.message}")
            return {
                "status": "REJECTED_HARD",
                "violations_count": 0,
                "violations": [],
                "audit_trail": "\n".join(audit_trail),
                "checksum": _semantic_checksum([])
            }
        
        # Track repairs
        repaired_errors = [e for e in norm_errors if e.severity == ErrorSeverity.REPAIRED]
        if repaired_errors:
            repaired = True
            for e in repaired_errors:
                audit_trail.append(f"[REPAIRED] {e.entity_id}: {e.message}")
        
        # Log warnings
        warning_errors = [e for e in norm_errors if e.severity == ErrorSeverity.WARNING]
        for e in warning_errors:
            audit_trail.append(f"[{e.severity}] {e.entity_id}: {e.message}")
        
        # Step 2 & 3: Run evaluation engine
        if normalized_room and norm_devices:
            result, engine_violations = evaluate_compliance(
                normalized_room, norm_devices, norm_obs, self.model
            )
            violations = engine_violations
            
            for v in violations:
                audit_trail.append(f"[{v.severity}] {v.rule}: {v.message}")
        
        # Step 4: Evaluate truth using core.truth_model
        truth_state = evaluate_truth(
            normalized_room,
            norm_devices,
            norm_obs,
            violations,
            repaired=repaired
        )
        
        # Map TruthState to output status
        status_map = {
            TruthState.PASS: "PASS",
            TruthState.FAIL: "FAIL",
            TruthState.REJECTED_HARD: "REJECTED_HARD",
            TruthState.REJECTED_AMBIGUOUS: "REJECTED_AMBIGUOUS"
        }
        final_status = status_map.get(truth_state, "FAIL")
        
        # If engine returned REJECTED_AMBIGUOUS via truth evaluation
        if truth_state == TruthState.REJECTED_AMBIGUOUS:
            final_status = "REJECTED_AMBIGUOUS"
            audit_trail.append("[REJECTED_AMBIGUOUS] Ambiguous geometry detected")
        
        # Step 5: Generate semantic checksum
        checksum = _semantic_checksum(violations)
        
        return {
            "status": final_status,
            "violations_count": len(violations),
            "violations": [
                {
                    "rule": v.rule,
                    "device_id": v.device_id,
                    "severity": v.severity,
                    "value": v.value,
                    "threshold": v.threshold,
                    "location": (quantize_point(v.location) if v.location else None)
                }
                for v in violations
            ],
            "audit_trail": "\n".join(audit_trail),
            "checksum": checksum
        }


# =============================================================================
# Snapshot Functions
# =============================================================================

def save_snapshot(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    output_path: str,
    source_units: str = "meters"
) -> None:
    """
    Save verification result to JSON file.
    
    Args:
        room: Room model
        devices: List of devices
        obstructions: List of obstructions
        output_path: Path to output JSON file
        source_units: Source units
    """
    oracle = ComplianceOracle()
    result = oracle.verify_truth(room, devices, obstructions, source_units)
    
    snapshot = {
        "status": result["status"],
        "violations_count": result["violations_count"],
        "violations": result["violations"],
        "checksum": result["checksum"],
        "audit_trail": result["audit_trail"]
    }
    
    with open(output_path, 'w') as f:
        json.dump(snapshot, f, indent=2)


def verify_snapshot(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    snapshot_path: str,
    source_units: str = "meters"
) -> bool:
    """
    Compare current result with saved snapshot.
    Returns True if checksums match.
    
    Args:
        room: Room model
        devices: List of devices
        obstructions: List of obstructions
        snapshot_path: Path to snapshot JSON file
        source_units: Source units
        
    Returns:
        True if checksums match (deterministic)
    """
    if not os.path.exists(snapshot_path):
        return False
    
    # Load snapshot
    with open(snapshot_path, 'r') as f:
        snapshot = json.load(f)
    
    # Evaluate current
    oracle = ComplianceOracle()
    result = oracle.verify_truth(room, devices, obstructions, source_units)
    
    # Compare checksums
    return snapshot["checksum"] == result["checksum"]


def compare_snapshots(snapshot_path_1: str, snapshot_path_2: str) -> dict:
    """
    Compare two JSON snapshot files.
    
    Args:
        snapshot_path_1: Path to first snapshot
        snapshot_path_2: Path to second snapshot
        
    Returns dict with comparison results
    """
    if not os.path.exists(snapshot_path_1) or not os.path.exists(snapshot_path_2):
        return {"error": "One or both snapshots not found"}
    
    with open(snapshot_path_1, 'r') as f:
        snapshot1 = json.load(f)
    
    with open(snapshot_path_2, 'r') as f:
        snapshot2 = json.load(f)
    
    checksums_match = snapshot1["checksum"] == snapshot2["checksum"]
    status_match = snapshot1["status"] == snapshot2["status"]
    violations_match = snapshot1["violations_count"] == snapshot2["violations_count"]
    
    return {
        "checksums_match": checksums_match,
        "status_match": status_match,
        "violations_match": violations_match,
        "regression_detected": not checksums_match,
        "status_1": snapshot1["status"],
        "status_2": snapshot2["status"]
    }


# =============================================================================
# Self-Test: Determinism Verification
# =============================================================================

def _run_determinism_test() -> None:
    """Verify Oracle determinism"""
    from shapely.geometry import Point, Polygon
    
    print("=" * 60)
    print("COMPLIANCE ORACLE DETERMINISM TEST")
    print("=" * 60)
    
    # Create test room - 10m x 10m
    room = Room(
        id="test_room",
        name="Test Room for Determinism",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0,
        ceiling_type="SMOOTH"
    )
    
    # Device in center - distance to wall = 5m (should fail)
    devices = [
        Device(
            id="smoke_center",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(5, 5),
            z_height=2.4,
            coverage_radius=4.6
        ),
        Device(
            id="smoke_corner",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(0.3, 0.3),
            z_height=2.4,
            coverage_radius=4.6
        )
    ]
    
    obstructions = [
        Obstruction(
            id="obs_wall",
            geometry=Polygon([(8, 0), (9, 0), (9, 10), (8, 10), (8, 0)]),
            height=3.0,
            blocks_visibility=True
        )
    ]
    
    oracle = ComplianceOracle()
    
    # Run 1
    result1 = oracle.verify_truth(room, devices, obstructions, "meters")
    checksum1 = result1["checksum"]
    status1 = result1["status"]
    
    # Run 2 (same input)
    result2 = oracle.verify_truth(room, devices, obstructions, "meters")
    checksum2 = result2["checksum"]
    status2 = result2["status"]
    
    # Verify against truth model
    from core.truth_model import evaluate_truth, TruthState
    
    # Create normalized versions for truth evaluation
    from validation.spatial_normalizer import SpatialNormalizer
    normalizer = SpatialNormalizer()
    norm_room, norm_devices, norm_obs, _ = normalizer.normalize(room, devices, obstructions, "meters")
    
    # Get violations from engine
    from spatial_field_engine import evaluate_compliance, NFPAConstraintModel
    model = NFPAConstraintModel()
    _, violations = evaluate_compliance(norm_room, norm_devices, norm_obs, model)
    
    # Evaluate truth
    truth_state = evaluate_truth(norm_room, norm_devices, norm_obs, violations)
    expected_state = {
        TruthState.PASS: "PASS",
        TruthState.FAIL: "FAIL",
        TruthState.REJECTED_HARD: "REJECTED_HARD",
        TruthState.REJECTED_AMBIGUOUS: "REJECTED_AMBIGUOUS"
    }.get(truth_state, "FAIL")
    
    print(f"Run 1 - Status: {status1}, Checksum: {checksum1[:16]}...")
    print(f"Run 2 - Status: {status2}, Checksum: {checksum2[:16]}...")
    print(f"Truth Model - Expected State: {expected_state}")
    print(f"Oracle matches Truth Model: {status1 == expected_state}")
    print(f"Checksums match: {checksum1 == checksum2}")
    print("=" * 60)
    
    if checksum1 == checksum2 and status1 == expected_state:
        print("✓ DETERMINISM VERIFIED")
    else:
        print("✗ DETERMINISM FAILED")
    print("=" * 60)


if __name__ == "__main__":
    _run_determinism_test()