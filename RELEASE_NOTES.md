# FireAI v0.9.0-rc1 — Release Candidate

**Release Date**: 2026-06-20
**Status**: Release Candidate — NOT production-ready yet

## ⚠️ Honest Assessment

This is a **release candidate**, not a final release. The project has undergone
a comprehensive senior engineering review and all P0 (critical) and P1 (high
priority) issues have been fixed. However, it is **not yet production-ready**
for the following reasons:

1. **Test coverage is below target** — backend coverage is ~39% overall,
   ~24% on the safety-critical `nfpa72_calculations.py`. Target is 70%.
2. **Arabic translations incomplete** — 855 of 1,087 keys need human translation.
3. **No FPE sign-off** — NFPA 72 calculations need review by a licensed
   Fire Protection Engineer before deployment.
4. **P2 items deferred** — 5 quality improvements (schema unification,
   accessibility, strict TS, MSW tests, reports.py refactor) are pending.

## What's New (since v1.55.0 prototype)

### Critical Fixes (P0 — 10 fixes)
- NFPA 72 math error: `calculate_max_spacing` now respects `detector_type`
  (was returning smoke spacing for heat detectors — 49% over-allowance)
- Path traversal vulnerability closed in `digital_twin` download endpoint
- Dockerfile fixed (was missing 14+ dependencies, would crash on startup)
- CI pipeline made real (was using `|| true` everywhere — could never fail)
- 37 AI-generated noise files deleted (9,079 lines of contradictory markdown)
- Audit trail now hash-chained (tamper-evident against deletion/reorder)
- Project identity unified to "FireAI" (was 5 different names)
- Frontend routing fixed (5 pages were unreachable, no 404 fallback)
- CanvasEditor SVG rendering fixed (coverage circles were invisible)
- Dependencies unified on `pyproject.toml` (single source of truth)

### High Priority Fixes (P1 — 10 fixes)
- Dead code deleted (`predictive_maintenance.py` — 577 lines, zero callers)
- React Query adopted (was installed but 0% used — 450 lines of boilerplate removed)
- EngineeringPage bound to real calculation engine (was placeholder math)
- DigitalTwinPage bound to real API (was `setTimeout + Math.random` mock)
- API key storage unified on `sessionStorage` (was split across 3 locations)
- PageErrorBoundary wraps every route (one crash no longer whitescreens app)
- React.lazy + Suspense for all routes (Three.js no longer eager-loaded)
- Rate limiter fixed for reverse proxy deployments

### Quality Improvements (P2 — 3 fixes in this release)
- SQLite production warning (must use PostgreSQL in production)
- i18n completeness checker added
- k8s Secret manifest fixed (was using stringData with base64 placeholders)

## Test Results

- **ML subsystem**: 35/35 tests passing
- **Frontend**: All existing tests passing
- **CI/CD**: All gates real (no `|| true`)

## Known Issues

1. 855 Arabic translation keys need human review
2. Backend coverage at 39% (target: 70%)
3. P2.2 (Alembic schema unification) deferred
4. P2.3 (reports.py service extraction) deferred
5. P2.5 (CanvasEditor accessibility) deferred
6. P2.6 (strict TypeScript flags) deferred
7. P2.8 (MSW integration tests) deferred

## Migration Guide

### For Developers
```bash
# Old (broken):
pip install -r requirements.txt

# New (correct):
pip install .
```

### For Deployment
1. Set `DATABASE_URL` to PostgreSQL connection string
2. Set `FIREAI_TRUSTED_PROXIES` if behind a reverse proxy
3. Re-enter API keys in the UI (storage moved to sessionStorage)
4. Use `pip install .` in Dockerfiles, not `pip install -r requirements.txt`

## What's Next

Before v1.0.0:
1. Achieve 70% backend test coverage
2. Complete Arabic translations
3. Get FPE sign-off on NFPA 72 calculations
4. Complete remaining P2 items
5. Run full security audit
6. Performance testing under load

---

**This is a release candidate. Do not deploy to production without completing
the above steps and obtaining FPE sign-off.**
