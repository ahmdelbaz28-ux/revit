# Decision 004: AI is ADVISORY Only — Never Authoritative

## Date: 2026-05-29 (V69-V80)

## Context

FireAI integrates multiple AI providers (OpenAI, Gemini, Z.ai) for memory extraction, occupancy classification, and report narrative generation. The question was: should AI ever be allowed to make or override engineering decisions?

## Decision

**AI results are ALWAYS advisory. They NEVER override deterministic NFPA 72 calculations.**

This decision is enforced through multiple layers:

1. **Source tagging**: Every AI result carries `source="llm_suggestion"` or `source="memory"`, NEVER `source="nfpa_engine"`
2. **Fail-safe on AI failure**: If AI provider fails, calculations proceed with empty context — no blocking, no waiting
3. **PE review gate**: AI suggestions flow through a human review node before any design modification
4. **Audit trail**: Every AI interaction logged with timestamp, provider, model, prompt, and response
5. **Verification gates**: AI cannot bypass the 8-gate release verification system

## Rationale

1. **Life safety**: Wrong AI output in a fire protection system can kill people. A hallucinated coverage percentage can leave a building unprotected.
2. **Regulatory compliance**: NFPA 72 requires deterministic, verifiable engineering calculations. "The AI said so" is not an acceptable engineering justification.
3. **Liability**: Professional Engineers sign off on designs. They cannot delegate responsibility to an AI model.
4. **Precedent**: V12 Bug 1 (detector misclassification) and V13 (point-cloud coverage illusion) show that automated systems can produce life-threatening errors. AI models are even more prone to such errors.
5. **Proven pattern**: The existing MemoryService already implements this pattern successfully — memory is advisory context only.

## Implementation

The ConsensusEngine provides an additional safety layer:
- Critical calculations are cross-verified across multiple AI providers
- If providers disagree, the result is flagged for PE review
- Consensus does NOT mean "majority vote overrides engine" — it means "flag discrepancy for human review"

## Consequences

- AI adds value by providing context, catching patterns, and accelerating research
- AI never puts lives at risk by making autonomous engineering decisions
- The system remains compliant with NFPA 72 and professional engineering standards
- PE reviewers have full visibility into what came from AI vs. what came from deterministic calculations

## Cross-References

- [[architecture/ai-providers|AI Provider Architecture]]
- [[architecture/safety-philosophy|Safety-First Design Philosophy]]
- [[bug-fixes/V12-critical|V12 — Why Automated Errors Can Be Catastrophic]]
