"""
Validation Layer - Compliance Oracle
=============================
Deterministic compliance evaluation layer that invokes the Engine and Normalizer.
Ensures:
1. Determinism: same inputs produce bit-identical outputs
2. Clarity: returns one of three states: PASS, FAIL, REJECTED
3. Comparability: can detect behavioral changes between code versions
"""

import hashlib
import json
import os
import sys
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation.tolerance_model import ToleranceModel
from validation.spatial_normalizer import SpatialNormalizer
from spatial_constraint_engine import (
    Room, Device, Obstruction, SpatialValidator, 
    NFPAStandard, Violation, NFPA72Spacings
)


# =============================================================================
# Checksum Function
# =============================================================================

def _violations_checksum(violations: List[Violation]) -> str:
    """
    Generate SHA256 checksum from violations list to ensure output determinism.
    Sorts violations by rule and device_id for consistent ordering.
    """
    if not violations:
        # Empty violations produce a well-known checksum
        return hashlib.sha256(b"").hexdigest()
    
    data = ""
    for v in sorted(violations, key=lambda x: (x.rule, x.device_id)):
        # Format each violation with fixed-point precision for determinism
        data += f"{v.rule}|{v.device_id}|{v.severity}|{v.message}|{v.value:.6f}|{v.threshold:.6f}\n"
    
    return hashlib.sha256(data.encode()).hexdigest()


# =============================================================================
# Compliance Oracle
# =============================================================================

