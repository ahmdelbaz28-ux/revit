#!/usr/bin/env python3
"""
FireAI 1,000,000 Room / 10,000 Floor Stress Test (Multiprocessing)
==================================================================
Per agent.md Rule 1: NEVER modify tests. This is a NEW test.
Per agent.md Rule 3: NO fabrication — results reported exactly as they occur.

Uses multiprocessing to leverage all available CPU cores.
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
from multiprocessing import Pool, cpu_count, Manager
from functools import partial


def process_room(args):
    """Process a single room — designed for multiprocessing."""
    room_id, w, l, h, dt, seed = args
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height

        opt = DensityOptimizer()
        room = Room(name=room_id, width=w, length=l, ceiling_height=h)
        spec = calculate_coverage_radius_from_height(h, dt)
        lay = opt.optimize(room, coverage_radius=spec.radius)

        return {
            'ok': True,
            'room': room_id,
            'cov': lay.coverage_pct,
            'nfpa_valid': lay.nfpa_valid,
            'proof_valid': lay.proof_valid,
            'fallback': lay.fallback_used,
            'det_count': lay.count,
            'method': lay.method,
            'radius': lay.coverage_radius,
            'w': w, 'l': l, 'h': h, 'dt': dt,
        }
    except Exception as e:
        return {
            'ok': False,
            'room': room_id,
            'error': str(e),
        }


def main():
    SEED = 2026
    N_FLOORS = 10000
    ROOMS_PER_FLOOR = 100
    N = N_FLOORS * ROOMS_PER_FLOOR  # 1,000,000
    N_CPUS = cpu_count()

    print(f'FireAI 1M Room Stress Test', flush=True)
    print(f'Rooms: {N:,} | Floors: {N_FLOORS:,} | Rooms/Floor: {ROOMS_PER_FLOOR}', flush=True)
    print(f'CPU cores: {N_CPUS}', flush=True)
    print(f'Seed: {SEED}', flush=True)
    print(flush=True)

    # Generate all room specifications
    print(f'Generating {N:,} room specifications...', flush=True)
    random.seed(SEED)
    room_specs = []
    for floor_num in range(N_FLOORS):
        for room_in_floor in range(ROOMS_PER_FLOOR):
            w = round(random.uniform(1.5, 60), 2)
            l = round(random.uniform(1.5, 60), 2)
            h = round(random.uniform(2.0, 15.0), 2)
            dt = 'heat' if random.random() < 0.2 else 'smoke'
            room_id = f'F{floor_num:04d}-R{room_in_floor:03d}'
            room_specs.append((room_id, w, l, h, dt, SEED))

    print(f'Generated {len(room_specs):,} room specs.', flush=True)
    print(f'Starting multiprocessing pool with {N_CPUS} workers...', flush=True)
    print(flush=True)

    # Process in batches of 10,000 rooms
    BATCH_SIZE = 10000
    total_batches = math.ceil(N / BATCH_SIZE)

    # Counters
    c100 = 0; c99 = 0; clt99 = 0
    nv = 0; ni = 0
    pv = 0; pi2 = 0
    fu = 0
    total_detectors = 0
    failures = []
    proof_fail_details = []
    errors = []

    t0 = time.time()

    with Pool(processes=N_CPUS) as pool:
        for batch_idx in range(total_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, N)
            batch = room_specs[start_idx:end_idx]

            batch_t0 = time.time()
            results = pool.map(process_room, batch)
            batch_elapsed = time.time() - batch_t0

            for r in results:
                if not r['ok']:
                    errors.append({'room': r['room'], 'error': r['error']})
                    continue

                cov = r['cov']
                if cov >= 99.99:
                    c100 += 1
                elif cov >= 99:
                    c99 += 1
                else:
                    clt99 += 1

                if r['nfpa_valid']:
                    nv += 1
                else:
                    ni += 1

                if r['proof_valid']:
                    pv += 1
                else:
                    pi2 += 1
                    if len(proof_fail_details) < 100:
                        proof_fail_details.append({
                            'room': r['room'], 'w': r['w'], 'l': r['l'], 'h': r['h'],
                            'type': r['dt'], 'cov': round(cov, 4),
                            'method': r['method'], 'radius_used': r['radius'],
                            'det_count': r['det_count'], 'nfpa_valid': r['nfpa_valid'],
                        })

                if r['fallback']:
                    fu += 1

                total_detectors += r['det_count']

                if cov < 99 or not r['nfpa_valid']:
                    if len(failures) < 200:
                        failures.append({
                            'room': r['room'], 'w': r['w'], 'l': r['l'], 'h': r['h'],
                            'type': r['dt'], 'cov': round(cov, 4),
                            'nfpa_valid': r['nfpa_valid'], 'proof_valid': r['proof_valid'],
                            'method': r['method'], 'det_count': r['det_count'],
                        })

            processed = end_idx
            elapsed = time.time() - t0
            rate = processed / elapsed
            eta = (N - processed) / rate if rate > 0 else 0

            print(f'  Batch {batch_idx+1}/{total_batches} | {processed:,}/{N:,} rooms | '
                  f'{rate:.0f} r/s | ETA {eta/60:.0f}min | '
                  f'Cov100={c100:,} NFPA={nv:,} Proof={pv:,} Fail={len(failures)} Err={len(errors)}',
                  flush=True)

            # Safety: stop if too many errors
            if len(errors) > 1000:
                print(f'\n⚠️ STOPPED: {len(errors)} errors. Reporting partial results.', flush=True)
                break

    e = time.time() - t0

    result = {
        'test': 'FireAI 1M Room / 10K Floor Stress Test (Multiprocessing)',
        'seed': SEED,
        'target_rooms': N,
        'target_floors': N_FLOORS,
        'rooms_per_floor': ROOMS_PER_FLOOR,
        'actually_processed': processed,
        'cpu_cores': N_CPUS,
        'elapsed_s': round(e, 1),
        'rooms_per_sec': round(processed / e, 1),
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
        'proof_fail_sample': proof_fail_details[:30],
        'errors': errors[:20],
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
    print(f'CPU cores used:     {N_CPUS}')
    print(f'Elapsed:            {e:.1f}s ({processed/e:.0f} r/s)')
    print(f'Total detectors:    {total_detectors:,}')
    print(f'Avg det/room:       {total_detectors/processed:.2f}')
    print(f'---')
    print(f'Coverage 100%:      {c100:>8,} ({100*c100/processed:.2f}%)')
    print(f'Coverage 99-99.9%:  {c99:>8,} ({100*c99/processed:.2f}%)')
    print(f'Coverage <99%:      {clt99:>8,} ({100*clt99/processed:.2f}%)')
    print(f'NFPA valid:         {nv:>8,} ({100*nv/processed:.2f}%)')
    print(f'Proof valid:        {pv:>8,} ({100*pv/processed:.2f}%)')
    print(f'Fallback used:      {fu:>8,}')
    print(f'Failures:           {len(failures):>8,}')
    print(f'Errors:             {len(errors):>8,}')
    print(f'---')
    print(f'Results saved to: {outpath}')


if __name__ == '__main__':
    main()
