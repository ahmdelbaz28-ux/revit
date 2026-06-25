/**
 * adversarialDebug.ts — Debug script for adversarial verification.
 * Run with: npx tsx lib/adversarialDebug.ts
 */

import { FormalVerifier } from './formalVerifier';
import { ATTACK_SCENARIOS } from './attackScenarios';
import { AdversarialEngine } from './adversarialEngine';

console.log('=== ADVERSARIAL VERIFICATION DEBUG ===\n');

// Run individual scenarios
for (const scenario of ATTACK_SCENARIOS) {
  const verifier = new FormalVerifier();
  const result = verifier.executeScenario(scenario);
  
  const status = result.status === 'PASS' ? '✅ PASS' : '❌ FAIL';
  console.log(`${status} ${scenario.name}`);
  
  if (result.status === 'FAIL') {
    console.log(`   Violations: ${result.total_violations}`);
    for (const v of result.failed_invariants) {
      console.log(`   - ${v.invariant}: ${v.violation}`);
    }
  }
}

console.log('\n=== FULL ADVERSARIAL CYCLE ===\n');

const engine = new AdversarialEngine();
const finalResult = engine.execute();

console.log(`Total cycles: ${finalResult.total_cycles}`);
console.log(`Clean cycles: ${finalResult.clean_cycles}`);
console.log(`Final status: ${finalResult.final_status}`);
console.log(`Resilience class: ${finalResult.resilience_class}`);
console.log(`Unresolved vectors: ${finalResult.unresolved_vectors.length}`);

for (const v of finalResult.unresolved_vectors) {
  console.log(`  - ${v}`);
}

console.log('\n=== CYCLE DETAILS ===\n');

for (const cycle of finalResult.cycle_results) {
  console.log(`Cycle ${cycle.cycle}: ${cycle.scenarios_passed}/${cycle.scenarios_run} passed, determinism: ${cycle.determinism_verified}`);
  
  for (const f of cycle.failures) {
    if (f.status === 'FAIL') {
      console.log(`  ❌ ${f.scenario} (${f.violations} violations)`);
      for (const inv of f.failed_invariants) {
        console.log(`     - ${inv}`);
      }
    }
  }
}