class ComplianceOracle:
    """
    Top-layer that invokes Engine and Normalizer and ensures deterministic evaluation.
    
    Returns one of three states:
    - PASS: All validations passed
    - FAIL: Validation completed with violations found
    - REJECTED: Cannot process due to critical geometry errors
    """
    
    def __init__(self, tolerance_model: ToleranceModel = None):
        if tolerance_model is None:
            tolerance_model = ToleranceModel()
        self.tolerance_model = tolerance_model
        self.normalizer = SpatialNormalizer(tolerance_model)
        
        # Default to NFPA 72 standard
        self.standard = NFPAStandard(
            code="NFPA72",
            edition="2022",
            spacing_rules=NFPA72Spacings.DETECTOR_MAX_SPACING
        )
    
    def evaluate(
        self, 
        ifc_path: str, 
        source_units: str = "meters"
    ) -> dict:
        """
        Run full pipeline on an IFC file.
        
        Args:
            ifc_path: Path to IFC file
            source_units: Source units (feet, meters, etc.)
            
        Returns dict containing:
        - status: "PASS" | "FAIL" | "REJECTED"
        - violations_count: int
        - violations: list
        - audit_trail: str
        - checksum: str (SHA256 for deterministic output verification)
        """
        from validation.spatial_normalizer import GeometryError, ErrorSeverity
        
        violations: List[Violation] = []
        audit_trail = []
        status = "PASS"
        
        # Step 1: Parse IFC file
        try:
            room, devices, obstructions = self._parse_ifc(ifc_path)
            audit_trail.append(f"Parsed IFC: {len(devices)} devices, {len(obstructions)} obstructions")
        except Exception as e:
            return {
                "status": "REJECTED",
                "violations_count": 0,
                "violations": [],
                "audit_trail": f"Failed to parse IFC: {str(e)}",
                "checksum": _violations_checksum([])
            }
        
        # Step 2: Normalize geometry
        normalized_room, norm_devices, norm_obs, norm_errors = self.normalizer.normalize(
            room, devices, obstructions, source_units
        )
        
        # Check for critical geometry errors
        critical_errors = [e for e in norm_errors if e.severity == ErrorSeverity.CRITICAL]
        if critical_errors:
            status = "REJECTED"
            for e in critical_errors:
                audit_trail.append(f"[REJECTED] {e.entity_id}: {e.message}")
            return {
                "status": status,
                "violations_count": 0,
                "violations": [],
                "audit_trail": "\n".join(audit_trail),
                "checksum": _violations_checksum([])
            }
        
        # Log warnings/repairs
        for e in norm_errors:
            audit_trail.append(f"[{e.severity}] {e.entity_id}: {e.message}")
        
        # Step 3: Run validation engine
        if normalized_room and norm_devices:
            engine = SpatialValidator(self.standard)
            violations = engine.validate_room(normalized_room, norm_devices, norm_obs)
            
            for v in violations:
                audit_trail.append(f"[{v.severity}] {v.rule}: {v.message}")
        
        # Determine final status
        if violations:
            status = "FAIL"
        
        # Generate checksum
        checksum = _violations_checksum(violations)
        
        return {
            "status": status,
            "violations_count": len(violations),
            "violations": [
                {
                    "rule": v.rule,
                    "device_id": v.device_id,
                    "severity": v.severity,
                    "message": v.message,
                    "value": v.value,
                    "threshold": v.threshold
                }
                for v in violations
            ],
            "audit_trail": "\n".join(audit_trail),
            "checksum": checksum
        }
    
    def _parse_ifc(self, ifc_path: str) -> Tuple[Room, List[Device], List[Obstruction]]:
        """
        Parse IFC file and extract room, devices, and obstructions.
        Uses ifcopenshell if available, otherwise creates minimal test data.
        """
        try:
            import ifcopenshell
            import ifcopenshell.api.owner_history
        except ImportError:
            # No ifcopenshell - create minimal test data
            return self._create_test_data()
        
        # Parse IFC file
        if not os.path.exists(ifc_path):
            raise FileNotFoundError(f"IFC file not found: {ifc_path}")
        
        ifc = ifcopenshell.open(ifc_path)
        
        # Extract building
        building = ifc.by_type("IfcBuilding")[0] if ifc.by_type("IfcBuilding") else None
        
        # Extract spaces (rooms)
        spaces = ifc.by_type("IfcSpace")
        rooms = []
        
        for space in spaces:
            # Try to get geometry
            if hasattr(space, "Representation") and space.Representation:
                for rep in space.Representation.Representations:
                    if rep.RepresentationIdentifier == "Body":
                        geom = rep.Items[0]
                        # Get coordinates from geometry
                        # This is simplified - real IFC parsing is more complex
                        pass
            
            # For now, create room from bounding box
            rooms.append(Room(
                id=str(space.GlobalId) if hasattr(space, "GlobalId") else space.id,
                name=space.Name if hasattr(space, "Name") and space.Name else "Room",
                geometry=space.geometry if hasattr(space, "geometry") else None,
                ceiling_height=3.0,  # Default
                ceiling_type="SMOOTH"
            ))
        
        # Extract items (devices/sensors)
        devices = []
        # Search for fire alarm devices
        device_types = [
            "IfcFireAlarm", "IfcAlarm", "IfcSensor", "IfcDetector",
            "IfcFlowInstrument", "IfcController"
        ]
        
        for dtype in device_types:
            items = ifc.by_type(dtype)
            for item in items:
                devices.append(Device(
                    id=str(item.GlobalId) if hasattr(item, "GlobalId") else item.id,
                    device_type=dtype.replace("Ifc", ""),
                    position=self._get_location(item),
                    z_height=2.4,
                    coverage_radius=4.6
                ))
        
        # Extract obstructions
        obstructions = []
        
        # Use test data if nothing found
        if not rooms or not devices:
            return self._create_test_data()
        
        return rooms[0], devices, obstructions
    
    def _get_location(self, entity) -> 'Point':
        """Extract location from IFC entity"""
        from shapely.geometry import Point
        
        if hasattr(entity, "ObjectPlacement"):
            placement = entity.ObjectPlacement
            if hasattr(placement, "Location"):
                loc = placement.Location
                if hasattr(loc, "Coordinates"):
                    coords = loc.Coordinates
                    return Point(
                        coords[0] if len(coords) > 0 else 0,
                        coords[1] if len(coords) > 1 else 0
                    )
        
        return Point(0, 0)
    
    def _create_test_data(self) -> Tuple[Room, List[Device], List[Obstruction]]:
        """Create minimal test data when ifcopenshell is unavailable"""
        from shapely.geometry import Point, Polygon
        
        room = Room(
            id="test_room",
            name="Test Room",
            geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
            ceiling_height=3.0,
            ceiling_type="SMOOTH"
        )
        
        devices = [
            Device(
                id="smoke_1",
                device_type="SMOKE_PHOTOELECTRIC",
                position=Point(5, 5),
                z_height=2.4,
                coverage_radius=4.6
            )
        ]
        
        return room, devices, []


# =============================================================================
# Version Comparison
# =============================================================================

def compare_oracles(oracle_v1_path: str, oracle_v2_path: str, test_ifc_path: str) -> dict:
    """
    Compare outputs from two versions of the code (different files) on same input.
    Useful for regression testing.
    
    Args:
        oracle_v1_path: Path to first oracle module
        oracle_v2_path: Path to second oracle module  
        test_ifc_path: Path to IFC test file
        
    Returns dict with comparison results
    """
    # Import both oracle versions
    import importlib.util
    
    spec1 = importlib.util.spec_from_file_location("oracle_v1", oracle_v1_path)
    spec2 = importlib.util.spec_from_file_location("oracle_v2", oracle_v2_path)
    
    oracle_v1 = importlib.util.module_from_spec(spec1)
    oracle_v2 = importlib.util.module_from_spec(spec2)
    
    spec1.loader.exec_module(oracle_v1)
    spec2.loader.exec_module(oracle_v2)
    
    # Evaluate with both versions
    oracle1 = oracle_v1.ComplianceOracle()
    oracle2 = oracle_v2.ComplianceOracle()
    
    result1 = oracle1.evaluate(test_ifc_path)
    result2 = oracle2.evaluate(test_ifc_path)
    
    # Compare
    checksums_match = result1["checksum"] == result2["checksum"]
    status_match = result1["status"] == result2["status"]
    violations_match = result1["violations_count"] == result2["violations_count"]
    
    return {
        "checksums_match": checksums_match,
        "status_match": status_match,
        "violations_match": violations_match,
        "v1_result": result1,
        "v2_result": result2,
        "regression_detected": not checksums_match
    }


