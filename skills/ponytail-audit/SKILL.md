---
name: ponytail-audit
description: >
  Whole-repo audit for over-engineering. Like ponytail-review, but scans the
  entire codebase instead of a diff: a ranked list of what to delete, simplify,
  or replace with stdlib/native equivalents. Use when the user says "audit this
  codebase", "audit for over-engineering", "what can I delete from this repo",
  "find bloat", "ponytail-audit", or "/ponytail-audit". One-shot report, does
  not apply fixes.

  FireAI note: regulated paths (fireai/core/nfpa72_*, voltage_drop.py,
  battery_aging_derating.py, qomn_kernel.py, marine/, qomn_conduit/,
  facp_system/, fireai/mcp_server/, backend/api_keys.py,
  backend/security_middleware.py, backend/rbac.py, backend/routers/dwg.py,
  backend/routers/sync.py, backend/routers/analyze.py,
  templates/revit_addin/) are governed by docs/archive/agent.md Rule 17 and
  are EXCLUDED from audit — changes there require PE sign-off. See AGENTS.md.
---

ponytail-review, repo-wide. Scan the whole tree instead of a diff. Rank
findings biggest cut first.

## FireAI scope rule

SKIP any path in the regulated-path list in `AGENTS.md`. Cited NFPA/NEC/SOLAS
constants, deterministic engineering math, security boundaries, and hardware
calibration knobs are NOT over-engineering — they are safety margins and
regulatory compliance. The audit's job is the rest of the repo: skills,
tooling, mocks, docs, non-regulated utilities, dead adapters, speculative
abstractions in non-regulated code.

## Tags

Same as ponytail-review:

- `delete:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `stdlib:` hand-rolled thing the standard library ships. Name the function.
- `native:` dependency or code doing what the platform already does. Name the feature.
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller.
- `shrink:` same logic, fewer lines. Show the shorter form.

## Hunt

Deps the stdlib or platform already ships, single-implementation interfaces,
factories with one product, wrappers that only delegate, files exporting one
thing, dead flags and config, hand-rolled stdlib.

## Output

One line per finding, ranked: `<tag> <what to cut>. <replacement>. [path]`.
End with `net: -<N> lines, -<M> deps possible.` Nothing to cut: `Lean already. Ship.`

## Boundaries

Scope: over-engineering and complexity only. Correctness bugs, security holes,
and performance are explicitly out of scope. Route them to a normal review
pass. Lists findings, applies nothing. One-shot.
"stop ponytail-audit" or "normal mode" to revert.
