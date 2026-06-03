# 🔍 Expert Audit Report — Finding #1: Smoke Detector Spacing NFPA Misalignment

**Audit ID:** V120
**Date:** 2026-06-03
**Auditor:** Arena Agent (Principal Engineer mode)
**Scope:** `compute_smoke_detector_spacing()` in `fireai/core/qomn_kernel.py` and 2 parallel implementations
**Severity:** 🟠 MEDIUM-HIGH — Correctness defect with cost-impact, but FAIL-SAFE direction (no life-safety regression)
**Status:** **NEEDS PROFESSIONAL ENGINEER (FPE) REVIEW BEFORE CODE FIX**

---

## ⚠️ Why This Is an Audit Report, Not a Code Fix

Per `agent.md` Rule #17 (NO HALF-SOLUTIONS — root-cause mandatory), I must
"never guess and patch." After deep investigation, the agent determined:

1. The defect is **real and reproducible** (evidence below)
2. The fix touches **a regulatory dataset** (NFPA 72 spacing values)
3. The repository contains **THREE PARALLEL implementations** with
   different values — fixing one creates more drift, not less
4. The correct canonical values require **professional judgment** that
   exceeds web research (NFPA 72-2022 is a paid standard; the agent
   used tertiary sources only)
5. Agent.md Rule #12: "Wrong code... is catastrophic — threatens human
   life. Zero tolerance for falsification or laziness"

**Therefore: this audit documents the defect, presents the evidence
chain, and proposes a fix plan — but defers actual data-table changes
to a licensed Fire Protection Engineer (FPE) review.**

A separate, narrow **safety-net change** IS being merged in V120
(WARNING log at high ceilings) as it is provably safe and surfaces the
underlying issue to system operators.

---

## 1. Defect Description

`fireai/core/qomn_kernel.py:compute_smoke_detector_spacing()` (lines
338–390 before V120) applies a **"1% per foot reduction above 10 ft"**
to smoke detector spacing values. The comment cites
`§17.7.3.2.3` of NFPA 72.

**Observed behavior** (from V117 baseline):

| Ceiling (ft) | Kernel returns | NFPA nominal | Extra Reduction |
|--------------|----------------|--------------|-----------------|
| 10 | 9.144 m | 9.144 m | 0% |
| 15 | 7.239 m | 9.144 m | 21% under |
| 20 | 5.212 m | 9.144 m | 43% under |
| 30 | 3.170 m | (out of spot scope) | n/a |
| 60 | 0.914 m | (out of spot scope) | n/a |

---

## 2. Evidence Chain (Why the Reduction Is Wrong)

### 2.1 Internal Project Evidence

The repository itself contains the **correct values** in three places
that contradict the kernel:

#### (a) `wiki/standards/nfpa72.md`
> "Section 17.7.3: Detector spacing — **smooth ceiling spacing is 9.1m
> (30ft) for smoke**, 7.0m for heat"

No mention of any per-foot reduction. This is the project's own
documentation of its NFPA implementation.

#### (b) `fireai/constants/__init__.py:43`
```python
SMOKE_MAX_SPACING_M: float = 9.10
"""Maximum listed spacing for smoke detectors on smooth flat ceilings
≤ 3.0m (10 ft). Per NFPA 72 Table 17.6.3.1.1."""
```

Centralized constants module uses **9.10 m flat** — no reduction.

#### (c) `qomn_fire/core/constants.py:6`
```python
NFPA_SMOKE_DETECTOR_SPACING_M = 9.144  # 30 feet smooth ceiling spacing
```

Sister module uses **9.144 m flat** — no reduction.

### 2.2 External Standards Evidence

#### (a) ECMAG (Electrical Contractor Magazine) — May 2022, by licensed FPE
Article: *"Using Smoke and Heat Detectors to Protect Difficult Areas"*
> *"Others will tell me the code has a table that reduces the spacing
> of smoke detectors as ceiling height increases so they follow that.
> **THERE IS NO SUCH TABLE.** They are referring to the table for heat
> detector spacing reduction... [which is] applicable only for flaming
> fires."*
>
> *"...never install spot-type smoke detectors on ceilings 20 feet or
> higher under any circumstances. In high ceiling environments, first
> determine what fire protection goal you are trying to meet. Then
> choose the appropriate smoke detection [technology]."*

#### (b) SFPE Europe Journal — Issue 33
Article: *"Closing the Gap: Design Guidance for Smoke Detector Spacing
on High Ceilings"*
> *"There is a table in NFPA 72 that is specific to heat detectors,
> but is **often misapplied to smoke detectors**, which leads to
> confusion and inconsistencies in design and code enforcement."*