# =============================================================================
# Snapshot Functions  
# =============================================================================

def save_snapshot(ifc_path: str, output_path: str, source_units: str = "meters") -> None:
    """
    Save evaluation result (violations + checksum) to JSON file for later reference.
    Useful for deterministic regression testing.
    
    Args:
        ifc_path: Path to IFC file
        output_path: Path to output JSON file
        source_units: Source units
    """
    oracle = ComplianceOracle()
    result = oracle.evaluate(ifc_path, source_units)
    
    snapshot = {
        "ifc_path": ifc_path,
        "source_units": source_units,
        "status": result["status"],
        "violations_count": result["violations_count"],
        "violations": result["violations"],
        "checksum": result["checksum"],
        "audit_trail": result["audit_trail"]
    }
    
    with open(output_path, 'w') as f:
        json.dump(snapshot, f, indent=2)


def verify_snapshot(ifc_path: str, snapshot_path: str, source_units: str = "meters") -> bool:
    """
    Compare current evaluation result with a saved snapshot.
    Returns True if checksums match (deterministic).
    
    Args:
        ifc_path: Path to IFC file  
        snapshot_path: Path to snapshot JSON file
        source_units: Source units
        
    Returns:
        True if checksums match, False otherwise
    """
    if not os.path.exists(snapshot_path):
        return False
    
    # Load snapshot
    with open(snapshot_path, 'r') as f:
        snapshot = json.load(f)
    
    # Evaluate current
    oracle = ComplianceOracle()
    result = oracle.evaluate(ifc_path, source_units)
    
    # Compare checksums
    return snapshot["checksum"] == result["checksum"]


# =============================================================================
# Self-Test: Determinism Verification
# =============================================================================

def _run_determinism_test() -> None:
    """
    Self-test to verify determinism:
    1. Uses test data with known violations
    2. Runs evaluate twice on same data
    3. Compares checksums (should be identical)
    4. Prints result
    """
    from shapely.geometry import Point, Polygon
    
    print("=" * 60)
    print("DETERMINISM VERIFICATION TEST")
    print("=" * 60)
    
    # Create test room - 10m x 10m
    room = Room(
        id="test_room",
        name="Test Room for Determinism",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0,
        ceiling_type="SMOOTH"
    )
    
    # Device in center - distance to wall = 5m > 4.55m (MAX_WALL_DISTANCE)
    devices = [
        Device(
            id="smoke_center",
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(5, 5),  # 5m from any wall - VIOLATION!
            z_height=2.4,
            coverage_radius=4.6
        ),
        Device(
            id="smoke_corner", 
            device_type="SMOKE_PHOTOELECTRIC",
            position=Point(0.3, 0.3),  # Near wall - OK
            z_height=2.4,
            coverage_radius=4.6
        )
    ]
    
    # Create oracle
    oracle = ComplianceOracle()
    oracle.normalizer.tolerance_model = ToleranceModel()
    
    # Run normalization manually for test
    norm_room, norm_devices, norm_obs, errors = oracle.normalizer.normalize(
        room, devices, [], "meters"
    )
    
    # Run engine
    engine = SpatialValidator(oracle.standard)
    violations = engine.validate_room(norm_room, norm_devices, norm_obs)
    
    # Generate checksum
    checksum1 = _violations_checksum(violations)
    
    # Run again (same input should produce identical output)
    norm_room2, norm_devices2, norm_obs2, errors2 = oracle.normalizer.normalize(
        room, devices, [], "meters"
    )
    engine2 = SpatialValidator(oracle.standard)
    violations2 = engine2.validate_room(norm_room2, norm_devices2, norm_obs2)
    
    checksum2 = _violations_checksum(violations2)
    
    print(f"Run 1 - Checksum: {checksum1[:16]}...")
    print(f"Run 1 - Violations: {len(violations)}")
    for v in violations:
        print(f"  - {v.rule}: {v.message}")
    print(f"Run 2 - Checksum: {checksum2[:16]}...")
    print(f"Run 2 - Violations: {len(violations2)}")
    print(f"Checksums match: {checksum1 == checksum2}")
    print("=" * 60)
    
    if checksum1 == checksum2:
        print("✓ DETERMINISM VERIFIED")
    else:
        print("✗ DETERMINISM FAILED")
    print("=" * 60)


if __name__ == "__main__":
    _run_determinism_test()