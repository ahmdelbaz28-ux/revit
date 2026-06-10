# System Integration Consistency Report

**Platform**: FireAI Digital Twin — Safety-Critical NFPA 72 Fire Alarm Engineering
**Date**: 2026-06-09
**Scope**: Architectural consistency only — no cosmetic issues reported
**Method**: Static analysis of all runtime registration paths, computation delegation chains, and authorization enforcement

---

## Executive Summary

The FireAI platform has **12 architectural inconsistencies** that create execution bypass risks. Three are CRITICAL — they can produce different safety outcomes between the workflow path and the canonical engine path. The remaining are HIGH — they create audit inconsistencies or leave safety-relevant modules disconnected from the runtime.

All findings share a root cause: **the system has two parallel computation paths** (LangGraph workflow vs pipeline/engine) that are not cross-validated, and multiple modules exist but are never wired into the runtime.

---

## 1. Modules Not Registered in Runtime System

### 1.1 QOMN Router — EXISTS, NOT MOUNTED [CRITICAL]

| Field | Value |
|-------|-------|
| File | `backend/routers/qomn.py` (788 lines) |
| Provides | REST API for QOMN kernel — detector spacing, voltage drop, battery, physics guards |
| Status | File exists but **no `include_router` call in `app.py`** |
| Rate-limit config | `/api/qomn` rate limit defined at `app.py:287` — but no router mounted to serve it |
| Import violations | Lines 91-93, 123, 519, 590, 667, 684 directly import from `fireai.core.qomn_kernel` bypassing `FireAIPluginAPI` |

**Risk**: The QOMN kernel's HTTP endpoints are unreachable. Any client calling `/api/qomn/*` receives 404. The kernel is accessible only via direct Python imports from `pipeline.py` and `device_placement.py` — these bypass the PluginAPI contract and the pipeline's contract validation (Stage 0).

**Remediation**: Either mount the router with `include_router(qomn.router, prefix="/api")` and refactor imports to go through `FireAIPluginAPI`, or remove the orphan file entirely.

---

### 1.2 FireAIPluginAPI — EXISTS, NOT USED BY ROUTERS [CRITICAL]

| Field | Value |
|-------|-------|
| File | `fireai/core/api_stability.py` (385 lines) |
| Provides | `FireAIPluginAPI` class, versioned dataclasses (`PluginRoom`, `PluginDetectorLayout`, `PluginBuildingResult`, `PluginCableRoute`), API_VERSION="29.0.0" |
| Status | Only self-referencing import exists (line 372: circular `from fireai.core.api_stability import check_api_compatibility` inside the same file) |
| Zero production imports | No router, service, or pipeline module imports `FireAIPluginAPI` |

**Risk**: The entire plugin stability contract — the module designed to prevent breaking changes — is an orphan. Routers import directly from `qomn_kernel.py`, `pipeline.py`, `models.py` etc., bypassing the versioned interface. Any internal refactor silently breaks the API.

**Remediation**: All routers must import from `FireAIPluginAPI` instead of direct kernel imports. The PluginAPI must be the sole entry point for any external-facing code.

---

### 1.3 TwinDB — EXISTS, NOT INTEGRATED INTO PIPELINE [HIGH]

| Field | Value |
|-------|-------|
| File | `fireai/core/twin_db.py` |
| Provides | `TwinSystemOfRecord`, `save_snapshot()`, `load_snapshot_bundle()`, `diff_snapshots()` — full undo/rollback capability |
| Status | All 9 references are internal (within `twin_db.py` itself, including docstring examples) |
| Zero production callers | No pipeline stage, router, or service calls snapshot/diff/restore |

**Risk**: The pipeline has NO undo mechanism. If a CAD operation corrupts the project state, there is no rollback path. TwinDB exists exactly for this purpose but is never invoked.

**Remediation**: Pipeline must call `save_snapshot()` before each mutation stage and provide `diff_snapshots()` for undo operations. This directly addresses responsibility #4 (CAD operations reversible and sandboxed).

---

### 1.4 Triple Audit Implementation — OVERLAPPING, NO SINGLE CANONICAL [HIGH]

