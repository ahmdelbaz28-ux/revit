# Known Issues — FireAI V9.6

**Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Document all known limitations

---

## ParserConfidence Limitations

### 1. Hybrid PDFs without raster symbols = CAUTION

- **Issue:** Generated hybrid PDFs get CAUTION not HIGH
- **Reason:** No raster symbols, legend, or layers
- **Resolution:** Expected behavior - document in V&V_RESULTS.md
- **Impact:** MEDIUM - Workaround exists

### 2. Visual Symbol Detection Not Implemented

- **Issue:** Cannot distinguish smoke vs heat detector symbols
- **Reason:** Text-only extraction, no CV
- **Resolution:** Future work
- **Impact:** HIGH - Manual verification required

### 3. Legend Parsing Not Implemented

- **Issue:** Cannot parse legend table (symbol = meaning)
- **Resolution:** Require explicit "legend" keyword
- **Impact:** MEDIUM - User awareness needed

### 4. ReverseScaleEstimator = Fallback Only

- **Issue:** Estimates scale from room size
- **Resolution:** Always flag as ESTIMATED
- **Impact:** HIGH if not flagged

---

## Safety Warnings

### ALL Outputs Require PE Review

- **Warning:** Regardless of score, all outputs require Professional Engineer review
- **CAUTION:** Means "analyze but flag uncertainty"
- **REJECT:** Means "do not proceed without manual verification"
- **HIGH:** Means "sufficient quality" - still requires review

---

## Workarounds

| Scenario | Workaround |
|----------|-----------|
| CAUTION result | Verify manually before use |
| No scale found | Check manually, request updated PDF |
| Symbol unclear | Verify against legend manually |
| Reverse scale flagged | MANUAL_VERIFICATION_REQUIRED |

---

## Resolution Timeline

| Issue | Status | ETA |
|-------|--------|-----|
| Visual symbol detection | Future | TBD |
| Legend parsing | Future | TBD |
| ReverseScale safety | Done | Done |

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-15 | 1.0 | Initial known issues |