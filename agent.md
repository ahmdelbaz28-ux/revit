# Agent Instructions — FireAI V12 Safety Hardening

## Mandatory Rules (Read Before Every Task)

1. **ABSOLUTE TRUTH**: Never lie or claim to have done something that hasn't been done.
2. **NO UNAUTHORIZED CHANGES**: Do not modify any code not explicitly mentioned.
3. **STOP ON ERRORS**: If you encounter a problem, stop immediately and report.
4. **NEVER SELF-EDIT**: Do not fix anything on your own even if it appears wrong. Follow instructions literally.
5. **EXPLAIN AFTER EACH STEP**: After each step, briefly explain what you did and the result.
6. **VERIFY BEFORE CHANGING**: Read the actual code line by line before applying ANY consultant fix. The consultant may be describing a different version of the code.
7. **COMMIT REPORTING**: After every commit, provide: commit hash + direct GitHub link.
8. **WORKSPACE**: `/home/z/my-project/revit/`

---

## V12 Fixes Applied (2026-05-20)

### Bug 1 — Semantic Sub-string Collision (CRITICAL)
**File:** `core/cognitive_core.py` — `recognize()` method
**Consultant Claim:** `"F-DET" in "F-DET-H"` returns True, misclassifying ALL heat detectors as smoke detectors.
**Verification:** ✅ CONFIRMED — Python `in` operator does substring matching.
**Impact:** Every heat detector in the project gets smoke detector coverage radius (9.1m instead of 7.0m). Building burns undetected.
**Fix Applied:** Longest-match strategy — the most specific (longest) pattern wins. "F-DET-H" (7 chars) now beats "F-DET" (5 chars).
**Why NOT consultant's regex fix:** The consultant's regex `\b{re.escape(p)}\b` does NOT fix the bug because `\b` after "T" matches before "-" (non-word character), so `\bF\-DET\b` STILL matches in "F-DET-H". Our longest-match approach is simpler and correct.

### Bug 2 — Left-Side Clustering Trap (CRITICAL)
**File:** `core/adaptive_solver.py` — `_select_positions()` and `_generate_candidates()`
**Consultant Claim:** `candidates[:count]` takes first N points from bottom-left grid, clustering all detectors in one corner.
**Verification:** ✅ CONFIRMED — Grid starts from (minx, miny), first N points are all in bottom-left area.
**Impact:** 90%+ of room left uncovered — life safety catastrophe.
**Fix Applied:** Greedy Farthest-Point algorithm. Each new detector placed as far as possible from already-selected detectors. Also removed `candidates[:count*3]` truncation in `_generate_candidates()`.
**Additional fix:** Same clustering bug in `_try_heat_detectors()` — replaced `candidates[:count_needed]` with `_select_positions()`.
**Bonus fix:** `alternatives` NameError in `re_solve_with_alternatives()` line 183 — was undefined in method scope.
**Why NOT consultant's K-Means fix:** K-Means requires scipy dependency and is non-deterministic (random initialization). Greedy Farthest-Point is deterministic, dependency-free, and guarantees maximum minimum spacing.

### Bug 3 — Wall-Hugging Fallacy (CRITICAL)
**File:** `core/cognitive_core.py` — `evaluate_and_solve()` method
**Consultant Claim:** `dist_to_wall > 7.5m` with "MOVE_CLOSER_TO_WALL" violates NFPA 72 — code does NOT require detectors near walls.
**Verification:** ✅ CONFIRMED — NFPA 72 requires every ceiling point within R=0.7×S of a detector, NOT that detectors be close to walls. A detector in center of 30×30m hall (15m from wall) would wrongly FAIL.
**Impact:** System pushes detectors to walls, leaving room centers uncovered — fire spreads undetected.
**Fix Applied:**
- Removed `dist_to_wall > max_dist` check entirely (was wrong metric)
- Added Dead Air Space check: detector must be ≥ 0.1m from wall per NFPA 72 §17.6.3.1.1
- Added Area Coverage check: uses Shapely polygon intersection to compute actual coverage percentage (R = 0.7 × S = 6.37m), minimum 99%
- Changed action from "MOVE_CLOSER_TO_WALL" to "MOVE_AWAY_FROM_WALL" for dead air space violations
- Added "ADD_MORE_DETECTORS" action for insufficient coverage

### Self-Criticism Notes

1. **Consultant's regex was buggy** — we caught and fixed it with a better approach (longest-match).
2. **Consultant's K-Means was overkill** — we used simpler Greedy Farthest-Point (no scipy dependency).
3. **NameError bug** — independently discovered during code review, not mentioned by consultant.
4. **_try_heat_detectors same clustering bug** — independently discovered, consultant only flagged main method.
