# Akamai Testing Checklist — BAZSPARK

> **قائمة اختبار ما بعد نشر Akamai**
> Run every test in this checklist after each Akamai Property activation
> (staging AND production). Document the results in `docs/akamai-test-results.md`.

---

## 1. اختبارات الاتصال الأساسية (Basic Connectivity)

### 1.1 DNS Resolution
- [ ] `dig api.bazspark.com` يعيد IPs تابعة لـ Akamai (23.x.x.x أو أي نطاق Akamai)
- [ ] `dig api.bazspark.com +short` يعيد CNAME إلى `*.edgeservices.net`
- [ ] `dig bazspark.com` يعيد Akamai apex IPs

### 1.2 HTTPS Connection
- [ ] `curl -I https://api.bazspark.com` يعود `200 OK` أو `401 Unauthorized` (لكن ليس 5xx)
- [ ] TLS 1.3 مُفعّل: `openssl s_client -connect api.bazspark.com:443 -tls1_3`
- [ ] شهادة TLS صالحة: `echo | openssl s_client -connect api.bazspark.com:443 2>/dev/null | openssl x509 -noout -dates`

### 1.3 Health Endpoint
- [ ] `curl https://api.bazspark.com/api/health` يعود JSON صالح
- [ ] الحالة: `"status": "ok"`
- [ ] قاعدة البيانات: `"database": "connected"`
- [ ] Uptime: `> 60` seconds

---

## 2. اختبارات Akamai Edge (Edge Headers)

### 2.1 EdgeWorker: inject-headers
- [ ] `curl -I https://api.bazspark.com/api/health` يحتوي على:
  ```
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  Referrer-Policy: no-referrer
  X-Akamai-EdgeWorker: inject-headers
  X-Akamai-EdgeWorker-Processed: true
  ```

### 2.2 EdgeWorker: verify-origin
- [ ] `curl -I https://api.bazspark.com/api/health` يحتوي على:
  ```
  X-Akamai-Translated-Request: true
  ```
- [ ] `curl -I https://api.bazspark.com/api/health` يحتوي على:
  ```
  X-Akamai-GRN: <request_id>
  ```

### 2.3 True-Client-IP injection
- [ ] استخدم endpoint يطبع IP الطلب (مثل `/api/v1/whoami` إن وجد، أو راجع logs)
- [ ] IP العميل الحقيقي يظهر في الـ logs (وليس Akamai edge IP مثل `23.32.x.x`)
- [ ] تحقق من audit trail: `SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 5;`

---

## 3. اختبارات WAF / Kona Rules

### 3.1 SQL Injection Blocking
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects?id=1' OR '1'='1"`
  - متوقع: `403 Forbidden` مع `X-Akamai-WAF: DENY`
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects?id=1; DROP TABLE projects;--"`
- [ ] **DENY**: `curl -X POST https://api.bazspark.com/api/v1/projects -d '{"name":"test\"; DROP TABLE users;--"}'`

### 3.2 XSS Blocking
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects?name=<script>alert(1)</script>"`
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects?name=<img src=x onerror=alert(1)>"`

### 3.3 Path Traversal Blocking
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects/../../../etc/passwd"`
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects/..%2F..%2Fetc%2Fpasswd"`

### 3.4 Command Injection Blocking
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects?id=1;cat /etc/passwd"`
- [ ] **DENY**: `curl "https://api.bazspark.com/api/v1/projects?id=1|whoami"`

### 3.5 Attack Tool User-Agent Blocking
- [ ] **DENY**: `curl -A "sqlmap/1.5" https://api.bazspark.com/api/v1/projects`
- [ ] **DENY**: `curl -A "nikto/2.1" https://api.bazspark.com/api/v1/projects`
- [ ] **DENY**: `curl -A "masscan" https://api.bazspark.com/api/v1/projects`

### 3.6 HTTP Method Restriction
- [ ] **DENY**: `curl -X TRACE https://api.bazspark.com/`
- [ ] **DENY**: `curl -X CONNECT https://api.bazspark.com/`
- [ ] **ALLOW**: `curl -X GET https://api.bazspark.com/api/health`
- [ ] **ALLOW**: `curl -X POST https://api.bazspark.com/api/v1/auth/login -H "Content-Type: application/json" -d '{}'`

---

## 4. اختبارات Rate Limiting

### 4.1 API Rate Limit (300/minute per IP)
- [ ] شغّل 350 طلب في دقيقة:
  ```bash
  for i in {1..350}; do
    curl -s -o /dev/null -w "%{http_code}\n" \
      -H "X-API-Key: $API_KEY" \
      https://api.bazspark.com/api/v1/projects
  done | sort | uniq -c
  ```
  - متوقع: 300×`200` + 50×`429`
- [ ] تحقق من header `X-RateLimit-Remaining` و `X-RateLimit-Reset`

