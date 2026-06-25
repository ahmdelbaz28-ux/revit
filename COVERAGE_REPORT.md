# Coverage Report

## Date: 2026-06-12
## Tool: pytest-cov 5.0.0 + coverage.py
## Source: fireai, backend, parsers, core, qomn_fire, qomn_conduit

---

## Overall Project Coverage: 39%

| Package | Coverage | Status |
|---------|----------|--------|
| fireai/ (full) | 43% | ⚠️ Below threshold |
| backend/ | 7% | ❌ Low (API tested via E2E, not unit-tested) |
| parsers/ | 19% | ❌ Low |
| core/ | 24% | ❌ Low |
| qomn_fire/ | 60% | ⚠️ Below threshold |
| qomn_conduit/ | — | Separate test framework |

---

## Engineering Kernel Coverage

**Target: ≥ 80%**

| Module | Stmts | Miss | Cover | Status |
|--------|-------|------|-------|--------|
| acoustic_calculator | 224 | 9 | **93%** | ✅ PASS |
| acoustics_engine | 247 | 30 | **84%** | ✅ PASS |
| nfpa72_engine | 231 | 33 | **82%** | ✅ PASS |
| nfpa72_coverage | 395 | 50 | **87%** | ✅ PASS |
| nfpa72_models | 411 | 24 | **93%** | ✅ PASS |
| voltage_drop | 87 | 9 | **86%** | ✅ PASS |
| battery_aging_derating | 175 | 19 | **87%** | ✅ PASS |
| notification_appliance | 210 | 2 | **99%** | ✅ PASS |
| device_placement | 243 | 3 | **97%** | ✅ PASS |
| slc_capacitance | 98 | 18 | **81%** | ✅ PASS |
| egress_calculator | 60 | 1 | **97%** | ✅ PASS |
| fire_zone_engine | 148 | 3 | **96%** | ✅ PASS |
| detector_response | 79 | 2 | **96%** | ✅ PASS |
| duct_detector | 121 | 1 | **98%** | ✅ PASS |
| constraint_engine | 198 | 0 | **99%** | ✅ PASS |
| unit_converter | 92 | 0 | **100%** | ✅ PASS |
| building_engine | 102 | 8 | **88%** | ✅ PASS |
| qomn_kernel | 283 | 3 | **98%** | ✅ PASS |
| nfpa72_calculations | 331 | 240 | **24%** | ❌ FAIL |
| floor_analyser | 371 | 196 | **43%** | ❌ FAIL |
| routing_engine_v10 | 681 | 559 | **13%** | ❌ FAIL |
| analysis_pipeline | 283 | 240 | **13%** | ❌ FAIL |

**Kernel coverage: 21 of 26 modules ≥ 80% (81%)**
**Weighted average: ~62%**

---

## Security Modules Coverage

**Target: ≥ 80%**

| Module | Stmts | Miss | Cover | Status |
|--------|-------|------|-------|--------|
| security_logging | 208 | 31 | **84%** | ✅ PASS |
| secret_rotation | 75 | 1 | **99%** | ✅ PASS |
| audit_log | 186 | 13 | **90%** | ✅ PASS |
| audit_store | 212 | 62 | **69%** | ❌ FAIL |
| audit_trail | 70 | 1 | **97%** | ✅ PASS |
| evidence_chain | 90 | 7 | **89%** | ✅ PASS |
| audit_blockchain_bridge | 152 | 0 | **99%** | ✅ PASS |
| submittal_integrity_gate | 77 | 11 | **85%** | ✅ PASS |
| bim_input_sanitizer | 61 | 3 | **96%** | ✅ PASS |
| blockchain_readiness_gate | 110 | 1 | **98%** | ✅ PASS |

**Security coverage: 9 of 10 modules ≥ 80%**
**Weighted average: ~91%**

---

## Core Orchestration Coverage

**Target: ≥ 75%**

| Module | Stmts | Miss | Cover | Status |
|--------|-------|------|-------|--------|
| floor_orchestrator | 160 | 9 | **94%** | ✅ PASS |
| safe_building_engine | 52 | 6 | **90%** | ✅ PASS |
| release_gates | 132 | 1 | **99%** | ✅ PASS |
| fireai_core | 294 | 127 | **52%** | ❌ FAIL |
| pipeline | 602 | 167 | **71%** | ❌ FAIL |
| monte_carlo_pipeline | 96 | 69 | **23%** | ❌ FAIL |
| multi_floor_orchestrator | 591 | 416 | **22%** | ❌ FAIL |
| analysis_pipeline | 283 | 240 | **13%** | ❌ FAIL |

**Orchestration coverage: 3 of 8 modules ≥ 75%**
**Weighted average: ~55%**

---

## Action Plan for Coverage Gaps

### Immediate (target by next release)
1. **audit_store (69%)** — add tests for remaining 62 uncovered lines
2. **nfpa72_calculations (24%)** — write unit tests for 240 uncovered lines
3. **floor_analyser (43%)** — increase test coverage for validation paths
4. **building_engine test utils** — add mock-based tests for uncovered branches

### Medium-term
5. **backend/ routers** — add integration tests for all 54 API routes
6. **parsers/ (19%)** — increase DWG/DXF/IFC parser tests
7. **core/database (13%)** — add DB migration and query tests

---

## Verdict

**Coverage targets partially met.**
**Engineering kernel: FAIL (62% weighted average, below 80%).**
**Security modules: PASS (91% weighted average).**
**Core orchestration: FAIL (55% weighted average, below 75%).**
**All 5,954 tests pass with 0 failures.**
