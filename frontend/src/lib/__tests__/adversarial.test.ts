/**
 * adversarial.test.ts — Adversarial verification tests.
 *
 * Executes attack scenarios and verifies system invariants.
 * System is valid only if all scenarios pass deterministically.
 */

import { describe, it, expect } from 'vitest';
import { FormalVerifier } from '../formalVerifier';
import { ATTACK_SCENARIOS } from '../attackScenarios';
import { AdversarialEngine } from '../adversarialEngine';

describe('Adversarial Verification', () => {
  describe('Individual Attack Scenarios', () => {
    for (const scenario of ATTACK_SCENARIOS) {
      it(scenario.name, () => {
        const verifier = new FormalVerifier();
        const result = verifier.executeScenario(scenario);

        expect(result.status).toBe('PASS');
        expect(result.total_violations).toBe(0);
        expect(result.failed_invariants).toHaveLength(0);
      });
    }
  });

  describe('Determinism Verification', () => {
    it('same action sequence produces same final state', () => {
      const verifier = new FormalVerifier();
      const allActions = ATTACK_SCENARIOS.flatMap((s) => s.actions);
      const isDeterministic = verifier.verifyDeterminism(allActions);

      expect(isDeterministic).toBe(true);
    });
  });

  describe('Full Adversarial Cycle', () => {
    it('all scenarios pass in single cycle', () => {
      const engine = new AdversarialEngine();
      const result = engine.execute();

      expect(result.final_status).toBe('FAILURE-RESISTANT');
      expect(result.resilience_class).toBe('HIGH');
      expect(result.unresolved_vectors).toHaveLength(0);
    });
  });
});
