# Pull Request: Adopt ponytail anti-overengineering ruleset — Phase 1 + 2 + 3

## Branch
`ponytail-phase-2-cleanup` → `main`

## Live links
- **Compare / open PR**: https://github.com/ahmdelbaz28-ux/revit/compare/main...ponytail-phase-2-cleanup
- **Branch**: https://github.com/ahmdelbaz28-ux/revit/tree/ponytail-phase-2-cleanup

## Summary

Adopts the [ponytail](https://github.com/DietrichGebert/ponytail) anti-overengineering ruleset (MIT-licensed) into FireAI with a **safety-critical hybrid**: regulated paths keep `docs/archive/agent.md` Rule 17 (NO HALF-SOLUTIONS); everything else follows the ponytail ladder (YAGNI → stdlib → native → installed dep → one-liner → minimum). Three commits, zero behavior change, **-787 LOC of dead code** removed across Phases 2 + 3.

| Phase | Commit | What | Net LOC |
|---|---|---|---|
| 1 | `0a75faae` | Foundation: `AGENTS.md` + 6 adapter files + 6 skills + 6 commands + 2 sync scripts | +17 new files |
| 2 | `14e75ed8` | Delete `RedisEventBus` + `KafkaEventBus` from `fireai/infrastructure/event_bus.py` (zero callers) | -350 LOC |
| 3 | `a0b7a7e4` | Delete `core/retry.py` (361-LOC dead wrapper around `tenacity`); rename test file | -437 LOC |

## Why ponytail?

`docs/archive/agent.md` has 21 mandatory rules but lives under `docs/archive/` — no AI agent auto-discovers it. The repo had **zero** AI-agent adapter files (`AGENTS.md`, `.cursor/rules/`, `.windsurf/`, `.clinerules/`, `.github/copilot-instructions.md`, `.kiro/steering/`, `.agents/rules/`). Every agent (Claude Code, Cursor, Copilot, Codex, Windsurf, Cline, Kiro) operated without the rules unless manually pointed at `agent.md`.

Ponytail is the most-cited minimal-ruleset for AI coding agents. Its benchmark (Haiku 4.5, 12 real FastAPI+React tasks, n=4) shows **-54% LOC, -22% tokens, -20% cost, -27% time, 100% safe** — versus a 7-word "YAGNI + one-liners" prompt that drops a safety guard 1-in-20.

## Safety design — the hybrid

**The conflict**: ponytail says "deletion over addition"; `agent.md` Rule 17 says "NO HALF-SOLUTIONS — root-cause fixes mandatory." Naive adoption would have an agent in `ultra` mode delete safety margins from `fireai/core/nfpa72_*.py` or collapse the 6 layers in `backend/api_keys.py` into one function.

**The resolution** (in `AGENTS.md` at repo root):

1. **Regulated paths** (NFPA/NEC/SOLAS/IEC constants, deterministic math, security boundaries, hardware calibration, audit trust boundaries) — Rule 17 applies. PE sign-off required (already enforced by `.github/workflows/regulatory-data-guard.yml`). ponytail `ultra` mode **refuses to fire** and logs every refusal to `worklog.md`.
2. **Everything else** (skills, tooling, mocks, docs, non-regulated utilities) — ponytail ladder applies. `lite`/`full` allowed; `ultra` allowed only on greenfield non-regulated subpackages.
3. **Conflict** → Rule 17 wins. Safety > Correctness > Verification > Reliability > Determinism > Maintainability > Traceability > Security > Performance > Developer Convenience.

The regulated-path list is enumerated explicitly in `AGENTS.md` and matches the safety-critical section of `.github/CODEOWNERS`.

## What's new (17 files)

### Always-on rules
- `AGENTS.md` (root, ~110 LOC) — canonical rule text
- `.cursor/rules/ponytail.mdc` (with `alwaysApply: true` frontmatter)
- `.windsurf/rules/ponytail.md`
- `.clinerules/ponytail.md`
- `.agents/rules/ponytail.md`
- `.github/copilot-instructions.md`
- `.kiro/steering/ponytail.md`

All 6 adapter bodies are byte-identical to `AGENTS.md` body. Drift is caught by `scripts/check-rule-copies.js` which asserts both byte-equality and 8 load-bearing invariant phrases (`input validation at trust boundaries`, `prevents data loss`, `security`, `accessibility`, `Lazy code without its check is unfinished`, `ONE runnable check`, `flimsier algorithm`, `naive heuristic`).

### Skills + commands
- 6 skills in `skills/`: `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain`, `ponytail-help`. The first 3 carry an explicit FireAI scope rule that skips regulated paths and logs every `ultra` refusal.
- 6 slash-command `.toml` files in `commands/`.

### Tooling
- `scripts/sync-agent-rules.sh` — regenerates the 6 adapters from `AGENTS.md`.
- `scripts/check-rule-copies.js` — CI verifier (exit 1 on drift).
- `ponytail-debt.md` — ledger of every `ponytail:` shortcut with ceiling + upgrade path. Updated by `/ponytail-debt` command.

## What's deleted (Phase 2 + 3)

### Phase 2: `fireai/infrastructure/event_bus.py` (-350 LOC)
`RedisEventBus` + `KafkaEventBus` classes (356 LOC) removed. Grep-verified zero callers outside the file itself. Only `InMemoryEventBus` was ever used. `EventBus` ABC preserved so a future impl can subclass it. A `ponytail:` comment at the deletion site documents the ceiling (zero callers) and upgrade path (re-introduce via real integration tests).

### Phase 3: `core/retry.py` (-361 LOC) + 3 retry tests
361-LOC thin wrapper around `tenacity` (already a project dependency). 7 retry decorators, 3 predefined configs, an `example_usage()` async function. Zero production callers (grep confirmed). The 3 retry-system tests in `test_skill_integration.py` were removed; the file was renamed to `test_skill_validator.py` (486 LOC, down from 562) since it now tests only the skill validator. `skills/README.md` updated to point users at `tenacity` directly.

## Verification

### Phase 1
```
node scripts/check-rule-copies.js
# → Rule copies match AGENTS.md; 8 rule invariants present in SKILL.md and AGENTS.md.
```

### Phase 2
```
python -c 'from fireai.infrastructure.event_bus import Event, EventBus, InMemoryEventBus, EventBusMiddleware, DeadLetterQueue, EventSchemaRegistry, RetryPolicy, DeadLetterRecord, register_default_schemas'
# → all imports OK

python -c 'from fireai.infrastructure.stream_processor import *'
# → OK (Event import preserved)

EventBus.__subclasses__()
# → ['InMemoryEventBus'] (was 3 before)

pytest tests/test_event_bus.py tests/test_workflow_service.py tests/test_qomn_integration.py
# → 101 passed, 1 skipped (pre-existing)
```

### Phase 3
```
pytest tests/test_skill_validator.py tests/test_event_bus.py tests/test_qomn_integration.py
# → 116 passed

grep -rn 'core\.retry' --include='*.py' --include='*.md' --include='*.toml' .
# → zero hits (excluding worklog.md, ponytail-debt.md, docs/archive/agent.md historical prose)
```

## What's NOT in this PR (deferred — see `ponytail-debt.md`)

Two regulated-path items remain deferred and require **PE sign-off**:

1. **`fireai/core/qomn_fire_v4_fail_loud.py`** — 8 adapter classes (~500 LOC). Callers exist INSIDE the same file (`execute_hospital_scenario` etc.) + 20+ tests. The file is regulated (the `fail_loud_v4` decorator + `SafetyResult` / `SystemStatus` are trust-boundary code). Defer to a dedicated engineering review.
2. **`fireai/core/blockchain_readiness_gate.py`** → `merkle_integrity_gate.py` rename (425 LOC, mechanical). Has a live caller in `fireai/core/as_built_reconciliator.py:57` + full test suite. The file is regulated (audit-trail trust boundary). PE sign-off required; the rename touches 6 files including `DEPENDENCY_INDEX.md`, `COVERAGE_REPORT.md`, and `docs/archive/agent.md`.

## Operator checklist before merge

- [ ] Review the 3 commits in order (Phase 1 → 2 → 3).
- [ ] Confirm the regulated-path list in `AGENTS.md` matches the safety-critical section of `.github/CODEOWNERS`.
- [ ] Run `node scripts/check-rule-copies.js` locally — should print PASS.
- [ ] Run `pytest tests/test_skill_validator.py tests/test_event_bus.py tests/test_qomn_integration.py` — should be 116 passed.
- [ ] Revoke both GitHub PATs visible in chat history (`github_pat_11CCHF4XA0...` already revoked; `ghp_48G4QTks...` still active). Rotate at https://github.com/settings/tokens.
- [ ] After merge: wire `scripts/check-rule-copies.js` into `.github/workflows/ci.yml` as a drift-prevention gate.

## Post-merge suggestions

1. **CI integration**: add a job that runs `node scripts/check-rule-copies.js` on every PR touching `AGENTS.md`, `skills/ponytail/SKILL.md`, or any adapter file.
2. **Try the commands**: in your next Claude Code / Codex / Copilot session in this repo, invoke `/ponytail-audit` on a non-regulated directory and review the delete-list. Then `/ponytail-review` on a recent diff.
3. **Monthly `/ponytail-debt` pass**: review `ponytail-debt.md` for `no-trigger` markers — those are the shortcuts most likely to rot.
4. **Address the 2 deferred items** in a separate engineering review with PE sign-off.
