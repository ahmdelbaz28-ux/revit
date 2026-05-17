# TECHNICAL_HONESTY.md
## وثيقة الصدق الفني لمشروع FireAI

**التاريخ:** 18 مايو 2026
**النسخة:** 2.2
**الغرض:** توثيق الحالة الراهنة للمشروع، حدود النظام المعروفة، وخطة
التطوير، التزاماً بمبدأ الشفافية الكاملة ورفض أي ادعاءات غير قابلة للتحقق.

---

## 1. ما يعمل فعلاً (Production-Ready)

| المكوّن | الملف | الحالة |
|---------|-------|--------|
| DensityOptimizer V7.3 | `fireai/core/spatial_engine/density_optimizer.py` | ✅ مُختبر (1000 غرفة) |
| MIP Solver (PuLP) | `fireai/core/spatial_engine/mip_solver.py` | ✅ اختياري — تحقق فقط |
| FloorAnalyser V2.3 | `fireai/core/floor_analyser.py` | ✅ مُختبر + MIP verifier + AuditTrail + AuditStore |
| BuildingEngine V0.1 | `fireai/core/building_engine.py` | ✅ مُختبر (6 سيناريوهات مبنى) |
| AuditTrail V5.3.0 | `fireai/core/audit_trail.py` | ✅ موحّد: thread-safe + log_rejection + 6 دوال تسجيل |
| AuditStore | `fireai/core/audit_store.py` | ✅ سلسلة هش غير قابلة للتعدیل + HMAC-SHA256 |
| nfpa72_models | `fireai/core/nfpa72_models.py` | ✅ يعمل مع الغرف المستطيلة |
| nfpa72_calculations | `fireai/core/nfpa72_calculations.py` | ✅ مطابق لـ NFPA 72-2022 |
| nfpa72_coverage | `fireai/core/nfpa72_coverage.py` | ✅ يعمل (690 سطر) |

**نتائج DensityOptimizer V7.3 (commit `dfaf5a7`):**
- nfpa_failures = 0/1000
- proof_failures = 8/1000 (جميعها بتغطية > 99.9%)
- شبكة التحقق: step = 0.20m
- نصف قطر التغطية: R = 6.40m ثابت

**نتائج FloorAnalyser V2.1:**
- 15 غرفة (3 طوابق): 15/15 PASS
- 10 غرف واقعية: 10/10 PASS
- تحذير BOUNDARY_LIMIT حي للـ 0.8% cases
- تكامل AuditTrail + AuditStore اختياري

**نتائج BuildingEngine V0.1:**
- مبنى فارغ: safe_to_submit=False ✅
- مبنى متوافق: safe_to_submit=True ✅
- غرفة unsafe تمنع المبنى بالكامل ✅
- AuditStore يتلقى أحداث من جميع الطوابق ✅
- composition (FloorAnalyser كمكوّن) — لا إعادة تنفيذ ✅

---

## 2. ما لا يعمل / غير موجود حالياً

| العنصر | السبب |
|--------|-------|
| كود V11 بالكامل | يعتمد على 5+ وحدات غير موجودة. لا يمكن تشغيل أي سطر منه |
| MIP Solver مُدمج | ✅ متاح كتحقق اختياري (use_mip=True) — لا يُستبدل greedy أبداً |
| ProjectMemory | غير موجود — ولن يُستخدم بين الغرف |
| دعم الأشكال غير المستطيلة | النظام يفترض غرفاً مستطيلة |
| duct_devices منطق كامل | الحقل موجود (=0)، منطق الحقن التلقائي لاحقاً |
| R متغير حسب ارتفاع السقف | V7.3 مُجمّد — يحتاج سبب هندسي محدد من اختبار واقعي |

---

## 3. القيود المعروفة (Known Limitations)

1. **0.8% فشل في إثبات التغطية (proof failures)**
   - 8 غرف من 1000 فشلت في التحقق الشبكي رغم تغطية > 99.9%
   - السبب: خطأ تقريب عائم مع step = 0.20m في غرف ذات نسب أبعاد شاذة
   - يُعالج عبر تحذير حي (BOUNDARY_LIMIT) وليس بتعديل الخوارزمية
   - FloorAnalyser V2.1 يُصدر WARNING ويُسجّل في AuditStore

2. **دعم الغرف المستطيلة فقط**
   - RoomSpec يتطلب width_m و depth_m
   - لا يمكن تحليل غرف على شكل L أو مضلعات معقدة

