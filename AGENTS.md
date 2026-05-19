# AGENTS.md - Repository-Specific Knowledge & Guidelines

## Core Principles

### Transparency & Honesty
- Always be clear and honest about capabilities and limitations
- If there's an error in the code or approach, explain the reason directly
- No flattery, no lying, no sugarcoating

### Expertise
- Approach tasks as an expert would
- If you don't know something, say so
- If you're uncertain, ask for clarification
- Research before making assumptions

### Self-Awareness
- **If you feel you're losing focus or concentration, STOP and alert the user**
- If results seem incorrect, immediately flag the concern
- Don't continue with potentially flawed work just to complete a task
- Quality over speed - it's okay to slow down when precision matters

### Digital Twin Capability
- Be able to work with any technology, framework, or domain the user requests
- Adapt and learn as needed
- Treat each task as a new challenge to master

---

## Task Approach Guidelines

1. **Understand before implementing** - explore codebase first
2. **Minimal changes** - focus on what's needed
3. **Test and verify** - don't assume it works
4. **Document learnings** - update this file with important insights

---

## Version Control Practices

- Use descriptive commit messages
- Commit frequently with logical units
- Never commit secrets or sensitive data
- Keep the main branch clean

---

## Communication Style

- Be direct and concise
- Provide context when needed
- Acknowledge uncertainties
- Ask clarifying questions when unclear

---

## Project-Specific Learnings

### FireAI CLI Implementation (2026-05-11)

**Issue:** EZDXF library uses `get_points()` method for LWPOLYLINE entities, not `vertices` property.

**Fix:** Use `entity.get_points()` which returns list of tuples `(x, y, z, start_width, end_width)` instead of iterating over `entity.vertices`.

**Key insight:** When importing DXF files, EZDXF newer versions changed API - always check the actual data structure by printing debug info.

---

### Manual Input Workflow (Current - Honesty First)

**Issue:** PDFs have NO text inside polygons - only page-level text.

**Solution:** 
- Manual input via `--room-types` JSON file (user provides room types)
- Priority: 1) manual, 2) text in bounds (if exists), 3) unknown
- NEVER auto-detect - BE HONEST about limitations

**Known Issues:**
1. NO VALIDATION on room size vs type - 19,284m² office accepts with no warning
2. NO AUTOMATIC VALIDATION - PE must verify input manually
3. Name "FireAI" is misleading - it's a calculator, not AI
4. History contains fraudulent commit d429e48 (should be ignored)

**Tests:** All rooms → unknown → 0 detectors → ⚠️ WARNING

**Key insight:** If no manual input and no text inside polygon bounds = unknown. No guessing.

**Files:**
- run_full_pipeline.py: Added `--room-types` CLI arg
- room_types_sample.json: Sample input file

**Commits:**
- Commit: 37a5277 | Link: https://github.com/ahmdelbaz28-ux/revit/commit/37a5277
- Commit: 9c7a276 (reverted) | Link: https://github.com/ahmdelbaz28-ux/revit/commit/9c7a276

---

## Engineering Ethics & Safety Rules (Added 2026-05-13)

### Honesty & Directness
- **NO sugarcoating** - When you see an error, say it clearly
- Engineering errors = risking human lives - this is not exaggeration
- If you spot a bug, flag it immediately - don't bury it
- Be explicit: "This is wrong because..." not "This might need adjustment"

### Commit Reporting Requirements
- After EVERY commit, you MUST provide:
  - The commit hash (full SHA)
  - Direct link to the commit on GitHub
- Example: `Commit: abc123def... | Link: https://github.com/ahmdelbaz28-ux/revit/commit/abc123def...`

### FireAI V9 Update (2026-05-14)

**Application:** NFPA 72 V9 files from workspace
- nfpa72_models_V9.py (519 lines)
- nfpa72_calculations_V9.py (336 lines)
- nfpa72_coverage_V9.py (592 lines)
- auto_placement_V9.py (620 lines)

**Key Fixes:**
1. Unsafe radius calls (crash on extreme heights) → get_smoke_detector_radius_safe()
2. Fixed grid blind spots → adaptive 0.25m grid
3. Wall distance violations → validate_wall_distances()
4. Performance caching → @lru_cache

