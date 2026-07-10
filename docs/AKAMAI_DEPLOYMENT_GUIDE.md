# Akamai Deployment Guide — BAZSPARK

> **دليل النشر الكامل لحماية BAZSPARK بـ Akamai**
> Prerequisites: Akamai account + contract + API credentials.

---

## 1. المتطلبات المسبقة (Prerequisites)

### 1.1 حساب Akamai

1. **إنشاء حساب**: تواصل مع `sales@akamai.com` أو من خلال [Akamai Control Center](https://control.akamai.com)
2. **الحصول على contract**: ستستلم `contract_id` (مثل `ctr_C-1234567`)
3. **الحصول على group**: ستستلم `group_id` (مثل `grp_12345`)
4. **شراء المنتجات**:
   - ✅ Property Manager (`prd_SPM`)
   - ✅ Kona Site Defender (WAF + DDoS)
   - ✅ Bot Manager
   - ✅ Account Protector
   - ✅ API Security
   - ✅ EdgeWorkers

### 1.2 API Credentials

1. سجّل الدخول إلى [Akamai Control Center](https://control.akamai.com)
2. اذهب إلى: **Account Admin** → **API Credentials**
3. أنشئ API credentials جديد بـ:
   - **Service**: Property Manager (`papi`)
   - **Access level**: Read-Write
   - **Products**: Kona Site Defender, Bot Manager, Account Protector, API Security, EdgeWorkers
4. احفظ:
   - `Host` (مثل `akab-abc123.luna.akamaiapis.net`)
   - `Client token`
   - `Client secret`
   - `Access token`

5. أنشئ ملف `~/.edgerc` على خادم النشر:
   ```ini
   [papi]
   host = akab-abc123.luna.akamaiapis.net
   client_token = akab-xxxx...
   client_secret = xxxx...
   access_token = akab-xxxx...
   ```

   **أو** عيّن متغيرات البيئة:
   ```bash
   export AKAMAI_HOST="akab-abc123.luna.akamaiapis.net"
   export AKAMAI_CLIENT_TOKEN="akab-xxxx..."
   export AKAMAI_CLIENT_SECRET="xxxx..."
   export AKAMAI_ACCESS_TOKEN="akab-xxxx..."
   ```

### 1.3 Domain + DNS

1. امتلك `bazspark.com` (أو domain آخر)
2. صلاحية تعديل DNS records (Cloudflare DNS, Route53, GoDaddy, إلخ)

### 1.4 Origin جاهز

- ✅ HF Space: <https://ahmdelbaz28-bazspark.hf.space> (يعمل)
- ✅ Vercel project: <https://revit-xxxx.vercel.app> (يعمل)
- ✅ Backend health: `/api/health` يعود `status: ok, database: connected`

---

## 2. النشر التدريجي (Step-by-Step Deployment)

### Step 1: تثبيت dependencies على خادم النشر

```bash
pip install edgegrid-python requests
```

### Step 2: تعيين متغيرات البيئة

```bash
# Akamai API (from ~/.edgerc OR env vars)
export AKAMAI_HOST="akab-abc123.luna.akamaiapis.net"
export AKAMAI_CLIENT_TOKEN="akab-xxxx..."
export AKAMAI_CLIENT_SECRET="xxxx..."
export AKAMAI_ACCESS_TOKEN="akab-xxxx..."

# Akamai Property config
export AKAMAI_EDGE_HOSTNAME="bazspark"           # → bazspark.edgeservices.net
export AKAMAI_ORIGIN_HOSTNAME="ahmdelbaz28-bazspark.hf.space"  # HF Space
# OR: export AKAMAI_ORIGIN_HOSTNAME="revit-xxxx.vercel.app"     # Vercel

# Origin verification token (generate a strong random secret)
export AKAMAI_REQUIRE_ORIGIN_TOKEN="$(openssl rand -hex 32)"

# Admin IP allowlist (comma-separated CIDRs)
export AKAMAI_ADMIN_IP_ALLOWLIST="203.0.113.0/24,198.51.100.10/32"
```

> ⚠️ **احفظ `AKAMAI_REQUIRE_ORIGIN_TOKEN` في مكان آمن** — يجب أن يكون متطابقاً بين Akamai والـ backend.

### Step 3: نشر الـ Akamai Property على staging

```bash
cd /home/z/my-project/repos/revit

python deploy/akamai/activate.py \
  --contract-id ctr_C-1234567 \
  --group-id grp_12345 \
  --activate-staging \
  --notify-email eng.ahmed.elbaz@gmail.com
```

السكريبت سيقوم بـ:
1. ✅ إنشاء Property جديد باسم `BAZSPARK`
2. ✅ استيراد القواعد من `deploy/akamai/property-main.json`
3. ✅ إضافة hostnames من `deploy/akamai/hostnames.json`
4. ✅ تفعيل على شبكة **staging**
5. ✅ طباعة تعليمات DNS

### Step 4: اختبار على staging

Akamai يوفر staging URLs بالصيغة:
```
https://{edge_hostname}.edgeservices.net/api/health
?akamai-staging=1
```

أو استخدم header:
```bash
curl -H "Pragma: akamai-x-get-extracted-values" \
     -H "X-Akamai-Debug: true" \
     https://bazspark.edgeservices.net.staging.akamaihd.net/api/health
```

تحقق من:
- ✅ Response header `X-Akamai-EdgeWorker: inject-headers` موجود
- ✅ Response header `X-Akamai-Translated-Request: true` موجود (من backend middleware)
- ✅ لا يوجد `X-Forwarded-For` مزيف
- ✅ `True-Client-IP` يعكس IP الحقيقي للعميل

### Step 5: تفعيل WAF / Bot Manager / Account Protector

```bash
# استيراد WAF config عبر Akamai Kona Security API
# (مختلف عن Property Manager API — راجع https://techdocs.akamai.com/kona-site-defender)
# Best done via Akamai Control Center UI:
#   Security → Security Configuration → Import → Choose file
#   Upload: deploy/akamai/waf/kona-config.json
#   Upload: deploy/akamai/waf/bot-manager.json
#   Upload: deploy/akamai/waf/account-protector.json
#   Upload: deploy/akamai/waf/api-security.json
```

### Step 6: نشر EdgeWorkers

```bash
# Bundle كل EdgeWorker
cd deploy/akamai/edgeworkers/verify-origin
zip -r verify-origin.zip . -x "*.DS_Store"
# ارفع عبر: Akamai Control Center → EdgeWorkers → Create → Upload bundle

cd ../geo-block
zip -r geo-block.zip . -x "*.DS_Store"

cd ../inject-headers
zip -r inject-headers.zip . -x "*.DS_Store"
```

ثم اربط كل EdgeWorker بالـ property:
- **verify-origin**: على `onClientRequest` لكل المسارات
- **geo-block**: على `onClientRequest` لكل المسارات
- **inject-headers**: على `onOriginResponse` و `onClientResponse`

### Step 7: تحديث DNS

في DNS provider الخاص بك:

```
Type    Name                   Value                                  TTL
CNAME   api.bazspark.com       bazspark.edgeservices.net              3600
CNAME   www.bazspark.com       bazspark.edgeservices.net              3600
A       bazspark.com           23.x.x.x (from Akamai API)             3600
TXT     _dnsauth.bazspark.com  (Akamai-provided validation token)     300
```

انتظر 5-30 دقيقة لـ DNS propagation.

### Step 8: تحديث backend لتفعيل Akamai

على HF Space + Vercel، عيّن هذه الـ secrets/env vars:

```bash
# HF Space
curl -X POST \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"AKAMAI_ENABLED\",\"value\":\"true\"}" \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets

curl -X POST \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"AKAMAI_REQUIRE_ORIGIN_TOKEN\",\"value\":\"$AKAMAI_REQUIRE_ORIGIN_TOKEN\"}" \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets

curl -X POST \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"AKAMAI_BLOCKED_COUNTRIES\",\"value\":\"IR,KP,SY,CU,VE,BY,RU\"}" \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets

# Vercel (same vars, via Vercel API)
# Use scripts/restore_standard_db_config.py pattern with these new vars
```

### Step 9: تفعيل الإنتاج (Production Activation)

بعد نجاح اختبارات staging:

```bash
python deploy/akamai/activate.py \
  --contract-id ctr_C-1234567 \
  --group-id grp_12345 \
  --property-id prj_XXXXXXXX \
  --activate-production \
  --notify-email eng.ahmed.elbaz@gmail.com
```

### Step 10: اختبار ما بعد النشر

اتبع `docs/AKAMAI_TESTING_CHECKLIST.md` لاختبار شامل.

---

## 3. الصيانة الدورية (Ongoing Maintenance)

### أسبوعياً
- راجع **Akamai Security Dashboard** للهجمات المحظورة
- افحص **Bot Manager dashboard** للـ bots الجديدة
- تحقق من **Rate limit hits** في الـ WAF logs

### شهرياً
- **Rotate** `AKAMAI_REQUIRE_ORIGIN_TOKEN`:
  1. ولّد token جديد: `openssl rand -hex 32`
  2. حدّثه في Akamai Property Manager (modifyHeader behavior)
  3. حدّثه في HF Space + Vercel
  4. Activate على staging → اختبار → activate على production
  5. احذف token القديم من الذاكرة
- **تحديث OFAC sanctioned countries list** في `deploy/akamai/edgeworkers/geo-block/main.js`

### كل 3 أشهر
- مراجعة WAF custom rules (احذف القواعد غير الفعالة)
- تحديث EdgeWorkers (تحديثات Akamai SDK)
- مراجعة Account Protector ML model performance

### سنوياً
- إعادة تفاوض عقد Akamai
- penetration test خارجي
- Akamai security audit

---

## 4. استكشاف الأخطاء (Troubleshooting)

### المشكلة: 503 Service Unavailable

**الأسباب المحتملة**:
- Origin (HF Space) لا يستجيب → تحقق من `/api/health`
- Akamai لا يستطيع الوصول للـ origin → تحقق من Origin Settings في Property Manager
- Rate limit exceeded → راجع WAF dashboard

### المشكلة: 403 Forbidden (مع `X-Akamai-Translated-Request: true`)

**الأسباب**:
- WAF حظر الطلب → راجع Akamai Security Events
- Bot score عالٍ على endpoint حساس → تحقق من `Akamai-Bot-Score` header
- Geo-blocked → تحقق من `Akamai-Geo-Country` header

### المشكلة: 403 Forbidden (بدون `X-Akamai-Translated-Request`)

**السبب**: الطلب لم يصل عبر Akamai (direct origin access)
- تحقق من DNS: هل `bazspark.com` يشير إلى Akamai؟
- تحقق من `AKAMAI_REQUIRE_ORIGIN_TOKEN`: هل هو متطابق بين Akamai والـ backend؟

### المشكلة: `X-Forwarded-For` يظهر IP خاطئ في الـ logs

**السبب**: `AKAMAI_ENABLED=false` على الـ backend
- فعّل: `export AKAMAI_ENABLED=true` على HF Space + Vercel

---

## 5. الدعم (Support)

- **Akamai Support**: افتح ticket عبر [Akamai Control Center](https://control.akamai.com) → Support → Contact Us
- **Akamai Documentation**: <https://techdocs.akamai.com/>
- **Akamai Community**: <https://community.akamai.com/>

للأسئلة الداخلية عن تكامل BAZSPARK، راجع:
- `backend/akamai_middleware.py` (تكامل التطبيق)
- `docs/AKAMAI_PROTECTION_PLAN.md` (الخطة الكاملة)
- `docs/AKAMAI_TESTING_CHECKLIST.md` (قائمة الاختبار)
- `docs/AKAMAI_MONITORING.md` (دليل المراقبة)
- `docs/AKAMAI_INCIDENT_RESPONSE.md` (خطة الاستجابة للحوادث)
