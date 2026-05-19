# FPE_REVIEW_CHECKLIST.md — Fire Protection Engineer Review

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Protocol for FPE to review and verify FireAI system

---

## 1. Pre-Review Requirements

### 1.1 Documents to Review

| Document | Path | Status |
|----------|------|--------|
| DECISION_LOG.md | docs/ | ✅ Required |
| PARSER_CONFIDENCE_4TIER_DOCUMENTATION.md | docs/ | ✅ Required |
| V&V_RESULTS.md | docs/ | ✅ Required |
| KNOWN_ISSUES.md | docs/ | ✅ Required |
| AGENTS.md | . | ✅ Required |

### 1.2 Code to Review

| Component | File | Purpose |
|-----------|------|---------|
| ParserConfidence | parsers/parser_confidence.py | Gate decision logic |
| NFPA 72 Coverage | nfpa72_coverage.py | Coverage calculation |
| Geometry Extractor | parsers/geometry_extractor.py | Wall extraction |

---

## 2. Review Protocol

### 2.1 ParserConfidence Review

**What to verify:**

- [ ] Threshold values in code match DECISION_LOG.md
- [ ] Score calculation algorithm is correct
- [ ] Gate decisions (REJECT/CAUTION/HIGH) are proper
- [ ] Safety flags are present

**How to verify:**
```bash
# Check thresholds in code
grep -n "0.70\|0.85" parsers/parser_confidence.py
```

### 2.2 NFPA 72 Coverage Review

**What to verify:**

- [ ] Max area per detector matches NFPA 72 2022
- [ ] Coverage calculations are correct for room sizes
- [ ] Device counts are accurate

**How to verify:**
```bash
# Run coverage tests
pytest tests/test_nfpa72*.py -v
```

### 2.3 Test Results Review

**What to verify:**

- [ ] 96 tests passing
- [ ] No false positives in edge cases
- [ ] Edge cases documented (oblivion, apocalypse, etc.)

**How to verify:**
```bash
# Run all tests
pytest tests/ -v
```

---

## 3. Safety Verification Checklist

### 3.1 Critical Safety Items

| Item | Check | Pass/Fail |
|------|-------|-----------|
| REJECT threshold prevents garbage in | Code review | ___ |
| CAUTION flags outputs properly | Code review | ___ |
| ReverseScale always flagged | Code review | ___ |
| No false coverage claims | Test review | ___ |
| Scale always verified | Code review | ___ |

### 3.2 NFPA 72 Compliance

| Item | Standard | Check | Pass/Fail |
|------|---------|-------|-----------|
| Smoke detector area | 100 m² max | Code | ___ |
| Heat detector area | 120 m² max | Code | ___ |
| Pull station spacing | Per zone | Code | ___ |
| Notification appliances | Per zone | Code | ___ |

---

## 4. Findings Form

### 4.1 Issues Found

| Issue # | Description | Severity | Recommended Fix |
|---------|------------|----------|----------------|
| 1 | | | | |
| 2 | | | |
| 3 | | | |

### 4.2 Recommendations

| # | Recommendation | Priority |
|----|-------------|----------|
| 1 | | |
| 2 | | |
| 3 | | | |

---

## 5. Sign-Off

**FPE Name:** ___________________________

**License #:** ___________________________

**Date:** ___________________________

**Signature:** ___________________________

---

## 6. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-15 | Initial checklist |