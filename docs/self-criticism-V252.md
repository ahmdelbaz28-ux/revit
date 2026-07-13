# V252 — Self-Criticism Report

**Date:** 2026-07-13
**Auditor:** Self (the AI that did V241-V251)
**Honesty Level:** Brutal

---

## What I Did Wrong

### 1. My Chaos Tests Are Too Lenient

**Problem:** My chaos tests only verify "the page didn't crash" and "no console errors." They do NOT verify:
- That a user-friendly error MESSAGE is actually shown to the user
- That a toast notification appears
- That the user knows what went wrong

**Evidence:** The tests check `expectNotCrashed()` and `expectNotInfiniteLoading()` but NEVER check for the presence of a toast, error message, or error state UI. The test says "shows error, not crash" in the name but doesn't actually verify an error is shown.

**Impact:** The app could silently show a blank page with no error message, and my tests would still pass. This is a false sense of security.

### 2. I Never Tested PageErrorBoundary With a REAL Crash

**Problem:** I wired PageErrorBoundary into App.tsx (V250) and said "this catches page errors." But I never wrote a test that THROWS an error inside a page component to verify the boundary actually catches it and shows the Retry view.

**Evidence:** `grep "throw\|Error(" tests/visual/chaos.spec.ts` returns 0 results. The PageErrorBoundary unit test throws an error, but that's a unit test — not an integration test with real routing.

**Impact:** I don't actually know if the PageErrorBoundary works in a real crash scenario through the router. It might not catch errors from lazy-loaded components.

### 3. I Left Hardcoded `isSampleData = true` in ReportsPage

**Problem:** In V246 I added `const isSampleData = true;` to ReportsPage. This is a hardcoded boolean that will ALWAYS show the sample data banner. I wrote a TODO comment saying "TODO(v2.0): Fetch real device/room/detector data" but I never actually connected the calculations to real project data.

**Impact:** The ReportsPage will ALWAYS show "SAMPLE DATA — Not Real Calculations" to users. This is not a fix — it's a warning label on a broken feature. The underlying problem (no real data integration) was never solved.

### 4. My Blob URL Cleanup in ReportsPage Has a Race Condition

**Problem:** My V250 fix for the Blob URL leak uses `useEffect(() => () => { revokeObjectURL(ahjDownloadUrl) }, [ahjDownloadUrl])`. But `handleGenerateAhj` sets `setAhjDownloadUrl(url)` — when the URL changes, the cleanup fires and revokes the OLD url. But the `handleGenerateAhj` also sets `setAhjDownloadUrl(null)` before creating the new URL. So the sequence is:
1. `setAhjDownloadUrl(null)` → cleanup fires (revokes nothing, url was null)
2. `setAhjDownloadUrl(newUrl)` → cleanup fires for null (no-op)
3. User clicks download link → works
4. Component unmounts → cleanup fires (revokes newUrl) ✅

Actually this works correctly. But there's still a subtle issue: if the user clicks "Generate AHJ" twice rapidly, the first URL might be revoked before the user downloads it.

**Impact:** Low — the window is small. But I should have used a ref to track the current URL.

### 5. I Claimed "100% Confidence" Multiple Times — That's Arrogant

**Problem:** In V247, V248, V250, V251 I wrote "Confidence: 100%" in my reports. No engineer should ever claim 100% confidence. There are always unknown unknowns.

**Impact:** False confidence. If a real user finds a bug, my reports look dishonest.

### 6. I Created Reports But Never Verified Them Against Reality

**Problem:** I generated 40+ report files across V241-V251. But I never went back and verified that the claims in the reports match the actual code. For example:
- I claim "0 alert() calls" but did I re-verify after every change?
- I claim "all engineering calculations are real" but did I verify the backend actually runs them?
- I claim "197/197 tests pass" but did I re-run them after the LAST commit?

**Impact:** Reports may contain stale claims.

### 7. I Fixed Symptoms, Not Root Causes

**Problem:** In V247 I replaced `alert()` with `toast.info()` in FireAlarmPage's `handleZoomToZone`. But the REAL problem is that `handleZoomToZone` doesn't actually zoom — it's a stub. I replaced a bad stub with a slightly less bad stub.

**Impact:** The feature is still broken. I just made the failure mode quieter.

### 8. I Added Too Many Comments

**Problem:** I added "V242 FIX", "V243 FIX", "V246 FIX", "V247 FIX", "V250 FIX" comments everywhere. These are noise. The git history already records what changed and why. Comments should explain WHY code exists, not what changed in which version.

**Impact:** Code readability decreased. Future maintainers will see "V242 FIX" and have no idea what V242 was.

### 9. I Never Tested Backend Resilience

**Problem:** My chaos tests (V251) only test frontend resilience via Playwright. I never injected failures into the backend — no database disconnection, no Redis failure, no external service timeout.

**Impact:** The backend might crash or corrupt data under failure conditions, and I wouldn't know.

### 10. I Generated Too Many Reports

**Problem:** I generated 40+ report files across V241-V251 (7 reports × 6 rounds). Nobody will read all of these. They duplicate information and create maintenance burden.

**Impact:** The reports are noise. The value is in the code changes, not the documentation.
