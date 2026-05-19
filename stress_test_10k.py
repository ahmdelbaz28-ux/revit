#!/usr/bin/env python3
"""
FireAI 10,000 Room Stress Test — R=0.7×S (post CRITICAL FIX)
=============================================================
Usage:  python3 stress_test_10k.py
Output: stress_test_10k_results.json

This test generates 10,000 random rooms with varying dimensions
and ceiling heights, then verifies coverage, NFPA compliance,
and proof validity. Results are saved to JSON.

Estimated runtime: ~30-50 minutes (VERIFY_STEP=0.20m)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random
import time
import json
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height


def main():
    SEED = 2026
    N = 10000

    random.seed(SEED)
    opt = DensityOptimizer()

    c100 = c99 = clt99 = nv = ni = pv = pi2 = fu = 0
    failures = []
    proof_fail_details = []

    t0 = time.time()
    for i in range(N):
        w = round(random.uniform(1.5, 60), 2)
        l = round(random.uniform(1.5, 60), 2)
        h = round(random.uniform(2.0, 12.0), 2)
        dt = 'heat' if random.random() < 0.2 else 'smoke'
        room = Room(name=f'R-{i:05d}', width=w, length=l, ceiling_height=h)
        spec = calculate_coverage_radius_from_height(h, dt)
        lay = opt.optimize(room, coverage_radius=spec.radius)

        cov = lay.coverage_pct
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
            proof_fail_details.append({
                'room': f'R-{i:05d}', 'w': w, 'l': l, 'h': h,
                'type': dt, 'cov': round(cov, 4), 'method': lay.method,
                'radius_used': lay.coverage_radius
            })

        if lay.fallback_used:
            fu += 1

        if cov < 99 or not lay.nfpa_valid:
            failures.append({
                'room': f'R-{i:05d}', 'w': w, 'l': l, 'h': h,
                'type': dt, 'cov': round(cov, 4), 'nfpa_valid': lay.nfpa_valid,
                'proof_valid': lay.proof_valid, 'method': lay.method
            })

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (N - i - 1) / rate
            print(f'  {i+1}/{N} done — {rate:.0f} r/s — ETA {eta:.0f}s', flush=True)

    e = time.time() - t0

    result = {
        'test': 'FireAI 10K Stress Test (R=0.7*S fix)',
        'seed': SEED,
        'N': N,
        'elapsed_s': round(e, 1),
        'rooms_per_sec': round(N / e, 0),
        'coverage_100_count': c100,
        'coverage_99_count': c99,
        'coverage_lt_99_count': clt99,
        'nfpa_valid_count': nv,
        'nfpa_invalid_count': ni,
        'proof_valid_count': pv,
        'proof_invalid_count': pi2,
        'fallback_used_count': fu,
        'failure_count': len(failures),
        'coverage_100_pct': round(100 * c100 / N, 2),
        'coverage_99plus_pct': round(100 * (c100 + c99) / N, 2),
        'nfpa_valid_pct': round(100 * nv / N, 2),
        'proof_valid_pct': round(100 * pv / N, 2),
        'failures': failures[:50],
        'proof_fail_sample': proof_fail_details[:20],
    }

    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'stress_test_10k_results.json')
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f'\n=== FireAI 10K Stress Test (R=0.7×S fix) ===')
    print(f'Rooms: {N}  Time: {e:.1f}s ({N/e:.0f} r/s)')
    print(f'Coverage 100%:      {c100:>6} ({100*c100/N:.1f}%)')
    print(f'Coverage 99-99.9%:  {c99:>6} ({100*c99/N:.1f}%)')
    print(f'Coverage <99%:      {clt99:>6} ({100*clt99/N:.1f}%)')
    print(f'NFPA valid:         {nv:>6} ({100*nv/N:.1f}%)')
    print(f'Proof valid:        {pv:>6} ({100*pv/N:.1f}%)')
    print(f'Fallback used:      {fu}')
    print(f'Coverage/NFPA failures: {len(failures)}')
    print(f'Results saved to: {outpath}')


if __name__ == '__main__':
    main()
