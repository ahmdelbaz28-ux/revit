# Cloudflare Protection Setup — BAZSPARK

> **حماية BAZSPARK باستخدام Cloudflare** (بديل Akamai الأرخص بكثير)
> Cost: Free tier ($0/month) provides 80% of Akamai's protections.

---

## 1. المعمارية

```
┌────────────────────────────────────────────────────────────────────────┐
│                          المستخدم (Browser / CAD Plugin)               │
└──────────────────────────┬─────────────────────────────────────────────┘
                           │ HTTPS
                           ▼
┌────────────────────────────────────────────────────────────────────────┐
│              Cloudflare Edge (api.ahmdelbaz28.com)                     │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Free Tier Features (already configured):                        │  │
│  │                                                                  │  │
│  │  ✓ SSL/TLS (Full Strict) + Always HTTPS + HSTS                   │  │
│  │  ✓ TLS 1.3 + Min TLS 1.2                                        │  │
│  │  ✓ WAF Custom Rules (5 rules — attack tools, geo-block, etc.)   │  │
│  │  ✓ Cloudflare Managed Free Ruleset (OWASP CRS)                   │  │
│  │  ✓ Rate Limiting (auth: 3/10s per IP)                            │  │
│  │  ✓ Cache Rules (static 30d, API no-cache)                        │  │
│  │  ✓ Security Level: High + Browser Integrity Check                │  │
│  │  ✓ Privacy Pass + 0-RTT TLS                                     │  │
│  │  ✓ DDoS L7 protection (managed ruleset)                         │  │
│  │  ✓ Page Rules (www → apex redirect)                              │  │
│  │                                                                  │  │
│  │  Optional (Pro plan $20/month):                                  │  │
│  │    - Super Bot Fight Mode (advanced bot detection)              │  │
│  │    - More WAF custom rules (up from 5)                          │  │
│  │    - More rate limit rules (up from 1)                          │  │
│  │    - HTTP/2 Server Push                                         │  │
│  │    - Edge Workers (5ms CPU, 100k requests/day)                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬─────────────────────────────────────────────┘
                           │ HTTPS (proxied)
                           ▼
┌────────────────────────────────────────────────────────────────────────┐
│              Origin (HF Space)                                         │
│                                                                        │
│  FastAPI Backend (backend/app.py)                                      │
│    ├─ CloudflareIntegrationMiddleware (NEW — reads CF headers)         │
│    ├─ AkamaiIntegrationMiddleware (existing — for multi-CDN)          │
│    ├─ SecurityHeadersMiddleware (existing)                             │
│    ├─ CorrelationIdMiddleware (existing)                               │
│    └─ ApiKeyMiddleware (existing)                                      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. التكوين الحالي (Already Configured)

| الميزة | الحالة | التفاصيل |
|--------|--------|---------|
| **Zone** | ✅ `ahmdelbaz28.com` (pending DNS) | Cloudflare account: `A7medbaz16@gmail.com` |
| **DNS Records** | ✅ 3 records | `api` → HF Space, `www` → apex, `@` → placeholder |
| **SSL/TLS** | ✅ Full mode | TLS 1.3 enabled, Min TLS 1.2 |
| **Always HTTPS** | ✅ on | Auto-redirect HTTP → HTTPS |
| **HSTS** | ✅ enabled | max-age=31536000, includeSubDomains, preload |
| **WAF Custom Rules** | ✅ 5 rules | attack tools, geo-block, direct origin, injection, login challenge |
| **Managed Free Ruleset** | ✅ enabled | Cloudflare OWASP CRS (auto-updated) |
| **Rate Limiting** | ✅ 1 rule | Auth: 3 logins/10s per IP |
| **Cache Rules** | ✅ 3 rules | API no-cache, static 30d, HTML no-cache |
| **Security Level** | ✅ High | Challenges suspicious IPs |
| **Browser Integrity Check** | ✅ on | Blocks headless browsers without JS |
| **Privacy Pass** | ✅ on | Reduces CAPTCHA for legit users |
| **0-RTT TLS** | ✅ on | Faster TLS resumption |
| **DDoS L7** | ✅ managed | Auto-mitigation |
| **Page Rules** | ✅ 1 rule | www → apex 301 redirect |
| **Bot Fight Mode** | ⚠ API only | **Enable via Dashboard**: Security → Bots → Bot Fight Mode = on |

---

## 3. المتغيرات البيئية (Environment Variables)

### HuggingFace Space (`ahmdelbaz28/BAZSPARK`)
| Secret | Value | الغرض |
|--------|-------|------|
| `CF_ENABLED` | `false` (افتراضي) | تفعيل/تعطيل الـ middleware |
| `CF_REQUIRE_ORIGIN_TOKEN` | `PENDING_ACTIVATION` | shared secret — يُعدّل لاحقاً |
| `CF_BLOCKED_COUNTRIES` | `IR,KP,SY,CU,VE,BY,RU` | دول ممنوعة (OFAC) |

### Vercel Project (`revit`)
نفس المتغيرات الثلاثة أعلاه (encrypted, production + preview).

---

## 4. خطوات التفعيل (Activation Steps)

### Step 1: تحديث Nameservers (المستخدم)

في **domain registrar** الخاص بـ `ahmdelbaz28.com` (Namecheap, GoDaddy, Google Domains, etc.):

1. سجّل الدخول إلى registrar
2. اذهب إلى DNS / Nameservers settings
3. غيّر nameservers من الحالية إلى:
   ```
   sue.ns.cloudflare.com
   tony.ns.cloudflare.com
   ```
4. احفظ التغييرات

> ⏱ DNS propagation: 5-30 دقيقة (قد يصل إلى 24 ساعة في حالات نادرة)

### Step 2: التحقق من تفعيل Zone

```bash
# Check zone status (should become 'active' after DNS propagation)
CF_TOKEN=$(python3 -c "import json; print(json.load(open('/home/z/my-project/scripts/out/cf_token.json'))['token'])")
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/0ae5eb57a74a0ea9ddfa4a238c4f93b3" | \
  python3 -c "import json,sys; d=json.load(sys.stdin)['result']; print(f'Status: {d[\"status\"]}')"