3. **نصف قطر تغطية ثابت (R = 6.40m) — ⚠️ ليس تحفظياً**
   - R = 6.40m صحيح للأسقف العالية (9.1m+) فقط حسب NFPA 72 Table 17.6.3.2
   - للأسقف المنخفضة (3.0-4.3m)، NFPA يتطلب R = 4.55m (كواشف أقرب)
   - استخدام R = 6.40m للأسقف المنخفضة يعني **كواشف أقل** مما يتطلبه NFPA
   - هذا **ليس تحفظياً (conservative)** — بل قد يكون أقل أماناً للأسقف المنخفضة
   - مراجعة PE مطلوبة خاصة للأسقف المنخفضة

4. **غياب الحد الأدنى المُثبت رياضياً (مُحدَّث)**
   - MIP Solver (PuLP) متاح الآن كخيار تحقق (use_mip=True)
   - عند نجاحه، `mip_proven_optimal_count` يحتوي على الحد الأدنى المُثبت على شبكة المرشحين
   - بدون MIP، يبقى `theoretical_lower_bound` تقديرياً فقط
   - مواضع MIP غير مُتحقق منها NFPA — لا تُخزّن في RoomSummary

---

## 4. تصنيف ميزات V11 المُقدَّمة

| الميزة | التصنيف | الحالة |
|--------|---------|--------|
| هيكل BuildingReport / BuildingEngine | **نفذ الآن** | ✅ BuildingEngine V0.1 |
| safe_to_submit محافظ | **نفذ الآن** | ✅ غرفة/طابق/مبنى |
| حقل duct_devices | **نفذ الآن** | ✅ حقل أولي (=0)، منطق كامل لاحقاً |
| هيكل الاختبارات (10 مجموعات) | **أعد كتابة** | ✅ test_comprehensive.py |
| دوال AuditTrail الموسّعة | **نفذ الآن** | ✅ AuditTrail V5.3.0 (موحّد) |
| theoretical_lower_bound | **نفذ الآن** | ✅ property + static method |
| efficiency_ratio | **نفذ الآن** | ✅ property على DetectorLayout |
| تحذير حي للـ 0.8% | **نفذ الآن** | ✅ BOUNDARY_LIMIT warning |
| AuditStore تكامل | **نفذ الآن** | ✅ FloorAnalyser + BuildingEngine |
| theoretical_minimum (كما في V11) | **مرفوض** | `_theoretical_minimum` private فقط |
| ProjectMemory | **مرفوض** | تلوث بين الغرف |
| ProcessPoolExecutor | **مرفوض** | أخطاء مخفية في نظام سلامة حرائق |
| أي import لوحدات V11 غير موجودة | **مرفوض** | لا stub/shim وهمية |
| MIP حقيقي (PuLP) | **مُنفذ (V2.3)** | ✅ تحقق اختياري — لا يُستبدل greedy |
| R متغير حسب ارتفاع السقف | **لاحقاً** | يحتاج تعديل V7.3 |
| دعم L-shape عبر Shapely | **لاحقاً** | يحتاج تعديل DensityOptimizer |
| duct_devices منطق كامل | **لاحقاً** | الحقل الآن، المنطق لاحقاً |
| Revit Connector | **لاحقاً** | سابق لأوانه |

---

## 5. الفرق الصارم: theoretical_lower_bound ≠ theoretical_minimum ≠ mip_proven_optimal_count

| المصطلح | المعنى | القابلية للتحقق |
|---------|--------|----------------|
| `theoretical_lower_bound` | تقدير: ceil(area / π×R²) — لا يمكن بأقل نظرياً | ❌ تقديري — قد يكون أقل من الممكن فعلياً |
| `mip_proven_optimal_count` | الحد الأدنى المُثبت على شبكة المرشحين فقط | ⚠️ مُثبت على الشبكة فقط — قد لا يكون الحد الأدنى المُطلق |
| `theoretical_minimum` | داخل MIPResult فقط — الحل الأمثل على الشبكة | ✅ مُثبت عندما solver_status == "Optimal" |
| `detector_count` | العدد الفعلي من greedy (مُتحقق NFPA) | ✅ مُتحقق |

**تحذير:** استخدام `theoretical_minimum` بدون MIP حقيقي يخلق "وهم دقة" —
نفس النوع من التضليل الذي كشفناه في MIP الوهمي سابقاً.
الاسم `theoretical_minimum` غير موجود في الواجهة العامة — فقط `_theoretical_minimum` (private).

