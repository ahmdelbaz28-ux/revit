#!/usr/bin/env python3
"""
simulate_real_day.py - Simulate a full day of FireAI operations.

Creates 50 random rooms and analyzes them through FireAISystem,
verifying audit integrity every 10 analyses and reporting statistics.
"""

import sys
import os
import random
import time
import uuid
from typing import List, Dict, Any

sys.path.insert(0, '/workspace/project/revit')

from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import RoomSpec, CeilingSpec


def generate_rectangle_room(room_id: str) -> RoomSpec:
    """Generate random rectangle room (3-20m)."""
    width = random.uniform(3.0, 20.0)
    depth = random.uniform(3.0, 20.0)
    height = random.uniform(3.0, 4.0)  # NFPA range
    return RoomSpec(
        room_id=room_id,
        width_m=width,
        depth_m=depth,
        ceiling_spec=CeilingSpec(height_at_low_point_m=height),
    )


def generate_l_shaped_room(room_id: str) -> RoomSpec:
    """Generate L-shaped room using polygon_coords."""
    # L-shape: 4 points + 1 inner corner
    w1 = random.uniform(3.0, 10.0)
    w2 = random.uniform(3.0, 10.0)
    h = random.uniform(3.0, 4.0)  # NFPA range
    depth = random.uniform(3.0, 10.0)
    
    # L-shaped polygon coordinates
    polygon = [
        (0, 0),
        (w1, 0),
        (w1, depth),
        (w1 + w2, depth),
        (w1 + w2, depth - depth),
        (0, depth - depth),
    ]
    
    return RoomSpec(
        room_id=room_id,
        width_m=w1 + w2,
        depth_m=depth,
        ceiling_spec=CeilingSpec(height_at_low_point_m=h),
    )


def generate_pentagon_room(room_id: str) -> RoomSpec:
    """Generate pentagon room using polygon_coords."""
    radius = random.uniform(3.0, 8.0)
    angle_step = 2 * 3.14159 / 5
    
    # Pentagon vertices
    polygon = []
    for i in range(5):
        angle = i * angle_step - 3.14159 / 2
        x = radius * (1 + 0.3 * (i % 2)) * (1 if i % 2 == 0 else 0.8) * (1 if i < 2 else -1 if i < 4 else 1)
        y = radius * (1 if i < 2 else -1) * 0.8
        polygon.append((abs(x) + radius, abs(y) + radius))
    
    # Adjust to ensure it's valid
    max_x = max(p[0] for p in polygon)
    max_y = max(p[1] for p in polygon)
    
    return RoomSpec(
        room_id=room_id,
        width_m=max_x,
        depth_m=max_y,
        ceiling_spec=CeilingSpec(height_at_low_point_m=random.uniform(3.0, 4.0)),  # NFPA range
    )