| Module | Exported By | Production Callers |
|--------|------------|-------------------|
| `fireai/core/audit_log.py` | NOT in `__init__.py` | `safety_assurance.py:42` (imports `compute_hmac` only) |
| `fireai/core/audit_store.py` | `__init__.py` line 25 | `fireai_core.py:29,386,667` |
| `fireai/core/audit_trail.py` | `__init__.py` line 28 | `__init__.py` export only — zero production callers |
| `fireai/core/audit_blockchain_bridge.py` | `__init__.py` lines 21-23 | `fireai_core.py:386,667` |

**Risk**: Three audit modules with overlapping functionality (`audit_log`, `audit_store`, `audit_trail`) plus a fourth (`audit_blockchain_bridge`) for hash-chain storage. `audit_trail.py` is exported from `__init__.py` but has zero production callers — it's an orphan. `audit_log.py` is only used for `compute_hmac` in `safety_assurance.py`. `audit_store.py` and `audit_blockchain_bridge.py` are both called by `fireai_core.py` for different purposes. No single canonical audit path exists.

**Remediation**: Consolidate into one canonical audit module. `audit_blockchain_bridge.py` (HMAC-signed hash chain) should be the single audit mechanism. `audit_log.py` and `audit_trail.py` should be deprecated. `audit_store.py` should delegate to the bridge.

---

### 1.5 ComplianceEngine — EXISTS, NOT CALLED FROM PIPELINE [HIGH]

| Field | Value |
|-------|-------|
| File | `fireai/validation/compliance_engine.py` (216 lines) |
| Provides | 12 NFPA/IEC lambda-based compliance rules with clause mapping |
| Status | Zero production callers — only referenced in its own docstring example and test file |
| Overlap | `NFPA72ComplianceChecker` in `rules_engine/compliance_bridge.py` provides similar checks and IS wired into pipeline Stage 3.5 |

**Risk**: Two compliance engines exist with overlapping but NOT identical rule sets. `ComplianceEngine` checks IEC 60079 clauses (4.3, 60079-0:5) that `NFPA72ComplianceChecker` does NOT check. These IEC checks are orphaned — hazardous area classification is never validated in the pipeline.

**Remediation**: Merge `ComplianceEngine`'s IEC rules into `NFPA72ComplianceChecker` (or register them via the rules engine), then deprecate the lambda-based engine. IEC validation must run as a pipeline gate.

---

## 2. Parallel Implementations (Duplicate Logic)

### 2.1 Detector Count Calculation — DUAL PATHS [CRITICAL]

| Path | File | Lines | Formula |
|------|------|-------|---------|
| **Workflow** | `workflow_service.py` | 825-842 | `math.ceil(area_sqm / 9.0)` for smoke, `area_sqm / 20.0` for heat, `area_sqm / 15.0` for other |
| **Canonical Engine** | `pipeline.py` → `nfpa72_engine.py` → `qomn_kernel.py` | Stage 1-2 | Full NFPA 72 lookup: `get_detector_spacing(ceiling_height, ceiling_type, detector_type)` → `DensityOptimizer` or hex-grid fallback → `ExactCoverageEngine` verification |

**Divergence**: The workflow uses a **fixed 9.0m² coverage area** regardless of ceiling height. NFPA 72 Chapter 17 specifies spacing that varies by ceiling height (e.g., 9.1m at 3m flat ceiling, reduced to 6.4m for sloped ceilings). A room with 3.5m ceiling and sloped surface would get `ceil(area/9.0)` from the workflow but `ceil(area/6.4)` from the engine — fewer detectors from the workflow, which is a **safety deficit**.

**Risk**: Two analysis paths produce different detector counts for the same room. The workflow path has no `ceiling_height` or `ceiling_type` sensitivity. No cross-validation exists between them.

---

### 2.2 Coverage Threshold — DUAL THRESHOLDS [CRITICAL]

| Path | File | Threshold |
|------|------|-----------|
| **Workflow** | `workflow_service.py:887` | `coverage_pct >= 99.0` |
| **Canonical Engine** | `nfpa72_coverage.py:473,956`, `density_optimizer.py:339,1106`, `constraint_solver.py` | `>= 99.9%` |
| **ComplianceEngine** | `compliance_engine.py:80` | `>= 99.9%` |
| **Release Gate G3** | `release_gates.py:96` | `>= 99.0%` (minimum gate) |
| **Safety Assurance** | `safety_assurance.py:569` | `< 99.0` → not PROOF_VALID |