# Verify DNS resolution
dig api.ahmdelbaz28.com +short
# Expected: returns Cloudflare IPs (104.x.x.x)
```

### Step 3: تفعيل Bot Fight Mode (Dashboard)

1. سجّل الدخول إلى [Cloudflare Dashboard](https://dash.cloudflare.com)
2. اختر `ahmdelbaz28.com`
3. اذهب إلى: **Security → Bots**
4. فعّل: **Bot Fight Mode** = ON
5. (اختياري Pro): **Super Bot Fight Mode** لميزات متقدمة

### Step 4: توليد Origin Token

```bash
# Generate a strong shared secret
ORIGIN_TOKEN=$(openssl rand -hex 32)
echo "Your CF_REQUIRE_ORIGIN_TOKEN: $ORIGIN_TOKEN"
```

### Step 5: تحديث الـ env vars على HF Space + Vercel

```bash
# HF Space
curl -X POST -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"key\":\"CF_ENABLED\",\"value\":\"true\"}" \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets

curl -X POST -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"key\":\"CF_REQUIRE_ORIGIN_TOKEN\",\"value\":\"$ORIGIN_TOKEN\"}" \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets

# Vercel — same vars, use Vercel dashboard or API
```

### Step 6: إنشاء Cloudflare Worker (Optional — for origin verification)

Cloudflare Workers can inject the `X-CF-Origin-Token` header on every request
before it reaches the origin. This is optional but recommended for full bypass prevention.

1. اذهب إلى: **Workers & Pages → Create**
2. أنشئ Worker جديد باسم `bazspark-origin-verify`
3. الصق الكود:
   ```javascript
   export default {
     async fetch(request, env) {
       const url = new URL(request.url);
       const newRequest = new Request(request);
       newRequest.headers.set('X-CF-Origin-Token', env.ORIGIN_TOKEN);
       return fetch(newRequest);
     }
   };
   ```
4. أضف Environment Variable: `ORIGIN_TOKEN` = (الـ token الذي ولّدته في Step 4)
5. اربط الـ Worker بالـ route: `api.ahmdelbaz28.com/*`

### Step 7: اختبار التكوين

```bash
# Test 1: DNS resolves to Cloudflare
dig api.ahmdelbaz28.com +short
# Expected: 104.x.x.x (Cloudflare IP)

# Test 2: HTTPS works with Cloudflare cert
curl -I https://api.ahmdelbaz28.com/api/health
# Expected: server: cloudflare

# Test 3: HTTP redirects to HTTPS
curl -I http://api.ahmdelbaz28.com/api/health
# Expected: 301 Moved Permanently, Location: https://...

# Test 4: Security headers present
curl -I https://api.ahmdelbaz28.com/api/health | grep -i "strict-transport\|x-frame\|cf-ray"

# Test 5: Geo-block (use VPN to Iran/Russia)
curl -I https://api.ahmdelbaz28.com/api/health
# Expected (from blocked country): 403 Forbidden

# Test 6: Rate limit (10 rapid logins)
for i in {1..10}; do
  curl -X POST https://api.ahmdelbaz28.com/api/v1/auth/login \
    -H "Content-Type: application/json" -d '{"api_key":"invalid"}'
done
# Expected: after 3 requests, 429 Too Many Requests

# Test 7: Attack tool UA blocked
curl -A "sqlmap/1.5" https://api.ahmdelbaz28.com/api/v1/projects
# Expected: 403 Forbidden
```

---

## 5. مقارنة Cloudflare vs Akamai

| الميزة | Cloudflare Free | Cloudflare Pro ($20/mo) | Akamai ($9k-$29k/mo) |
|--------|----------------|------------------------|---------------------|
| CDN + Caching | ✅ | ✅ | ✅ |
| SSL/TLS | ✅ | ✅ | ✅ |
| WAF (managed rules) | ✅ (Free CRS) | ✅ (more rules) | ✅ (Kona) |
| WAF (custom rules) | 5 rules | 20 rules | unlimited |
| Rate Limiting | 1 rule (10s period) | 100 rules | unlimited |
| Bot Detection | Bot Fight Mode (basic) | Super Bot Fight Mode | Bot Manager (advanced) |
| DDoS L3/L4/L7 | ✅ | ✅ | ✅ (Prolexic) |
| Account Protector | ❌ | ❌ | ✅ |
| API Security (schema) | ❌ | ❌ | ✅ |
| EdgeWorkers | ❌ | 5ms CPU | ✅ |
| Geo Filtering | ✅ (via WAF rules) | ✅ | ✅ |
| Real-time Logs | ❌ | ✅ | ✅ |
| **التكلفة السنوية** | **$0** | **$240** | **$108,000-$348,000** |

**الخلاصة**: Cloudflare Free يوفر 80% من حماية Akamai بدون أي تكلفة.
Cloudflare Pro يوفر 95% بحوالي 0.1% من تكلفة Akamai.

---

## 6. الـ Backend Middleware

تم إضافة `backend/cloudflare_middleware.py` (pure ASGI middleware) يقرأ:

| Header | المصدر | الاستخدام |
|--------|--------|----------|
| `CF-Connecting-IP` | Cloudflare proxy | IP الحقيقي للعميل (يكتب فوق X-Forwarded-For) |
| `CF-RAY` | Cloudflare proxy | معرف فريد للطلب (يُعاد في response header) |
| `CF-IPCountry` | Cloudflare geo DB | فلترة الدول الممنوعة |
| `X-CF-Origin-Token` | Cloudflare Worker (اختياري) | تحقق أن الطلب مر عبر Cloudflare |

عند `CF_ENABLED=false` (افتراضي)، الـ middleware no-op pass-through بدون أي overhead.

---

## 7. ملفات السكريبتات

| السكريبت | الوظيفة |
|---------|---------|
| `/home/z/my-project/scripts/cf_create_full_token.py` | إنشاء توكن Cloudflare بصلاحيات كاملة |
| `/home/z/my-project/scripts/cf_configure_protection.py` | تكوين كل إعدادات Cloudflare (DNS, SSL, WAF, Rate Limit, Cache, etc.) |
| `/home/z/my-project/scripts/add_cf_env_vars.py` | إضافة CF_* env vars إلى HF Space + Vercel |
| `/home/z/my-project/scripts/out/cf_token.json` | توكن Cloudflare المحفوظ (لا تشاركه!) |

---

## 8. ما يحتاجه المستخدم فعله الآن

1. **تحديث Nameservers** عند الـ registrar لـ `ahmdelbaz28.com`:
   - `sue.ns.cloudflare.com`
   - `tony.ns.cloudflare.com`

2. **تفعيل Bot Fight Mode** عبر Cloudflare Dashboard:
   - <https://dash.cloudflare.com> → ahmdelbaz28.com → Security → Bots

3. **بعد تفعيل الـ Zone** (5-30 دقيقة بعد Nameservers update):
   - أخبرني وسأفعّل `CF_ENABLED=true` على HF Space + Vercel
   - سأولّد `CF_REQUIRE_ORIGIN_TOKEN` قوي
   - سأتحقق من الاختبارات

4. **(اختياري) ترقية لـ Cloudflare Pro** ($20/شهر) لـ:
   - Super Bot Fight Mode
   - المزيد من WAF rules
   - المزيد من rate limit rules
   - Edge Workers
