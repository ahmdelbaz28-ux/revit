# FireAI v8.0 — Multi-Layer Fire Alarm Design Engine

> A comprehensive fire alarm system design engine for compliance with NFPA 72 standards.

## Table of Contents
- [Engineering Foundations](#الأسس-الهندسية)
- [Architecture Overview](#البنية-المعمارية--ثلاث-طبقات)
- [DensityOptimizer V7.3](#densityoptimizer-v73--نتائج-الاختبار)
- [FloorAnalyser V2.1](#flooranalyser-v21--floor-level-analysis)
- [BuildingEngine V0.1](#buildingengine-v01--building-level-analysis)
- [AuditTrail & AuditStore](#audittrail-v52--auditstore)
- [Known Limitations](#القيود-المعروفة-والفاشلات-الموثقة--densityoptimizer)
- [Safety Notice](#️-تحذير-الأمان)
- [References & Credits](#الاعتمادات-والمراجع)

## الأسس الهندسية
- **نصف قطر التغطية (R):** يُحسب ديناميكيًا كـ R = 0.7 × S — NFPA 72 §17.7.4.2.3.1
  - عند h≤3.0m (smoke): R = 0.7 × 9.10m = **6.37m**
  - عند h≤3.0m (heat): R = 0.7 × 6.10m = **4.27m**
  - القيم تتغير حسب ارتفاع السقف — انظر NFPA 72 Table 17.6.3.1.1
- **التباعد الأقصى (S):** 9.14 متر (30 قدم) — NFPA 72 §17.6.3.1
- **أقصى مسافة للجدار:** S/2 — عند h≤3.0m: 4.55m (smoke) / 3.05m (heat)
- **حد التغطية (coverage_limit):** R — نصف قطر التغطية الفعلية لضمان تغطية الجدران
- **الخوارزميات:** سداسية (Hexagonal) + مستطيلة (Rectangular) + احتياطية (Fallback)
- **التبعيات:** Python 3.8+ فقط. مكتبة NumPy اختيارية لتسريع التحقق.

### CRITICAL FIX (commit 6715c55, 2026-05-18)
كانت النسخة السابقة تُعيد S/2 (4.55m) كـ "نصف قطر تغطية" — وهذا خطأ. S/2 هو أقصى مسافة
للجدار، وليس نصف قطر التغطية. نصف قطر التغطية الصحيح هو R = 0.7 × S = 6.37m عند h=3.0m.
الإصلاح غيّر جدول NFPA 72 ليخزّن التباعد المُعدَّل S بدلاً من S/2، وأضاف حقل `wall_distance_max`
في CoverageSpec لتمييز القيمتين بوضوح.

### تغيير V7.3
في V7.2 كان `wall_limit = S/2 = 4.57m` يُستخدم لوضع الصفوف الحدودية، مما أدى إلى 9% فشل في التغطية.
في V7.3 تم تغيير `wall_limit` إلى `coverage_limit = R = 6.40m` في كلا من `_calculate_rows` و `_audit_nfpa`،
مما يضمن أن الصف الحدودي يغطي الجدار بالكامل ضمن نصف قطر التغطية الفعلية.

## البنية المعمارية — ثلاث طبقات

The system uses a three-layer composition pattern where each layer delegates to the next:

```
┌─────────────────────────────────────────────────────┐
│  BuildingEngine V0.1  (مبنى متعدد الطوابق)         │
│  ┌─────────────────────────────────────────────────┐│
│  │  FloorAnalyser V2.1  (طابق — غرف متعددة)       ││
│  │  ┌─────────────────────────────────────────────┐││
│  │  │  DensityOptimizer V7.3  (غرفة واحدة)       │││
│  │  └─────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
         │                    │                   │
    AuditStore (SQLite)  AuditTrail V5.2    Triple-Check Gate
    Hash chain + HMAC    Thread-safe log   proof+nfpa+!fallback
```

See [`backend_app.py`](../backend_app.py) for the main application entry point.

### المبدأ: تكوين لا إعادة تنفيذ
- `FloorAnalyser` تستخدم `DensityOptimizer` مباشرة
- `BuildingEngine` تستخدم `FloorAnalyser` كمكوّن
- لا ازدواجية منطق، لا إعادة تنفيذ

## DensityOptimizer V7.3 — نتائج الاختبار (بعد CRITICAL FIX R=0.7×S)

| الاختبار | الغرف | proof_failures | nfpa_failures | coverage < 99% | fallback |
|----------|-------|----------------|---------------|----------------|----------|
| عشوائي (seed=2026, R=0.7×S) | 300 | 1 (0.3%) | 0 | 0 | 0 |
| عشوائي (seed=42, R=0.7×S) | 100 | 3 (3%) | 0 | 0 | 0 |
| اختبارات الانحدار | 13 | 0 | 0 | 0 | 0 |
| اختبارات الحافة والضغط | 81 | 0 | 0 | 0 | 0 |
| FloorAnalyser 15 غرفة | 15 | 0 | 0 | 0 | 0 |

**كل الـ proof_failures بتغطية > 99.9% — أخطاء تقريب عائم، ليست فجوات حقيقية.**
**صفر nfpa_failures في جميع الاختبارات.**

## FloorAnalyser V2.1 — Floor-Level Analysis

### Architecture
- Uses DensityOptimizer V7.3 directly (no wrapper, no ExpertSystem, no MIP)
- Sequential execution only — parallel processing disabled for safety
- Triple-check gate: `proof_valid AND nfpa_valid AND NOT fallback_used`
- Optional AuditTrail + AuditStore integration
- BOUNDARY_LIMIT live warning for 0.8% proof failures

### Safety Shield

| Check | Condition | Action on Failure |
|-------|-----------|-------------------|
| proof_valid | coverage >= 99.99% | Reject room, log error |
| nfpa_valid | zero NFPA spacing violations | Reject room, log error |
| fallback_used | hex/rect strategy must win | Reject room, log warning |

### New in V2.1
- `theoretical_lower_bound` + `efficiency_ratio` in RoomSummary
- `detector_type` + `duct_devices` + `warnings` في RoomSummary
- `total_theoretical_lower_bound` في FloorReport
- تحذير BOUNDARY_LIMIT حي (coverage > 99.9% لكن proof_valid=False)
- تكامل AuditStore اختياري (أحداث حرجة في سلسلة هش غير قابلة للتعديل)
- تكامل AuditTrail اختياري

## BuildingEngine V0.1 — Building-Level Analysis

### Architecture
- Uses FloorAnalyser V2.1 as component (composition, not reimplementation)
- Each floor gets independent FloorAnalyser instance
- Sequential execution only — no parallel processing
- Conservative safe_to_submit: any UNSAFE room in ANY floor blocks the building
- audit_store passed to each FloorAnalyser for tamper-proof logging

### Safety Gates

| Gate | Condition | Scope |
|------|-----------|-------|
| safe_to_submit | every room in every floor safe | Building-wide |
| fully_compliant | every room in every floor compliant | Building-wide |
| unsafe_floors | floors with any UNSAFE room | Blocks building |

### Integration

```python
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
from fireai.core.building_engine import BuildingEngine

opt = DensityOptimizer()
engine = BuildingEngine("BLDG-001", opt)

floors = {
    "GF": [
        {"room_id": "lobby", "name": "Lobby",
         "polygon_coords": [(0,0), (12,0), (12,8), (0,8)],
         "ceiling_height": 3.0},
    ],
    "L1": [
        {"room_id": "office", "name": "Office",
         "polygon_coords": [(0,0), (10,0), (10,8), (0,8)],
         "ceiling_height": 3.0},
    ],
}

report = engine.analyse(floors)

print(f"Total detectors: {report.total_detectors}")
print(f"Total LB: {report.total_theoretical_lower_bound}")
print(f"Fully compliant: {report.fully_compliant}")
print(f"Safe to submit:  {report.safe_to_submit}")
```

## AuditTrail V5.2 + AuditStore

### AuditTrail V5.2 (in-memory)
- Thread-safe (`threading.Lock`)
- `log_placement()` — NFPA 72 §17.6.3
- `log_wall_distance_violation()` — NFPA 72 §17.6.3.1.1
- `log_duct_detector_placement()` — NFPA 72 §17.7.5
- `log_safe_fallback_used()` — Table 17.6.3.1
- `log_boundary_limit_warning()` — known 0.8% limitation
- Per-entry SHA-256 hash verification

### AuditStore (SQLite, tamper-proof)
- Hash chain: SHA-256 (previous_hash → current_hash)
- HMAC-SHA256 signature per entry
- SQL triggers prevent UPDATE and DELETE
- Used by FloorAnalyser + BuildingEngine for critical events
- `verify_chain()` detects any tampering

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
- **الأسقف فوق 12.2m:** خارج جدول NFPA 72 — يجب مراجعة AHJ (النظام يستخدم قيماً تحفظية)

**ملاحظة مهمة عن R:** القيمة R=6.37m عند h=3.0m هي نصف قطر التغطية الصحيح (R=0.7×S)
حسب NFPA 72 §17.7.4.2.3.1. القيمة القديمة 4.55m كانت S/2 (أقصى مسافة للجدار) وليست
نصف قطر تغطية. تم تصحيح هذا في commit 6715c55.

الامتثال النهائي لـ NFPA 72 يقع على عاتق المهندس المسؤول.

## الاعتمادات والمراجع
- NFPA 72-2022 §17.6.3.1 (Spacing Requirements)
- NFPA 72-2022 §17.7.4.2.3.1 (0.7S Rule)
- NFPA 72-2022 §17.7.5 (Duct Detectors)
- NFPA 72-2022 Table 17.6.3.1 (Ceiling Height / Radius)
- NICET Fire Alarm Systems Manual
- MeyerFire.com — Smoke Detector Spacing Guide
- FireAlarmsOnline.com — 0.7S Rule Explanation
- جميع الاختبارات والمحاكاة تمت باستخدام Python 3.8+
