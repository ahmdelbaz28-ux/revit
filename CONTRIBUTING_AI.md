# CONTRIBUTING_AI.md - AI Assistant Constitution for FireAI Development

**هذا الملف هو "دستور إلزامي" لأي مساعد ذكي يعمل على هذا المشروع.**
**يُقرأ قبل أي محادثة تبدأ مع AI حولFireAI.**

---

## 🔴 القواعد الأساسية

### 1. المصداقية (No Sugarcoating)
- **لا تُجمّل**. لا تستخدم "ربما" أو "قد" أو "أعتقد".
- إجاباتك: **نعم** / **لا** / **مش عارف**.
- إذا اكتشفت تزييف أو تناقض → announce **STOP** فوراً واشرح السبب.

### 2. الإثبات الإلزامي (Proof Required)
- كل نتيجة فنية يجب أن ترافقها **دليل**:
  - اسم الملف
  - رقم السطر
  - أو معيار NFPA المرجعي
- لا تكفي "الاختبارات نجحت" ← أظهر رقم الـ Commit.

### 3. دفع الكود (Code Push Protocol)
- بعد كل إصلاح حرج:
  1. `git add -A`
  2. `git commit -m "fix: [وصف موجز]"`
  3. `git push origin [branch]`
- قدّم رابط الـ Commit فوراً.

### 4. قاعدة STOP
- **STOP** إذا:
  - التعليمات غير واضحة أو خطرة
  - الكود يُسبب ضرراً بالمستودع
  - تفتقر لعنصر حرج (اختبارات، توثيق)
- **لا تستمر** بعد STOP إلا بعد تأكيد المستخدم.

### 5. النواة الصلبة vs الديكور
- **نواة صلبة** (لا تُعدّل بدون PR):
  - `nfpa72_coverage.py`
  - `pdf_to_rooms_adapter.py`
  - `select_safe_detector_type()`
  - `validate_wall_distances()`

- **ديكور** (يمكن تعديله بحرية):
  - واجهات المستخدم
  - التقارير
  - السكربتات المساعدة

---

## 📋 قوائم التعليمات الملزمة

### القائمة القديمة (，必须遵守)
| # | التعليمات |
|---|-----------|
| 1 | لا كومنت خارج_context@ |
| 2 | لا تزييف |
| 3 | إثبات إجباري (git + pytest + رابط) |
| 4 | دفع كامل (add/commit/push + مسار) |
| 5 | صدق وحزم (نعم/لا/مش عارف) |
| 6 | مسار واضح |
| 7 | قاعدة STOP |

### القائمة الجديدة ( 必须遵守)
| # | التعليمات |
|---|-----------|
| 1 | إعلان صريح بدون تجميل |
| 2 | النواة أولاً (Digital Twin مجمد) |
| 3 | إصلاح فوري للأخطاء المنطقية |
| 4 | التوثيق يعكس الواقع |
| 5 | AuditTrail لكل مشروع (لا singletons) |
| 6 | 10 اختبارات وحدة لكل إضافة |

---

## 🔧 قاعدة "التحقق المزدوج"

**حتى مع وجود هذا الملف، لا تثق في أي إصلاح حرج إلا بخطوتين:**

1. **خطوة 1**: اطلب من المساعد تشغيل اختبار وحدة (Unit Test) مخصص لهذا الإصلاح فوراً.
2. **خطوة 2**: راجع سطر الكود المُغير يدوياً قبل الـ Commit.

**القاعدة: "لا ثقة عمياء، حتى مع أفضل البرومبتات".**

---

## 🧪 معايير الاختبار

### اختبارات السلامة الإلزامية (8/8)
```
pytest tests/test_safety_critical.py -v
```

| Test | Description |
|------|-------------|
| test_kitchen_no_smoke | المطبخ ← HEAT (NOT SMOKE) |
| test_server_room_multi_criteria | السيرفر ← MULTI-CRITERIA |
| test_impossible_height_clamped | إرتفاع >6m ← clamp |
| test_high_ceiling_clamped | ارتفاع سقف عالٍ ← clamp |
| test_l_shaped_coverage | غرفة L-شكل ← polygon coverage |
| test_detector_selection_logic | اختيار الكاشف |
| test_no_bare_except | لا bare except |
| test_no_todos | لا TODO في الكود الإنتاجي |

---

## 🚨 الأخطاء القاتلة (Must Fix)

### 1. خطأ الجدران (Wall Distance Bug)
```python
# ❌ خطأ - يؤدي لإنذارات كاذبة
if dist > max_wall:
    violations.append(...)

# ✅ صحيح
if dist < MIN_WALL_DISTANCE_M:
    violations.append(...)
```
**الملف:** `nfpa72_coverage.py`
**المرجع:** NFPA 72 §17.6.3.1.1

### 2. خطأ اختيار الكاشف
```python
# ❌ خطأ
if room_type == "office":
    return DetectorType.HEAT  # خطأ!

# ✅ صحيح
if room_type == "office":
    return DetectorType.SMOKE  # صحيح!
```
**الملف:** `pdf_to_rooms_adapter.py`

### 3. خطأ Fail-Safe
```python
# ✅ Fail-Safe صحيح
if occupancy_type == "unknown":
    detector_count = 0  # NOT HEAT!
    detector_type = "UNKNOWN"
```

---

## 🛡️ قائمة المحظورات (Read-Only Zones)

**هذه الملفات لا تُعدّل بدون Pull Request يمر باختبارات السلامة:**

1. `nfpa72_coverage.py`
2. `nfpa72_models.py`
3. `nfpa72_calculations.py`
4. `adapters/pdf_to_rooms_adapter.py`
5. `parsers/geometry_extractor.py`
6. `run_full_pipeline.py`

---

## 📝 نموذجCommit Message

```
<type>: <description>

<detailed explanation if needed>

Fixes: #<issue-number>
Tests: pytest tests/test_safety_critical.py -v
Commit: <sha>
```

---

## 🔗 المراجع

- NFPA 72-2022: National Fire Alarm and Signaling Code
- BS 5839-1: Fire detection and alarm systems
- Clean Architecture principles

---

**آخر تحديث:** 2026-05-15  
**الحالة:** PRODUCTION READY ✅