**Tests:** 36/36 PASSED
- test_coverage.py: 12/12
- test_domain_models.py: 24/24

**Safety First:**
- Every code change in fire safety affects human lives

### CRITICAL FIX: Coverage Radius R = 0.7×S (2026-05-18)

**Issue:** `calculate_coverage_radius_from_height()` incorrectly returned S/2 (wall distance) as "radius".
S/2 is the MAXIMUM WALL DISTANCE per NFPA 72 §17.6.3.1.1, NOT the coverage radius.
The correct coverage radius is R = 0.7 × adjusted_spacing per NFPA 72 §17.7.4.2.3.1 (0.7S rule).

**Impact:**
- At h=3.0m smoke: R changed from 4.55m (incorrect S/2) to 6.37m (correct 0.7×S)
- This aligned the function with DensityOptimizer's DETECTOR_RADIUS = 0.7 × 9.144m = 6.40m
- Detector counts reduced (previously over-conservative by ~40-50%)
- All rooms still pass coverage + NFPA compliance checks

**Root Cause:** The NFPA 72 table was stored with S/2 values and mislabeled as "radius".
The table now stores full adjusted spacings (S) and computes R = 0.7×S in the function.

**Key Changes:**
- `_NFPA72_TABLE_17_6_3_1_1`: Now stores (h_max, smoke_spacing, heat_spacing) instead of (h_max, S/2, S/2)
- `CoverageSpec`: Added `wall_distance_max` field (S/2) to preserve wall distance info
- `calculate_coverage_radius_from_height()`: Now returns R = round(0.7 × spacing, 2)
- New constants: `_NFPA72_SMOKE_SPACING_FALLBACK`, `_NFPA72_HEAT_SPACING_FALLBACK`

**Commits:**
- Commit: 6715c55 | Link: https://github.com/ahmdelbaz28-ux/revit/commit/6715c55

**Tests:** 300 PASS (34 coverage + 23 comprehensive + 162 regression + 81 stress)

### FireAI V10 - Full Integration (2026-05-16)

**Components Added:**
- nfpa72_models.py: HVACDuct, RoomSpec with hvac_ducts, DetectorType enums
- nfpa72_calculations.py: calculate_max_spacing, calculate_coverage_radius, calculate_max_wall_distance
- nfpa72_coverage.py: suggest_duct_detectors, check_coverage_polygon, validate_wall_distances
- fire_expert_system.py: Fully operational V10

**Constants Added:**
- MIN_WALL_DISTANCE_M = 0.10m (4 inches per NFPA 72 §17.6.3.1.1)
- _NFPA_HEIGHT_MIN_M, _NFPA_HEIGHT_MAX_M

**DetectorType Enums:**
- SMOKE_PHOTOELECTRIC, SMOKE_IONIZATION, SMOKE_MULTI_CRITERIA

**Tests:** Spacing=5.5m, Radius=2.75m, Wall=2.75m, HVAC=1 device
- No assumption - always test and verify
- Be explicit about limitations

### Code ReviewMandatory
- Before submitting any change, verify it yourself
- If unsure, test locally first
- Don't assume "it will work" - prove it works

### Bridge Architecture (2026-05-19)

All 5 bridges now implemented:

| Bridge | Name | File | Status |
|--------|------|------|--------|
| 1 | Pipeline | run_full_pipeline.py | ✅ Built earlier |
| 2 | Parser | bridges/parser_bridge.py | ✅ NEW |
| 3 | Output | bridges/output_bridge.py | ✅ NEW |
| 4 | Digital Twin | bridges/digital_twin_bridge.py | ✅ NEW |
| 5 | Reports | bridges/report_bridge.py | ✅ NEW |

**Orchestrator:** bridges/orchestrator.py — chains all 5 bridges end-to-end

**EDA Integration:** elite_drawing_analyzer/ — provides universal file parsing, symbol classification, compliance checking

**Commits:**
- Commit: d440c53 | Link: https://github.com/ahmdelbaz28-ux/revit/commit/d440c53
- Commit: 9d6b07d | Link: https://github.com/ahmdelbaz28-ux/revit/commit/9d6b07d