**Divergence**: The workflow declares compliance at `99.0%` while the canonical engine requires `99.9%`. A room at `99.5%` coverage would be declared `nfpa_compliant = True` by the workflow but FAIL the engine's coverage verification. The 0.9% gap represents a real safety difference — at `99.5%` coverage, up to 0.5% of the room area has NO fire detection.

**Additional defect**: The workflow assigns `coverage_pct = 100.0` (line 830) as a hardcoded constant for EVERY successfully analyzed room, regardless of actual coverage geometry. No coverage calculation is performed. The "overall coverage" (line 884-886) is then averaged from these fake `100.0` values.

**Risk**: The workflow can report 100% coverage for rooms where actual geometric coverage is <99.9%. This is a **false-positive safety declaration**.

---

### 2.3 NFPA Compliance Validation — THREE OVERLAPPING ENGINES [HIGH]

| Engine | File | Rule Source | Coverage |
|--------|------|-------------|----------|
| `ComplianceEngine` | `validation/compliance_engine.py` | 12 hardcoded lambda validators | NFPA 72 ch17, ch10, NFPA 92, NFPA 101, NEC, **IEC 60079** |
| `NFPA72ComplianceChecker` | `rules_engine/compliance_bridge.py` | Declarative rules from `nfpa72_rules.py` | NFPA 72 ch17, ch10, ch12, ch21 |
| Release Gates | `release_gates.py` | 8 hardcoded gate checks | Coverage, voltage, battery, wall distance, SLC, safety tier |

**Overlap**: Spacing, coverage, and voltage drop checks exist in all three. Each uses different thresholds and different logic.
**Gap**: IEC 60079 hazardous area rules exist ONLY in `ComplianceEngine` (orphan). NFPA 72 Chapter 12 (SLC fault isolator) and Chapter 21 (elevator shunt trip) exist ONLY in `NFPA72ComplianceChecker`.

---

### 2.4 Audit Trail — FOUR PARALLEL IMPLEMENTATIONS [HIGH]

See §1.4 above. Three audit modules (`audit_log`, `audit_store`, `audit_trail`) plus `audit_blockchain_bridge`. No canonical single path. Different modules record different events with different HMAC strategies.

---

### 2.5 Wall Thickness — HARDCODED vs PARSED [HIGH]

| Path | File | Value |
|------|------|-------|
| **Pipeline** | `pipeline.py:1450` | `WALL_THICKNESS_M = 0.2` (hardcoded "Project Spec default") |
| **DXF Parser** | `parsers/dwg_parser.py` | Wall thickness parsed from DXF entity properties |
| **Workflow** | `workflow_service.py` | No wall thickness consideration at all |

**Divergence**: The pipeline ignores parsed wall thickness and uses a hardcoded 0.2m. Different building types (commercial, industrial, residential) have different wall thicknesses (0.1m to 0.4m). A 0.4m wall building would have wall clearance zones that are 50% too small (0.6m vs 1.2m needed).

---

## 3. Direct Computation Bypassing Official Engine

### 3.1 Workflow `node_nfpa_analysis` — FULL ENGINE BYPASS [CRITICAL]

| Bypassed Stage | What the Workflow Does Instead |
|----------------|-------------------------------|
| Stage 0: Contract validation | No input validation |
| Stage 0.5: QOMN Physics Guards | No `guard_ceiling_height_m`, `guard_area_m2` — NaN/Inf inputs pass silently |
| Stage 1: NFPA spacing lookup | `area_sqm / 9.0` heuristic (no ceiling height/type sensitivity) |
| Stage 2: DensityOptimizer placement | No geometric placement — count-only |
| Stage 3: ExactCoverageEngine | `coverage_pct = 100.0` hardcoded (no geometric verification) |
| Stage 3.5: Rules engine compliance | No NFPA72ComplianceChecker evaluation |
| Stage 4: Safety tier classification | No tier assignment |
| Stage 5: 8 release gates | Zero gates checked |
| Stage 6: HMAC audit packaging | No tamper-evident audit chain |

**Total pipeline stages bypassed**: 9 out of 9.

