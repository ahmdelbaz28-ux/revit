# ADR-001: Code Authority as Single Source of Truth

## Status: Accepted

## Date: 2026-05-14

## Context
We need authoritative source for all NFPA/NEC numeric constants to ensure auditability and immutability.

## Decision
We will use CodeAuthority as the single source of truth for all fire safety constants. No hardcoded values anywhere else.

## Consequences
- ✅ All constants are versioned with jurisdiction/edition
- ✅ UPDATE/DELETE blocked at database level
- ✅ Audit trail for every constant addition
- ⚠️ Migration required for existing hardcoded constants

---

# ADR-002: Parser Confidence Gate

## Status: Accepted

## Date: 2026-05-14

## Context
The parser silently mis-reads input. We need a gate to reject or flag bad input before compliance calculations.

## Decision
ParserConfidence with 8 signals and hard-refuse thresholds:
- scale_present < 0.5 → REFUSE immediately
- coordinate_sanity < 0.3 → REFUSE immediately

## Consequences
- ✅ No calculations on bad input
- ⚠️ Some drawings may be rejected (expected)
- ⚠️ Need to maintain signal computation

---

# ADR-003: Override Token System

## Status: Accepted

## Date: 2026-05-14

## Context
PE overrides must be cryptographically secure, traceable, and revokable.

## Decision
SecureTokenGenerator + OverrideRevocationManager:
- 256-bit entropy tokens
- Expiration dates
- Revocation with reason logged to audit

## Consequences
- ✅ Unhackable tokens
- ✅ Complete audit trail
- ⚠️ Need key management

---

# ADR-004: No Automatic Learning (Human Review Required)

## Status: Accepted

## Date: 2026-05-14

## Context
Self-learning systems can learn incorrect patterns. Fire safety requires FPE verification.

## Decision
Patterns submitted to human review (FPE). No automatic improvement from any file.

## Consequences
- ✅ No incorrect patterns learned
- ⚠️ Slower improvement cycle
- ⚠️ Requires human workflow

---

# ADR-005: DB Pool for Thread Safety

## Status: Accepted

## Date: 2026-05-14

## Context
Concurrent access to SQLite requires connection pooling to prevent deadlocks.

## Decision
DatabasePool with 5 connections, context manager pattern.

## Consequences
- ✅ No deadlocks
- ⚠️ Pool size tuning may be needed

---

# ADR-006: Limited Signal Computation (Known Gap)

## Status: Documented Limitation

## Date: 2026-05-14

## Context
Parser Confidence has 8 signals defined, but only 4 are computed in pipeline.

## Decision
Document gap, expand hard-refuse to use computed signals only.

## Computed Signals (4/8):
- ✅ scale_present (checked)
- ✅ vector_purity (checked)
- ✅ coordinate_sanity (checked)
- ✅ ocr_confidence (computed but not checked)

## Missing Signals (4/8):
- ❌ legend_coverage
- ❌ polygon_closure
- ❌ layer_hygiene (DXF only)
- ❌ title_block_completeness

## Consequences
- ⚠️ Gate runs with 50% data
- ⚠️ May reject valid files or accept invalid
- ⚠️ Need Phase 2 implementation

---

This file: ADRs for V8 major architectural decisions.

See also: [ARCHITECTURE.md](../ARCHITECTURE.md)