# Akamai Incident Response — BAZSPARK

> **خطة الاستجابة للحوادث الأمنية على Akamai**
> Follow this runbook when an Akamai-related security incident is detected.

---

## 1. تصنيف الحوادث (Incident Severity)

| Severity | Definition | Examples | Response Time |
|----------|-----------|----------|---------------|
| **SEV-1 (Critical)** | Service down or active breach | DDoS overwhelming origin, confirmed data breach, WAF bypass exploited | < 15 min |
| **SEV-2 (High)** | Major degradation or active attack | Credential stuffing attack, bot swarm, 5xx spike > 50% | < 1 hour |
| **SEV-3 (Medium)** | Minor degradation or isolated attack | Single IP abuse, WAF false positive, cache hit drop | < 4 hours |
| **SEV-4 (Low)** | Investigation needed | Suspicious pattern, low-volume scan, config warning | Next business day |

---

## 2. SEV-1: DDoS Attack

### 2.1 Indicators
- Akamai sends DDoS alert (Prolexic triggered)
- Origin 5xx errors > 100/minute
- Origin response time > 5000ms
- Backend `/api/health` returns `database: disconnected` (origin overwhelmed)

### 2.2 Immediate Actions (first 5 minutes)

1. **Acknowledge alert** في Akamai Control Center
2. **Verify it's a real attack** (not a marketing campaign / load test):
   ```bash
   # Check traffic sources
   curl -H "Authorization: Bearer $AKAMAI_TOKEN" \
     "https://{host}/reporting-api/v1/reports/traffic-by-time/summarize?start=$(date -d '15 min ago' -u +%Y-%m-%dT%H:%M)&end=$(date -u +%Y-%m-%dT%H:%M)"
   ```
3. **Activate DDoS Protection Mode** في Property Manager:
   - Navigate to Property → Rules → DDoS Protection
   - Switch from "DETECT" to "MITIGATE"
   - Activate on production (immediate, no staging)
4. **Notify incident commander**: `eng.ahmed.elbaz@gmail.com` + `+20-XXX-XXXX-XXX`

### 2.3 Mitigation Actions (5-30 minutes)

1. **Block top attacking IPs**:
   - Akamai Control Center → Security → IP Allowlist/Denylist
   - Add offending IPs/CIDRs to denylist
2. **Tighten rate limits**:
   - Property Manager → Rate Limiting
   - Reduce API rate from 300/min → 50/min
   - Reduce auth rate from 10/min → 3/min
3. **Enable additional bot challenges**:
   - Bot Manager → All endpoints → JS Challenge
4. **Monitor**:
   - Watch Security Events dashboard
   - Watch origin 5xx error rate
   - Watch `/api/health` endpoint

### 2.4 Recovery (after attack subsides)

1. **Document the attack**:
   - Start time, end time, peak RPS, source IPs, attack type
   - Save Security Events CSV
2. **Gradually relax rate limits**:
   - 50/min → 100/min → 200/min → 300/min (every 30 min)
3. **Post-incident review** within 48 hours
4. **Update WAF rules** based on attack patterns

---

## 3. SEV-2: Credential Stuffing Attack

### 3.1 Indicators
- Account Protector alert: `CREDENTIAL_STUFFING_DETECTED`
- > 50 failed logins from same IP in 5 min
- > 500 failed logins across multiple IPs in 10 min
- Successful logins followed by immediate sensitive actions (API key generation)

### 3.2 Immediate Actions

1. **Verify the attack**:
   ```bash
   # Check failed login patterns
   curl -H "Authorization: Bearer $AKAMAI_TOKEN" \
     "https://{host}/siem/v1/attacks?attackType=credential_stuffing&start=$(date -d '1 hour ago' -u +%Y-%m-%dT%H:%M)"
   ```
2. **Auto-mitigation** (should trigger automatically):
   - Bot Manager blocks source IPs for 1 hour
   - Account Protector locks targeted accounts for 30 min
   - Backend rate limiter returns 429
3. **Manual escalation** (if auto-mitigation insufficient):
   - Bot Manager → Challenge ALL login attempts with CAPTCHA
   - Add source IPs to global denylist
4. **Notify affected users**:
   - Send email to all users whose accounts were targeted
   - Recommend password change if any account was compromised

### 3.3 Recovery

1. Review attack patterns
2. Update `account-protector.json` thresholds if needed
3. Add compromised credentials to forced password reset list

---

## 4. SEV-1: WAF Bypass Exploited

### 4.1 Indicators
- Successful SQL injection / XSS payload reaches backend
- Backend audit logs show unexpected SQL patterns
- Database integrity check fails
- WAF did NOT block the request (check Security Events)

### 4.2 Immediate Actions (first 15 minutes)

1. **Identify the bypass**:
   - Pull backend logs for the suspicious request
   - Extract the payload
   - Test the payload against staging WAF
2. **Block the specific pattern**:
   - Akamai Control Center → Security → Custom Rules
   - Add new rule: `IF request.body matches "<payload_pattern>" THEN DENY`
   - Activate immediately on production