The workflow uses `select_safe_detector_type` from `adapters/pdf_to_rooms_adapter` (not from the engine) plus `math.ceil` division. No computation hashes, no audit chain, no physics guards, no release gates.

---

### 3.2 QOMN Router Direct Imports — CONTRACT BYPASS [HIGH]

| Router File | Lines | Import |
|-------------|-------|--------|
| `qomn.py` | 91-93 | `QOMNKernel`, `PhysicsGuardError`, `ComputationError`, `ValidationError` directly from `qomn_kernel.py` |
| `qomn.py` | 123 | `QOMNKernel` instantiated directly |
| `qomn.py` | 519, 590 | `compute_smoke_detector_spacing`, `compute_heat_detector_spacing` directly |
| `qomn.py` | 667, 684 | `guard_area_m2`, `guard_efficiency` directly |

All imports bypass `FireAIPluginAPI` (the versioned stability contract). If the kernel's internal API changes, the router silently breaks with no version compatibility check.

Although the router is not mounted (§1.1), these direct imports represent an architectural violation: the router exists as a file that would bypass the PluginAPI if ever mounted.

---

### 3.3 Device Placement Direct Kernel Import [HIGH]

`fireai/core/device_placement.py:33-40` imports directly from `qomn_kernel.py`, bypassing both the pipeline contract validation (Stage 0) and the PluginAPI. Device placement is a safety-critical operation — detector positions determine whether fire is detected. No physics guard, no release gate, no audit chain.

---

### 3.4 Workflow Parser Imports — DIRECT PARSER COUPLING [MEDIUM]

| Workflow File | Lines | Import |
|---------------|-------|--------|
| `workflow_service.py` | 306 | `from parsers.geometry_extractor import GeometryExtractor` |
| `workflow_service.py` | 305, 324 | `from parsers.dwg_parser import DWGParser` |

AI workflow directly couples to parser internals instead of going through a parser gateway interface (per PluginAPI proposal P2).

---

## 4. Safety Overrides Without Authorization Chain

### 4.1 `force=True` on Detector Status Transitions [CRITICAL]

| Field | Detail |
|-------|--------|
| File | `fireai/core/digital_twin.py:994-1089` |
| Method | `Detector.update_status(detector_id, new_status, verified_by="", force=False)` |
| What it bypasses | `validate_status_transition()` — prevents illegal status transitions (e.g., COMMISSIONED → PLANNED which would remove fire protection) |
| Authorization required | **NONE** — `force=True` can be set by any caller with no `verified_by` requirement |
| Audit trail | Logs WARNING with "SAFETY CHECK BYPASSED" but records `verified_by` as empty string |
| API exposure | Search found zero `force=True` calls in router code. However, `force` is a parameter on a public method — any future router or service could invoke it |

**Risk**: A detector in `OK` status (providing fire protection) could be forced back to `PLANNED` (not providing protection) by any code path, with no authorization and only a WARNING log. In a life-safety system, this could suppress real fire alarms.

**Remediation**: When `force=True`, require `verified_by` to be non-empty AND match an authorized role (FPE, AHJ). Log as CRITICAL (not WARNING). Add to `OverrideRecord` audit chain.

---

### 4.2 `skip_human_review` — ENVIRONMENT GATE ONLY, NO AUTHORIZATION CHAIN [HIGH]

| Field | Detail |
|-------|--------|
| File | `backend/routers/workflow.py:139-186` |
| Guard | `FIREAI_ENV` check blocks in production (HTTP 403) |
| Authorization in dev/test | **NONE** — in development environment, any API caller can skip PE review with no identity record |
| Audit trail | Logs WARNING with no caller identity |

**Risk**: The environment gate is a deployment guard, not an authorization chain. In a dev/test environment, any automated client can bypass PE review with no record of who authorized it. The `OverrideRecord` class (which requires `authorizer_name` + `authorizer_role`) is never created when `skip_human_review=True`.

**Remediation**: Even in dev/test, require `authorizer_name` and `authorizer_role`. Create an `OverrideRecord` for every bypass. The environment gate should be a SUPPLEMENT to the authorization chain, not a replacement.

---

### 4.3 HazardOverrideVerifier — AUTOMATIC, NO HUMAN AUTHORIZATION [POSITIVE]

