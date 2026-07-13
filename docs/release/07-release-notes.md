# 07 — Release Notes

**Project:** BAZspark v1.55.0
**Release Date:** 2026-07-13
**Final Commit:** `d1fc9d18`

---

## Release Highlights

### V247 (This Release)
- **CRITICAL:** Removed fake fire-alarm detectors from FireAlarmDesigner
- **CRITICAL:** Replaced all `alert()` calls with toast/console
- **HIGH:** Fixed "File browser not implemented" → real file inputs
- **HIGH:** Added toast notifications for silent download/export errors
- **HIGH:** Removed `any` types from FireAlarmDesigner

### V241-V246 (Previous Rounds)
- 50% smaller initial bundle (705kB → 349kB)
- Zero skipped tests (9 skips → 0)
- Lighthouse: 77/100/96/100 → 83-94/100/100/100
- 104+ backend endpoints rate-limited
- Redis session store with in-memory fallback
- All CRITICAL/HIGH security vulnerabilities fixed
- All `FIREAI_ENV` defaults → "production" (fail-safe)
- 64 new safety-critical unit tests (NFPA72, Coverage, Battery, CodeValidator)

## Files Modified (V247)

| File | Change |
|---|---|
| `FireAlarmDesigner.tsx` | Removed fake detectors; fixed any types |
| `FireAlarmPage.tsx` | alert() → toast.info() |
| `ReportsPage.tsx` | alert() → toast.error(); silent console.error → toast |
| `ReportGeneratorPage.tsx` | Silent console.error → toast.error() |
| `CADSettingsPage.tsx` | 3× "not implemented" → real file inputs |
| `RiskAssessment.tsx` | alert() → console.info() |
| `SystemAnalyzer.tsx` | 2× alert() → console.info() |
| `SystemOptimizer.tsx` | alert() → console.info() |
| `ImportExportManager.tsx` | 2× alert() → console.info()/error() |

## Breaking Changes

None. All changes are backward-compatible.

## Migration Guide

No migration required. Existing deployments will pick up the fixes on next
`git pull` + rebuild.

## Verification

- ✅ 0 build errors
- ✅ 0 lint errors
- ✅ 0 TypeScript errors
- ✅ 197/197 tests pass (0 skips)
- ✅ Lighthouse: 83-94/100/100/100
- ✅ 0 npm audit vulnerabilities
- ✅ 0 alert() calls in production code
- ✅ 0 "not implemented" messages
- ✅ 0 fake/mock data in production paths
