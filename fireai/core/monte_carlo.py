from __future__ import annotations

"""
monte_carlo.py — Accelerated Monte Carlo Resilience Check
=======================================================
Optional accelerated version using numpy if available.
Falls back to original implementation otherwise.

This module provides run_resilience_check which uses vectorized
operations for faster Monte Carlo simulations.
"""

import random
from typing import List, Tuple

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

# Constants from V10
_MC_ITERATIONS: int = 50
_MC_RESILIENCE_FLOOR: float = 0.80

# Try to import numpy
try:
    import numpy as np

    _NUMPY = True
except ImportError:
    _NUMPY = False


def run_resilience_check(
    positions: List[Tuple[float, float]],
    poly: Polygon,
    radius: float,
    floor: float = _MC_RESILIENCE_FLOOR,
    iterations: int = _MC_ITERATIONS,
    seed: int = 42,
) -> Tuple[float, float, bool]:
    """Run Monte Carlo resilience check for detector placement.

    Args:
        positions: Current detector positions.
        poly: Room polygon for coverage check.
        radius: Coverage radius per detector.
        floor: Minimum pass rate (default 80%).
        iterations: Number of Monte Carlo iterations.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (pass_rate, min_coverage_seen, resilient)

    """
    if _NUMPY:
        return _run_resilience_check_fast(positions, poly, radius, floor, iterations, seed)
    # Fall back to original implementation
    return _run_resilience_check_original(positions, poly, radius, floor, iterations, seed)


def _run_resilience_check_fast(
    positions: List[Tuple[float, float]],
    poly: Polygon,
    radius: float,
    floor: float = _MC_RESILIENCE_FLOOR,
    iterations: int = _MC_ITERATIONS,
    seed: int = 42,
) -> Tuple[float, float, bool]:
    """Accelerated Monte Carlo using numpy vectorized operations.

    Args:
        positions: Current detector positions.
        poly: Room polygon for coverage check.
        radius: Coverage radius per detector.
        floor: Minimum pass rate (default 80%).
        iterations: Number of Monte Carlo iterations.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (pass_rate, min_coverage_seen, resilient)

    """
    if len(positions) < 2:
        return (1.0, 1.0, False)

    # Convert to numpy arrays
    pos_array = np.array(positions)
    n_detectors = len(positions)

    # Pre-compute coverage circles for all detectors
    circles = np.array([Point(x, y).buffer(radius, quad_segs=12) for x, y in positions])
    unary_union(circles)
    total_area = poly.area

    np.random.seed(seed)
    scenarios_passed = 0
    min_coverage_seen = 1.0

    for _ in range(iterations):
        # Randomly remove one detector
        idx = np.random.randint(0, n_detectors)
        remaining = np.delete(pos_array, idx, axis=0)

        if len(remaining) == 0:
            min_coverage_seen = 0.0
            break

        # Calculate coverage
        circles_remaining = np.array([Point(x, y).buffer(radius, quad_segs=12) for x, y in remaining])
        coverage = unary_union(circles_remaining)
        covered_area = poly.intersection(coverage).area
        coverage_fraction = covered_area / total_area

        min_coverage_seen = min(min_coverage_seen, coverage_fraction)

        if coverage_fraction >= floor:
            scenarios_passed += 1

    pass_rate = scenarios_passed / iterations
    resilient = pass_rate >= floor

    return (pass_rate, min_coverage_seen, resilient)


def _run_resilience_check_original(
    positions: List[Tuple[float, float]],
    poly: Polygon,
    radius: float,
    floor: float = _MC_RESILIENCE_FLOOR,
    iterations: int = _MC_ITERATIONS,
    seed: int = 42,
) -> Tuple[float, float, bool]:
    """Original Monte Carlo implementation (fallback).

    This is the same as the implementation in fire_expert_system.py.

    Args:
        positions: Current detector positions.
        poly: Room polygon for coverage check.
        radius: Coverage radius per detector.
        floor: Minimum pass rate (default 80%).
        iterations: Number of Monte Carlo iterations.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (pass_rate, min_coverage_seen, resilient)

    """
    if len(positions) < 2:
        return (1.0, 1.0, False)

    random.seed(seed)
    scenarios_passed = 0
    min_coverage_seen = 1.0

    for _ in range(iterations):
        if not positions:
            break
        idx = random.randint(0, len(positions) - 1)
        remaining = positions[:idx] + positions[idx + 1 :]

        if not remaining:
            min_coverage_seen = 0.0
            break

        coverage = unary_union([Point(x, y).buffer(radius, quad_segs=12) for x, y in remaining])
        covered_area = poly.intersection(coverage).area
        coverage_fraction = covered_area / poly.area

        min_coverage_seen = min(min_coverage_seen, coverage_fraction)

        if coverage_fraction >= floor:
            scenarios_passed += 1

    pass_rate = scenarios_passed / iterations
    resilient = pass_rate >= floor

    return (pass_rate, min_coverage_seen, resilient)
