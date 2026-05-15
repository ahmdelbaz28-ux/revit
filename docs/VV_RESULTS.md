# V&V Results - FireAlarm Engine Beta

## Test Summary (2026-05-15)

| Category | Count | % |
|----------|-------|---|
| HIGH_CONFIDENCE | 1 | 7% |
| CAUTION | 5 | 36% |
| REJECT | 8 | 57% |

### V&V Dataset

**Real Projects** (5 PDFs):
| Drawing | Score | Gate | Result |
|---------|-------|------|--------|
| kcha_fireAlarm | 1.00 | HIGH | PASS |
| fire_alarm_sample | 0.50 | REJECT | No scale |
| leicester | 0.30 | REJECT | Low quality |
| montana | 0.20 | REJECT | Low quality |
| usc_center | 0.00 | REJECT | Empty |

**Test PDFs** (14 PDFs):
| Drawing | Score | Gate | Rooms | Devices |
|---------|-------|------|-------|----------|
| test_full | 0.90 | HIGH | 2 | 13 |
| project_0 | 0.70 | CAUTION | 1 | 1 |
| project_1 | 0.70 | CAUTION | 1 | 1 |
| project_2 | 0.70 | CAUTION | 1 | 1 |
| test | 0.70 | CAUTION | 1 | 3 |

### Safety Compliance

- BETA flag on all outputs ✅
- EULA required ✅
- FPE review required ✅
- 95% confidence threshold for raster ✅

### Lead Engineer

**AhmedElbaz** - 2026-05-15
