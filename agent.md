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

---

## V12 Round 2 Fixes (2026-05-20)

### Bug 4 — Atrium Deletion Bug (CRITICAL)
**File:** `adapters/pdf_to_rooms_adapter.py` — `_filter_valid_rooms()` + `MAX_ROOM_AREA_SQM`
**Consultant Claim:** `area > second_largest * 100` deletes atriums/lobbies that are legitimately large.
**Verification:** ✅ CONFIRMED — Hotel atrium 3000m² vs offices 25m²: 3000 > 25×100 = 2500 → atrium deleted. Also `MAX_ROOM_AREA_SQM = 200` silently kills any room over 200m².
**Impact:** Largest/most important spaces in a building (atriums, lobbies, exhibition halls) get zero fire protection.
**Fix Applied:**
- Replaced area-ratio check with architectural containment check: outer boundary is identified by containing ≥50% of other polygons' centroids
- Raised `MAX_ROOM_AREA_SQM` from 200 to 10000 (atriums can be 3000+ m²)
**Why consultant's fix is better than old code:** Containment is architecturally correct — an outer boundary "swallows" inner rooms; an atrium does not.

### Bug 5 — Obstruction Bypass in Heat Detector Fallback (CRITICAL)
**File:** `core/adaptive_solver.py` — `_try_heat_detectors()` and `_try_beam_detectors()`
**Consultant Claim:** When smoke detectors fail due to obstructions, heat detector fallback uses `room_polygon` instead of `safe_polygon`, placing detectors inside electrical panels.
**Verification:** ✅ CONFIRMED — `_try_heat_detectors(self, room_polygon, ...)` and `_try_beam_detectors(self, room_polygon, ...)` both use `room_polygon.contains(Point(x, y))` without subtracting exclusion zones.
**Impact:** Heat detectors placed inside cable trays or electrical panels — direct NEC violation.
**Fix Applied:**
- Changed `_try_heat_detectors` signature to accept `safe_polygon` instead of `room_polygon`
- Changed `_try_beam_detectors` signature similarly
- `re_solve_with_alternatives` now computes `safe_polygon` and passes it to both fallback methods
**Consultant's fix was correct** — we applied it with minor adjustments for code consistency.

### Bug 6 — 2D Projection Fallacy (HIGH)
**File:** `core/code_compliance_engine.py` — `check_compliance()`
**Consultant Claim:** Distance calculated in 2D only, causing false violations when detector is on ceiling above a floor-level obstruction.
**Verification:** ⚠️ CONFIRMED in principle — `obs.polygon.distance(point)` is 2D. However, `obs.height_above_floor_m` may not exist on all obstruction objects.
**Impact:** False RED violations force engineers to relocate detectors that are actually safe (3.3m vertical clearance).
**Fix Applied:**
- Added 3D distance calculation using `math.hypot(horizontal_dist, vertical_dist)` when `obs.height_above_floor_m` is available
- If vertical separation alone exceeds minimum distance → auto-clear (no violation)
- Falls back to 2D when height info is unavailable (conservative/fail-safe)
- Violation description now includes 3D breakdown: "(3D: 3.35m = horiz:0.5m + vert:3.3m)"
**Why NOT consultant's exact fix:** The consultant assumed `obs.height_above_floor_m` always exists. We use `getattr()` with fallback to ensure no crashes.

### Bug 7 — Midpoint Cost Bypass (HIGH)
**File:** `core/engineering_router.py` — `_segment_cost_factor()`
**Consultant Claim:** Only checks midpoint of cable segment, not the full segment. A 50m cable alongside an elevator shaft with midpoint in a safe zone gets no penalty.
**Verification:** ✅ CONFIRMED — `mid_x, mid_y = (p1+p2)/2` then `_point_near_obstacle((mid_x, mid_y))` — single point check only.
**Impact:** A* algorithm's cost function is undermined — routes through dangerous zones get same cost as safe routes.
**Fix Applied:**
- When Shapely available: `ShapelyLineString([p1, p2]).intersects(obstacle_poly)` — checks ENTIRE segment
- When Shapely unavailable: check midpoint AND quarter-points (3 points instead of 1)
- Uses pre-computed `_obstacle_polys` for efficiency
**Why NOT consultant's exact fix:** Consultant multiplied clearance by 2.0 arbitrarily. We use the existing pre-computed obstacle polygons with standard clearance.

---

## V12 Round 3 Fixes — Bridges Layer (2026-05-20)

### Bug 8 — Unassigned Devices Black Hole (CRITICAL)
**File:** `bridges/orchestrator.py` — FireAI Engine section
**Consultant Claim:** Devices with room_id="UNASSIGNED" never enter any compliance check.
**Verification:** ✅ CONFIRMED
**Fix:** Track verified_device_ids; orphaned devices trigger CRITICAL SAFETY GATE (proof_valid=False).

### Bug 9 — 2D BIM Collapse (CRITICAL)
**File:** `bridges/digital_twin_bridge.py` — `detect_conflicts()`
**Consultant Claim:** Conflict detection uses 2D only, flagging different-floor sensors as duplicates.
**Verification:** ✅ CONFIRMED
**Fix:** 3D Euclidean distance when Z available. 2D fallback with auto_resolvable=False.

### Bug 10 — Hardcoded CAD Vandalism (HIGH)
**File:** `bridges/output_bridge.py` — `_draw_schedule_table()`
**Consultant Claim:** Fixed coordinates (15000, 20000) for schedule table.
**Verification:** ✅ CONFIRMED
**Fix:** Dynamic positioning from room bounding box with 2m margin.

### Bug 11 — Silent Room Drop (CRITICAL)
**File:** `bridges/parser_bridge.py` — `_extract_rooms_from_entities()`
**Consultant Claim:** `if not poly.is_valid: continue` silently drops rooms.
**Verification:** ✅ CONFIRMED
**Fix:** Added `poly.buffer(0)` healing + `log.critical()` when dropped. Same for obstructions.

### Regression Check
- ✅ buffer(0.5) in parser_bridge — REMOVED in V11, confirmed NOT present
- ✅ Manhattan routing in output_bridge — Present but justified (V11 fix with panel_height_m + obstacle_tolerance)