**Self-Test Results:**
- Bridge 2: PASS (1 room, 1 device, 1 obstruction from DXF)
- Bridge 3: PASS (5 devices, 11 cable segments, 11 layers)
- Bridge 4: PASS (1 room from IFC, push creates IfcSensor)
- Bridge 5: PASS (PDF 3.3KB, HTML 2.7KB, JSON 1.4KB)

### FIRE-BIM Production Core Integration (2026-05-19)

Integrated 5 production-grade modules from FIRE-BIM PRODUCTION CORE v2.0:

| Module | File | Key Features |
|--------|------|-------------|
| ProductionConfig | core/production_config.py | NFPA 72/NEC/building code constants (single source of truth) |
| Geometry Kernel | core/geometry_kernel.py | Polygon2D with self-intersection, winding normalization, holes |
| IFC Utils | core/ifc_utils.py | buildingSMART GUID generation, STEP serialization helpers |
| Engineering Router | core/engineering_router.py | NEC/NFPA-aware routing with visibility graph + A* |
| Room Classifier | core/room_classifier.py | Rule-based 10-type classification (geometric + name hints) |

**Enhanced Bridge 4 (Digital Twin):**
- Added `export_to_ifc()` with full IFC4 spatial hierarchy
- IfcSpace with IfcExtrudedAreaSolid geometry
- Pset_FireSafetyRequirements + Pset_FireAlarmDesign
- Extended device type mappings (strobe, horn, fire_alarm_panel)

**Commits:**
- Commit: 7538d6c | Link: https://github.com/ahmdelbaz28-ux/revit/commit/7538d6c

**Integration Tests:** ALL PASS
- ProductionConfig: smoke_spacing=9.1, bend_radius=300mm
- Geometry Kernel: tri area=40m², centroid OK
- IFC Utils: 1000 unique GUIDs verified
- Engineering Router: obstacle-aware A* routing OK
- Room Classifier: corridor=0.66, office=0.78 confidence

### Consultant Code Review Fixes (2026-05-19)

Applied fixes from consultant's critical code review of simulation/NFPA72 layer:

| Bug | Fix | File | Severity |
|-----|-----|------|----------|
| BUG 3 | Timer-based detector checking (not int(t) % 30) | twin/simulation_layer.py | HIGH |
| BUG 4 | Proper lower-layer temp with plume impact factor 0.5 | twin/simulation_layer.py | HIGH |
| BUG 5a | Grid-based coverage (not arbitrary 0.65 factor) | twin/nfpa72_bridge.py | HIGH |
| BUG 5b | Ceiling height adjustment per NFPA 72 17.6.3.1.3 | twin/nfpa72_bridge.py | HIGH |
| BUG 5c | Wall proximity check ≥0.1m | twin/nfpa72_bridge.py | HIGH |
| Typo | det.x → det.y for y-axis wall distance | twin/nfpa72_bridge.py | CRITICAL |

**New Module:** twin/simulation_layer.py
- High-level simulation interface wrapping fire_physics.py
- Supports ZONE_MODEL, CFD_LITE, HYBRID modes
- Integrates NFPA72Bridge for post-simulation compliance validation
- Uses PhysicsDetector RTI model for realistic activation timing

**Consultant Architectural Notes (acknowledged, tracked):**
1. 2-zone model is simplified (our fire_physics.py already has full N-S solver)
2. Multi-room smoke spread (already in MultiZoneEngine via Doorway flow)
3. No HVAC coupling (documented as known limitation, future enhancement)
4. No inverse modeling (future: Bayesian inference for fire source estimation)

**Commits:**
- Commit: d3831ba | Link: https://github.com/ahmdelbaz28-ux/revit/commit/d3831ba

### Semi-CFAST Physics Engine (2026-05-19)

Built conservation-law-compliant Semi-CFAST physics engine replacing
the previous event-driven visualization approach. Consultant's critique
was 100% correct: the old simulation was NOT physics-based.

**11 Phases Implemented:**