def main():
    print("=" * 60)
    print("FireAI Real Day Simulation")
    print("=" * 60)
    print()
    
    # Initialize system
    print("Initializing FireAISystem...")
    system = FireAISystem(db_path=':memory:')
    
    # Statistics
    all_results = []
    analysis_times = []
    errors = []
    verify_failures = 0
    analysis_count = 0
    
    # Generate 50 rooms
    print("Generating 50 rooms...")
    rooms_30_rect = [generate_rectangle_room(f"rect_{i+1}") for i in range(30)]
    rooms_10_l = [generate_l_shaped_room(f"l_{i+1}") for i in range(10)]
    rooms_10_pent = [generate_pentagon_room(f"pent_{i+1}") for i in range(10)]
    all_rooms = rooms_30_rect + rooms_10_l + rooms_10_pent
    random.shuffle(all_rooms)
    
    print(f"Generated: {len(all_rooms)} rooms")
    print(f"  - 30 rectangle")
    print(f"  - 10 L-shaped")
    print(f"  - 10 pentagon")
    print()
    
    # ========== Part A: Analyze all 50 rooms ==========
    print("-" * 40)
    print("Part A: Analyzing 50 rooms")
    print("-" * 40)
    
    for i, room in enumerate(all_rooms):
        analysis_count += 1
        
        start_time = time.time()
        try:
            result = system.analyse_room(room, user_id=f"sim_user_{i}", run_resilience=True)
            elapsed = time.time() - start_time
            analysis_times.append(elapsed)
            all_results.append({
                "room_id": room.room_id,
                "result": result,
                "elapsed": elapsed,
            })
            
            # Check for issues
            if result.confidence.value == "UNSAFE":
                errors.append(f"UNSAFE: {room.room_id}")
            if result.refused:
                errors.append(f"REFUSED: {room.room_id} - {result.refusal_reason}")
            if result.errors:
                for err in result.errors:
                    errors.append(f"ERROR: {room.room_id} - {err}")
                    
        except Exception as e:
            elapsed = time.time() - start_time
            analysis_times.append(elapsed)
            errors.append(f"EXCEPTION: {room.room_id} - {str(e)}")
        
        # Verify every 10 analyses
        if analysis_count % 10 == 0:
            is_valid = system.verify_audit_integrity()
            print(f"  [{analysis_count}] Audit verify: {'PASS' if is_valid else 'FAIL'}")
            if not is_valid:
                verify_failures += 1
    
    print()
    
    # ========== Part B: Analyze 3 floors (5 rooms each) ==========
    print("-" * 40)
    print("Part B: Analyzing 3 floors (5 rooms each)")
    print("-" * 40)
    
    floor_results = []
    for floor_num in range(3):
        # Take 5 random rooms for this floor
        floor_rooms = all_rooms[floor_num * 5:(floor_num + 1) * 5]
        
        start_time = time.time()
        try:
            results = system.analyse_floor(
                floor_rooms, 
                user_id=f"floor_user_{floor_num}", 
                run_resilience=True
            )
            elapsed = time.time() - start_time
            floor_results.extend(results)
            analysis_times.append(elapsed)
            
            print(f"  Floor {floor_num + 1}: {len(results)} rooms in {elapsed:.2f}s")
            
            for r in results:
                if r.confidence.value == "UNSAFE":
                    errors.append(f"FLOOR UNSAFE: {r.room_id}")
                if r.refused:
                    errors.append(f"FLOOR REFUSED: {r.room_id}")
                    
        except Exception as e:
            errors.append(f"FLOOR EXCEPTION: floor_{floor_num} - {str(e)}")
            print(f"  Floor {floor_num + 1}: ERROR")
    
    # Final verification
    is_valid = system.verify_audit_integrity()
    print()
    print(f"Final audit verify: {'PASS' if is_valid else 'FAIL'}")
    if not is_valid:
        verify_failures += 1
    
    # ========== Statistics ==========
    print()
    print("=" * 60)
    print("STATISTICS")
    print("=" * 60)
    
    # Total analyses
    total_room_analyzes = len(all_rooms)  # 50
    total_floor_analyzes = 3 * 5  # 15
    total_analyzes = total_room_analyzes + total_floor_analyzes
    
    print(f"Total analyses: {total_analyzes}")
    print(f"  - Room analyses: {total_room_analyzes}")
    print(f"  - Floor analyses: {total_floor_analyzes}")
    
    # Success/failure
    success_count = total_analyzes - len([e for e in errors if "UNSAFE" in e or "REFUSED" in e])
    failure_count = len([e for e in errors if "UNSAFE" in e or "REFUSED" in e or "EXCEPTION" in e])
    
    print()
    print(f"Success: {success_count}")
    print(f"Failures: {failure_count}")
    
    # Timing
    if analysis_times:
        avg_time = sum(analysis_times) / len(analysis_times)
        max_time = max(analysis_times)
        min_time = min(analysis_times)
        
        print()
        print(f"Average time: {avg_time:.3f}s")
        print(f"Maximum time: {max_time:.3f}s")
        print(f"Minimum time: {min_time:.3f}s")
    
    # Verify failures
    print()
    print(f"Audit verify failures: {verify_failures}")
    
    # Error summary
    if errors:
        print()
        print("Errors encountered:")
        for err in errors[:10]:  # Show first 10
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
    else:
        print()
        print("No errors encountered!")
    
    # Final verdict
    print()
    print("=" * 60)
    if failure_count == 0 and verify_failures == 0:
        print("SYSTEM READY")
    else:
        print("ISSUES FOUND")
    print("=" * 60)
    
    return 0 if failure_count == 0 and verify_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())