**ملاحظة مهمة (V2.3):**
- `mip_proven_optimal_count` قد يكون أقل من `detector_count` لأن MIP لا يُخضع
  مواضعه لتحقق NFPA (جدار، تباعد). هذا لا يعني أن greedy مُفرط — بل يعني
  أن MIP يحل مشكلة مختلفة (set covering خالص بدون قيود NFPA).
- عند وجود فجوة (MIP < greedy)، يُصدر تحذير `MIP_OPTIMALITY_GAP`
  لمراجعة PE إمكانية تقليل عدد الكواشف.
- `candidate_step` يتحكم بدقة الشبكة: 1.0m = دقة معقولة، 0.5m = أدق لكن أبطأ.
  الشبكة لا تغطي كل المواضع الممكنة — لذلك `mip_proven_optimal_count`
  ليس الحد الأدنى المُطلق بل الحد الأدنى على الشبكة.

---

## 6. آلية التحذير الحي للـ 0.8% (مُنفذة)

عندما: proof_valid == False لكن coverage_pct > 99.9%

يُصدر FloorAnalyser تحذيراً (وليس خطأ):

```
BOUNDARY_LIMIT: Coverage {x}% exceeds 99.9% but grid
verification at step=0.20m could not confirm 100%.
This is a known limitation (0.8% of rooms). PE review recommended.
```

التسجيل:
- يُضاف إلى `RoomSummary.warnings`
- يُسجّل في `AuditTrail.log_boundary_limit_warning()`
- يُسجّل في `AuditStore.add_event("BOUNDARY_LIMIT_WARNING", ...)`

---

## 7. Commits الموثوقة

| Commit | الوصف | الحالة |
|--------|-------|--------|
| `dfaf5a7` | V7.3 code change (coverage_limit = R) | ✅ مُختبر ومُوثق |
| `d832a28` | V7.3 + FloorAnalyser V2 documentation | ✅ مُختبر ومُوثق |
| `4de84ab` | TECHNICAL_HONESTY.md V1.0 | ✅ صادق (مُحدّث في هذا commit) |
| `3544fdb` | Test Suite V2 — 10 realistic rooms | ✅ 10/10 PASS |
| `86f3cc8` | Phase 2 — theoretical_lower_bound, AuditTrail V5.2, BOUNDARY_LIMIT | ✅ مُختبر |
| `66b952f` | Phase 3 — BuildingEngine V0.1 | ✅ 6/6 PASS |
| `784c265` | Phase 4 — FloorAnalyser V2.2 + expanded tests (25 PASS + 3 SKIP) | ✅ مُختبر |
| `35047d1` | Phase 5 — MIP Solver (PuLP) as verifier (35 PASS + 2 SKIP) | ✅ مُختبر |
| `d429e48` | ⛔ مُزوَّر — يجب تجاهله حسب AGENTS.md | ❌ مرفوض |

---

## 8. الالتزام بالثوابت

- لا يُعدّل V7.3 إلا بسبب هندسي مُحدد يظهر في اختبار واقعي
- لا معالجة متوازية في أي طبقة تحليل
- لا ذاكرة مشتركة بين الغرف
- لا كود وهمي (stub/shim)
- theoretical_lower_bound هو الوحيد المستخدم للحد الأدنى التقديري
- theoretical_minimum محجوز لـ MIPResult فقط (الحل الأمثل على الشبكة)
- mip_proven_optimal_count في RoomSummary — مُثبت على شبكة المرشحين فقط
- AuditStore يُستخدم لتسجيل الأحداث الحرجة (سلسلة هش غير قابلة للتعدیل)
- BuildingEngine تستخدم FloorAnalyser كمكوّن (composition not reimplementation)
- MIP هو VERIFIER فقط — لا يُستبدل greedy placement أبداً
- AuditTrail V5.3.0 هي النسخة الوحيدة — لا نسخة مكررة في الجذر
- لا ملفات .py تراثية في الجذر — الكل داخل fireai/core/
- FloorAnalyser يستخدم استيراد طبيعي (لا importlib hack)

---

**تم تحرير هذه الوثيقة بناءً على مراجعة نقدية شاملة للكود المُقدَّم (V11)
والمشروع الحالي (V7.3 + FloorAnalyser V2.3 + BuildingEngine V0.1 + AuditTrail V5.3.0 + AuditStore).
أي تطوير لاحق سيُقاس بمدى توافقه مع هذه الوثيقة.**
