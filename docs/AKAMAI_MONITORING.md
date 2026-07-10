# Akamai Monitoring Guide — BAZSPARK

> **دليل مراقبة BAZSPARK على Akamai**

---

## 1. لوحات المعلومات (Dashboards)

### 1.1 Akamai Control Center

| Dashboard | URL | الغرض |
|-----------|-----|------|
| Property Manager | [Control Center → Property Manager](https://control.akamai.com/wh).properties | حالة الـ properties والـ activations |
| Security Events | [Security → Security Events](https://control.akamai.com/wh.security.events) | هجمات محظورة + WAF events |
| Bot Manager | [Security → Bot Manager](https://control.akamai.com/wh.security.bot-manager) | إحصائيات الـ bots |
| Account Protector | [Security → Account Protector](https://control.akamai.com/wh.security.account-protector) | credential stuffing + ATO |
| API Security | [Security → API Security](https://control.akamai.com/wh.security.api-security) | endpoint violations + schema mismatches |
| Traffic Reports | [Reports → Traffic](https://control.akamai.com/wh.reports.traffic) | CDN cache hit ratio + bandwidth |
| Performance | [Performance → Performance](https://control.akamai.com/wh.performance) | latency + origin response time |

### 1.2 Backend Monitoring

| الموقع | الغرض |
|--------|------|
| HF Space logs | backend logs (AkamaiIntegrationMiddleware warnings) |
| `/api/v1/monitor/health` | backend health + DB connection |
| `/api/v1/monitor/metrics` | Prometheus-format metrics |
| Vercel logs | frontend build logs + edge function logs |

---

## 2. المقاييس الأساسية (Key Metrics)

### 2.1 أمان (Security)

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Blocked requests / hour | < 100 | > 1000 (spike = attack) |
| WAF rules triggered / hour | < 10 | > 100 (targeted attack) |
| Bot score > 80 requests / hour | < 50 | > 500 (bot swarm) |
| Failed logins / IP / 5 min | < 5 | > 10 (credential stuffing) |
| Geo-blocked requests / hour | < 20 | > 100 (distributed attack) |
| Direct origin attempts / day | 0 | > 1 (DNS leak or attack) |

### 2.2 أداء (Performance)

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Edge response time (P50) | < 100ms | > 500ms |
| Edge response time (P95) | < 500ms | > 2000ms |
| Origin response time (P50) | < 200ms | > 1000ms |
| Cache hit ratio (static) | > 95% | < 80% |
| Cache hit ratio (overall) | > 70% | < 50% |
| 5xx errors / minute | < 1 | > 10 |
| 4xx errors / minute | < 10 | > 100 |

### 2.3 توفر (Availability)

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Edge uptime | 99.99% | < 99.9% |
| Origin uptime (HF Space) | 99.5% | < 99% |
| TLS certificate validity | > 30 days remaining | < 7 days |
| Property activation status | ACTIVE | FAILED/ABORTED |

---

## 3. التنبيهات (Alerts)

### 3.1 Akamai Native Alerts

فعّل هذه عبر **Account Admin → Alerts**:

| Alert Type | Trigger | Notification |
|------------|---------|--------------|
| Security Event Spike | > 100 blocked requests in 5 min | Email + webhook |
| Origin 5xx Spike | > 10 5xx in 1 min | Email + webhook |
| Cache Hit Drop | ratio drops > 20% in 1 hour | Email |
| Bot Attack Detected | Bot Manager auto-detection | Email + webhook |
| Property Activation Failed | activation status = FAILED | Email + SMS |
| TLS Expiring | cert < 30 days remaining | Email |
| DDoS Attack | Akamai Prolexic triggered | Email + SMS + webhook |

### 3.2 Backend Alerts

في HF Space logs، ابحث عن:

```bash
# Warning: Missing Akamai-Internal token (potential bypass attempt)
grep "Missing Akamai-Internal token" /var/log/fireai/app.log

# Warning: Geo-blocked request
grep "Geo-blocked request" /var/log/fireai/app.log

# Warning: Bot score exceeded
grep "Bot score.*exceeds threshold" /var/log/fireai/app.log

# Critical: Direct origin access blocked
grep "Direct origin access blocked" /var/log/fireai/app.log
```

### 3.3 Webhook Integration

عيّن webhook URL (مثل `/api/v1/admin/security/alerts` على BAZSPARK) لاستقبال:

```json
{
  "alert_type": "SECURITY_EVENT_SPIKE",
  "severity": "HIGH",
  "timestamp": "2026-07-09T21:03:00Z",
  "property_id": "prp_XXXXXX",
  "details": {
    "blocked_count": 145,
    "window": "5min",
    "top_attack_type": "SQL_INJECTION",
    "top_source_ip": "203.0.113.5"
  }
}
```

---

## 4. المراقبة في الوقت الفعلي (Real-time Monitoring)

### 4.1 Akamai Real-Time Reports

- **Traffic**: <https://control.akamai.com/wh.reports.real-time-traffic>
- **Security Events**: <https://control.akamai.com/wh.security.events.real-time>
- **Origin Health**: <https://control.akamai.com/wh.origin-health>

### 4.2 Backend Real-time

```bash
# Watch HF Space logs in real-time
curl -N -H "Authorization: Bearer $HF_TOKEN" \
  "https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/logs/build?stream=true" | \
  grep -E "WARNING|ERROR|CRITICAL"

# Poll health endpoint
watch -n 5 'curl -s https://ahmdelbaz28-bazspark.hf.space/api/health | jq ".data.status"'

# Watch DB connection
watch -n 30 'curl -s https://ahmdelbaz28-bazspark.hf.space/api/health | jq ".data.database"'
```

---

## 5. تقارير دورية (Periodic Reports)

### 5.1 يومياً (Daily)

```bash
# Generate daily security report
python scripts/akamai_daily_report.py --date $(date -d "yesterday" +%Y-%m-%d) \
  --output /home/z/my-project/download/akamai-daily-$(date +%Y%m%d).pdf
```

المحتوى:
- إجمالي الطلبات
- الطلبات المحظورة (مع الأسباب)
- أعلى 10 IPs مُصدرة للطلبات
- أعلى 10 دول
- WAF rules triggered
- Bot score distribution
- Cache hit ratio
- Average latency

### 5.2 أسبوعياً (Weekly)

- تحليل اتجاهات الهجمات
- مراجعة الـ false positives (مع تحديث WAF exceptions)
- تحديث قائمة الـ allowed bots إن لزم

### 5.3 شهرياً (Monthly)

- مراجعة شاملة لأداء Akamai
- مقارنة مع الأشهر السابقة
- تقرير للإدارة العليا

---

## 6. استكشاف الأخطاء (Troubleshooting)

### 6.1 ارتفاع مفاجئ في 5xx errors

1. تحقق من **Akamai Security Events** (هل هناك هجوم؟)
2. تحقق من **HF Space status** (هل الـ Space sleeping؟)
3. تحقق من **Origin Response Time** في Akamai Performance dashboard
4. راجع **backend logs** للأخطاء

### 6.2 انخفاض cache hit ratio

1. تحقق من `Cache-Control` headers على الاستجابات
2. تأكد أن static assets لها hash في اسم الملف (`index-xxxx.js`)
3. راجع property-main.json caching rules

### 6.3 WAF يحظر طلبات شرعية (false positives)

1. ابحث عن الـ request في **Security Events** بالـ `X-Akamai-GRN` header
2. حدّد أي rule حظر الطلب
3. أضف exception في `kona-config.json` → `exceptions` array
4. اعمل activate على staging → اختبر → activate على production

---

## 7. المراجع

- [Akamai Kona Site Defender Docs](https://techdocs.akamai.com/kona-site-defender)
- [Akamai Bot Manager Docs](https://techdocs.akamai.com/bot-manager)
- [Akamai Security Events API](https://techdocs.akamai.com/security-events)
- [Akamai Reporting API](https://techdocs.akamai.com/reporting)
