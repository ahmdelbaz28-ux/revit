# Ponytail Debt Ledger — FireAI

This file is the canonical ledger of every `ponytail:` shortcut in the FireAI
repo. Generated and maintained by `/ponytail-debt` (see
`skills/ponytail-debt/SKILL.md`). Do not edit by hand unless you are resolving
an entry.

Format: `<file>:<line> — <what was simplified>. ceiling: <limit>. upgrade: <trigger>.`

Tags:
- `no-trigger` — the marker names no upgrade path; rot risk, review and resolve.
- `regulated` — the marker is in a regulated path; PE sign-off required to resolve.

## Active debt

### 2026-06-19 — Phase 2 cleanup

- `fireai/infrastructure/event_bus.py:428` — RedisEventBus + KafkaEventBus
  removed (356 LOC). ceiling: zero production callers; only `InMemoryEventBus`
  is used. upgrade: re-introduce via real integration tests if a production
  need arises — do NOT revive the dead wrappers as-is. The `EventBus` ABC is
  preserved so a future impl can subclass it.

### Deferred to Phase 3 (regulated-path or shared-test cleanup)

- `fireai/core/qomn_fire_v4_fail_loud.py:816-1140` — 8 adapter classes
  (`AamksAdapter`, `Evac4BimAdapter`, `OpenFireAdapter`,
  `EmergencyEvacuationAdapter`, `SafeGuardAiAdapter`, `DisasterEvacuationAdapter`,
  `EpytAdapter`, `SprayHydraulicAdapter`). ceiling: callers exist INSIDE the
  same file (`execute_hospital_scenario`, `execute_high_rise_scenario`, etc.)
  + 20+ tests in the same file. upgrade: this is a **regulated path** (the
  `fail_loud_v4` decorator and the file's `SafetyResult` / `SystemStatus`
  types are trust-boundary code). Do NOT delete. If the scenarios are
  themselves unused in production, isolate the question, get PE sign-off,
  and remove scenarios + adapters together as one unit.

- `fireai/core/blockchain_readiness_gate.py` (425 LOC) — filename says
  "blockchain" but the implementation is a SHA-256 hash chain / Merkle tree.
  ceiling: caller in `fireai/core/as_built_reconciliator.py:57` + full test
  suite in `tests/test_blockchain_readiness_gate.py`. upgrade: this is a
  **regulated path** (audit-trail trust boundary). Mechanical rename to
  `merkle_integrity_gate.py` is safe but must update: imports in
  `as_built_reconciliator.py`, test file, `fireai/DEPENDENCY_INDEX.md`,
  `fireai/CROSSREF_INDEX.md`, `COVERAGE_REPORT.md`, `docs/archive/agent.md`
  (prose only). Defer to Phase 3 with PE sign-off.

## Resolved debt

- 2026-06-19 Phase 3: `core/retry.py` deleted (361 LOC). The 4 retry-system
  tests in `tests/test_skill_integration.py` (lines 300-368) were removed;
  the file was renamed to `tests/test_skill_validator.py` to reflect its
  remaining content. `skills/README.md` updated to point users at `tenacity`
  directly. Ceiling: zero production callers. Upgrade path: any future retry
  need uses `from tenacity import retry, stop_after_attempt, wait_exponential`
  directly — no wrapper, no abstraction layer.

## Audit history

- 2026-06-19 Phase 2 initial pass: identified 4 candidate cleanups, executed 1
  (event_bus Redis+Kafka), deferred 3 (retry needs test-file split, fail_loud
  adapters are regulated, blockchain rename needs PE sign-off for the audit
  trail path). Net: -356 LOC, 0 behavior change, 101/101 tests pass.
- 2026-06-19 Phase 3: resolved the retry deferral. Deleted core/retry.py
  (361 LOC) + 3 retry tests, renamed test_skill_integration.py ->
  test_skill_validator.py, updated skills/README.md. Net: -361 LOC, 0
  behavior change. Remaining Phase 3 candidates (fail_loud adapters,
  blockchain rename) still require PE sign-off — see deferred entries above.
