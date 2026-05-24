#!/usr/bin/env python3
"""
FireAI 1,000,000 Room / 10,000 Floor Stress Test — Batch Mode
==============================================================
Per agent.md: NO fabrication, report EXACT results.
Processes rooms in batches to manage memory efficiently.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random, time, json, math, gc, traceback

def run_batch(opt, start_idx, batch_size, seed_offset):
    """Process a batch of rooms and return stats."""
    random.seed(2026 + seed_offset)
    # Skip to the right position in the random sequence
    for _ in range(start_idx * 5):
        random.random()

    c100 = 0; c99 = 0; clt99 = 0
    nv = 0; ni = 0
    pv = 0; pi2 = 0
    fu = 0
    total_det = 0
    failures = []
    proof_fails = []
    errors = []

    from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height

    for i in range(batch_size):
        try:
            w = round(random.uniform(1.5, 60), 2)
            l = round(random.uniform(1.5, 60), 2)
            h = round(random.uniform(2.0, 15.0), 2)
            dt = 'heat' if random.random() < 0.2 else 'smoke'

            from fireai.core.spatial_engine.density_optimizer import Room
            room = Room(name=f'B{seed_offset}-R{i:04d}', width=w, length=l, ceiling_height=h)
            spec = calculate_coverage_radius_from_height(h, dt)
            lay = opt.optimize(room, coverage_radius=spec.radius)

            cov = lay.coverage_pct
            if cov >= 99.99: c100 += 1
            elif cov >= 99: c99 += 1
            else: clt99 += 1

            if lay.nfpa_valid: nv += 1
            else: ni += 1

            if lay.proof_valid: pv += 1
            else:
                pi2 += 1
                if len(proof_fails) < 5:
                    proof_fails.append({'room': room.name, 'w':w, 'l':l, 'h':h,
                                       'type':dt, 'cov':round(cov,4), 'method':lay.method,
                                       'dets':lay.count, 'radius':lay.coverage_radius})

            if lay.fallback_used: fu += 1
            total_det += lay.count

            if cov < 99 or not lay.nfpa_valid:
                if len(failures) < 5:
                    failures.append({'room': room.name, 'w':w, 'l':l, 'h':h,
                                    'type':dt, 'cov':round(cov,4),
                                    'nfpa':lay.nfpa_valid, 'proof':lay.proof_valid,
                                    'method':lay.method, 'dets':lay.count})
        except Exception as e:
            if len(errors) < 5:
                errors.append({'room': f'B{seed_offset}-R{i:04d}', 'error': str(e)})

    return {
        'c100': c100, 'c99': c99, 'clt99': clt99,
        'nv': nv, 'ni': ni, 'pv': pv, 'pi2': pi2,
        'fu': fu, 'total_det': total_det,
        'batch_size': batch_size,
        'failures': failures, 'proof_fails': proof_fails, 'errors': errors,
    }


def main():
    N_FLOORS = 10000
    ROOMS_PER_FLOOR = 100
    N = N_FLOORS * ROOMS_PER_FLOOR  # 1,000,000
    BATCH_SIZE = 5000  # 5000 rooms per batch
    N_BATCHES = N // BATCH_SIZE  # 200 batches

    from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
    opt = DensityOptimizer()

    print(f'FireAI 1M Room / 10K Floor Stress Test — Batch Mode', flush=True)
    print(f'Total: {N:,} rooms | {N_FLOORS:,} floors | {ROOMS_PER_FLOOR} rooms/floor', flush=True)
    print(f'Batch size: {BATCH_SIZE:,} rooms | {N_BATCHES} batches', flush=True)
    print(f'Seed: 2026', flush=True)
    print(flush=True)

    # Global counters
    C100 = 0; C99 = 0; CLT99 = 0
    NV = 0; NI = 0
    PV = 0; PI2 = 0
    FU = 0
    TOTAL_DET = 0
    ALL_FAILURES = []
    ALL_PROOF_FAILS = []
    ALL_ERRORS = []
    PROCESSED = 0

    t0 = time.time()

    for batch_idx in range(N_BATCHES):
        bt0 = time.time()
        result = run_batch(opt, batch_idx * BATCH_SIZE, BATCH_SIZE, batch_idx)
        bt = time.time() - bt0

        C100 += result['c100']
        C99 += result['c99']
        CLT99 += result['clt99']
        NV += result['nv']
        NI += result['ni']
        PV += result['pv']
        PI2 += result['pi2']
        FU += result['fu']
        TOTAL_DET += result['total_det']
        PROCESSED += result['batch_size']

        ALL_FAILURES.extend(result['failures'])
        ALL_PROOF_FAILS.extend(result['proof_fails'])
        ALL_ERRORS.extend(result['errors'])

        elapsed = time.time() - t0
        rate = PROCESSED / elapsed
        eta = (N - PROCESSED) / rate if rate > 0 else 0

        print(f'  Batch {batch_idx+1}/{N_BATCHES} | {PROCESSED:,}/{N:,} rooms | '
              f'{bt:.1f}s/batch | {rate:.0f} r/s | ETA {eta/60:.0f}min | '
              f'Cov100={C100:,} NFPA={NV:,} Proof={PV:,} Fail={CLT99:,} Err={len(ALL_ERRORS)}',
              flush=True)

        gc.collect()

        # Safety: stop if too many errors
        if len(ALL_ERRORS) > 1000:
            print(f'\n⚠️ STOPPED: {len(ALL_ERRORS)} errors. Reporting partial results.', flush=True)
            break

        # Also stop if runtime exceeds 8 minutes to avoid timeout
        if elapsed > 480:
            print(f'\n⚠️ TIME LIMIT: {elapsed:.0f}s elapsed. Reporting partial results.', flush=True)
            break

    e = time.time() - t0

    result = {
        'test': 'FireAI 1M Room / 10K Floor Stress Test (Batch Mode)',
        'seed': 2026,
        'target_rooms': N,
        'target_floors': N_FLOORS,
        'rooms_per_floor': ROOMS_PER_FLOOR,
        'actually_processed': PROCESSED,
        'elapsed_s': round(e, 1),
        'rooms_per_sec': round(PROCESSED / e, 1),
        'total_detectors': TOTAL_DET,
        'avg_detectors_per_room': round(TOTAL_DET / PROCESSED, 2) if PROCESSED > 0 else 0,
        'coverage_100_count': C100,
        'coverage_99_count': C99,
        'coverage_lt_99_count': CLT99,
        'nfpa_valid_count': NV,
        'nfpa_invalid_count': NI,
        'proof_valid_count': PV,
        'proof_invalid_count': PI2,
        'fallback_used_count': FU,
        'failure_count': CLT99 + NI,
        'error_count': len(ALL_ERRORS),
        'coverage_100_pct': round(100 * C100 / PROCESSED, 2) if PROCESSED > 0 else 0,
        'coverage_99plus_pct': round(100 * (C100 + C99) / PROCESSED, 2) if PROCESSED > 0 else 0,
        'nfpa_valid_pct': round(100 * NV / PROCESSED, 2) if PROCESSED > 0 else 0,
        'proof_valid_pct': round(100 * PV / PROCESSED, 2) if PROCESSED > 0 else 0,
        'failures_sample': ALL_FAILURES[:50],
        'proof_fail_sample': ALL_PROOF_FAILS[:30],
        'errors_sample': ALL_ERRORS[:20],
        'early_stop': PROCESSED < N,
        'estimated_full_runtime_hours': round(N * e / PROCESSED / 3600, 1) if PROCESSED > 0 else None,
    }

    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'stress_test_1M_results.json')
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f'\n{"="*70}')
    print(f'FireAI 1M Room / 10K Floor Stress Test — EXACT RESULTS')
    print(f'{"="*70}')
    print(f'Rooms processed:    {PROCESSED:,} / {N:,} {"(EARLY STOP)" if PROCESSED < N else ""}')
    print(f'Elapsed:            {e:.1f}s ({PROCESSED/e:.0f} r/s)')
    print(f'Total detectors:    {TOTAL_DET:,}')
    print(f'Avg det/room:       {TOTAL_DET/PROCESSED:.2f}')
    print(f'---')
    print(f'Coverage 100%:      {C100:>8,} ({100*C100/PROCESSED:.2f}%)')
    print(f'Coverage 99-99.9%:  {C99:>8,} ({100*C99/PROCESSED:.2f}%)')
    print(f'Coverage <99%:      {CLT99:>8,} ({100*CLT99/PROCESSED:.2f}%)')
    print(f'NFPA valid:         {NV:>8,} ({100*NV/PROCESSED:.2f}%)')
    print(f'Proof valid:        {PV:>8,} ({100*PV/PROCESSED:.2f}%)')
    print(f'Fallback used:      {FU:>8,}')
    print(f'Failures (cov<99 or nfpa invalid): {CLT99+NI:,}')
    print(f'Errors:             {len(ALL_ERRORS):>8,}')
    if PROCESSED < N:
        print(f'Estimated full runtime: {N*e/PROCESSED/3600:.1f} hours')
    print(f'---')
    print(f'Results saved to: {outpath}')


if __name__ == '__main__':
    main()
