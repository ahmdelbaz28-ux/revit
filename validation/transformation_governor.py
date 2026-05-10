"""
Validation Layer - Transformation Governor
================================
Tracks and classifies all geometric transformations with full audit trail.

Principle: "Every modification must be traceable, reversible, and justified."
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from shapely.geometry import Point, Polygon
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spatial_constraint_engine import Room, Device, Obstruction


# =============================================================================
# Error Classification
# =============================================================================

class GeometryErrorClass(Enum):
    """Classification of geometric errors by severity"""
    HARD_INVALID = "HARD_INVALID"       # Must reject
    REPAIRABLE = "REPAIRABLE"           # Can auto-repair
    AMBIGUOUS = "AMBIGUOUS"             # Needs human review


# =============================================================================
# Transformation Record
# =============================================================================

@dataclass
class TransformationRecord:
    """Represents a single geometric modification"""
    operation: str                     # e.g. "unit_conversion", "buffer_repair"
    entity_id: str                     # room.id, device.id, etc.
    before: Optional[str]            # description or wkt preview
    after: Optional[str]             # description or wkt preview
    reason: str                    # human explanation
    error_class: GeometryErrorClass  # severity classification
    confidence: float = 1.0        # 0.0 to 1.0


# =============================================================================
# Transformation Governor
# =============================================================================

class TransformationGovernor:
    """
    Enforces governance over all geometric transformations.
    
    Responsibilities:
    - Records every operation with full audit trail
    - Classifies errors by severity
    - Prevents silent repairs
    - Provides audit trail for compliance review
    """
    
    def __init__(self):
        self.log: List[TransformationRecord] = []
        self._operations_count = {
            "unit_conversion": 0,
            "buffer_repair": 0,
            "origin_normalization": 0,
            "degenerate_check": 0,
            "spatial_validation": 0,
        }
    
    def record(self, rec: TransformationRecord):
        """Record a transformation"""
        self.log.append(rec)
        if rec.operation in self._operations_count:
            self._operations_count[rec.operation] += 1
    
    def get_records_by_class(self, err_class: GeometryErrorClass) -> List[TransformationRecord]:
        """Get all records of a specific error class"""
        return [r for r in self.log if r.error_class == err_class]
    
    def get_hard_errors(self) -> List[TransformationRecord]:
        """Get all HARD_INVALID errors - must reject"""
        return self.get_records_by_class(GeometryErrorClass.HARD_INVALID)
    
    def get_repairs(self) -> List[TransformationRecord]:
        """Get all REPAIRABLE operations - auto-repaired"""
        return self.get_records_by_class(GeometryErrorClass.REPAIRABLE)
    
    def get_ambiguities(self) -> List[TransformationRecord]:
        """Get all AMBIGUOUS cases - needs human review"""
        return self.get_records_by_class(GeometryErrorClass.AMBIGUOUS)
    
    def audit_trail(self) -> str:
        """Return human-readable audit summary"""
        lines = ["=" * 50]
        lines.append("GEOMETRY TRANSFORMATION AUDIT TRAIL")
        lines.append("=" * 50)
        
        if not self.log:
            lines.append("No transformations recorded.")
            return "\n".join(lines)
        
        # Summary by class
        hard_count = len(self.get_hard_errors())
        repair_count = len(self.get_repairs())
        ambiguous_count = len(self.get_ambiguities())
        
        lines.append(f"\nSummary:")
        lines.append(f"  HARD_INVALID (must reject): {hard_count}")
        lines.append(f"  REPAIRABLE (auto-repaired): {repair_count}")
        lines.append(f"  AMBIGUOUS (needs review): {ambiguous_count}")
        
        lines.append(f"\nDetailed Operations ({len(self.log)} total):")
        lines.append("-" * 50)
        
        for i, r in enumerate(self.log, 1):
            class_marker = {
                GeometryErrorClass.HARD_INVALID: "❌",
                GeometryErrorClass.REPAIRABLE: "🔧",
                GeometryErrorClass.AMBIGUOUS: "⚠️",
            }.get(r.error_class, "?")
            
            lines.append(f"{i}. {class_marker} [{r.error_class.value}] {r.operation}")
            lines.append(f"   Entity: {r.entity_id}")
            lines.append(f"   Reason: {r.reason}")
            if r.before and r.after:
                lines.append(f"   Before: {r.before[:40]}...")
                lines.append(f"   After:  {r.after[:40]}...")
            lines.append(f"   Confidence: {r.confidence:.0%}")
            lines.append("")
        
        return "\n".join(lines)
    
    def has_critical_preventing_compliance(self) -> bool:
        """True if there are HARD_INVALID errors that block compliance evaluation"""
        return len(self.get_hard_errors()) > 0
    
    def get_summary(self) -> dict:
        """Get summary statistics"""
        return {
            "total_operations": len(self.log),
            "hard_invalid": len(self.get_hard_errors()),
            "repairable": len(self.get_repairs()),
            "ambiguous": len(self.get_ambiguities()),
            "can_proceed": not self.has_critical_preventing_compliance(),
        }


# =============================================================================
# Integrated Normalization Pipeline
# =============================================================================

def governed_normalization_pipeline(
    room: Room,
    devices: List[Device],
    obstructions: List[Obstruction],
    source_units: str = "feet"
) -> Tuple[Room, List[Device], List[Obstruction], TransformationGovernor]:
    """
    Full governed normalization pipeline.
    
    Args:
        room: Room with original coordinates
        devices: List of devices
        obstructions: List of obstructions  
        source_units: Source units (feet, meters, etc.)
        
    Returns:
        Tuple of (normalized_room, normalized_devices, normalized_obstructions, governor)
    """
    governor = TransformationGovernor()
    
    # ==========================================================================
    # Step 1: Unit Coercion
    # ==========================================================================
    from validation.unit_coercion import coerce_units
    
    room_m, devices_m, obst_m, tol = coerce_units(
        room, devices, obstructions, source_units
    )
    
    if source_units.lower() != "meters":
        governor.record(TransformationRecord(
            operation="unit_conversion",
            entity_id="all",
            before=f"units={source_units}",
            after="units=meters",
            reason=f"Converted from {source_units} to meters using factor {tol.unit_scale_factor:.4f}",
            error_class=GeometryErrorClass.REPAIRABLE,
            confidence=1.0
        ))
    
    # ==========================================================================
    # Step 2: Room Geometry Repair
    # ==========================================================================
    from validation.geometry_repair import (
        repair_self_intersection,
        is_degenerate,
        repair_duplicate_points
    )
    
    # Repair room self-intersection
    if not room_m.geometry.is_valid:
        repaired = repair_self_intersection(room_m.geometry)
        governor.record(TransformationRecord(
            operation="buffer_repair",
            entity_id=room_m.id,
            before="invalid_polygon",
            after="buffer(0)_repaired",
            reason="Self-intersection repaired via buffer(0)",
            error_class=GeometryErrorClass.REPAIRABLE,
            confidence=0.95
        ))
        room_m.geometry = repaired
    
    # Repair duplicate points
    repaired = repair_duplicate_points(room_m.geometry, tol.linear_epsilon)
    if repaired != room_m.geometry:
        governor.record(TransformationRecord(
            operation="point_dedup",
            entity_id=room_m.id,
            before="duplicate_points",
            after="deduplicated",
            reason="Removed near-duplicate consecutive points",
            error_class=GeometryErrorClass.REPAIRABLE,
            confidence=0.98
        ))
        room_m.geometry = repaired
    
    # Degeneracy check
    if is_degenerate(room_m.geometry, tol.area_epsilon):
        governor.record(TransformationRecord(
            operation="degenerate_check",
            entity_id=room_m.id,
            before="valid_area",
            after="zero_area",
            reason="Room area near zero after repair",
            error_class=GeometryErrorClass.HARD_INVALID,
            confidence=1.0
        ))
    
    # ==========================================================================
    # Step 3: Obstruction Geometry Repair
    # ==========================================================================
    repaired_obst = []
    for obs in obst_m:
        # Repair self-intersection
        if not obs.geometry.is_valid:
            repaired = repair_self_intersection(obs.geometry)
            governor.record(TransformationRecord(
                operation="buffer_repair",
                entity_id=obs.id,
                before="invalid_polygon",
                after="buffer(0)_repaired",
                reason="Obstruction self-intersection repaired",
                error_class=GeometryErrorClass.REPAIRABLE,
                confidence=0.95
            ))
            obs.geometry = repaired
        
        # Degeneracy check - warning only for obstacles
        if is_degenerate(obs.geometry, tol.area_epsilon):
            governor.record(TransformationRecord(
                operation="degenerate_check",
                entity_id=obs.id,
                before="valid_area",
                after="zero_area",
                reason="Obstruction has near-zero area",
                error_class=GeometryErrorClass.AMBIGUOUS,
                confidence=0.9
            ))
            continue  # Skip degenerate obstructions
        
        repaired_obst.append(obs)
    
    obst_m = repaired_obst
    
    # ==========================================================================
    # Step 4: Origin Normalization (shift to 0,0)
    # ==========================================================================
    min_x, min_y, max_x, max_y = room_m.geometry.bounds
    
    if min_x != 0.0 or min_y != 0.0:
        # Shift room
        room_coords = list(room_m.geometry.exterior.coords)
        shifted = [(x - min_x, y - min_y) for x, y in room_coords]
        room_m = Room(
            id=room_m.id,
            name=room_m.name,
            geometry=Polygon(shifted),
            ceiling_height=room_m.ceiling_height,
            ceiling_type=room_m.ceiling_type
        )
        
        governor.record(TransformationRecord(
            operation="origin_normalization",
            entity_id="room",
            before=f"min_x={min_x}, min_y={min_y}",
            after="origin_at_0_0",
            reason="Local origin reset to (0,0) for reproducibility",
            error_class=GeometryErrorClass.REPAIRABLE,
            confidence=1.0
        ))
        
        # Shift devices
        for i, dev in enumerate(devices_m):
            new_x = dev.position.x - min_x
            new_y = dev.position.y - min_y
            devices_m[i] = Device(
                id=dev.id,
                device_type=dev.device_type,
                position=Point(new_x, new_y),
                z_height=dev.z_height,
                coverage_radius=dev.coverage_radius
            )
        
        governor.record(TransformationRecord(
            operation="origin_normalization",
            entity_id="devices",
            before="global_coords",
            after="local_coords",
            reason="Devices shifted with room origin",
            error_class=GeometryErrorClass.REPAIRABLE,
            confidence=1.0
        ))
        
        # Shift obstructions
        shifted_obst = []
        for obs in obst_m:
            obs_coords = list(obs.geometry.exterior.coords)
            shifted = [(x - min_x, y - min_y) for x, y in obs_coords]
            shifted_obst.append(Obstruction(
                id=obs.id,
                geometry=Polygon(shifted),
                height=obs.height,
                blocks_visibility=obs.blocks_visibility
            ))
        
        if shifted_obst != obst_m:
            governor.record(TransformationRecord(
                operation="origin_normalization",
                entity_id="obstructions",
                before="global_coords",
                after="local_coords",
                reason="Obstructions shifted with room origin",
                error_class=GeometryErrorClass.REPAIRABLE,
                confidence=1.0
            ))
        
        obst_m = shifted_obst
    
    # ==========================================================================
    # Step 5: Spatial Validation
    # ==========================================================================
    room_geom = room_m.geometry
    
    for dev in devices_m:
        if not room_geom.covers(dev.position):
            governor.record(TransformationRecord(
                operation="spatial_validation",
                entity_id=dev.id,
                before="inside",
                after="outside",
                reason=f"Device {dev.id} is outside room bounds",
                error_class=GeometryErrorClass.HARD_INVALID,
                confidence=1.0
            ))
    
    for obs in obst_m:
        if not room_geom.contains(obs.geometry):
            # Partially outside - warning
            intersection = room_geom.intersection(obs.geometry)
            if intersection.area > 0:
                governor.record(TransformationRecord(
                    operation="spatial_validation",
                    entity_id=obs.id,
                    before="fully_inside",
                    after="partially_outside",
                    reason=f"Obstruction {obs.id} not fully inside room",
                    error_class=GeometryErrorClass.AMBIGUOUS,
                    confidence=0.8
                ))
            else:
                governor.record(TransformationRecord(
                    operation="spatial_validation",
                    entity_id=obs.id,
                    before="inside",
                    after="outside",
                    reason=f"Obstruction {obs.id} completely outside room",
                    error_class=GeometryErrorClass.HARD_INVALID,
                    confidence=1.0
                ))
        
        # Check no device inside obstruction
        for dev in devices_m:
            if obs.geometry.covers(dev.position):
                governor.record(TransformationRecord(
                    operation="spatial_validation",
                    entity_id=dev.id,
                    before="clear",
                    after="inside_obstruction",
                    reason=f"Device {dev.id} is inside obstruction {obs.id}",
                    error_class=GeometryErrorClass.HARD_INVALID,
                    confidence=1.0
                ))
    
    return room_m, devices_m, obst_m, governor


# =============================================================================
# Test
# =============================================================================

def run_test_case(name: str, room, devices, obstructions, source_units: str):
    """Run a test case and print results"""
    print("=" * 60)
    print(f"TEST: {name}")
    print("=" * 60)
    
    room_norm, devices_norm, obst_norm, gov = governed_normalization_pipeline(
        room, devices, obstructions, source_units
    )
    
    # Print audit trail
    print(gov.audit_trail())
    
    summary = gov.get_summary()
    print(f"\n--- Summary ---")
    print(f"Total: {summary['total_operations']}, HARD: {summary['hard_invalid']}, REPAIR: {summary['repairable']}, AMBIG: {summary['ambiguous']}")
    print(f"Can proceed: {summary['can_proceed']}")
    
    blocked = gov.has_critical_preventing_compliance()
    print(f"\n{'❌ BLOCKED' if blocked else '✅ CAN PROCEED'}")
    
    return blocked, summary


if __name__ == "__main__":
    from shapely.geometry import Point, Polygon
    from spatial_constraint_engine import Room, Device, Obstruction
    
    # ==========================================================================
    # Test 1: Simple feet to meters (should pass)
    # ==========================================================================
    print("\n" + "#" * 60)
    print("# TEST 1: Feet to Meters Conversion")
    print("#" * 60)
    
    room1 = Room(
        id="room_ft",
        name="Room 32.8ft",
        geometry=Polygon([(0, 0), (32.8, 0), (32.8, 32.8), (0, 32.8), (0, 0)]),
        ceiling_height=8.0
    )
    devices1 = [Device(id="smoke_1", device_type="SMOKE_PHOTOELECTRIC", position=Point(16.4, 16.4))]
    obst1 = []
    
    blocked1, sum1 = run_test_case("Feet to Meters", room1, devices1, obst1, "feet")
    
    # ==========================================================================
    # Test 2: Device outside room (should BLOCK)
    # ==========================================================================
    print("\n" + "#" * 60)
    print("# TEST 2: Device Outside Room")
    print("#" * 60)
    
    room2 = Room(
        id="room_2",
        name="Room 10x10",
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        ceiling_height=3.0
    )
    devices2 = [
        Device(id="smoke_inside", device_type="SMOKE_PHOTOELECTRIC", position=Point(5, 5)),
        Device(id="smoke_outside", device_type="SMOKE_PHOTOELECTRIC", position=Point(15, 15)),  # OUTSIDE!
    ]
    
    blocked2, sum2 = run_test_case("Device Outside", room2, devices2, obst1, "meters")
    
    # ==========================================================================
    # Test 3: Self-intersecting polygon (auto-repaired)
    # ==========================================================================
    print("\n" + "#" * 60)
    print("# TEST 3: Self-Intersecting Polygon")
    print("#" * 60)
    
    # Create a simple self-intersecting polygon (figure-8 / bowtie shape)
    room3 = Room(
        id="room_bowtie",
        name="Bowtie Room",
        geometry=Polygon([(0, 0), (10, 5), (0, 10), (5, 5), (0, 0)]),
        ceiling_height=3.0
    )
    devices3 = [Device(id="smoke_1", device_type="SMOKE_PHOTOELECTRIC", position=Point(2, 2))]
    
    blocked3, sum3 = run_test_case("Self-Intersecting", room3, devices3, obst1, "meters")
    
    # ==========================================================================
    # Test 4: Full integration test
    # ==========================================================================
    print("\n" + "#" * 60)
    print("# TEST 4: Full Pipeline (feet + self-intersection)")
    print("#" * 60)
    
    room4 = Room(
        id="room_full",
        name="32.8ft with bowtie",
        geometry=Polygon([(0, 0), (32.8, 0), (32.8, 32.8), (0, 32.8), (16.4, 16.4), (0, 0)]),
        ceiling_height=8.0
    )
    devices4 = [Device(id="smoke_1", device_type="SMOKE_PHOTOELECTRIC", position=Point(16.4, 16.4))]
    
    blocked4, sum4 = run_test_case("Full Pipeline", room4, devices4, obst1, "feet")
    
    # Final summary
    print("\n" + "=" * 60)
    print("FINAL TEST SUMMARY")
    print("=" * 60)
    print(f"Test 1 (feet):      {'BLOCKED' if blocked1 else 'PASSED'} - {sum1['repairable']} repairs")
    print(f"Test 2 (outside):   {'BLOCKED' if blocked2 else 'PASSED'} - {sum2['hard_invalid']} hard errors")
    print(f"Test 3 (bowtie):    {'BLOCKED' if blocked3 else 'PASSED'} - {sum3['repairable']} repairs")
    print(f"Test 4 (full):     {'BLOCKED' if blocked4 else 'PASSED'} - {sum4['repairable']} repairs")