### 4.2 Auth Rate Limit (10/minute per IP)
- [ ] شغّل 15 محاولة login فاشلة في دقيقة:
  ```bash
  for i in {1..15}; do
    curl -s -o /dev/null -w "%{http_code}\n" \
      -X POST https://api.bazspark.com/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"api_key":"invalid"}'
  done | sort | uniq -c
  ```
  - متوقع: 10×`401` + 5×`429`

### 4.3 Captcha After Failed Logins
- [ ] بعد 3 failed logins، الطلب التالي يحتوي على CAPTCHA challenge:
  ```bash
  curl -v -X POST https://api.bazspark.com/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"api_key":"invalid"}'
  # Look for: 200 OK with HTML body containing "captcha"
  ```

---

## 5. اختبارات Bot Manager

### 5.1 Browser Bot Detection
- [ ] استخدم Chrome DevTools Network tab، أرسل طلب، تحقق من:
  - `Akamai-Bot-Score` header (0-30 = human)
  - `Akamai-Bot-Category` = `HUMAN`

### 5.2 Scripted Bot Detection
- [ ] `curl -A "Python/3.9 requests/2.28" https://api.bazspark.com/api/v1/projects` → تحقق من:
  - `Akamai-Bot-Score` header (60-100 = bot)
  - أو `403 Forbidden` على endpoints حساسة

### 5.3 Browser Bot (Selenium/Puppeteer)
- [ ] شغّل Selenium script بسيط، تحقق من:
  - `Akamai-Bot-Score` header (21-40 = browser bot)
  - الطلب يمر بدون مشاكل

### 5.4 JS Challenge on Login
- [ ] في المتصفح، افتح DevTools، ادخل `/api/v1/auth/login`:
  - تحقق من وجود challenge request (301/302 redirect أو 200 with JS challenge)
  - بعد حل الـ challenge، الـ login request ينجح

---

## 6. اختبارات Geo Blocking

### 6.1 Sanctioned Country Block
- [ ] استخدم VPN (مثل NordVPN) بـ server في إيران:
  - `curl https://api.bazspark.com/api/v1/projects` → `403 Forbidden`
  - الـ body: `{"code": "GEO_BLOCKED", "message": "Access from IR is not permitted"}`
- [ ] كرر لبقية الدول: RU, KP, SY, CU, VE, BY

### 6.2 Allowed Country Access
- [ ] بدون VPN (من مصر مثلاً):
  - `curl https://api.bazspark.com/api/health` → `200 OK`
  - `Akamai-Geo-Country: EG` header موجود

### 6.3 Health Endpoint Exception
- [ ] من دولة ممنوعة، `curl https://api.bazspark.com/api/health` → `200 OK`
  - (الاستثناء مسموح)

---

## 7. اختبارات Account Protector

### 7.1 Credential Stuffing Detection
- [ ] شغّل 50 login attempts بأسماء مستخدمين مختلفة في 5 دقائق:
  ```bash
  for i in {1..50}; do
    curl -X POST https://api.bazspark.com/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d "{\"api_key\":\"fake_key_$i\"}"
  done
  ```
- [ ] بعد 50 محاولة، IP محظور لمدة ساعة
- [ ] تحقق من الـ webhook (إذا تم تكوينه): استلم alert JSON

### 7.2 Brute Force Detection
- [ ] شغّل 11 login attempts لنفس الـ API key:
  ```bash
  for i in {1..11}; do
    curl -X POST https://api.bazspark.com/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"api_key":"known_invalid_key"}'
  done
  ```
- [ ] بعد 10 محاولات، الحساب محظور لمدة 30 دقيقة

### 7.3 ATO (Account Takeover) Detection
- [ ] سجّل دخول من IP جغرافي مختلف (VPN بمسافة > 500km):
  - متوقع: طلب step-up authentication (2FA أو email verification)

---

## 8. اختبارات Direct Origin Bypass Prevention

### 8.1 Direct HF Space Access
- [ ] `curl -H "X-Forwarded-For: 1.2.3.4" https://ahmdelbaz28-bazspark.hf.space/api/health`
  - متوقع: `403 Forbidden` مع `X-Akamai-Translated-Request: absent` (لأن الـ middleware رفض)
  - **في الإنتاج**: رفض مباشر
  - **في التطوير**: السماح مع log warning

### 8.2 Direct Vercel Access
- [ ] `curl https://revit-xxxx.vercel.app/api/health`
  - متوقع: `403 Forbidden` (إذا Vercel خلف Akamai) أو `200 OK` (إذا Vercel يستخدم مباشرة)

### 8.3 Missing Origin Token
- [ ] على الـ origin مباشرة، أرسل طلب بدون header `Akamai-Internal`:
  - متوقع في الإنتاج: `403 Forbidden`

---

## 9. اختبارات الأداء (Performance)

### 9.1 Latency
- [ ] `curl -w "@curl-format.txt" -o /dev/null -s https://api.bazspark.com/api/health`
  - `curl-format.txt`:
    ```
    time_namelookup:  %{time_namelookup}\n
    time_connect:     %{time_connect}\n
    time_appconnect:  %{time_appconnect}\n
    time_pretransfer: %{time_pretransfer}\n
    time_starttransfer: %{time_starttransfer}\n
    time_total:       %{time_total}\n
    ```
  - متوقع: `time_total < 500ms` للـ API endpoints

