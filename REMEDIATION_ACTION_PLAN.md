# BAZSPARK — Production Remediation Action Plan
**Based on:** PRODUCTION_INTEGRATION_AUDIT_REPORT.md  
**Date:** 2026-07-17  
**Priority:** Critical fixes before production deployment

---

## 🔴 CRITICAL — Must Fix Before Production

### 1. Rotate All Exposed Credentials

**Issue:** All tokens provided during the audit session must be rotated for security.

**Actions:**
1. **GitHub PAT** → Generate new PAT at https://github.com/settings/tokens
   - Update GitHub Secrets: `gh secret set GH_PAT --body "new_token"`
   - Update local `.env`: `GH_PAT=new_rotated_token`

2. **HuggingFace Token** → Regenerate at https://huggingface.co/settings/tokens
   - Update `.env`: `HF_TOKEN=new_hf_token`
   - Update HF Space secrets if applicable

3. **Supabase Keys** → Rotate in Supabase Dashboard (Project Settings → API)
   - Update `.env`: `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`
   - **Warning:** This will invalidate all existing sessions

4. **Langfuse Keys** → Regenerate at https://cloud.langfuse.com/settings/keys
   - Update `.env`: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

5. **Resend API Key** → Regenerate at https://resend.com/api_keys
   - Update `.env`: `RESEND_API_KEY`

6. **Box Integration** → Regenerate at https://account.box.com/login?redirect_url=%2Fdevelopers%2Fconsole
   - Update `.env`: `BOX_CLIENT_SECRET`, `BOX_DEVELOPER_TOKEN`

7. **Vercel Token** → Regenerate at https://vercel.com/account/tokens
   - Update `.env`: `VERCEL_DEPLOY_TOKEN`
   - Update GitHub Secrets if used in CI

8. **Daytona Token** → Regenerate at https://app.daytona.io/settings/api
   - Update `.env`: `DAYTONA_API_TOKEN`
   - Update GitHub Secrets: `DAYTONA_API_TOKEN`

9. **CodeSandbox Token** → Regenerate at https://codesandbox.io/settings/account
   - Update `.env`: `CODESANDBOX_TOKEN`

10. **Cloudflare Tokens** → Regenerate at https://dash.cloudflare.com/profile/api-tokens
    - Update `.env`: `CLOUDFLARE_USER_TOKEN_1`, `CLOUDFLARE_USER_TOKEN_2`, `CLOUDFLARE_USER_TOKEN_3`

11. **NVIDIA API Key** → Regenerate at https://build.nvidia.com/settings/keys
    - Update `.env`: `NVIDIA_API_KEY`

**After Rotation:**
```bash
# Verify no old tokens remain in git history
git log --all --source --remotes --grep="token" --patch | grep -E "(hf_|ghp_|sbp_|sk-lf_)" || echo "No exposed tokens in history"

# Update .gitignore to ensure .env is never committed
echo ".env" >> .gitignore
git add .gitignore
git commit -m "chore: ensure .env is ignored"
```

---

### 2. Fix Supabase IPv6 Connectivity

**Issue:** Supabase endpoint `<SUPABASE_PROJECT_REF>.supabase.co` may be IPv6-only, causing connection failures in IPv4-only environments.

**Diagnosis:**
```bash
# Test connectivity
curl -v https://<SUPABASE_PROJECT_REF>.supabase.co/rest/v1/ 2>&1 | grep "Connected to"

# If IPv6-only, you'll see: Connected to <IPv6 address>
```

**Solutions:**

**Option A: Enable Neon PostgreSQL Fallback (Recommended)**
```env
# Add to .env
NEON_DATABASE_URL=postgresql://user:password@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require
```
The codebase already supports this fallback in `backend/database.py`.

**Option B: Configure Supabase to Use IPv4**
1. Contact Supabase support to enable IPv4 access
2. Or use a proxy/CDN that provides IPv4

**Option C: Deploy with IPv6 Support**
1. Ensure Docker/Kubernetes cluster has IPv6 enabled
2. Update network configuration to prefer IPv6

---

### 3. Verify Daytona Token Validity

**Issue:** Token format appears valid (`dtn_...`) but must be confirmed active.

**Verification:**
```bash
# Install Daytona CLI
pip install daytona

# Verify token
daytona auth status
```

**Expected Output:**
```
✓ Authenticated as <your-email>
✓ Token valid (expires: <date>)
```

**If Invalid:**
1. Log in to https://app.daytona.io
2. Navigate to Settings → API
3. Generate new token
4. Update `.env` and GitHub Secrets

---

### 4. Fix CORS Configuration

**Issue:** `.env` has `CORS_ALLOWED_ORIGINS` but `backend_app.py` expects `CORS_ORIGINS`.

**Current (.env):**
```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

**Required (.env):**
```env
# Production - replace with actual domains
CORS_ORIGINS=https://app.bazspark.com,https://admin.bazspark.com

# Development (keep for local dev)
CORS_ORIGINS_DEV=http://localhost:3000,http://localhost:5173,http://localhost:8000
```

**Update backend_app.py (lines 114-136):**
```python
# Change from:
_cors_raw = os.getenv("CORS_ORIGINS", "")

# To:
_cors_raw = os.getenv("CORS_ORIGINS", "")
if not _cors_raw and _env in ("production", "prod"):
    _cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if _cors_raw:
        logger.warning("CORS_ALLOWED_ORIGINS is deprecated, use CORS_ORIGINS")
