# V&V Protocol - Validation & Verification
## How to test 50+ fire alarm drawings systematically

---

## Purpose

This protocol defines how to verify the FireAlarm Engine on a diverse set of real drawings.
This is NOT a formal validation — it's a development dataset.

---

## Ground Rules

| Rule | Explanation |
|------|------------|
| **Beta = Beta** | Results need FPE review |
| **Data ≠ Certification** | More drawings = better system, but not certified |
| **Honest about limits** | If it fails, say it fails |

---

## Dataset Requirements

### Target: 50 diverse drawings

| Category | Count | Source |
|----------|-------|--------|
| Vector (CAD导出) | 20 | Modern projects |
| Raster (scanned) | 20 | Legacy projects |
| Mixed | 10 | Varies |

### Diversity Requirements

- **Building types**: Office, school, hospital, warehouse, residential
- **Scales**: 1/8", 1/4", 1:100, 1:50
- **Quality**: Excellent to poor
- **Regions**: US drawings (NFPA 72)

---

## Testing Protocol

### Phase 1: Collection

1. Source diverse PDFs (not just successful ones)
2. Include failures and edge cases
3. Document source and date

### Phase 2: Ground Truth

For each drawing, record:
- **Manual analysis**: What an engineer expects
- **System output**: What the engine produces
- **Comparison**: Match/dismatch

### Phase 3: Analysis

| Metric | Definition |
|--------|------------|
| **Detection Rate** | How often walls/symbols found |
| **Accuracy** | How close to manual |
| **Coverage** | Room/device matching |
| **False Positives** | Wrong detections |
| **Failures** | Complete rejections |

### Phase 4: Reporting

Report per category:
- Pass/Fail/Error counts
- Common failure modes
- Specific improvements needed

---

## Metrics Definition

### Pass Criteria

| Gate | Score | Meaning |
|------|-------|---------|
| HIGH_CONFIDENCE | ≥0.85 | Auto-processable |
| CAUTION | 0.70-0.84 | Needs review |
| REJECT | <0.70 | Failed gate |

### Success Metrics

| Metric | Target |
|--------|--------|
| Vector pass rate | >80% |
| Raster pass rate | >50% |
| Scale extraction | >70% |
| Coverage match | >80% |

---

## Safety Requirements

### For Beta Release

1. **EULA Required** - User must accept
2. **Beta Watermark** - On all outputs
3. **FPE Disclosure** - Clear message

### Not Release Until

- [ ] 20+ drawings tested
- [ ] >70% success rate
- [ ] FPE review process defined
- [ ] Error handling documented
- [ ] EULA accepted by test users

---

## Version History

| Version | Date | Changes |
|---------|------|--------|
| 1.0 | 2026-05-15 | Initial protocol |

---

*This is a development protocol, not a certification document.*