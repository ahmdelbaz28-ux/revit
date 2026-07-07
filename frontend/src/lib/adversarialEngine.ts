/**
 * adversarialEngine.ts — Executes attack scenarios against formal verifier.
 *
 * Runs continuous adversarial cycles until no new failures in 3 consecutive cycles.
 */

import { FormalVerifier } from './formalVerifier';
import { ATTACK_SCENARIOS } from './attackScenarios';

export type CycleResult = {
  cycle: number;
  scenarios_run: number;
  scenarios_passed: number;
  scenarios_failed: number;
  failures: {
    scenario: string;
    status: 'PASS' | 'FAIL' | 'UNKNOWN';
    violations: number;
    failed_invariants: string[];
  }[];
  determinism_verified: boolean;
};

export type AdversarialResult = {
  total_cycles: number;
  clean_cycles: number;
  final_status: 'FAILURE-RESISTANT' | 'NOT_READY';
  resilience_class: 'LOW' | 'MEDIUM' | 'HIGH';
  unresolved_vectors: string[];
  cycle_results: CycleResult[];
};

export class AdversarialEngine {
  private verifier: FormalVerifier;
  private cycleResults: CycleResult[] = [];
  private consecutiveCleanCycles = 0;
  private maxCycles = 10;

  constructor() {
    this.verifier = new FormalVerifier();
  }

  private runCycle(cycleNumber: number): CycleResult {
    const failures: CycleResult['failures'] = [];
    let passed = 0;
    let failed = 0;

    for (const scenario of ATTACK_SCENARIOS) {
      const result = this.verifier.executeScenario(scenario);

      const scenarioResult = {
        scenario: scenario.name,
        status: result.status,
        violations: result.total_violations,
        failed_invariants: result.failed_invariants.map((i) => i.invariant),
      };

      failures.push(scenarioResult);

      if (result.status === 'PASS') {
        passed++;
      } else {
        failed++;
      }
    }

    // Verify determinism
    const allActions = ATTACK_SCENARIOS.flatMap((s) => s.actions);
    const determinismVerified = this.verifier.verifyDeterminism(allActions);

    return {
      cycle: cycleNumber,
      scenarios_run: ATTACK_SCENARIOS.length,
      scenarios_passed: passed,
      scenarios_failed: failed,
      failures,
      determinism_verified: determinismVerified,
    };
  }

  execute(): AdversarialResult {
    let cycle = 1;

    while (cycle <= this.maxCycles && this.consecutiveCleanCycles < 3) {
      const result = this.runCycle(cycle);
      this.cycleResults.push(result);

      if (result.scenarios_failed === 0 && result.determinism_verified) {
        this.consecutiveCleanCycles++;
      } else {
        this.consecutiveCleanCycles = 0;
      }

      cycle++;
    }

    const totalCycles = this.cycleResults.length;
    const cleanCycles = this.consecutiveCleanCycles;
    const finalStatus = cleanCycles >= 3 ? 'FAILURE-RESISTANT' : 'NOT_READY';

    // Determine resilience class
    const totalScenarios = this.cycleResults.reduce((sum, r) => sum + r.scenarios_passed, 0);
    const totalRuns = this.cycleResults.reduce((sum, r) => sum + r.scenarios_run, 0);
    const passRate = totalRuns > 0 ? totalScenarios / totalRuns : 0;

    let resilienceClass: 'LOW' | 'MEDIUM' | 'HIGH';
    if (passRate >= 0.95 && finalStatus === 'FAILURE-RESISTANT') {
      resilienceClass = 'HIGH';
    } else if (passRate >= 0.80) {
      resilienceClass = 'MEDIUM';
    } else {
      resilienceClass = 'LOW';
    }

    // Collect unresolved attack vectors
    const unresolvedVectors: string[] = [];
    const lastCycle = this.cycleResults[this.cycleResults.length - 1];
    if (lastCycle) {
      for (const f of lastCycle.failures) {
        if (f.status === 'FAIL') {
          unresolvedVectors.push(f.scenario);
        }
      }
      if (!lastCycle.determinism_verified) {
        unresolvedVectors.push('DETERMINISM_VERIFICATION_FAILED');
      }
    }

    return {
      total_cycles: totalCycles,
      clean_cycles: cleanCycles,
      final_status: finalStatus,
      resilience_class: resilienceClass,
      unresolved_vectors: unresolvedVectors,
      cycle_results: this.cycleResults,
    };
  }
}

export const adversarialEngine = new AdversarialEngine();
export default adversarialEngine;