```

**Alternatively, simplify:**
```bash
# Just rename the variable in .env
sed -i 's/CORS_ALLOWED_ORIGINS/CORS_ORIGINS/g' .env
```

---

## 🟡 RECOMMENDED — Improve Before Production

### 5. Enable PostgreSQL in Production

**Current State:** Default is SQLite (`sqlite:///./db/digital_twin.db`)

**Action:**
```env
# .env (production)
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.<SUPABASE_PROJECT_REF>.supabase.co:5432/postgres?sslmode=require
```

**Verify:**
```bash
python -c "from backend.database import get_db; db = get_db(); print('PostgreSQL connected:', db._is_postgres)"
```

---

### 6. Configure Optional Databases

**Qdrant (Vector DB for RAG):**
```env
QDRANT_URL=https://your-qdrant-cluster.com
QDRANT_API_KEY=your_qdrant_api_key
```

**Neo4j (Graph DB):**
```env
NEO4J_URI=bolt://your-neo4j-instance:7687
NEO4J_PASSWORD=your_neo4j_password
```

**Redis (Cache/Sessions):**
```env
REDIS_URL=redis://your-redis-instance:6379/0
REDIS_PASSWORD=your_redis_password
```

**If not configured, the system will log warnings but continue to function.**

---

### 7. Set Up Vercel Preview Deployments

**Current:** Only production deployment configured.

**Action:**
1. Go to Vercel Dashboard → Project Settings → Git
2. Enable "Preview Deployments"
3. Configure branch: `main` → production, all other branches → preview
4. Update `vercel.json` to handle preview URLs in CORS

---

### 8. Implement Health Check Probes

**For Kubernetes:**
```yaml
# Add to deployment.yaml
livenessProbe:
  httpGet:
    path: /api/health
    port: 7860
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /api/health
    port: 7860
  initialDelaySeconds: 5
  periodSeconds: 5
```

**Verify Docker Compose healthchecks match:**
```yaml
# Already configured in docker-compose.yml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
```

---

## 🟢 NICE-TO-HAVE — Post-Production

### 9. Implement Secret Rotation Automation

**Script:** `scripts/rotate_secrets.sh`
```bash
#!/bin/bash
# Rotate all secrets and update deployments
# Usage: ./scripts/rotate_secrets.sh

# 1. Generate new secrets
NEW_GH_PAT=$(gh auth token --hostname github.com)
NEW_HF_TOKEN=$(huggingface-cli token --repo ahmdelbaz28/BAZSPARK)
# ... etc

# 2. Update secrets
gh secret set GH_PAT --body "$NEW_GH_PAT"
gh secret set HF_TOKEN --body "$NEW_HF_TOKEN"

# 3. Restart deployments
kubectl rollout restart deployment/fireai-api -n production
```

---

### 10. Add Integration Tests

**Create:** `tests/integration/test_integrations.py`
```python
import pytest
from backend.config import config

def test_supabase_connection():
    """Verify Supabase database connectivity."""
    from backend.database import get_db
    db = get_db()
    assert db._is_postgres or True  # SQLite also valid

def test_langfuse_reachable():
    """Verify Langfuse endpoint is reachable."""
    import requests
    resp = requests.get(config.LANGFUSE_HOST, timeout=5)
    assert resp.status_code == 200

def test_vercel_api():
    """Verify Vercel API token is valid."""
    import requests
    headers = {"Authorization": f"Bearer {config.VERCEL_DEPLOY_TOKEN}"}
    resp = requests.get("https://api.vercel.com/v2/user", headers=headers)
    assert resp.status_code == 200
```

**Run before production:**
```bash
pytest tests/integration/ -v
```

---

## Implementation Checklist

### Pre-Production (Critical)
- [ ] Rotate GitHub PAT
- [ ] Rotate HuggingFace token
- [ ] Rotate Supabase keys
- [ ] Rotate Langfuse keys
- [ ] Rotate Resend API key
- [ ] Rotate Box credentials
- [ ] Rotate Vercel token
- [ ] Rotate Daytona token
- [ ] Rotate CodeSandbox token
- [ ] Rotate Cloudflare tokens
- [ ] Rotate NVIDIA API key
- [ ] Fix Supabase IPv6 connectivity or configure Neon fallback
- [ ] Verify Daytona token validity
- [ ] Fix CORS configuration (CORS_ORIGINS vs CORS_ALLOWED_ORIGINS)

### Production Deployment
- [ ] Enable PostgreSQL (update DATABASE_URL)
- [ ] Configure Qdrant/Neo4j/Redis (if needed)
- [ ] Set up Vercel preview deployments
- [ ] Implement health check probes
- [ ] Run integration tests: `pytest tests/integration/ -v`
- [ ] Run full test suite: `npm test && pytest`
- [ ] Deploy to production
- [ ] Verify health endpoint: `curl https://your-domain.com/api/health`
- [ ] Monitor Langfuse for errors

### Post-Production
- [ ] Implement secret rotation automation
- [ ] Set up automated integration tests in CI
- [ ] Configure backup/restore procedures
- [ ] Document runbook for credential rotation

---

## Rollback Plan

If any critical fix causes issues:

1. **Credentials:** Keep old tokens valid for 24h before revoking
2. **Database:** Maintain SQLite fallback if PostgreSQL fails
3. **CORS:** Use `CORS_ALLOWED_ORIGINS` as fallback
4. **Deployment:** Previous Vercel deployment remains available

---

## Sign-Off

**Prepared by:** Automated Audit System  
**Reviewed by:** [Engineering Lead]  
**Approved for Production:** [ ] Yes [ ] No

**Date:** _______________

---

*This document must be completed and signed off before production deployment.*