# Local Static Analysis Report — Post-NOSONAR-Removal Verification

**Timestamp:** 2026-07-08T09:10:40.852255+00:00
**Tools:** ruff ruff 0.15.20, bandit 1.9.4

> ⚠️ **Note**: This is a LOCAL analysis using ruff + bandit as a proxy for
> SonarCloud (SONAR_TOKEN was not available). It catches the same categories
> of issues (bugs, code smells, security) but is NOT a 1:1 replacement.
> For the full SonarCloud report, follow OPS_RUNBOOK.md Task 2.

## Verdict

**✅ PASS: No real bugs in critical files, 0 bugs in production, 0 HIGH security issues**

## 1. Critical Files Analysis (F-series = real bugs)

| File | Total Issues | Real Bugs (F-series) | Status |
|------|-------------|---------------------|--------|
| `fireai/core/fireai_kernel_v30.py` | 18 | 0 | ✅ CLEAN |
| `fireai/core/scenario_engine.py` | 13 | 0 | ✅ CLEAN |
| `fireai/core/hac_classification_engine.py` | 36 | 0 | ✅ CLEAN |
| `fireai/core/nfpa72_calculations.py` | 8 | 0 | ✅ CLEAN |

## 2. Production-Wide Summary

| Module | Files | Total Issues | Real Bugs | Status |
|--------|-------|-------------|-----------|--------|
| `fireai/core/` | 161 | 1593 | 0 | ✅ |
| `fireai/infrastructure/` | 14 | 43 | 0 | ✅ |
| `fireai/validation/` | 4 | 23 | 0 | ✅ |
| `fireai/analytics/` | 4 | 31 | 0 | ✅ |
| `fireai/agents/` | 5 | 29 | 0 | ✅ |
| `fireai/mcp_server/` | 5 | 10 | 0 | ✅ |
| `fireai/bridges/` | 9 | 46 | 0 | ✅ |
| `fireai/integration/` | 9 | 63 | 0 | ✅ |
| `fireai/conduit/` | 10 | 14 | 0 | ✅ |
| `fireai/tools/` | 7 | 29 | 0 | ✅ |
| `fireai/v17_core/` | 4 | 3 | 0 | ✅ |
| `backend/routers/` | 27 | 371 | 0 | ✅ |
| `backend/services/` | 16 | 113 | 0 | ✅ |
| `qomn_fire/` | 31 | 108 | 0 | ✅ |
| `qomn_conduit/` | 18 | 41 | 0 | ✅ |
| `parsers/` | 22 | 118 | 0 | ✅ |
| `core/` | 7 | 85 | 0 | ✅ |
| `adapters/` | 2 | 1 | 0 | ✅ |

## 3. Bandit Security Scan (Critical Files)

- **Lines scanned:** 4272
- **HIGH severity:** 0
- **MEDIUM severity:** 0
- **LOW severity:** 1

✅ No security issues found in critical files.

## Interpretation

- **F-series (pyflakes)**: Real bugs — undefined names, unused imports,
  syntax errors. These MUST be fixed.
- **E-series (pycodestyle)**: Code style — line length, whitespace.
  Pre-existing; not blocking.
- **PLR2004 (magic values)**: Code smell — numeric literals in comparisons.
  Pre-existing; not blocking.
- **C901 (complexity)**: Code smell — function too complex. Pre-existing;
  documented in NOSONAR_AUDIT.md as S3776.
- **Bandit HIGH/MEDIUM**: Security issues. MUST be investigated.

## Next Steps

1. If any F-series bugs found above → fix immediately
2. If any Bandit HIGH/MEDIUM found → investigate and fix
3. For full SonarCloud analysis → follow OPS_RUNBOOK.md Task 2
