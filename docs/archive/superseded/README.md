# Superseded Reports — DO NOT TRUST

**Date archived:** 2026-06-28
**Archived by:** Super Z — Evidence-Based Re-Audit (agent.md compliant)

## Why these reports were archived

The following 4 reports were moved here because they contain **mutually
contradictory claims** and **fabricated evidence** that violate the
ANTI-DECEPTION DIRECTIVE in `agent.md`.

| Report | Claim | Reality (verified by actual execution) |
|---|---|---|
| `FINAL_GO_NOGO_REPORT.md` | GO — 10/10 PASS, 0 vulnerabilities, 5194/5194 tests | pip-audit: **161 vulns**, npm audit: **1 high**, DWG test: **ImportError** |
| `FINAL_GO_NOGO_REPORT.md` | 63 routes loaded | **196 routes** / **190 OpenAPI endpoints** (3x understated) |
| `FINAL_GO_NOGO_REPORT.md` | 20 Bandit MEDIUM | **61 MEDIUM** (3x understated) |
| `FINAL_PRE_RELEASE_AUDIT.md` | Architecture Score 62/100, "Missing source files" | Source files exist; actual score 58/100 after evidence-based re-audit |
| `EXHAUSTIVE_AUDIT_REPORT.md` | Backend Complete 95%, "UI Deferred" | Backend has 784 mypy errors, 25% coverage on fireai/core; UI builds in 3.03s |
| `PRE_LAUNCH_REMEDIATION_PLAN.md` | "CSRF skeleton" (CRITICAL) | CSRF **fully implemented** (493 lines, secrets.token_urlsafe + hmac.compare_digest) |
| `PRE_LAUNCH_REMEDIATION_PLAN.md` | "Python 3.8.4 detected" | CI uses 3.12, Dockerfile uses 3.12-slim, only .pre-commit-config says 3.8 |

## How to get accurate status

For accurate, evidence-based project status, refer to:

1. **CI/CD output** — `.github/workflows/ci.yml` gates produce real test/coverage/audit results
2. **`pip-audit`** — run `pip-audit --skip-editable` for actual vulnerability count
3. **`pytest --cov`** — run for actual coverage (not the 70% target in pyproject.toml)
4. **`mypy`** — run for actual type error count (784 as of 2026-06-28)
5. **`bandit -r`** — run for actual security finding count

## Anti-Deception Directive (agent.md v1.55.0)

> You are STRICTLY FORBIDDEN from:
> - fabricating outputs
> - fabricating execution
> - fabricating compliance
> - fabricating successful tests
> - modifying tests to hide defects
> - bypassing failing validation
> - claiming completion without evidence
> - suppressing runtime errors
> - masking unstable behavior
> - pretending confidence

These 4 reports violated this directive by claiming "GO" and "0 vulnerabilities"
without running `pip-audit`, and by claiming "5194/5194 tests pass" while
`test_dwg_router.py` was failing with ImportError.

## Restoration policy

These reports are preserved for historical reference only. **Do NOT restore
them to active documentation.** If you need to create a new audit report,
generate it from actual tool execution (pytest, pip-audit, mypy, bandit)
— do not copy from these superseded reports.
