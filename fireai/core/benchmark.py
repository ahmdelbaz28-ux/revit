#!/usr/bin/env python3
"""
benchmark.py — FireAI Performance Benchmark
Compares analysis time with vs without resilience checks.

Usage:  python fireai/core/benchmark.py
Output: Timing table showing overhead of resilience testing

What it measures:
  - run_resilience=True:  Full Monte Carlo resilience testing (50 scenarios)
  - run_resilience=False: Basic placement only, no resilience

Co-authored-by: openhands <openhands@all-hands.dev>
"""
import time
import statistics
import sys
sys.path.insert(0, '/workspace/project/revit')

from fireai.core.nfpa72_models import RoomSpec, CeilingSpec
from fireai.core.fireai_core import FireAISystem


# Test rooms of different sizes
ROOMS = [
    ("small_3x4", 3, 4, 3.0),
    ("medium_10x8", 10, 8, 3.0),
    ("large_20x15", 20, 15, 4.0),
    ("corridor_20x2", 20, 2, 3.0),
    ("warehouse_30x25", 30, 25, 8.0),
]

REPEATS = 3


def make_spec(label, width, depth, height):
    """Create RoomSpec for benchmarking."""
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=height,
    )
    return RoomSpec(
        room_id=f"{label}_bench",
        width_m=width,
        depth_m=depth,
        occupancy_type="office",
        ceiling_spec=ceiling,
    )


def benchmark(resilience: bool = True) -> dict:
    """Run benchmark with or without resilience."""
    system = FireAISystem(':memory:')
    times = {}
    
    for label, width, depth, height in ROOMS:
        runs = []
        for _ in range(REPEATS):
            spec = make_spec(label, width, depth, height)
            t0 = time.perf_counter()
            system.analyse_room(spec, user_id='bench', run_resilience=resilience)
            runs.append(time.perf_counter() - t0)
        times[label] = statistics.mean(runs)
    
    return times


def main():
    print("=" * 70)
    print("FireAI Performance Benchmark")
    print("=" * 70)
    
    print("\nRunning WITH resilience...")
    t_with = benchmark(resilience=True)
    
    print("Running WITHOUT resilience...")
    t_without = benchmark(resilience=False)
    
    # Print results table
    print(f"\n{'Room':<20} {'With (ms)':>12} {'Without (ms)':>14} {'Slowdown':>10}")
    print("-" * 70)
    
    for i, (label, w, d, h) in enumerate(ROOMS):
        tm = t_with[label] * 1000
        tn = t_without[label] * 1000
        if tn > 0:
            slow = tm / tn
        else:
            slow = 1.0
        print(f"{label:<20} {tm:>12.1f} {tn:>14.1f} {slow:>9.1f}x")
    
    # Average slowdown
    avg_slow = statistics.mean(
        t_with[ROOMS[i][0]] / t_without[ROOMS[i][0]]
        for i in range(len(ROOMS))
        if t_without[ROOMS[i][0]] > 0
    )
    
    print("-" * 70)
    print(f"{'Average resilience overhead':<20} {avg_slow:>33.1f}x")
    print("=" * 70)


if __name__ == "__main__":
    main()