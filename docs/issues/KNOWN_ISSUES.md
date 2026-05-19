# KNOWN_ISSUES.md — FireAI Known Issues (HONEST VERSION)

**Version:** 1.1  
**Date:** 2026-05-15  
**Purpose:** Document ALL limitations - NO marketing

---

## CRITICAL: Symbol Detection Gap

### What We CAN Do:
- Read text from PDF (get_text)
- Detect vector lines (walls) 
- Calculate coverage areas

### What We CANNOT Do:
- Visual symbol detection - cannot distinguish smoke vs heat detector
- Graphical legend parsing - cannot read legend table images
- Shape recognition - cannot identify shapes automatically
- Circle detection - cannot tell "circle = smoke detector"

### FPE Question Expected:
**Q:** "How does the program know this circle is a smoke detector?"  
**A:** "Currently can't - requires PE REVIEW"

---

## Rating

| Component | Reality |
|-----------|----------|
| Code | Basic text search + geometry |
| "Elite" | Marketing - basic if/else + 16 keywords |
| "Closed programmatically" | True - no symbol detection |
| Symbol detection | MISSING - TODO |

---

## Action Items

1. Get real PDF → test text detection
2. Implement symbol detection → needs CV/shape matching
3. Document honestly in FPE review

---

## Disclaimer

This system provides ANALYSIS, not APPROVAL.  
All outputs require PE REVIEW.