`hazard_override.py` overrides AI hazard classifications upward (never downward). This is a **conservative-only deterministic override** — no human authorization is needed because it can ONLY make classifications MORE severe, never less. This is architecturally correct for a life-safety system. The override IS logged with full context (original prediction, overridden classification, reason).

**No remediation needed** — this is the correct pattern for non-bypassable safety overrides.

---

### 4.4 OverrideRecord — DEFINED, NEVER CREATED IN PRODUCTION [HIGH]

| Field | Detail |
|-------|--------|
| File | `fireai/core/safety_assurance.py:454-479` |
| Class | `OverrideRecord(authorizer_name, authorizer_role, ...)` — frozen dataclass |
| Required fields | `authorizer_name: str`, `authorizer_role: OverrideRole`, `justification: str`, `timestamp: datetime` (auto) |
| NON_OVERRIDABLE set | 4 conditions can NEVER be overridden (proof_valid_false, coverage_below_90, audit_chain_broken, hmac_key_invalid) |
| Production usage | **ZERO** — only created in `test_safety_assurance.py` test cases |

**Risk**: The override authorization infrastructure exists but is never used. The `force=True` bypass (§4.1) and `skip_human_review` bypass (§4.2) both skip validation WITHOUT creating an `OverrideRecord`. The authorization chain is defined but not enforced.

**Remediation**: All bypass/override points must create an `OverrideRecord` with required fields. Missing `authorizer_name` or `authorizer_role` must raise, not default to empty.

---

## 5. Single Source of Truth Enforcement

### 5.1 Canonical Authority Mapping

| Domain | Canonical Source | Current Violation |
|--------|-----------------|-------------------|
| Detector spacing | `nfpa72_engine.py:get_detector_spacing()` | Workflow uses `area_sqm / 9.0` heuristic |
| Detector count | `qomn_kernel.py:compute_smoke_detector_spacing()` + `DensityOptimizer` | Workflow uses `math.ceil(area_sqm / X)` |
| Coverage percentage | `ExactCoverageEngine` or `nfpa72_coverage.py` | Workflow hardcodes `100.0` |
| Coverage threshold | `>= 99.9%` (engine standard) | Workflow uses `>= 99.0%` |
| Wall thickness | DXF parser (`dwg_parser.py`) | Pipeline hardcodes `0.2m` |
| Hazard classification | `hazard_override.py` (mandatory minimums) | ✅ Single source — no violation |
| Audit chain | `audit_blockchain_bridge.py:HashChainAuditStore` | Three parallel audit implementations |
| NFPA compliance | `rules_engine/compliance_bridge.py:NFPA72ComplianceChecker` | `ComplianceEngine` (lambda) orphaned with IEC rules |
| API contract | `api_stability.py:FireAIPluginAPI` | Routers import directly from kernel |

---

### 5.2 Required Consolidation Actions

| # | Action | Priority | Risk if Unfixed |
|---|--------|----------|-----------------|
| C-1 | Workflow must delegate all engineering computation to `pipeline.run_analysis()` | CRITICAL | Different detector counts → real safety deficit |
| C-2 | Workflow must use `>= 99.9%` coverage threshold (not `99.0%`) | CRITICAL | 0.9% unmonitored area = false-positive compliance |
| C-3 | Workflow must NOT hardcode `coverage_pct = 100.0` — must call coverage engine | CRITICAL | False-positive 100% coverage for rooms that aren't covered |
| C-4 | `force=True` must require `verified_by` + `OverrideRecord` creation | CRITICAL | Detector status transitions without authorization |
| H-1 | Audit trail: consolidate to `audit_blockchain_bridge.py` as sole canonical | HIGH | Audit inconsistency → tamper-evidence gap |
| H-2 | IEC rules from `ComplianceEngine` must merge into `NFPA72ComplianceChecker` | HIGH | Hazardous area classification never validated in pipeline |
| H-3 | TwinDB snapshot/restore must integrate into pipeline mutation stages | HIGH | No undo/rollback for CAD operations |
| H-4 | All routers must import from `FireAIPluginAPI`, not kernel internals | HIGH | Silent API breakage on internal refactors |
| H-5 | QOMN router: either mount via PluginAPI or remove orphan file | HIGH | Dead code with direct kernel imports |
| H-6 | `WALL_THICKNESS_M` must come from DXF parser, not hardcoded | HIGH | Wrong clearance zones for non-standard buildings |
| M-1 | Workflow parser coupling must go through gateway interface | MEDIUM | Parser refactor breaks workflow silently |

