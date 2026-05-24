#!/usr/bin/env python3
"""
FireAI 1,000,000 Room / 10,000 Floor Stress Test
=================================================
MUST NOT BE MODIFIED — per agent.md LIFE-SAFETY RULE 1.

This test generates 1,000,000 random rooms distributed across 10,000 floors
(100 rooms per floor), with varying dimensions and ceiling heights, then
verifies coverage, NFPA compliance, and proof validity.

Results are reported EXACTLY as they occur — no fabrication per Rule 3.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random
import time
import json
import traceback
import math
import gc
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height


def main():
    SEED = 2026
    N_FLOORS = 10000
    ROOMS_PER_FLOOR = 100  # = 1,000,000 total rooms
    N = N_FLOORS * ROOMS_PER_FLOOR

    random.seed(SEED)
    opt = DensityOptimizer()

    # Counters
    c100 = 0  # coverage == 100%
    c99 = 0   # coverage 99-99.9%
    clt99 = 0 # coverage < 99%
    nv = 0    # NFPA valid
    ni = 0    # NFPA invalid
    pv = 0    # proof valid
    pi2 = 0   # proof invalid
    fu = 0    # fallback used
    total_detectors = 0
    failures = []
    proof_fail_details = []
    errors = []
    floor_results = {}

    # Room dimension ranges — realistic building rooms
    # Width/Length: 1.5m (closet) to 60m (warehouse/atrium)
    # Height: 2.0m (basement) to 15.0m (atrium/beyond table)
    # Detector types: 80% smoke, 20% heat

    t0 = time.time()
    room_index = 0

    for floor_num in range(N_FLOORS):
        floor_start = time.time()
        floor_detectors = 0
        floor_nfpa_valid = 0
        floor_proof_valid = 0
        floor_coverage_100 = 0
        floor_errors = 0

        for room_in_floor in range(ROOMS_PER_FLOOR):
            try:
                w = round(random.uniform(1.5, 60), 2)
                l = round(random.uniform(1.5, 60), 2)
                h = round(random.uniform(2.0, 15.0), 2)  # Extended to 15m to test beyond-table fallback
                dt = 'heat' if random.random() < 0.2 else 'smoke'
                room = Room(name=f'F{floor_num:04d}-R{room_in_floor:03d}', width=w, length=l, ceiling_height=h)
                spec = calculate_coverage_radius_from_height(h, dt)
                lay = opt.optimize(room, coverage_radius=spec.radius)

                cov = lay.coverage_pct
                if cov >= 99.99:
                    c100 += 1
                    floor_coverage_100 += 1
                elif cov >= 99:
                    c99 += 1
                else:
                    clt99 += 1

                if lay.nfpa_valid:
                    nv += 1
                    floor_nfpa_valid += 1
                else:
                    ni += 1

                if lay.proof_valid:
                    pv += 1
                    floor_proof_valid += 1
                else:
                    pi2 += 1
                    if len(proof_fail_details) < 50:
                        proof_fail_details.append({
                            'room': f'F{floor_num:04d}-R{room_in_floor:03d}',
                            'w': w, 'l': l, 'h': h,
                            'type': dt, 'cov': round(cov, 4),
                            'method': lay.method,
                            'radius_used': lay.coverage_radius,
                            'det_count': lay.count,
                            'nfpa_valid': lay.nfpa_valid,
                        })

                if lay.fallback_used:
                    fu += 1

                total_detectors += lay.count
                floor_detectors += lay.count

                if cov < 99 or not lay.nfpa_valid:
                    if len(failures) < 100:
                        failures.append({
                            'room': f'F{floor_num:04d}-R{room_in_floor:03d}',
                            'w': w, 'l': l, 'h': h,
                            'type': dt, 'cov': round(cov, 4),
                            'nfpa_valid': lay.nfpa_valid,
                            'proof_valid': lay.proof_valid,
                            'method': lay.method,
                            'det_count': lay.count,
                        })

            except Exception as e:
                floor_errors += 1
                if len(errors) < 50:
                    errors.append({
                        'room': f'F{floor_num:04d}-R{room_in_floor:03d}',
                        'error': str(e),
                        'traceback': traceback.format_exc(),
                    })

            room_index += 1

        # Floor summary
        floor_elapsed = time.time() - floor_start
        floor_results[floor_num] = {
            'rooms': ROOMS_PER_FLOOR,
            'elapsed_s': round(floor_elapsed, 2),
            'detectors': floor_detectors,
            'nfpa_valid': floor_nfpa_valid,
            'proof_valid': floor_proof_valid,
            'coverage_100': floor_coverage_100,
            'errors': floor_errors,
        }

        # Progress report every 100 floors (10,000 rooms)
        if (floor_num + 1) % 100 == 0:
            elapsed = time.time() - t0
            processed = (floor_num + 1) * ROOMS_PER_FLOOR
            rate = processed / elapsed
            eta = (N - processed) / rate
            mem_mb = 0
            try:
                import psutil
                mem_mb = psutil.Process().memory_info().rss / 1024 / 1024
            except:
                pass
            print(f'  Floor {floor_num+1}/{N_FLOORS} | {processed:,}/{N:,} rooms | '
                  f'{rate:.0f} r/s | ETA {eta:.0f}s | '
                  f'Cov100={c100} NFPA={nv} Proof={pv} Fail={len(failures)} Err={len(errors)} '
                  f'Mem={mem_mb:.0f}MB', flush=True)

            # Force GC to prevent memory buildup
            gc.collect()

        # Stop early if too many errors (safety per agent.md Rule 3)
        if len(errors) > 1000:
            print(f'\n⚠️ STOPPED EARLY: {len(errors)} errors exceeded threshold. Reporting partial results.', flush=True)
            break

    e = time.time() - t0
    processed = room_index

    result = {
        'test': 'FireAI 1M Room / 10K Floor Stress Test',
        'seed': SEED,
        'target_rooms': N,
        'target_floors': N_FLOORS,
        'rooms_per_floor': ROOMS_PER_FLOOR,
        'actually_processed': processed,
        'elapsed_s': round(e, 1),
        'rooms_per_sec': round(processed / e, 1) if e > 0 else 0,
        'total_detectors': total_detectors,
        'avg_detectors_per_room': round(total_detectors / processed, 2) if processed > 0 else 0,
        'coverage_100_count': c100,
        'coverage_99_count': c99,
        'coverage_lt_99_count': clt99,
        'nfpa_valid_count': nv,
        'nfpa_invalid_count': ni,
        'proof_valid_count': pv,
        'proof_invalid_count': pi2,
        'fallback_used_count': fu,
        'failure_count': len(failures),
        'error_count': len(errors),
        'coverage_100_pct': round(100 * c100 / processed, 2) if processed > 0 else 0,
        'coverage_99plus_pct': round(100 * (c100 + c99) / processed, 2) if processed > 0 else 0,
        'nfpa_valid_pct': round(100 * nv / processed, 2) if processed > 0 else 0,
        'proof_valid_pct': round(100 * pv / processed, 2) if processed > 0 else 0,
        'failures': failures[:50],
        'proof_fail_sample': proof_fail_details[:20],
        'errors': errors[:20],
        'floor_sample': {str(k): floor_results[k] for k in list(floor_results.keys())[:10]},
        'early_stop': processed < N,
    }

    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'stress_test_1M_results.json')
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f'\n{"="*70}')
    print(f'FireAI 1M Room / 10K Floor Stress Test — EXACT RESULTS')
    print(f'{"="*70}')
    print(f'Rooms processed:    {processed:,} / {N:,} {"(EARLY STOP)" if processed < N else ""}')
    print(f'Elapsed:            {e:.1f}s ({processed/e:.0f} r/s)' if e > 0 else 'Elapsed: N/A')
    print(f'Total detectors:    {total_detectors:,}')
    print(f'Avg det/room:       {total_detectors/processed:.2f}' if processed > 0 else 'Avg det/room: N/A')
    print(f'---')
    print(f'Coverage 100%:      {c100:>8,} ({100*c100/processed:.2f}%)' if processed > 0 else '')
    print(f'Coverage 99-99.9%:  {c99:>8,} ({100*c99/processed:.2f}%)' if processed > 0 else '')
    print(f'Coverage <99%:      {clt99:>8,} ({100*clt99/processed:.2f}%)' if processed > 0 else '')
    print(f'NFPA valid:         {nv:>8,} ({100*nv/processed:.2f}%)' if processed > 0 else '')
    print(f'Proof valid:        {pv:>8,} ({100*pv/processed:.2f}%)' if processed > 0 else '')
    print(f'Fallback used:      {fu:>8,}')
    print(f'Failures:           {len(failures):>8,}')
    print(f'Errors:             {len(errors):>8,}')
    print(f'---')
    print(f'Results saved to: {outpath}')


if __name__ == '__main__':
    main()
