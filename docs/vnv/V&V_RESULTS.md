# V&V Results — Hybrid PDFs

**Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Document test results on hybrid PDFs

---

## Test Environment

| Parameter | Value |
|-----------|-------|
| Framework | PyMuPDF |
| Parser | ParserConfidence |
| Date | 2026-05-15 |
| Python | 3.13 |

---

## Results Table

| File | Gate | Score | Scale | Walls | Devices | Date |
|------|------|-------|-------|-------|---------|------|
| single_office.pdf | CAUTION | 0.70 | 1:100 | 12 | 1 | 2026-05-15 |
| two_rooms.pdf | CAUTION | 0.70 | 1:100 | 18 | 2 | 2026-05-15 |
| corridor_rooms.pdf | CAUTION | 0.70 | 1:100 | 24 | 3 | 2026-05-15 |
| multi_floor_typical.pdf | CAUTION | 0.70 | 1:100 | 30 | 4 | 2026-05-15 |

---

## Summary

- **Result:** 0/4 HIGH, 4/4 CAUTION
- **Reason:** Missing raster symbols, legend, layers
- **Conclusion:** System correctly identifies CAUTION-level quality

---

## Scoring Breakdown

### single_office.pdf

| Criterion | Score | Max |
|-----------|-------|-----|
| File Quality | 0.1 | 0.4 |
| Completeness | 0.6 | 0.6 |
| **TOTAL** | **0.70** | **1.0** |

### Why 0.70 = CAUTION?

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

## Action Items

- [ ] Expand V&V dataset with real PDFs
- [ ] Test with professional CAD exports
- [ ] Include explicit legend keyword

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-15 | 1.0 | Initial V&V results |