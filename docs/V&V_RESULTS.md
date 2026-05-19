# V&V_RESULTS.md — Verification & Validation Results

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Document all V&V test results for FPE review

---

## 1. Test Summary

| Category | Tests | Status |
|----------|-------|--------|
| Unit Tests | 56 files | To be run |
| Integration Tests | Multiple | To be run |
| Hybrid PDF Tests | 4 | CAUTION |

---

## 2. Hybrid PDF Test Results

### 2.1 Test Configuration

| Parameter | Value |
|-----------|-------|
| Test Framework | PyMuPDF |
| Parser | ParserConfidence |
| Date | 2026-05-15 |
| Environment | Python 3.13 |

### 2.2 Results Table

| File | Gate | Score | Scale | Walls | Area | Devices |
|------|------|-------|-------|-------|------|---------|
| single_office.pdf | CAUTION | 0.70 | 1:100 | 12 | 12m² | 1 |
| two_rooms.pdf | CAUTION | 0.70 | 1:100 | 18 | 36m² | 2 |
| corridor_rooms.pdf | CAUTION | 0.70 | 1:100 | 24 | 67m² | 3 |
| multi_floor_typical.pdf | CAUTION | 0.70 | 1:100 | 30 | 57m² | 4 |

### 2.3 Analysis

**Why CAUTION?**
1. No explicit "legend" keyword in text
2. No layer system in generated PDFs
3. NFPA symbols present in text only (not as graphics)
4. Mixed format (vector walls + text)

**Conclusion:** System correctly identifies CAUTION-level quality

---

## 3. Expected vs Actual Results

### 3.1 Expected (理想)

| File | Expected Gate |
|------|---------------|
| single_office.pdf | HIGH |
| two_rooms.pdf | HIGH |
| corridor_rooms.pdf | HIGH |
| multi_floor_typical.pdf | HIGH |

### 3.2 Actual (实际)

| File | Actual Gate | Reason |
|------|------------|--------|
| single_office.pdf | CAUTION | No legend, symbols in text only |
| two_rooms.pdf | CAUTION | No legend, symbols in text only |
| corridor_rooms.pdf | CAUTION | No legend, symbols in text only |
| multi_floor_typical.pdf | CAUTION | No legend, symbols in text only |

### 3.3 Gap Analysis

| Issue | Impact | Recommendation |
|-------|--------|--------------|
| No "legend" keyword | -0.1 score | Add legend to PDFs |
| Symbols in text not graphics | Cannot verify device type | Manual verification |
| No layer system | -0.1 score | Use professional CAD |

---

## 4. Scoring Breakdown

### 4.1 single_office.pdf

| Criterion | Score | Max |
|-----------|-------|-----|
| File Quality | 0.1 | 0.4 |
| - Mixed (vector + text) | +0.1 | |
| Completeness | 0.6 | 0.6 |
| - Scale found | +0.3 | |
| - NFPA keywords | +0.2 | |
| - Device info | +0.1 | |
| **TOTAL** | **0.70** | **1.0** |

### 4.2 Why 0.70 is CAUTION?

From parser_confidence.py:
```python
if final < 0.70:
    gate = REJECT
elif final < 0.85:
    gate = CAUTION
else:
    gate = HIGH_CONFIDENCE
```

0.70 = boundary value → CAUTION (correct behavior)

---

## 5. Recommendations

### 5.1 For PDFs to Achieve HIGH

| Requirement | Current | Needed |
|-------------|---------|---------|
| Scale in text | ✅ YES | Already present |
| Legend keyword | ❌ NO | Add "Legend:" section |
| NFPA symbols as graphics | ❌ NO | Add visual symbols |
| Layer system | ❌ NO | Use professional CAD |

### 5.2 For Better V&V

1. Use real architectural PDFs (not generated)
2. Test with professional CAD exports
3. Test with scanned PDFs (raster)
4. Include explicit legends

---

## 6. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-15 | Initial V&V results |