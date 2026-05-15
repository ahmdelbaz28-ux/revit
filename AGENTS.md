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

### Input Layer Implementation (2026-05-15)

**Issue:** Engine was blind - could calculate coverage but couldn't see real drawings.

**Solution:** Built complete input layer:
1. ParserConfidence Gate - evaluates PDF before engine (REJECT/CAUTION/HIGH)
2. GeometryExtractor - extracts walls from vector paths
3. SymbolExtractor - extracts NFPA 170 device symbols from text
4. PDFInputLayer - integrates all extractors

**Key insight:** PyMuPDF `draw_rect()` returns `type='s'` (stroke), not `'re'`. Use bounding rect for wall extraction since detailed path items are not returned.

**Tests:** 38 tests added - all passing. Zero tolerance for unqualified drawings.

**Files added:**
- parsers/parser_confidence.py
- parsers/geometry_extractor.py
- parsers/symbol_extractor.py
- parsers/pdf_input_layer.py

**Commits:**
- Commit: 028122b10c86c4093075797f6e7670f9974ff34b | Link: https://github.com/ahmdelbaz28-ux/revit/commit/028122b10c86c4093075797f6e7670f9974ff34b
- Commit: 2865da6299e4b5409c10008d55629e690ca7676e | Link: https://github.com/ahmdelbaz28-ux/revit/commit/2865da6299e4b5409c10008d55629e690ca7676e

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