### 9.2 Cache Hit Ratio (Static Assets)
- [ ] `curl -I https://api.bazspark.com/assets/index-xxxx.js` مرتين
  - متوقع: الطلب الثاني يحتوي على `X-Cache: HIT` من Akamai
- [ ] راجع `X-Cache-Key`, `X-Cache-Action`, `X-Cache-Origin` headers

### 9.3 Concurrent Connections
- [ ] شغّل 100 طلب متزامن:
  ```bash
  ab -n 100 -c 10 https://api.bazspark.com/api/health
  ```
  - متوقع: `100% success rate`, `mean latency < 200ms`

---

## 10. اختبارات الأمان المتقدمة (Advanced Security)

### 10.1 SSL Labs Test
- [ ] افتح <https://www.ssllabs.com/ssltest/analyze.html?d=api.bazspark.com>
- [ ] متوقع: **A+ grade** مع:
  - TLS 1.3 مُفعّل
  - TLS 1.0 / 1.1 مُعطّل
  - HSTS مُفعّل
  - Certificate valid + chain complete
  - No weak ciphers

### 10.2 SecurityHeaders.com
- [ ] افتح <https://securityheaders.com/?q=api.bazspark.com>
- [ ] متوقع: **A grade** على الأقل

### 10.3 CSP Evaluation
- [ ] افتح <https://csp-evaluator.withgoogle.com/>
- [ ] الصق CSP header من response
- [ ] متوقع: لا توجد warnings حرجة

### 10.4 External Penetration Test
- [ ] شغّل OWASP ZAP ضد `https://api.bazspark.com`:
  ```bash
  docker run -t owasp/zap2docker-stable zap-baseline.py -t https://api.bazspark.com
  ```
- [ ] راجع النتائج، يجب ألا يكون هناك high-severity findings

---

## 11. اختبارات الـ Failover (Failover Testing)

### 11.1 Origin Failure
- [ ] أوقف HF Space مؤقتاً (pause the Space)
- [ ] تحقق من استجابة Akamai:
  - متوقع: `503 Service Unavailable` بعد `timeoutResponse: 300s` (إذا كان في property-main.json)
  - أو: `200 OK` من cached response (إذا كان static asset)

### 11.2 Stale Content Serving
- [ ] أوقف الـ origin، اطلب صفحة static قديمة
- [ ] متوقع: `200 OK` من Akamai cache مع `X-Cache: HIT` و warning header

### 11.3 Recovery
- [ ] أعد تشغيل HF Space
- [ ] تحقق من `/api/health` يعود `200 OK`

---

## 12. التحقق النهائي (Final Verification)

### 12.1 Complete Smoke Test
- [ ] شغّل سكريبت الاختبار الشامل:
  ```bash
  python tests/akamai_smoke_test.py --base-url https://api.bazspark.com --api-key $API_KEY
  ```

### 12.2 Real User Monitoring
- [ ] افتح `https://api.bazspark.com` في المتصفح
- [ ] سجّل دخول بـ API key صالح
- [ ] تنقّل في Dashboard → Room Design → Marine → AI Agent → Reports
- [ ] كل صفحة تحمل بدون أخطاء
- [ ] Network tab لا يظهر أخطاء 5xx أو CORS

### 12.3 Sign-off
- [ ] كل الاختبارات السابقة نجحت
- [ ] لا يوجد أخطاء في Akamai Security Events (خلال آخر 24 ساعة)
- [ ] لا يوجد أخطاء في HF Space logs (خلال آخر 24 ساعة)
- [ ] الـ backend health يعود `status: ok`

---

## 13. تقرير النتائج (Test Results Report)

بعد إكمال الاختبارات، اكتب تقريراً في `docs/akamai-test-results.md`:

```markdown
# Akamai Deployment Test Results — YYYY-MM-DD

## Environment
- Property ID: prp_XXXXXX
- Version: vX
- Network: PRODUCTION
- Tested by: Ahmed Elbaz

## Summary
- Total tests: 80
- Passed: 78
- Failed: 2
- Blocked: 0

## Failed Tests
### Test 4.2 — Auth Rate Limit
- Expected: 10×401 + 5×429
- Actual: 15×401
- Root cause: AKAMAI_ENABLED=false on HF Space (forgot to set)
- Fix: Set AKAMAI_ENABLED=true, restart Space, retest.

### Test 7.1 — Credential Stuffing
- Expected: IP blocked after 50 attempts
- Actual: No block observed
- Root cause: Account Protector not activated in Akamai Control Center
- Fix: Activate Account Protector policy in Security Configurations.

## Sign-off
- [ ] All critical tests pass
- [ ] Failed tests have remediation plan
- [x] Ready for production traffic

Signed: Ahmed Elbaz
Date: YYYY-MM-DD
```