#### (c) NFPA Research Foundation — Smoke Detector Spacing in High Ceiling Spaces Phase II (2023)
> *"The distance between smoke detectors must not exceed a nominal
> spacing of 30 ft (9.1 m)...All points on the ceiling are required
> to have a detector within one-half... Although the 30 ft (9.1 m)
> spacing criterion is a requirement, NFPA 72 section 17.7.1.3 permits
> designers to use any other spacing they deem appropriate as a
> performance-based alternative."*

#### (d) NFPA 72-2022 §17.7.3.2.3.1 (cited verbatim in ECMAG)
> "In the absence of specific performance-based design criteria, one
> of the following requirements shall apply:
> (1) The distance between smoke detectors shall not exceed a
>     nominal spacing of 30 ft (9.1 m)...
> (2) All points on the ceiling shall have a detector within a
>     distance equal to or less than 0.7 times the nominal 30 ft
>     (9.1 m) spacing (0.7S)."

§17.7.3.2.3.3 PERMITS (not REQUIRES) other spacing — this is the
AHJ/FPE judgment door, **not a mechanical 1%/foot reduction formula**.

### 2.3 Root Cause (with 95% confidence)

The kernel formula `S = S_table × (1 − 0.01 × feet_above_10ft)` is a
misapplication of **Table 17.6.3.5.1 — Heat Detector Spacing Reduction
Based on Ceiling Height**. That table:
- Applies **only to heat detectors** (per ECMAG and SFPE Europe)
- Models the physics of **flaming fires** (thermal plume rise rate)
- Does not appear in the smoke detector section §17.7.3 / §17.7.4

The smoke detector physics is dominated by **stratification** (NFPA 72
§17.7.1.11), which is a **discontinuous step phenomenon**, not a linear
1%/foot scaling. The correct engineering response above ~20 ft is to
switch technologies (beam, aspirating) or perform a performance-based
analysis per Annex B — never to scale spot-detector spacing.

---

## 3. Architectural Defect (Discovered During Investigation)

The repository contains **THREE distinct, divergent implementations**
of NFPA 72 smoke detector spacing:

| # | File | Table name | Rows | h≤3m → S | h=4.6m → S | Method |
|---|------|------------|------|----------|------------|--------|
| 1 | `fireai/core/qomn_kernel.py` | `NFPA72_SMOKE_SPACING_TABLE` | 10 | 9.144 | 7.620 | Table lookup + 1%/ft reduction |
| 2 | `fireai/core/nfpa72_technology_dispatcher.py` | `_NFPA72_SMOKE_SPACING_TABLE` | 9 | 9.10 | 8.20 | Pre-reduced table, no scalar adjust |
| 3 | `fireai/core/nfpa72_calculations.py` | `_NFPA72_TABLE_17_6_3_1_1` | 9 | 9.10 | 8.20 | Same as #2 but bundled with heat |
| 4 | `fireai/constants/__init__.py` | `SMOKE_MAX_SPACING_M` | scalar | 9.10 | 9.10 | **No reduction** |
| 5 | `wiki/standards/nfpa72.md` | Documentation | n/a | 9.1 | 9.1 | **No reduction** |

**Tables #2 and #3 also implement reduction (likely from the same
misapplication), but with different numeric values than #1.**

This is a **violation of agent.md Priority #7 (Traceability)** and
Rule #6 (single source of truth). Picking which of these to keep
is an engineering judgment that must involve the FPE who originally
authored the project.

---

## 4. Behavioral Impact Analysis

### 4.1 Safety Direction (Critical for Decision)
**The defect is in the FAIL-SAFE direction:**
- Kernel returns SMALLER spacings → MORE detectors required
- More detectors = MORE detection coverage = SAFER, not less safe
- A building designed using these numbers will have **excess** smoke
  detection coverage, not insufficient

### 4.2 Negative Impacts (Why It's Still a Defect)
1. **Code traceability violated**: An AHJ inspector cannot reconcile
   the kernel's output with NFPA 72 §17.7.3.2.3 directly. The output
   "fails the back-of-envelope check" — a sophisticated AHJ will
   reject the design as "code-incorrect" even though it's conservative.
2. **Economic harm**: Over-densification by 4× at 60ft = significant
   unnecessary equipment, installation, and maintenance cost.
3. **Misleads engineers**: Junior engineers using this kernel as a
   reference will internalize the wrong rule, propagating the defect
   to designs not produced by FireAI.
4. **False precision**: Returning values for 60ft ceilings implies
   the system supports such designs prescriptively. Per ECMAG/SFPE,
   spot smoke detection is unsuitable above 20ft and requires a
   technology change or performance-based design.

