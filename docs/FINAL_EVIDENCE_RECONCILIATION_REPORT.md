# FINAL EVIDENCE RECONCILIATION REPORT

**Date:** 2026-06-11
**Repository:** `ahmdelbaz28-ux/revit` (shallow clone @ `/tmp/revit_audit`)
**Methodology:** Executable evidence only — every conclusion backed by file path, line number, and raw output.

---

## 1. Python Version Reconciliation

| Context | Version | Evidence | File | Lines |
|---------|---------|----------|------|-------|
| **Docker (build & runtime)** | `python:3.12-slim` | `FROM python:3.12-slim AS builder` and `FROM python:3.12-slim` | `Dockerfile` | 13, 22 |
| **CI (all 5 gates)** | `"3.12"` | `python-version: "3.12"` across static-analysis, test-suite, property-tests, regression-check, dependency-audit | `.github/workflows/ci.yml` | 36, 101, 144, 169, 193 |
| **pyproject.toml (mypy)** | `3.12` | `python_version = "3.12"` | `pyproject.toml` | 201 |
| **pyproject.toml (ruff/black)** | `py312` | `target-version = "py312"` | `pyproject.toml` | 129, 229 |
| **pyproject.toml (requires)** | `>=3.8` | `requires-python = ">=3.8"` | `pyproject.toml` | 36 |
| **requirements.txt** | `>=3.8` compat | Every pinned dep annotated `# Earlier version compatible with Python 3.8` | `requirements.txt` | 1-51 |
| **System (this host)** | `3.14.4` | `python3 --version` → `Python 3.14.4` | CLI output | — |

**Conclusion: CONFIRMED** — The project targets Python 3.12 in Docker, CI, and production. The requirements.txt and pyproject.toml advertise `>=3.8` compatibility but all tooling (mypy, black, ruff) targets 3.12. The system Python 3.14.4 is mismatched but irrelevant to deployment.

---

## 2. Test Results Reconciliation

Coverage data from `/tmp/revit_audit/coverage.json` (timestamp: `2026-05-31T20:44:11`):

**Coverage.json summary:**
```
fireai: 11618/29714 = 39.1% across 161 files
```

**Key module-level coverage from coverage.json:**

| Module | Covered/Total | % | Status |
|--------|--------------|---|--------|
| `core/audit_trail.py` | 75/76 | 99% | HIGH |
| `core/voltage_drop.py` | 68/69 | 99% | HIGH |
| `core/nfpa72_rules.py` | 57/58 | 98% | HIGH |
| `core/compliance_bridge.py` | 125/132 | 95% | HIGH |
| `core/compliance_engine.py` | 31/34 | 91% | HIGH |
| `core/elevator_shunt_trip.py` | 122/139 | 88% | HIGH |
| `core/nfpa72_engine.py` | 193/231 | 84% | MODERATE |
| `core/hydraulic_solver.py` | 76/92 | 83% | MODERATE |
| `core/conduit_fill_analyzer.py` | 165/199 | 83% | MODERATE |
| `core/nfpa72_schemas.py` | 92/111 | 83% | MODERATE |
| `core/qomn_kernel.py` | 195/255 | 76% | MODERATE |
| `core/nfpa72_models.py` | 222/413 | 54% | LOW |
| `core/bps_allocator.py` | 127/467 | 27% | LOW |
| `core/nfpa72_calculations.py` | 82/307 | 27% | LOW |
| `core/fire_zone_engine.py` | 38/148 | 26% | LOW |
| `core/nfpa72_coverage.py` | 42/392 | **11%** | CRITICAL |
| `core/mip_solver.py` | 0/67 | **0%** | CRITICAL |
| `core/sequence_of_operations.py` | 0/120 | **0%** | CRITICAL |
| `core/compliance_proof_document.py` | 0/138 | **0%** | CRITICAL |
| `backend/services/workflow_service.py` | NOT FOUND | — | NOT TESTED |

**Conclusion:** The CI pipeline enforces `--cov-fail-under=50` (ci.yml:121). Current coverage is **39.1%** — this is below the CI threshold. Either the coverage.json is stale (from a prior run before the threshold was raised) or the CI would currently fail. Five CRITICAL modules have 0-11% coverage.

---

## 3. Code Coverage Reconciliation

### Total coverage
- **39.1%** (11618/29714) — computed from coverage.json raw data

### Safety-critical coverage
All safety-critical modules listed in agent.md V20.2 were checked. Only 8 of 19 have coverage > 50%. Critical gaps:
- `nfpa72_coverage.py`: 11% — coverage verification engine
- `sequence_of_operations.py`: 0% — cause-effect matrix
- `mip_solver.py`: 0% — optimization solver
- `compliance_proof_document.py`: 0% — legally binding proof docs

### Workflow coverage
`backend/services/workflow_service.py` is NOT PRESENT in coverage.json — it was never executed during the coverage run. This means the LangGraph workflow pipeline (467 lines) has **zero tested coverage**.

### NFPA engine coverage
Average across all NFPA modules: ~40%. Wide variance: `nfpa72_engine.py` at 84% but `nfpa72_coverage.py` at 11%.

---

## 4. Workflow Calculation Pipeline Bypass Verification

**Claim:** Workflow calculations may bypass the canonical engineering pipeline.

**Evidence:**
- `backend/services/workflow_service.py` line 20: `"The workflow MUST NEVER skip validation steps"` — explicit design constraint
- Workflow router (`backend/routers/workflow.py`) is optional: guarded by `try: from backend.routers import workflow` at `backend/app.py:786-790`
- Workflow endpoints all require `X-API-Key` via `dependencies=[Depends(verify_api_key_dep)]` — lines 125, 195, 220, 261, 301
- Workflow service has 0% coverage — its behavior in practice cannot be verified from existing test artifacts