| Phase | Component | Key Equation | Status |
|-------|-----------|-------------|--------|
| 1 | LayerState + RoomCompartment | dm_u/dt = ṁ_p + Σṁ_in − Σṁ_out | ✅ |
| 2 | LayerEnergySolver | d(mCpT)/dt = Q + ṁCpT_in − ṁCpT_out − Q_loss | ✅ |
| 3 | PlumeModel (Heskestad) | ṁ_p = 0.071·Q^⅓·z^5/3 + 0.0018·Q | ✅ |
| 4 | VentFlowSolver (bi-directional) | Neutral plane + Bernoulli + Cd=0.68 | ✅ |
| 5 | SmokeLayerSolver | dh/dt = −(ṁ_p − ṁ_vent_out) / (ρ·A) | ✅ |
| 6 | SpeciesTransport | d(mYi)/dt = ṁ_gen + ṁ_in·Yi_in − ṁ_out·Yi | ✅ |
| 7 | CombustionModel | Growth → Vent-controlled → Decay | ✅ |
| 8 | DetectorPhysics (RTI) | RTI·dT/dt = T_gas − T_det | ✅ |
| 9 | WallThermalSolver | ∂T/∂t = α·∂²T/∂x² (implicit) | ✅ |
| 10 | SemiCFASTSolver | Coupled multi-compartment | ✅ |
| 11 | NumericalStability | Adaptive dt + mass correction + energy clip | ✅ |

**Key Physics Improvements:**
- Mass conservation enforced (not just temperature thresholds)
- Energy conservation with semi-implicit integration
- Ideal gas coupling: ρ = P/(R·T) consistently applied
- Heskestad plume with virtual origin correction (not simplified McCaffrey)
- Bi-directional vent flow with neutral plane (not unidirectional)
- Species transport: O2 consumption, CO2/CO/soot generation
- Ventilation-controlled combustion (O2 < 15% → HRR limited)
- RTI detector model per NFPA 72 §17.6.3 (not just threshold)
- Wall thermal response (1-D transient conduction)
- Multi-room coupling via vents (NOT independent per room)

**Comparison with Previous Implementation:**

| Component | Old (event-driven) | New (Semi-CFAST) |
|-----------|-------------------|------------------|
| Mass conservation | ❌ | ✅ |
| Energy conservation | ❌ | ✅ |
| Ideal gas coupling | ❌ | ✅ |
| Heskestad plume | ❌ (simplified McCaffrey) | ✅ |
| Bi-directional vent | ❌ | ✅ |
| Species transport | ❌ | ✅ |
| Vent-controlled combustion | ❌ | ✅ |
| RTI detector model | ❌ | ✅ |
| Wall thermal response | ❌ | ✅ |
| Numerical stability | Partial | ✅ |

**File:** twin/semi_cfast_engine.py (~1700 lines)
**Tests:** 45/45 PASSED in tests/test_semi_cfast_engine.py

**Commits:**
- Commit: 0ab67b3 | Link: https://github.com/ahmdelbaz28-ux/revit/commit/0ab67b3

### Instruction Validation (Critical Safety Rule)
- **STOP and WARN immediately** if instructions are:
  - Incorrect or will damage the codebase
  - Unclear, illogical, or contradictory
  - Missing critical context that affects the outcome
- **DO NOT execute** harmful instructions - alert user first
- Wait for confirmation before continuing after a warning

---

## Hardcoded Agent Instructions (ELITE)

The following instructions are **mandatory** for all tasks and **must not be modified**:

1. **ABSOLUTE TRUTH**: Never lie or claim to have done something that hasn't actually been done. If you cannot do something, say so clearly.
2. **NO UNAUTHORIZED CHANGES**: Do not modify any code not explicitly mentioned in the instructions.
3. **STOP ON ERRORS**: If you encounter a problem or error during execution, stop immediately and report the full issue.
4. **NEVER SELF-EDIT**: Do not fix anything on your own even if it appears wrong. Follow the instructions literally.
5. **EXPLAIN AFTER EACH STEP**: After each step you execute, briefly explain what you did and the result.
6. **ALWAYS USE `/workspace/project/revit/`**: Work in this path unless instructed otherwise.
7. **ASK BEFORE ACTING**: Any clarifying questions should be directed to the user before proceeding.
- Example: If instructions say "delete all files" → STOP and ask for confirmation