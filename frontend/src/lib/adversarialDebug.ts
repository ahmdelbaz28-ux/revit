/**
 * adversarialDebug.ts — Debug script for adversarial verification.
 *
 * V194 REFACTOR: Previously this file executed top-level code on import,
 * which meant that if it was ever accidentally bundled, it would spam the
 * console with 20+ console.log calls in production. Now it's wrapped in
 * an async main() function that only runs when explicitly invoked:
 *
 *   npx tsx lib/adversarialDebug.ts
 *
 * Or programmatically:
 *   import { runAdversarialDebug } from './adversarialDebug';
 *   runAdversarialDebug();
 */

import { FormalVerifier } from './formalVerifier';
import { ATTACK_SCENARIOS } from './attackScenarios';
import { AdversarialEngine } from './adversarialEngine';

/**
 * Run the adversarial verification debug suite.
 * Prints results to console. Intended for development/debugging only.
 */
export async function runAdversarialDebug(): Promise<void> {
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
		console.log(
			`Cycle ${cycle.cycle}: ${cycle.scenarios_passed}/${cycle.scenarios_run} passed, determinism: ${cycle.determinism_verified}`,
		);

		for (const f of cycle.failures) {
			if (f.status === 'FAIL') {
				console.log(`  ❌ ${f.scenario} (${f.violations} violations)`);
				for (const inv of f.failed_invariants) {
					console.log(`     - ${inv}`);
				}
			}
		}
	}
}

// Auto-run only when executed directly via `npx tsx lib/adversarialDebug.ts`
// (not when imported as a module). This prevents accidental production execution.
// Using import.meta.url to detect direct execution (ESM pattern).
if (
	typeof process !== 'undefined' &&
	process.argv[1] &&
	import.meta.url === new URL(`file://${process.argv[1]}`).href
) {
	runAdversarialDebug().catch((err) => {
		console.error('Adversarial debug failed:', err);
		process.exit(1);
	});
}