3. **Identify compromised data**:
   ```bash
   # Check if data was exfiltrated
   grep "API_KEY_VALID" /var/log/fireai/audit.log | grep "<attacker_ip>"
   ```
4. **Rotate all API keys**:
   ```bash
   # Force-rotate ALL API keys (nuclear option)
   python scripts/rotate_all_api_keys.py --reason "WAF bypass incident"
   ```

### 4.3 Investigation (1-4 hours)

1. Pull all logs for the attacker IP (last 7 days)
2. Identify all affected endpoints
3. Notify users whose data may have been accessed
4. Engage Akamai support for forensic analysis

### 4.4 Recovery

1. Patch the WAF bypass (update Kona rules + custom rules)
2. Test the patch on staging
3. Deploy to production
4. Document the bypass in `docs/security/waf-bypasses-history.md`

---

## 5. SEV-2: Direct Origin Access Detected

### 5.1 Indicators
- Backend logs show: `Direct origin access blocked`
- Multiple requests to HF Space direct URL (`ahmdelbaz28-bazspark.hf.space`)
- The `Akamai-Internal` header is missing

### 5.2 Immediate Actions

1. **Confirm it's an attack** (not a misconfigured monitor):
   - Check User-Agent (curl/python = attack, uptime-monitor = misconfigured)
   - Check request pattern (single request = probe, flood = attack)
2. **Block the offending IPs**:
   - On HF Space: add to `BLOCKED_IPS` env var
   - On Vercel: add to firewall rules
3. **Investigate the leak**:
   - Search GitHub / public code for the HF Space URL
   - Search Shodan / Censys for indexed exposure
   - Check if a subdomain was previously pointing to HF Space
4. **Hide the origin** (long-term):
   - Consider moving backend to a non-public URL
   - Use Vercel's preview deployments (random URLs)
   - Configure HF Space to require auth header

### 5.3 Recovery

1. Update `AKAMAI_REQUIRE_ORIGIN_TOKEN` (rotate the secret)
2. Document the leak source in `docs/security/origin-leak-incident.md`

---

## 6. SEV-3: WAF False Positive

### 6.1 Indicators
- Legitimate user reports 403 Forbidden
- WAF rule triggered on a benign request
- Backend never received the request

### 6.2 Actions

1. **Get the request details**:
   - User provides: URL, method, body, timestamp, `X-Akamai-GRN` (if visible)
2. **Find the rule that blocked it**:
   - Akamai Control Center → Security Events
   - Search by `X-Akamai-GRN` or timestamp
3. **Add exception**:
   - Update `kona-config.json` → `exceptions` array
   - OR: Update the specific custom rule to be more specific
4. **Test on staging**:
   ```bash
   curl -H "Pragma: akamai-x-get-extracted-values" \
        -H "X-Akamai-Debug: true" \
        https://bazspark.edgeservices.net.staging.akamaihd.net/<path> \
        -d '<body>'
   ```
5. **Deploy to production**

---

## 7. Contact List

| Role | Name | Contact | When to contact |
|------|------|---------|-----------------|
| Incident Commander | Eng. Ahmed Elbaz | eng.ahmed.elbaz@gmail.com / +20-XXX | All SEV-1/SEV-2 incidents |
| Akamai Support | Akamai 24/7 | +1-617-444-2525 / Support Portal | WAF bypass, DDoS, Property activation issues |
| Backend Developer | (TBD) | (TBD) | Backend-specific issues |
| Database Admin | (TBD) | (TBD) | DB-related incidents |

---

## 8. Post-Incident Review Template

بعد كل incident (خلال 48 ساعة)، اكتب تقريراً في `docs/incidents/INCIDENT-YYYY-MM-DD-XX.md`:

```markdown
# Incident Report — YYYY-MM-DD-XX

## Summary
- Type: DDoS / Credential Stuffing / WAF Bypass / Other
- Severity: SEV-1 / SEV-2 / SEV-3
- Start: YYYY-MM-DD HH:MM (UTC)
- End: YYYY-MM-DD HH:MM (UTC)
- Duration: X hours Y minutes
- Detected by: Akamai alert / User report / Backend log

## Timeline
- HH:MM — Alert received
- HH:MM — Investigation started
- HH:MM — Root cause identified
- HH:MM — Mitigation applied
- HH:MM — Recovery complete

## Impact
- Users affected: X
- Requests blocked: X
- Data compromised: None / X records (describe)
- Downtime: X minutes
- Business impact: (describe)

## Root Cause
(Detailed technical analysis)

## Mitigation
(What was done to stop the incident)

## Lessons Learned
1. (Specific actionable lesson)
2. (Specific actionable lesson)

## Action Items
- [ ] Update WAF rule X — owner: NAME, due: YYYY-MM-DD
- [ ] Add monitoring for Y — owner: NAME, due: YYYY-MM-DD
- [ ] Train team on Z — owner: NAME, due: YYYY-MM-DD

## References
- Akamai Security Event ID: SE-XXXXXX
- HF Space logs: (link)
- Backend audit trail: (query)

## Sign-off
- Incident Commander: Ahmed Elbaz
- Date: YYYY-MM-DD
```
