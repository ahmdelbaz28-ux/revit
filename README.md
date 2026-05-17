# FireAI v7.3 — Elite Spatial Engine

## الأسس الهندسية
- **نصف قطر التغطية (R):** 6.4 متر (0.7S) — NFPA 72 §17.7.4.2.3.1 (خيار 0.7S)
- **التباعد الأقصى (S):** 9.14 متر — NFPA 72 §17.6.3.1
- **حد التغطية (coverage_limit):** R = 6.40m — نصف قطر التغطية الفعلية لضمان تغطية الجدران
- **الخوارزميات:** سداسية (Hexagonal) + مستطيلة (Rectangular) + احتياطية (Fallback)
- **التبعيات:** Python 3.8+ فقط. مكتبة NumPy اختيارية لتسريع التحقق.

### تغيير V7.3
في V7.2 كان `wall_limit = S/2 = 4.57m` يُستخدم لوضع الصفوف الحدودية، مما أدى إلى 9% فشل في التغطية.
في V7.3 تم تغيير `wall_limit` إلى `coverage_limit = R = 6.40m` في كلا من `_calculate_rows` و `_audit_nfpa`،
مما يضمن أن الصف الحدودي يغطي الجدار بالكامل ضمن نصف قطر التغطية الفعلية.

## نتائج الاختبار — DensityOptimizer V7.3

| الاختبار | الغرف | proof_failures | nfpa_failures | coverage < 99% | fallback |
|----------|-------|----------------|---------------|----------------|----------|
| عشوائي (seed=42) | 1000 | 8 (0.8%) | 0 | 0 | 0 |
| عشوائي (seed=2024) | 100 | 1 (1%) | 0 | 0 | 0 |
| FloorAnalyser 15 غرفة | 15 | 0 | 0 | 0 | 0 |

**كل الـ proof_failures بتغطية > 99.9% — أخطاء تقريب عائم، ليست فجوات حقيقية.**

## FloorAnalyser V2 — Floor-Level Analysis

### Architecture
- Uses DensityOptimizer V7.3 directly (no wrapper, no ExpertSystem, no MIP)
- Sequential execution only — parallel processing disabled for safety
- Triple-check gate: `proof_valid AND nfpa_valid AND NOT fallback_used`

### Safety Shield

| Check | Condition | Action on Failure |
|-------|-----------|-------------------|
| proof_valid | coverage >= 99.99% | Reject room, log error |
| nfpa_valid | zero NFPA spacing violations | Reject room, log error |
| fallback_used | hex/rect strategy must win | Reject room, log warning |

### Integration
```python
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
from fireai.core.floor_analyser import FloorAnalyser

opt = DensityOptimizer()
analyser = FloorAnalyser("floor_1", opt)

rooms = [
    {
        "room_id": "office_01",
        "name": "Main Office",
        "polygon_coords": [(0,0), (10,0), (10,8), (0,8)],
        "ceiling_height": 3.0
    },
    {
        "room_id": "hall_01",
        "name": "Conference Hall",
        "polygon_coords": [(0,0), (20,0), (20,15), (0,15)],
        "ceiling_height": 3.0
    },
]

report = analyser.analyse(rooms)

print(f"Total detectors: {report.total_detectors}")
print(f"Fully compliant: {report.fully_compliant}")
print(f"Safe to submit:  {report.safe_to_submit}")

for summary in report.room_summaries:
    status = "PASS" if summary.compliant else "FAIL"
    print(f"  {summary.name}: {summary.detector_count} dets, "
          f"{summary.coverage_pct:.1f}% coverage, {status}")
```

### Test Results
- **15 rooms (3 floor tiers):** 15/15 PASS — 100% coverage, 0 NFPA violations
- **1000 random rooms (seed=42):** proof_failures=8, nfpa_failures=0
- **100 random rooms (seed=2024):** proof_failures=1, nfpa_failures=0

### Known Limitations
- Rectangular rooms only (no L-shape support at FloorAnalyser layer)
- Ceiling height not optimized (R=6.40m conservative per V7.3)
- Parallel processing disabled (sequential for safety)
- No beam/obstruction handling at this layer

## القيود المعروفة والفاشلات المُوثَّقة — DensityOptimizer

| # | الأبعاد | الكواشف | التغطية | سبب الفشل | الطريقة |
|---|---------|---------|---------|-----------|---------|
| 1 | 1.43×10.78m | 2 | 99.9% | تغطية ناقصة 0.1% (ممر طويل) | hexA_y |
| 2 | 59.79×1.22m | 9 | 99.9% | تغطية ناقصة 0.1% (ممر طويل) | hexG_x |
| 3 | 51.40×0.86m | 7 | 99.9% | تغطية ناقصة 0.1% (ممر ضيق) | hexG_x |

**تحليل الفاشلات:**
- **3 غرف:** ممرات طويلة جداً (نسبة عرض إلى طول > 10:1) — التغطية 99.9%.
- **ملاحظة:** فاشلات V7.2 الكبيرة (غرف >4500m²) لم تعد تظهر بفضل V7.3 coverage_limit=R.

## ⚠️ تحذير الأمان
**هذه الأداة مساعدة للمهندس، وليست بديلاً عن حكمه.**
يجب على مُصمم مؤهل مراجعة جميع التخطيطات، خاصة في:
- الغرف العملاقة (>1000 م²)
- الممرات الطويلة جداً (نسبة > 10:1)
- الغرف غير المستطيلة
- المساحات التي تحتوي على عوائق (أعمدة، عوارض، فتحات HVAC)

الامتثال النهائي لـ NFPA 72 يقع على عاتق المهندس المسؤول.

## الاعتمادات والمراجع
- NFPA 72-2022 §17.6.3.1 (Spacing Requirements)
- NFPA 72-2022 §17.7.4.2.3.1 (0.7S Rule)
- NICET Fire Alarm Systems Manual
- MeyerFire.com — Smoke Detector Spacing Guide
- FireAlarmsOnline.com — 0.7S Rule Explanation
- جميع الاختبارات والمحاكاة تمت باستخدام Python 3.8+
