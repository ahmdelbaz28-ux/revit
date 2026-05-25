# Decision Log — FireAI V9.6

**Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Audit trail for safety-critical decisions

---

## 2026-05-15 15:31 — Threshold Choice

- **Question:** Why 0.7 for REJECT, 0.85 for HIGH?
- **Answer:** 
  - 0.7 = safety margin for raster uncertainty
  - 0.85 = high confidence requires all checks
- **Decision:** Keep thresholds. Document in 4-tier docs.
- **Commit:** d996376
- **Source:** parsers/parser_confidence.py lines 146-150

---

## 2026-05-15 15:31 — Hybrid PDF Results

- **Question:** 4/4 CAUTION — is this acceptable?
- **Answer:** 
  - Yes. CAUTION = "analyze with PE review"
  - HIGH requires raster symbols + legend
- **Decision:** Document CAUTION as expected behavior
- **Commit:** d996376

---

## 2026-05-15 15:31 — 4-Tier System Necessity

- **Question:** Why 4 tiers needed?
- **Answer:**
  - No single method works on all PDF types
  - Each tier handles different failure mode
  - Tier 1: Text (fast, vector PDFs)
  - Tier 2: CV pattern (graphic scale bars)
  - Tier 3: RasterEnhancer (scanned PDFs)
  - Tier 4: ReverseScale (last resort, always flagged)
- **Decision:** Maintain 4-tier approach
- **Commit:** d996376

---

## 2026-05-15 15:31 — ReverseScale Safety

- **Question:** Why flag reverse scale estimates?
- **Answer:**
  - Reverse scale is ESTIMATION, not MEASUREMENT
  - Assumes typical room sizes (3x3m to 6x6m)
  - Wrong room = wrong scale = wrong coverage calculations
- **Decision:** ALWAYS flag as: MANUAL_VERIFICATION_REQUIRED
- **Safety Notice:** This is critical for life safety
- **Commit:** d996376

---

## 2026-05-15 15:31 — Symbol Detection Gap

- **Question:** Can parser detect smoke vs heat detector symbols?
- **Answer:** NO
  - System reads text only
  - Cannot distinguish visual symbols
  - Only detects keywords in text ("smoke", "heat")
- **Limitation:** Document in KNOWN_ISSUES.md
- **Workaround:** Require explicit legend + manual verification
- **Commit:** d996376

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-15 | 1.0 | Initial decision log |