---

## 6. Mandatory Router Registration Validation

### 6.1 Current Router Registration Map

| Router File | Mounted? | Prefix |
|-------------|----------|--------|
| `health.py` | ✅ | `/api` |
| `projects.py` | ✅ | `/api` |
| `devices.py` | ✅ | `/api` |
| `connections.py` | ✅ | `/api` |
| `reports.py` | ✅ | `/api` |
| `exports.py` | ✅ | `/api` |
| `sync.py` | ✅ | `/api` |
| `elements.py` | ✅ | (no prefix) |
| `conflicts.py` | ✅ | (no prefix) |
| `connections_v2.py` | ✅ | (no prefix) |
| `environment.py` | ✅ | `/api` |
| `facp.py` | ✅ | `/api` |
| `workflow.py` | ✅ (conditional) | `/api` |
| `memory.py` | ✅ (conditional) | `/api` |
| **`qomn.py`** | ❌ NOT MOUNTED | Rate-limit config exists for `/api/qomn` but no `include_router` |

### 6.2 Registration Validation Requirement

**Proposal**: Add a startup validation hook in `app.py` that:

1. Scans `backend/routers/` for all `.py` files defining a `router` attribute
2. Checks each against the mounted router set
3. Logs CRITICAL for any unmounted router
4. Optionally refuses to start if an unmounted safety-relevant router is found

This prevents orphan routers from accumulating and ensures every API surface is intentionally registered.

---

## 7. Heuristic Calculation Inventory in Workflows

### 7.1 Complete Inventory of Workflow Heuristics

| # | Location | Heuristic | Canonical Engine Equivalent |
|---|----------|-----------|---------------------------|
| 1 | `workflow_service.py:825` | `math.ceil(area_sqm / 9.0)` — smoke detector count | `nfpa72_engine.get_detector_spacing()` → `DensityOptimizer.optimize()` |
| 2 | `workflow_service.py:827` | `math.ceil(area_sqm / 20.0)` — heat detector count | `nfpa72_engine.get_detector_spacing()` → `DensityOptimizer.optimize()` |
| 3 | `workflow_service.py:829` | `math.ceil(area_sqm / 15.0)` — "other" detector count | `nfpa72_engine.get_detector_spacing()` → `DensityOptimizer.optimize()` |
| 4 | `workflow_service.py:842` | `math.ceil(area_sqm / 20.0)` — kitchen heat count | Same as #2 |
| 5 | `workflow_service.py:830` | `coverage_pct = 100.0` — hardcoded "100%" | `ExactCoverageEngine.calculate()` or `nfpa72_coverage.py` |
| 6 | `workflow_service.py:884-886` | Average of per-room coverage values | Pipeline Stage 3 aggregate coverage |
| 7 | `workflow_service.py:887` | `nfpa_compliant = rooms_failing == 0 and coverage_pct >= 99.0` | Release Gate G3: `coverage >= 99.0` + Gate G8: `safety_tier >= PROOF_VALID` + all 8 gates |

**All 7 heuristics must be replaced with engine API calls.** The workflow should become a state machine orchestrator that delegates computation to the pipeline, not a parallel computation engine.

---

## 8. Safety Override Authorization Enforcement

### 8.1 Authorization Chain Specification

Every override/bypass in a life-safety system must satisfy:

```
OverrideRecord(
    authorizer_name: str,     # NOT empty — must be a real person
    authorizer_role: OverrideRole,  # FPE, AHJ, SENIOR_ENGINEER, QA_AUDITOR
    justification: str,       # NOT empty — reason for override
    timestamp: datetime,      # Auto-generated UTC
    target: str,              # What was overridden
    original_value: Any,      # What the system would have done
    overridden_value: Any,    # What was actually done
)
```

### 8.2 Current Authorization Gaps

