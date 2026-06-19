# FireAI Agent Rules — Safety-Critical + Lazy-Senior Hybrid

This is a **safety-critical fire-protection-engineering system** (NFPA 72, NEC,
SOLAS, IEC 60092, ISO 15370, FSS, LR). Two rule sets coexist by path:

- **Regulated paths** (cited standards, deterministic engineering math, security
  boundaries, hardware calibration): governed by `docs/archive/agent.md` Rule 17
  (NO HALF-SOLUTIONS — root-cause fixes mandatory). Ponytail `ultra` is
  **forbidden** here.
- **Everything else** (skills, tooling, mocks, docs, non-regulated utilities):
  governed by the **ponytail ladder** below. `lite`/`full` allowed; `ultra`
  allowed only on greenfield non-regulated subpackages.

For the full 21 mandatory rules, the V12–V129 commit log, and the engineering
priority hierarchy, read `docs/archive/agent.md`.

## Regulated paths (Rule 17 applies — never `ultra`)

Any change to the files below requires PE sign-off (per
`.github/workflows/regulatory-data-guard.yml`) and root-cause analysis per
Rule 17:

- `fireai/core/qomn_kernel.py`, `fireai/core/nfpa72_*.py`,
  `fireai/core/voltage_drop.py`, `fireai/core/battery_aging_derating.py`,
  `fireai/core/device_placement.py`, `fireai/core/floor_orchestrator.py`,
  `fireai/core/floor_analyser.py`, `fireai/core/fireai_kernel_v30.py`,
  `fireai/core/hydraulic_solver.py`, `fireai/core/egress_calculator.py`,
  `fireai/core/stairwell_smoke_control.py`, `fireai/core/semi_cfast_engine.py`,
  `fireai/core/qomn_fire_v4_fail_loud.py` (the `fail_loud_v4` decorator only)
- `fireai/constants/nfpa72.py`, `fireai/constants/nec.py`
- `qomn_fire/core/constants.py`, `qomn_fire/engine/*`
- `qomn_conduit/` (NEC conduit fill — entire package)
- `marine/` (SOLAS/IEC/ISO/FSS/LR — entire module)
- `facp_system/` (FACP selection — entire package)
- `fireai/mcp_server/` (sanitized_handler, thread_safe_queue, revit_mcp_server)
- `backend/api_keys.py`, `backend/security_middleware.py`, `backend/rbac.py`,
  `backend/auth.py`
- `backend/routers/dwg.py` (file upload + path traversal),
  `backend/routers/sync.py` (WebSocket + HMAC), `backend/routers/analyze.py`
  (physics-guard detail sanitization)
- `templates/revit_addin/ThreadSafeQueueHandler.cs` (Revit thread-safety)

## Ponytail ladder (everything else)

Before writing any code, stop at the first rung that holds:

1. Does this need to be built at all? (YAGNI)
2. Does the standard library already do this? Use it.
3. Does a native platform feature cover it? Use it.
4. Does an already-installed dependency solve it? Use it.
5. Can this be one line? Make it one line.
6. Only then: write the minimum code that works.

Rules:

- No abstractions that weren't explicitly requested.
- No new dependency if it can be avoided.
- No boilerplate nobody asked for.
- Deletion over addition. Boring over clever. Fewest files possible.
- Question complex requests: "Do you actually need X, or does Y cover it?"
- Pick the edge-case-correct option when two stdlib approaches are the same
  size, lazy means less code, not the flimsier algorithm.
- Mark intentional simplifications with a `ponytail:` comment. If the shortcut
  has a known ceiling (global lock, O(n²) scan, naive heuristic), the comment
  names the ceiling and the upgrade path.

Not lazy about: input validation at trust boundaries, error handling that
prevents data loss, security, accessibility, the calibration real hardware
needs (the platform is never the spec ideal, a clock drifts, a sensor reads
off), anything explicitly requested. Lazy code without its check is unfinished: non-trivial logic leaves ONE runnable check behind, the smallest
thing that fails if the logic breaks (an assert-based demo/self-check or one
small test file; no frameworks, no fixtures). Trivial one-liners need no test.

## Commands

| Command | What it does |
|---------|--------------|
| `/ponytail [lite \| full \| ultra \| off]` | Set the intensity for non-regulated code only. |
| `/ponytail-review` | Review the current diff for over-engineering (non-regulated files). |
| `/ponytail-audit` | Audit the whole repo for over-engineering (skips regulated paths). |
| `/ponytail-debt` | Harvest `ponytail:` comments into a tracked ledger. |
| `/ponytail-gain` | Show the published benchmark scoreboard. |
| `/ponytail-help` | Quick reference. |

## Resolution order

1. If a path is in the regulated list above → Rule 17 (`docs/archive/agent.md`).
2. Else → ponytail ladder (this file + `skills/ponytail/SKILL.md`).
3. Conflict? Rule 17 wins. Safety > Correctness > Verification > Reliability >
   Determinism > Maintainability > Traceability > Security > Performance >
   Developer Convenience.

## Mode default

`full`. Change with `PONYTAIL_DEFAULT_MODE` env var (`lite`/`full`/`ultra`/`off`)
or `~/.config/ponytail/config.json` (`{"defaultMode": "lite"}`). **`ultra`
refuses to fire on regulated paths** — it must be confirmed per session and
logs every refusal to the worklog.

---

(Yes, this file also applies to agents working on the revit repo itself.
Especially to them.)