### 4.3 Cannot-Verify-Currently
- Whether existing FireAI-produced designs in the field rely on these
  numbers
- Whether any AHJ has already accepted designs based on this output
- Whether the original FPE who authored this project intended this as
  a "safety-margin" rule (conservative over-design as policy)

---

## 5. Proposed Remediation Plan (Phased)

### Phase A — Immediate Safety Net (✅ MERGED IN V120)
**Scope:** WARNING log only. No data table changes.

Add a `logger.warning()` in `compute_smoke_detector_spacing()` when
ceiling height > 6.096 m (20 ft), text matching ECMAG guidance.
This surfaces the regulatory concern to operators without changing
any numbers, preserving backward compatibility for any in-flight
projects.

**Risk:** ZERO — additive logging only.

### Phase B — FPE Review (REQUIRES OPERATOR ACTION)
**Scope:** Engineering decision on canonical NFPA values.

Operator must engage a licensed Fire Protection Engineer to:
1. Review this audit report against NFPA 72-2022 §17.7.3 verbatim text
2. Determine the canonical spacing table for FireAI
3. Decide whether tables #2 and #3 should be removed, modified, or
   unified into a single source of truth
4. Sign off on the chosen approach with their PE number recorded

### Phase C — Code Implementation (POST-FPE)
**Scope:** Implement the FPE-approved fix.

Likely changes (subject to FPE direction):
1. Replace 3 tables with 1 canonical source (likely
   `fireai/constants/__init__.py`)
2. Remove or replace the 1%/ft reduction in `qomn_kernel.py`
3. Add high-ceiling rejection or technology dispatch
4. Update tests for new expected values (anti-pattern tests in
   `test_qomn_integration.py:444` will fail and must be replaced)
5. Migration notes for any consumers of the old behavior

### Phase D — Cross-Reference Cleanup
**Scope:** Align all related modules.

1. `nfpa72_technology_dispatcher.py` — update table or remove
2. `nfpa72_calculations.py` — update table or remove
3. `qomn_fire/core/constants.py` — verify alignment
4. `wiki/standards/nfpa72.md` — confirm matches code

---

## 6. Agent Self-Assessment (per Rule #21)

**Agent confidence in audit findings:** 95%
- Internal evidence (wiki, constants module) confirms the formula is wrong
- 4 independent external sources (ECMAG, SFPE, NFPA Research, forum
  quoting NFPA 72 verbatim) confirm "no such table exists"
- Architectural defect (3 parallel implementations) is directly
  verifiable from grep results

**Agent confidence in proposed canonical values:** 50%
- The agent does NOT have NFPA 72-2022 PDF
- Internal `nfpa72_technology_dispatcher.py` table differs from §17.7.3
  verbatim and may itself be wrong
- FPE judgment required to select the canonical implementation

**Why the agent stops here:**
Per Rule #17: *"If the agent cannot identify the root cause with
confidence, it MUST research further before acting — never guess and
patch."* The agent has identified the root cause (95%) but cannot
identify the correct numerical replacement with sufficient confidence.
Picking arbitrary values from a tertiary source for a safety-critical
NFPA table would be **engineering negligence**, the exact failure mode
the agent.md V17 self-criticism (line 711) calls out: "Temperature-
only checking was engineering negligence... I will never again accept
a simplified model without checking the underlying physics."

---

## 7. Action Items

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Audit report (this file) | Agent | ✅ Complete |
| 2 | Phase A — WARNING log safety net | Agent | ✅ Complete (V120) |
| 3 | Phase B — FPE review of audit | Operator | ⏳ Pending |
| 4 | Phase C — Implement FPE-approved fix | Agent (post-FPE) | ⏸ Blocked on (3) |
| 5 | Phase D — Cross-module cleanup | Agent (post-FPE) | ⏸ Blocked on (3) |

---

## 8. References

1. NFPA 72-2022, *National Fire Alarm and Signaling Code*, Section
   17.7.3.2.3 (Smooth Ceiling Spacing for Spot-Type Smoke Detectors)
2. ECMAG, *Using Smoke and Heat Detectors to Protect Difficult Areas*,
   May 2022 — https://www.ecmag.com/magazine/articles/article-detail/integrated-systems-using-smoke-and-heat-detectors-protect-difficult-areas
3. SFPE Europe Journal Issue 33, *Closing the Gap: Design Guidance for
   Smoke Detector Spacing on High Ceilings* (2023)
4. NFPA Research Foundation, *Smoke Detector Spacing in High Ceiling
   Spaces Phase II*, August 2023
5. NFPA 72-2022 §17.7.1.11 (Stratification effects)
6. Repository internal: `wiki/standards/nfpa72.md`,
   `fireai/constants/__init__.py`
