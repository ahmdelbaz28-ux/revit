# Akamai Protection Plan — FireAI / BAZSPARK

> **المعمارية الكاملة لحماية التطبيق بـ Akamai**
> Status: Draft v1.0 — 2026-07-09
> Owner: Eng. Ahmed Elbaz
> Document type: Implementation Plan + Code Configuration

---

## 1. نظرة عامة (Executive Summary)

الهدف هو حماية BAZSPARK (FireAI Safety-Critical Platform) باستخدام Akamai
كمستوى أمامي (Edge) يعمل كـ:

1. **CDN** — تسريع المحتوى الثابت (Frontend React assets)
2. **WAF / Kona Site Defender** — حماية الـ API من SQLi, XSS, RCE, LFI
3. **Bot Manager** — منع الـ bots من استهداف `/api/v1/auth/login`
4. **DDoS Protection** — Layer 3/4/7 DDoS mitigation
5. **API Security** — schema-based protection للـ 30+ API routers
6. **Account Protector** — منع account takeover على الـ auth endpoints
7. **EdgeWorkers** — تنفيذ logic عند الـ edge (geo-blocking, A/B testing)

---

## 2. المعمارية المستهدفة

```
┌────────────────────────────────────────────────────────────────────────┐
│                          المستخدم (Browser / CAD Plugin)               │
└──────────────────────────┬─────────────────────────────────────────────┘
                           │ HTTPS
                           ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    Akamai Edge (api.bazspark.com)                      │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Property Manager (Property: prp_BAZSPARK)                       │  │
│  │                                                                  │  │
│  │  ┌────────────────┐  ┌──────────────┐  ┌──────────────────────┐ │  │
│  │  │ Kona WAF       │  │ Bot Manager  │  │ API Security         │ │  │
│  │  │ (SQLi/XSS/RCE) │  │ (login forms)│  │ (OpenAPI schema)     │ │  │
│  │  └────────────────┘  └──────────────┘  └──────────────────────┘ │  │
│  │                                                                  │  │
│  │  ┌────────────────┐  ┌──────────────┐  ┌──────────────────────┐ │  │
│  │  │ Rate Limiting  │  │ Geo Block    │  │ Account Protector    │ │  │
│  │  │ (per endpoint) │  │ (sanctioned) │  │ (credential stuffing)│ │  │
│  │  └────────────────┘  └──────────────┘  └──────────────────────┘ │  │
│  │                                                                  │  │
│  │  ┌────────────────┐  ┌──────────────┐  ┌──────────────────────┐ │  │
│  │  │ DDoS L3/L4/L7  │  │ TLS 1.3      │  │ Client Reputation    │ │  │
│  │  │ Prolexic       │  │ Cert mgmt    │  │ (IP scoring)         │ │  │
│  │  └────────────────┘  └──────────────┘  └──────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  EdgeWorkers (serverless JS at edge):                                  │
│    - Verify Akamai-signed requests                                     │
│    - Inject True-Client-IP header                                      │
│    - Custom challenge for suspicious IPs                               │
└──────────────────────────┬─────────────────────────────────────────────┘
                           │ Akamai → Origin (HTTPS, mTLS optional)
                           ▼
┌────────────────────────────────────────────────────────────────────────┐
│              Origin (HF Space + Vercel)                                │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Backend (backend/app.py)                                │  │
│  │                                                                  │  │
│  │  NEW: AkamaiIntegrationMiddleware                                │  │
│  │    - Verify request came through Akamai (Akamai-Internal header) │  │
│  │    - Trust True-Client-IP instead of X-Forwarded-For             │  │
│  │    - Handle Akamai bot detection headers                        │  │
│  │    - Reject direct origin access (bypass prevention)             │  │
│  │                                                                  │  │
│  │  EXISTING: SecurityHeadersMiddleware + CorrelationIdMiddleware   │  │
│  │  EXISTING: limiter (slowapi) — application-level rate limiting   │  │
│  │  EXISTING: backend/auth.py (X-API-Key + RBAC)                   │  │
│  │  EXISTING: backend/security_csrf.py (CSRF)                      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. المتطلبات (Prerequisites)

### 3.1 ما يحتاجه المستخدم (لا يمكنني عمله بمفردي)

| المتطلب | السبب |
|---------|-------|
| **Akamai account + contract** | Akamai خدمة enterprise مدفوعة، تحتاج توقيع contract |
| **Akamai API credentials** (`{contract_id}`, `{group_id}`, `{property_id}`) | لاستدعاء Property Manager API |
| **Edge hostname** (مثل `api.bazspark.com.edgeservices.net`) | يجب شراؤه عبر Akamai Control Center |
| **DNS access** لـ `bazspark.com` | لتحويل CNAME إلى Akamai edge |
| **TLS certificate** على Akamai (Let's Encrypt أو Akamai-managed) | لـ HTTPS termination عند الـ edge |

### 3.2 ما سأنفذه بمفردي (لا يحتاج تدخلك)

| المهمة | المخرجات |
|--------|---------|
| تطوير `AkamaiIntegrationMiddleware` في الـ backend | ملف Python جديد |
| تعديل `limiter.py` لاستخدام `True-Client-IP` من Akamai | تعديل ملف موجود |
| إنشاء Property Manager JSON template | ملف JSON جاهز للاستيراد |
| إنشاء WAF custom rules (Kona Rule Set) | ملف JSON |
| إنشاء Bot Manager configuration | ملف JSON |
| توثيق الـ activation workflow | ملف MD |
| سكريبت deployment آلي عبر Akamai API | سكريبت Python |

---

## 4. المراحل التنفيذية (Implementation Phases)

### Phase 1: تطبيق إصلاحات backend (يعمل بدون Akamai) — ⏱ ~30 دقيقة

**الهدف**: تطبيق الإصلاحات اللازمة في الـ backend لتكون جاهزة للاستقبال Akamai
كـ reverse proxy. هذه الإصلاحات تعمل بشكل مستقل ( defense-in-depth ) حتى قبل
تفعيل Akamai.

| المهمة | الملف | الحالة |
|--------|------|--------|
| إنشاء `AkamaiIntegrationMiddleware` | `backend/akamai_middleware.py` | جديد |
| تعديل `limiter.py` لاستخدام `True-Client-IP` | `backend/limiter.py` | تعديل |
| إضافة middleware إلى `backend/app.py` | `backend/app.py` | تعديل |
| إضافة `AKAMAI_*` env vars للـ config | `backend/config.py` | تعديل |
| إضافة اختبارات وحدة (unit tests) | `backend/tests/test_akamai_middleware.py` | جديد |

### Phase 2: تكوين Akamai Property Manager — ⏱ ~1 ساعة

**الهدف**: إنشاء قوالب JSON جاهزة للاستيراد في Akamai Control Center أو
نشرها عبر Akamai API.

| المهمة | الملف |
|--------|------|
| Property Manager main config | `deploy/akamai/property-main.json` |
| Hostname config (api.bazspark.com) | `deploy/akamai/hostnames.json` |
| Origin config (HF Space + Vercel) | `deploy/akamai/origins.json` |
| Behavior templates (caching, TLS, etc.) | `deploy/akamai/behaviors/` |
| Activation workflow script | `deploy/akamai/activate.py` |

### Phase 3: WAF / Kona Rules — ⏱ ~1 ساعة

| المملف | الوصف |
|--------|------|
| `deploy/akamai/waf/kona-config.json` | Kona Rule Set configuration |
| `deploy/akamai/waf/custom-rules.json` | Custom rules لـ FireAI-specific threats |
| `deploy/akamai/waf/api-security.json` | API Security schema-based protection |
| `deploy/akamai/waf/bot-manager.json` | Bot Manager configuration |
| `deploy/akamai/waf/account-protector.json` | Account Protector (credential stuffing) |

### Phase 4: EdgeWorkers — ⏱ ~30 دقيقة

| المملف | الوصف |
|--------|------|
| `deploy/akamai/edgeworkers/verify-origin/main.js` | EdgeWorker يتحقق من signed requests |
| `deploy/akamai/edgeworkers/geo-block/main.js` | EdgeWorker لـ geo-blocking |
| `deploy/akamai/edgeworkers/inject-headers/main.js` | EdgeWorker يضيف security headers عند الـ edge |

### Phase 5: توثيق + مراقبة — ⏱ ~30 دقيقة

| المملف | الوصف |
|--------|------|
| `docs/AKAMAI_DEPLOYMENT_GUIDE.md` | دليل النشر الكامل |
| `docs/AKAMAI_TESTING_CHECKLIST.md` | قائمة اختبار ما بعد النشر |
| `docs/AKAMAI_MONITORING.md` | دليل المراقبة (Akamai Kona dashboard) |
| `docs/AKAMAI_INCIDENT_RESPONSE.md` | خطة الاستجابة للحوادث |

---

## 5. تفاصيل تنفيذ Phase 1 (سأبدأ بها الآن)

### 5.1 `backend/akamai_middleware.py` (جديد)

وظائفه:

1. **Verify request origin**: يتأكد أن الطلب جاء من Akamai (header `Akamai-Internal: 1`)
2. **Trust True-Client-IP**: يستبدل `X-Forwarded-For` بـ `True-Client-IP` (الـ IP الحقيقي)
3. **Bot detection**: يقرأ `Akamai-Bot-Preview` ويتعامل مع الـ bots
4. **Bypass prevention**: في الإنتاج، يرفض أي طلب مباشر للـ origin ( HF Space URL)
5. **Rate limit headers**: يضيف `X-RateLimit-*` headers استجابةً لطلبات Akamai
6. **Geo filtering**: يقرأ `Akamai-Geo-Country` ويرفض الدول الممنوعة

### 5.2 تعديل `backend/limiter.py`

```python
def get_remote_address(request):
    # Priority: True-Client-IP (Akamai) > X-Forwarded-For > request.client.host
    if tci := request.headers.get("True-Client-IP"):
        return tci.strip()
    if xff := request.headers.get("X-Forwarded-For"):
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"
```

### 5.3 تكوين البيئة (env vars)

| المتغير | القيمة الافتراضية | الوصف |
|---------|------------------|-------|
| `AKAMAI_ENABLED` | `false` | تفعيل/تعطيل الـ middleware |
| `AKAMAI_REQUIRE_ORIGIN_TOKEN` | `` | shared secret للتحقق من signed requests |
| `AKAMAI_BLOCKED_COUNTRIES` | `""` | قائمة دول ممنوعة (ISO 3166-1 alpha-2) |
| `AKAMAI_ALLOWED_BOT_SCORE` | `30` | الحد الأقصى لـ bot score (0-100) |
| `AKAMAI_RATE_LIMIT_HEADER` | `true` | إضافة `X-RateLimit-*` headers |

---

## 6. تكلفة Akamai (تقديرية)

| الخدمة | التكلفة التقديرية/شهر |
|--------|---------------------|
| Akamai Ion (CDN + basic WAF) | $1,000 - $3,000 |
| Kona Site Defender (advanced WAF) | $3,000 - $10,000 |
| Bot Manager | $2,000 - $8,000 |
| Account Protector | $1,000 - $3,000 |
| DDoS (Prolexic) | $2,000 - $5,000 |
| **الإجمالي التقديري** | **$9,000 - $29,000/شهر** |

> ⚠️ Akamai يقدم عادةً خصومات للـ startups و المشاريع الصغيرة.
> يُنصح بالتواصل مع `sales@akamai.com` للحصول على عرض سعر مخصص.

---

## 7. البدائل المقترحة (إذا كانت التكلفة عالية)

إذا كانت تكلفة Akamai مرتفعة، يمكن استخدام بدائل أرخص بنفس الميزات:

| البديل | التكلفة | الميزات المطابقة |
|--------|--------|------------------|
| **Cloudflare Pro** | $20/شهر | CDN + WAF + DDoS + Bot |
| **Cloudflare Business** | $200/شهر | + Custom SSL + WAF custom rules |
| **AWS WAF + CloudFront** | ~$50-200/شهر | CDN + WAF (pay-per-request) |
| **Fastly** | $50-500/شهر | CDN + WAF + EdgeWorkers |

> 💡 إذا كنت تفضل Cloudflare (الأرخص بكثير)، أخبرني وسأكتب خطة بديلة لها.

---

## 8. الخطوات التالية (Next Steps)

### ما سأفعله الآن (بدون تدخلك):
1. ✅ إنشاء `backend/akamai_middleware.py` (المهمة 2 من Phase 1)
2. ✅ تعديل `backend/limiter.py` لاستخدام `True-Client-IP`
3. ✅ تحديث `backend/config.py` بـ env vars الجديدة
4. ✅ إنشاء قوالب Akamai JSON (Phase 2-4)
5. ✅ توثيق النشر (Phase 5)
6. ✅ عمل commit + push على GitHub
7. ✅ مزامنة HF Space

### ما تحتاج فعله (بعد إكمالي):
1. 📧 **التواصل مع Akamai sales** لإنشاء account + contract
2. 🔑 **إنشاء Akamai API credentials** (EdgeGrid authentication)
3. 🌐 **شراء/تكوين domain** `api.bazspark.com` (إذا لم يكن موجوداً)
4. 📋 **استيراد قوالب JSON** في Akamai Control Center
5. ✅ **تفعيل Property** على شبكة Akamai (staging → production)
6. 🔄 **تغيير DNS** من HF Space مباشرة إلى Akamai edge hostname
7. 🧪 **تشغيل اختبارات** من `docs/AKAMAI_TESTING_CHECKLIST.md`

---

## 9. التوافق مع `agent.md`

هذه الخطة متوافقة مع بروتوكول `agent.md` (FireAI Safety-Critical Engineering):

| القاعدة | الالتزام |
|---------|---------|
| Safety priority #1 | WAF rules تحمي الـ engineering API من الـ injection |
| Correctness priority #2 | `True-Client-IP` يضمن logging صحيح للـ IP الحقيقي |
| Verification priority #3 | اختبارات وحدة للـ middleware قبل النشر |
| Security priority #8 | تطبيق defense-in-depth (Akamai + app middleware) |
| Traceability | كل rule له `comment` يشرح السبب |
| Adversarial QA | محاكاة bypass attempts في الـ tests |

---

**تاريخ البدء**: 2026-07-09
**تاريخ الإكمال المتوقع (بدون تدخل المستخدم)**: 2026-07-09 (نفس اليوم)
**تاريخ الإكمال الكامل (مع تدخل المستخدم لتفعيل Akamai)**: يعتمد على سرعة استجابة Akamai sales
