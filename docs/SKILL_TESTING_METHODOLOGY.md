# Skill A/B Testing Methodology — FireAI Adaptation

> **Source attribution**: Adapted (NOT copied) from
> `harness/skills/harness/references/skill-testing-guide.md` (Apache-2.0).
> The original is a Korean-language methodology guide for Claude Code
> skill testing. This document translates the IDEAS into concrete
> FireAI-applicable patterns.

## Why A/B Testing for Skills?

The harness project's key insight: **you can't know if a skill/prompt/agent
improves quality without comparing it against a baseline.** Subjective
"this looks better" reviews are unreliable — you need parallel execution
with the SAME input, then compare outputs against assertion-based grading.

## Methodology

### 1. Define the Test Prompt

Use a REAL user-like prompt, not an artificial one:

**Bad** (artificial):
```
"Test the NFPA 72 calculations"
```

**Good** (realistic):
```
"A 15m × 20m office room with 3.5m ceiling height needs smoke detector
placement per NFPA 72. Calculate the number of detectors and their
positions. The room has a flat ceiling with no beams."
```

### 2. Spawn Two Parallel Agents

```
Agent A (with skill):  Load the FireAI skill + run the prompt
Agent B (baseline):    Run the prompt WITHOUT the skill (raw Claude)
```

Both agents get the EXACT same prompt. Run them in parallel (background)
to save time.

### 3. Grade with Assertions (NOT subjective review)

Create a `grading.json` before running the test:

```json
{
  "test_id": "nfpa72-detector-count-15x20-3.5m",
  "prompt": "A 15m × 20m office room...",
  "assertions": [
    {
      "id": "A1",
      "text": "Output mentions 6 smoke detectors (ceil(15/9.1) × ceil(20/9.1) = 2×3 = 6)",
      "passed": null,
      "evidence": ""
    },
    {
      "id": "A2",
      "text": "Output cites NFPA 72 §17.6.3.1.1 for spacing",
      "passed": null,
      "evidence": ""
    },
    {
      "id": "A3",
      "text": "Output uses R = 0.7 × S = 6.37m coverage radius",
      "passed": null,
      "evidence": ""
    },
    {
      "id": "A4",
      "text": "Output does NOT recommend AWG 18 wire (illegal for FA circuits)",
      "passed": null,
      "evidence": ""
    }
  ]
}
```

### 4. Compare Results

| Metric | Agent A (with skill) | Agent B (baseline) |
|--------|---------------------|-------------------|
| Assertions passed | 4/4 | 2/4 |
| NFPA 72 citation | ✅ Correct §17.6.3.1.1 | ❌ Cited §17.6.3 (wrong) |
| AWG recommendation | ✅ AWG 14 (legal) | ❌ AWG 18 (illegal) |
| Detector count | ✅ 6 | ✅ 6 |

### 5. Non-Discriminating Assertion Warning

**Bad assertion** (always passes, tells you nothing):
```
"Output contains a number"
```

**Good assertion** (discriminates between correct and incorrect):
```
"Output contains exactly 6 as the detector count"
```

### 6. Iterate

If Agent A fails an assertion:
1. Fix the skill (SKILL.md or reference docs)
2. Re-run the A/B test
3. Confirm the fix didn't break other assertions

Termination condition: 3 consecutive iterations with 0 new failures,
OR max 5 iterations.

## FireAI-Specific Test Cases

### Test Case 1: NFPA 72 Detector Placement
- **Prompt**: Room dimensions + ceiling type → detector count + positions
- **Assertions**: Count, spacing citation, coverage radius, wall distance

### Test Case 2: Voltage Drop Calculation
- **Prompt**: Circuit specs (24V, 0.5A, 50m cable) → voltage drop + compliance
- **Assertions**: Drop ≤10% (PLFA) or ≤20% (NAC), correct formula, AWG selection

### Test Case 3: Battery Capacity Sizing
- **Prompt**: Standby + alarm currents → required Ah capacity
- **Assertions**: 24h standby minimum, 5min alarm, safety factor ≥1.20

### Test Case 4: AWG Wire Selection
- **Prompt**: Load + distance → recommended AWG gauge
- **Assertions**: AWG ≥14 (NEC 760.71), drop within limit, device voltage ≥16V

### Test Case 5: CSRF Token Flow
- **Prompt**: API interaction requiring CSRF token
- **Assertions**: Token obtained from /api/csrf-token, token sent as X-CSRF-Token,
  403 on missing/invalid token, token consumed after use

## Integration with FireAI CI

This methodology can be integrated into the CI pipeline as a new gate
(Gate 8 — Skill Quality) once the skills are mature enough. For now,
it's a manual process run before each skill release.

## License

This methodology is adapted from the harness project (Apache-2.0).
The adaptation is original work for FireAI and does not include any
copied code — only translated ideas and patterns.