| Override Point | Authorization Required | Audit Trail | OverrideRecord Created | API-Exposed |
|---------------|----------------------|-------------|----------------------|-------------|
| `force=True` (digital_twin.py:994) | ❌ None | ⚠️ WARNING only | ❌ No | ✅ Public method |
| `skip_human_review` (workflow.py:139) | ⚠️ Environment gate only | ⚠️ WARNING only | ❌ No | ✅ Query param |
| `hazard_override.py` (auto override) | ✅ Not needed (conservative-only) | ✅ Full log | ❌ No (but appropriate) | ❌ Internal only |
| `OverrideRecord` creation | ✅ Required fields defined | ✅ HMAC chain | ❌ Never created in prod | ❌ Not exposed |

### 8.3 Required Enforcement Actions

| # | Action | Impact |
|---|--------|--------|
| C-4a | `force=True` requires `verified_by` non-empty + `OverrideRecord` creation | Prevents unauthorized detector status changes |
| C-4b | `skip_human_review` requires `authorizer_name` + `authorizer_role` + `OverrideRecord` in dev/test | Creates accountability even in non-production |
| H-4a | All `OverrideRecord` creation must be HMAC-signed into the audit blockchain | Tamper-evident override history |
| H-4b | Override audit entries must appear in pipeline Stage 6 audit package | Override history accompanies every engineering output |

---

## 9. Cross-Validation Requirement

The root cause of CRITICAL findings is **two unverified parallel paths**. The architecture must enforce:

**Rule**: No engineering result may be returned to a client without passing through the full 6-stage pipeline (contract → physics guard → compute → verify → safety classify → release gate → audit).

The workflow may orchestrate state transitions, but the computation MUST be:

```
workflow node → calls pipeline.run_analysis(room) → returns pipeline result
```

NOT:

```
workflow node → math.ceil(area / 9.0) → returns heuristic result
```

---

## 10. Summary Risk Matrix

| ID | Finding | Risk | Type | Module Affected |
|----|---------|------|------|----------------|
| C-1 | Workflow bypasses entire 9-stage pipeline | CRITICAL | Computation bypass | `workflow_service.py` |
| C-2 | Workflow coverage threshold 99.0% vs canonical 99.9% | CRITICAL | Threshold divergence | `workflow_service.py:887` |
| C-3 | Workflow hardcodes coverage_pct = 100.0 | CRITICAL | False-positive | `workflow_service.py:830` |
| C-4 | `force=True` requires no authorization | CRITICAL | Auth bypass | `digital_twin.py:994` |
| H-1 | Four parallel audit implementations | HIGH | Audit inconsistency | `audit_log/store/trail/blockchain_bridge` |
| H-2 | IEC 60079 rules orphaned from pipeline | HIGH | Validation gap | `compliance_engine.py` |
| H-3 | TwinDB undo/rollback not integrated | HIGH | No rollback | `twin_db.py` |
| H-4 | FireAIPluginAPI unused by routers | HIGH | Contract bypass | `api_stability.py`, all routers |
| H-5 | QOMN router not mounted | HIGH | Dead code | `routers/qomn.py` |
| H-6 | Wall thickness hardcoded | HIGH | Domain error | `pipeline.py:1450` |
| M-1 | Workflow direct parser coupling | MEDIUM | Architecture violation | `workflow_service.py:305-324` |

**Total**: 4 CRITICAL, 6 HIGH, 1 MEDIUM. Zero findings are cosmetic.

---

## 11. Enforcement Priority Order

1. **C-1 + C-2 + C-3** — Replace workflow heuristics with pipeline delegation. This eliminates the three most dangerous bypasses in a single architectural change.
2. **C-4** — Add `OverrideRecord` requirement to `force=True`. Prevents unauthorized safety state changes.
3. **H-1** — Consolidate audit trail to `audit_blockchain_bridge.py`.
4. **H-2** — Merge IEC rules into pipeline compliance check.
5. **H-3** — Integrate TwinDB snapshots into pipeline stages.
6. **H-4 + H-5** — Route all external access through `FireAIPluginAPI`. Mount or remove QOMN router.
7. **H-6** — Parse wall thickness from DXF, remove hardcoded constant.
8. **M-1** — Introduce parser gateway interface.

---

*Report ends. All findings are architectural — no cosmetic issues included.*