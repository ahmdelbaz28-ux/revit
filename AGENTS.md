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
- No assumption - always test and verify
- Be explicit about limitations

### Code ReviewMandatory
- Before submitting any change, verify it yourself
- If unsure, test locally first
- Don't assume "it will work" - prove it works

### Instruction Validation (Critical Safety Rule)
- **STOP and WARN immediately** if instructions are:
  - Incorrect or will damage the codebase
  - Unclear, illogical, or contradictory
  - Missing critical context that affects the outcome
- **DO NOT execute** harmful instructions - alert user first
- Wait for confirmation before continuing after a warning
- Example: If instructions say "delete all files" → STOP and ask for confirmation