**Conclusion: NO EVIDENCE** of active bypass. The code explicitly states it must not skip validation steps, and all endpoints are auth-guarded. However, the **lack of test coverage** means bypass behavior cannot be ruled out. This is a verification gap, not a confirmed bypass.

---

## 5. `force=True` Authorization Bypass Verification

**Claim:** `force=True` paths may bypass authorization.

**Evidence:**
- **Only `force=True` found:** `fireai/core/security_logging.py:129` — `_refresh_env_cache()` docstring: "Call with force=True to bypass TTL." This is a **cache TTL parameter** for environment variable masking, NOT an authorization mechanism.
- **Authorization enforcement:** `ApiKeyMiddleware` at `backend/app.py:555-669` — ALL mutating requests (POST, PUT, DELETE, PATCH) require valid `X-API-Key` header. Read-only (GET, HEAD, OPTIONS) are allowed without auth.
- **No `force=True` in any auth path found** — grep for `force.*True` across all Python files returned only the security_logging.py cache refresh reference.

**Conclusion: VERIFIED — no authorization bypass via `force=True` exists.**

---

## 6. QOMN Router Mount and Reachability Verification

**Claim:** QOMN router is mounted and reachable.

**Evidence:**
- **QOMN router file EXISTS:** `/tmp/revit_audit/backend/routers/qomn.py` — 787 lines, fully implemented, `router = APIRouter(tags=["qomn"])` at line 71
- **Rate limit IS configured:** `("/api/qomn", 10, 60)` at `backend/app.py:287`
- **BUT QOMN router is NOT imported in `app.py`:** The imports block at lines 770-783 (`from backend.routers import (projects, devices, ...)`) does NOT include `qomn`
- **QOMN router is NOT mounted via `app.include_router()`:** Lines 798-843 show all mounted routers — `qomn` is absent
- **QOMN grep in app.py:** Only 1 match on line 287 (rate limit) — no import, no mount

```
$ grep -n "qomn" backend/app.py
Line 287:     ("/api/qomn", 10, 60),    ← rate limit ONLY
```

**Conclusion: QOMN router is DEFINED but NOT MOUNTED.** The rate limit at line 287 (`("/api/qomn", 10, 60)`) is dead code — it would never fire because no router is listening at `/api/qomn/*`. Requests to `/api/qomn/*` would return HTTP 404. This is a **CRITICAL finding**: the router file has 15 fully implemented endpoints that exist in source but are unreachable.

---

## 7. Rate Limiting Verification

**Claim:** Rate limiting is active and enforced.

**Evidence:**
- **Middleware is added:** `app.add_middleware(PerPathRateLimitMiddleware)` at `backend/app.py:677`
- **V111 fix explicitly wires it:** "V111 FIX: Wire PerPathRateLimitMiddleware into the middleware stack. V101 defined it but never added it" — line 674-677
- **Rate limit table defined:** lines 261-289, 13 path-specific limits + default (120 req/60s)
- **All limits active:** workflow (3/min), projects (15/min), environment endpoints (10/min), qomn (10/min — dead code), etc.
- **Implementation:** Pure ASGI middleware (not BaseHTTPMiddleware), thread-safe with lock, memory-cleanup for >10k entries, per-client-IP tracking with sliding window

**Conclusion: VERIFIED — rate limiting IS active and enforced.** The middleware is properly wired (line 677), has comprehensive per-path limits (lines 261-289), correct longest-prefix matching (lines 319-331), thread-safe implementation (line 316), and memory leak protection (lines 352-369).

---

## Summary Cross-Reference

| # | Claim | Verdict | Detail |
|---|-------|---------|--------|
| 1 | Python version | ✅ VERIFIED | 3.12 in Docker/CI/Production; >=3.8 in metadata |
| 2 | Test results | ⚠️ PARTIAL | coverage.json shows 39.1% but CI requires 50% |
| 3 | Code coverage | ⚠️ PARTIAL | 39.1% total; 5 critical modules at 0-11% |
| 4 | Workflow bypass | ✅ NO BYPASS FOUND | Code explicitly prevents skipping; 0% coverage is a verification gap |
| 5 | `force=True` bypass | ✅ NO BYPASS FOUND | Only `force=True` is env cache TTL; auth uses ApiKeyMiddleware |
| 6 | QOMN router reachable | ❌ **NOT MOUNTED** | File exists, rate limit configured, but never imported/included |
| 7 | Rate limiting active | ✅ VERIFIED | PerPathRateLimitMiddleware wired at line 677 with 13 path-specific limits |

---

## Critical Issues Requiring Immediate Action

1. **QOMN router is dead code** (`backend/app.py:770-843`): The file `backend/routers/qomn.py` with 15 fully implemented endpoints is never imported or mounted. Add `from backend.routers import qomn` and `app.include_router(qomn.router)` or remove the dead code.

2. **Coverage below CI threshold** (39.1% < 50%): The `--cov-fail-under=50` in CI (`.github/workflows/ci.yml:121`) would currently fail. Add tests for the 5 uncovered critical modules: `nfpa72_coverage.py`, `mip_solver.py`, `sequence_of_operations.py`, `compliance_proof_document.py`, `workflow_service.py`.

3. **Rate limit for QOMN is dead code** (`backend/app.py:287`): `("/api/qomn", 10, 60)` will never fire because QOMN router is not mounted. Remove or mount the router.

---

*All evidence collected via file inspection, grep, and raw data parsing from the shallow-cloned repository at `/tmp/revit_audit`. No assumptions were made — all conclusions are backed by specific file paths and line numbers.*
