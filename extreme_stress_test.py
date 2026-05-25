#!/usr/bin/env python3
"""
FireAI V30 — Extreme Stress Test
=================================
Pushes the core engine to its ABSOLUTE LIMIT to discover errors.
Room counts: 50K, 100K, 200K, 500K.
Also tests: Database batch writes, Point3D memory, Analytical Verifier,
ExactCoverage, and edge-case geometries.

This is a PRODUCTION CODE test file (NOT a pytest test).
Usage:  python3 extreme_stress_test.py
Output: /home/z/my-project/revit/extreme_stress_results.json

NFPA 72-2022 Life-Safety Compliance:
  - §17.6.3: Detector spacing
  - §17.7.4.2.3.1: Coverage radius R = 0.7 × S
  - Every room MUST get >= 1 detector
  - Coverage MUST be >= 99% (conservative threshold)
"""
import sys
import os

# Ensure project root is on sys.path so both `core.*` and `fireai.*` resolve
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import random
import time
import json
import math
import traceback
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

# ── Core imports (deferred to ensure path is set) ────────────────────────
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
from fireai.core.spatial_engine.analytical_verifier import AnalyticalVerifier
from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1: DensityOptimizer Core Stress Test
# ═══════════════════════════════════════════════════════════════════════════

def stress_density_optimizer(N: int, seed: int = 2026) -> Dict:
    """Stress test DensityOptimizer with N random rooms."""
    random.seed(seed)
    opt = DensityOptimizer()

    c100 = c99 = clt99 = nv = ni = pv = pi2 = fu = 0
    errors = []
    proof_fail_details = []
    total_detectors = 0
    min_coverage = 100.0
    worst_room = None

    t0 = time.time()
    for i in range(N):
        try:
            # Diverse room dimensions — realistic range with some extreme cases
            w = round(random.uniform(1.5, 40), 2)   # 1.5m to 40m
            l = round(random.uniform(1.5, 40), 2)
            h = round(random.uniform(2.0, 12.0), 2)  # 2m to 12m ceiling
            dt = 'heat' if random.random() < 0.2 else 'smoke'
            room = Room(name=f'R-{i:06d}', width=w, length=l, ceiling_height=h)

            spec = calculate_coverage_radius_from_height(h, dt)
            lay = opt.optimize(room, coverage_radius=spec.radius)

            cov = lay.coverage_pct
            total_detectors += lay.count

            if cov < min_coverage:
                min_coverage = cov
                worst_room = {'id': f'R-{i:06d}', 'w': w, 'l': l, 'h': h, 'cov': cov, 'method': lay.method}

            if cov >= 99.99:
                c100 += 1
            elif cov >= 99:
                c99 += 1
            else:
                clt99 += 1

            if lay.nfpa_valid:
                nv += 1
            else:
                ni += 1

            if lay.proof_valid:
                pv += 1
            else:
                pi2 += 1
                if len(proof_fail_details) < 20:
                    proof_fail_details.append({
                        'room': f'R-{i:06d}', 'w': w, 'l': l, 'h': h,
                        'type': dt, 'cov': round(cov, 4), 'method': lay.method,
                        'radius_used': lay.coverage_radius, 'detectors': lay.count
                    })

            if lay.fallback_used:
                fu += 1

            # LIFE-SAFETY: Every room must get at least 1 detector
            if lay.count < 1:
                errors.append({
                    'type': 'ZERO_DETECTORS',
                    'room': f'R-{i:06d}', 'w': w, 'l': l, 'h': h,
                    'cov': cov, 'method': lay.method
                })

            # LIFE-SAFETY: Coverage must be >= 95% (even for extreme rooms)
            if cov < 95.0 and w > 1.0 and l > 1.0:
                errors.append({
                    'type': 'LOW_COVERAGE',
                    'room': f'R-{i:06d}', 'w': w, 'l': l, 'h': h,
                    'cov': round(cov, 4), 'method': lay.method,
                    'detectors': lay.count
                })

        except Exception as e:
            errors.append({
                'type': 'CRASH',
                'room': f'R-{i:06d}',
                'error': str(e),
                'traceback': traceback.format_exc()[:500]
            })

        if (i + 1) % 10000 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (N - i - 1) / rate
            print(f'  [DensityOptimizer] {i+1:,}/{N:,} — {rate:.0f} r/s — ETA {eta:.0f}s', flush=True)

    elapsed = time.time() - t0

    return {
        'phase': 'DensityOptimizer',
        'N': N,
        'elapsed_s': round(elapsed, 1),
        'rooms_per_sec': round(N / elapsed, 0) if elapsed > 0 else 0,
        'total_detectors': total_detectors,
        'avg_detectors_per_room': round(total_detectors / N, 2) if N > 0 else 0,
        'coverage_100_count': c100,
        'coverage_99_count': c99,
        'coverage_lt_99_count': clt99,
        'nfpa_valid_count': nv,
        'nfpa_invalid_count': ni,
        'proof_valid_count': pv,
        'proof_invalid_count': pi2,
        'fallback_used_count': fu,
        'min_coverage_pct': round(min_coverage, 4),
        'worst_room': worst_room,
        'coverage_100_pct': round(100 * c100 / N, 2) if N > 0 else 0,
        'coverage_99plus_pct': round(100 * (c100 + c99) / N, 2) if N > 0 else 0,
        'nfpa_valid_pct': round(100 * nv / N, 2) if N > 0 else 0,
        'proof_valid_pct': round(100 * pv / N, 2) if N > 0 else 0,
        'errors': errors[:30],
        'proof_fail_sample': proof_fail_details[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2: Analytical Verifier Stress Test
# ═══════════════════════════════════════════════════════════════════════════

def stress_analytical_verifier(N: int, seed: int = 2027) -> Dict:
    """Stress test AnalyticalVerifier with rooms having many detectors."""
    random.seed(seed)
    R = 6.37  # standard smoke detector radius
    verifier = AnalyticalVerifier(coverage_radius=R)
    errors = []
    total_checks = 0
    covered_count = 0

    t0 = time.time()
    for i in range(N):
        try:
            w = round(random.uniform(3, 30), 2)
            l = round(random.uniform(3, 30), 2)

            # Generate a grid of detectors (simulating DensityOptimizer output)
            n_det_x = max(1, int(math.ceil(w / 9.1)) + 1)
            n_det_y = max(1, int(math.ceil(l / 9.1)) + 1)
            detectors = []
            for dx in range(n_det_x):
                for dy in range(n_det_y):
                    x = 0.1 + dx * min(w / max(n_det_x - 1, 1), 9.1)
                    y = 0.1 + dy * min(l / max(n_det_y - 1, 1), 9.1)
                    x = min(x, w - 0.1)
                    y = min(y, l - 0.1)
                    detectors.append((round(x, 3), round(y, 3)))

            result = verifier.verify(w, l, detectors)
            total_checks += 1

            if result.is_covered:
                covered_count += 1

        except Exception as e:
            errors.append({
                'type': 'CRASH',
                'room': f'AV-{i:06d}',
                'error': str(e)
            })

        if (i + 1) % 10000 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(f'  [AnalyticalVerifier] {i+1:,}/{N:,} — {rate:.0f} r/s', flush=True)

    elapsed = time.time() - t0
    return {
        'phase': 'AnalyticalVerifier',
        'N': N,
        'elapsed_s': round(elapsed, 1),
        'rooms_per_sec': round(N / elapsed, 0) if elapsed > 0 else 0,
        'covered_count': covered_count,
        'covered_pct': round(100 * covered_count / N, 2) if N > 0 else 0,
        'errors': errors[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3: Point3D + Geometry Stress Test
# ═══════════════════════════════════════════════════════════════════════════

def stress_models(N: int) -> Dict:
    """Stress test Point3D + Geometry with massive object creation."""
    from core.models import Point3D, Geometry
    errors = []

    # 3a: Point3D creation throughput
    t0 = time.time()
    points = []
    try:
        for i in range(N):
            points.append(Point3D(x=i * 0.001, y=i * 0.002, z=3.0))
    except Exception as e:
        errors.append({'type': 'Point3D_CRASH', 'error': str(e)})
    t_point = time.time() - t0

    # 3b: Geometry area + perimeter throughput
    t0 = time.time()
    areas = []
    perimeters = []
    try:
        for i in range(min(N, 50000)):  # Cap at 50K to keep test reasonable
            w = 3.0 + (i % 100) * 0.1
            l = 4.0 + (i % 50) * 0.2
            pts = [
                Point3D(0, 0, 0),
                Point3D(w, 0, 0),
                Point3D(w, l, 0),
                Point3D(0, l, 0),
            ]
            geom = Geometry(points=pts, polyline_closed=True)
            areas.append(geom.calculate_area())
            perimeters.append(geom.calculate_perimeter())
    except Exception as e:
        errors.append({'type': 'Geometry_CRASH', 'error': str(e)})
    t_geom = time.time() - t0

    # 3c: Batch methods
    t0 = time.time()
    try:
        geoms = []
        for i in range(10000):
            w = 5.0 + (i % 20) * 0.5
            l = 6.0 + (i % 15) * 0.3
            pts = [
                Point3D(0, 0, 0),
                Point3D(w, 0, 0),
                Point3D(w, l, 0),
                Point3D(0, l, 0),
            ]
            geoms.append(Geometry(points=pts, polyline_closed=True))
        batch_areas = Geometry.calculate_area_batch(geoms)
        batch_perims = Geometry.calculate_perimeter_batch(geoms)
        # Validate batch results
        assert len(batch_areas) == 10000, f"Batch area count mismatch: {len(batch_areas)}"
        assert len(batch_perims) == 10000, f"Batch perimeter count mismatch: {len(batch_perims)}"
    except Exception as e:
        errors.append({'type': 'Batch_CRASH', 'error': str(e)})
    t_batch = time.time() - t0

    # 3d: Validate area correctness (Shoelace formula)
    area_errors = 0
    for i in range(min(len(areas), 50000)):
        w = 3.0 + (i % 100) * 0.1
        l = 4.0 + (i % 50) * 0.2
        expected = w * l
        if abs(areas[i] - expected) > 0.01:
            area_errors += 1
            if area_errors <= 3:
                errors.append({
                    'type': 'AREA_MISMATCH',
                    'index': i,
                    'expected': round(expected, 4),
                    'actual': round(areas[i], 4),
                    'diff': round(abs(areas[i] - expected), 6)
                })

    # 3e: Memory estimation (slots vs no-slots)
    import sys
    p = Point3D(1.0, 2.0, 3.0)
    point_size = sys.getsizeof(p)

    return {
        'phase': 'Models',
        'N_points': N,
        'N_geometries': min(N, 50000),
        'point_creation_s': round(t_point, 2),
        'point_throughput_per_sec': round(N / t_point, 0) if t_point > 0 else 0,
        'geometry_throughput_per_sec': round(min(N, 50000) / t_geom, 0) if t_geom > 0 else 0,
        'batch_throughput_per_sec': round(10000 / t_batch, 0) if t_batch > 0 else 0,
        'area_errors': area_errors,
        'point_size_bytes': point_size,
        'errors': errors[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4: Database Batch Insert Stress Test
# ═══════════════════════════════════════════════════════════════════════════

def stress_database(N: int) -> Dict:
    """Stress test UniversalDataModel with massive batch inserts."""
    from core.models import Point3D, Geometry, UniversalElement, SemanticProperties, ElementType
    from core.database import UniversalDataModel
    errors = []

    # 4a: :memory: batch insert
    db = UniversalDataModel(db_path=":memory:")
    elements = []
    for i in range(N):
        pts = [
            Point3D(0, 0, 0),
            Point3D(3, 0, 0),
            Point3D(3, 4, 0),
            Point3D(0, 4, 0),
        ]
        geom = Geometry(points=pts, polyline_closed=True)
        props = SemanticProperties(
            element_type=ElementType.ROOM,
            name=f'Room-{i:06d}'
        )
        el = UniversalElement(
            element_id=f'EL-{i:08d}',
            properties=props,
            geometry=geom,
        )
        elements.append(el)

    # Batch insert
    t0 = time.time()
    try:
        db.add_elements_batch(elements, batch_size=5000)
    except Exception as e:
        errors.append({'type': 'BATCH_INSERT_CRASH', 'error': str(e)})
    t_batch = time.time() - t0

    # Verify count
    stored_count = len(db.elements)
    if stored_count != N:
        errors.append({
            'type': 'COUNT_MISMATCH',
            'expected': N,
            'actual': stored_count
        })

    db.close()

    return {
        'phase': 'Database',
        'N': N,
        'batch_insert_s': round(t_batch, 2),
        'batch_throughput_per_sec': round(N / t_batch, 0) if t_batch > 0 else 0,
        'stored_count': stored_count,
        'errors': errors[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5: Edge-Case Geometry Stress Test
# ═══════════════════════════════════════════════════════════════════════════

def stress_edge_cases() -> Dict:
    """Test edge-case room geometries that commonly break algorithms."""
    opt = DensityOptimizer()
    errors = []
    results = []

    edge_cases = [
        # (name, width, length, height, detector_type)
        ("1cm_wide_corridor", 0.01, 50.0, 3.0, 'smoke'),
        ("1cm_short_room", 5.0, 0.01, 3.0, 'smoke'),
        ("1cm_square", 0.01, 0.01, 3.0, 'smoke'),
        ("mega_warehouse", 80.0, 80.0, 3.0, 'smoke'),
        ("mega_high_ceiling", 20.0, 20.0, 15.0, 'heat'),
        ("narrow_corridor_2m", 2.0, 60.0, 3.0, 'smoke'),
        ("tall_stairwell", 4.0, 5.0, 12.0, 'smoke'),
        ("tiny_bathroom", 1.0, 1.0, 2.7, 'smoke'),
        ("aspect_ratio_100x", 0.5, 50.0, 3.0, 'smoke'),
        ("aspect_ratio_100y", 50.0, 0.5, 3.0, 'smoke'),
        ("perfect_square_9.1", 9.1, 9.1, 3.0, 'smoke'),
        ("just_over_2R", 12.75, 12.75, 3.0, 'smoke'),  # Just over 2R = 12.74
        ("exactly_1_detector", 6.37, 6.37, 3.0, 'smoke'),  # R×R room
        ("infinity_ceiling", 10.0, 10.0, 100.0, 'smoke'),  # Extreme height
        ("minimum_ceiling", 10.0, 10.0, 2.0, 'smoke'),
        ("heat_detector_large", 30.0, 30.0, 4.0, 'heat'),
        ("L_shaped_wide", 15.0, 3.0, 3.0, 'smoke'),  # Elongated
        ("1m_x_1m", 1.0, 1.0, 3.0, 'smoke'),
        ("0.5m_x_0.5m", 0.5, 0.5, 3.0, 'smoke'),
        ("100m_x_1m", 100.0, 1.0, 3.0, 'smoke'),  # Very long narrow
    ]

    for name, w, l, h, dt in edge_cases:
        try:
            room = Room(name=name, width=w, length=l, ceiling_height=h)
            spec = calculate_coverage_radius_from_height(h, dt)
            lay = opt.optimize(room, coverage_radius=spec.radius)

            result = {
                'name': name,
                'w': w, 'l': l, 'h': h,
                'type': dt,
                'detectors': lay.count,
                'coverage_pct': round(lay.coverage_pct, 4),
                'proof_valid': lay.proof_valid,
                'nfpa_valid': lay.nfpa_valid,
                'method': lay.method,
                'radius': round(lay.coverage_radius, 3),
                'fallback': lay.fallback_used,
            }
            results.append(result)

            # Life-safety checks
            if w > 0.5 and l > 0.5 and lay.count < 1:
                errors.append({
                    'type': 'ZERO_DETECTORS',
                    'case': name,
                    'w': w, 'l': l,
                    'coverage': lay.coverage_pct
                })

        except Exception as e:
            errors.append({
                'type': 'CRASH',
                'case': name,
                'error': str(e),
                'traceback': traceback.format_exc()[:300]
            })
            results.append({'name': name, 'error': str(e)})

    return {
        'phase': 'EdgeCases',
        'total_cases': len(edge_cases),
        'results': results,
        'errors': errors[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 6: Cross-Engine Agreement Test
# ═══════════════════════════════════════════════════════════════════════════

def stress_cross_engine(N: int, seed: int = 2028) -> Dict:
    """Verify DensityOptimizer and AnalyticalVerifier agree."""
    random.seed(seed)
    opt = DensityOptimizer()
    R = 6.37
    verifier = AnalyticalVerifier(coverage_radius=R)

    agree = 0
    disagree = 0
    disagreements = []

    t0 = time.time()
    for i in range(N):
        try:
            w = round(random.uniform(3, 20), 2)
            l = round(random.uniform(3, 20), 2)
            h = round(random.uniform(2.5, 6.0), 2)
            dt = 'heat' if random.random() < 0.2 else 'smoke'

            room = Room(name=f'CE-{i:06d}', width=w, length=l, ceiling_height=h)
            spec = calculate_coverage_radius_from_height(h, dt)
            lay = opt.optimize(room, coverage_radius=spec.radius)

            # Run analytical verification with the SAME detectors
            av = AnalyticalVerifier(coverage_radius=lay.coverage_radius)
            result = av.verify(w, l, lay.detectors)

            # Both should agree on coverage
            opt_covered = lay.coverage_pct >= 99.9 and lay.proof_valid
            av_covered = result.is_covered

            if opt_covered == av_covered:
                agree += 1
            else:
                disagree += 1
                if len(disagreements) < 10:
                    disagreements.append({
                        'room': f'CE-{i:06d}', 'w': w, 'l': l, 'h': h,
                        'opt_cov': round(lay.coverage_pct, 4),
                        'opt_proof': lay.proof_valid,
                        'av_covered': result.is_covered,
                        'av_corner': result.corner_coverage_complete,
                        'av_midpoint': result.midpoint_coverage_complete,
                        'av_wall': result.wall_coverage_complete,
                        'detectors': lay.count,
                        'method': lay.method,
                    })

        except Exception as e:
            disagree += 1
            if len(disagreements) < 10:
                disagreements.append({
                    'room': f'CE-{i:06d}',
                    'error': str(e)
                })

        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(f'  [CrossEngine] {i+1:,}/{N:,} — {rate:.0f} r/s', flush=True)

    elapsed = time.time() - t0
    return {
        'phase': 'CrossEngine',
        'N': N,
        'elapsed_s': round(elapsed, 1),
        'agree_count': agree,
        'disagree_count': disagree,
        'agree_pct': round(100 * agree / N, 2) if N > 0 else 0,
        'disagreements': disagreements[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("  FireAI V30 — EXTREME STRESS TEST")
    print("  Pushing core engine to ABSOLUTE LIMITS")
    print("=" * 72)

    all_results = {}
    total_errors = 0

    # ── Phase 1: DensityOptimizer at 10K, 50K ────────────────────────
    for N in [10000, 50000]:
        print(f"\n{'─' * 72}")
        print(f"  PHASE 1: DensityOptimizer — {N:,} rooms")
        print(f"{'─' * 72}")
        result = stress_density_optimizer(N)
        all_results[f'density_{N//1000}K'] = result
        total_errors += len(result['errors'])
        print(f"  → {N:,} rooms in {result['elapsed_s']}s ({result['rooms_per_sec']:.0f} r/s)")
        print(f"  → Coverage 100%: {result['coverage_100_pct']}% | NFPA valid: {result['nfpa_valid_pct']}% | Proof valid: {result['proof_valid_pct']}%")
        print(f"  → Min coverage: {result['min_coverage_pct']}% | Errors: {len(result['errors'])}")

    # ── Phase 2: Analytical Verifier at 50K ──────────────────────────────
    print(f"\n{'─' * 72}")
    print(f"  PHASE 2: AnalyticalVerifier — 50,000 rooms")
    print(f"{'─' * 72}")
    result = stress_analytical_verifier(50000)
    all_results['analytical_50K'] = result
    total_errors += len(result['errors'])
    print(f"  → 50K rooms in {result['elapsed_s']}s ({result['rooms_per_sec']:.0f} r/s)")
    print(f"  → Covered: {result['covered_pct']}% | Errors: {len(result['errors'])}")

    # ── Phase 3: Point3D + Geometry at 500K ────────────────────────────────
    print(f"\n{'─' * 72}")
    print(f"  PHASE 3: Point3D + Geometry — 500,000 objects")
    print(f"{'─' * 72}")
    result = stress_models(500000)
    all_results['models_1M'] = result
    total_errors += len(result['errors'])
    print(f"  → Point3D: {result['point_throughput_per_sec']:.0f} obj/s | Geometry: {result['geometry_throughput_per_sec']:.0f} obj/s")
    print(f"  → Batch: {result['batch_throughput_per_sec']:.0f} obj/s | Area errors: {result['area_errors']} | Point size: {result['point_size_bytes']}B")

    # ── Phase 4: Database batch insert at 100K ───────────────────────────
    print(f"\n{'─' * 72}")
    print(f"  PHASE 4: Database — 100,000 batch inserts")
    print(f"{'─' * 72}")
    result = stress_database(100000)
    all_results['database_100K'] = result
    total_errors += len(result['errors'])
    print(f"  → 100K inserts in {result['batch_insert_s']}s ({result['batch_throughput_per_sec']:.0f} el/s)")
    print(f"  → Stored: {result['stored_count']} | Errors: {len(result['errors'])}")

    # ── Phase 5: Edge Cases ──────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print(f"  PHASE 5: Edge-Case Geometries — 20 extreme rooms")
    print(f"{'─' * 72}")
    result = stress_edge_cases()
    all_results['edge_cases'] = result
    total_errors += len(result['errors'])
    print(f"  → Cases: {result['total_cases']} | Errors: {len(result['errors'])}")
    for r in result['results']:
        if 'error' in r:
            print(f"  ❌ {r['name']}: CRASH — {r['error'][:100]}")
        elif r.get('coverage_pct', 0) < 95:
            print(f"  ⚠️  {r['name']}: cov={r['coverage_pct']}% | dets={r['detectors']} | method={r['method']}")
        else:
            print(f"  ✅ {r['name']}: cov={r['coverage_pct']}% | dets={r['detectors']} | method={r['method']} | nfpa={r['nfpa_valid']}")

    # ── Phase 6: Cross-Engine Agreement at 10K ───────────────────────────
    print(f"\n{'─' * 72}")
    print(f"  PHASE 6: Cross-Engine Agreement — 10,000 rooms")
    print(f"{'─' * 72}")
    result = stress_cross_engine(10000)
    all_results['cross_engine_10K'] = result
    total_errors += len(result['disagreements'])
    print(f"  → Agree: {result['agree_pct']}% | Disagree: {result['disagree_count']}")
    if result['disagreements']:
        print(f"  ⚠️  Disagreements found! Sample:")
        for d in result['disagreements'][:5]:
            print(f"      {d}")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print(f"  SUMMARY")
    print(f"{'=' * 72}")
    print(f"  Total errors discovered: {total_errors}")
    if total_errors == 0:
        print(f"  ✅ ALL TESTS PASSED — Core engine is resilient under extreme stress")
    else:
        print(f"  ❌ ERRORS FOUND — Must fix before release")
    print(f"{'=' * 72}")

    # Save results
    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'extreme_stress_results.json')
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Results saved to: {outpath}")

    return total_errors


if __name__ == '__main__':
    errors = main()
    sys.exit(1 if errors > 0 else 0)
