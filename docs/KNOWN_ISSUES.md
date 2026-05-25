# KNOWN_ISSUES.md — FireAI Known Issues and Workarounds

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Document all known limitations and workarounds

---

## 1. ParserConfidence Issues

### 1.1 Cannot Detect Visual Symbols

| Issue | Description |
|-------|------------|
| Problem | System reads text, cannot detect visual symbols |
| Impact | Cannot distinguish smoke vs heat detector symbols |
| Risk | MEDIUM - Requires manual verification |
| Workaround | Require explicit legend in text |

**Technical Details:**
- PyMuPDF `get_text()` extracts text only
- Visual detection requires CV/image processing
- Current system cannot classify circle = smoke vs heat

---

### 1.2 Legend Not Parsed

| Issue | Description |
|-------|------------|
| Problem | Cannot parse legend table (symbol = meaning) |
| Impact | Loses 0.1-0.2 score |
| Risk | LOW |
| Workaround | Ensure "legend" keyword in text, manually verify symbols |

---

### 1.3 Layer Detection Limited

| Issue | Description |
|-------|------------|
| Problem | ReportLab PDFs lack layer system |
| Impact | Loses 0.1 score on generated PDFs |
| Risk | LOW - Only affects test PDFs |
| Workaround | Use professional CAD software |

---

## 2. NFPA 72 Coverage Issues

### 2.1 Room Geometry Assumptions

| Issue | Description |
|-------|------------|
| Problem | Assumes rectangular rooms |
| Impact | Complex room shapes may have errors |
| Risk | MEDIUM |
| Workaround | Manual verification for non-rectangular rooms |

---

### 2.2 Device Spacing

| Issue | Description |
|-------|------------|
| Problem | Per-zone spacing not fully implemented |
| Impact | Pull station spacing may be inaccurate |
| Risk | MEDIUM |
| Workaround | Manual zone verification |

---

## 3. Test Data Issues

### 3.1 Generated PDFs Not Real

| Issue | Description |
|-------|------------|
| Problem | Hybrid test PDFs are programmatically generated |
| Impact | Missing professional CAD features |
| Risk | LOW - Test data only |
| Workaround | Use real PDFs for production V&V |

---

### 3.2 Limited V&V Dataset

| Issue | Description |
|-------|------------|
| Problem | Only 4 hybrid test PDFs available |
| Impact | Limited statistical significance |
| Risk | MEDIUM |
| Workaround | Expand dataset with real PDFs |

---

## 4. Architectural Issues

### 4.1 Reverse Scale Estimation

| Issue | Description |
|-------|------------|
| Problem | Estimates scale from room size, not direct measurement |
| Impact | May be inaccurate |
| Risk | HIGH - Always flagged |
| Workaround | ALWAYS flag as: MANUAL_VERIFICATION_REQUIRED |

---

### 4.2 Non-Standard Scales

| Issue | Description |
|-------|------------|
| Problem | Only handles common scales (1:50, 1:100, 1:200) |
| Impact | May fail on unusual scales |
| Risk | MEDIUM |
| Workaround | Manual scale verification |

---

## 5. Priority Issue List

### 5.1 High Priority (Fix Before Production)

| Issue | Owner | ETA |
|------|-------|-----|
| Visual symbol detection | Future | TBD |
| ReverseScale safety flag | Done | Done |
| FPE review | You | TBD |

### 5.2 Medium Priority (Fix in Next Release)

| Issue | Owner | ETA |
|------|-------|-----|
| Legend parsing | Future | TBD |
| Non-rectangular rooms | Future | TBD |
| Extended scale support | Future | TBD |

### 5.3 Low Priority (Nice to Have)

| Issue | Owner | ETA |
|------|-------|-----|
| Layer detection | Future | TBD |
| Handwritten text | Future | TBD |
| More V&V data | Future | TBD |

---

## 6. Workaround Summary

### For Users

| Scenario | Workaround |
|----------|-----------|
| CAUTION result | Verify manually before use |
| No scale found | Check manually, request updated PDF |
| Symbol unclear | Verify against legend manually |
| Reverse scale flagged | MANUAL_VERIFICATION_REQUIRED |

### For FPEs

| Scenario | Workaround |
|----------|-----------|
| Review needed | Use FPE_REVIEW_CHECKLIST.md |
| Questions | Start with DECISION_LOG.md |
| Test data | Use V&V_RESULTS.md |

---

## 7. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-15 | Initial known issues |