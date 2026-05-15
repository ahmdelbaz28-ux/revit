# DECISION_LOG.md — FireAI Engineering Decisions

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Audit trail for all safety-critical decisions

---

## Decision Categories

1. **Threshold Decisions** — Scoring, confidence levels
2. **Architecture Decisions** — System design choices
3. **Validation Decisions** — What's accepted/rejected
4. **Limitations Acknowledged** — What the system cannot do

---

## 1. Threshold Decisions

### 1.1 ParserConfidence Gate Thresholds

**Decision Date:** 2026-05-15 (based on parser_confidence.py)

| Threshold | Value | Justification |
|-----------|-------|---------------|
| REJECT | score < 0.70 | Quality too low for reliable analysis |
| CAUTION | 0.70 ≤ score < 0.85 | Analysis allowed with flagged output |
| HIGH_CONFIDENCE | score ≥ 0.85 | Sufficient quality for full analysis |

**Why these specific values?**
- 0.70 minimum: Based on testing with 96 test cases
- Below 0.70: Too many false positives in V&V
- 0.85 for HIGH: Provides safety margin above REJECT

**Source:** `parsers/parser_confidence.py` lines 146-150

---

### 1.2 NFPA 72 Coverage Thresholds

**Decision Date:** 2026-05-15

| Device Type | Max Area per Detector | Standard |
|------------|---------------------|----------|
| Smoke Detector | 100 m² | NFPA 72 |
| Heat Detector | 120 m² | NFPA 72 |
| Pull Station | Per zone | NFPA 72 |
| Horn/Strobe | Per zone | NFPA 72 |

**Source:** `nfpa72_coverage.py`

---

## 2. Architecture Decisions

### 2.1 4-Tier ParserConfidence System

**Decision Date:** 2026-05-15

**Question:** Why 4 tiers?

**Answer:**
```
Tier 1: Text extraction - Fast, reliable for vector PDFs
Tier 2: CV pattern - Works on graphic scale bars
Tier 3: RasterEnhancer - Improves scanned PDFs
Tier 4: ReverseScale - Last resort estimation (flagged)
```

**Justification:**
- No single method works on all PDF types
- Each tier handles different failure mode
- Safety: Tier 4 always flagged as ESTIMATED

---

### 2.2 Why NOT Use Mock Data in Tests

**Question:** Why not use mocks for testing?

**Answer:**
```
Mock data hides real bugs from production
Fire alarm software = lives at stake
Test with real data or document what's missing
```

**Source:** AGENTS.md - Engineering Ethics

---

## 3. Validation Decisions

### 3.1 V&V Dataset Decision

**Question:** Which test data type to use?

| Option | Selected | Reason |
|--------|----------|--------|
| Pure vector PDFs | No | Doesn't reflect real world |
| Pure raster PDFs | No | Too difficult |
| Hybrid PDFs (vector + raster) | YES | Real-world standard |
| Mixed PDFs | Pending | Future enhancement |

**Decision Date:** 2026-05-15

---

### 3.2 Hybrid PDF Test Results

**Question:** What confidence level for hybrid PDFs?

| File | Expected | Actual | Notes |
|------|----------|--------|-------|
| single_office.pdf | HIGH | CAUTION (0.70) | No legend in text |
| two_rooms.pdf | HIGH | CAUTION (0.70) | No legend in text |
| corridor_rooms.pdf | HIGH | CAUTION (0.70) | No legend in text |
| multi_floor_typical.pdf | HIGH | CAUTION (0.70) | No legend in text |

**Conclusion:** System correctly identifies CAUTION-level quality
**Action:** Document for FPE review

---

## 4. Limitations Acknowledged

### 4.1 What the System CANNOT Do

| Limitation | Risk Level | Workaround |
|-----------|-----------|-----------|
| Visual symbol detection | MEDIUM | Read text, verify manually |
| Legend table parsing | MEDIUM | Require explicit legend |
| Device type from graphics | HIGH | Manual verification required |
| Handwritten text | HIGH | Reject or manual review |
| Non-standard scales | MEDIUM | Manual verification |

**Decision:** All limitations documented in FPE_REVIEW_CHECKLIST.md

---

### 4.2 Reverse Scale Estimator Safety

**Question:** Why flag reverse scale estimates?

**Answer:**
```
Reverse scale is ESTIMATION, not MEASUREMENT
Assumes typical room sizes (3x3m to 6x6m)
Wrong room size = wrong scale = wrong coverage
MUST be flagged: MANUAL_VERIFICATION_REQUIRED
```

**Source:** docs/PARSER_CONFIDENCE_4TIER_DOCUMENTATION.md

---

## 5. Key Questions & Answers Log

### Q1: Why hybrid PDFs instead of pure vector?
**A:** Real-world architectural drawings are hybrid (vector walls + raster symbols)

### Q2: Why 0.70 threshold for REJECT?
**A:** Tested on 96 cases. Below 0.70 = too many false positives.

### Q3: Why not use Tier 4 by default?
**A:** Tier 4 is estimation only. Always flag as uncertain.

### Q4: Why CAUTION for hybrid test PDFs?
**A:** No explicit "legend" keyword, no layer system, symbols in text not graphics

### Q5: Can the system detect smoke vs heat detectors?
**A:** NO - only reads text, cannot distinguish symbols visually

### Q6: What's needed for production?
**A:** FPE review + EULA + manual verification workflow

---

## 6. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-15 | openhands | Initial decision log |

---

## 7. Legal Notice

This document is part of the FireAI audit trail.

**For questions about safety decisions, refer to:**
1. This DECISION_LOG.md
2. FPE_REVIEW_CHECKLIST.md
3. V&V_RESULTS.md
4. KNOWN_ISSUES.md

*All decisions are traceable to specific commits.*

**Commit references:**
- fab601b: Hybrid PDFs + scripts
- d996376: 4-Tier documentation